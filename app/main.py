from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import date
from pydantic import BaseModel
from typing import Dict, Optional

from .core.config import USER_CONFIGS, DEFAULT_USER
from .core import db

app = FastAPI(title="Daily Check-in - Simplified")


@app.on_event("startup")
def _startup():
    db.init_db()
    # Initialize todo_coding from TSV file
    try:
        db.init_todo_coding()
    except Exception as e:
        print(f"Warning: Failed to initialize todo_coding: {e}")


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# Simplified request models
class ActivityToggleRequest(BaseModel):
    task: str
    activity: str
    completed: bool


class TodoCodingToggleRequest(BaseModel):
    problem_id: int
    completed: bool


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    today = db.get_current_date().isoformat()
    return templates.TemplateResponse("index.html", {"request": request, "today": today})


# New simplified API endpoints
@app.post("/api/activity/toggle")
async def toggle_activity(request: ActivityToggleRequest):
    """Toggle activity completion status"""
    try:
        db.set_activity_completion(task=request.task, activity=request.activity, completed=request.completed)
        return {"success": True, "completed": request.completed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error toggling activity: {str(e)}")


@app.get("/api/day/completions")
async def get_day_completions(date_str: Optional[str] = None):
    """Get all activity completions for a specific date"""
    try:
        completions = db.get_day_completions(date_str)
        last_completions = db.get_last_completion_dates(date_str)
        return {
            "date": date_str or db.get_current_date().isoformat(),
            "completions": completions,
            "last_completions": last_completions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting day completions: {str(e)}")


@app.get("/api/history")
async def get_history(days: int = 30):
    """Get completion history for the last N days"""
    try:
        history = db.get_history(days)
        return {"history": history, "days": days}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting history: {str(e)}")


@app.get("/api/stats")
async def get_stats():
    """Get current statistics"""
    try:
        streak = db.get_streak()
        total_stars_365 = db.get_total_completions(365)

        # Get today's completions
        today_completions = db.get_day_completions()
        today_total = sum(sum(activities.values()) for activities in today_completions.values())

        return {"streak": streak, "total_stars_365": total_stars_365, "today_total": today_total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")


@app.get("/api/config")
async def api_config():
    """Get application configuration"""
    return {"user_configs": USER_CONFIGS, "default_user": DEFAULT_USER}


# Todo_coding endpoints
@app.get("/todo_coding", response_class=HTMLResponse)
async def todo_coding_page(request: Request):
    return templates.TemplateResponse("todo_coding.html", {"request": request})


@app.get("/api/todo_coding/items")
async def api_todo_coding_items():
    """Get all todo_coding items with completion status"""
    try:
        items = db.get_todo_coding_items()
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting todo_coding items: {str(e)}")


@app.post("/api/todo_coding/toggle")
async def api_todo_coding_toggle(request: TodoCodingToggleRequest):
    """Toggle todo_coding completion status"""
    try:
        new_status = db.toggle_todo_coding_completion(request.problem_id)
        return {"problem_id": request.problem_id, "completed": new_status, "success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error toggling todo_coding: {str(e)}")
