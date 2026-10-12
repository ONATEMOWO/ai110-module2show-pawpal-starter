"""PawPal+ domain model: Owner, Pet, Task and Scheduler.

Design rules:
- Pets own their tasks. The Scheduler keeps no task data of its own; it reads
  tasks through the Owner, so there is a single source of truth. The Owner is
  the only place that maps a task back to its pet (Task has no pet field, so
  there is no redundant state that could disagree with Pet.name).
- Nothing here reads the system clock. Callers pass dates/datetimes in, which
  keeps sorting, recurrence, planning and conflict checks deterministic.
- All datetimes are NAIVE local times. Time zones and daylight-saving changes
  are out of scope for this project; tz-aware datetimes are rejected.
- A task occupies the half-open interval [scheduled_at, end_time), so
  back-to-back tasks do not conflict.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

SCHEMA_VERSION = 1
DEFAULT_CATEGORY = "general"


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class PawPalError(Exception):
    """Base class for PawPal domain errors (bad input raises ValueError)."""


class DuplicateError(PawPalError):
    """A pet name, task id or recurrence occurrence already exists."""


class NotFoundError(PawPalError):
    """A pet or task could not be found."""


class PersistenceError(PawPalError):
    """Saved data could not be read or is invalid."""


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------
class Priority(IntEnum):
    """Task priority. Integer values so priorities sort and compare directly."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @classmethod
    def from_str(cls, value: str) -> Priority:
        """Parse 'low' / 'medium' / 'high' (case-insensitive), e.g. from the UI."""
        try:
            return cls[str(value).strip().upper()]
        except KeyError:
            raise ValueError(f"Unknown priority: {value!r}") from None


class Frequency(Enum):
    """How often a task repeats."""

    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"

    def interval(self) -> Optional[timedelta]:
        """Time between occurrences (1 day, 7 days), or None for NONE."""
        return {
            Frequency.NONE: None,
            Frequency.DAILY: timedelta(days=1),
            Frequency.WEEKLY: timedelta(days=7),
        }[self]


def _new_id() -> str:
    return uuid4().hex


def _check_naive(value: datetime, label: str) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{label} must be a datetime")
    if value.tzinfo is not None:
        raise ValueError(f"{label} must be a naive datetime (time zones unsupported)")


# --------------------------------------------------------------------------
# Task
# --------------------------------------------------------------------------
@dataclass
class Task:
    """One pet-care activity with a start time, a duration and a priority."""

    description: str
    scheduled_at: datetime
    duration_minutes: int
    priority: Priority = Priority.MEDIUM
    frequency: Frequency = Frequency.NONE
    category: str = DEFAULT_CATEGORY
    completed: bool = False
    id: str = field(default_factory=_new_id)
    # Shared by every occurrence of a recurring task; defaults to the task's own id.
    series_id: str = ""

    def __post_init__(self) -> None:
        self.description = str(self.description).strip()
        if not self.description:
            raise ValueError("Task description must not be empty")
        _check_naive(self.scheduled_at, "scheduled_at")
        if (
            isinstance(self.duration_minutes, bool)
            or not isinstance(self.duration_minutes, int)
            or self.duration_minutes <= 0
        ):
            raise ValueError("duration_minutes must be a positive integer")
        if not isinstance(self.priority, Priority):
            raise ValueError("priority must be a Priority")
        if not isinstance(self.frequency, Frequency):
            raise ValueError("frequency must be a Frequency")
        self.category = str(self.category).strip().lower() or DEFAULT_CATEGORY
        if not self.id:
            raise ValueError("Task id must not be empty")
        if not self.series_id:
            self.series_id = self.id

    @property
    def end_time(self) -> datetime:
        """scheduled_at + duration_minutes (exclusive end of the interval)."""
        return self.scheduled_at + timedelta(minutes=self.duration_minutes)

    def overlaps(self, other: Task) -> bool:
        """True if the half-open intervals [start, end) intersect."""
        return self.scheduled_at < other.end_time and other.scheduled_at < self.end_time

    def next_occurrence(self, after: datetime) -> Optional[Task]:
        """Next occurrence strictly after `after`, or None for a one-off task.

        Advances from this task's original cadence (start + k * interval) and
        takes the first slot strictly after `after`, so completing late never
        creates a backlog of missed instances. The new task is incomplete, has a
        fresh id and keeps the series_id.
        """
        interval = self.frequency.interval()
        if interval is None:
            return None
        _check_naive(after, "after")
        periods = max(1, (after - self.scheduled_at) // interval + 1)
        return replace(
            self,
            id=_new_id(),
            scheduled_at=self.scheduled_at + periods * interval,
            completed=False,
        )

    def mark_complete(self, completed_at: Optional[datetime] = None) -> Optional[Task]:
        """Mark done and return the next occurrence (DAILY/WEEKLY) or None.

        `completed_at` is the reference time for recurrence and defaults to
        scheduled_at (completed on time). Completing an already-completed task
        is a no-op that returns None, so it can never spawn duplicates.
        """
        if self.completed:
            return None
        self.completed = True
        return self.next_occurrence(completed_at or self.scheduled_at)

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation (ISO datetime, enum names/values)."""
        return {
            "id": self.id,
            "series_id": self.series_id,
            "description": self.description,
            "scheduled_at": self.scheduled_at.isoformat(),
            "duration_minutes": self.duration_minutes,
            "priority": self.priority.name,
            "frequency": self.frequency.value,
            "category": self.category,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Task:
        """Rebuild a Task; raises PersistenceError on missing/invalid fields."""
        d = _require_dict(data, "task")
        try:
            return cls(
                description=_require(d, "description", str),
                scheduled_at=datetime.fromisoformat(_require(d, "scheduled_at", str)),
                duration_minutes=_require(d, "duration_minutes", int),
                priority=Priority[_require(d, "priority", str)],
                frequency=Frequency(_require(d, "frequency", str)),
                category=_require(d, "category", str),
                completed=_require(d, "completed", bool),
                id=_require(d, "id", str),
                series_id=_require(d, "series_id", str),
            )
        except (ValueError, KeyError) as exc:
            raise PersistenceError(f"Invalid task data: {exc}") from exc


# --------------------------------------------------------------------------
# Pet
# --------------------------------------------------------------------------
@dataclass
class Pet:
    """A pet and the tasks that belong to it."""

    name: str
    species: str = "other"
    tasks: list[Task] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("Pet name must not be empty")
        initial, self.tasks = list(self.tasks), []
        for task in initial:
            self.add_task(task)

    def add_task(self, task: Task) -> None:
        """Attach a task, rejecting duplicate ids and duplicate recurrence slots.

        Two tasks with the same (series_id, scheduled_at) are the same
        occurrence. Distinct tasks at the same time are allowed; they are a
        scheduling conflict, not a duplicate.
        """
        for existing in self.tasks:
            if existing.id == task.id:
                raise DuplicateError(f"Task id {task.id} already exists for {self.name}")
            if (
                existing.series_id == task.series_id
                and existing.scheduled_at == task.scheduled_at
            ):
                raise DuplicateError(
                    f"'{task.description}' already has an occurrence at {task.scheduled_at}"
                )
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> bool:
        """Remove a task by id. Return False if it was not found."""
        for i, task in enumerate(self.tasks):
            if task.id == task_id:
                del self.tasks[i]
                return True
        return False

    def get_task(self, task_id: str) -> Optional[Task]:
        """Look up a task by id."""
        return next((t for t in self.tasks if t.id == task_id), None)

    def list_tasks(self) -> list[Task]:
        """A copy of this pet's tasks in insertion order."""
        return list(self.tasks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "species": self.species,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: Any) -> Pet:
        d = _require_dict(data, "pet")
        tasks_raw = _require(d, "tasks", list)
        try:
            return cls(
                name=_require(d, "name", str),
                species=_require(d, "species", str),
                tasks=[Task.from_dict(t) for t in tasks_raw],
            )
        except (ValueError, DuplicateError) as exc:
            raise PersistenceError(f"Invalid pet data: {exc}") from exc


# --------------------------------------------------------------------------
# Owner
# --------------------------------------------------------------------------
@dataclass
class Owner:
    """The single user: owns pets, a daily time budget and planning preferences."""

    name: str
    daily_budget_minutes: int = 180
    # Tie-break order for equal-priority tasks: earlier categories win.
    preferred_categories: list[str] = field(default_factory=list)
    # Waking hours: the default window for next-available-slot searches.
    day_start: time = time(7, 0)
    day_end: time = time(21, 0)
    pets: list[Pet] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("Owner name must not be empty")
        if (
            isinstance(self.daily_budget_minutes, bool)
            or not isinstance(self.daily_budget_minutes, int)
            or self.daily_budget_minutes <= 0
        ):
            raise ValueError("daily_budget_minutes must be a positive integer")
        if self.day_end <= self.day_start:
            raise ValueError("day_end must be after day_start")
        self.preferred_categories = [c.strip().lower() for c in self.preferred_categories]
        initial, self.pets = list(self.pets), []
        for pet in initial:
            self.add_pet(pet)

    def add_pet(self, pet: Pet) -> None:
        """Add a pet. Names are unique per owner (case-insensitive) and task ids
        are unique across all of the owner's pets."""
        if self.get_pet(pet.name) is not None:
            raise DuplicateError(f"A pet named '{pet.name}' already exists")
        known = {t.id for t in self.all_tasks()}
        if any(t.id in known for t in pet.tasks):
            raise DuplicateError(f"Pet '{pet.name}' has a task id already in use")
        self.pets.append(pet)

    def get_pet(self, name: str) -> Optional[Pet]:
        """Look up a pet by name (case-insensitive)."""
        key = str(name).strip().lower()
        return next((p for p in self.pets if p.name.lower() == key), None)

    def list_pets(self) -> list[Pet]:
        return list(self.pets)

    def all_tasks(self) -> list[Task]:
        """Every task across every pet: pets in insertion order, then tasks."""
        return [t for pet in self.pets for t in pet.tasks]

    def find_task(self, task_id: str) -> Optional[tuple[Pet, Task]]:
        """The (pet, task) pair for an id, or None."""
        for pet in self.pets:
            task = pet.get_task(task_id)
            if task is not None:
                return pet, task
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "name": self.name,
            "daily_budget_minutes": self.daily_budget_minutes,
            "preferred_categories": list(self.preferred_categories),
            "day_start": self.day_start.isoformat(timespec="minutes"),
            "day_end": self.day_end.isoformat(timespec="minutes"),
            "pets": [p.to_dict() for p in self.pets],
        }

    @classmethod
    def from_dict(cls, data: Any) -> Owner:
        d = _require_dict(data, "owner")
        if d.get("version") != SCHEMA_VERSION:
            raise PersistenceError(f"Unsupported data version: {d.get('version')!r}")
        cats = _require(d, "preferred_categories", list)
        if not all(isinstance(c, str) for c in cats):
            raise PersistenceError("preferred_categories must be a list of strings")
        try:
            return cls(
                name=_require(d, "name", str),
                daily_budget_minutes=_require(d, "daily_budget_minutes", int),
                preferred_categories=cats,
                day_start=time.fromisoformat(_require(d, "day_start", str)),
                day_end=time.fromisoformat(_require(d, "day_end", str)),
                pets=[Pet.from_dict(p) for p in _require(d, "pets", list)],
            )
        except (ValueError, DuplicateError) as exc:
            raise PersistenceError(f"Invalid owner data: {exc}") from exc


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Conflict:
    """Two incomplete tasks whose time intervals overlap."""

    first: Task
    second: Task
    first_pet: str
    second_pet: str
    overlap_minutes: int

    @property
    def cross_pet(self) -> bool:
        return self.first_pet != self.second_pet


@dataclass(frozen=True)
class PlanEntry:
    """A task in a daily plan with a short explanation of the decision."""

    task: Task
    pet_name: str
    reason: str


@dataclass(frozen=True)
class DailyPlan:
    """Result of Scheduler.build_daily_plan (both lists are chronological)."""

    day: date
    budget_minutes: int
    selected: list[PlanEntry]
    skipped: list[PlanEntry]

    @property
    def minutes_used(self) -> int:
        return sum(e.task.duration_minutes for e in self.selected)

    @property
    def minutes_free(self) -> int:
        return self.budget_minutes - self.minutes_used


# --------------------------------------------------------------------------
# Scheduler
# --------------------------------------------------------------------------
class Scheduler:
    """Organizes, checks and plans tasks across all of an owner's pets."""

    def __init__(self, owner: Owner) -> None:
        self.owner = owner

    # -- helpers ----------------------------------------------------------
    def _pet_names(self) -> dict[str, str]:
        return {t.id: pet.name for pet in self.owner.pets for t in pet.tasks}

    def pet_name_of(self, task_id: str) -> str:
        """Name of the pet that owns the task ('' if unknown)."""
        return self._pet_names().get(task_id, "")

    # -- mutation ---------------------------------------------------------
    def add_task(self, pet_name: str, task: Task) -> list[Conflict]:
        """Add a task to the named pet and return the conflicts it creates.

        Conflicts are a warning, not a rejection. Raises NotFoundError for an
        unknown pet and DuplicateError for a reused id or recurrence slot.
        """
        pet = self.owner.get_pet(pet_name)
        if pet is None:
            raise NotFoundError(f"No pet named '{pet_name}'")
        if self.owner.find_task(task.id) is not None:
            raise DuplicateError(f"Task id {task.id} already exists")
        pet.add_task(task)
        return self.conflicts_for(task.id)

    def complete_task(
        self, task_id: str, completed_at: Optional[datetime] = None
    ) -> Optional[Task]:
        """Complete a task and, if it recurs, add its next occurrence to the same pet.

        Returns the new occurrence, or None if the task is one-off, was already
        completed, or its next occurrence already exists. Raises NotFoundError
        for an unknown id.
        """
        found = self.owner.find_task(task_id)
        if found is None:
            raise NotFoundError(f"No task with id {task_id}")
        pet, task = found
        following = task.mark_complete(completed_at)
        if following is None:
            return None
        try:
            pet.add_task(following)
        except DuplicateError:
            return None
        return following

    # -- sorting / filtering ----------------------------------------------
    def sort_by_time(self, tasks: Optional[list[Task]] = None) -> list[Task]:
        """Chronological order. Ties break by higher priority, then pet name,
        then description; remaining ties keep insertion order (stable sort)."""
        names = self._pet_names()
        source = self.owner.all_tasks() if tasks is None else list(tasks)
        return sorted(
            source,
            key=lambda t: (
                t.scheduled_at,
                -int(t.priority),
                names.get(t.id, "").lower(),
                t.description.lower(),
            ),
        )

    def filter_tasks(
        self,
        pet_name: Optional[str] = None,
        completed: Optional[bool] = None,
        on_date: Optional[date] = None,
    ) -> list[Task]:
        """Tasks matching every non-None filter, chronologically.

        `on_date` matches the task's start date (a task running past midnight
        belongs to the day it starts).
        """
        if pet_name is None:
            tasks = self.owner.all_tasks()
        else:
            pet = self.owner.get_pet(pet_name)
            tasks = pet.list_tasks() if pet else []
        if completed is not None:
            tasks = [t for t in tasks if t.completed == completed]
        if on_date is not None:
            tasks = [t for t in tasks if t.scheduled_at.date() == on_date]
        return self.sort_by_time(tasks)

    # -- conflicts --------------------------------------------------------
    def detect_conflicts(self) -> list[Conflict]:
        """All overlapping pairs of incomplete tasks, across every pet.

        Sweep over tasks sorted by start: for each task, later tasks that start
        before it ends overlap it. Back-to-back tasks and completed tasks never
        conflict. Returns pairs in chronological order of the earlier task.
        """
        names = self._pet_names()
        active = self.sort_by_time([t for t in self.owner.all_tasks() if not t.completed])
        found: list[Conflict] = []
        for i, a in enumerate(active):
            for b in active[i + 1:]:
                if b.scheduled_at >= a.end_time:
                    break
                overlap = min(a.end_time, b.end_time) - b.scheduled_at
                found.append(
                    Conflict(
                        first=a,
                        second=b,
                        first_pet=names.get(a.id, ""),
                        second_pet=names.get(b.id, ""),
                        overlap_minutes=int(overlap.total_seconds() // 60),
                    )
                )
        return found

    def conflicts_for(self, task_id: str) -> list[Conflict]:
        """Conflicts that involve the given task."""
        return [
            c for c in self.detect_conflicts() if task_id in (c.first.id, c.second.id)
        ]

    # -- planning ---------------------------------------------------------
    def build_daily_plan(
        self, day: date, budget_minutes: Optional[int] = None
    ) -> DailyPlan:
        """Greedy, deterministic plan for one day within a minute budget.

        Candidates are the incomplete tasks starting on `day`; their start times
        are fixed. They are ranked by (1) higher priority, (2) the owner's
        preferred_categories order, (3) earlier start, (4) description, then
        insertion order. Walking that ranking, a task is selected unless it
        overlaps an already-selected task or its duration exceeds the minutes
        left; skipped tasks get the reason. A skipped task never stops later,
        smaller tasks from fitting. Tasks are not modified.
        """
        budget = self.owner.daily_budget_minutes if budget_minutes is None else budget_minutes
        if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
            raise ValueError("budget_minutes must be a non-negative integer")

        names = self._pet_names()
        prefs = self.owner.preferred_categories
        candidates = [
            t
            for t in self.owner.all_tasks()
            if not t.completed and t.scheduled_at.date() == day
        ]
        order = {t.id: i for i, t in enumerate(candidates)}

        def rank(t: Task) -> tuple:
            pref = prefs.index(t.category) if t.category in prefs else len(prefs)
            return (-int(t.priority), pref, t.scheduled_at, t.description.lower(), order[t.id])

        selected: list[PlanEntry] = []
        skipped: list[PlanEntry] = []
        chosen: list[Task] = []
        used = 0
        for task in sorted(candidates, key=rank):
            pet = names.get(task.id, "")
            clash = next((c for c in chosen if task.overlaps(c)), None)
            if clash is not None:
                reason = (
                    f"Overlaps '{clash.description}' "
                    f"({_hhmm(clash.scheduled_at)}-{_hhmm(clash.end_time)}), "
                    "which ranked higher"
                )
                skipped.append(PlanEntry(task, pet, reason))
            elif task.duration_minutes > budget - used:
                reason = (
                    f"Needs {task.duration_minutes} min but only {budget - used} min "
                    f"left in the {budget}-min budget"
                )
                skipped.append(PlanEntry(task, pet, reason))
            else:
                used += task.duration_minutes
                reason = f"{task.priority.name.capitalize()} priority; fits the budget"
                chosen.append(task)
                selected.append(PlanEntry(task, pet, reason))

        by_time = lambda e: (e.task.scheduled_at, order[e.task.id])  # noqa: E731
        return DailyPlan(day, budget, sorted(selected, key=by_time), sorted(skipped, key=by_time))

    def find_next_available_slot(
        self, duration_minutes: int, window_start: datetime, window_end: datetime
    ) -> Optional[datetime]:
        """Earliest start in [window_start, window_end] where a task of this
        length fits without overlapping any incomplete task of any pet.

        The slot must end by window_end. Adjacent tasks do not block (intervals
        are half-open). Returns None if nothing fits. Completed tasks are free
        time. Raises ValueError for a non-positive duration or reversed window.
        """
        if (
            isinstance(duration_minutes, bool)
            or not isinstance(duration_minutes, int)
            or duration_minutes <= 0
        ):
            raise ValueError("duration_minutes must be a positive integer")
        _check_naive(window_start, "window_start")
        _check_naive(window_end, "window_end")
        if window_end < window_start:
            raise ValueError("window_end must not be before window_start")

        need = timedelta(minutes=duration_minutes)
        busy = sorted(
            (t for t in self.owner.all_tasks()
             if not t.completed and t.end_time > window_start and t.scheduled_at < window_end),
            key=lambda t: t.scheduled_at,
        )
        cursor = window_start
        for task in busy:
            if cursor + need <= task.scheduled_at:
                return cursor
            cursor = max(cursor, task.end_time)
        return cursor if cursor + need <= window_end else None


def _hhmm(value: datetime) -> str:
    return value.strftime("%H:%M")


# --------------------------------------------------------------------------
# Persistence helpers (JSON, standard library only)
# --------------------------------------------------------------------------
def _require_dict(data: Any, label: str) -> dict:
    if not isinstance(data, dict):
        raise PersistenceError(f"Expected an object for {label}")
    return data


def _require(data: dict, key: str, expected: type) -> Any:
    if key not in data:
        raise PersistenceError(f"Missing field '{key}'")
    value = data[key]
    # bool is a subclass of int; never accept it where an int is expected.
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise PersistenceError(f"Field '{key}' must be {expected.__name__}")
    return value


def save_owner(owner: Owner, path: str | Path) -> None:
    """Write the owner, pets and tasks to a JSON file (replaced atomically)."""
    target = Path(path)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(owner.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp, target)


def load_owner(path: str | Path) -> Owner:
    """Read an Owner (with real Pet/Task objects) from a JSON file.

    Raises PersistenceError if the file is missing, not valid JSON, or fails
    validation.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PersistenceError(f"Cannot read {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PersistenceError(f"{path} is not valid JSON: {exc}") from exc
    return Owner.from_dict(data)
