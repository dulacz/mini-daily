# -*- coding: UTF-8 -*-
"""
Sina realtime quotes for A-shares (GBK encoded, requires a Sina Referer).

Daily bars live in app/core/kline.py — they need dividend adjustment, which Sina
does not provide.
"""

import re
from typing import Optional

import httpx

QUOTE_URL = "https://hq.sinajs.cn/list={symbols}"
# Sina rejects requests without one of its own domains as Referer.
HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}
FETCH_TIMEOUT = 10

_QUOTE_RE = re.compile(r'var hq_str_(\w+)="([^"]*)"')

PREFIXED_RE = re.compile(r"^(sh|sz|bj)\d{6}$")
BARE_RE = re.compile(r"^\d{6}$")
# A-share codes carry their exchange in the leading digit.
_EXCHANGE_BY_LEAD = {
    "5": "sh", "6": "sh", "7": "sh", "9": "sh",  # 沪市主板/科创板/基金/B股/新股
    "0": "sz", "1": "sz", "2": "sz", "3": "sz",  # 深市主板/创业板/基金/B股
    "4": "bj", "8": "bj",  # 北交所
}


def normalize_symbol(raw: str) -> str:
    """Turn a 6-digit A-share code into a Sina symbol; an explicit sh/sz/bj prefix wins.

    The prefix is only needed to disambiguate indices (e.g. sh000001 上证指数 vs 000001 平安银行).
    """
    symbol = (raw or "").strip().lower().replace(".", "")
    if PREFIXED_RE.match(symbol):
        return symbol
    if BARE_RE.match(symbol):
        exchange = _EXCHANGE_BY_LEAD.get(symbol[0])
        if exchange:
            return exchange + symbol
    raise ValueError(f"无法识别的股票代码 '{raw}'——请输入 6 位数字代码，如 600519")


def bare_code(symbol: str) -> str:
    """Strip the exchange prefix for display."""
    return symbol[2:] if PREFIXED_RE.match(symbol or "") else symbol


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse_quote_line(symbol: str, payload: str) -> dict:
    """Parse one `hq_str_*` payload into a quote dict.

    Stocks/ETFs return 32+ comma-separated fields; indices return only 6.
    `valid` is False for suspended or unknown symbols (price is 0 or fields missing).
    """
    fields = payload.split(",")
    invalid = {"symbol": symbol, "valid": False, "name": "", "price": 0.0, "prev_close": 0.0}

    if len(fields) >= 32:
        price = _to_float(fields[3])
        prev_close = _to_float(fields[2])
        if price <= 0 or prev_close <= 0:
            return invalid | {"name": fields[0]}
        return {
            "symbol": symbol,
            "valid": True,
            "kind": "stock",
            "name": fields[0],
            "open": _to_float(fields[1]),
            "prev_close": prev_close,
            "price": price,
            "high": _to_float(fields[4]),
            "low": _to_float(fields[5]),
            "volume": _to_int(fields[8]),
            "amount": _to_float(fields[9]),
            "date": fields[30],
            "time": fields[31],
        }

    if len(fields) >= 6:
        price = _to_float(fields[1])
        change = _to_float(fields[2])
        if price <= 0:
            return invalid | {"name": fields[0]}
        return {
            "symbol": symbol,
            "valid": True,
            "kind": "index",
            "name": fields[0],
            "open": 0.0,
            "prev_close": price - change,
            "price": price,
            "high": 0.0,
            "low": 0.0,
            "volume": _to_int(fields[4]),
            "amount": _to_float(fields[5]),
            "date": "",
            "time": "",
        }

    return invalid


def parse_quote_response(text: str) -> dict[str, dict]:
    """Parse a full hq.sinajs.cn response body into {symbol: quote}."""
    return {symbol: parse_quote_line(symbol, payload) for symbol, payload in _QUOTE_RE.findall(text)}


def fetch_quotes(symbols: list[str], client: Optional[httpx.Client] = None, attempts: int = 3) -> dict[str, dict]:
    """Fetch all symbols in a single batched request, retrying transient failures."""
    if not symbols:
        return {}
    url = QUOTE_URL.format(symbols=",".join(symbols))
    owned = client is None
    client = client or httpx.Client()
    try:
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            try:
                resp = client.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT)
                resp.raise_for_status()
                return parse_quote_response(resp.content.decode("gbk", errors="replace"))
            except Exception as e:
                last_error = e
                print(f"[Sina] Quote fetch attempt {attempt + 1}/{attempts} failed: {e}")
        raise last_error  # type: ignore[misc]
    finally:
        if owned:
            client.close()
