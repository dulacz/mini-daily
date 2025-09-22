from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import date
from pydantic import BaseModel
from typing import Dict

from .core.config import (
    USER_CONFIGS,
    get_user_config,
    get_all_users,
    get_user_tasks,
    get_user_task_activities,
    get_user_activity_levels,
    DEFAULT_USER,
)
from .core import db

app = FastAPI(title="Daily Check-in")


@app.on_event("startup")
def _startup():
    db.init_db()
    # Initialize todo questions from TSV file
    try:
        db.init_todo_questions()
    except Exception as e:
        print(f"Warning: Failed to initialize todo questions: {e}")
        # Continue startup even if todo initialization fails


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class TaskLevelRequest(BaseModel):
    task: str
    level: int


class TaskActivityLevelRequest(BaseModel):
    task: str
    activity: str
    level: int


class TaskNoteRequest(BaseModel):
    task: str
    note: str


class TaskActivityNoteRequest(BaseModel):
    task: str
    activity: str
    note: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Initialize all users for today
    for user in get_all_users():
        db.ensure_today_rows(user)

    today = date.today().isoformat()
    return templates.TemplateResponse(
        "index.html", {"request": request, "today": today, "user_configs": USER_CONFIGS, "default_user": DEFAULT_USER}
    )


# Legacy endpoint for backward compatibility
@app.get("/toggle/{task}")
async def toggle(task: str):
    """Legacy endpoint for backward compatibility"""
    user_tasks = get_user_tasks(DEFAULT_USER)
    if task not in user_tasks:
        return RedirectResponse("/", status_code=302)
    db.toggle_task(task, DEFAULT_USER)
    return RedirectResponse("/", status_code=302)


# New user-specific API endpoints for hierarchical structure
@app.post("/api/user/{user}/task/activity/level")
async def set_user_task_activity_level(user: str, request: TaskActivityLevelRequest):
    """Set task-activity completion level (0-3 stars) for a specific user"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    user_tasks = get_user_tasks(user)
    if request.task not in user_tasks:
        raise HTTPException(status_code=400, detail="Invalid task for this user")

    user_activities = get_user_task_activities(user, request.task)
    if request.activity not in user_activities:
        raise HTTPException(status_code=400, detail="Invalid activity for this task")

    if not (0 <= request.level <= 3):
        raise HTTPException(status_code=400, detail="Level must be between 0 and 3")

    try:
        db.set_task_activity_level(request.task, request.activity, request.level, user)
        db.ensure_today_rows(user)
        status = db.get_today_status(user)
        return {
            "success": True,
            "user": user,
            "task": request.task,
            "activity": request.activity,
            "level": request.level,
            "status": status,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/user/{user}/task/{task}/activities")
async def api_get_user_task_activities(user: str, task: str):
    """Get available activities for a user's task"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    user_tasks = get_user_tasks(user)
    if task not in user_tasks:
        raise HTTPException(status_code=400, detail="Invalid task for this user")

    try:
        activities = get_user_task_activities(user, task)
        return {"user": user, "task": task, "activities": activities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving activities: {str(e)}")


@app.get("/api/user/{user}/task/{task}/activity/{activity}/status")
async def get_user_task_activity_status(user: str, task: str, activity: str):
    """Get current status for a specific task-activity for a user"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    user_tasks = get_user_tasks(user)
    if task not in user_tasks:
        raise HTTPException(status_code=400, detail="Invalid task for this user")

    user_activities = get_user_task_activities(user, task)
    if activity not in user_activities:
        raise HTTPException(status_code=400, detail="Invalid activity for this task")

    try:
        level = db.get_task_activity_level(task, activity, user)
        note = db.get_task_activity_note(task, activity, user)
        return {"user": user, "task": task, "activity": activity, "level": level, "note": note}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving status: {str(e)}")


@app.get("/api/user/{user}/task/{task}/activity/{activity}/levels")
async def api_get_user_activity_levels(user: str, task: str, activity: str):
    """Get available levels for a user's task activity"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    user_tasks = get_user_tasks(user)
    if task not in user_tasks:
        raise HTTPException(status_code=400, detail="Invalid task for this user")

    user_activities = get_user_task_activities(user, task)
    if activity not in user_activities:
        raise HTTPException(status_code=400, detail="Invalid activity for this task")

    try:
        levels = get_user_activity_levels(user, task, activity)
        return {"user": user, "task": task, "activity": activity, "levels": levels}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving levels: {str(e)}")


# Legacy endpoints (updated to handle backward compatibility)
@app.post("/api/user/{user}/task/level")
async def set_user_task_level(user: str, request: TaskLevelRequest):
    """Set task completion level (0-3 stars) for a specific user - Legacy endpoint"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    user_tasks = get_user_tasks(user)
    if request.task not in user_tasks:
        raise HTTPException(status_code=400, detail="Invalid task for this user")

    if not (0 <= request.level <= 3):
        raise HTTPException(status_code=400, detail="Level must be between 0 and 3")

    try:
        # For legacy support, use the first activity as default
        user_activities = get_user_task_activities(user, request.task)
        if user_activities:
            first_activity = list(user_activities.keys())[0]
            db.set_task_activity_level(request.task, first_activity, request.level, user)
        else:
            # Fallback to old method if no activities defined
            db.set_task_level(request.task, request.level, user)

        db.ensure_today_rows(user)
        status = db.get_today_status(user)
        return {"success": True, "user": user, "task": request.task, "level": request.level, "status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# Original user-specific API endpoints
@app.post("/api/user/{user}/task/level/original")
async def set_user_task_level_original(user: str, request: TaskLevelRequest):
    """Set task completion level (0-3 stars) for a specific user"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    user_tasks = get_user_tasks(user)
    if request.task not in user_tasks:
        raise HTTPException(status_code=400, detail="Invalid task for this user")

    if not (0 <= request.level <= 3):
        raise HTTPException(status_code=400, detail="Level must be between 0 and 3")

    try:
        db.set_task_level(request.task, request.level, user)
        db.ensure_today_rows(user)
        status = db.get_today_status(user)
        return {"success": True, "user": user, "task": request.task, "level": request.level, "status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/user/{user}/status/today")
async def api_user_today(user: str):
    """Get today's completion status for a specific user"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        db.ensure_today_rows(user)
        status = db.get_today_status(user)
        user_config = get_user_config(user)
        return {"date": date.today().isoformat(), "status": status, "user_config": user_config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/user/{user}/history")
async def api_user_history(user: str, days: int = 30):
    """Get completion history for a specific user"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        hist = db.get_history(days=days, user=user)
        user_config = get_user_config(user)
        return {"history": hist, "user_config": user_config, "days": days}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.post("/api/user/{user}/task/note")
async def set_user_task_note(user: str, request: TaskNoteRequest):
    """Set note for a task for a specific user"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    user_tasks = get_user_tasks(user)
    if request.task not in user_tasks:
        raise HTTPException(status_code=400, detail="Invalid task for this user")

    try:
        db.set_task_note(request.task, request.note, user)
        return {"success": True, "user": user, "task": request.task, "note": request.note}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/user/{user}/task/{task}/note")
async def get_user_task_note(user: str, task: str):
    """Get note for a task for a specific user"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    user_tasks = get_user_tasks(user)
    if task not in user_tasks:
        raise HTTPException(status_code=400, detail="Invalid task for this user")

    try:
        note = db.get_task_note(task, user)
        return {"user": user, "task": task, "note": note}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# Activity-based note endpoints
@app.post("/api/user/{user}/task/activity/note")
async def set_user_task_activity_note(user: str, request: TaskActivityNoteRequest):
    """Set note for a specific task-activity for a user"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    user_tasks = get_user_tasks(user)
    if request.task not in user_tasks:
        raise HTTPException(status_code=400, detail="Invalid task for this user")

    user_activities = get_user_task_activities(user, request.task)
    if request.activity not in user_activities:
        raise HTTPException(status_code=400, detail="Invalid activity for this task")

    try:
        db.set_task_activity_note(request.task, request.activity, request.note, user)
        return {"success": True, "user": user, "task": request.task, "activity": request.activity, "note": request.note}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/user/{user}/task/{task}/activity/{activity}/note")
async def get_user_task_activity_note(user: str, task: str, activity: str):
    """Get note for a specific task-activity for a user"""
    if user not in USER_CONFIGS:
        raise HTTPException(status_code=404, detail="User not found")

    user_tasks = get_user_tasks(user)
    if task not in user_tasks:
        raise HTTPException(status_code=400, detail="Invalid task for this user")

    user_activities = get_user_task_activities(user, task)
    if activity not in user_activities:
        raise HTTPException(status_code=400, detail="Invalid activity for this task")

    try:
        note = db.get_task_activity_note(task, activity, user)
        return {"user": user, "task": task, "activity": activity, "note": note}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# Legacy API endpoints for backward compatibility
@app.post("/api/task/level")
async def set_task_level(request: TaskLevelRequest):
    """Legacy endpoint - uses default user"""
    return await set_user_task_level(DEFAULT_USER, request)


@app.get("/api/status/today")
async def api_today():
    """Legacy endpoint - uses default user"""
    return await api_user_today(DEFAULT_USER)


@app.get("/api/history")
async def api_history(days: int = 30):
    """Legacy endpoint - uses default user"""
    return await api_user_history(DEFAULT_USER, days)


# Configuration endpoints
@app.get("/api/config")
async def api_config():
    """Get application configuration"""
    return {"user_configs": USER_CONFIGS, "users": get_all_users(), "default_user": DEFAULT_USER}


# Todo-related endpoints and models
class TodoToggleRequest(BaseModel):
    question_id: str
    completed: bool


@app.get("/todo", response_class=HTMLResponse)
async def todo_page(request: Request):
    """Render the todo.html page"""
    return templates.TemplateResponse("todo.html", {"request": request})


@app.get("/api/todo/questions")
async def get_todo_questions():
    """Get all todo questions"""
    try:
        # Initialize questions if empty
        questions = db.get_todo_questions()
        if not questions:
            db.init_todo_questions()
            questions = db.get_todo_questions()
        return questions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load questions: {str(e)}")


@app.get("/api/todo/completed")
async def get_completed_questions(user: str = DEFAULT_USER):
    """Get all completed questions for a user"""
    try:
        return db.get_completed_questions(user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load completed questions: {str(e)}")


@app.post("/api/todo/toggle")
async def toggle_question_completion(request: TodoToggleRequest, user: str = DEFAULT_USER):
    """Toggle question completion status"""
    try:
        success = db.toggle_question_completion(request.question_id, request.completed, user)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle question: {str(e)}")


@app.get("/api/todo/stats")
async def get_todo_stats(user: str = DEFAULT_USER):
    """Get todo completion statistics"""
    try:
        return db.get_todo_stats(user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@app.get("/api/users")
async def api_users():
    """Get list of all users"""
    return {"users": get_all_users(), "user_configs": USER_CONFIGS}


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def devtools_config():
    """Chrome DevTools configuration endpoint - prevents 404 errors in logs"""
    return {}


# dev run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
