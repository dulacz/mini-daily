import sqlite3
from pathlib import Path
from .config import DB_PATH, get_user_tasks, DEFAULT_USER
from .sina_quotes import bare_code, normalize_symbol
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


# ---------------------------------------------------------------------------
# A-share price monitor
#
# Only the watchlist config and triggered alerts are persisted; daily quotes and
# K-line data are deliberately not stored (see app/core/stocks.py snapshot file).
# ---------------------------------------------------------------------------

def _validate_symbol(symbol: str) -> str:
    return normalize_symbol(symbol)


# Alert bands are global, not per stock.
DEFAULT_ALERT_SETTINGS = {"rsi_high": 70.0, "rsi_low": 30.0, "pct_high": 90.0, "pct_low": 10.0}


def init_stocks():
    """Create the stock tables and seed the watchlist from data/stocks.yaml."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                direction TEXT NOT NULL,
                price REAL NOT NULL,
                threshold REAL NOT NULL,
                triggered_at TEXT NOT NULL,
                UNIQUE(symbol, trade_date, direction)
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_daily (
                symbol TEXT NOT NULL,
                day TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL NOT NULL,
                volume INTEGER,
                PRIMARY KEY (symbol, day)
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """)
        # Drop the legacy per-stock threshold columns; the bands are global now.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(stocks)")}
        if "target_high" in columns:
            conn.execute("ALTER TABLE stocks RENAME TO stocks_legacy")
            conn.execute("""
                CREATE TABLE stocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1
                )
                """)
            conn.execute(
                "INSERT INTO stocks (id, symbol, name, sort_order, enabled) "
                "SELECT id, symbol, name, sort_order, enabled FROM stocks_legacy"
            )
            conn.execute("DROP TABLE stocks_legacy")
            print("[Stocks] Migrated stocks table to global alert settings")

    seed_path = Path(__file__).parent.parent.parent / "data" / "stocks.yaml"
    if not seed_path.exists():
        return
    try:
        import yaml

        with open(seed_path, "r", encoding="utf-8") as f:
            entries = (yaml.safe_load(f) or {}).get("stocks", []) or []
    except Exception as e:
        print(f"Warning: Failed to read stocks.yaml: {e}")
        return

    with get_conn() as conn:
        # A persistent flag, not an empty table: deleting every stock must not re-seed on restart.
        already_seeded = (
            conn.execute("SELECT 1 FROM app_meta WHERE key = 'stocks_seeded'").fetchone() is not None
            or conn.execute("SELECT 1 FROM stocks LIMIT 1").fetchone() is not None
        )
        added = 0
        for order, entry in enumerate(entries):
            if already_seeded:
                break
            try:
                symbol = _validate_symbol(entry.get("symbol", ""))
            except ValueError as e:
                print(f"Warning: skipping stocks.yaml entry — {e}")
                continue
            conn.execute(
                "INSERT OR IGNORE INTO stocks (symbol, name, sort_order, enabled) VALUES (?, ?, ?, 1)",
                (symbol, str(entry.get("name") or symbol), order),
            )
            added += 1
        conn.execute("INSERT OR IGNORE INTO app_meta (key, value) VALUES ('stocks_seeded', '1')")
    if added:
        print(f"[Stocks] Seeded {added} stocks from stocks.yaml")


def get_alert_settings() -> Dict[str, Optional[float]]:
    """Global RSI and 1-year percentile bands, falling back to the defaults."""
    with get_conn() as conn:
        stored = dict(conn.execute("SELECT key, value FROM app_meta WHERE key LIKE 'alert_%'").fetchall())
    settings: Dict[str, Optional[float]] = {}
    for key, default in DEFAULT_ALERT_SETTINGS.items():
        raw = stored.get(f"alert_{key}")
        if raw is None:
            settings[key] = default
        else:
            settings[key] = float(raw) if raw != "" else None
    return settings


def set_alert_settings(**values: Optional[float]):
    """Store alert bands; an explicit None disables that side."""
    unknown = set(values) - set(DEFAULT_ALERT_SETTINGS)
    if unknown:
        raise ValueError(f"未知的警告设置: {', '.join(sorted(unknown))}")
    for key, value in values.items():
        if value is not None and not 0 <= value <= 100:
            raise ValueError(f"{key} 需在 0-100 之间")
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO app_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [(f"alert_{k}", "" if v is None else str(v)) for k, v in values.items()],
        )


_STOCK_COLUMNS = "id, symbol, name, sort_order, enabled"


def _stock_row_to_dict(row) -> Dict:
    return {
        "id": row[0],
        "symbol": row[1],
        "code": bare_code(row[1]),
        "name": row[2],
        "sort_order": row[3],
        "enabled": bool(row[4]),
    }


def list_stocks(enabled_only: bool = False) -> List[Dict]:
    """Return the watchlist ordered by the bare 6-digit code."""
    query = f"SELECT {_STOCK_COLUMNS} FROM stocks"
    if enabled_only:
        query += " WHERE enabled = 1"
    # substr(symbol, 3) drops the sh/sz/bj prefix so ordering matches what the UI shows.
    query += " ORDER BY substr(symbol, 3), symbol"
    with get_conn() as conn:
        return [_stock_row_to_dict(row) for row in conn.execute(query).fetchall()]


def add_stock(symbol: str, name: str) -> Dict:
    """Add a stock to the watchlist."""
    symbol = _validate_symbol(symbol)
    name = (name or "").strip() or symbol
    with get_conn() as conn:
        if conn.execute("SELECT id FROM stocks WHERE symbol = ?", (symbol,)).fetchone():
            raise ValueError(f"Stock {symbol} is already on the watchlist")
        next_order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM stocks").fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO stocks (symbol, name, sort_order, enabled) VALUES (?, ?, ?, 1)",
            (symbol, name, next_order),
        )
        return {
            "id": cursor.lastrowid,
            "symbol": symbol,
            "code": bare_code(symbol),
            "name": name,
            "sort_order": next_order,
            "enabled": True,
        }


def update_stock(stock_id: int, name: Optional[str] = None, enabled: Optional[bool] = None) -> Dict:
    """Rename a stock or toggle whether it is monitored."""
    with get_conn() as conn:
        row = conn.execute(f"SELECT {_STOCK_COLUMNS} FROM stocks WHERE id = ?", (stock_id,)).fetchone()
        if row is None:
            raise ValueError(f"Stock {stock_id} not found")
        current = _stock_row_to_dict(row)
        updated = {
            "name": (name.strip() if name and name.strip() else current["name"]),
            "enabled": current["enabled"] if enabled is None else bool(enabled),
        }
        conn.execute(
            "UPDATE stocks SET name = ?, enabled = ? WHERE id = ?",
            (updated["name"], int(updated["enabled"]), stock_id),
        )
        return current | updated


def delete_stock(stock_id: int):
    """Remove a stock from the watchlist along with its stored daily bars."""
    with get_conn() as conn:
        conn.execute("DELETE FROM stock_daily WHERE symbol = (SELECT symbol FROM stocks WHERE id = ?)", (stock_id,))
        conn.execute("DELETE FROM stocks WHERE id = ?", (stock_id,))


def upsert_daily_bars(symbol: str, bars: List[Dict]):
    """Store daily bars; the most recent day is rewritten because it moves intraday."""
    if not bars:
        return
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO stock_daily (symbol, day, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, day) DO UPDATE SET
                open = excluded.open, high = excluded.high, low = excluded.low,
                close = excluded.close, volume = excluded.volume
            """,
            [
                (symbol, b["day"], b.get("open"), b.get("high"), b.get("low"), b["close"], b.get("volume"))
                for b in bars
                if b.get("day") and b.get("close")
            ],
        )


def replace_daily_bars(symbol: str, bars: List[Dict]):
    """Swap in a fresh series, dropping older rows that a re-adjustment invalidated."""
    if not bars:
        return
    with get_conn() as conn:
        conn.execute("DELETE FROM stock_daily WHERE symbol = ?", (symbol,))
        conn.executemany(
            "INSERT INTO stock_daily (symbol, day, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (symbol, b["day"], b.get("open"), b.get("high"), b.get("low"), b["close"], b.get("volume"))
                for b in bars
                if b.get("day") and b.get("close")
            ],
        )


def get_daily_bars(symbol: str, limit: int = 120) -> List[Dict]:
    """Return the most recent stored daily bars, oldest first."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT day, open, high, low, close, volume FROM stock_daily WHERE symbol = ? ORDER BY day DESC LIMIT ?",
            (symbol, max(1, int(limit))),
        ).fetchall()
    return [
        {"day": r[0], "open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
        for r in reversed(rows)
    ]


def record_alert(symbol: str, name: str, trade_date: str, direction: str, price: float, threshold: float) -> bool:
    """Store an alert. Returns False when this symbol/date/direction already fired."""
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO stock_alerts (symbol, name, trade_date, direction, price, threshold, triggered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (symbol, name, trade_date, direction, price, threshold, datetime.now(APP_TZ).isoformat(timespec="seconds")),
        )
        return cursor.rowcount > 0


def list_alerts(limit: int = 50) -> List[Dict]:
    """Return the most recently triggered alerts."""
    limit = max(1, min(int(limit), 500))
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT symbol, name, trade_date, direction, price, threshold, triggered_at
            FROM stock_alerts
            ORDER BY trade_date DESC, triggered_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "symbol": row[0],
                "code": bare_code(row[0]),
                "name": row[1],
                "trade_date": row[2],
                "direction": row[3],
                "price": row[4],
                "threshold": row[5],
                "triggered_at": row[6],
            }
            for row in cursor.fetchall()
        ]


# ---------------------------------------------------------------------------
# Paper trading account
# ---------------------------------------------------------------------------

DEFAULT_DRIFT_TOLERANCE_PCT = 20.0
DEFAULT_MIN_TRADE_AMOUNT = 3000.0


def init_paper():
    """Create the paper-trading tables and the single account row."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cash REAL NOT NULL DEFAULT 0,
                drift_tolerance_pct REAL NOT NULL DEFAULT 20
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                shares INTEGER NOT NULL DEFAULT 0,
                cost_total REAL NOT NULL DEFAULT 0,
                realized_pnl REAL NOT NULL DEFAULT 0,
                target_weight REAL
            )
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                direction TEXT NOT NULL,
                weight_pct REAL NOT NULL,
                target_pct REAL NOT NULL,
                drift_pct REAL NOT NULL,
                triggered_at TEXT NOT NULL,
                UNIQUE(symbol, trade_date, direction)
            )
            """)
        conn.execute(
            "INSERT OR IGNORE INTO paper_account (id, cash, drift_tolerance_pct) VALUES (1, 0, ?)",
            (DEFAULT_DRIFT_TOLERANCE_PCT,),
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(paper_account)")}
        if "min_trade_amount" not in columns:
            conn.execute(
                f"ALTER TABLE paper_account ADD COLUMN min_trade_amount REAL NOT NULL DEFAULT {DEFAULT_MIN_TRADE_AMOUNT}"
            )
        conn.execute("DROP TABLE IF EXISTS paper_trades")


def get_paper_account() -> Dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT cash, drift_tolerance_pct, min_trade_amount FROM paper_account WHERE id = 1"
        ).fetchone()
    if row is None:
        return {
            "cash": 0.0,
            "drift_tolerance_pct": DEFAULT_DRIFT_TOLERANCE_PCT,
            "min_trade_amount": DEFAULT_MIN_TRADE_AMOUNT,
        }
    return {"cash": row[0], "drift_tolerance_pct": row[1], "min_trade_amount": row[2]}


def set_paper_cash(cash: float):
    if cash < 0:
        raise ValueError("现金不能为负数")
    with get_conn() as conn:
        conn.execute("UPDATE paper_account SET cash = ? WHERE id = 1", (float(cash),))


def set_paper_settings(drift_tolerance_pct: float, min_trade_amount: Optional[float] = None):
    if drift_tolerance_pct <= 0:
        raise ValueError("漂移容差必须大于 0")
    if min_trade_amount is not None and min_trade_amount < 0:
        raise ValueError("最小调仓金额不能为负数")
    with get_conn() as conn:
        conn.execute("UPDATE paper_account SET drift_tolerance_pct = ? WHERE id = 1", (float(drift_tolerance_pct),))
        if min_trade_amount is not None:
            conn.execute("UPDATE paper_account SET min_trade_amount = ? WHERE id = 1", (float(min_trade_amount),))


def list_paper_positions() -> List[Dict]:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT symbol, name, shares, cost_total, realized_pnl, target_weight
            FROM paper_positions ORDER BY substr(symbol, 3), symbol
            """
        )
        return [
            {
                "symbol": row[0],
                "code": bare_code(row[0]),
                "name": row[1],
                "shares": row[2],
                "cost_total": row[3],
                "realized_pnl": row[4],
                "target_weight": row[5],
            }
            for row in cursor.fetchall()
        ]


def record_paper_trade(symbol: str, name: str, side: str, shares: int, price: float) -> Dict:
    """Apply a buy/sell to the account. Raises ValueError on insufficient cash or shares."""
    symbol = _validate_symbol(symbol)
    if side not in ("buy", "sell"):
        raise ValueError("方向必须是 buy 或 sell")
    if shares <= 0:
        raise ValueError("数量必须大于 0")
    if price <= 0:
        raise ValueError("成交价必须大于 0")

    amount = round(shares * price, 2)
    with get_conn() as conn:
        cash = conn.execute("SELECT cash FROM paper_account WHERE id = 1").fetchone()[0]
        row = conn.execute(
            "SELECT shares, cost_total, realized_pnl FROM paper_positions WHERE symbol = ?", (symbol,)
        ).fetchone()
        held, cost_total, realized = row if row else (0, 0.0, 0.0)

        if side == "buy":
            if amount > cash:
                raise ValueError(f"现金不足：需要 {amount:,.2f}，可用 {cash:,.2f}")
            cash = round(cash - amount, 2)
            held += shares
            cost_total = round(cost_total + amount, 2)
        else:
            if shares > held:
                raise ValueError(f"持股不足：需要 {shares} 股，持有 {held} 股")
            avg_cost = cost_total / held
            realized = round(realized + amount - avg_cost * shares, 2)
            cost_total = round(cost_total - avg_cost * shares, 2)
            held -= shares
            cash = round(cash + amount, 2)

        conn.execute(
            """
            INSERT INTO paper_positions (symbol, name, shares, cost_total, realized_pnl)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name = excluded.name, shares = excluded.shares,
                cost_total = excluded.cost_total, realized_pnl = excluded.realized_pnl
            """,
            (symbol, name or symbol, held, cost_total, realized),
        )
        conn.execute("UPDATE paper_account SET cash = ? WHERE id = 1", (cash,))

    return {
        "symbol": symbol,
        "code": bare_code(symbol),
        "side": side,
        "shares": shares,
        "price": price,
        "amount": amount,
        "cash": cash,
    }


def set_paper_target_weight(symbol: str, target_weight: Optional[float], name: Optional[str] = None):
    """Set a target weight, creating a flat position so you can allocate into a new name."""
    if target_weight is not None and not 0 <= target_weight <= 100:
        raise ValueError("目标权重需在 0-100 之间")
    symbol = _validate_symbol(symbol)
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM paper_positions WHERE symbol = ?", (symbol,)).fetchone() is None:
            if not name:
                raise ValueError(f"持仓中没有 {bare_code(symbol)}")
            conn.execute(
                "INSERT INTO paper_positions (symbol, name, shares, cost_total, realized_pnl) VALUES (?, ?, 0, 0, 0)",
                (symbol, name),
            )
        conn.execute("UPDATE paper_positions SET target_weight = ? WHERE symbol = ?", (target_weight, symbol))


def delete_paper_position(symbol: str):
    """Drop a fully closed position row."""
    symbol = _validate_symbol(symbol)
    with get_conn() as conn:
        row = conn.execute("SELECT shares FROM paper_positions WHERE symbol = ?", (symbol,)).fetchone()
        if row is None:
            return
        if row[0] > 0:
            raise ValueError("仍有持股，请先全部卖出")
        conn.execute("DELETE FROM paper_positions WHERE symbol = ?", (symbol,))


def set_paper_cost(symbol: str, avg_cost: float):
    """Override the average cost of a holding, e.g. to match a real broker statement."""
    if avg_cost < 0:
        raise ValueError("成本价不能为负数")
    symbol = _validate_symbol(symbol)
    with get_conn() as conn:
        row = conn.execute("SELECT shares FROM paper_positions WHERE symbol = ?", (symbol,)).fetchone()
        if row is None:
            raise ValueError(f"持仓中没有 {bare_code(symbol)}")
        if row[0] <= 0:
            raise ValueError("没有持股，无法设定成本价")
        conn.execute(
            "UPDATE paper_positions SET cost_total = ? WHERE symbol = ?",
            (round(avg_cost * row[0], 2), symbol),
        )


def record_paper_alert(
    symbol: str, name: str, trade_date: str, direction: str, weight_pct: float, target_pct: float, drift_pct: float
) -> bool:
    """Store a drift alert. Returns False when this symbol/date/direction already fired."""
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO paper_alerts
                (symbol, name, trade_date, direction, weight_pct, target_pct, drift_pct, triggered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                name,
                trade_date,
                direction,
                weight_pct,
                target_pct,
                drift_pct,
                datetime.now(APP_TZ).isoformat(timespec="seconds"),
            ),
        )
        return cursor.rowcount > 0


def list_paper_alerts(limit: int = 50) -> List[Dict]:
    limit = max(1, min(int(limit), 500))
    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT symbol, name, trade_date, direction, weight_pct, target_pct, drift_pct, triggered_at
            FROM paper_alerts ORDER BY trade_date DESC, triggered_at DESC LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "symbol": row[0],
                "name": row[1],
                "trade_date": row[2],
                "direction": row[3],
                "weight_pct": row[4],
                "target_pct": row[5],
                "drift_pct": row[6],
                "triggered_at": row[7],
            }
            for row in cursor.fetchall()
        ]
