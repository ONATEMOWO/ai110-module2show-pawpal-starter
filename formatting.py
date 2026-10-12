"""Plain-text and display helpers shared by the CLI demo (main.py) and the
Streamlit app. Pure functions: they format data and never change it."""

from __future__ import annotations

from typing import Iterable, Optional

from pawpal_system import Conflict, DailyPlan, Frequency, Priority, Scheduler, Task

PRIORITY_ICONS = {Priority.HIGH: "🔴", Priority.MEDIUM: "🟡", Priority.LOW: "🟢"}


def priority_label(priority: Priority, icons: bool = False) -> str:
    """'HIGH' or, with icons=True, '🔴 High' for UI display."""
    if icons:
        return f"{PRIORITY_ICONS[priority]} {priority.name.capitalize()}"
    return priority.name


def status_label(task: Task, icons: bool = False) -> str:
    """'done' / 'todo' (or '✅ Done' / '⏳ To do')."""
    if icons:
        return "✅ Done" if task.completed else "⏳ To do"
    return "done" if task.completed else "todo"


def repeat_label(task: Task) -> str:
    """'-' for one-off tasks, otherwise 'daily' / 'weekly'."""
    return "-" if task.frequency is Frequency.NONE else task.frequency.value


def time_range(task: Task, with_date: bool = False) -> str:
    """'07:30-08:00', optionally prefixed with the date."""
    span = f"{task.scheduled_at:%H:%M}-{task.end_time:%H:%M}"
    return f"{task.scheduled_at:%a %d %b} {span}" if with_date else span


def section(title: str) -> str:
    """A banner line for CLI sections."""
    return f"\n{'=' * 68}\n {title}\n{'=' * 68}"


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Left-aligned text table with a header rule; '(none)' when empty."""
    if not rows:
        return "  (none)"
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

    def line(cells: list[str]) -> str:
        return "  " + "  ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()

    rule = "  " + "  ".join("-" * w for w in widths)
    return "\n".join([line(headers), rule, *(line(r) for r in rows)])


def format_task_table(scheduler: Scheduler, tasks: Iterable[Task]) -> str:
    """Schedule table: when, pet, task, minutes, priority, repeat, status."""
    rows = [
        [
            time_range(t, with_date=True),
            scheduler.pet_name_of(t.id),
            t.description,
            str(t.duration_minutes),
            priority_label(t.priority),
            repeat_label(t),
            status_label(t),
        ]
        for t in tasks
    ]
    return format_table(["When", "Pet", "Task", "Min", "Priority", "Repeat", "Status"], rows)


def describe_conflict(conflict: Conflict) -> str:
    """One sentence naming both tasks, their pets and the overlap."""
    a, b = conflict.first, conflict.second
    scope = "cross-pet" if conflict.cross_pet else "same pet"
    return (
        f"{conflict.first_pet}: {a.description} ({time_range(a)}) overlaps "
        f"{conflict.second_pet}: {b.description} ({time_range(b)}) "
        f"by {conflict.overlap_minutes} min [{scope}]"
    )


def format_conflicts(conflicts: list[Conflict]) -> str:
    """Bulleted conflict warnings, or a 'no conflicts' line."""
    if not conflicts:
        return "  No conflicts."
    return "\n".join(f"  ! {describe_conflict(c)}" for c in conflicts)


def format_plan(plan: DailyPlan, title: Optional[str] = None) -> str:
    """Selected and skipped tasks of a daily plan, each with its reason."""
    head = title or f"Plan for {plan.day:%a %d %b %Y}"
    lines = [
        f"  {head} - budget {plan.budget_minutes} min, "
        f"used {plan.minutes_used}, free {plan.minutes_free}",
        "  Selected:",
    ]
    lines += [
        f"    + {time_range(e.task)}  {e.pet_name}: {e.task.description} "
        f"({e.task.duration_minutes} min) - {e.reason}"
        for e in plan.selected
    ] or ["    (nothing selected)"]
    lines.append("  Skipped:")
    lines += [
        f"    - {time_range(e.task)}  {e.pet_name}: {e.task.description} "
        f"({e.task.duration_minutes} min, {e.task.priority.name}) - {e.reason}"
        for e in plan.skipped
    ] or ["    (nothing skipped)"]
    return "\n".join(lines)
