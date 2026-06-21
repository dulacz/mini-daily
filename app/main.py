from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import date
from pathlib import Path
import re
from pydantic import BaseModel
from typing import Dict, List, Optional

from .core.config import USER_CONFIGS, DEFAULT_USER, TASK_CONFIGS
from .core import db

# ---------------------------------------------------------------------------
# Optional private features — imported only if their source files exist locally.
# This lets the newsfeed modules be excluded from git without breaking
# the rest of the app.
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent.parent

newsfeed_s1 = None
if (_BASE_DIR / "app" / "core" / "newsfeed_s1.py").exists() and (_BASE_DIR / "templates" / "newsfeed_s1.html").exists():
    try:
        from .core import newsfeed_s1 as _newsfeed_s1  # type: ignore

        newsfeed_s1 = _newsfeed_s1
    except Exception as e:
        print(f"Warning: Failed to import newsfeed_s1: {e}")
        newsfeed_s1 = None

newsfeed_hn = None
if (_BASE_DIR / "app" / "core" / "newsfeed_hn.py").exists() and (_BASE_DIR / "templates" / "newsfeed_hn.html").exists():
    try:
        from .core import newsfeed_hn as _newsfeed_hn  # type: ignore

        newsfeed_hn = _newsfeed_hn
    except Exception as e:
        print(f"Warning: Failed to import newsfeed_hn: {e}")
        newsfeed_hn = None

FEATURES = {
    "newsfeed_s1": newsfeed_s1 is not None,
    "newsfeed_hn": newsfeed_hn is not None,
}

app = FastAPI(title="Daily Check-in - Simplified")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.on_event("startup")
def _startup():
    db.init_db()
    db.init_review_cards()
    # Initialize todo_coding from TSV file
    try:
        db.init_todo_coding()
    except Exception as e:
        print(f"Warning: Failed to initialize todo_coding: {e}")
    # Start S1 newsfeed background worker
    if newsfeed_s1 is not None:
        newsfeed_s1.start_background_worker()
    # Start Hacker News newsfeed background worker
    if newsfeed_hn is not None:
        newsfeed_hn.start_background_worker()


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
# Expose feature flags to all templates so nav links can be toggled.
templates.env.globals["features"] = FEATURES


# Simplified request models
class ActivityToggleRequest(BaseModel):
    task: str
    activity: str
    completed: bool
    date: Optional[str] = None  # If provided, record completion for this specific date


class TodoCodingToggleRequest(BaseModel):
    problem_id: int
    completed: bool


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    today = db.get_current_date().isoformat()
    return templates.TemplateResponse(request, "index.html", {"today": today})


# New simplified API endpoints
@app.post("/api/activity/toggle")
async def toggle_activity(request: ActivityToggleRequest):
    """Toggle activity completion status"""
    try:
        db.set_activity_completion(task=request.task, activity=request.activity, completed=request.completed, date_str=request.date)
        return {"success": True, "completed": request.completed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error toggling activity: {str(e)}")


@app.get("/api/day/completions")
async def get_day_completions(date_str: Optional[str] = None):
    """Get all activity completions for a specific date"""
    try:
        completions = db.get_day_completions(date_str)
        last_completions = db.get_last_completion_dates(date_str)
        recent_counts = db.get_activity_recent_counts(TASK_CONFIGS)
        return {
            "date": date_str or db.get_current_date().isoformat(),
            "completions": completions,
            "last_completions": last_completions,
            "recent_counts": recent_counts,
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
    return templates.TemplateResponse(request, "todo_coding.html")


@app.get("/worldcup-flag-quiz", response_class=HTMLResponse)
async def worldcup_flag_quiz_page(request: Request):
    return templates.TemplateResponse(request, "worldcup_flag_quiz.html")


@app.get("/worldcup_flag_quiz")
async def worldcup_flag_quiz_redirect():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/worldcup-flag-quiz")


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


@app.get("/api/todo_coding/today")
async def api_today_questions():
    """Get today's selected questions (2 medium + 1 hard)"""
    try:
        questions = db.get_today_questions()
        return {"questions": questions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting today's questions: {str(e)}")


# ---------------------------------------------------------------------------
# S1 Newsfeed routes (registered only if the module is available)
# ---------------------------------------------------------------------------

if newsfeed_s1 is not None:

    @app.get("/newsfeed_s1", response_class=HTMLResponse)
    async def newsfeed_s1_page(request: Request):
        """S1 外野 daily newsfeed page"""
        return templates.TemplateResponse(request, "newsfeed_s1.html")

    # Keep old URL working as redirect
    @app.get("/newsfeed", response_class=HTMLResponse)
    async def newsfeed_redirect(request: Request):
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/newsfeed_s1")

    @app.get("/api/newsfeed_s1/status")
    async def api_newsfeed_s1_status():
        """Return metadata about the last S1 newsfeed run"""
        return newsfeed_s1.get_status() | {"is_running": newsfeed_s1.is_running()}

    @app.get("/api/newsfeed_s1/latest")
    async def api_newsfeed_s1_latest(date: Optional[str] = None):
        """Return newsfeed data for a specific UTC date, or the most recent day."""
        if date:
            data = newsfeed_s1.get_day_result_filtered(date)
        else:
            data = newsfeed_s1.get_latest_result()
        if data is None:
            return {"ready": False, "posts": []}
        return data | {"ready": True}

    @app.get("/api/newsfeed_s1/dates")
    async def api_newsfeed_s1_dates():
        """Return the list of UTC dates with stored S1 newsfeed refreshes, newest first."""
        return {"dates": newsfeed_s1.get_available_dates()}

    @app.post("/api/newsfeed_s1/run")
    async def api_newsfeed_s1_run():
        """Manually trigger an S1 newsfeed generation job (runs in background thread)"""
        started = newsfeed_s1.trigger_manual_job(days_ago=1)
        if not started:
            return {"started": False, "message": "Job already running"}
        return {"started": True, "message": "Job started in background"}


# ---------------------------------------------------------------------------
# Hacker News Newsfeed routes (registered only if the module is available)
# ---------------------------------------------------------------------------

if newsfeed_hn is not None:

    @app.get("/newsfeed_hn", response_class=HTMLResponse)
    async def newsfeed_hn_page(request: Request):
        """Hacker News daily newsfeed page"""
        return templates.TemplateResponse(request, "newsfeed_hn.html")

    @app.get("/api/newsfeed_hn/status")
    async def api_newsfeed_hn_status():
        """Return metadata about the last HN newsfeed run"""
        return newsfeed_hn.get_status() | {"is_running": newsfeed_hn.is_running()}

    @app.get("/api/newsfeed_hn/latest")
    async def api_newsfeed_hn_latest(date: Optional[str] = None):
        """Return HN newsfeed data for a specific UTC date, or the most recent day."""
        if date:
            data = newsfeed_hn.get_day_result_filtered(date)
        else:
            data = newsfeed_hn.get_latest_result()
        if data is None:
            return {"ready": False, "posts": []}
        return data | {"ready": True}

    @app.get("/api/newsfeed_hn/dates")
    async def api_newsfeed_hn_dates():
        """Return the list of UTC dates with stored HN newsfeed refreshes, newest first."""
        return {"dates": newsfeed_hn.get_available_dates()}

    @app.post("/api/newsfeed_hn/run")
    async def api_newsfeed_hn_run():
        """Manually trigger an HN newsfeed generation job"""
        started = newsfeed_hn.trigger_manual_job()
        if not started:
            return {"started": False, "message": "Job already running"}
        return {"started": True, "message": "Job started in background"}


# ---------------------------------------------------------------------------
# Review Cards (Anki-style spaced repetition)
# ---------------------------------------------------------------------------


class ReviewCardCreateRequest(BaseModel):
    title: str
    category_name: str


class ReviewCardReviewRequest(BaseModel):
    card_id: int
    difficulty: str  # "easy" | "ok" | "hard"


class ReviewCardRenameRequest(BaseModel):
    card_id: int
    title: str


@app.get("/review_cards", response_class=HTMLResponse)
async def review_cards_page(request: Request):
    return templates.TemplateResponse(request, "review_cards.html")


@app.get("/api/review_cards/categories")
async def api_review_categories():
    return {"categories": db.get_review_categories()}


@app.get("/api/review_cards/all")
async def api_review_cards_all():
    return {"cards": db.get_review_cards(), "intervals": db.REVIEW_INTERVALS}


@app.get("/api/review_cards/today")
async def api_review_cards_today():
    return {"cards": db.get_today_review_cards(), "intervals": db.REVIEW_INTERVALS}


@app.post("/api/review_cards/create")
async def api_review_card_create(req: ReviewCardCreateRequest):
    try:
        cat_id = db.create_review_category(req.category_name)
        card = db.create_review_card(req.title, cat_id)
        return {"success": True, "card": card}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/review_cards/review")
async def api_review_card_review(req: ReviewCardReviewRequest):
    try:
        result = db.review_card(req.card_id, req.difficulty)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/review_cards/rename")
async def api_review_card_rename(req: ReviewCardRenameRequest):
    try:
        db.rename_review_card(req.card_id, req.title)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/review_cards/{card_id}")
async def api_review_card_delete(card_id: int):
    try:
        db.delete_review_card(card_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
