import pytest
from fastapi.testclient import TestClient

from app.core import db, kline, sina_quotes, stocks
from app.main import app

# A real hq.sinajs.cn payload shape: 33 comma-separated fields.
STOCK_PAYLOAD = (
    "浦发银行,9.00,8.99,9.50,9.60,8.95,9.49,9.50,12345678,111111111.00,"
    + ",".join(["0"] * 20)
    + ",2026-08-03,15:00:00,00"
)
INDEX_PAYLOAD = "上证指数,3428.9539,12.3179,0.36,199409,25324564"
SUSPENDED_PAYLOAD = "某停牌股,0.000,10.000,0.000,0.000,0.000,0.000,0.000,0,0.0000," + ",".join(["0"] * 20) + ",2026-08-03,15:00:00,00"


def test_parse_stock_quote():
    quote = sina_quotes.parse_quote_line("sh600000", STOCK_PAYLOAD)
    assert quote["valid"] is True
    assert quote["kind"] == "stock"
    assert quote["name"] == "浦发银行"
    assert quote["price"] == pytest.approx(9.50)
    assert quote["prev_close"] == pytest.approx(8.99)
    assert quote["volume"] == 12345678
    assert quote["date"] == "2026-08-03"


def test_parse_index_quote():
    quote = sina_quotes.parse_quote_line("sh000001", INDEX_PAYLOAD)
    assert quote["valid"] is True
    assert quote["kind"] == "index"
    assert quote["price"] == pytest.approx(3428.9539)
    assert quote["prev_close"] == pytest.approx(3416.636)


def test_parse_suspended_and_unknown_quotes():
    assert sina_quotes.parse_quote_line("sh600001", SUSPENDED_PAYLOAD)["valid"] is False
    assert sina_quotes.parse_quote_line("sh999999", "")["valid"] is False
    assert sina_quotes.parse_quote_line("sh600002", "a,b,c")["valid"] is False


def test_parse_quote_response_batch():
    body = f'var hq_str_sh600000="{STOCK_PAYLOAD}";\nvar hq_str_sh000001="{INDEX_PAYLOAD}";\n'
    parsed = sina_quotes.parse_quote_response(body)
    assert set(parsed) == {"sh600000", "sh000001"}


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("600519", "sh600519"),  # 沪市主板
        ("688981", "sh688981"),  # 科创板
        ("510300", "sh510300"),  # 沪市 ETF
        ("000001", "sz000001"),  # 深市主板
        ("300750", "sz300750"),  # 创业板
        ("159915", "sz159915"),  # 深市 ETF
        ("830799", "bj830799"),  # 北交所
        ("430047", "bj430047"),
        ("sh000001", "sh000001"),  # explicit prefix wins (上证指数)
        ("SH600519", "sh600519"),
        ("  600519  ", "sh600519"),
    ],
)
def test_normalize_symbol(raw, expected):
    assert sina_quotes.normalize_symbol(raw) == expected


@pytest.mark.parametrize("raw", ["", "60051", "6005199", "nasdaq", "aapl", "us600519"])
def test_normalize_symbol_rejects_junk(raw):
    with pytest.raises(ValueError):
        sina_quotes.normalize_symbol(raw)


def test_bare_code():
    assert sina_quotes.bare_code("sh600519") == "600519"
    assert sina_quotes.bare_code("600519") == "600519"


def test_fetch_quotes_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class _Client:
        def get(self, url, headers=None, timeout=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("timed out")
            return _Resp()

        def close(self):
            pass

    class _Resp:
        content = f'var hq_str_sh600000="{STOCK_PAYLOAD}";'.encode("gbk")

        def raise_for_status(self):
            pass

    monkeypatch.setattr(sina_quotes.httpx, "Client", _Client)
    assert sina_quotes.fetch_quotes(["sh600000"])["sh600000"]["valid"] is True
    assert calls["n"] == 3


def test_fetch_quotes_raises_after_all_attempts(monkeypatch):
    class _Client:
        def get(self, url, headers=None, timeout=None):
            raise RuntimeError("timed out")

        def close(self):
            pass

    monkeypatch.setattr(sina_quotes.httpx, "Client", _Client)
    with pytest.raises(RuntimeError):
        sina_quotes.fetch_quotes(["sh600000"])


def test_resolve_name(monkeypatch):
    monkeypatch.setattr(
        stocks.sina_quotes, "fetch_quotes", lambda symbols: {"sh600519": {"valid": True, "name": "贵州茅台"}}
    )
    assert stocks.resolve_name("sh600519") == "贵州茅台"

    monkeypatch.setattr(stocks.sina_quotes, "fetch_quotes", lambda symbols: {"sh600519": {"valid": False}})
    assert stocks.resolve_name("sh600519") == ""


def test_resolve_name_survives_network_error(monkeypatch):
    def _boom(symbols):
        raise RuntimeError("timed out")

    monkeypatch.setattr(stocks.sina_quotes, "fetch_quotes", _boom)
    assert stocks.resolve_name("sh600519") == ""


def test_add_stock_fills_missing_name(isolated_stocks, monkeypatch):
    monkeypatch.setattr(stocks, "resolve_name", lambda symbol: "宁德时代")
    with TestClient(app) as client:
        resp = client.post("/api/stocks/add", json={"symbol": "300750"})
        assert resp.status_code == 200
        assert resp.json()["stock"] == {
            **resp.json()["stock"],
            "symbol": "sz300750",
            "code": "300750",
            "name": "宁德时代",
        }


def test_add_stock_rejects_unresolvable_name(isolated_stocks, monkeypatch):
    monkeypatch.setattr(stocks, "resolve_name", lambda symbol: "")
    with TestClient(app) as client:
        assert client.post("/api/stocks/add", json={"symbol": "300750"}).status_code == 400


def test_seeding_happens_once(tmp_path, monkeypatch):
    """Deleting every stock must not bring the yaml seeds back on the next startup."""
    db_path = str(tmp_path / "seed.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "get_conn", lambda: __import__("sqlite3").connect(db_path))

    db.init_stocks()
    assert len(db.list_stocks()) > 0

    for stock in db.list_stocks():
        db.delete_stock(stock["id"])
    db.init_stocks()
    assert db.list_stocks() == []


def test_watchlist_sorted_by_code(isolated_stocks):
    for code in ("300750", "601318", "000002", "830799"):
        db.add_stock(code, f"S{code}")
    assert [s["code"] for s in db.list_stocks()] == ["000002", "300750", "600000", "601318", "830799"]


@pytest.fixture
def isolated_stocks(tmp_path, monkeypatch):
    """Point the DB and snapshot file at a temp dir with a single test stock."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "get_conn", lambda: __import__("sqlite3").connect(db_path))
    monkeypatch.setattr(stocks, "SNAPSHOT_PATH", tmp_path / "snapshot.json")
    # No network: indicators are derived purely from whatever is already in stock_daily.
    monkeypatch.setattr(stocks.kline, "fetch_daily_bars", lambda symbol, count: ([], True))

    with db.get_conn() as conn:
        conn.execute(
            "CREATE TABLE stocks (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT UNIQUE NOT NULL, "
            "name TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1)"
        )
        conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "CREATE TABLE stock_alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, "
            "name TEXT NOT NULL, trade_date TEXT NOT NULL, direction TEXT NOT NULL, price REAL NOT NULL, "
            "threshold REAL NOT NULL, triggered_at TEXT NOT NULL, UNIQUE(symbol, trade_date, direction))"
        )
        conn.execute(
            "CREATE TABLE stock_daily (symbol TEXT NOT NULL, day TEXT NOT NULL, open REAL, high REAL, "
            "low REAL, close REAL NOT NULL, volume INTEGER, PRIMARY KEY (symbol, day))"
        )
    db.init_paper()  # run_job prices paper holdings in the same batch
    db.add_stock("sh600000", "浦发银行")
    return tmp_path


def _stub_quotes(monkeypatch, price, trade_date):
    payload = STOCK_PAYLOAD.replace(",9.50,", f",{price},", 1).replace("2026-08-03", trade_date)
    monkeypatch.setattr(
        stocks.sina_quotes,
        "fetch_quotes",
        lambda symbols: {"sh600000": sina_quotes.parse_quote_line("sh600000", payload)},
    )


def _seed_rising_bars(symbol="sh600000", count=100):
    """100 sessions ending well below the stubbed quote, so RSI and percentile both top out."""
    db.upsert_daily_bars(
        symbol,
        [{"day": f"2026-0{1 + i // 28}-{1 + i % 28:02d}", "open": 1.0, "high": 1.0, "low": 1.0,
          "close": 1.0 + i * 0.01, "volume": 1} for i in range(count)],
    )


def test_run_job_alerts_once_per_day(isolated_stocks, monkeypatch):
    today = stocks._beijing_now().date().isoformat()
    _stub_quotes(monkeypatch, 9.50, today)
    _seed_rising_bars()
    toasts = []
    monkeypatch.setattr(stocks.notify, "send_toast", lambda title, lines: toasts.append(lines) or True)

    first = stocks.run_job("1430")
    assert sorted(a["direction"] for a in first["alerts"]) == ["pct_high", "rsi_high"]

    second = stocks.run_job("1505")
    assert second["alerts"] == []
    assert len(toasts) == 1
    assert len(db.list_alerts()) == 2


def test_run_job_skips_alerts_on_non_trading_day(isolated_stocks, monkeypatch):
    _stub_quotes(monkeypatch, 9.50, "2020-01-01")
    _seed_rising_bars()
    monkeypatch.setattr(stocks.notify, "send_toast", lambda title, lines: pytest.fail("should not toast"))

    assert stocks.run_job("1430")["alerts"] == []
    assert db.list_alerts() == []
    assert stocks.get_status()["is_trading_day"] is False


def test_watchlist_metrics(isolated_stocks, monkeypatch):
    today = stocks._beijing_now().date().isoformat()
    _stub_quotes(monkeypatch, 9.50, today)
    _seed_rising_bars()
    monkeypatch.setattr(stocks.notify, "send_toast", lambda title, lines: True)
    stocks.run_job("1430")

    row = stocks.get_watchlist()[0]
    assert sorted(row["breached"]) == ["pct_high", "rsi_high"]
    assert row["pct_1y"] == pytest.approx(100.0)
    assert row["change_pct"] == pytest.approx((9.50 - 8.99) / 8.99 * 100)

def test_clearing_a_band_disables_that_alert(isolated_stocks, monkeypatch):
    today = stocks._beijing_now().date().isoformat()
    _stub_quotes(monkeypatch, 9.50, today)
    _seed_rising_bars()
    db.set_alert_settings(rsi_high=None, rsi_low=None, pct_high=90.0, pct_low=None)
    monkeypatch.setattr(stocks.notify, "send_toast", lambda title, lines: True)

    assert [a["direction"] for a in stocks.run_job("1430")["alerts"]] == ["pct_high"]


def test_stock_crud_and_validation(isolated_stocks):
    created = db.add_stock("000001", "平安银行")
    assert created["symbol"] == "sz000001"
    assert created["code"] == "000001"

    with pytest.raises(ValueError):
        db.add_stock("sz000001", "重复")
    with pytest.raises(ValueError):
        db.add_stock("nasdaq", "非法")

    updated = db.update_stock(created["id"], name="平安", enabled=False)
    assert updated["name"] == "平安"
    assert updated["enabled"] is False
    assert len(db.list_stocks(enabled_only=True)) == 1

    db.delete_stock(created["id"])
    assert [s["symbol"] for s in db.list_stocks()] == ["sh600000"]


def test_alert_settings_defaults_and_updates(isolated_stocks):
    assert db.get_alert_settings() == db.DEFAULT_ALERT_SETTINGS

    db.set_alert_settings(rsi_high=75.0, rsi_low=25.0, pct_high=None, pct_low=5.0)
    assert db.get_alert_settings() == {"rsi_high": 75.0, "rsi_low": 25.0, "pct_high": None, "pct_low": 5.0}

    with pytest.raises(ValueError):
        db.set_alert_settings(rsi_high=150.0)
    with pytest.raises(ValueError):
        db.set_alert_settings(nonsense=1.0)


def test_compute_rsi():
    assert stocks.RSI_PERIOD == 12
    assert stocks.compute_rsi([1.0] * 10) is None
    assert stocks.compute_rsi([float(i) for i in range(1, 30)]) == pytest.approx(100.0)
    assert stocks.compute_rsi([float(i) for i in range(30, 1, -1)]) == pytest.approx(0.0)

    # Wilder's textbook series — RSI(14) on the first 15 closes is ~70.46.
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
              45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    assert stocks.compute_rsi(closes, period=14) == pytest.approx(70.46, abs=0.1)


def test_compute_percentile():
    closes = [float(i) for i in range(1, 101)]  # 1..100
    assert stocks.compute_percentile(closes, 100.0) == pytest.approx(99.5)
    assert stocks.compute_percentile(closes, 1.0) == pytest.approx(0.5)
    assert stocks.compute_percentile(closes, 50.0) == pytest.approx(49.5)
    assert stocks.compute_percentile(closes, 200.0) == pytest.approx(100.0)

    # Too little history, or no price, gives no reading rather than a misleading one.
    assert stocks.compute_percentile([1.0] * 10, 1.0) is None
    assert stocks.compute_percentile(closes, 0.0) is None


def test_moving_average():
    ma = stocks.moving_average([1.0, 2.0, 3.0, 4.0, 5.0], 3)
    assert ma[:2] == [None, None]
    assert ma[2:] == pytest.approx([2.0, 3.0, 4.0])
    assert stocks.moving_average([1.0, 2.0], 3) == [None, None]


def test_toast_lines_name_the_indicator(isolated_stocks, monkeypatch):
    today = stocks._beijing_now().date().isoformat()
    _stub_quotes(monkeypatch, 9.50, today)
    _seed_rising_bars()
    toasts = []
    monkeypatch.setattr(stocks.notify, "send_toast", lambda title, lines: toasts.append(lines) or True)

    stocks.run_job("1430")
    joined = " ".join(toasts[0])
    assert "RSI" in joined
    assert "分位" in joined


def test_late_start_marks_earlier_slots_done(isolated_stocks, monkeypatch):
    today = stocks._beijing_now().date().isoformat()
    _stub_quotes(monkeypatch, 8.50, today)
    monkeypatch.setattr(stocks.notify, "send_toast", lambda title, lines: True)

    stocks.run_job("1505")
    assert stocks.get_status()["runs_done"] == ["1430", "1505"]


def test_kline_carries_moving_average(isolated_stocks):
    db.replace_daily_bars(
        "sh600000",
        [{"day": f"2026-0{1 + i // 28}-{1 + i % 28:02d}", "open": 1.0, "high": 1.0, "low": 1.0,
          "close": 10.0, "volume": 1} for i in range(100)],
    )
    original_period = stocks.MA_PERIOD
    try:
        stocks.MA_PERIOD = 5
        bars = stocks.get_kline("sh600000", days=100)
    finally:
        stocks.MA_PERIOD = original_period

    assert len(bars) == 100
    assert bars[0]["ma"] is None
    assert bars[-1]["ma"] == pytest.approx(10.0)


def test_replace_daily_bars_drops_stale_adjustment(isolated_stocks):
    db.replace_daily_bars("sh600000", [{"day": "2026-01-01", "close": 2.0}, {"day": "2026-01-02", "close": 2.1}])
    # A dividend rescales the whole history, so the refreshed series must not merge with the old one.
    db.replace_daily_bars("sh600000", [{"day": "2026-01-02", "close": 1.9}, {"day": "2026-01-03", "close": 2.0}])

    stored = db.get_daily_bars("sh600000")
    assert [b["day"] for b in stored] == ["2026-01-02", "2026-01-03"]
    assert stored[0]["close"] == pytest.approx(1.9)


def test_fetch_daily_bars_prefers_adjusted(monkeypatch):
    monkeypatch.setattr(kline, "fetch_qfq_bars", lambda symbol, count: [{"day": "2026-01-02", "close": 1.9}])
    monkeypatch.setattr(kline, "fetch_raw_bars", lambda symbol, count: pytest.fail("should not fall back"))

    bars, adjusted = kline.fetch_daily_bars("sh600000")
    assert adjusted is True
    assert bars[0]["close"] == 1.9


def test_fetch_daily_bars_falls_back_to_raw(monkeypatch):
    monkeypatch.setattr(kline, "fetch_qfq_bars", lambda symbol, count: [])
    monkeypatch.setattr(kline, "fetch_raw_bars", lambda symbol, count: [{"day": "2026-01-02", "close": 2.5}])

    bars, adjusted = kline.fetch_daily_bars("bj430047")
    assert adjusted is False
    assert bars[0]["close"] == 2.5


def test_stock_api_endpoints():
    with TestClient(app) as client:
        assert client.get("/stocks").status_code == 200
        listing = client.get("/api/stocks/list").json()
        assert "stocks" in listing and "settings" in listing
        assert "alerts" in client.get("/api/stocks/alerts").json()
        assert "is_running" in client.get("/api/stocks/status").json()
        assert client.get("/api/stocks/kline?symbol=not-a-symbol").status_code == 400
        assert client.get("/api/stocks/kline?symbol=600519&days=5").json()["symbol"] == "sh600519"
        assert client.post("/api/stocks/add", json={"symbol": "bad", "name": "x"}).status_code == 422
        assert client.post("/api/stocks/settings", json={"rsi_high": 150}).status_code == 422
