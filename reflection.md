# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- Briefly describe your initial UML design.
- What classes did you include, and what responsibilities did you assign to each?

My first design has the four required classes plus a few small helpers. The main user actions I designed around are: adding a pet-care task for one of my pets, seeing everything coming up across all my pets in time order, and marking a task done (which should create the next one if it repeats).

- **Owner** holds the owner's name and a list of pets, and can give back every task across all pets. It's the one entry point to the data.
- **Pet** holds its name, species and its own list of tasks. I made pets own their tasks instead of keeping one big task list, because a task really belongs to one pet.
- **Task** is a dataclass with a description, a start `datetime`, `duration_minutes`, a priority, a frequency, a completed flag and an id. It knows its own end time and whether it overlaps another task, and `mark_complete()` returns the next occurrence if it repeats.
- **Scheduler** doesn't store any tasks. It holds a reference to the Owner and does the "smart" work: sorting, filtering, completing recurring tasks and detecting conflicts. That way there's only one copy of the data and the Scheduler can't get out of sync with it.

I also added `Priority` and `Frequency` enums (so the UI's "low/medium/high" can't turn into typos) and a small `Conflict` dataclass so conflict detection returns something I can test and display rather than a printed string.

Some decisions I made on purpose:

- **Time:** one `scheduled_at` datetime plus `duration_minutes`; the end time is calculated. Datetimes are naive (no time zones) to keep it simple, and nothing in the logic calls `datetime.now()`, so tests can use fixed dates.
- **Task ids:** each task gets a uuid so I can find a task even if two have the same description. Recurring occurrences share a `series_id`.
- **Recurrence:** the next occurrence is only created when the current one is completed (not pre-generated for months). `Pet.add_task` rejects a task with the same `series_id` and start time, and completing an already-completed task does nothing, so double-clicking can't create duplicates.
- **Conflicts vs. duplicates:** a conflict is two unfinished tasks whose time ranges overlap, even across different pets, since there's only one owner. Back-to-back tasks are fine. A duplicate is the same task entered twice, which is different and gets rejected when adding. Conflicts are a warning, not an error.
- **Determinism:** sorting is by start time, then priority, then pet name, then description, so the same input always gives the same order.

One tradeoff I'm not sure about: `Task` stores `pet_name` so the Scheduler can say which pet a task is for. It's a bit of duplicated information, but the alternative was returning (pet, task) pairs everywhere.

**b. Design changes**

The design changed after I reviewed the Phase 1 draft, before and during implementation. The concrete changes and reasons:

- **The scheduler is more than a sorted calendar.** The starter README asks for a daily plan that respects available time, priority and owner preferences and explains itself, and my first draft only sorted and filtered. I added `Owner.daily_budget_minutes` and `preferred_categories`, a `Scheduler.build_daily_plan()` method and `DailyPlan`/`PlanEntry` result types so every selected or skipped task carries a reason.
- **Removed `Task.pet_name`.** In the draft it duplicated the pet's name and could drift out of sync with `Pet.name`. Now `Owner.find_task()` is the only place a task is mapped to its pet, and `Conflict`/`PlanEntry` record pet names as a snapshot in the result. The cost is a lookup instead of a field.
- **Recurrence:** the draft only said "create the next occurrence on completion". It now advances along the original cadence to the first occurrence strictly after an injectable completion time, so a late completion makes one new task, not a backlog. Completing twice returns nothing, and `Pet.add_task` refuses a second occurrence of the same `(series_id, scheduled_at)`.
- **Duplicates vs. conflicts:** I originally wanted to reject "the same task entered twice". That would also reject two different tasks at the same time, which is really a conflict the owner should hear about. Duplicates are now only repeated ids or repeated recurrence slots; everything else overlapping is a `Conflict`.
- **Validation and small renames:** `Frequency.ONCE` became `NONE`; tasks validate a positive integer duration and reject timezone-aware datetimes; `Conflict` gained both pet names; a `category` field supports the owner's tie-break preference.
- **New features not in the draft:** `find_next_available_slot`, JSON `to_dict`/`from_dict`/`save_owner`/`load_owner`, and `formatting.py` shared by the CLI and the app.

The final diagram is in `diagrams/uml_final.mmd` (also copied to `uml.mmd`); the draft is kept in `diagrams/uml_draft.mmd` as history.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

The planner considers, in this order: the day (only incomplete tasks starting that day), the owner's available minutes, fixed start times (no overlaps among chosen tasks), priority, then the owner's preferred categories, start time and description as tie-breakers. I put priority first because a high-priority task such as medication matters more than where it falls in the day, and the time budget second because it is the hard limit. Preferences only break ties, so they can never outrank an urgent task. Conflicts are checked across all pets because one person has to do the care.

**b. Tradeoffs**

The daily plan is greedy. It walks tasks from most to least important and keeps each one that still fits and doesn't overlap, which is easy to explain and fully deterministic, but it isn't optimal: a big high-priority task can use up budget that two medium tasks could have shared. I accepted that because an owner can read "why was this skipped" in one sentence, and an exact knapsack solver would be harder to explain and test for a project this size. A second tradeoff: tasks have fixed times, so the planner only chooses among them; it does not move tasks (the next-slot search is the separate tool for that). Naive datetimes (no time zones) are a third, deliberate simplification.

---

## 3. AI Collaboration

**a. How you used AI**

I used Claude Code in separate phases: first only architecture (class responsibilities, the UML draft, class skeletons and the design questions about ids, time representation, recurrence and conflicts), then a review where I decided what to change, then one implementation pass for the backend, tests, CLI, Streamlit app and docs. Prompts that stated constraints explicitly (for example "completing late must not create a backlog", "back-to-back tasks must not conflict") produced the most useful results, because they turned into tests directly.

**b. Judgment and verification**

- **Accepted:** my review said to either remove or consistently validate the duplicated `Task.pet_name`, and the AI chose to remove it and keep one owner-level lookup (`Owner.find_task`). I kept that choice because it removes a whole class of inconsistency instead of adding validation code. `test_owner_pets_unique_and_multi_pet_aggregation` checks the pet lookup.
- **Revised:** the Phase 1 draft I received treated duplicates and recurrence too loosely and had no budgeted plan; I did not accept that design as-is and sent it back with specific corrections (listed in 1b). Separately, the first version of the plan explanations included a running "N of B min used" figure; in the CLI output it was listed in priority order rather than time order and read as confusing, so it was changed to "fits the budget".
- **Verification:** the AI's first test run had one failing test, `test_full_containment_and_same_start_are_conflicts`. The cause was the expected pair order in the test (the sort puts the earlier-starting task first), not the conflict code; the test was corrected and the suite re-run. I have not hand-checked the algorithms beyond reading the CLI output and tests. Manual testing of the Streamlit app in a browser is pending.

---

## 4. Testing and Verification

**a. What you tested**

The 42 pytest tests (see README) cover task validation and completion, pet/owner management, sorting tie-breaks, filtering, conflicts (partial, containment, identical start, adjacent, completed, cross-pet), daily/weekly/late recurrence and idempotency, the daily plan (priority vs. time, budget changes, skip reasons, tie-breaks, no mutation), the next-slot search, JSON round-trip and invalid data, and empty inputs. They mattered because these rules are where scheduling bugs hide (off-by-one at interval edges, duplicate recurrences) and they all use fixed dates, so results are reproducible.

**b. Confidence**

All 42 tests passed on the last run and the CLI demo output matches the documented rules, so I'm fairly confident in the backend. I'm less sure about the Streamlit UI: it was only exercised with Streamlit's headless `AppTest` (create owner, add pet/task, conflict warning, complete, save/load) and a server start-up check, not by hand in a browser; visual layout and responsiveness are unverified (pending). Next I would test tasks that cross midnight, very many tasks (the conflict check is quadratic in the worst case), and a recurring task with an existing future occurrence.

---

## 5. Reflection

**a. What went well**

Separating design from implementation worked: reviewing the draft before any logic existed caught the missing daily plan, the duplicate-state problem and the loose recurrence rule while they were cheap to fix. Making the scheduler a pure function of the owner's data plus injected dates also made the tests easy to write.

**b. What you would improve**

I would add editing and deleting tasks and pets, let a recurring series end, and have the planner place unscheduled tasks into free slots rather than only choosing among fixed times.

**c. Key takeaway**

Being explicit about edge-case rules (half-open intervals, "strictly after", what counts as a duplicate) up front matters more than the code itself, and an AI assistant is most useful when those rules are given as constraints and then checked by tests rather than trusted. Its first design needed a human review before it was good.
