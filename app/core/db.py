import sqlite3
from pathlib import Path
from .config import DB_PATH, TASKS
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
    UNIQUE(d, task)
)
"""

# Migration DDL to update existing databases
MIGRATION_DDL = """
ALTER TABLE checkin ADD COLUMN level INTEGER DEFAULT 0;
UPDATE checkin SET level = done WHERE level = 0;
"""


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        # Create table
        conn.execute(DDL)

        # Try to migrate existing data
        try:
            # Check if level column exists
            cursor = conn.execute("PRAGMA table_info(checkin)")
            columns = [column[1] for column in cursor.fetchall()]
            if "level" not in columns:
                # Add level column and migrate data
                conn.execute("ALTER TABLE checkin ADD COLUMN level INTEGER DEFAULT 0")
                conn.execute("UPDATE checkin SET level = done WHERE level = 0")
        except sqlite3.Error as e:
            print(f"Migration note: {e}")


def ensure_today_rows():
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        for t in TASKS:
            conn.execute("INSERT OR IGNORE INTO checkin(d,task,level) VALUES(?,?,0)", (today, t))


def get_today_status() -> Dict[str, int]:
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        # Try new column first, fallback to old column for compatibility
        try:
            cur = conn.execute("SELECT task, level FROM checkin WHERE d=?", (today,))
            return {task: level for task, level in cur.fetchall()}
        except sqlite3.OperationalError:
            # Fallback to old 'done' column
            cur = conn.execute("SELECT task, done FROM checkin WHERE d=?", (today,))
            return {task: (1 if done else 0) for task, done in cur.fetchall()}


def set_task_level(task: str, level: int):
    """Set task completion level (0-3)"""
    today = get_pacific_date().isoformat()
    level = max(0, min(3, level))  # Ensure level is between 0-3

    with get_conn() as conn:
        # Insert or update the task level
        conn.execute("INSERT OR REPLACE INTO checkin(d,task,level) VALUES(?,?,?)", (today, task, level))


def toggle_task(task: str):
    """Legacy function for backward compatibility - toggles between 0 and 1"""
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        try:
            cur = conn.execute("SELECT level FROM checkin WHERE d=? AND task=?", (today, task))
            row = cur.fetchone()
            if not row:
                conn.execute("INSERT OR IGNORE INTO checkin(d,task,level) VALUES(?,?,0)", (today, task))
                level = 0
            else:
                level = row[0]
            new_val = 0 if level else 1
            conn.execute("UPDATE checkin SET level=? WHERE d=? AND task=?", (new_val, today, task))
        except sqlite3.OperationalError:
            # Fallback to old 'done' column
            cur = conn.execute("SELECT done FROM checkin WHERE d=? AND task=?", (today, task))
            row = cur.fetchone()
            if not row:
                conn.execute("INSERT OR IGNORE INTO checkin(d,task,done) VALUES(?,?,0)", (today, task))
                done = 0
            else:
                done = row[0]
            new_val = 0 if done else 1
            conn.execute("UPDATE checkin SET done=? WHERE d=? AND task=?", (new_val, today, task))


def get_history(days: int = 30):
    cutoff = (get_pacific_date() - timedelta(days=days - 1)).isoformat()
    with get_conn() as conn:
        try:
            # Try new schema first
            cur = conn.execute("SELECT d, task, level FROM checkin WHERE d >= ? ORDER BY d DESC, task", (cutoff,))
            rows = cur.fetchall()
            grouped = {}
            for d, task, level in rows:
                grouped.setdefault(d, {})[task] = level
            return grouped
        except sqlite3.OperationalError:
            # Fallback to old schema
            cur = conn.execute("SELECT d, task, done FROM checkin WHERE d >= ? ORDER BY d DESC, task", (cutoff,))
            rows = cur.fetchall()
            grouped = {}
            for d, task, done in rows:
                grouped.setdefault(d, {})[task] = done
            return grouped
