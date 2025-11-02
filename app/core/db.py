import sqlite3
from pathlib import Path
from .config import DB_PATH, get_user_tasks, DEFAULT_USER
from datetime import date, datetime, timedelta
import pytz
from typing import Dict, List, Optional

# Timezone configuration
APP_TZ = pytz.timezone("Pacific/Honolulu")


def get_current_date():
    """Get current date in the configured timezone"""
    return datetime.now(APP_TZ).date()


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

        # Create todo_coding table (includes all TSV columns)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todo_coding(
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                difficulty TEXT,
                link TEXT,
                topics TEXT,
                completed BOOLEAN NOT NULL DEFAULT 0,
                completed_at TIMESTAMP
            )
        """
        )


def set_activity_completion(task: str, activity: str, completed: bool, date_str: Optional[str] = None):
    """Set activity completion status for a specific date"""
    if date_str is None:
        date_str = get_current_date().isoformat()

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
        date_str = get_current_date().isoformat()

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
        exclude_date = get_current_date().isoformat()

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
    cutoff = (get_current_date() - timedelta(days=days - 1)).isoformat()

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
    today = get_current_date()
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
    cutoff = (get_current_date() - timedelta(days=days - 1)).isoformat()

    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM activity_completions 
            WHERE date >= ? AND completed = 1
        """,
            (cutoff,),
        )

        return cursor.fetchone()[0]


# Todo_coding functions
def init_todo_coding():
    """Initialize todo_coding from todo_coding.tsv file on server startup"""
    import csv
    from pathlib import Path

    tsv_path = Path(__file__).parent.parent.parent / "data" / "todo_coding.tsv"
    if not tsv_path.exists():
        print(f"Warning: todo_coding.tsv not found at {tsv_path}")
        return

    try:
        with get_conn() as conn:
            with open(tsv_path, "r", encoding="utf-8") as file:
                reader = csv.DictReader(file, delimiter="\t")
                problems_added = 0

                for row in reader:
                    try:
                        problem_number = int(row["ProblemNumber"])
                        problem_name = row["Problem Name"]
                        difficulty = row.get("Difficulty", "")
                        link = row.get("Link", "")
                        topics = row.get("Topics", "")

                        # Insert new problems with completed=0 if they don't exist
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO todo_coding (id, name, difficulty, link, topics, completed, completed_at)
                            VALUES (?, ?, ?, ?, ?, 0, NULL)
                        """,
                            (problem_number, problem_name, difficulty, link, topics),
                        )
                        
                        if conn.total_changes > 0:
                            problems_added += 1
                    except Exception as e:
                        print(f"Error adding problem {row.get('Problem Name', 'unknown')}: {e}")

                if problems_added > 0:
                    print(f"Successfully added {problems_added} new todo_coding problems")
    except Exception as e:
        print(f"Error initializing todo_coding: {e}")


def get_todo_coding_items() -> List[Dict]:
    """Get all todo_coding items"""
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT id, name, difficulty, link, topics, completed, completed_at 
            FROM todo_coding 
            ORDER BY id
        """
        )

        return [
            {
                "id": row[0],
                "name": row[1],
                "difficulty": row[2],
                "link": row[3],
                "topics": row[4],
                "completed": bool(row[5]),
                "completed_at": row[6],
            }
            for row in cursor.fetchall()
        ]


def toggle_todo_coding_completion(problem_id: int) -> bool:
    """Toggle todo_coding completion status and return new status"""
    with get_conn() as conn:
        # Get current status
        cursor = conn.execute("SELECT completed FROM todo_coding WHERE id = ?", (problem_id,))
        row = cursor.fetchone()
        
        if row is None:
            raise ValueError(f"Problem ID {problem_id} not found")
        
        current_status = bool(row[0])
        new_status = not current_status
        
        # Update status
        if new_status:
            # Mark as completed
            conn.execute(
                """
                UPDATE todo_coding 
                SET completed = 1, completed_at = datetime('now')
                WHERE id = ?
            """,
                (problem_id,),
            )
        else:
            # Mark as not completed
            conn.execute(
                """
                UPDATE todo_coding 
                SET completed = 0, completed_at = NULL
                WHERE id = ?
            """,
                (problem_id,),
            )
        
        return new_status
