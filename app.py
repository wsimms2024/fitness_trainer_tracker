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

# Maps Liftoff exercise names (lowercase) to the canonical names used in this app.
# Add entries here when you add new exercises to EXERCISES.
EXERCISE_MAP = {
    "bench press":            "Bench",
    "romanian deadlift":      "SLDL",
    "stiff leg deadlift":     "SLDL",
    "smith romanian deadlift":"SLDL",
}


def _map_exercise(name):
    return EXERCISE_MAP.get(name.strip().lower(), name.strip())


def _parse_liftoff(df):
    """Handle Liftoff exports where every set is its own row.

    Groups by (date, exercise) and keeps the top set by e1RM.
    Zero-weight rows (bodyweight moves) are silently dropped.
    """
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    df["date_only"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date_only"])
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce").fillna(0)
    df["reps"]   = pd.to_numeric(df["reps"],   errors="coerce").fillna(0)

    # Drop bodyweight / zero-weight rows — e1RM is meaningless for them
    df = df[df["weight"] > 0]

    df["e1rm"] = df["weight"] * (1 + df["reps"] / 30.0)

    # One top set per exercise per day
    idx      = df.groupby(["date_only", "exercise"])["e1rm"].idxmax()
    top_sets = df.loc[idx]

    valid, errors = [], []
    for _, row in top_sets.iterrows():
        try:
            exercise = _map_exercise(str(row["exercise"]))
            weight   = float(row["weight"])
            reps     = int(float(row["reps"]))
            if reps < 1:
                raise ValueError(f"reps must be ≥ 1")
            valid.append({"date": row["date_only"], "exercise": exercise,
                          "weight": weight, "reps": reps})
        except Exception as e:
            errors.append(f"{row.get('date_only', '?')} — {row.get('exercise', '?')}: {e}")

    return valid, errors, None


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
    sep = "\t" if "\t" in first_line else ";" if ";" in first_line else ","

    try:
        df = pd.read_csv(io.StringIO(text), sep=sep)
    except Exception as e:
        return [], [], f"Could not read file: {e}"

    # Liftoff exports always have a "Set Order" column
    if "Set Order" in df.columns or "set order" in [c.lower() for c in df.columns]:
        return _parse_liftoff(df)

    # ── Generic CSV path ──────────────────────────────────────────────────────
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
            exercise  = _map_exercise(str(row["exercise"]))
            weight    = float(row["weight"])
            reps      = int(float(row["reps"]))
            if not exercise or exercise.lower() == "nan":
                raise ValueError("exercise is empty")
            if weight <= 0:
                raise ValueError(f"weight must be > 0")
            if reps < 1:
                raise ValueError(f"reps must be ≥ 1")
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
