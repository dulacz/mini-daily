import sqlite3
from pathlib import Path
from .config import DB_PATH, TASKS
from datetime import date, datetime, timedelta
from typing import Dict

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

DDL = """
CREATE TABLE IF NOT EXISTS checkin(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    d TEXT NOT NULL,
    task TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    UNIQUE(d, task)
)
"""


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        conn.execute(DDL)


def ensure_today_rows():
    today = date.today().isoformat()
    with get_conn() as conn:
        for t in TASKS:
            conn.execute("INSERT OR IGNORE INTO checkin(d,task,done) VALUES(?,?,0)", (today, t))


def get_today_status() -> Dict[str, int]:
    today = date.today().isoformat()
    with get_conn() as conn:
        cur = conn.execute("SELECT task, done FROM checkin WHERE d=?", (today,))
        return {task: done for task, done in cur.fetchall()}


def toggle_task(task: str):
    today = date.today().isoformat()
    with get_conn() as conn:
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
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    with get_conn() as conn:
        cur = conn.execute("SELECT d, task, done FROM checkin WHERE d >= ? ORDER BY d DESC, task", (cutoff,))
        rows = cur.fetchall()
    grouped = {}
    for d, task, done in rows:
        grouped.setdefault(d, {})[task] = done
    return grouped
