from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import date
from pydantic import BaseModel
from typing import Dict

from .core.config import USER_CONFIGS, get_user_config, get_all_users, get_user_tasks, DEFAULT_USER
from .core import db

app = FastAPI(title="Daily Check-in")


@app.on_event("startup")
def _startup():
    db.init_db()


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class TaskLevelRequest(BaseModel):
    task: str
    level: int


class TaskNoteRequest(BaseModel):
    task: str
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


# New user-specific API endpoints
@app.post("/api/user/{user}/task/level")
async def set_user_task_level(user: str, request: TaskLevelRequest):
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


@app.get("/api/users")
async def api_users():
    """Get list of all users"""
    return {"users": get_all_users(), "user_configs": USER_CONFIGS}


@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def devtools_config():
    """Chrome DevTools configuration endpoint - prevents 404 errors in logs"""
    return {}


# dev run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
