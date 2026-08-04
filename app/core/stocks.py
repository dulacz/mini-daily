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


def distribution_yield_series(bars: list[dict], window: int = PERCENTILE_WINDOW) -> list[float]:
    """Trailing distribution yield in percent, one value per day once the window is full.

    The adjusted series reinvests distributions while the raw one does not, so the gap
    between their returns over the window is what the fund actually paid out. This is the
    fund's own payout, not the underlying index yield: an accumulating ETF reads ~0.
    """
    out = []
    for i in range(window, len(bars)):
        now, then = bars[i], bars[i - window]
        if not (now.get("close") and now.get("close_raw") and then.get("close") and then.get("close_raw")):
            continue
        total_return = now["close"] / then["close"]
        price_return = now["close_raw"] / then["close_raw"]
        out.append((total_return / price_return - 1) * 100)
    return out


def _refresh_metrics(symbol: str, price: float, trade_date: str = "") -> dict:
    """Refresh the stored daily bars and return the derived indicators."""
    bars, adjusted = kline.fetch_daily_bars(symbol, KLINE_HISTORY_DAYS)
    if bars:
        # Forward adjustment rescales the whole history on every dividend, so the
        # series has to be replaced wholesale rather than merged with older values.
        db.replace_daily_bars(symbol, bars)
    stored = db.get_daily_bars(symbol, limit=KLINE_HISTORY_DAYS)
    closes = [b["close"] for b in stored if b["close"]]
    # The raw closes are kept only to infer what the fund paid out; every indicator
    # below runs on the adjusted series.
    yields = distribution_yield_series(stored)
    div_yield = yields[-1] if yields else None

    # Both sides come from the stored bars so the ratio is unit-free: Tencent reports lots
    # while the Sina fallback reports shares, and the live quote uses shares either way.
    volumes = [(b["day"], b["volume"]) for b in stored if b.get("volume")]
    volume_ratio = None
    if len(volumes) >= 2 and volumes[-2][1] and (not trade_date or volumes[-1][0] == trade_date):
        volume_ratio = volumes[-1][1] / volumes[-2][1]

    return {
        "rsi": compute_rsi(closes),
        "pct_1y": compute_percentile(closes[-PERCENTILE_WINDOW:], price),
        "div_yield": div_yield,
        "div_yield_pct": compute_percentile(yields, div_yield) if div_yield is not None else None,
        "volume_ratio": volume_ratio,
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

    # A failed fetch must not blank the page: fall back to the last known good quote per symbol.
    previous = load_snapshot().get("quotes", {})
    for symbol, quote in previous.items():
        if quote.get("valid") and not (quotes.get(symbol) or {}).get("valid"):
            quotes[symbol] = quote

    valid = {sym: q for sym, q in quotes.items() if q.get("valid")}
    # Sina reports the last trading day, so a stale date means today is not a trading day.
    trade_date = next((q["date"] for q in valid.values() if q.get("date")), "")
    is_trading_day = trade_date == beijing_date

    metrics_by_symbol: dict[str, dict] = {}
    for stock in stocks:
        symbol = stock["symbol"]
        try:
            metrics_by_symbol[symbol] = _refresh_metrics(symbol, (valid.get(symbol) or {}).get("price", 0.0), trade_date)
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
            "active_alerts": snapshot.get("active_alerts", []),
        }
    )

    if not is_trading_day:
        print(f"[Stocks] Quote date {trade_date or '(unknown)'} != {beijing_date} — not a trading day, no alerts.")
        return {"trade_date": trade_date, "alerts": [], "drift_alerts": []}

    breaches = []
    settings = db.get_alert_settings()
    for stock in stocks:
        quote = valid.get(stock["symbol"])
        if not quote:
            continue
        for breach in _evaluate(metrics_by_symbol.get(stock["symbol"], {}), settings):
            breaches.append({**breach, "name": stock["name"], "symbol": stock["symbol"]})

    try:
        drift_alerts = paper.drifted_holdings(quotes)
    except Exception as e:
        print(f"[Stocks] Drift check failed: {e}")
        drift_alerts = []

    # Edge-triggered: a condition that was already breaching on the previous run stays quiet,
    # so a stock parked above the RSI band does not toast every single day.
    was_active = set(snapshot.get("active_alerts", []))
    active = {_alert_key(a) for a in breaches} | {_alert_key(a) for a in drift_alerts}
    new_alerts = [a for a in breaches if _alert_key(a) not in was_active]
    new_drift = [a for a in drift_alerts if _alert_key(a) not in was_active]
    _persist_alerts(breaches, drift_alerts, trade_date, was_active)
    _save_snapshot({**load_snapshot(), "active_alerts": sorted(active)})

    lines = [_alert_line(a) for a in new_alerts] + [paper.alert_line(a) for a in new_drift]
    if lines:
        notify.send_toast(f"股价提醒 · {trade_date}", lines)
        print(f"[Stocks] {len(lines)} new alert(s): {'; '.join(lines)}")
    else:
        print(f"[Stocks] No new alerts ({len(active)} still active).")

    return {"trade_date": trade_date, "alerts": new_alerts, "drift_alerts": new_drift}


def _alert_key(alert: dict) -> str:
    return f"{alert['symbol']}|{alert['direction']}"


def _persist_alerts(breaches: list[dict], drift: list[dict], trade_date: str, was_active: set):
    """Open an episode for a fresh breach, or stretch the running one by another trading day."""
    for alert in breaches:
        if _alert_key(alert) in was_active:
            db.extend_alert(alert["symbol"], alert["direction"], trade_date)
        else:
            db.record_alert(
                symbol=alert["symbol"],
                name=alert["name"],
                trade_date=trade_date,
                direction=alert["direction"],
                price=alert["value"],
                threshold=alert["threshold"],
            )
    for alert in drift:
        if _alert_key(alert) in was_active:
            db.extend_paper_alert(alert["symbol"], alert["direction"], trade_date)
        else:
            db.record_paper_alert(
                symbol=alert["symbol"],
                name=alert["name"],
                trade_date=trade_date,
                direction=alert["direction"],
                weight_pct=alert["weight_pct"],
                target_pct=alert["target_pct"],
                drift_pct=alert["drift_pct"],
            )


_ALERT_LABELS = {"rsi_high": "RSI ", "rsi_low": "RSI ", "pct_high": "分位 ", "pct_low": "分位 "}

TEST_TOAST_MAX_LINES = 8


def run_alert_test() -> dict:
    """Toast and record whatever is breaching right now, without waiting for a scheduled slot."""
    snapshot = load_snapshot()
    metrics = snapshot.get("metrics", {})
    quotes = snapshot.get("quotes", {})
    trade_date = snapshot.get("trade_date") or _beijing_now().date().isoformat()
    settings = db.get_alert_settings()

    lines = []
    breaches = []
    for stock in db.list_stocks(enabled_only=True):
        for breach in _evaluate(metrics.get(stock["symbol"], {}), settings):
            breaches.append({**breach, "name": stock["name"], "symbol": stock["symbol"]})
            lines.append(_alert_line({**breach, "name": stock["name"]}))

    drift = paper.drifted_holdings(quotes)
    lines += [paper.alert_line(a) for a in drift]
    _persist_alerts(breaches, drift, trade_date, set(snapshot.get("active_alerts", [])))

    plan = paper.plan_rebalance(quotes)
    lines += [
        f"{'买入' if o['side'] == 'buy' else '卖出'} {o['name']} {o['order_shares']} 股"
        for o in plan["orders"]
        if o["side"] != "hold"
    ]

    shown = lines[:TEST_TOAST_MAX_LINES]
    if len(lines) > TEST_TOAST_MAX_LINES:
        shown.append(f"…另有 {len(lines) - TEST_TOAST_MAX_LINES} 条")
    sent = notify.send_toast(f"测试提醒 · {trade_date}", shown or ["当前没有任何越界、漂移或调仓建议"])
    return {"sent": sent, "trade_date": trade_date, "count": len(lines), "lines": lines}


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
            "div_yield": metrics.get("div_yield"),
            "div_yield_pct": metrics.get("div_yield_pct"),
            "volume_ratio": metrics.get("volume_ratio"),
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
