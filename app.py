"""PawPal+ Streamlit app. All logic lives in pawpal_system.py; this file only
collects input, calls the backend and displays results."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import streamlit as st

from formatting import describe_conflict, priority_label, repeat_label, status_label, time_range
from main import build_demo
from pawpal_system import (
    Frequency,
    Owner,
    PawPalError,
    Pet,
    PersistenceError,
    Priority,
    Scheduler,
    Task,
    load_owner,
    save_owner,
)

CATEGORIES = ["walk", "feeding", "meds", "grooming", "enrichment", "vet", "general"]
SPECIES = ["dog", "cat", "other"]
DEFAULT_SAVE_PATH = "data.json"

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="wide")


# ------------------------------------------------------------------ state helpers
def flash(kind: str, message: str) -> None:
    """Queue a message to show on the next render (callbacks run before reruns)."""
    st.session_state.flash.append((kind, message))


def get_owner() -> Owner | None:
    return st.session_state.get("owner")


def now_minute() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


st.session_state.setdefault("flash", [])
st.session_state.setdefault("owner", None)


# ---------------------------------------------------------------------- callbacks
def create_owner() -> None:
    try:
        st.session_state.owner = Owner(
            st.session_state.setup_name, st.session_state.setup_budget
        )
        flash("success", "Owner created. Add a pet to get started.")
    except ValueError as exc:
        flash("error", str(exc))


def use_sample_data() -> None:
    st.session_state.owner, _ = build_demo(date.today())
    flash("success", "Loaded sample owner, pets and tasks scheduled for today.")


def reset_all() -> None:
    st.session_state.owner = None
    flash("info", "Cleared. Create a new owner or load saved data.")


def save_settings() -> None:
    owner = get_owner()
    start, end = st.session_state.set_start, st.session_state.set_end
    if end <= start:
        flash("error", "Day end must be after day start.")
        return
    owner.name = st.session_state.set_name.strip() or owner.name
    owner.daily_budget_minutes = int(st.session_state.set_budget)
    owner.preferred_categories = list(st.session_state.set_prefs)
    owner.day_start, owner.day_end = start, end
    flash("success", "Settings updated.")


def save_data() -> None:
    try:
        save_owner(get_owner(), st.session_state.save_path)
        flash("success", f"Saved to {st.session_state.save_path}.")
    except OSError as exc:
        flash("error", f"Could not save: {exc}")


def load_data() -> None:
    try:
        st.session_state.owner = load_owner(st.session_state.save_path)
        flash("success", f"Loaded {st.session_state.save_path}.")
    except PersistenceError as exc:
        flash("error", f"Could not load: {exc}")


def add_pet() -> None:
    try:
        get_owner().add_pet(Pet(st.session_state.pet_name, st.session_state.pet_species))
        flash("success", f"Added {st.session_state.pet_name.strip()}.")
    except (ValueError, PawPalError) as exc:
        flash("error", str(exc))


def add_task() -> None:
    s = st.session_state
    try:
        task = Task(
            description=s.task_desc,
            scheduled_at=datetime.combine(s.task_date, s.task_time),
            duration_minutes=int(s.task_duration),
            priority=Priority.from_str(s.task_priority),
            frequency=Frequency(s.task_frequency),
            category=s.task_category,
        )
        conflicts = Scheduler(get_owner()).add_task(s.task_pet, task)
    except (ValueError, PawPalError) as exc:
        flash("error", f"Task not added: {exc}")
        return
    flash("success", f"Added '{task.description}' for {s.task_pet}.")
    for conflict in conflicts:
        flash("warning", "Conflict: " + describe_conflict(conflict))


def complete_task(task_id: str) -> None:
    try:
        following = Scheduler(get_owner()).complete_task(task_id, completed_at=now_minute())
    except PawPalError as exc:
        flash("error", str(exc))
        return
    flash("success", "Task completed.")
    if following is not None:
        flash("info", f"Next occurrence scheduled for {following.scheduled_at:%a %d %b %H:%M}.")


# ------------------------------------------------------------------------ layout
st.title("🐾 PawPal+")
st.caption("A pet-care planner: schedule tasks across your pets, catch conflicts, "
           "and plan a day that fits the time you have.")

for kind, message in st.session_state.flash:
    {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(
        message, icon={"success": "✅", "error": "🚫", "warning": "⚠️"}.get(kind, "ℹ️")
    )
st.session_state.flash = []

owner = get_owner()

if owner is None:
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.subheader("Set up your profile")
        with st.form("setup_form"):
            st.text_input("Your name", value="Jordan", key="setup_name")
            st.number_input("Daily care budget (minutes)", 1, 1440, 120, key="setup_budget")
            st.form_submit_button("Create owner", on_click=create_owner, type="primary")
    with right, st.container(border=True):
        st.subheader("Or pick up where you left off")
        st.text_input("Data file", DEFAULT_SAVE_PATH, key="save_path")
        st.button("Load saved data", on_click=load_data)
        st.button("Try sample data", on_click=use_sample_data)
    st.stop()

sched = Scheduler(owner)

# ---- sidebar: owner settings and persistence
with st.sidebar:
    st.header(f"👤 {owner.name}")
    with st.form("settings_form"):
        st.text_input("Name", owner.name, key="set_name")
        st.number_input("Daily care budget (min)", 1, 1440, owner.daily_budget_minutes,
                        key="set_budget")
        st.multiselect(
            "Preferred categories", CATEGORIES,
            default=[c for c in owner.preferred_categories if c in CATEGORIES],
            key="set_prefs", help="Earlier choices win ties between equal-priority tasks.")
        st.time_input("Day starts", owner.day_start, key="set_start")
        st.time_input("Day ends", owner.day_end, key="set_end")
        st.form_submit_button("Save settings", on_click=save_settings)
    st.divider()
    st.text_input("Data file", DEFAULT_SAVE_PATH, key="save_path")
    c1, c2 = st.columns(2)
    c1.button("💾 Save", on_click=save_data)
    c2.button("📂 Load", on_click=load_data)
    st.button("Start over", on_click=reset_all)

# ---- summary cards
all_tasks = owner.all_tasks()
conflicts = sched.detect_conflicts()
cards = [
    ("Pets", len(owner.pets)),
    ("Open tasks", sum(not t.completed for t in all_tasks)),
    ("Completed", sum(t.completed for t in all_tasks)),
    ("Conflicts", len(conflicts)),
]
for col, (label, value) in zip(st.columns(4), cards):
    with col, st.container(border=True):
        st.metric(label, value)

if conflicts:
    with st.expander(f"⚠️ {len(conflicts)} scheduling conflict(s)", expanded=True):
        for conflict in conflicts:
            st.warning(describe_conflict(conflict))

tab_tasks, tab_pets, tab_plan, tab_slot = st.tabs(
    ["📋 Tasks", "🐶 Pets", "🗓️ Daily plan", "🔎 Find a slot"]
)

# ---- pets
with tab_pets:
    with st.container(border=True):
        st.subheader("Add a pet")
        with st.form("pet_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            c1.text_input("Pet name", key="pet_name")
            c2.selectbox("Species", SPECIES, key="pet_species")
            st.form_submit_button("Add pet", on_click=add_pet)
    if not owner.pets:
        st.info("No pets yet. Add your first pet above.")
    for pet in owner.pets:
        open_count = sum(not t.completed for t in pet.tasks)
        st.markdown(
            f"**{pet.name}** · {pet.species} · {open_count} open / {len(pet.tasks)} total tasks"
        )

# ---- tasks
with tab_tasks:
    if not owner.pets:
        st.info("Add a pet in the **Pets** tab before creating tasks.")
    else:
        with st.expander("➕ Add a task", expanded=not all_tasks):
            with st.form("task_form"):
                c1, c2, c3 = st.columns(3)
                c1.selectbox("Pet", [p.name for p in owner.pets], key="task_pet")
                c2.text_input("Description", key="task_desc", placeholder="Morning walk")
                c3.selectbox("Category", CATEGORIES, key="task_category")
                c4, c5, c6 = st.columns(3)
                c4.date_input("Date", date.today(), key="task_date")
                c5.time_input("Start time", time(8, 0), key="task_time")
                c6.number_input("Duration (min)", 1, 1440, 30, key="task_duration")
                c7, c8 = st.columns(2)
                c7.selectbox("Priority", ["low", "medium", "high"], index=1, key="task_priority")
                c8.selectbox("Repeats", [f.value for f in Frequency], key="task_frequency")
                st.form_submit_button("Add task", on_click=add_task, type="primary")

        f1, f2, f3 = st.columns(3)
        pet_filter = f1.selectbox("Pet", ["All"] + [p.name for p in owner.pets], key="f_pet")
        use_date = f2.checkbox("Filter by date", key="f_use_date")
        date_filter = f2.date_input("Date", date.today(), key="f_date", disabled=not use_date,
                                    label_visibility="collapsed")
        status = f3.radio("Status", ["All", "To do", "Done"], horizontal=True, key="f_status")

        shown = sched.filter_tasks(
            pet_name=None if pet_filter == "All" else pet_filter,
            completed={"All": None, "To do": False, "Done": True}[status],
            on_date=date_filter if use_date else None,
        )
        if not shown:
            st.info("No tasks match. Add a task or relax the filters.")
        else:
            header = st.columns([2.4, 1.3, 3, 1, 1.4, 1.1, 1.3])
            for col, label in zip(header, ["When", "Pet", "Task", "Min", "Priority", "Repeat", ""]):
                col.caption(label)
            for task in shown:
                row = st.columns([2.4, 1.3, 3, 1, 1.4, 1.1, 1.3])
                row[0].write(time_range(task, with_date=True))
                row[1].write(sched.pet_name_of(task.id))
                row[2].write(f"~~{task.description}~~" if task.completed else task.description)
                row[3].write(str(task.duration_minutes))
                row[4].write(priority_label(task.priority, icons=True))
                row[5].write(repeat_label(task))
                if task.completed:
                    row[6].write(status_label(task, icons=True))
                else:
                    row[6].button("Complete", key=f"done_{task.id}", on_click=complete_task,
                                  args=(task.id,))

# ---- daily plan
with tab_plan:
    st.write("Pick a day and a time budget. Higher-priority tasks are chosen first; "
             "a task is skipped if it overlaps a chosen one or no longer fits the budget.")
    c1, c2 = st.columns(2)
    plan_day = c1.date_input("Day", date.today(), key="plan_day")
    budget = c2.number_input("Available minutes", 0, 1440, owner.daily_budget_minutes,
                             key="plan_budget")
    plan = sched.build_daily_plan(plan_day, int(budget))
    m1, m2, m3 = st.columns(3)
    for col, (label, value) in zip((m1, m2, m3), [("Budget", f"{plan.budget_minutes} min"),
                                                  ("Planned", f"{plan.minutes_used} min"),
                                                  ("Free", f"{plan.minutes_free} min")]):
        with col, st.container(border=True):
            st.metric(label, value)
    if not plan.selected and not plan.skipped:
        st.info("No open tasks on this day.")
    st.subheader("✅ Planned")
    if plan.selected:
        st.dataframe(
            [{"Time": time_range(e.task), "Pet": e.pet_name, "Task": e.task.description,
              "Min": e.task.duration_minutes, "Priority": priority_label(e.task.priority, True),
              "Why": e.reason} for e in plan.selected],
            hide_index=True)
    else:
        st.caption("Nothing planned.")
    st.subheader("⏭️ Skipped")
    if plan.skipped:
        st.dataframe(
            [{"Time": time_range(e.task), "Pet": e.pet_name, "Task": e.task.description,
              "Min": e.task.duration_minutes, "Priority": priority_label(e.task.priority, True),
              "Why skipped": e.reason} for e in plan.skipped],
            hide_index=True)
    else:
        st.caption("Nothing skipped.")

# ---- next available slot
with tab_slot:
    st.write("Find the earliest gap that fits a new task without overlapping any pet's open tasks.")
    c1, c2, c3 = st.columns(3)
    slot_day = c1.date_input("Day", date.today(), key="slot_day")
    slot_minutes = c2.number_input("Duration (min)", 1, 1440, 30, key="slot_minutes")
    c4, c5 = st.columns(2)
    slot_from = c4.time_input("Search from", owner.day_start, key="slot_from")
    slot_to = c5.time_input("Search until", owner.day_end, key="slot_to")
    if slot_to <= slot_from:
        st.warning("The search window must end after it starts.")
    else:
        found = sched.find_next_available_slot(
            int(slot_minutes), datetime.combine(slot_day, slot_from),
            datetime.combine(slot_day, slot_to))
        if found is None:
            st.error("No gap that long in this window.")
        else:
            end = found + timedelta(minutes=int(slot_minutes))
            st.success(f"Earliest slot: {found:%H:%M} - {end:%H:%M}")
