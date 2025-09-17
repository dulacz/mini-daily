from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_user_tasks, DEFAULT_USER


def test_toggle_flow():
    """Test the legacy toggle endpoint functionality"""
    # Use context manager to ensure startup/shutdown events fire
    with TestClient(app) as client:
        # Test home page loads
        r = client.get("/")
        assert r.status_code == 200
        
        # Get first task for the default user
        user_tasks = get_user_tasks(DEFAULT_USER)
        assert len(user_tasks) > 0, "No tasks configured for default user"
        
        task = user_tasks[0]
        
        # Test toggle endpoint (legacy) - TestClient follows redirects by default
        toggle_response = client.get(f"/toggle/{task}")
        assert toggle_response.status_code in [200, 302]  # Either redirect or followed redirect
        
        # Test that the app still loads after toggle
        r3 = client.get("/")
        assert r3.status_code == 200
        assert "daily" in r3.text.lower()


def test_api_endpoints():
    """Test the modern API endpoints"""
    with TestClient(app) as client:
        # Test config endpoint
        config_response = client.get("/api/config")
        assert config_response.status_code == 200
        config_data = config_response.json()
        assert "users" in config_data
        assert "user_configs" in config_data
        
        # Test user history endpoint
        history_response = client.get(f"/api/user/{DEFAULT_USER}/history?days=7")
        assert history_response.status_code == 200
        
        # Test setting a task activity level with real task and activity data
        user_tasks = get_user_tasks(DEFAULT_USER)
        if user_tasks:
            task = user_tasks[0]
            from app.core.config import get_user_task_activities
            activities = get_user_task_activities(DEFAULT_USER, task)
            if activities:
                activity_id = list(activities.keys())[0]
                level_data = {
                    "task": task,
                    "activity": activity_id,
                    "level": 1
                }
                level_response = client.post(f"/api/user/{DEFAULT_USER}/task/activity/level", json=level_data)
                assert level_response.status_code == 200
                
                # Verify the response contains expected data
                response_data = level_response.json()
                assert response_data["success"] is True
                assert response_data["level"] == 1
