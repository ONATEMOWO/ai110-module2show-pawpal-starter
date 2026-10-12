"""Deterministic tests for PawPal+ (no clock, network or external files)."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from pawpal_system import (
    DuplicateError,
    Frequency,
    NotFoundError,
    Owner,
    Pet,
    PersistenceError,
    Priority,
    Scheduler,
    Task,
    load_owner,
    save_owner,
)

DAY = date(2026, 3, 2)


def dt(hour, minute=0, day=DAY):
    return datetime(day.year, day.month, day.day, hour, minute)


def task(desc="Walk", hour=8, minute=0, duration=30, **kw):
    return Task(desc, dt(hour, minute), duration, **kw)


@pytest.fixture
def setup():
    owner = Owner("Jordan", daily_budget_minutes=120)
    owner.add_pet(Pet("Mochi", "dog"))
    owner.add_pet(Pet("Whiskers", "cat"))
    return owner, Scheduler(owner)


# ---------------------------------------------------------------- tasks / pets
def test_task_completion_marks_done_and_one_off_has_no_next():
    t = task()
    assert t.completed is False
    assert t.mark_complete() is None
    assert t.completed is True


def test_end_time_and_validation():
    assert task(hour=8, duration=45).end_time == dt(8, 45)
    for bad in (0, -5, 1.5, True):
        with pytest.raises(ValueError):
            task(duration=bad)
    with pytest.raises(ValueError):
        task(desc="   ")
    with pytest.raises(ValueError):
        Task("x", datetime(2026, 3, 2, 8, tzinfo=timezone.utc), 10)


def test_pet_add_task_and_lookup():
    pet = Pet("Mochi")
    t = task()
    pet.add_task(t)
    assert pet.list_tasks() == [t] and pet.get_task(t.id) is t
    assert pet.remove_task(t.id) is True
    assert pet.remove_task(t.id) is False and pet.tasks == []


def test_pet_rejects_duplicate_id_but_allows_same_time_distinct_task():
    pet = Pet("Mochi")
    a = task("Walk")
    pet.add_task(a)
    with pytest.raises(DuplicateError):
        pet.add_task(a)
    pet.add_task(task("Feed"))  # same start time, different task: allowed
    assert len(pet.tasks) == 2


def test_owner_pets_unique_and_multi_pet_aggregation(setup):
    owner, sched = setup
    sched.add_task("Mochi", task("Walk", 8))
    sched.add_task("Whiskers", task("Feed", 9))
    assert {t.description for t in owner.all_tasks()} == {"Walk", "Feed"}
    assert sched.pet_name_of(owner.all_tasks()[1].id) == "Whiskers"
    with pytest.raises(DuplicateError):
        owner.add_pet(Pet("mochi"))
    with pytest.raises(NotFoundError):
        sched.add_task("Rex", task())


def test_task_id_unique_across_pets(setup):
    _, sched = setup
    t = task()
    sched.add_task("Mochi", t)
    with pytest.raises(DuplicateError):
        sched.add_task("Whiskers", t)


# ------------------------------------------------------------ sorting / filter
def test_chronological_sort_with_deterministic_tie_breaks(setup):
    _, sched = setup
    sched.add_task("Mochi", task("Late", 15))
    sched.add_task("Whiskers", task("B low", 9, priority=Priority.LOW))
    sched.add_task("Mochi", task("A high", 9, priority=Priority.HIGH))
    sched.add_task("Mochi", task("Early", 7))
    order = [t.description for t in sched.sort_by_time()]
    assert order == ["Early", "A high", "B low", "Late"]


def test_filtering_by_pet_status_and_date(setup):
    _, sched = setup
    a = task("Walk", 8)
    sched.add_task("Mochi", a)
    sched.add_task("Mochi", Task("Next day", dt(8, day=DAY + timedelta(days=1)), 20))
    sched.add_task("Whiskers", task("Feed", 9))
    a.mark_complete()
    assert [t.description for t in sched.filter_tasks(pet_name="Whiskers")] == ["Feed"]
    assert [t.description for t in sched.filter_tasks(completed=True)] == ["Walk"]
    assert [t.description for t in sched.filter_tasks("Mochi", False, DAY)] == []
    assert [t.description for t in sched.filter_tasks(on_date=DAY)] == ["Walk", "Feed"]
    assert sched.filter_tasks(pet_name="Nobody") == []


# ------------------------------------------------------------------- conflicts
def test_conflict_across_pets_with_partial_overlap(setup):
    _, sched = setup
    sched.add_task("Mochi", task("Groom", 9, duration=45))
    warnings = sched.add_task("Whiskers", task("Play", 9, 30, duration=30))
    assert len(warnings) == 1
    c = warnings[0]
    assert (c.first.description, c.second.description) == ("Groom", "Play")
    assert c.overlap_minutes == 15 and c.cross_pet


def test_full_containment_and_same_start_are_conflicts(setup):
    _, sched = setup
    sched.add_task("Mochi", task("Long", 9, duration=60))
    sched.add_task("Mochi", task("Inside", 9, 15, duration=10))
    sched.add_task("Whiskers", task("Same start", 9, duration=30))
    pairs = {(c.first.description, c.second.description) for c in sched.detect_conflicts()}
    assert ("Long", "Inside") in pairs and ("Long", "Same start") in pairs
    assert ("Same start", "Inside") in pairs  # 9:15-9:25 inside 9:00-9:30


def test_adjacent_tasks_do_not_conflict(setup):
    _, sched = setup
    sched.add_task("Mochi", task("A", 8, duration=30))
    assert sched.add_task("Whiskers", task("B", 8, 30, duration=30)) == []
    assert sched.detect_conflicts() == []


def test_completed_tasks_do_not_conflict(setup):
    _, sched = setup
    a = task("A", 8)
    sched.add_task("Mochi", a)
    sched.add_task("Whiskers", task("B", 8, 10))
    assert len(sched.detect_conflicts()) == 1
    a.mark_complete()
    assert sched.detect_conflicts() == []


# ------------------------------------------------------------------ recurrence
def test_daily_recurrence_creates_next_day(setup):
    owner, sched = setup
    t = task("Feed", 8, frequency=Frequency.DAILY)
    sched.add_task("Mochi", t)
    nxt = sched.complete_task(t.id)
    assert nxt.scheduled_at == dt(8, day=DAY + timedelta(days=1))
    assert nxt.series_id == t.series_id and nxt.id != t.id and not nxt.completed
    assert nxt in owner.get_pet("Mochi").tasks


def test_weekly_recurrence_creates_next_week(setup):
    _, sched = setup
    t = task("Bath", 18, frequency=Frequency.WEEKLY)
    sched.add_task("Mochi", t)
    assert sched.complete_task(t.id).scheduled_at == dt(18, day=DAY + timedelta(days=7))


def test_late_completion_skips_missed_days_without_backlog(setup):
    owner, sched = setup
    t = task("Feed", 8, frequency=Frequency.DAILY)
    sched.add_task("Mochi", t)
    late = dt(10, day=DAY + timedelta(days=3))  # 3 days later, after 08:00
    nxt = sched.complete_task(t.id, completed_at=late)
    assert nxt.scheduled_at == dt(8, day=DAY + timedelta(days=4))
    assert len(owner.all_tasks()) == 2  # original + exactly one next


def test_next_occurrence_is_strictly_after_reference(setup):
    t = task("Feed", 8, frequency=Frequency.DAILY)
    exactly_next = dt(8, day=DAY + timedelta(days=1))
    assert t.next_occurrence(exactly_next).scheduled_at == dt(8, day=DAY + timedelta(days=2))
    early = t.next_occurrence(dt(6))  # completed before it was due
    assert early.scheduled_at == dt(8, day=DAY + timedelta(days=1))


def test_completing_twice_does_not_duplicate(setup):
    owner, sched = setup
    t = task("Feed", 8, frequency=Frequency.DAILY)
    sched.add_task("Mochi", t)
    assert sched.complete_task(t.id) is not None
    assert sched.complete_task(t.id) is None
    assert len(owner.all_tasks()) == 2


def test_duplicate_recurrence_occurrence_is_rejected_by_pet(setup):
    owner, sched = setup
    t = task("Feed", 8, frequency=Frequency.DAILY)
    sched.add_task("Mochi", t)
    clone = t.next_occurrence(t.scheduled_at)
    owner.get_pet("Mochi").add_task(clone)
    with pytest.raises(DuplicateError):
        owner.get_pet("Mochi").add_task(t.next_occurrence(t.scheduled_at))
    # if the next slot already exists, completing the original adds nothing
    assert sched.complete_task(t.id) is None
    assert len(owner.all_tasks()) == 2


def test_complete_unknown_task_raises(setup):
    with pytest.raises(NotFoundError):
        setup[1].complete_task("nope")


# -------------------------------------------------------------------- planning
def test_higher_priority_wins_budget_over_earlier_time(setup):
    _, sched = setup
    sched.add_task("Mochi", task("Early low", 8, duration=60, priority=Priority.LOW))
    sched.add_task("Mochi", task("Late high", 15, duration=60, priority=Priority.HIGH))
    plan = sched.build_daily_plan(DAY, 60)
    assert [e.task.description for e in plan.selected] == ["Late high"]
    assert "budget" in plan.skipped[0].reason and "60" in plan.skipped[0].reason


def test_changing_budget_changes_selection(setup):
    _, sched = setup
    sched.add_task("Mochi", task("A", 8, duration=30, priority=Priority.HIGH))
    sched.add_task("Mochi", task("B", 10, duration=30, priority=Priority.MEDIUM))
    sched.add_task("Mochi", task("C", 12, duration=30, priority=Priority.LOW))
    names = lambda p: [e.task.description for e in p.selected]  # noqa: E731
    assert names(sched.build_daily_plan(DAY, 30)) == ["A"]
    assert names(sched.build_daily_plan(DAY, 60)) == ["A", "B"]
    assert names(sched.build_daily_plan(DAY, 90)) == ["A", "B", "C"]


def test_changing_priority_changes_selection(setup):
    _, sched = setup
    a = task("A", 8, duration=40, priority=Priority.MEDIUM)
    b = task("B", 10, duration=40, priority=Priority.LOW)
    sched.add_task("Mochi", a)
    sched.add_task("Mochi", b)
    assert [e.task.description for e in sched.build_daily_plan(DAY, 50).selected] == ["A"]
    b.priority = Priority.HIGH
    assert [e.task.description for e in sched.build_daily_plan(DAY, 50).selected] == ["B"]


def test_plan_skips_overlap_with_reason_and_continues_to_smaller_tasks(setup):
    _, sched = setup
    sched.add_task("Mochi", task("Big", 8, duration=50, priority=Priority.HIGH))
    sched.add_task("Whiskers", task("Clash", 8, 30, duration=30, priority=Priority.MEDIUM))
    sched.add_task("Mochi", task("Too long", 12, duration=40, priority=Priority.MEDIUM))
    sched.add_task("Mochi", task("Small", 14, duration=10, priority=Priority.LOW))
    plan = sched.build_daily_plan(DAY, 60)
    assert [e.task.description for e in plan.selected] == ["Big", "Small"]
    reasons = {e.task.description: e.reason for e in plan.skipped}
    assert "Overlaps 'Big'" in reasons["Clash"]
    assert "Needs 40 min but only 10 min left" in reasons["Too long"]
    assert plan.minutes_used == 60 and plan.minutes_free == 0


def test_equal_priority_ties_use_category_preference_then_time(setup):
    owner, sched = setup
    owner.preferred_categories = ["meds"]
    sched.add_task("Mochi", task("Walk", 8, duration=30, category="walk"))
    sched.add_task("Mochi", task("Pill", 16, duration=30, category="meds"))
    assert [e.task.description for e in sched.build_daily_plan(DAY, 30).selected] == ["Pill"]
    owner.preferred_categories = []
    assert [e.task.description for e in sched.build_daily_plan(DAY, 30).selected] == ["Walk"]


def test_plan_ignores_completed_and_other_days_and_does_not_mutate(setup):
    owner, sched = setup
    done = task("Done", 8)
    done.completed = True
    sched.add_task("Mochi", done)
    sched.add_task("Mochi", Task("Tomorrow", dt(8, day=DAY + timedelta(days=1)), 10))
    sched.add_task("Mochi", task("Today", 9, frequency=Frequency.DAILY))
    before = [t.to_dict() for t in owner.all_tasks()]
    plan = sched.build_daily_plan(DAY)
    assert [e.task.description for e in plan.selected] == ["Today"]
    assert plan.skipped == []
    assert [t.to_dict() for t in owner.all_tasks()] == before


def test_plan_is_deterministic_and_uses_owner_budget_by_default(setup):
    owner, sched = setup
    for i in range(4):
        sched.add_task("Mochi", task(f"T{i}", 8 + i, duration=50))
    first = sched.build_daily_plan(DAY)
    assert first.budget_minutes == 120
    assert [e.task.description for e in first.selected] == ["T0", "T1"]
    assert first == sched.build_daily_plan(DAY)
    with pytest.raises(ValueError):
        sched.build_daily_plan(DAY, -1)


def test_empty_owner_and_empty_schedule():
    owner = Owner("Solo")
    sched = Scheduler(owner)
    assert owner.all_tasks() == [] and sched.sort_by_time() == []
    assert sched.detect_conflicts() == []
    plan = sched.build_daily_plan(DAY)
    assert plan.selected == [] and plan.skipped == []
    assert sched.find_next_available_slot(30, dt(7), dt(9)) == dt(7)
    assert sched.filter_tasks(completed=False) == []


# ------------------------------------------------------------- next free slot
def test_next_slot_skips_busy_blocks_across_pets(setup):
    _, sched = setup
    sched.add_task("Mochi", task("A", 7, duration=60))
    sched.add_task("Whiskers", task("B", 8, 30, duration=30))
    # 08:00-08:30 is free but only 30 min wide
    assert sched.find_next_available_slot(30, dt(7), dt(12)) == dt(8)
    assert sched.find_next_available_slot(45, dt(7), dt(12)) == dt(9)


def test_next_slot_adjacent_edges_and_exact_fit(setup):
    _, sched = setup
    sched.add_task("Mochi", task("A", 8, duration=60))
    assert sched.find_next_available_slot(60, dt(7), dt(8)) == dt(7)  # ends exactly at 08:00
    assert sched.find_next_available_slot(30, dt(8), dt(9)) is None   # window fully busy
    assert sched.find_next_available_slot(30, dt(8), dt(9, 30)) == dt(9)


def test_next_slot_none_when_nothing_fits_and_completed_tasks_are_free(setup):
    _, sched = setup
    a = task("A", 8, duration=120)
    sched.add_task("Mochi", a)
    assert sched.find_next_available_slot(90, dt(8), dt(11)) is None
    a.mark_complete()
    assert sched.find_next_available_slot(90, dt(8), dt(11)) == dt(8)


def test_next_slot_validation(setup):
    _, sched = setup
    for bad in (0, -1):
        with pytest.raises(ValueError):
            sched.find_next_available_slot(bad, dt(8), dt(9))
    with pytest.raises(ValueError):
        sched.find_next_available_slot(10, dt(9), dt(8))


# ----------------------------------------------------------------- persistence
def test_json_round_trip_preserves_everything(setup, tmp_path):
    owner, sched = setup
    owner.preferred_categories = ["meds"]
    t = task("Feed", 8, frequency=Frequency.DAILY, priority=Priority.HIGH, category="feeding")
    sched.add_task("Mochi", t)
    sched.complete_task(t.id, completed_at=dt(9))
    path = tmp_path / "data.json"
    save_owner(owner, path)
    loaded = load_owner(path)
    assert loaded == owner
    assert isinstance(loaded.pets[0], Pet) and isinstance(loaded.all_tasks()[0], Task)
    first = loaded.all_tasks()[0]
    assert first.completed and first.id == t.id and first.priority is Priority.HIGH
    assert first.frequency is Frequency.DAILY and first.series_id == t.series_id
    assert not Scheduler(loaded).complete_task(first.id)  # still idempotent after reload


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("pets"),
        lambda d: d.update(version=99),
        lambda d: d["pets"][0]["tasks"][0].update(duration_minutes=0),
        lambda d: d["pets"][0]["tasks"][0].update(scheduled_at="not-a-date"),
        lambda d: d["pets"][0]["tasks"][0].update(priority="URGENT"),
        lambda d: d["pets"][0]["tasks"][0].update(frequency="hourly"),
        lambda d: d["pets"][0]["tasks"][0].update(completed="yes"),
        lambda d: d["pets"][0]["tasks"][0].update(duration_minutes=True),
        lambda d: d["pets"].append(d["pets"][0]),
    ],
)
def test_invalid_saved_data_raises_persistence_error(setup, tmp_path, mutate):
    owner, sched = setup
    sched.add_task("Mochi", task())
    data = owner.to_dict()
    mutate(data)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(PersistenceError):
        load_owner(path)


def test_corrupt_and_missing_files_raise_persistence_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(PersistenceError):
        load_owner(bad)
    with pytest.raises(PersistenceError):
        load_owner(tmp_path / "missing.json")
