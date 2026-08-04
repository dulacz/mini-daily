# -*- coding: UTF-8 -*-
"""Daily market note from satori5.icu.

The site is a client-rendered SPA, so the headline is not in the served HTML; it comes
from the same JSON API the page itself calls.
"""

import time
from typing import Optional

import httpx

API_URL = "https://satori5.icu/api/market-analysis"
SITE_URL = "https://satori5.icu/#home"
FETCH_TIMEOUT = 10
# The site caches for 5 minutes and is a free personal project, so do not poll harder.
CACHE_TTL_SEC = 600

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://satori5.icu/",
}

_cache: Optional[tuple[float, dict]] = None


def fetch_market_note() -> dict:
    """Headline and paragraph for today, or empty strings when unavailable."""
    global _cache
    if _cache and time.monotonic() - _cache[0] < CACHE_TTL_SEC:
        return _cache[1]

    note = {"title": "", "summary": "", "date": "", "url": SITE_URL}
    try:
        resp = httpx.get(API_URL, headers=HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        note["title"] = str((data.get("summaryMeta") or {}).get("title") or "")
        note["summary"] = str(data.get("summary") or "")
        note["date"] = str(data.get("date") or "")
    except Exception as e:
        print(f"[Satori] Market note fetch failed: {e}")
        return note

    _cache = (time.monotonic(), note)
    return note
