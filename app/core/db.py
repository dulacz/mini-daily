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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_completions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                task TEXT NOT NULL,
                activity TEXT NOT NULL,
                completed BOOLEAN NOT NULL DEFAULT 0,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, task, activity)
            )
        """)

        # Create todo_coding table (includes all TSV columns)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS todo_coding(
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                difficulty TEXT,
                link TEXT,
                topics TEXT,
                completed BOOLEAN NOT NULL DEFAULT 0,
                completed_at TIMESTAMP
            )
        """)


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


def get_activity_recent_counts(task_configs: Dict) -> Dict[str, Dict[str, int]]:
    """Get completion counts per activity within each activity's 3x interval_days window."""
    today = get_current_date()
    result = {}
    with get_conn() as conn:
        for task_id, task_cfg in task_configs.items():
            activities = task_cfg.get("activities", {})
            for activity_id, act_cfg in activities.items():
                interval = act_cfg.get("interval_days")
                if not interval:
                    continue
                cutoff = (today - timedelta(days=3 * interval - 1)).isoformat()
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) FROM activity_completions
                    WHERE task = ? AND activity = ? AND completed = 1 AND date >= ?
                    """,
                    (task_id, activity_id, cutoff),
                )
                count = cursor.fetchone()[0]
                result.setdefault(task_id, {})[activity_id] = count
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
        cursor = conn.execute("""
            SELECT id, name, difficulty, link, topics, completed, completed_at 
            FROM todo_coding 
            ORDER BY id
        """)

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

        # Get current date in app timezone
        current_date = get_current_date().isoformat()

        # Update status
        if new_status:
            # Mark as completed with current date in app timezone
            conn.execute(
                """
                UPDATE todo_coding 
                SET completed = 1, completed_at = ?
                WHERE id = ?
            """,
                (current_date, problem_id),
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


def get_today_questions(date_str: Optional[str] = None) -> List[Dict]:
    """Get today's questions: up to 2 medium + 1 hard, selected in order by ID.

    Reduces count as questions are completed today:
    - If 0 completed today: show 2 medium + 1 hard (3 total)
    - If 1 completed today: show fewer questions (2 total)
    - As more are completed, list shrinks accordingly

    Selection rules:
    - Choose problems in order of ID (lowest first)
    - Skip problems completed before today
    - Include problems completed today (they're still in the list)
    """
    if date_str is None:
        date_str = get_current_date().isoformat()

    with get_conn() as conn:
        # Count how many medium problems were completed today
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM todo_coding 
            WHERE difficulty = 'Medium' 
            AND completed_at = ?
            """,
            (date_str,),
        )
        medium_completed_today = cursor.fetchone()[0]

        # Count how many hard problems were completed today
        cursor = conn.execute(
            """
            SELECT COUNT(*) FROM todo_coding 
            WHERE difficulty = 'Hard' 
            AND completed_at = ?
            """,
            (date_str,),
        )
        hard_completed_today = cursor.fetchone()[0]

        # Calculate how many to show: 2 medium + 1 hard, minus what's completed
        medium_needed = max(0, 2 - medium_completed_today)
        hard_needed = max(0, 1 - hard_completed_today)

        results = []

        # Get hard problem(s) if needed
        if hard_needed > 0:
            cursor = conn.execute(
                """
                SELECT id, name, difficulty, link, topics, completed, completed_at
                FROM todo_coding 
                WHERE difficulty = 'Hard' 
                AND (completed = 0 OR completed_at = ?)
                ORDER BY id
                LIMIT ?
                """,
                (date_str, hard_needed),
            )
            results.extend(cursor.fetchall())

        # Get medium problems if needed
        if medium_needed > 0:
            cursor = conn.execute(
                """
                SELECT id, name, difficulty, link, topics, completed, completed_at
                FROM todo_coding 
                WHERE difficulty = 'Medium'
                AND (completed = 0 OR completed_at = ?)
                ORDER BY id
                LIMIT ?
                """,
                (date_str, medium_needed),
            )
            results.extend(cursor.fetchall())

        # If we still don't have problems (e.g., ran out of hard), fill with any remaining
        total_needed = 3 - medium_completed_today - hard_completed_today
        if len(results) < total_needed and total_needed > 0:
            needed = total_needed - len(results)
            existing_ids = [row[0] for row in results]

            cursor = conn.execute(
                f"""
                SELECT id, name, difficulty, link, topics, completed, completed_at
                FROM todo_coding 
                WHERE (completed = 0 OR completed_at = ?)
                AND id NOT IN ({','.join('?' * len(existing_ids)) if existing_ids else 'NULL'})
                ORDER BY id
                LIMIT ?
                """,
                (date_str, *existing_ids, needed) if existing_ids else (date_str, needed),
            )
            results.extend(cursor.fetchall())

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
            for row in results
        ]


# ---------------------------------------------------------------------------
# Review Cards (Anki-style spaced repetition)
# ---------------------------------------------------------------------------

# Ebbinghaus forgetting curve intervals (in days)
REVIEW_INTERVALS = [1, 2, 4, 7, 15, 30]


def init_review_cards():
    """Create review_cards and review_categories tables"""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS review_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS review_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                interval_index INTEGER NOT NULL DEFAULT 0,
                next_review_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_reviewed_at TEXT,
                review_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (category_id) REFERENCES review_categories(id)
            )
            """)


def get_review_categories() -> List[Dict]:
    """Get all review categories"""
    with get_conn() as conn:
        cursor = conn.execute("SELECT id, name FROM review_categories ORDER BY name")
        return [{"id": row[0], "name": row[1]} for row in cursor.fetchall()]


def create_review_category(name: str) -> int:
    """Create a category if it doesn't exist, return its id"""
    name = name.strip()
    with get_conn() as conn:
        cursor = conn.execute("SELECT id FROM review_categories WHERE name = ?", (name,))
        row = cursor.fetchone()
        if row:
            return row[0]
        cursor = conn.execute("INSERT INTO review_categories (name) VALUES (?)", (name,))
        return cursor.lastrowid


def create_review_card(title: str, category_id: int) -> Dict:
    """Create a new review card. First review is tomorrow."""
    today = get_current_date().isoformat()
    next_review = (get_current_date() + timedelta(days=REVIEW_INTERVALS[0])).isoformat()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO review_cards (title, category_id, interval_index, next_review_date, created_at)
            VALUES (?, ?, 0, ?, ?)
            """,
            (title, category_id, next_review, today),
        )
        return {
            "id": cursor.lastrowid,
            "title": title,
            "category_id": category_id,
            "interval_index": 0,
            "next_review_date": next_review,
            "created_at": today,
            "last_reviewed_at": None,
            "review_count": 0,
        }


def review_card(card_id: int, difficulty: str) -> Dict:
    """Review a card with difficulty: easy / ok / hard.

    Given the card's current interval_index i in REVIEW_INTERVALS:
      - easy:  next interval = REVIEW_INTERVALS[i+1]  (advance)
      - ok:    next interval = REVIEW_INTERVALS[i]    (stay)
      - hard:  next interval = REVIEW_INTERVALS[i-1]  (regress)

    When a card at the last interval (30d) is reviewed with easy,
    it becomes mastered (next_review_date = NULL).
    """
    today = get_current_date()
    with get_conn() as conn:
        cursor = conn.execute(
            "SELECT interval_index, review_count FROM review_cards WHERE id = ?",
            (card_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Card {card_id} not found")

        idx, review_count = row
        max_idx = len(REVIEW_INTERVALS) - 1

        if difficulty == "easy":
            new_idx = min(idx + 1, max_idx + 1)  # can go past max to indicate mastered
        elif difficulty == "ok":
            new_idx = idx
        elif difficulty == "hard":
            new_idx = max(idx - 1, 0)
        else:
            raise ValueError(f"Invalid difficulty: {difficulty}")

        # Mastered: past the last interval
        if new_idx > max_idx:
            conn.execute(
                """
                UPDATE review_cards
                SET interval_index = ?, next_review_date = NULL,
                    last_reviewed_at = ?, review_count = ?
                WHERE id = ?
                """,
                (new_idx, today.isoformat(), review_count + 1, card_id),
            )
            return {
                "id": card_id,
                "interval_index": new_idx,
                "interval_days": None,
                "next_review_date": None,
                "review_count": review_count + 1,
                "mastered": True,
            }

        interval_days = REVIEW_INTERVALS[new_idx]
        next_review = (today + timedelta(days=interval_days)).isoformat()

        conn.execute(
            """
            UPDATE review_cards
            SET interval_index = ?, next_review_date = ?,
                last_reviewed_at = ?, review_count = ?
            WHERE id = ?
            """,
            (new_idx, next_review, today.isoformat(), review_count + 1, card_id),
        )
        return {
            "id": card_id,
            "interval_index": new_idx,
            "interval_days": interval_days,
            "next_review_date": next_review,
            "review_count": review_count + 1,
            "mastered": False,
        }


def _card_row_to_dict(row) -> Dict:
    """Convert a review_cards query row to a dict."""
    idx = row[4]
    max_idx = len(REVIEW_INTERVALS) - 1
    mastered = idx > max_idx
    return {
        "id": row[0],
        "title": row[1],
        "category_id": row[2],
        "category_name": row[3],
        "interval_index": idx,
        "interval_days": REVIEW_INTERVALS[idx] if idx <= max_idx else None,
        "next_review_date": row[5],
        "created_at": row[6],
        "last_reviewed_at": row[7],
        "review_count": row[8],
        "mastered": mastered,
        "progress": min(idx, len(REVIEW_INTERVALS) - 1) * 100 // (len(REVIEW_INTERVALS) - 1),
    }


def get_review_cards() -> List[Dict]:
    """Get all review cards with category name"""
    with get_conn() as conn:
        cursor = conn.execute("""
            SELECT c.id, c.title, c.category_id, cat.name AS category_name,
                   c.interval_index, c.next_review_date, c.created_at,
                   c.last_reviewed_at, c.review_count
            FROM review_cards c
            JOIN review_categories cat ON c.category_id = cat.id
            ORDER BY cat.name, c.next_review_date
            """)
        return [_card_row_to_dict(row) for row in cursor.fetchall()]


def get_today_review_cards() -> List[Dict]:
    """Get cards due for review today (next_review_date <= today), excluding mastered"""
    today = get_current_date().isoformat()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT c.id, c.title, c.category_id, cat.name AS category_name,
                   c.interval_index, c.next_review_date, c.created_at,
                   c.last_reviewed_at, c.review_count
            FROM review_cards c
            JOIN review_categories cat ON c.category_id = cat.id
            WHERE c.next_review_date IS NOT NULL AND c.next_review_date <= ?
            ORDER BY c.next_review_date, cat.name
            """,
            (today,),
        )
        return [_card_row_to_dict(row) for row in cursor.fetchall()]


def delete_review_card(card_id: int):
    """Delete a review card"""
    with get_conn() as conn:
        conn.execute("DELETE FROM review_cards WHERE id = ?", (card_id,))


def rename_review_card(card_id: int, new_title: str):
    """Rename a review card"""
    new_title = new_title.strip()
    if not new_title:
        raise ValueError("Title cannot be empty")
    with get_conn() as conn:
        cursor = conn.execute("SELECT id FROM review_cards WHERE id = ?", (card_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Card {card_id} not found")
        conn.execute("UPDATE review_cards SET title = ? WHERE id = ?", (new_title, card_id))
