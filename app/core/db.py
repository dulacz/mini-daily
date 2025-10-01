import sqlite3
from pathlib import Path
from .config import DB_PATH, get_user_tasks, DEFAULT_USER
from datetime import date, datetime, timedelta
import pytz
from typing import Dict, List, Optional

# Pacific timezone with DST support
PACIFIC_TZ = pytz.timezone("America/Los_Angeles")


def get_pacific_date():
    """Get current date in Pacific Time"""
    return datetime.now(PACIFIC_TZ).date()


Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    """Initialize database tables"""
    with get_conn() as conn:
        # Create activity_completions table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_completions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                task TEXT NOT NULL,
                activity TEXT NOT NULL,
                completed BOOLEAN NOT NULL DEFAULT 0,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, task, activity)
            )
        """
        )

        # Create todo_questions table
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

        # Create todo_completed table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todo_completed(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id TEXT NOT NULL,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(question_id)
            )
        """
        )


def set_activity_completion(task: str, activity: str, completed: bool, date_str: Optional[str] = None):
    """Set activity completion status for a specific date"""
    if date_str is None:
        date_str = get_pacific_date().isoformat()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO activity_completions (date, task, activity, completed, completed_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """,
            (date_str, task, activity, completed),
        )


def get_day_completions(date_str: Optional[str] = None) -> Dict[str, Dict[str, bool]]:
    """Get all activity completions for a specific date organized by task"""
    if date_str is None:
        date_str = get_pacific_date().isoformat()

    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT task, activity, completed FROM activity_completions 
            WHERE date = ?
        """,
            (date_str,),
        )

        result = {}
        for task, activity, completed in cursor.fetchall():
            if task not in result:
                result[task] = {}
            result[task][activity] = bool(completed)

        return result


def get_last_completion_dates(exclude_date: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """Get the last completion date for each activity (excluding a specific date, typically today)"""
    if exclude_date is None:
        exclude_date = get_pacific_date().isoformat()

    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT task, activity, MAX(date) as last_date
            FROM activity_completions 
            WHERE completed = 1 AND date < ?
            GROUP BY task, activity
        """,
            (exclude_date,),
        )

        result = {}
        for task, activity, last_date in cursor.fetchall():
            if task not in result:
                result[task] = {}
            result[task][activity] = last_date

        return result


def get_history(days: int = 30) -> Dict[str, Dict[str, int]]:
    """Get completion history for the last N days"""
    cutoff = (get_pacific_date() - timedelta(days=days - 1)).isoformat()

    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT date, task, COUNT(*) as completed_activities
            FROM activity_completions 
            WHERE date >= ? AND completed = 1
            GROUP BY date, task
            ORDER BY date DESC, task
        """,
            (cutoff,),
        )

        grouped = {}
        for date_str, task, count in cursor.fetchall():
            grouped.setdefault(date_str, {})[task] = count

        return grouped


def get_streak() -> int:
    """Calculate current streak of days with any completed activities"""
    today = get_pacific_date()
    streak = 0

    with get_conn() as conn:
        # Check each day backwards from today
        for i in range(365):  # Max 365 days
            check_date = (today - timedelta(days=i)).isoformat()
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM activity_completions 
                WHERE date = ? AND completed = 1
            """,
                (check_date,),
            )

            count = cursor.fetchone()[0]
            if count > 0:
                streak += 1
            else:
                break

    return streak


def get_total_completions(days: int = 365) -> int:
    """Get total number of completed activities in the last N days"""
    cutoff = (get_pacific_date() - timedelta(days=days - 1)).isoformat()

    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM activity_completions 
            WHERE date >= ? AND completed = 1
        """,
            (cutoff,),
        )

        return cursor.fetchone()[0]


# Todo-related functions (simplified - no user support)
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

            with open(tsv_path, "r", encoding="utf-8") as file:
                reader = csv.DictReader(file, delimiter="\t")
                questions_added = 0

                for row in reader:
                    try:
                        # Generate question_id from the problem name
                        question_id = row["Problem Name"].lower().replace(" ", "_").replace("-", "_")

                        conn.execute(
                            """
                            INSERT INTO todo_questions (question_id, name, difficulty, link, topics, day)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """,
                            (
                                question_id,
                                row["Problem Name"],
                                row["Difficulty"],
                                row["Link"],
                                row["Topics"],
                                int(row["Day"]),
                            ),
                        )
                        questions_added += 1
                    except Exception as e:
                        print(f"Error adding question {row.get('Problem Name', 'unknown')}: {e}")

                print(f"Successfully initialized {questions_added} todo questions")
    except Exception as e:
        print(f"Error initializing todo questions: {e}")


def get_todo_questions() -> List[Dict]:
    """Get all available todo questions"""
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT question_id, name, difficulty, link, topics, day 
            FROM todo_questions 
            ORDER BY day, difficulty
        """
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
            for row in cursor.fetchall()
        ]


def toggle_todo_completion(question_id: str) -> bool:
    """Toggle todo completion status and return new status"""
    with get_conn() as conn:
        # Check if already completed
        cursor = conn.execute("SELECT 1 FROM todo_completed WHERE question_id = ?", (question_id,))
        is_completed = cursor.fetchone() is not None

        if is_completed:
            # Remove completion
            conn.execute("DELETE FROM todo_completed WHERE question_id = ?", (question_id,))
            return False
        else:
            # Add completion
            conn.execute(
                """
                INSERT OR IGNORE INTO todo_completed (question_id)
                VALUES (?)
            """,
                (question_id,),
            )
            return True


def get_completed_todos() -> List[str]:
    """Get list of completed todo question IDs"""
    with get_conn() as conn:
        cursor = conn.execute("SELECT question_id FROM todo_completed")
        return [row[0] for row in cursor.fetchall()]
