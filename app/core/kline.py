# -*- coding: UTF-8 -*-
"""
Daily bars for A-shares.

Percentiles, RSI and moving averages must run on a total-return series: a
dividend-paying ETF's raw price steps down on every ex-dividend date, which makes
it look far cheaper than it is. Tencent serves forward-adjusted (前复权) bars for
free; Sina's are unadjusted and only used as a fallback where Tencent has no data.
"""

import json
import re
from typing import Optional

import httpx

QFQ_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{count},qfq"
RAW_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={count}"
)
HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}
FETCH_TIMEOUT = 20
# Asking Tencent for more than this silently drops the response back to ~640 bars.
MAX_QFQ_BARS = 800

_BARE_KEY_RE = re.compile(r"([{,])\s*(\w+)\s*:")


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def fetch_qfq_bars(symbol: str, count: int = MAX_QFQ_BARS) -> list[dict]:
    """Forward-adjusted daily bars, oldest first. Empty list if unavailable."""
    count = max(5, min(int(count), MAX_QFQ_BARS))
    try:
        resp = httpx.get(QFQ_URL.format(symbol=symbol, count=count), headers=HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json().get("data", {}).get(symbol)
        rows = (payload.get("qfqday") or payload.get("day") or []) if isinstance(payload, dict) else []
    except Exception as e:
        print(f"[Kline] Adjusted fetch failed for {symbol}: {e}")
        return []

    bars = []
    for row in rows:
        if len(row) < 6:
            continue
        bars.append(
            {
                "day": row[0],
                "open": _to_float(row[1]),
                "close": _to_float(row[2]),
                "high": _to_float(row[3]),
                "low": _to_float(row[4]),
                "volume": _to_int(row[5]),
            }
        )
    return bars


def fetch_raw_bars(symbol: str, count: int = 1023) -> list[dict]:
    """Unadjusted daily bars from Sina, oldest first."""
    count = max(5, min(int(count), 1023))
    try:
        resp = httpx.get(RAW_URL.format(symbol=symbol, count=count), headers=HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        body = _BARE_KEY_RE.sub(r'\1"\2":', resp.text.strip())
        rows = json.loads(body) if body else []
    except Exception as e:
        print(f"[Kline] Raw fetch failed for {symbol}: {e}")
        return []

    return [
        {
            "day": row.get("day", ""),
            "open": _to_float(row.get("open")),
            "high": _to_float(row.get("high")),
            "low": _to_float(row.get("low")),
            "close": _to_float(row.get("close")),
            "volume": _to_int(row.get("volume")),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def fetch_daily_bars(symbol: str, count: int = MAX_QFQ_BARS) -> tuple[list[dict], bool]:
    """Return (bars, adjusted). Falls back to unadjusted Sina bars for symbols
    Tencent does not cover, such as Beijing-exchange listings.

    Each bar also carries close_raw, the unadjusted close. Adjusted closes drift
    upward with reinvested dividends, so anything measuring price *level* rather
    than *return* has to use the raw series instead.
    """
    bars = fetch_qfq_bars(symbol, count)
    if not bars:
        return fetch_raw_bars(symbol, count), False

    raw_by_day = {b["day"]: b["close"] for b in fetch_raw_bars(symbol, count)}
    for bar in bars:
        bar["close_raw"] = raw_by_day.get(bar["day"])
    return bars, True
