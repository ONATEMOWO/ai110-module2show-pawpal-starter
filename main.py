"""Deterministic CLI demo of PawPal+ (fixed date and sample data, no clock use).

Run with:  python3 main.py
"""

from __future__ import annotations

import tempfile
from datetime import date, datetime, time
from pathlib import Path

from formatting import format_conflicts, format_plan, format_task_table, section
from pawpal_system import (
    Frequency,
    Owner,
    Pet,
    Priority,
    Scheduler,
    Task,
    load_owner,
    save_owner,
)

DAY = date(2026, 3, 2)  # a Monday


def at(hour: int, minute: int = 0, day: date = DAY) -> datetime:
    return datetime.combine(day, time(hour, minute))


def build_demo() -> tuple[Owner, Scheduler]:
    """Sample data, added deliberately out of chronological order."""
    owner = Owner("Jordan", daily_budget_minutes=120, preferred_categories=["meds", "feeding"])
    owner.add_pet(Pet("Mochi", "dog"))
    owner.add_pet(Pet("Whiskers", "cat"))
    sched = Scheduler(owner)
    sched.add_task("Whiskers", Task("Flea medication", at(18), 5, Priority.HIGH,
                                    Frequency.WEEKLY, "meds"))
    sched.add_task("Mochi", Task("Evening walk", at(17, 30), 40, Priority.MEDIUM,
                                 Frequency.NONE, "walk"))
    sched.add_task("Mochi", Task("Grooming", at(9), 45, Priority.MEDIUM,
                                 Frequency.NONE, "grooming"))
    sched.add_task("Whiskers", Task("Playtime", at(9, 30), 30, Priority.LOW,
                                    Frequency.NONE, "enrichment"))
    sched.add_task("Mochi", Task("Training", at(12), 30, Priority.MEDIUM,
                                 Frequency.NONE, "enrichment"))
    sched.add_task("Whiskers", Task("Breakfast", at(8), 15, Priority.HIGH,
                                    Frequency.DAILY, "feeding"))
    sched.add_task("Mochi", Task("Morning walk", at(7, 30), 30, Priority.HIGH,
                                 Frequency.DAILY, "walk"))
    return owner, sched


def find(owner: Owner, description: str) -> Task:
    return next(t for t in owner.all_tasks() if t.description == description)


def main() -> None:
    owner, sched = build_demo()
    print(f"PawPal+ demo for {owner.name} - pets: "
          f"{', '.join(f'{p.name} ({p.species})' for p in owner.pets)}")

    print(section("1. Everything, sorted chronologically (added out of order)"))
    print(format_task_table(sched, sched.sort_by_time()))

    print(section("2. Filtering"))
    print("  Mochi only:")
    print(format_task_table(sched, sched.filter_tasks(pet_name="Mochi")))
    print("\n  Whiskers, Monday 2 Mar, not completed:")
    print(format_task_table(sched, sched.filter_tasks("Whiskers", completed=False, on_date=DAY)))

    print(section("3. Conflict detection (across pets; back-to-back is fine)"))
    print(format_conflicts(sched.detect_conflicts()))
    print("  Note: Morning walk 07:30-08:00 and Breakfast 08:00-08:15 touch but do not conflict.")

    print(section("4. Daily plan, 120-minute budget"))
    print(format_plan(sched.build_daily_plan(DAY)))

    print(section("5. Same day, smaller budget (60 min): fewer tasks selected"))
    print(format_plan(sched.build_daily_plan(DAY, 60)))

    print(section("6. Priority changes the outcome: Playtime LOW -> HIGH (120 min)"))
    playtime = find(owner, "Playtime")
    playtime.priority = Priority.HIGH
    print(format_plan(sched.build_daily_plan(DAY)))
    playtime.priority = Priority.LOW  # restore sample data

    print(section("7. Next available slot (window 07:00-21:00)"))
    start, end = at(7), at(21)
    for minutes in (30, 60, 600):
        slot = sched.find_next_available_slot(minutes, start, end)
        print(f"  {minutes:>3} min -> {slot:%H:%M}" if slot else f"  {minutes:>3} min -> no slot")

    print(section("8. Recurring tasks"))
    walk = find(owner, "Morning walk")
    reference = at(10, 0, date(2026, 3, 3))
    following = sched.complete_task(walk.id, completed_at=reference)
    print(f"  Completed 'Morning walk' (was {walk.scheduled_at:%a %d %b %H:%M}) "
          f"late, at {reference:%a %d %b %H:%M}.")
    print(f"  Next occurrence: {following.scheduled_at:%a %d %b %H:%M} "
          "(strictly after the completion time; no backlog)")
    print(f"  Completing it again creates another? {sched.complete_task(walk.id) is not None}")
    flea = find(owner, "Flea medication")
    weekly = sched.complete_task(flea.id)
    print(f"  Weekly 'Flea medication' completed -> next {weekly.scheduled_at:%a %d %b %H:%M}")
    print(format_task_table(sched, sched.filter_tasks("Mochi")))

    print(section("9. JSON persistence (temporary file)"))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "pawpal_demo.json"
        save_owner(owner, path)
        loaded = load_owner(path)
        print(f"  Saved {len(owner.all_tasks())} tasks and reloaded "
              f"{len(loaded.all_tasks())} tasks for {loaded.name}.")
        print(f"  Round-trip identical: {loaded == owner}")
        print(f"  Completion preserved: {find(loaded, 'Morning walk').completed}; "
              f"recurrence preserved: {find(loaded, 'Breakfast').frequency.value}")


if __name__ == "__main__":
    main()
