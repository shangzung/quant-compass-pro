"""
Position Sizing & Taiwan Stock Transaction Cost Calculator.
"""
import math
from typing import Dict
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
) -> Dict[str, float]:
    risk_per_share = entry_price - stop_loss
    if risk_per_share <= 0 or entry_price <= 0:
        return {"shares": 0, "capital_used": 0.0, "max_loss": 0.0}

    max_risk_amount = total_equity * config.MAX_RISK_PER_TRADE_PCT
    shares_by_risk = int(max_risk_amount // risk_per_share)

    max_position_value = total_equity * config.MAX_SINGLE_POSITION_PCT
    usable_cash = max(0.0, available_cash - (total_equity * config.MIN_CASH_RESERVE_PCT))
    budget = min(max_position_value, usable_cash)

    shares_by_budget = int(budget // (entry_price * (1.0 + config.BROKERAGE_FEE_RATE + config.SLIPPAGE_RATE)))
    raw_shares = min(shares_by_risk, shares_by_budget)

    if raw_shares <= 0:
        return {"shares": 0, "capital_used": 0.0, "max_loss": 0.0}

    final_shares = (raw_shares // 1000) * 1000 if raw_shares >= 1000 else raw_shares
    return {
        "shares": final_shares,
        "capital_used": round(final_shares * entry_price, 2),
        "max_loss": round(final_shares * risk_per_share, 2),
    }
