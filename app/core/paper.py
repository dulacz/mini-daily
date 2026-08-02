# -*- coding: UTF-8 -*-
"""
Paper trading account — positions valued from Sina quotes, with target-weight
drift alerts raised by the same scheduled job as the price monitor.
"""

from typing import Optional

from . import db, sina_quotes


def _quote_price(symbol: str, quotes: dict) -> float:
    quote = quotes.get(symbol) or {}
    return quote.get("price") or 0.0 if quote.get("valid") else 0.0


def fetch_price(symbol: str) -> tuple[str, float, str]:
    """Normalised symbol, live price and name, used as the fill price of a trade."""
    symbol = sina_quotes.normalize_symbol(symbol)
    quote = sina_quotes.fetch_quotes([symbol]).get(symbol) or {}
    if not quote.get("valid"):
        raise ValueError(f"无法获取 {sina_quotes.bare_code(symbol)} 的行情（代码有误或已停牌）")
    return symbol, quote["price"], quote.get("name") or symbol


def build_portfolio(quotes: Optional[dict] = None) -> dict:
    """Positions valued at the latest known prices, with weights and drift."""
    account = db.get_paper_account()
    positions = db.list_paper_positions()

    if quotes is None:
        from . import stocks

        quotes = stocks.load_snapshot().get("quotes", {})

    # Flat positions still need a price when they carry a target weight to buy into.
    missing = [
        p["symbol"]
        for p in positions
        if (p["shares"] > 0 or p["target_weight"] is not None) and not _quote_price(p["symbol"], quotes)
    ]
    if missing:
        try:
            quotes = {**quotes, **sina_quotes.fetch_quotes(missing)}
        except Exception as e:
            print(f"[Paper] Price fetch failed for {missing}: {e}")

    rows = []
    market_value_total = 0.0
    prices_complete = True
    for position in positions:
        price = _quote_price(position["symbol"], quotes)
        shares = position["shares"]
        if shares > 0 and price <= 0:
            prices_complete = False
        # Rounded so a sub-cent float residue can't read as a gain.
        market_value = round(price * shares, 2)
        market_value_total += market_value
        avg_cost = position["cost_total"] / shares if shares else 0.0
        unrealized = round(market_value - position["cost_total"], 2)
        rows.append(
            {
                **position,
                "priced": price > 0 or shares == 0,
                "price": price,
                "avg_cost": avg_cost,
                "market_value": market_value,
                "unrealized_pnl": unrealized,
                "total_pnl": round(unrealized + position["realized_pnl"], 2),
                "return_pct": (unrealized / position["cost_total"] * 100) if position["cost_total"] else None,
            }
        )

    total_assets = round(account["cash"] + market_value_total, 2)
    tolerance = account["drift_tolerance_pct"]

    for row in rows:
        row["weight_pct"] = (row["market_value"] / total_assets * 100) if total_assets else 0.0
        row["drift_pct"] = _relative_drift(row["weight_pct"], row["target_weight"])
        row["drifted"] = row["drift_pct"] is not None and abs(row["drift_pct"]) >= tolerance

    cash_weight = (account["cash"] / total_assets * 100) if total_assets else 0.0

    return {
        "cash": account["cash"],
        "cash_weight_pct": cash_weight,
        "drift_tolerance_pct": tolerance,
        "min_trade_amount": account["min_trade_amount"],
        "prices_complete": prices_complete,
        "market_value_total": round(market_value_total, 2),
        "total_assets": total_assets,
        "total_cost": round(sum(p["cost_total"] for p in positions), 2),
        "total_unrealized_pnl": round(sum(r["unrealized_pnl"] for r in rows), 2),
        "total_realized_pnl": round(sum(p["realized_pnl"] for p in positions), 2),
        "positions": rows,
    }


def _relative_drift(weight_pct: float, target_pct: Optional[float]) -> Optional[float]:
    """Drift relative to target, e.g. actual 26% vs target 20% -> +30%."""
    if target_pct is None or target_pct <= 0:
        return None
    return (weight_pct - target_pct) / target_pct * 100


def trade(symbol: str, side: str, shares: int) -> dict:
    symbol, price, name = fetch_price(symbol)
    return db.record_paper_trade(symbol, name, side, shares, price)


def set_target(symbol: str, target_weight: Optional[float]):
    """Set a target weight, looking the name up when the symbol is not held yet."""
    symbol = sina_quotes.normalize_symbol(symbol)
    if any(p["symbol"] == symbol for p in db.list_paper_positions()):
        db.set_paper_target_weight(symbol, target_weight)
        return
    _, _, name = fetch_price(symbol)
    db.set_paper_target_weight(symbol, target_weight, name=name)


def set_shares(symbol: str, target_shares: int) -> Optional[dict]:
    """Trade the difference so the holding ends up at target_shares."""
    symbol = sina_quotes.normalize_symbol(symbol)
    held = next((p["shares"] for p in db.list_paper_positions() if p["symbol"] == symbol), 0)
    delta = target_shares - held
    if delta == 0:
        return None
    return trade(symbol, "buy" if delta > 0 else "sell", abs(delta))


def check_drift(trade_date: str, quotes: dict) -> list[dict]:
    """Record newly drifted holdings for the day and return them for notification."""
    portfolio = build_portfolio(quotes)
    if not portfolio["prices_complete"]:
        # Missing prices would read as 0% weight and fire bogus under-weight alerts.
        print("[Paper] Skipping drift check — some holdings have no price.")
        return []
    tolerance = portfolio["drift_tolerance_pct"]

    candidates = [
        {
            "symbol": row["symbol"],
            "code": row["code"],
            "name": row["name"],
            "weight_pct": row["weight_pct"],
            "target_pct": row["target_weight"],
            "drift_pct": row["drift_pct"],
        }
        for row in portfolio["positions"]
        if row["drifted"]
    ]

    new_alerts = []
    for item in candidates:
        direction = "over" if item["drift_pct"] > 0 else "under"
        if db.record_paper_alert(
            symbol=item["symbol"],
            name=item["name"],
            trade_date=trade_date,
            direction=direction,
            weight_pct=item["weight_pct"],
            target_pct=item["target_pct"],
            drift_pct=item["drift_pct"],
        ):
            new_alerts.append({**item, "direction": direction})

    if new_alerts:
        print(f"[Paper] {len(new_alerts)} drift alert(s) at tolerance ±{tolerance}%")
    return new_alerts


def alert_line(alert: dict) -> str:
    arrow = "超配" if alert["direction"] == "over" else "低配"
    return f"{alert['name']} {arrow} {alert['weight_pct']:.1f}% (目标 {alert['target_pct']:.1f}%, 偏离 {alert['drift_pct']:+.0f}%)"


def held_symbols() -> list[str]:
    return [p["symbol"] for p in db.list_paper_positions() if p["shares"] > 0]


# ---------------------------------------------------------------------------
# Rebalancing
# ---------------------------------------------------------------------------

LOT_SIZE = 100


def plan_rebalance(quotes: Optional[dict] = None) -> dict:
    """Orders that move every targeted position back to its weight, spending the cash down.

    Target weights are normalised to 100% so leftover cash gets deployed even when
    they do not add up. Sells round down and buys round to whole lots.
    """
    portfolio = build_portfolio(quotes)
    eligible = [p for p in portfolio["positions"] if p["target_weight"] is not None]

    def empty(reason: str) -> dict:
        return {"ready": False, "reason": reason, "orders": [], "skipped": [], **_plan_totals([], portfolio["cash"])}

    if not eligible:
        return empty("尚未设置目标权重")
    if not portfolio["prices_complete"]:
        return empty("行情不完整，暂不生成方案")
    unpriced = [p for p in eligible if p["price"] <= 0]
    if unpriced:
        return empty(f"{'、'.join(p['code'] for p in unpriced)} 无行情，暂不生成方案")

    weight_sum = sum(p["target_weight"] for p in eligible)
    if weight_sum <= 0:
        return empty("目标权重合计为 0")

    min_amount = db.get_paper_account()["min_trade_amount"]
    investable = portfolio["cash"] + sum(p["market_value"] for p in eligible)
    plan = {
        p["symbol"]: {
            "symbol": p["symbol"],
            "code": p["code"],
            "name": p["name"],
            "price": p["price"],
            "shares": p["shares"],
            "market_value": p["market_value"],
            "weight_pct": p["weight_pct"],
            "target_weight": p["target_weight"],
            "target_value": round(investable * p["target_weight"] / weight_sum, 2),
            "delta_shares": 0,
        }
        for p in eligible
    }

    cash = portfolio["cash"]

    # Sells first so their proceeds are available to the buys. Sub-threshold sells are
    # dropped here rather than later, so the buys are never funded by cash that never arrives.
    for row in plan.values():
        gap = row["target_value"] - row["market_value"]
        if gap >= 0 or row["shares"] <= 0:
            continue
        lot_cost = row["price"] * LOT_SIZE
        # A zero target means exit completely, odd lots included.
        sell = row["shares"] if row["target_weight"] == 0 else min(int(-gap // lot_cost) * LOT_SIZE, row["shares"])
        if sell > 0 and sell * row["price"] >= min_amount:
            row["delta_shares"] = -sell
            cash = round(cash + sell * row["price"], 2)

    def remaining_gap(row):
        return row["target_value"] - (row["market_value"] + row["delta_shares"] * row["price"])

    # Bulk buys, scaled down proportionally if the sells did not free up enough cash.
    buyable = [r for r in plan.values() if remaining_gap(r) > 0]
    total_gap = sum(remaining_gap(r) for r in buyable)
    scale = min(1.0, cash / total_gap) if total_gap > 0 else 0.0
    for row in sorted(buyable, key=remaining_gap, reverse=True):
        lot_cost = row["price"] * LOT_SIZE
        lots = int(min(remaining_gap(row) * scale, cash) // lot_cost)
        if lots > 0:
            row["delta_shares"] += lots * LOT_SIZE
            cash = round(cash - lots * LOT_SIZE * row["price"], 2)

    # Mop up: one lot at a time to whoever is furthest below target, while it still helps.
    for _ in range(1000):
        candidates = [
            r for r in plan.values()
            if r["price"] * LOT_SIZE <= cash and remaining_gap(r) >= r["price"] * LOT_SIZE / 2
        ]
        if not candidates:
            break
        row = max(candidates, key=remaining_gap)
        row["delta_shares"] += LOT_SIZE
        cash = round(cash - LOT_SIZE * row["price"], 2)

    # Drop buys too small to be worth the friction, then top up the ones that survived.
    for row in plan.values():
        if 0 < row["delta_shares"] * row["price"] < min_amount:
            cash = round(cash + row["delta_shares"] * row["price"], 2)
            row["delta_shares"] = 0
    for _ in range(1000):
        candidates = [
            r for r in plan.values()
            if r["delta_shares"] > 0
            and r["price"] * LOT_SIZE <= cash
            and remaining_gap(r) >= r["price"] * LOT_SIZE / 2
        ]
        if not candidates:
            break
        row = max(candidates, key=remaining_gap)
        row["delta_shares"] += LOT_SIZE
        cash = round(cash - LOT_SIZE * row["price"], 2)

    orders = []
    for row in plan.values():
        delta = row["delta_shares"]
        projected_value = round(row["market_value"] + delta * row["price"], 2)
        orders.append(
            {
                **row,
                "side": "buy" if delta > 0 else "sell" if delta < 0 else "hold",
                "order_shares": abs(delta),
                "order_amount": round(abs(delta) * row["price"], 2),
                "projected_shares": row["shares"] + delta,
                "projected_value": projected_value,
                "projected_weight_pct": (projected_value / investable * 100) if investable else 0.0,
            }
        )
    orders.sort(key=lambda o: (o["side"] == "hold", o["side"], o["code"]))

    skipped = [
        {"code": p["code"], "name": p["name"], "shares": p["shares"], "market_value": p["market_value"]}
        for p in portfolio["positions"]
        if p["target_weight"] is None
    ]
    return {
        "ready": True,
        "reason": "",
        "orders": orders,
        "skipped": skipped,
        "min_trade_amount": min_amount,
        **_plan_totals(orders, cash),
    }


def _plan_totals(orders: list[dict], cash_after: float) -> dict:
    sell_amount = sum(o["order_amount"] for o in orders if o["side"] == "sell")
    buy_amount = sum(o["order_amount"] for o in orders if o["side"] == "buy")
    return {
        "sell_amount": round(sell_amount, 2),
        "buy_amount": round(buy_amount, 2),
        "order_count": sum(1 for o in orders if o["side"] != "hold"),
        "cash_after": round(cash_after, 2),
    }


def execute_rebalance() -> dict:
    """Apply a freshly computed plan: sells first, then buys."""
    plan = plan_rebalance()
    if not plan["ready"]:
        raise ValueError(plan["reason"])
    if not plan["order_count"]:
        return {"executed": 0, "plan": plan}

    executed = 0
    for side in ("sell", "buy"):
        for order in plan["orders"]:
            if order["side"] != side:
                continue
            db.record_paper_trade(order["symbol"], order["name"], side, order["order_shares"], order["price"])
            executed += 1
    return {"executed": executed, "plan": plan}
