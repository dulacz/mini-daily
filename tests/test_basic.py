from fastapi.testclient import TestClient
from app.main import app
from app.core.config import TASKS


def test_toggle_flow():
    # Use context manager to ensure startup/shutdown events fire
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        task = TASKS[0]
        client.get(f"/toggle/{task}")
        r3 = client.get("/").text
        assert ("已完成" in r3) or ("撤销" in r3)
