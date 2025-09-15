from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import date

from .core.config import TASKS
from .core import db

app = FastAPI(title="Daily Checkin")


@app.on_event("startup")
def _startup():
    db.init_db()


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    db.ensure_today_rows()
    status = db.get_today_status()
    today = date.today().isoformat()
    return templates.TemplateResponse(
        "index.html", {"request": request, "today": today, "tasks": TASKS, "status": status}
    )


@app.get("/toggle/{task}")
async def toggle(task: str):
    if task not in TASKS:
        return RedirectResponse("/", status_code=302)
    db.toggle_task(task)
    return RedirectResponse("/", status_code=302)


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
        },
    )


@app.get("/api/status/today")
async def api_today():
    db.ensure_today_rows()
    return {"date": date.today().isoformat(), "status": db.get_today_status()}


# dev run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
