from typing import List, Dict
import yaml
from pathlib import Path

# Configuration file path
USERS_CONFIG_PATH = Path("data/users.yaml")


def load_user_configs() -> Dict:
    """Load user configurations from YAML file"""
    try:
        if USERS_CONFIG_PATH.exists():
            with open(USERS_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("users", {})
    except Exception as e:
        print(f"Error loading user config: {e}")

    # Fallback configuration if file doesn't exist or fails to load
    return {
        "alice": {
            "name": "Alice",
            "color": "#6366f1",
            "tasks": {
                "reading": {
                    "title": "Reading",
                    "icon": "📚",
                    "description": "Feed your mind with knowledge!",
                    "levels": {1: "1 page read", 2: "5 minutes reading", 3: "15 minutes reading"},
                },
                "exercise": {
                    "title": "Exercise",
                    "icon": "💪",
                    "description": "Strengthen your body and mind!",
                    "levels": {1: "10 minutes movement", 2: "20 minutes workout", 3: "45 minutes exercise"},
                },
                "caring": {
                    "title": "Self-Care",
                    "icon": "❤️",
                    "description": "Nurture your wellbeing!",
                    "levels": {1: "5 minutes meditation", 2: "15 minutes self-care", 3: "30 minutes wellness"},
                },
            },
        }
    }


def get_default_user() -> str:
    """Get default user from YAML config"""
    try:
        if USERS_CONFIG_PATH.exists():
            with open(USERS_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("default_user", "alice")
    except Exception as e:
        print(f"Error loading default user: {e}")
    return "alice"


# Load configurations
USER_CONFIGS = load_user_configs()
DEFAULT_USER = get_default_user()

# Legacy support - default to first user for backward compatibility
TASK_LEVELS = USER_CONFIGS[DEFAULT_USER]["tasks"]
TASKS: List[str] = list(TASK_LEVELS.keys())


# Helper functions
def get_user_config(user: str) -> Dict:
    """Get configuration for a specific user"""
    return USER_CONFIGS.get(user, USER_CONFIGS[DEFAULT_USER])


def get_all_users() -> List[str]:
    """Get list of all configured users"""
    return list(USER_CONFIGS.keys())


def get_user_tasks(user: str) -> List[str]:
    """Get task list for a specific user"""
    return list(get_user_config(user)["tasks"].keys())


def get_user_task_activities(user: str, task: str) -> Dict:
    """Get activities for a specific user's task"""
    user_config = get_user_config(user)
    task_config = user_config["tasks"].get(task, {})
    return task_config.get("activities", {})


def get_user_activity_levels(user: str, task: str, activity: str) -> Dict:
    """Get levels for a specific user's task activity"""
    activities = get_user_task_activities(user, task)
    activity_config = activities.get(activity, {})
    return activity_config.get("levels", {})


# Database configuration
DB_PATH = "data/checkins.db"
