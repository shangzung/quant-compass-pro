"""
Dynamic Risk Management, Position Sizing & Taiwan Transaction Cost Calculator.
"""
import math
from typing import Any, Dict, List
import config


def calculate_buy_cost(price: float, shares: int) -> float:
    notional = price * shares
    raw_fee = notional * config.BROKERAGE_FEE_RATE * config.BROKERAGE_DISCOUNT
    min_fee = config.MIN_BROKERAGE_FEE_LOT if shares >= 1000 and shares % 1000 == 0 else config.MIN_BROKERAGE_FEE_ODD
    fee = max(math.floor(raw_fee), min_fee)
    slippage = notional * config.SLIPPAGE_RATE
    return round(fee + slippage, 2)


def calculate_sell_cost(price: float, shares: int) -> float:
    notional = price * shares
    raw_fee = notional * config.BROKERAGE_FEE_RATE * config.BROKERAGE_DISCOUNT
    min_fee = config.MIN_BROKERAGE_FEE_LOT if shares >= 1000 and shares % 1000 == 0 else config.MIN_BROKERAGE_FEE_ODD
    fee = max(math.floor(raw_fee), min_fee)
    tax = math.floor(notional * config.SELL_TAX_RATE)
    slippage = notional * config.SLIPPAGE_RATE
    return round(fee + tax + slippage, 2)


def calculate_position_size(
    total_equity: float,
    available_cash: float,
    entry_price: float,
    stop_loss: float,
    risk_pct: float = config.MAX_RISK_PER_TRADE_PCT,
) -> Dict[str, float]:
    risk_per_share = entry_price - stop_loss
    if risk_per_share <= 0 or entry_price <= 0:
        return {"shares": 0, "capital_used": 0.0, "max_loss": 0.0, "est_buy_cost": 0.0}

    max_risk_amount = total_equity * risk_pct
    shares_by_risk = int(max_risk_amount // risk_per_share)

    max_position_value = total_equity * config.MAX_SINGLE_POSITION_PCT
    usable_cash = max(0.0, available_cash - (total_equity * config.MIN_CASH_RESERVE_PCT))
    budget = min(max_position_value, usable_cash)

    shares_by_budget = int(budget // (entry_price * (1.0 + config.BROKERAGE_FEE_RATE + config.SLIPPAGE_RATE)))
    raw_shares = min(shares_by_risk, shares_by_budget)

    if raw_shares <= 0:
        return {"shares": 0, "capital_used": 0.0, "max_loss": 0.0, "est_buy_cost": 0.0}

    final_shares = (raw_shares // 1000) * 1000 if raw_shares >= 1000 else raw_shares
    buy_cost = calculate_buy_cost(entry_price, final_shares)
    return {
        "shares": final_shares,
        "capital_used": round(final_shares * entry_price, 2),
        "max_loss": round(final_shares * risk_per_share + buy_cost, 2),
        "est_buy_cost": buy_cost,
    }


def evaluate_portfolio_risk(
    open_trades: List[Dict[str, Any]],
    cash: float,
    total_equity: float,
    market_temp: Dict[str, Any],
    latest_prices: Dict[str, float],
) -> Dict[str, Any]:
    """
    Computes Home Dashboard Investment Risk Alerts:
    - Position risk, capital utilization, max single risk, stop-loss alerts,
      sector concentration, market risk, and whether to reduce positions.
    """
    market_value = 0.0
    total_open_risk = 0.0
    max_single_risk_pct = 0.0
    sl_alerts: List[str] = []
    sector_exposure: Dict[str, float] = {}

    for tr in open_trades:
        sym = tr["symbol"]
        cur_p = latest_prices.get(sym, tr["buy_price"])
        mv = cur_p * tr["shares"]
        market_value += mv
        sec = tr.get("sector", "其他")
        sector_exposure[sec] = sector_exposure.get(sec, 0.0) + mv

        risk_amt = max(0.0, (cur_p - tr["stop_loss"]) * tr["shares"])
        total_open_risk += risk_amt
        risk_pct = (risk_amt / total_equity * 100.0) if total_equity > 0 else 0.0
        max_single_risk_pct = max(max_single_risk_pct, risk_pct)

        dist_to_sl_pct = ((cur_p - tr["stop_loss"]) / cur_p * 100.0) if cur_p > 0 else 0.0
        if dist_to_sl_pct <= 2.5:
            sl_alerts.append(f"{tr['name']} ({sym}) 距離停損價 {tr['stop_loss']:.2f} 僅剩 {dist_to_sl_pct:.1f}%")

    utilization_pct = round((market_value / total_equity * 100.0), 1) if total_equity > 0 else 0.0
    total_risk_pct = round((total_open_risk / total_equity * 100.0), 2) if total_equity > 0 else 0.0

    sector_warnings = [
        f"產業「{sec}」佔總資金 {val / total_equity * 100:.1f}% (> {config.MAX_SECTOR_EXPOSURE_PCT*100:.0f}% 上限)"
        for sec, val in sector_exposure.items()
        if total_equity > 0 and (val / total_equity) > config.MAX_SECTOR_EXPOSURE_PCT
    ]

    need_reduce = False
    reduce_reason = "目前風險在安全範圍內，維持紀律操作即可。"
    if market_temp.get("temp", 50.0) < config.AI_MIN_MARKET_TEMP and utilization_pct > 40.0:
        need_reduce = True
        reduce_reason = "大盤溫度低於 40 分且持股比例超過 40%，建議逢反彈適度減碼控制風險。"
    elif total_risk_pct > 5.0:
        need_reduce = True
        reduce_reason = f"目前總停損暴露風險達 {total_risk_pct:.2f}% (> 5%)，建議縮減部位。"
    elif sector_warnings:
        need_reduce = True
        reduce_reason = "單一產業過度集中，建議分散持倉。"

    return {
        "utilization_pct": utilization_pct,
        "total_open_risk_pct": total_risk_pct,
        "max_single_risk_pct": round(max_single_risk_pct, 2),
        "sl_alerts": sl_alerts,
        "sector_warnings": sector_warnings,
        "market_risk_label": market_temp.get("risk", "未知"),
        "need_reduce": need_reduce,
        "reduce_reason": reduce_reason,
    }
