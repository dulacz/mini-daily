from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import date
from pathlib import Path
import re
from pydantic import BaseModel, Field
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

from .core import paper, sina_quotes, stocks

FEATURES = {
    "newsfeed_s1": newsfeed_s1 is not None,
    "newsfeed_hn": newsfeed_hn is not None,
    "stocks": True,
    "paper": True,
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
    try:
        db.init_stocks()
        db.init_paper()
        stocks.start_background_worker()
    except Exception as e:
        print(f"Warning: Failed to initialize stocks: {e}")
    # Start S1 newsfeed background worker
    if newsfeed_s1 is not None:
        newsfeed_s1.start_background_worker()
    # Start Hacker News newsfeed background worker
    if newsfeed_hn is not None:
        newsfeed_hn.start_background_worker()


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def _static_url(path: str) -> str:
    """Static URL stamped with the file's mtime so browsers never serve a stale asset."""
    file = _BASE_DIR / "static" / path
    version = int(file.stat().st_mtime) if file.exists() else 0
    return f"/static/{path}?v={version}"


templates.env.globals["static_url"] = _static_url
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


# ---------------------------------------------------------------------------
# A-share price monitor
# ---------------------------------------------------------------------------

# Accepts a bare 6-digit A-share code; an sh/sz/bj prefix is only needed for indices.
SYMBOL_PATTERN = r"^((sh|sz|bj)\d{6}|\d{6})$"


class StockAddRequest(BaseModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    name: str = ""


class StockUpdateRequest(BaseModel):
    id: int
    name: Optional[str] = None
    enabled: Optional[bool] = None


class AlertSettingsRequest(BaseModel):
    rsi_high: Optional[float] = Field(default=None, ge=0, le=100)
    rsi_low: Optional[float] = Field(default=None, ge=0, le=100)
    pct_high: Optional[float] = Field(default=None, ge=0, le=100)
    pct_low: Optional[float] = Field(default=None, ge=0, le=100)


@app.get("/stocks", response_class=HTMLResponse)
async def stocks_page(request: Request):
    return templates.TemplateResponse(request, "stocks.html")


@app.get("/api/stocks/list")
async def api_stocks_list():
    return {"stocks": stocks.get_watchlist(), "settings": db.get_alert_settings()}


@app.post("/api/stocks/settings")
async def api_stocks_settings(req: AlertSettingsRequest):
    try:
        db.set_alert_settings(**req.model_dump())
        return {"success": True, "settings": db.get_alert_settings()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/stocks/status")
async def api_stocks_status():
    return stocks.get_status()


@app.get("/api/stocks/alerts")
async def api_stocks_alerts(limit: int = 50):
    return {"alerts": db.list_alerts(limit)}


@app.get("/api/stocks/kline")
async def api_stocks_kline(symbol: str, days: int = stocks.CHART_DAYS):
    try:
        symbol = sina_quotes.normalize_symbol(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"symbol": symbol, "bars": stocks.get_kline(symbol, days)}


@app.post("/api/stocks/run")
async def api_stocks_run():
    if not stocks.trigger_manual_job():
        return {"started": False, "message": "Job already running"}
    return {"started": True, "message": "Job started in background"}


@app.post("/api/stocks/add")
async def api_stocks_add(req: StockAddRequest):
    try:
        symbol = sina_quotes.normalize_symbol(req.symbol)
        name = req.name.strip() or stocks.resolve_name(symbol)
        if not name:
            raise HTTPException(status_code=400, detail=f"无法获取 {req.symbol} 的名称，请检查代码或手动填写")
        stock = db.add_stock(symbol, name)
        return {"success": True, "stock": stock}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/stocks/update")
async def api_stocks_update(req: StockUpdateRequest):
    try:
        return {"success": True, "stock": db.update_stock(req.id, req.name, req.enabled)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/stocks/{stock_id}")
async def api_stocks_delete(stock_id: int):
    db.delete_stock(stock_id)
    return {"success": True}


# ---------------------------------------------------------------------------
# Paper trading
# ---------------------------------------------------------------------------


class PaperTradeRequest(BaseModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    side: str = Field(pattern=r"^(buy|sell)$")
    shares: int = Field(gt=0)


class PaperCashRequest(BaseModel):
    cash: float = Field(ge=0)


class PaperSettingsRequest(BaseModel):
    drift_tolerance_pct: float = Field(gt=0, le=1000)
    min_trade_amount: Optional[float] = Field(default=None, ge=0)


class PaperTargetRequest(BaseModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    target_weight: Optional[float] = Field(default=None, ge=0, le=100)


class PaperCostRequest(BaseModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    avg_cost: float = Field(ge=0)


class PaperSharesRequest(BaseModel):
    symbol: str = Field(pattern=SYMBOL_PATTERN)
    shares: int = Field(ge=0)


@app.get("/paper", response_class=HTMLResponse)
async def paper_page(request: Request):
    return templates.TemplateResponse(request, "paper.html")


@app.get("/api/paper/portfolio")
async def api_paper_portfolio():
    return paper.build_portfolio()


@app.get("/api/paper/alerts")
async def api_paper_alerts(limit: int = 50):
    return {"alerts": db.list_paper_alerts(limit)}


@app.get("/api/paper/rebalance")
async def api_paper_rebalance():
    return paper.plan_rebalance()


@app.post("/api/paper/rebalance/execute")
async def api_paper_rebalance_execute():
    try:
        return {"success": True, **paper.execute_rebalance()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/paper/cash")
async def api_paper_cash(req: PaperCashRequest):
    try:
        db.set_paper_cash(req.cash)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/paper/settings")
async def api_paper_settings(req: PaperSettingsRequest):
    try:
        db.set_paper_settings(req.drift_tolerance_pct, req.min_trade_amount)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/paper/trade")
async def api_paper_trade(req: PaperTradeRequest):
    try:
        return {"success": True, "trade": paper.trade(req.symbol, req.side, req.shares)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/paper/target")
async def api_paper_target(req: PaperTargetRequest):
    try:
        paper.set_target(req.symbol, req.target_weight)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/paper/cost")
async def api_paper_cost(req: PaperCostRequest):
    try:
        db.set_paper_cost(req.symbol, req.avg_cost)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/paper/shares")
async def api_paper_shares(req: PaperSharesRequest):
    """Set an absolute share count, trading the difference at the live price."""
    try:
        return {"success": True, "trade": paper.set_shares(req.symbol, req.shares)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/paper/position/{symbol}")
async def api_paper_position_delete(symbol: str):
    try:
        db.delete_paper_position(sina_quotes.normalize_symbol(symbol))
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
