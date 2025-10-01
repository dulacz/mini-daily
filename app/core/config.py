from typing import List, Dict
import yaml
from pathlib import Path

# Configuration file path
TASKS_CONFIG_PATH = Path("data/tasks.yaml")


def load_task_configs() -> Dict:
    """Load task configurations from YAML file"""
    try:
        if TASKS_CONFIG_PATH.exists():
            with open(TASKS_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("tasks", {})
    except Exception as e:
        print(f"Error loading task config: {e}")
        return {}


# Load configurations
TASK_CONFIGS = load_task_configs()
TASKS: List[str] = list(TASK_CONFIGS.keys())


# Helper functions (simplified for single user)
def get_task_config(task: str) -> Dict:
    """Get configuration for a specific task"""
    return TASK_CONFIGS.get(task, {})


def get_all_tasks() -> List[str]:
    """Get list of all configured tasks"""
    return TASKS


def get_task_activities(task: str) -> Dict:
    """Get activities for a specific task"""
    task_config = get_task_config(task)
    return task_config.get("activities", {})


def get_activity_config(task: str, activity: str) -> Dict:
    """Get configuration for a specific activity"""
    activities = get_task_activities(task)
    return activities.get(activity, {})


# Legacy support for backward compatibility with old API
USER_CONFIGS = {"alice": {"name": "User", "color": "#6366f1", "tasks": TASK_CONFIGS}}
DEFAULT_USER = "alice"
TASK_LEVELS = TASK_CONFIGS


# Legacy helper functions
def get_user_config(user: str) -> Dict:
    """Get configuration for a specific user (legacy support)"""
    return {"name": "User", "color": "#6366f1", "tasks": TASK_CONFIGS}


def get_all_users() -> List[str]:
    """Get list of all configured users (legacy support)"""
    return ["alice"]


def get_user_tasks(user: str) -> List[str]:
    """Get task list for a specific user (legacy support)"""
    return TASKS


def get_user_task_activities(user: str, task: str) -> Dict:
    """Get activities for a specific user's task (legacy support)"""
    return get_task_activities(task)


def get_user_activity_levels(user: str, task: str, activity: str) -> Dict:
    """Get levels for a specific user's task activity (legacy support)"""
    activity_config = get_activity_config(task, activity)
    return activity_config.get("levels", {})


def get_default_user() -> str:
    """Get default user (legacy support)"""
    return "alice"


# Database configuration
DB_PATH = "data/checkins.db"
