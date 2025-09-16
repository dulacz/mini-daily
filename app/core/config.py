from typing import List

# 每日固定任务列表；修改后重启服务即可生效
TASKS: List[str] = ["reading", "exercise", "caring"]  # 阅读, 锻炼, 自我关怀

# Task star level definitions
TASK_LEVELS = {
    "reading": {
        1: "1 page read",
        2: "5 minutes reading", 
        3: "15 minutes reading"
    },
    "exercise": {
        1: "10 minutes movement",
        2: "20 minutes workout",
        3: "45 minutes exercise"
    },
    "caring": {
        1: "5 minutes meditation",
        2: "15 minutes self-care",
        3: "30 minutes wellness"
    }
}

DB_PATH = "data/checkins.db"
