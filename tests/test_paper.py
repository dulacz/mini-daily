import pytest
from fastapi.testclient import TestClient

from app.core import db, paper, stocks
from app.main import app


@pytest.fixture
def account(tmp_path, monkeypatch):
    """A fresh paper account backed by a temp database, with stubbed quotes."""
    db_path = str(tmp_path / "paper.db")
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "get_conn", lambda: __import__("sqlite3").connect(db_path))
    monkeypatch.setattr(stocks, "SNAPSHOT_PATH", tmp_path / "snapshot.json")

    prices = {"sh600519": 100.0, "sz000001": 10.0}
    monkeypatch.setattr(
        paper.sina_quotes,
        "fetch_quotes",
        lambda symbols: {s: {"valid": True, "price": prices[s], "name": s.upper()} for s in symbols if s in prices},
    )

    db.init_paper()
    db.set_paper_cash(100_000)
    db.set_paper_settings(drift_tolerance_pct=20, min_trade_amount=0)
    paper._quote_cache.clear()  # module-level cache would leak prices between tests
    return prices


def test_buy_updates_cash_and_position(account):
    paper.trade("600519", "buy", 100)  # bare code, exchange inferred

    portfolio = paper.build_portfolio()
    assert portfolio["cash"] == pytest.approx(90_000)
    assert portfolio["market_value_total"] == pytest.approx(10_000)
    assert portfolio["total_assets"] == pytest.approx(100_000)

    position = portfolio["positions"][0]
    assert position["symbol"] == "sh600519"
    assert position["code"] == "600519"
    assert position["shares"] == 100
    assert position["avg_cost"] == pytest.approx(100.0)
    assert position["unrealized_pnl"] == pytest.approx(0.0)
    assert position["weight_pct"] == pytest.approx(10.0)


def test_cumulative_return_survives_selling_and_deleting(account, monkeypatch):
    # The fixture funded the account with 100k, so that is the deposit baseline.
    assert paper.build_portfolio()["total_return"] == pytest.approx(0.0)

    paper.trade("600519", "buy", 200)  # 20k at 100
    monkeypatch.setattr(
        paper.sina_quotes,
        "fetch_quotes",
        lambda symbols: {s: {"valid": True, "price": 150.0, "name": "X"} for s in symbols},
    )
    paper.trade("600519", "sell", 200)  # +10k realised, straight into cash
    db.delete_paper_position("sh600519")

    portfolio = paper.build_portfolio()
    assert portfolio["positions"] == []
    assert portfolio["total_unrealized_pnl"] == pytest.approx(0.0)  # nothing is held
    assert portfolio["total_return"] == pytest.approx(10_000)  # but the gain still shows
    assert portfolio["total_return_pct"] == pytest.approx(10.0)

    # Paying more money in must not read as profit.
    db.set_paper_cash(portfolio["cash"] + 50_000)
    assert paper.build_portfolio()["total_return"] == pytest.approx(10_000)


def test_buy_rejects_insufficient_cash(account):
    with pytest.raises(ValueError, match="现金不足"):
        paper.trade("sh600519", "buy", 2000)


def test_sell_realizes_pnl_and_keeps_avg_cost(account, monkeypatch):
    paper.trade("sh600519", "buy", 200)  # avg cost 100

    monkeypatch.setattr(
        paper.sina_quotes,
        "fetch_quotes",
        lambda symbols: {s: {"valid": True, "price": 120.0, "name": "X"} for s in symbols},
    )
    paper.trade("sh600519", "sell", 100)

    portfolio = paper.build_portfolio()
    position = portfolio["positions"][0]
    assert position["shares"] == 100
    assert position["avg_cost"] == pytest.approx(100.0)
    assert position["unrealized_pnl"] == pytest.approx(2_000)
    assert "realized_pnl" not in position
    assert portfolio["cash"] == pytest.approx(100_000 - 20_000 + 12_000)


def test_sell_rejects_more_than_held(account):
    paper.trade("sh600519", "buy", 100)
    with pytest.raises(ValueError, match="持股不足"):
        paper.trade("sh600519", "sell", 101)


def test_relative_drift_math():
    assert paper._relative_drift(26.0, 20.0) == pytest.approx(30.0)
    assert paper._relative_drift(15.0, 20.0) == pytest.approx(-25.0)
    assert paper._relative_drift(10.0, None) is None


def test_drift_alert_records_once_per_day(account):
    paper.trade("600519", "buy", 300)  # 30% of 100k
    paper.set_target("600519", 20)  # +50% relative drift, tolerance 20%

    drifted = paper.drifted_holdings({})
    assert [a["direction"] for a in drifted] == ["over"]
    assert drifted[0]["drift_pct"] == pytest.approx(50.0)

    # Reported for as long as it stays out of band; run_job decides what is worth a toast.
    assert [a["direction"] for a in paper.drifted_holdings({})] == ["over"]


def test_disabling_drift_silences_alerts_but_keeps_exits(account):
    paper.trade("600519", "buy", 300)  # 30% against a 20% target -> +50% drift
    paper.set_target("600519", 20)
    paper.set_target("000001", 80)
    assert paper.drifted_holdings({})  # baseline: monitoring on

    db.set_paper_settings(drift_tolerance_pct=20, min_trade_amount=0, drift_enabled=False)

    portfolio = paper.build_portfolio()
    assert portfolio["drift_enabled"] is False
    assert all(not p["drifted"] for p in portfolio["positions"])
    assert portfolio["positions"][1]["drift_pct"] is not None  # still shown, just not flagged
    assert paper.drifted_holdings({}) == []
    assert {o["side"] for o in paper.plan_rebalance()["orders"]} == {"hold"}

    # A zero target still has to be able to exit.
    paper.set_target("600519", 0)
    orders = {o["code"]: o["side"] for o in paper.plan_rebalance()["orders"]}
    assert orders["600519"] == "sell"


def test_no_drift_alert_inside_tolerance(account):
    paper.trade("sh600519", "buy", 220)  # 22% of 100k
    paper.set_target("sh600519", 20)  # +10% relative, under the 20% tolerance

    assert paper.drifted_holdings({}) == []


def test_no_drift_alert_when_prices_missing(account, monkeypatch):
    paper.trade("sh600519", "buy", 300)
    paper.set_target("sh600519", 20)

    def _fail(symbols):
        raise RuntimeError("timed out")

    monkeypatch.setattr(paper.sina_quotes, "fetch_quotes", _fail)
    portfolio = paper.build_portfolio({})
    assert portfolio["prices_complete"] is False
    assert portfolio["positions"][0]["priced"] is False
    assert paper.drifted_holdings({}) == []
    assert db.list_paper_alerts() == []


def test_cash_change_reweights_positions(account):
    paper.trade("600519", "buy", 100)  # 10,000 of 100,000
    assert paper.build_portfolio()["positions"][0]["weight_pct"] == pytest.approx(10.0)

    db.set_paper_cash(10_000)
    portfolio = paper.build_portfolio()
    assert portfolio["total_assets"] == pytest.approx(20_000)
    assert portfolio["positions"][0]["weight_pct"] == pytest.approx(50.0)
    assert portfolio["cash_weight_pct"] == pytest.approx(50.0)


def test_no_phantom_gain_from_float_residue(account, monkeypatch):
    monkeypatch.setattr(
        paper.sina_quotes,
        "fetch_quotes",
        lambda symbols: {s: {"valid": True, "price": 2.087, "name": "豆粕ETF"} for s in symbols},
    )
    paper.trade("159985", "buy", 36700)

    position = paper.build_portfolio()["positions"][0]
    assert position["unrealized_pnl"] == 0.0


def test_delete_position_requires_flat(account):
    paper.trade("sh600519", "buy", 100)
    with pytest.raises(ValueError, match="仍有持股"):
        db.delete_paper_position("600519")

    paper.trade("sh600519", "sell", 100)
    db.delete_paper_position("600519")
    assert db.list_paper_positions() == []


def test_set_shares_trades_the_difference(account):
    paper.set_shares("000001", 500)
    assert db.list_paper_positions()[0]["shares"] == 500
    assert db.get_paper_account()["cash"] == pytest.approx(95_000)

    paper.set_shares("000001", 200)  # sells 300 back
    assert db.list_paper_positions()[0]["shares"] == 200
    assert db.get_paper_account()["cash"] == pytest.approx(98_000)

    assert paper.set_shares("000001", 200) is None  # no-op


def test_set_cost_overrides_the_basis(account):
    paper.trade("000001", "buy", 500)  # avg cost 10
    db.set_paper_cost("000001", 8.0)

    position = paper.build_portfolio()["positions"][0]
    assert position["avg_cost"] == pytest.approx(8.0)
    assert position["cost_total"] == pytest.approx(4_000)
    assert position["unrealized_pnl"] == pytest.approx(1_000)  # 500 * (10 - 8)

    with pytest.raises(ValueError):
        db.set_paper_cost("600519", 1.0)  # not held


def test_positions_sorted_by_code(account):
    paper.trade("600519", "buy", 10)
    paper.trade("000001", "buy", 10)
    assert [p["code"] for p in paper.build_portfolio()["positions"]] == ["000001", "600519"]


def test_paper_api_endpoints():
    with TestClient(app) as client:
        # The paper page was merged into /stocks; only the APIs remain.
        assert client.get("/paper").status_code == 404
        assert "positions" in client.get("/api/paper/portfolio").json()
        assert "alerts" in client.get("/api/paper/alerts").json()
        assert "orders" in client.get("/api/paper/rebalance").json()
        assert client.get("/api/paper/trades").status_code == 404
        assert client.post("/api/paper/trade", json={"symbol": "bad", "side": "buy", "shares": 1}).status_code == 422
        assert client.post("/api/paper/trade", json={"symbol": "60051", "side": "buy", "shares": 1}).status_code == 422
        assert client.post("/api/paper/trade", json={"symbol": "600519", "side": "hold", "shares": 1}).status_code == 422
        assert client.post("/api/paper/trade", json={"symbol": "600519", "side": "buy", "shares": 0}).status_code == 422
        assert client.post("/api/paper/cash", json={"cash": -1}).status_code == 422


# ---------------------------------------------------------------------------
# Rebalancing
# ---------------------------------------------------------------------------


def test_rebalance_needs_targets(account):
    paper.trade("600519", "buy", 100)
    plan = paper.plan_rebalance()
    assert plan["ready"] is False
    assert "目标权重" in plan["reason"]


def test_rebalance_sells_overweight_and_buys_underweight(account):
    # 100k cash -> 600519 @100 is 60%, 000001 @10 is 0%; targets are 30/70.
    paper.trade("600519", "buy", 600)
    paper.set_target("600519", 30)
    paper.set_target("000001", 70)

    plan = paper.plan_rebalance()
    assert plan["ready"] is True
    orders = {o["code"]: o for o in plan["orders"]}

    assert orders["600519"]["side"] == "sell"
    assert orders["000001"]["side"] == "buy"
    # Total assets stay 100k, so the targets are 30k and 70k.
    assert orders["600519"]["projected_value"] == pytest.approx(30_000, abs=100)
    assert orders["000001"]["projected_value"] == pytest.approx(70_000, abs=100)
    assert plan["cash_after"] < 100 * 100  # less than one lot of the pricier name


def test_rebalance_leaves_holdings_inside_the_tolerance_band(account):
    # 60k in 000001 and 40k cash: weight 60% against a 58% target is only +3.4% relative drift.
    paper.trade("000001", "buy", 6_000)
    paper.set_target("000001", 58)
    paper.set_target("600519", 42)
    db.set_paper_settings(drift_tolerance_pct=20, min_trade_amount=0)

    orders = {o["code"]: o for o in paper.plan_rebalance()["orders"]}
    assert orders["000001"]["side"] == "hold"  # inside the band, left alone
    assert orders["600519"]["side"] == "buy"  # holds nothing, so -100% drift

    # Tightening the band brings the settled holding back into scope.
    db.set_paper_settings(drift_tolerance_pct=1, min_trade_amount=0)
    assert {o["code"]: o["side"] for o in paper.plan_rebalance()["orders"]}["000001"] == "sell"


def test_rebalance_orders_are_whole_lots(account):
    paper.trade("600519", "buy", 600)
    paper.set_target("600519", 33)
    paper.set_target("000001", 67)

    for order in paper.plan_rebalance()["orders"]:
        assert order["order_shares"] % paper.LOT_SIZE == 0


def test_rebalance_spends_cash_down(account):
    # Two flat-ish positions plus a big cash pile: the plan should deploy nearly all of it.
    paper.trade("600519", "buy", 100)
    paper.trade("000001", "buy", 100)
    db.set_paper_cash(100_000)
    paper.set_target("600519", 50)
    paper.set_target("000001", 50)

    plan = paper.plan_rebalance()
    assert plan["ready"] is True
    assert all(o["side"] != "sell" for o in plan["orders"])
    # Leftover has to be smaller than the cheapest lot we could still have bought.
    assert plan["cash_after"] < 100 * paper.LOT_SIZE


def test_rebalance_zero_target_exits_completely(account, monkeypatch):
    paper.trade("600519", "buy", 150)  # includes an odd lot
    paper.set_target("600519", 0)
    paper.set_target("000001", 100)

    orders = {o["code"]: o for o in paper.plan_rebalance()["orders"]}
    assert orders["600519"]["side"] == "sell"
    assert orders["600519"]["order_shares"] == 150
    assert orders["600519"]["projected_shares"] == 0


def test_execute_rebalance_applies_the_orders(account):
    paper.trade("600519", "buy", 600)
    paper.set_target("600519", 30)
    paper.set_target("000001", 70)

    result = paper.execute_rebalance()
    assert result["executed"] == 2

    after = paper.build_portfolio()
    weights = {p["code"]: p["weight_pct"] for p in after["positions"]}
    assert weights["600519"] == pytest.approx(30, abs=1)
    assert weights["000001"] == pytest.approx(70, abs=1)
    # A second pass has nothing left to do.
    assert paper.plan_rebalance()["order_count"] == 0


def test_execute_rebalance_never_overdraws_cash(account):
    paper.trade("600519", "buy", 900)  # 90k of the 100k
    paper.set_target("600519", 10)
    paper.set_target("000001", 90)

    paper.execute_rebalance()
    assert db.get_paper_account()["cash"] >= 0


def test_rebalance_skips_orders_below_the_minimum(account):
    # 60k in 000001 (lot = 1,000) + 40k cash; a 50/50 target wants a 10k sell.
    paper.trade("000001", "buy", 6000)
    paper.set_target("000001", 50)
    paper.set_target("600519", 50)

    db.set_paper_settings(drift_tolerance_pct=20, min_trade_amount=0)
    orders = {o["code"]: o for o in paper.plan_rebalance()["orders"]}
    assert orders["000001"]["side"] == "sell"
    assert orders["000001"]["order_amount"] == pytest.approx(10_000)

    # A floor above both legs leaves the portfolio untouched.
    db.set_paper_settings(drift_tolerance_pct=20, min_trade_amount=60_000)
    plan = paper.plan_rebalance()
    assert plan["order_count"] == 0
    assert all(o["side"] == "hold" for o in plan["orders"])
    assert plan["cash_after"] == pytest.approx(40_000)


def test_dropped_sell_does_not_fund_a_buy(account):
    paper.trade("000001", "buy", 6000)  # 60k held, 40k cash
    paper.set_target("000001", 50)
    paper.set_target("600519", 50)

    # The 10k sell is below the floor, so the buy may only spend the 40k of cash.
    db.set_paper_settings(drift_tolerance_pct=20, min_trade_amount=20_000)
    plan = paper.plan_rebalance()
    assert all(o["side"] != "sell" for o in plan["orders"])
    assert plan["buy_amount"] == pytest.approx(40_000)
    assert plan["cash_after"] >= 0
