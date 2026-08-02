# -*- coding: UTF-8 -*-
"""
A-share price monitor — fetches Sina quotes twice per trading day and raises a
Windows toast when a watched stock crosses its configured price lines.

Quotes are kept in a single overwritten snapshot file rather than the database;
only the watchlist and triggered alerts are persisted (see app/core/db.py).
"""

import json
import threading
import time
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from typing import Optional

import pytz

from . import db, kline, notify, paper, sina_quotes

SNAPSHOT_PATH = Path("data/stocks_snapshot.json")
BEIJING_TZ = pytz.timezone("Asia/Shanghai")
# Beijing-time slots: a pre-close warning and a post-close final reading.
RUN_SLOTS: list[tuple[str, dtime]] = [("1430", dtime(14, 30)), ("1505", dtime(15, 5))]
POLL_INTERVAL_SEC = 120
# Tencent serves at most 800 adjusted bars, which bounds the chart and MA warm-up.
KLINE_HISTORY_DAYS = kline.MAX_QFQ_BARS
RSI_PERIOD = 12
MA_PERIOD = 250
# Kept below KLINE_HISTORY_DAYS - MA_PERIOD so the MA line spans the whole chart.
CHART_DAYS = 550
PERCENTILE_WINDOW = 250
MIN_PERCENTILE_BARS = 60

_job_lock = threading.Lock()
_is_running = False


# ---------------------------------------------------------------------------
# Snapshot (latest quotes only — overwritten on every run)
# ---------------------------------------------------------------------------


def _beijing_now() -> datetime:
    return datetime.now(BEIJING_TZ)


def load_snapshot() -> dict:
    try:
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_snapshot(snapshot: dict):
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def _runs_done_today(snapshot: dict, beijing_date: str) -> list[str]:
    if snapshot.get("beijing_date") != beijing_date:
        return []
    return list(snapshot.get("runs_done", []))


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------


def compute_rsi(closes: list[float], period: int = RSI_PERIOD) -> Optional[float]:
    """Wilder-smoothed RSI over closes ordered oldest first."""
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    avg_gain = sum(d for d in deltas[:period] if d > 0) / period
    avg_loss = sum(-d for d in deltas[:period] if d < 0) / period

    for delta in deltas[period:]:
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def compute_percentile(closes: list[float], price: float) -> Optional[float]:
    """Where price sits within closes, 0-100. Midrank so repeated closes don't skew it."""
    if price <= 0 or len(closes) < MIN_PERCENTILE_BARS:
        return None
    below = sum(1 for c in closes if c < price)
    equal = sum(1 for c in closes if c == price)
    return (below + equal / 2) / len(closes) * 100


def moving_average(closes: list[float], period: int) -> list[Optional[float]]:
    """Simple moving average aligned with closes; None until the window is full."""
    out: list[Optional[float]] = []
    running = 0.0
    for i, close in enumerate(closes):
        running += close
        if i >= period:
            running -= closes[i - period]
        out.append(running / period if i >= period - 1 else None)
    return out


def _refresh_metrics(symbol: str, price: float) -> dict:
    """Refresh the stored daily bars and return the derived indicators."""
    bars, adjusted = kline.fetch_daily_bars(symbol, KLINE_HISTORY_DAYS)
    if bars:
        # Forward adjustment rescales the whole history on every dividend, so the
        # series has to be replaced wholesale rather than merged with older values.
        db.replace_daily_bars(symbol, bars)
    closes = [b["close"] for b in db.get_daily_bars(symbol, limit=KLINE_HISTORY_DAYS) if b["close"]]

    return {
        "rsi": compute_rsi(closes),
        "pct_1y": compute_percentile(closes[-PERCENTILE_WINDOW:], price),
        "adjusted": adjusted if bars else None,
    }


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


def _evaluate(metrics: dict, settings: dict) -> list[dict]:
    """Return every band breach for one stock. Alerts use the 1-year percentile."""
    rsi = metrics.get("rsi")
    pct = metrics.get("pct_1y")
    breaches = []
    checks = [
        ("rsi_high", settings.get("rsi_high"), rsi),
        ("rsi_low", settings.get("rsi_low"), rsi),
        ("pct_high", settings.get("pct_high"), pct),
        ("pct_low", settings.get("pct_low"), pct),
    ]
    for direction, threshold, value in checks:
        if threshold is None or value is None:
            continue
        above = direction.endswith("_high")
        if (value >= threshold) if above else (value <= threshold):
            breaches.append({"direction": direction, "threshold": threshold, "value": value})
    return breaches


def run_job(slot: str = "manual") -> dict:
    """Fetch quotes and daily bars, refresh the snapshot, and toast newly breached thresholds."""
    stocks = db.list_stocks(enabled_only=True)
    beijing_now = _beijing_now()
    beijing_date = beijing_now.date().isoformat()

    print(f"[Stocks] Running slot={slot} at {beijing_now.isoformat(timespec='seconds')} ({len(stocks)} symbols)")

    quotes: dict[str, dict] = {}
    # Paper holdings are priced in the same batch so drift can be checked without a second fetch.
    symbols = list(dict.fromkeys([s["symbol"] for s in stocks] + paper.held_symbols()))
    if symbols:
        try:
            quotes = sina_quotes.fetch_quotes(symbols)
        except Exception as e:
            print(f"[Stocks] Quote fetch failed: {e}")

    valid = {sym: q for sym, q in quotes.items() if q.get("valid")}
    # Sina reports the last trading day, so a stale date means today is not a trading day.
    trade_date = next((q["date"] for q in valid.values() if q.get("date")), "")
    is_trading_day = trade_date == beijing_date

    metrics_by_symbol: dict[str, dict] = {}
    for stock in stocks:
        symbol = stock["symbol"]
        try:
            metrics_by_symbol[symbol] = _refresh_metrics(symbol, (valid.get(symbol) or {}).get("price", 0.0))
        except Exception as e:
            print(f"[Stocks] Daily bar refresh failed for {symbol}: {e}")
            metrics_by_symbol[symbol] = {}

    snapshot = load_snapshot()
    runs_done = _runs_done_today(snapshot, beijing_date)
    if valid and slot != "manual":
        # Mark this slot and every earlier one so a late start does not run twice.
        slot_names = [name for name, _ in RUN_SLOTS]
        for name in slot_names[: slot_names.index(slot) + 1]:
            if name not in runs_done:
                runs_done.append(name)

    _save_snapshot(
        {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "beijing_date": beijing_date,
            "trade_date": trade_date,
            "is_trading_day": is_trading_day,
            "runs_done": runs_done,
            "quotes": quotes,
            "metrics": metrics_by_symbol,
        }
    )

    if not is_trading_day:
        print(f"[Stocks] Quote date {trade_date or '(unknown)'} != {beijing_date} — not a trading day, no alerts.")
        return {"trade_date": trade_date, "alerts": [], "drift_alerts": []}

    new_alerts = []
    settings = db.get_alert_settings()
    for stock in stocks:
        quote = valid.get(stock["symbol"])
        if not quote:
            continue
        for breach in _evaluate(metrics_by_symbol.get(stock["symbol"], {}), settings):
            if db.record_alert(
                symbol=stock["symbol"],
                name=stock["name"],
                trade_date=trade_date,
                direction=breach["direction"],
                price=breach["value"],
                threshold=breach["threshold"],
            ):
                new_alerts.append({**breach, "name": stock["name"], "symbol": stock["symbol"]})

    try:
        drift_alerts = paper.check_drift(trade_date, quotes)
    except Exception as e:
        print(f"[Stocks] Drift check failed: {e}")
        drift_alerts = []

    lines = [_alert_line(a) for a in new_alerts] + [paper.alert_line(a) for a in drift_alerts]
    if lines:
        notify.send_toast(f"股价提醒 · {trade_date}", lines)
        print(f"[Stocks] {len(lines)} new alert(s): {'; '.join(lines)}")
    else:
        print("[Stocks] No new alerts.")

    return {"trade_date": trade_date, "alerts": new_alerts, "drift_alerts": drift_alerts}


_ALERT_LABELS = {"rsi_high": "RSI ", "rsi_low": "RSI ", "pct_high": "分位 ", "pct_low": "分位 "}


def _alert_line(alert: dict) -> str:
    direction = alert["direction"]
    op = "≥" if direction.endswith("_high") else "≤"
    return f"{alert['name']} {_ALERT_LABELS.get(direction, '')}{alert['value']:.1f} {op} {alert['threshold']:.0f}"


# ---------------------------------------------------------------------------
# K-line (served from the stored daily bars)
# ---------------------------------------------------------------------------


def get_kline(symbol: str, days: int = CHART_DAYS) -> list[dict]:
    """Chart bars for the last `days` sessions, each carrying its MA250 value."""
    bars = db.get_daily_bars(symbol, limit=KLINE_HISTORY_DAYS)
    if len(bars) < min(days, RSI_PERIOD + 1):
        _refresh_metrics(symbol, 0.0)
        bars = db.get_daily_bars(symbol, limit=KLINE_HISTORY_DAYS)
    # The MA is computed over the full history so it is already warmed up at the window's start.
    ma = moving_average([b["close"] for b in bars], MA_PERIOD)
    return [{**bar, "ma": ma[i]} for i, bar in enumerate(bars)][-days:]


def resolve_name(symbol: str) -> str:
    """Look up the security's name from Sina; empty string if it can't be fetched."""
    try:
        quote = sina_quotes.fetch_quotes([symbol]).get(symbol) or {}
    except Exception as e:
        print(f"[Stocks] Name lookup failed for {symbol}: {e}")
        return ""
    return quote.get("name", "") if quote.get("valid") else ""


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def get_watchlist() -> list[dict]:
    """Watchlist rows joined with the latest snapshot quote and derived metrics."""
    snapshot = load_snapshot()
    quotes = snapshot.get("quotes", {})
    metrics_by_symbol = snapshot.get("metrics", {})
    settings = db.get_alert_settings()
    rows = []
    for stock in db.list_stocks():
        quote = quotes.get(stock["symbol"]) or {}
        price = quote.get("price") or 0.0
        prev_close = quote.get("prev_close") or 0.0
        metrics = metrics_by_symbol.get(stock["symbol"]) or {}
        row = {
            **stock,
            "quote_name": quote.get("name") or "",
            "valid": bool(quote.get("valid")),
            "price": price,
            "prev_close": prev_close,
            "open": quote.get("open") or 0.0,
            "high": quote.get("high") or 0.0,
            "low": quote.get("low") or 0.0,
            "volume": quote.get("volume") or 0,
            "amount": quote.get("amount") or 0.0,
            "rsi": metrics.get("rsi"),
            "pct_1y": metrics.get("pct_1y"),
            "adjusted": metrics.get("adjusted"),
            "change_pct": ((price - prev_close) / prev_close * 100) if prev_close else None,
        }
        row["breached"] = [b["direction"] for b in _evaluate(metrics, settings)] if row["valid"] else []
        rows.append(row)
    return rows


def get_status() -> dict:
    snapshot = load_snapshot()
    return {
        "last_run": snapshot.get("fetched_at"),
        "trade_date": snapshot.get("trade_date", ""),
        "is_trading_day": snapshot.get("is_trading_day", False),
        "runs_done": snapshot.get("runs_done", []),
        "ready": bool(snapshot.get("quotes")),
        "is_running": _is_running,
    }


# ---------------------------------------------------------------------------
# Background scheduler
# ---------------------------------------------------------------------------


def _due_slot() -> Optional[str]:
    """Return the slot that should run now, or None."""
    now = _beijing_now()
    if now.weekday() >= 5:
        return None
    beijing_date = now.date().isoformat()
    runs_done = _runs_done_today(load_snapshot(), beijing_date)
    # Reversed so a late start runs only the latest due slot; run_job marks the
    # earlier ones done too, so nothing fires twice in a row.
    for slot, slot_time in reversed(RUN_SLOTS):
        if now.time() >= slot_time and slot not in runs_done:
            return slot
    return None


def _background_worker():
    global _is_running
    while True:
        try:
            slot = _due_slot()
            if slot:
                if _job_lock.acquire(blocking=False):
                    _is_running = True
                    try:
                        run_job(slot)
                    finally:
                        _is_running = False
                        _job_lock.release()
                else:
                    print("[Stocks] Background worker skipping — job already in progress.")
        except Exception as e:
            print(f"[Stocks] Background worker error: {e}")

        time.sleep(POLL_INTERVAL_SEC)


def start_background_worker():
    t = threading.Thread(target=_background_worker, daemon=True, name="stocks-worker")
    t.start()
    print("[Stocks] Background worker started")


def trigger_manual_job() -> bool:
    global _is_running
    if not _job_lock.acquire(blocking=False):
        return False
    _is_running = True

    def _run():
        global _is_running
        try:
            run_job("manual")
        except Exception as e:
            print(f"[Stocks] Manual run error: {e}")
        finally:
            _is_running = False
            _job_lock.release()

    threading.Thread(target=_run, daemon=True, name="stocks-manual-run").start()
    return True


def is_running() -> bool:
    return _is_running
