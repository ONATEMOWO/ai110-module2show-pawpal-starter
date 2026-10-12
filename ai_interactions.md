# AI Interactions Log

> Only the stretch features that were attempted are documented here.

---

## Agent Workflow (SF7)

> Multi-step changes made autonomously by an AI agent (Claude Code, run in the project repository).

**What task did you give the agent?**

From the project prompt for the implementation phase: add a third distinctive scheduling capability beyond sort/filter/conflict/recurrence — a `find_next_available_slot` function that finds the earliest time a task of a given duration fits within a time window without overlapping incomplete tasks. Required handling: occupied intervals, adjacent tasks, no available slot, multi-pet conflicts, and positive-duration validation. It was one part of a larger request (backend, tests, CLI demo, Streamlit app, docs) with these constraints: standard library only, deterministic (no system clock), no commits pushed.

**What did the agent do?**

1. Read the Phase 1 skeleton (`pawpal_system.py`, `diagrams/uml_draft.mmd`) and kept `Task.end_time`/`overlaps` and the half-open `[start, end)` interval rule as the foundation.
2. Added `Scheduler.find_next_available_slot(duration_minutes, window_start, window_end)` in `pawpal_system.py`: it validates the duration (positive int) and window (naive datetimes, end not before start), collects incomplete tasks from **all pets** that intersect the window, sorts them by start, and sweeps a cursor forward — returning the cursor as soon as `cursor + duration <= next task start`, otherwise advancing the cursor to `max(cursor, task.end_time)`; after the last task it returns the cursor if it still fits before the window end, else `None`.
3. Wrote tests in `tests/test_pawpal.py`: `test_next_slot_skips_busy_blocks_across_pets`, `test_next_slot_adjacent_edges_and_exact_fit`, `test_next_slot_none_when_nothing_fits_and_completed_tasks_are_free`, `test_next_slot_validation`, plus the empty-owner case in `test_empty_owner_and_empty_schedule`.
4. Added a "Next available slot" section to `main.py` (30, 60 and 600 minute requests on the fixed demo day) and a "Find a slot" tab in `app.py`.
5. Ran `python3 main.py`, `python3 -m pytest`, `ruff` and `flake8` and read the results.

**Files modified:** `pawpal_system.py`, `tests/test_pawpal.py`, `main.py`, `app.py`, `diagrams/uml_final.mmd`, `README.md`.

**Observed results:** in the demo, a 30-minute slot is found at 07:00, a 60-minute slot at 10:00 (the gaps 07:00-07:30 and 08:15-09:00 are too short, and 09:00-10:00 is busy because Mochi's grooming and Whiskers' playtime overlap), and a 600-minute request returns no slot. The full suite passed (42 tests; see README for the output).

**What did you have to verify or fix manually?**

No bug was found in the slot logic itself; the single failing test in the first run (`test_full_containment_and_same_start_are_conflicts`) was an incorrect expected pair order in a conflict test, fixed in the test. Reading the demo output to confirm the 10:00 result against the task times was done from the printed schedule. The "Find a slot" tab was only exercised headlessly and was not checked by hand in a browser.

---

## Prompt Comparison (SF11)

> Compare two different prompts (or two different models) on the same task.

**Task:** Detect scheduling conflicts between pet-care tasks.

**Option A — my own independent explanation (written by the implementing agent, Claude, before seeing any other model's answer):**

`Scheduler.detect_conflicts` treats each incomplete task as the half-open interval `[start, start + duration)` and reports every pair of tasks whose intervals intersect, regardless of which pet they belong to, because the same owner has to perform all of them. It filters out completed tasks, sorts the rest by start time and, for each task, scans the following tasks until one starts at or after the current task's end (a sweep), so non-overlapping stretches are skipped quickly. Back-to-back tasks do not conflict because the end is exclusive; identical start times do conflict. Tradeoffs: it reports pairs rather than "groups" (three mutually overlapping tasks produce three conflicts), it is quadratic in the worst case when many tasks overlap, it warns instead of blocking (the user may deliberately double-book), it ignores travel time/buffers, and it relies on naive datetimes so daylight-saving changes are not handled. I chose a pairwise sweep over a naive all-pairs check or an interval tree because it is easy to test and explain for a small number of tasks.

**Option B — ChatGPT (GPT-6), independent answer to the identical question (verbatim):**

> I would represent each unfinished task by a half-open time interval [start, end), where end = start + duration. Two tasks conflict exactly when A.start < B.end and B.start < A.end. That condition catches partial overlap and full containment, and correctly treats a task ending at 08:00 followed by one starting at 08:00 as nonconflicting. The check must include tasks across different pets because one owner manages their schedules.
>
> For a small classroom application, I would first sort all unfinished tasks by start time, then scan later tasks for each task and stop scanning once their start time is at or beyond the current task's end. Report each overlapping pair with pet names, times, and overlap duration. Warn rather than reject because double-booking may sometimes be intentional.
>
> This approach is straightforward to verify, but worst-case work remains quadratic if many tasks overlap. An active-interval sweep could scale better for a large task collection. It also does not account for travel or preparation time, time zones, or daylight-saving changes. I would explicitly test equal starts, containment, partial overlap, adjacent intervals, completed tasks, and cross-pet conflicts before accepting it.

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | Claude (Claude Code, Sonnet 5.5) | ChatGPT (GPT-6) |
| **Prompt** | "Explain your conflict-detection approach and its tradeoffs." | Identical prompt |
| **Response summary** | Half-open intervals; filter out completed tasks; sort by start; scan until a later task starts at/after the current end; cross-pet pairs; warn, don't block | Same interval rule and sorted scan, stated as the formula `A.start < B.end and B.start < A.end`; reports pairs with pet names, times and overlap duration; warn, don't reject |
| **What was useful** | Describes the code as written (`Scheduler.detect_conflicts`): it names the pairwise-not-grouped reporting, the exclusive end, and the limits (no buffers or travel time, naive datetimes) | States the conflict condition as an explicit formula, offers an active-interval sweep as a scalability alternative, and lists the exact cases to test (equal starts, containment, partial overlap, adjacent, completed, cross-pet) |
| **Limitations / problems** | Written by the same assistant that wrote the implementation, so it mostly confirms the code rather than challenging it; it does not give a concrete list of test cases | Generic: it never refers to PawPal+'s classes, so it does not say that overlap minutes, pet names and warn-don't-block already exist in `Conflict` and `Scheduler.add_task`. Its "quadratic worst case" point is true, but an active-interval sweep would not remove it when every overlapping pair must be reported |
| **Decision** | Keep as implemented | Used as a checklist, not as a rewrite |

**Which approach did you use in your final implementation and why?**

I kept the existing implementation. The two answers agree on the core: half-open `[start, end)` intervals, only incomplete tasks, all pets together, a scan over tasks sorted by start time, and conflicts reported as warnings. That matches `Scheduler.detect_conflicts` in `pawpal_system.py`, which sorts the incomplete tasks with `sort_by_time`, then for each task walks the later ones and breaks as soon as `b.scheduled_at >= a.end_time`; each pair becomes a `Conflict` with both pet names and `overlap_minutes`, and `Scheduler.add_task` returns the new task's conflicts as a warning rather than rejecting it. Reading that loop, the work per task is one step plus the number of later tasks that actually overlap it, so the cost grows with the number of reported pairs and is only quadratic when nearly everything overlaps; an active-interval sweep would not reduce that because the output itself is quadratic in that case. For a household's daily task list, the simple scan is easier to explain and test, so I did not rewrite it just to be different from the Claude answer.

GPT-6's testing advice was the most useful addition, so I checked it against the existing tests rather than changing code: partial overlap and cross-pet (`test_conflict_across_pets_with_partial_overlap`), containment and equal starts (`test_full_containment_and_same_start_are_conflicts`), adjacent intervals (`test_adjacent_tasks_do_not_conflict`) and completed tasks (`test_completed_tasks_do_not_conflict`) are all already covered, so no new tests were needed. Both answers also list the same limits (no travel or preparation time, naive datetimes with no time-zone or daylight-saving handling), which are documented in the README's limitations. The scalability alternative is a possible future improvement if the app ever holds many more tasks than a household would.
