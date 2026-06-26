import streamlit as st
import pandas as pd
from datetime import date

import db

db.init_db()

EXERCISES = ["Squat", "Bench", "SLDL"]

st.set_page_config(page_title="Lift Tracker", layout="wide")
st.title("Lift Tracker")

# ── Log Entry ────────────────────────────────────────────────────────────────
st.header("Log a Lift")

with st.form("log_form", clear_on_submit=True):
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    with c1:
        lift_date = st.date_input("Date", value=date.today())
    with c2:
        exercise = st.selectbox("Exercise", EXERCISES)
    with c3:
        weight = st.number_input("Weight (lbs)", min_value=0.0, step=2.5, value=135.0)
    with c4:
        reps = st.number_input("Reps", min_value=1, step=1, value=5)
    submitted = st.form_submit_button("Log Lift", use_container_width=True)

if submitted:
    if weight > 0 and reps >= 1:
        e1rm = db.epley(weight, reps)
        new_pr = db.is_new_pr(exercise, e1rm)
        db.add_lift(lift_date, exercise, weight, reps)
        if new_pr:
            st.success(f"New {exercise} PR: {e1rm:.1f} lb e1RM!", icon="🏆")
        else:
            st.success(
                f"Logged {exercise}: {weight} lbs × {reps} reps  |  e1RM: {e1rm:.1f} lbs"
            )
    else:
        st.error("Weight must be > 0 and reps must be ≥ 1.")

st.divider()

# ── PRs + Plateau Flags ───────────────────────────────────────────────────────
pr_col, plateau_col = st.columns(2)

with pr_col:
    st.subheader("Current PRs")
    prs = db.get_current_prs()
    if prs:
        metric_cols = st.columns(len(prs))
        for col, (ex, val) in zip(metric_cols, prs.items()):
            col.metric(ex, f"{val:.1f} lbs")
    else:
        st.info("No lifts logged yet.")

with plateau_col:
    st.subheader("Plateau Flags")
    flags = db.get_plateau_flags()
    if flags:
        for ex in EXERCISES:
            if ex in flags:
                st.warning(f"{ex} has stalled for 3 sessions.")
    else:
        all_lifts = db.get_all_lifts()
        if all_lifts:
            st.success("No plateau detected — keep lifting.")
        else:
            st.info("Log at least 3 sessions per lift to see plateau flags.")

st.divider()

# ── Progress Charts ───────────────────────────────────────────────────────────
st.header("Progress Charts")

chart_cols = st.columns(3)
for col, ex in zip(chart_cols, EXERCISES):
    with col:
        st.subheader(ex)
        lifts = db.get_lifts_for_exercise(ex)
        if lifts:
            df = pd.DataFrame(lifts, columns=["id", "date", "exercise", "weight", "reps", "sets", "e1rm"])
            df["date"] = pd.to_datetime(df["date"])
            chart_df = df[["date", "e1rm"]].rename(columns={"e1rm": "e1RM (lbs)"})
            chart_df = chart_df.set_index("date")
            st.line_chart(chart_df)
        else:
            st.info("No data yet.")

st.divider()

# ── Log Table ─────────────────────────────────────────────────────────────────
st.header("All Lifts")

filter_ex = st.selectbox("Filter by exercise", ["All"] + EXERCISES, key="filter_ex")

all_lifts = db.get_all_lifts()
if all_lifts:
    df = pd.DataFrame(all_lifts)
    df["e1RM (lbs)"] = df["e1rm"].round(1)
    display_df = df[["date", "exercise", "weight", "reps", "e1RM (lbs)"]].rename(
        columns={
            "date": "Date",
            "exercise": "Exercise",
            "weight": "Weight (lbs)",
            "reps": "Reps",
        }
    )
    if filter_ex != "All":
        display_df = display_df[display_df["Exercise"] == filter_ex]
    st.dataframe(display_df, use_container_width=True, hide_index=True)
else:
    st.info("No lifts logged yet. Use the form above to log your first lift.")
