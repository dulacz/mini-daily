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
    UNIQUE(d, task, user)
)
"""


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        # Create table with new schema
        conn.execute(DDL)


def ensure_today_rows(user: str = DEFAULT_USER):
    today = get_pacific_date().isoformat()
    user_tasks = get_user_tasks(user)
    with get_conn() as conn:
        for task in user_tasks:
            conn.execute("INSERT OR IGNORE INTO checkin(d,task,level,user) VALUES(?,?,0,?)", (today, task, user))


def get_today_status(user: str = DEFAULT_USER) -> Dict[str, int]:
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        cur = conn.execute("SELECT task, level FROM checkin WHERE d=? AND user=?", (today, user))
        return {task: level for task, level in cur.fetchall()}


def set_task_level(task: str, level: int, user: str = DEFAULT_USER):
    """Set task completion level (0-3) for a specific user"""
    today = get_pacific_date().isoformat()
    level = max(0, min(3, level))  # Ensure level is between 0-3

    with get_conn() as conn:
        # Insert or update the task level
        conn.execute("INSERT OR REPLACE INTO checkin(d,task,level,user) VALUES(?,?,?,?)", (today, task, level, user))


def toggle_task(task: str, user: str = DEFAULT_USER):
    """Legacy function for backward compatibility - toggles between 0 and 1"""
    today = get_pacific_date().isoformat()
    with get_conn() as conn:
        cur = conn.execute("SELECT level FROM checkin WHERE d=? AND task=? AND user=?", (today, task, user))
        row = cur.fetchone()
        if not row:
            conn.execute("INSERT OR IGNORE INTO checkin(d,task,level,user) VALUES(?,?,0,?)", (today, task, user))
            level = 0
        else:
            level = row[0]
        new_val = 0 if level else 1
        conn.execute("UPDATE checkin SET level=? WHERE d=? AND task=? AND user=?", (new_val, today, task, user))


def get_history(days: int = 30, user: str = DEFAULT_USER):
    cutoff = (get_pacific_date() - timedelta(days=days - 1)).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT d, task, level FROM checkin WHERE d >= ? AND user = ? ORDER BY d DESC, task", (cutoff, user)
        )
        rows = cur.fetchall()
        grouped = {}
        for d, task, level in rows:
            grouped.setdefault(d, {})[task] = level
        return grouped
