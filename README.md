# 🐾 PawPal+

PawPal+ is a pet-care planner for a busy owner with more than one pet. You record care tasks (walks, feeding, meds, grooming, ...) with a date, time, duration and priority; PawPal+ keeps them in time order, warns you when two tasks overlap, rolls recurring tasks forward when you finish them, and builds a **daily plan** that fits the time you actually have, explaining every task it chose or skipped.

It is a CodePath AI110 (Module 2) project. The design was done first (UML), then the backend, tests, CLI and Streamlit UI were built on top of it.

## Features

- One owner, many pets; tasks belong to a pet (`Owner` → `Pet` → `Task`).
- Tasks with description, category, start date/time, positive duration, priority (low/medium/high), completion status and optional daily/weekly repeat.
- Chronological sorting and filtering by pet, status and date.
- Conflict detection across **all** pets (one owner can't do two things at once).
- Recurring tasks that never create duplicates or a backlog of missed days.
- A budgeted, priority-aware daily plan with a reason for every decision.
- Next-available-slot search, JSON save/load, a CLI demo and a Streamlit app.

## Setup

Requires Python 3.10+ (developed on 3.12). Everything except the UI uses only the standard library.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # streamlit + pytest
```

## Run it

```bash
python3 main.py                 # deterministic CLI demo (fixed date, sample data)
python3 -m pytest               # run the test suite
streamlit run app.py            # the interactive app
```

## Class responsibilities

All domain code is in [pawpal_system.py](pawpal_system.py).

| Class | Responsibility |
|-------|----------------|
| `Owner` | The one user: name, daily time budget (`daily_budget_minutes`), `preferred_categories` (tie-breaks), waking hours, and their pets. Aggregates tasks across pets (`all_tasks`) and is the only place that maps a task to its pet (`find_task`). Pet names are unique (case-insensitive). |
| `Pet` | Name, species and its own tasks. `add_task` / `remove_task` / `get_task` / `list_tasks`; rejects duplicate ids and duplicate recurrence occurrences. |
| `Task` | One activity. Validates its input (non-empty description, positive integer duration, naive datetime). Knows its `end_time`, whether it `overlaps` another, its `next_occurrence`, and `mark_complete`. |
| `Scheduler` | Holds **no tasks** of its own; reads them through the `Owner`. Sorting, filtering, conflicts, completion with recurrence, daily planning and slot search. |
| `Priority`, `Frequency` | Enums (`LOW/MEDIUM/HIGH` as ints; `NONE/DAILY/WEEKLY`). |
| `Conflict`, `DailyPlan`, `PlanEntry` | Frozen result objects, so the logic returns data instead of printing. |

Errors: `ValueError` for invalid input, plus `DuplicateError`, `NotFoundError` and `PersistenceError` (all `PawPalError`).

## Scheduling algorithms

| Feature | Method(s) | Behaviour |
|---------|-----------|-----------|
| Sorting | `Scheduler.sort_by_time` | By start time; ties by higher priority, pet name, description, then insertion order, so output is fully deterministic. |
| Filtering | `Scheduler.filter_tasks(pet_name, completed, on_date)` | Any combination; results are chronological. A task belongs to the date it starts on. |
| Conflicts | `Scheduler.detect_conflicts`, `conflicts_for`, `Task.overlaps` | Sweep over incomplete tasks sorted by start; reports every overlapping pair, across pets. |
| Recurrence | `Task.next_occurrence`, `Task.mark_complete`, `Scheduler.complete_task` | Daily/weekly. See below. |
| Daily plan | `Scheduler.build_daily_plan(day, budget_minutes)` | Greedy, budgeted, explained. See below. |
| Next free slot | `Scheduler.find_next_available_slot` | Earliest gap in a window that fits a duration. |
| Persistence | `save_owner`, `load_owner`, `to_dict`/`from_dict` | JSON round-trip. |

### Conflict semantics
A task occupies the half-open interval `[start, end)`. Two incomplete tasks conflict if the intervals intersect (partial overlap, containment or identical times), whether they are for the same pet or different pets. **Back-to-back tasks (one ends exactly when the next starts) do not conflict**, and completed tasks never block anything. Two tasks at the same time are *not* treated as duplicates: they are reported as a conflict. `Scheduler.add_task` returns the conflicts a new task creates as a warning; it does not reject the task.

### Recurrence semantics
Completing a `DAILY`/`WEEKLY` task creates the next occurrence with a new id but the same `series_id`. The next occurrence is the first point on the **original cadence** (`start + k × interval`) that is **strictly after** the completion time, so finishing a daily task three days late creates one task for the next relevant day, not a backlog. The completion time is a parameter (`completed_at`, default = the task's own start) so tests never read the clock. Completing the same task twice returns `None` the second time, and `Pet.add_task` refuses a second occurrence with the same `(series_id, scheduled_at)`, so duplicates cannot be created.

### Daily planning and tie-breaking
`build_daily_plan(day, budget_minutes)` considers incomplete tasks starting on `day` (their times are fixed). It ranks them by:

1. higher **priority**,
2. the owner's `preferred_categories` order (earlier = preferred),
3. earlier start time,
4. description (case-insensitive),
5. insertion order.

Walking that ranking, a task is **selected** unless it overlaps an already selected task or its duration is more than the minutes left; otherwise it is **skipped** with a reason (`Overlaps 'X' (hh:mm-hh:mm), which ranked higher` or `Needs N min but only M min left in the B-min budget`). A skipped task does not stop smaller later tasks from fitting. Selected and skipped tasks are both returned in chronological order, and generating a plan never modifies any task. This is a greedy heuristic, not an optimal knapsack: a high-priority task can use budget that two smaller medium tasks could have shared.

### Next available slot
`find_next_available_slot(duration_minutes, window_start, window_end)` walks the incomplete tasks (all pets) sorted by start, moving a cursor past each busy block, and returns the first cursor position where the duration fits before the next block or the window end. Adjacent tasks leave no gap but also don't block; it returns `None` if nothing fits and raises `ValueError` for a non-positive duration or a reversed window.

### JSON persistence
`save_owner(owner, path)` writes the owner, pets and tasks (ISO datetimes, enum names, ids, completion and recurrence info) using only the standard library; `load_owner(path)` rebuilds real `Owner`/`Pet`/`Task` objects. Missing files, bad JSON, wrong types, unknown enum values, a non-positive duration, duplicate ids and unsupported schema versions raise `PersistenceError`. The Streamlit sidebar saves to `data.json` by default; that file is git-ignored runtime data. Limitations: one owner per file, no migration between schema versions, and no locking.

## Sample CLI output

Copied from `python3 main.py` (the demo uses a fixed date, so it is reproducible):

```
PawPal+ demo for Jordan - pets: Mochi (dog), Whiskers (cat)

====================================================================
 1. Everything, sorted chronologically (added out of order)
====================================================================
  When                    Pet       Task             Min  Priority  Repeat  Status
  ----------------------  --------  ---------------  ---  --------  ------  ------
  Mon 02 Mar 07:30-08:00  Mochi     Morning walk     30   HIGH      daily   todo
  Mon 02 Mar 08:00-08:15  Whiskers  Breakfast        15   HIGH      daily   todo
  Mon 02 Mar 09:00-09:45  Mochi     Grooming         45   MEDIUM    -       todo
  Mon 02 Mar 09:30-10:00  Whiskers  Playtime         30   LOW       -       todo
  Mon 02 Mar 12:00-12:30  Mochi     Training         30   MEDIUM    -       todo
  Mon 02 Mar 17:30-18:10  Mochi     Evening walk     40   MEDIUM    -       todo
  Mon 02 Mar 18:00-18:05  Whiskers  Flea medication  5    HIGH      weekly  todo

====================================================================
 2. Filtering
====================================================================
  Mochi only:
  When                    Pet    Task          Min  Priority  Repeat  Status
  ----------------------  -----  ------------  ---  --------  ------  ------
  Mon 02 Mar 07:30-08:00  Mochi  Morning walk  30   HIGH      daily   todo
  Mon 02 Mar 09:00-09:45  Mochi  Grooming      45   MEDIUM    -       todo
  Mon 02 Mar 12:00-12:30  Mochi  Training      30   MEDIUM    -       todo
  Mon 02 Mar 17:30-18:10  Mochi  Evening walk  40   MEDIUM    -       todo

  Whiskers, Monday 2 Mar, not completed:
  When                    Pet       Task             Min  Priority  Repeat  Status
  ----------------------  --------  ---------------  ---  --------  ------  ------
  Mon 02 Mar 08:00-08:15  Whiskers  Breakfast        15   HIGH      daily   todo
  Mon 02 Mar 09:30-10:00  Whiskers  Playtime         30   LOW       -       todo
  Mon 02 Mar 18:00-18:05  Whiskers  Flea medication  5    HIGH      weekly  todo

====================================================================
 3. Conflict detection (across pets; back-to-back is fine)
====================================================================
  ! Mochi: Grooming (09:00-09:45) overlaps Whiskers: Playtime (09:30-10:00) by 15 min [cross-pet]
  ! Mochi: Evening walk (17:30-18:10) overlaps Whiskers: Flea medication (18:00-18:05) by 5 min [cross-pet]
  Note: Morning walk 07:30-08:00 and Breakfast 08:00-08:15 touch but do not conflict.

====================================================================
 4. Daily plan, 120-minute budget
====================================================================
  Plan for Mon 02 Mar 2026 - budget 120 min, used 95, free 25
  Selected:
    + 07:30-08:00  Mochi: Morning walk (30 min) - High priority; fits the budget
    + 08:00-08:15  Whiskers: Breakfast (15 min) - High priority; fits the budget
    + 09:00-09:45  Mochi: Grooming (45 min) - Medium priority; fits the budget
    + 18:00-18:05  Whiskers: Flea medication (5 min) - High priority; fits the budget
  Skipped:
    - 09:30-10:00  Whiskers: Playtime (30 min, LOW) - Overlaps 'Grooming' (09:00-09:45), which ranked higher
    - 12:00-12:30  Mochi: Training (30 min, MEDIUM) - Needs 30 min but only 25 min left in the 120-min budget
    - 17:30-18:10  Mochi: Evening walk (40 min, MEDIUM) - Overlaps 'Flea medication' (18:00-18:05), which ranked higher

====================================================================
 5. Same day, smaller budget (60 min): fewer tasks selected
====================================================================
  Plan for Mon 02 Mar 2026 - budget 60 min, used 50, free 10
  Selected:
    + 07:30-08:00  Mochi: Morning walk (30 min) - High priority; fits the budget
    + 08:00-08:15  Whiskers: Breakfast (15 min) - High priority; fits the budget
    + 18:00-18:05  Whiskers: Flea medication (5 min) - High priority; fits the budget
  Skipped:
    - 09:00-09:45  Mochi: Grooming (45 min, MEDIUM) - Needs 45 min but only 10 min left in the 60-min budget
    - 09:30-10:00  Whiskers: Playtime (30 min, LOW) - Needs 30 min but only 10 min left in the 60-min budget
    - 12:00-12:30  Mochi: Training (30 min, MEDIUM) - Needs 30 min but only 10 min left in the 60-min budget
    - 17:30-18:10  Mochi: Evening walk (40 min, MEDIUM) - Overlaps 'Flea medication' (18:00-18:05), which ranked higher

====================================================================
 6. Priority changes the outcome: Playtime LOW -> HIGH (120 min)
====================================================================
  Plan for Mon 02 Mar 2026 - budget 120 min, used 110, free 10
  Selected:
    + 07:30-08:00  Mochi: Morning walk (30 min) - High priority; fits the budget
    + 08:00-08:15  Whiskers: Breakfast (15 min) - High priority; fits the budget
    + 09:30-10:00  Whiskers: Playtime (30 min) - High priority; fits the budget
    + 12:00-12:30  Mochi: Training (30 min) - Medium priority; fits the budget
    + 18:00-18:05  Whiskers: Flea medication (5 min) - High priority; fits the budget
  Skipped:
    - 09:00-09:45  Mochi: Grooming (45 min, MEDIUM) - Overlaps 'Playtime' (09:30-10:00), which ranked higher
    - 17:30-18:10  Mochi: Evening walk (40 min, MEDIUM) - Overlaps 'Flea medication' (18:00-18:05), which ranked higher

====================================================================
 7. Next available slot (window 07:00-21:00)
====================================================================
   30 min -> 07:00
   60 min -> 10:00
  600 min -> no slot

====================================================================
 8. Recurring tasks
====================================================================
  Completed 'Morning walk' (was Mon 02 Mar 07:30) late, at Tue 03 Mar 10:00.
  Next occurrence: Wed 04 Mar 07:30 (strictly after the completion time; no backlog)
  Completing it again creates another? False
  Weekly 'Flea medication' completed -> next Mon 09 Mar 18:00
  When                    Pet    Task          Min  Priority  Repeat  Status
  ----------------------  -----  ------------  ---  --------  ------  ------
  Mon 02 Mar 07:30-08:00  Mochi  Morning walk  30   HIGH      daily   done
  Mon 02 Mar 09:00-09:45  Mochi  Grooming      45   MEDIUM    -       todo
  Mon 02 Mar 12:00-12:30  Mochi  Training      30   MEDIUM    -       todo
  Mon 02 Mar 17:30-18:10  Mochi  Evening walk  40   MEDIUM    -       todo
  Wed 04 Mar 07:30-08:00  Mochi  Morning walk  30   HIGH      daily   todo

====================================================================
 9. JSON persistence (temporary file)
====================================================================
  Saved 9 tasks and reloaded 9 tasks for Jordan.
  Round-trip identical: True
  Completion preserved: True; recurrence preserved: daily
```

## Testing PawPal+

```bash
python3 -m pytest
```

Actual output from the last run:

```
============================= test session starts ==============================
platform darwin -- Python 3.12.0, pytest-9.0.0, pluggy-1.6.0
rootdir: /Users/temz/ai110-module2show-pawpal-starter
plugins: anyio-4.11.0
collected 42 items

tests/test_pawpal.py ..........................................          [100%]

============================== 42 passed in 0.15s ==============================
```

A harmless one-line `UserWarning` about `file_or_dir` from this machine's pytest/Python combination is printed before the header; it is unrelated to the project and omitted above.

`tests/test_pawpal.py` covers: task completion and validation (zero/negative/non-integer duration, empty description, timezone-aware datetimes); pet task add/remove/lookup and duplicate protection; multi-pet aggregation and unique ids; sorting with tie-breaks; filtering by pet/status/date; conflicts across pets, partial overlap, containment, identical start, adjacent (no conflict) and completed tasks; daily and weekly recurrence, late completion without backlog, strictly-after semantics, completing twice, duplicate occurrence protection, unknown ids; daily planning (priority beats earlier time, budget and priority changes alter the selection, overlap and budget skip reasons, category tie-break, ignores completed/other-day tasks, no mutation, determinism); next available slot (busy blocks across pets, adjacency, exact fit, no slot, completed tasks, validation); JSON round-trip, nine kinds of invalid data, corrupt and missing files; and an empty owner/schedule. All tests use fixed dates and temporary files; none reads the clock or network.

## Streamlit app

`streamlit run app.py` opens the planner. The `Owner` lives in `st.session_state`, all changes happen in button callbacks, and the page is rendered from the backend objects (there is no second data model).

- **Sidebar:** owner name, daily budget, preferred categories, waking hours, save/load file, start over.
- **Summary cards:** pets, open tasks, completed, conflicts; conflicts are shown as warnings, never crashes.
- **Tasks tab:** add a task (pet, description, category, date, time, duration, priority, repeat), filter by pet/date/status, mark complete (a recurring task shows its next occurrence).
- **Pets tab:** add and list pets.
- **Daily plan tab:** choose a day and the available minutes; see planned and skipped tasks with reasons.
- **Find a slot tab:** earliest gap for a new task.

Invalid input (empty description, duplicate pet, bad data file) produces an error message instead of a traceback. "Try sample data" on the start screen loads the demo pets with tasks dated today.

## Demo walkthrough

1. Start the app and create an owner profile (or click **Try sample data** / **Load saved data**).
2. In **Pets**, add one or more pets.
3. In **Tasks**, add tasks for a pet with a date, time, duration, priority and optional daily/weekly repeat; an overlapping task immediately produces a conflict warning, and the conflict panel at the top lists it.
4. Filter the task list by pet, date or status, then press **Complete** on a task; if it repeats, the next occurrence appears.
5. In **Daily plan**, pick a day and a time budget; lower the budget to watch lower-priority tasks move to the skipped list with their reasons.
6. In **Find a slot**, enter a duration to see the earliest free gap; use **Save** in the sidebar to persist everything to JSON.

**Screenshot or video** *(optional)*: not included.

## Stretch features

| Feature | Where |
|---------|-------|
| Next available slot (advanced algorithm) | `Scheduler.find_next_available_slot` in [pawpal_system.py](pawpal_system.py); tests `test_next_slot_*`; workflow in [ai_interactions.md](ai_interactions.md) |
| Priority-based, budgeted scheduling | `Scheduler.build_daily_plan`; tests `test_higher_priority_wins_budget_over_earlier_time`, `test_changing_budget_changes_selection`, `test_changing_priority_changes_selection`; CLI sections 4-6 |
| JSON persistence | `save_owner` / `load_owner` / `to_dict` / `from_dict`; tests `test_json_round_trip_*`, `test_invalid_saved_data_*`; CLI section 9; Streamlit sidebar |
| Formatting | [formatting.py](formatting.py): `format_task_table`, `format_plan`, `format_conflicts`, `describe_conflict`, `format_table`, `section` (CLI text tables), and `priority_label`/`status_label`/`repeat_label`/`time_range` (also used for the Streamlit icons and tables) |

## UML

- Initial design: [diagrams/uml_draft.mmd](diagrams/uml_draft.mmd) (design history, kept as written after the Phase 1 review).
- Final design: [diagrams/uml_final.mmd](diagrams/uml_final.mmd), identical to [diagrams/uml.mmd](diagrams/uml.mmd). Mermaid class diagrams; paste into any Mermaid viewer to render.

## Limitations and future work

- Naive datetimes only: no time zones or daylight-saving handling.
- The planner is greedy and works on tasks with **fixed** start times; it does not move tasks around or pick start times for them (use the slot finder for that).
- Duration is whole minutes; a task is assigned to the day it starts.
- Recurrence supports daily and weekly only; there is no "skip" or "end date" for a series.
- One owner per data file; no editing of an existing task or removing a pet in the UI yet.
- The Streamlit app was exercised headlessly (see below) but not yet checked by hand in a browser.
- Future: edit/delete tasks, auto-placing unscheduled tasks into free slots, monthly recurrence, reminders.

Headless checks of `app.py` (Streamlit's `AppTest`: create owner, add pet/tasks, conflict warning, invalid input, complete, save/load, sample data) were run during development with a throwaway script that is not part of the repository.
