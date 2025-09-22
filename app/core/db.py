import sqlite3
from pathlib import Path
from .config import DB_PATH, get_user_tasks, DEFAULT_USER
from datetime import date, datetime, timedelta
import pytz
from typing import Dict

# Pacific timezone with DST support
PACIFIC_TZ = pytz.timezone("America/Los_Angeles")


def get_pacific_date():
    """Get current date in Pacific Time"""
    return datetime.now(PACIFIC_TZ).date()


Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

DDL = """
CREATE TABLE IF NOT EXISTS checkin(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    d TEXT NOT NULL,
    task TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,
    user TEXT NOT NULL DEFAULT 'alice',
    note TEXT NOT NULL DEFAULT '',
    activity TEXT NOT NULL DEFAULT 'activity1',
    UNIQUE(d, task, user, activity)
);

CREATE TABLE IF NOT EXISTS todo_questions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    link TEXT NOT NULL,
    topics TEXT NOT NULL,
    day INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS todo_completed(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL,
    user TEXT NOT NULL DEFAULT 'alice',
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(question_id, user)
);
"""


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        # Create tables with individual statements
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkin(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                d TEXT NOT NULL,
                task TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 0,
                user TEXT NOT NULL DEFAULT 'alice',
                note TEXT NOT NULL DEFAULT '',
                activity TEXT NOT NULL DEFAULT 'activity1',
                UNIQUE(d, task, user, activity)
            )
        """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todo_questions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                link TEXT NOT NULL,
                topics TEXT NOT NULL,
                day INTEGER NOT NULL
            )
        """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todo_completed(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id TEXT NOT NULL,
                user TEXT NOT NULL DEFAULT 'alice',
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(question_id, user)
            )
        """
        )


def ensure_today_rows(user: str = DEFAULT_USER):
    """Ensure today's rows exist for all tasks and their first activities (for backward compatibility)"""
    today = get_pacific_date().isoformat()
    user_tasks = get_user_tasks(user)
    with get_conn() as conn:
        for task in user_tasks:
            # For backward compatibility, create row with first activity as default
            conn.execute(
                "INSERT OR IGNORE INTO checkin(d,task,level,user,note,activity) VALUES(?,?,0,?,?,?)",
                (today, task, user, "", "activity1"),
            )


def set_task_activity_level(task: str, activity: str, level: int, user: str = DEFAULT_USER):
    """Set task-activity completion level (0-3) for a specific user"""
    today = get_pacific_date().isoformat()
    level = max(0, min(3, level))  # Ensure level is between 0-3

    with get_conn() as conn:
        # First try to update existing row
        result = conn.execute(
            "UPDATE checkin SET level=? WHERE d=? AND task=? AND user=? AND activity=?",
            (level, today, task, user, activity),
        )

        # If no rows were updated, insert a new row
        if result.rowcount == 0:
            conn.execute(
                "INSERT INTO checkin(d,task,level,user,note,activity) VALUES(?,?,?,?,?,?)",
                (today, task, level, user, "", activity),
            )


def get_today_status_with_activities(user: str = DEFAULT_USER) -> Dict[str, Dict[str, dict]]:
    """Get today's status including activities"""
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        cur = conn.execute("SELECT task, activity, level, note FROM checkin WHERE d=? AND user=?", (today, user))
        result = {}
        for task, activity, level, note in cur.fetchall():
            if task not in result:
                result[task] = {}
            result[task][activity] = {"level": level, "note": note}
        return result


def get_today_status(user: str = DEFAULT_USER) -> Dict[str, dict]:
    """Get today's status with MAX level per task (not sum of activities)"""
    from .config import get_user_tasks  # Import here to avoid circular import

    today = get_pacific_date().isoformat()
    user_tasks = get_user_tasks(user)  # Get valid tasks for this user

    with get_conn() as conn:
        # Get the maximum level and corresponding note for each task
        cur = conn.execute(
            """
            SELECT task, MAX(level) as max_level, note, activity 
            FROM checkin 
            WHERE d=? AND user=? 
            GROUP BY task
            ORDER BY max_level DESC
        """,
            (today, user),
        )
        result = {}
        for task, max_level, note, activity in cur.fetchall():
            # Only include tasks that are configured for this user
            if task in user_tasks:
                result[task] = {"level": max_level, "note": note, "activity": activity}
        return result


def set_task_level(task: str, level: int, user: str = DEFAULT_USER):
    """Set task completion level (0-3) for a specific user (legacy function)"""
    today = get_pacific_date().isoformat()
    level = max(0, min(3, level))  # Ensure level is between 0-3

    with get_conn() as conn:
        # First try to update existing row (with default activity)
        result = conn.execute(
            "UPDATE checkin SET level=? WHERE d=? AND task=? AND user=? AND activity=?",
            (level, today, task, user, "activity1"),
        )

        # If no rows were updated, insert a new row with default activity
        if result.rowcount == 0:
            conn.execute(
                "INSERT INTO checkin(d,task,level,user,note,activity) VALUES(?,?,?,?,?,?)",
                (today, task, level, user, "", "activity1"),
            )


def toggle_task(task: str, user: str = DEFAULT_USER):
    """Legacy function for backward compatibility - toggles between 0 and 1"""
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        cur = conn.execute("SELECT level FROM checkin WHERE d=? AND task=? AND user=?", (today, task, user))
        row = cur.fetchone()
        if not row:
            conn.execute(
                "INSERT OR IGNORE INTO checkin(d,task,level,user,note) VALUES(?,?,0,?,?)", (today, task, user, "")
            )
            level = 0
        else:
            level = row[0]
        new_val = 0 if level else 1
        conn.execute("UPDATE checkin SET level=? WHERE d=? AND task=? AND user=?", (new_val, today, task, user))


def get_history(days: int = 30, user: str = DEFAULT_USER):
    from .config import get_user_tasks  # Import here to avoid circular import

    cutoff = (get_pacific_date() - timedelta(days=days - 1)).isoformat()
    user_tasks = get_user_tasks(user)  # Get valid tasks for this user

    with get_conn() as conn:
        # Get the maximum level for each task per date (not sum of activities)
        cur = conn.execute(
            "SELECT d, task, MAX(level) as max_level FROM checkin WHERE d >= ? AND user = ? GROUP BY d, task ORDER BY d DESC, task",
            (cutoff, user),
        )
        rows = cur.fetchall()
        grouped = {}
        for d, task, max_level in rows:
            # Only include tasks that are configured for this user
            if task in user_tasks:
                grouped.setdefault(d, {})[task] = max_level
        return grouped


def set_task_note(task: str, note: str, user: str = DEFAULT_USER):
    """Set note for a task on today's date (legacy function)"""
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        # Ensure row exists for today with default activity
        conn.execute(
            "INSERT OR IGNORE INTO checkin(d,task,level,user,note,activity) VALUES(?,?,0,?,?,?)",
            (today, task, user, "", "activity1"),
        )
        # Update the note
        conn.execute(
            "UPDATE checkin SET note=? WHERE d=? AND task=? AND user=? AND activity=?",
            (note, today, task, user, "activity1"),
        )


def get_task_note(task: str, user: str = DEFAULT_USER) -> str:
    """Get note for a task on today's date (legacy function)"""
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT note FROM checkin WHERE d=? AND task=? AND user=? AND activity=?", (today, task, user, "activity1")
        )
        row = cur.fetchone()
        return row[0] if row else ""


def set_task_activity_note(task: str, activity: str, note: str, user: str = DEFAULT_USER):
    """Set note for a specific task-activity on today's date"""
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        # Ensure row exists for today
        conn.execute(
            "INSERT OR IGNORE INTO checkin(d,task,level,user,note,activity) VALUES(?,?,0,?,?,?)",
            (today, task, user, "", activity),
        )
        # Update the note
        conn.execute(
            "UPDATE checkin SET note=? WHERE d=? AND task=? AND user=? AND activity=?",
            (note, today, task, user, activity),
        )


def get_task_activity_note(task: str, activity: str, user: str = DEFAULT_USER) -> str:
    """Get note for a specific task-activity on today's date"""
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT note FROM checkin WHERE d=? AND task=? AND user=? AND activity=?", (today, task, user, activity)
        )
        row = cur.fetchone()
        return row[0] if row else ""


def get_task_activity_level(task: str, activity: str, user: str = DEFAULT_USER) -> int:
    """Get level for a specific task-activity on today's date"""
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT level FROM checkin WHERE d=? AND task=? AND user=? AND activity=?", (today, task, user, activity)
        )
        row = cur.fetchone()
        return row[0] if row else 0


# Todo-related functions
def init_todo_questions():
    """Initialize todo questions from questions.tsv file"""
    import csv
    from pathlib import Path

    tsv_path = Path(__file__).parent.parent.parent / "data" / "questions.tsv"
    if not tsv_path.exists():
        print(f"Warning: questions.tsv not found at {tsv_path}")
        return

    try:
        with get_conn() as conn:
            # Clear existing questions
            conn.execute("DELETE FROM todo_questions")

            # Read and insert questions from TSV
            with open(tsv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    question_id = create_question_id(row["Problem Name"])
                    conn.execute(
                        """INSERT OR REPLACE INTO todo_questions 
                           (question_id, name, difficulty, link, topics, day) 
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            question_id,
                            row["Problem Name"],
                            row["Difficulty"],
                            row["Link"],
                            row["Topics"],
                            int(row["Day"]),
                        ),
                    )
            print(f"Successfully initialized {conn.total_changes} todo questions")
    except Exception as e:
        print(f"Error initializing todo questions: {e}")
        raise


def create_question_id(name: str) -> str:
    """Create a unique question ID from the problem name"""
    import re

    return re.sub(r"[^a-z0-9\s]", "", name.lower()).replace(" ", "-")


def get_todo_questions():
    """Get all todo questions"""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT question_id, name, difficulty, link, topics, day FROM todo_questions ORDER BY day, name"
        )
        return [
            {
                "question_id": row[0],
                "name": row[1],
                "difficulty": row[2],
                "link": row[3],
                "topics": row[4],
                "day": row[5],
            }
            for row in cur.fetchall()
        ]


def get_completed_questions(user: str = DEFAULT_USER):
    """Get all completed questions for a user"""
    with get_conn() as conn:
        cur = conn.execute("SELECT question_id FROM todo_completed WHERE user = ?", (user,))
        return [{"question_id": row[0]} for row in cur.fetchall()]


def toggle_question_completion(question_id: str, completed: bool, user: str = DEFAULT_USER):
    """Toggle question completion status"""
    with get_conn() as conn:
        if completed:
            # Mark as completed
            conn.execute("INSERT OR REPLACE INTO todo_completed (question_id, user) VALUES (?, ?)", (question_id, user))
        else:
            # Mark as not completed
            conn.execute("DELETE FROM todo_completed WHERE question_id = ? AND user = ?", (question_id, user))
        return True


def get_todo_stats(user: str = DEFAULT_USER):
    """Get todo completion statistics"""
    with get_conn() as conn:
        # Get total questions
        total_cur = conn.execute("SELECT COUNT(*) FROM todo_questions")
        total_questions = total_cur.fetchone()[0]

        # Get completed questions
        completed_cur = conn.execute("SELECT COUNT(*) FROM todo_completed WHERE user = ?", (user,))
        completed_questions = completed_cur.fetchone()[0]

        # Get completed days
        day_stats_cur = conn.execute(
            """
            SELECT tq.day, COUNT(*) as total, 
                   COUNT(tc.question_id) as completed
            FROM todo_questions tq
            LEFT JOIN todo_completed tc ON tq.question_id = tc.question_id AND tc.user = ?
            GROUP BY tq.day
            """,
            (user,),
        )

        completed_days = 0
        for day, total, completed in day_stats_cur.fetchall():
            if total > 0 and completed == total:
                completed_days += 1

        return {
            "total_questions": total_questions,
            "completed_questions": completed_questions,
            "completed_days": completed_days,
            "progress_percentage": (completed_questions / total_questions * 100) if total_questions > 0 else 0,
        }
