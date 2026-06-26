import io
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

# ── Bulk Upload ───────────────────────────────────────────────────────────────
def parse_upload(uploaded_file):
    """Parse a CSV or TXT file into valid lift dicts and error strings.

    Returns (valid_rows, row_errors, fatal_error).
    fatal_error is a string if the file can't be parsed at all, else None.
    """
    content = uploaded_file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    first_line = text.split("\n")[0]
    if "\t" in first_line:
        sep = "\t"
    elif ";" in first_line:
        sep = ";"
    else:
        sep = ","

    try:
        df = pd.read_csv(io.StringIO(text), sep=sep)
    except Exception as e:
        return [], [], f"Could not read file: {e}"

    # Map common column name variants to canonical names
    aliases = {
        "date":     ["date", "day", "workout_date", "session_date", "training_date"],
        "exercise": ["exercise", "lift", "movement", "exercise_name", "name"],
        "weight":   ["weight", "weight_lbs", "lbs", "load", "weight (lbs)", "weight(lbs)"],
        "reps":     ["reps", "rep", "repetitions", "reps_completed", "rep_count"],
    }
    lowered = {c.strip().lower(): c for c in df.columns}
    rename = {}
    for canonical, options in aliases.items():
        for opt in options:
            if opt in lowered:
                rename[lowered[opt]] = canonical
                break
    df = df.rename(columns=rename)

    missing = {"date", "exercise", "weight", "reps"} - set(df.columns)
    if missing:
        found = ", ".join(df.columns.tolist())
        return [], [], (
            f"Missing required columns: {', '.join(sorted(missing))}. "
            f"Columns found in file: {found}. "
            f"Rename your headers to: date, exercise, weight, reps."
        )

    valid, errors = [], []
    for i, row in df.iterrows():
        try:
            lift_date = pd.to_datetime(row["date"]).date()
            exercise  = str(row["exercise"]).strip()
            weight    = float(row["weight"])
            reps      = int(float(row["reps"]))
            if not exercise or exercise.lower() == "nan":
                raise ValueError("exercise is empty")
            if weight <= 0:
                raise ValueError(f"weight must be > 0, got {weight}")
            if reps < 1:
                raise ValueError(f"reps must be ≥ 1, got {reps}")
            valid.append({"date": lift_date, "exercise": exercise, "weight": weight, "reps": reps})
        except Exception as e:
            errors.append(f"Row {i + 2}: {e}")

    return valid, errors, None


with st.expander("Upload historical data (CSV / TXT)"):
    st.markdown(
        "File must have columns: **date, exercise, weight, reps** "
        "(header names are flexible — see examples below).\n\n"
        "**Example CSV:**\n"
        "```\ndate,exercise,weight,reps\n"
        "2024-01-01,Squat,315,3\n"
        "2024-01-01,Bench,225,5\n"
        "2024-01-08,SLDL,275,4\n```"
    )

    uploaded = st.file_uploader("Choose file", type=["csv", "txt"])

    if uploaded:
        valid_rows, row_errors, fatal = parse_upload(uploaded)

        if fatal:
            st.error(fatal)
        else:
            if row_errors:
                with st.expander(f"{len(row_errors)} row(s) could not be parsed — click to view"):
                    for err in row_errors:
                        st.text(err)

            if valid_rows:
                preview = pd.DataFrame(valid_rows)
                preview["e1RM (lbs)"] = preview.apply(
                    lambda r: round(db.epley(r["weight"], r["reps"]), 1), axis=1
                )
                st.dataframe(preview, use_container_width=True, hide_index=True)

                if st.button(f"Import {len(valid_rows)} lift(s)", type="primary"):
                    inserted, skipped = db.bulk_insert_lifts(valid_rows)
                    st.success(f"Done — {inserted} imported, {skipped} duplicate(s) skipped.")
                    st.rerun()
            else:
                st.warning("No valid rows found in the file.")

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
