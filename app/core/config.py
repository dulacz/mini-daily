from typing import List

# Task configuration - single source of truth for all task information
TASK_LEVELS = {
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
}

# Derived task list from TASK_LEVELS keys
TASKS: List[str] = list(TASK_LEVELS.keys())

# Database configuration
DB_PATH = "data/checkins.db"
