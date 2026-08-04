import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.core.config import DEFAULT_USER, get_user_task_activities, get_user_tasks
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient backed by a temp database so tests never touch the real check-in data."""
    db_path = str(tmp_path / "checkin.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "get_conn", lambda: sqlite3.connect(db_path))
    with TestClient(app) as test_client:
        yield test_client


def test_index_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "daily" in response.text.lower()


def test_activity_toggle_flow(client):
    tasks = get_user_tasks(DEFAULT_USER)
    assert tasks, "No tasks configured for default user"
    task = tasks[0]
    activities = get_user_task_activities(DEFAULT_USER, task)
    assert activities, f"No activities configured for task {task}"
    activity = next(iter(activities))

    toggle = client.post(
        "/api/activity/toggle",
        json={"task": task, "activity": activity, "completed": True, "date": "2024-01-02"},
    )
    assert toggle.status_code == 200
    assert toggle.json() == {"success": True, "completed": True}

    completions = client.get("/api/day/completions", params={"date_str": "2024-01-02"})
    assert completions.status_code == 200
    assert completions.json()["completions"][task][activity] is True

    untoggle = client.post(
        "/api/activity/toggle",
        json={"task": task, "activity": activity, "completed": False, "date": "2024-01-02"},
    )
    assert untoggle.status_code == 200
    day = client.get("/api/day/completions", params={"date_str": "2024-01-02"}).json()
    assert day["completions"][task][activity] is False

    assert client.get("/").status_code == 200


def test_api_endpoints(client):
    config = client.get("/api/config")
    assert config.status_code == 200
    config_data = config.json()
    assert config_data["default_user"] == DEFAULT_USER
    assert DEFAULT_USER in config_data["user_configs"]

    history = client.get("/api/history", params={"days": 7})
    assert history.status_code == 200
    assert history.json()["days"] == 7

    stats = client.get("/api/stats")
    assert stats.status_code == 200
    assert set(stats.json()) == {"streak", "total_stars_365", "today_total"}
