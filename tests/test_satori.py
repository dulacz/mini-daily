import httpx
import pytest

from app.core import satori


@pytest.fixture(autouse=True)
def clear_cache():
    satori._cache = None
    yield
    satori._cache = None


def test_market_note_reads_the_headline(monkeypatch):
    payload = {
        "date": "2026-08-03",
        "summary": "全市场共统计 5,534 只股票…",
        "summaryMeta": {"title": "个股普涨，创业板指表现居前", "model": "deepseek-v4-pro"},
    }
    calls = []

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    def _get(url, **kwargs):
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(satori.httpx, "get", _get)

    note = satori.fetch_market_note()
    assert note["title"] == "个股普涨，创业板指表现居前"
    assert note["date"] == "2026-08-03"
    assert note["url"] == satori.SITE_URL

    # Second call is served from the cache; the site is a free personal project.
    satori.fetch_market_note()
    assert len(calls) == 1


def test_market_note_survives_a_dead_site(monkeypatch):
    def _boom(url, **kwargs):
        raise httpx.ConnectTimeout("nope")

    monkeypatch.setattr(satori.httpx, "get", _boom)

    note = satori.fetch_market_note()
    assert note == {"title": "", "summary": "", "date": "", "url": satori.SITE_URL}
    assert satori._cache is None  # a failure must not be cached
