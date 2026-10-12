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

No bug was found in the slot logic itself; the single failing test in the first run (`test_full_containment_and_same_start_are_conflicts`) was an incorrect expected pair order in a conflict test, fixed in the test. Reading the demo output to confirm the 10:00 result against the task times was done from the printed schedule. Checking the feature by hand in the Streamlit UI is pending (the tab was only exercised headlessly).

---

## Prompt Comparison (SF11)

> Compare two different prompts (or two different models) on the same task.

**Task:** Detect scheduling conflicts between pet-care tasks.

**Option A — my own independent explanation (written by the implementing agent, Claude, before seeing any other model's answer):**

`Scheduler.detect_conflicts` treats each incomplete task as the half-open interval `[start, start + duration)` and reports every pair of tasks whose intervals intersect, regardless of which pet they belong to, because the same owner has to perform all of them. It filters out completed tasks, sorts the rest by start time and, for each task, scans the following tasks until one starts at or after the current task's end (a sweep), so non-overlapping stretches are skipped quickly. Back-to-back tasks do not conflict because the end is exclusive; identical start times do conflict. Tradeoffs: it reports pairs rather than "groups" (three mutually overlapping tasks produce three conflicts), it is quadratic in the worst case when many tasks overlap, it warns instead of blocking (the user may deliberately double-book), it ignores travel time/buffers, and it relies on naive datetimes so daylight-saving changes are not handled. I chose a pairwise sweep over a naive all-pairs check or an interval tree because it is easy to test and explain for a small number of tasks.

**Option B — comparison answer (to be added):**

> **PLACEHOLDER:** paste the separate ChatGPT/GPT answer to the same question here, then fill in the table below. Nothing has been compared yet.

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | Claude (Claude Code) | *pending* |
| **Prompt** | "Explain your conflict-detection approach and its tradeoffs." | *pending* |
| **Response summary** | Half-open intervals, sweep over sorted incomplete tasks, cross-pet pairs, warn-don't-block | *pending* |
| **What was useful** | *pending comparison* | *pending* |
| **Problems noticed** | *pending comparison* | *pending* |
| **Decision** | *pending* | *pending* |

**Which approach did you use in your final implementation and why?**

The implementation follows Option A. The final comparison conclusion is pending until Option B is provided.
