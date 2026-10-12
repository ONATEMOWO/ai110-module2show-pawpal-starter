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

- Did your design change during implementation?
- If yes, describe at least one change and why you made it.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
