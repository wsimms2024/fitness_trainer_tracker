import sqlite3
from datetime import date

DB_PATH = "lifts.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lifts (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                date     TEXT    NOT NULL,
                exercise TEXT    NOT NULL,
                weight   REAL    NOT NULL,
                reps     INTEGER NOT NULL,
                sets     INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.commit()


def epley(weight, reps):
    return weight * (1 + reps / 30.0)


def add_lift(lift_date, exercise, weight, reps):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO lifts (date, exercise, weight, reps) VALUES (?, ?, ?, ?)",
            (str(lift_date), exercise, float(weight), int(reps)),
        )
        conn.commit()


def is_new_pr(exercise, e1rm):
    """True if e1rm beats all previous entries for this exercise (before inserting the new one)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT weight, reps FROM lifts WHERE exercise = ?", (exercise,)
        ).fetchall()
    if not rows:
        return False  # first entry — nothing to beat yet
    prev_best = max(epley(r["weight"], r["reps"]) for r in rows)
    return e1rm > prev_best


def get_current_prs():
    """Best e1RM ever per exercise, for exercises that have data."""
    with get_conn() as conn:
        rows = conn.execute("SELECT exercise, weight, reps FROM lifts").fetchall()
    bests = {}
    for r in rows:
        ex = r["exercise"]
        val = epley(r["weight"], r["reps"])
        if ex not in bests or val > bests[ex]:
            bests[ex] = val
    return bests


def get_all_lifts():
    """All rows, newest first, with computed e1RM."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM lifts ORDER BY date DESC, id DESC"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["e1rm"] = epley(d["weight"], d["reps"])
        result.append(d)
    return result


def get_lifts_for_exercise(exercise):
    """All rows for one exercise, oldest first, with computed e1RM."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM lifts WHERE exercise = ? ORDER BY date ASC, id ASC",
            (exercise,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["e1rm"] = epley(d["weight"], d["reps"])
        result.append(d)
    return result


def get_plateau_flags():
    """Returns the set of exercise names that have stalled over the last 3 sessions.

    A 'session' is a distinct date. We take the best e1RM per date and check
    whether the most recent session's best is no higher than the oldest of the
    last-3 sessions' best.
    """
    stalled = set()
    with get_conn() as conn:
        exercises = [r[0] for r in conn.execute(
            "SELECT DISTINCT exercise FROM lifts"
        ).fetchall()]
        for ex in exercises:
            rows = conn.execute(
                """SELECT date, MAX(weight * (1 + reps / 30.0)) AS best_e1rm
                   FROM lifts
                   WHERE exercise = ?
                   GROUP BY date
                   ORDER BY date ASC""",
                (ex,),
            ).fetchall()
            if len(rows) >= 3:
                last3 = rows[-3:]
                e1rms = [r["best_e1rm"] for r in last3]
                if e1rms[-1] <= e1rms[0]:
                    stalled.add(ex)
    return stalled
