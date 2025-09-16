from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import date
from pydantic import BaseModel
from typing import Dict

from .core.config import TASKS, TASK_LEVELS
from .core import db

app = FastAPI(title="Daily Wellness Tracker")


@app.on_event("startup")
def _startup():
    db.init_db()


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class TaskLevelRequest(BaseModel):
    task: str
    level: int


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    db.ensure_today_rows()
    status = db.get_today_status()
    today = date.today().isoformat()
    return templates.TemplateResponse(
        "index.html", {
            "request": request, 
            "today": today, 
            "tasks": TASKS, 
            "status": status,
            "task_levels": TASK_LEVELS
        }
    )


@app.get("/toggle/{task}")
async def toggle(task: str):
    """Legacy endpoint for backward compatibility"""
    if task not in TASKS:
        return RedirectResponse("/", status_code=302)
    db.toggle_task(task)
    return RedirectResponse("/", status_code=302)


@app.post("/api/task/level")
async def set_task_level(request: TaskLevelRequest):
    """Set task completion level (0-3 stars)"""
    if request.task not in TASKS:
        return JSONResponse(
            status_code=400, 
            content={"error": "Invalid task"}
        )
    
    if not (0 <= request.level <= 3):
        return JSONResponse(
            status_code=400,
            content={"error": "Level must be between 0 and 3"}
        )
    
    try:
        db.set_task_level(request.task, request.level)
        db.ensure_today_rows()
        status = db.get_today_status()
        return {
            "success": True,
            "task": request.task,
            "level": request.level,
            "status": status
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Database error: {str(e)}"}
        )


@app.get("/api/status/today")
async def api_today():
    """Get today's completion status"""
    try:
        db.ensure_today_rows()
        status = db.get_today_status()
        return {
            "date": date.today().isoformat(), 
            "status": status,
            "tasks": TASKS,
            "task_levels": TASK_LEVELS
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Database error: {str(e)}"}
        )


@app.get("/api/history")
async def api_history(days: int = 30):
    """Get completion history"""
    try:
        hist = db.get_history(days=days)
        return {
            "history": hist,
            "tasks": TASKS,
            "days": days
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Database error: {str(e)}"}
        )


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request, days: int = 30):
    hist = db.get_history(days=days)
    ordered_dates = sorted(hist.keys(), reverse=True)
    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "dates": ordered_dates,
            "tasks": TASKS,
            "hist": hist,
            "days": days,
            "task_levels": TASK_LEVELS
        },
    )


# dev run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
