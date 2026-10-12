"""PawPal+ domain model: Owner, Pet, Task and Scheduler.

Phase 1 skeleton only. Every behaviour method is a stub that raises
NotImplementedError; the structure below is what the UML in
diagrams/uml_draft.mmd describes.

Design rules the implementation should follow:
- Pets own their tasks. The Scheduler never keeps its own copy of tasks, it
  reads them through the Owner, so there is one source of truth.
- Nothing here reads the system clock. Callers pass dates/datetimes in, which
  keeps sorting, recurrence and conflict checks deterministic and testable.
- Datetimes are naive (local time). Time zones are out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum, IntEnum
from typing import Optional
from uuid import uuid4


class Priority(IntEnum):
    """Task priority. Integer values so priorities sort and compare directly."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @classmethod
    def from_str(cls, value: str) -> Priority:
        """Parse 'low' / 'medium' / 'high' (case-insensitive), e.g. from the UI."""
        raise NotImplementedError


class Frequency(Enum):
    """How often a task repeats."""

    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"

    def interval(self) -> Optional[timedelta]:
        """Time between occurrences (1 day, 7 days), or None for ONCE."""
        raise NotImplementedError


def _new_id() -> str:
    return uuid4().hex


@dataclass
class Task:
    """One pet-care activity with a start time, a duration and a priority."""

    description: str
    scheduled_at: datetime
    duration_minutes: int
    priority: Priority = Priority.MEDIUM
    frequency: Frequency = Frequency.NONE
    category: str = "general"
    completed: bool = False
    id: str = field(default_factory=_new_id)
    # Shared by every occurrence of a recurring task; defaults to the task's own id.
    series_id: str = ""

    @property
    def end_time(self) -> datetime:
        """scheduled_at + duration_minutes."""
        raise NotImplementedError

    def overlaps(self, other: Task) -> bool:
        """True if the half-open intervals [start, end) intersect."""
        raise NotImplementedError

    def next_occurrence(self, after: datetime) -> Optional[Task]:
        """Next occurrence strictly after `after`, advancing from the original
        cadence (no backlog of missed instances). None for NONE frequency."""
        raise NotImplementedError

    def mark_complete(self, completed_at: Optional[datetime] = None) -> Optional[Task]:
        """Mark done. Return the next occurrence for DAILY/WEEKLY tasks, else None.

        `completed_at` is injectable (defaults to scheduled_at). Completing an
        already-completed task is a no-op that returns None.
        """
        raise NotImplementedError


@dataclass
class Pet:
    """A pet and the tasks that belong to it."""

    name: str
    species: str = "other"
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Attach a task. Reject duplicate ids and duplicate (series_id,
        scheduled_at) pairs so recurrence cannot double-book. Same-time tasks
        that are NOT the same series are allowed (they may conflict)."""
        raise NotImplementedError

    def remove_task(self, task_id: str) -> bool:
        """Remove a task by id. Return False if it was not found."""
        raise NotImplementedError

    def get_task(self, task_id: str) -> Optional[Task]:
        """Look up a task by id."""
        raise NotImplementedError


@dataclass
class Owner:
    """The single user; owns one or more pets."""

    name: str
    daily_budget_minutes: int = 180
    preferred_categories: list[str] = field(default_factory=list)  # tie-break order
    pets: list[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        """Add a pet. Pet names must be unique per owner (case-insensitive)."""
        raise NotImplementedError

    def get_pet(self, name: str) -> Optional[Pet]:
        """Look up a pet by name."""
        raise NotImplementedError

    def all_tasks(self) -> list[Task]:
        """Every task across every pet, in insertion order."""
        raise NotImplementedError

    def find_task(self, task_id: str) -> Optional[tuple[Pet, Task]]:
        """The (pet, task) pair for an id; the Owner is the only place that maps
        a task to its pet, so there is no redundant pet_name on Task."""
        raise NotImplementedError


@dataclass(frozen=True)
class Conflict:
    """Two incomplete tasks whose time intervals overlap."""

    first: Task
    second: Task
    first_pet: str
    second_pet: str
    overlap_minutes: int


@dataclass(frozen=True)
class PlanEntry:
    """A task in a daily plan with a short explanation of the decision."""

    task: Task
    pet_name: str
    reason: str


@dataclass(frozen=True)
class DailyPlan:
    """Result of Scheduler.build_daily_plan."""

    day: date
    budget_minutes: int
    selected: list[PlanEntry]
    skipped: list[PlanEntry]


class Scheduler:
    """Organizes and checks tasks across all of an owner's pets.

    Holds a reference to the Owner and reads tasks through it; it stores no
    task data of its own.
    """

    def __init__(self, owner: Owner) -> None:
        self.owner = owner

    def add_task(self, pet_name: str, task: Task) -> list[Conflict]:
        """Add a task to the named pet. Return any conflicts the new task creates
        (a warning, not a rejection)."""
        raise NotImplementedError

    def complete_task(
        self, task_id: str, completed_at: Optional[datetime] = None
    ) -> Optional[Task]:
        """Complete a task and, if it recurs, add the next occurrence to the same
        pet. Return the new occurrence or None."""
        raise NotImplementedError

    def build_daily_plan(
        self, day: date, budget_minutes: Optional[int] = None
    ) -> DailyPlan:
        """Greedy plan: rank the day's incomplete tasks by priority (then owner
        category preference, start time), take each that fits the minute budget
        and overlaps nothing already chosen; explain every decision."""
        raise NotImplementedError

    def find_next_available_slot(
        self, duration_minutes: int, window_start: datetime, window_end: datetime
    ) -> Optional[datetime]:
        """Earliest start in the window where a task of this length overlaps no
        incomplete task (any pet), or None."""
        raise NotImplementedError

    def sort_by_time(self, tasks: Optional[list[Task]] = None) -> list[Task]:
        """Chronological order. Ties break by higher priority, then pet name,
        then description, so the result is fully deterministic."""
        raise NotImplementedError

    def filter_tasks(
        self,
        pet_name: Optional[str] = None,
        completed: Optional[bool] = None,
        on_date: Optional[date] = None,
    ) -> list[Task]:
        """Tasks matching every filter that is not None, in chronological order."""
        raise NotImplementedError

    def detect_conflicts(self) -> list[Conflict]:
        """Overlapping incomplete tasks across ALL pets (one owner can't do two
        things at once). Back-to-back tasks do not conflict."""
        raise NotImplementedError
