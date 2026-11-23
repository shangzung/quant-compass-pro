"""
Performance Evaluation Engine (Win Rate, Expectancy, Profit Factor, MDD).
"""
from typing import Any, Dict, Optional
import config
from database import LedgerDB


def generate_performance_report(
    db: LedgerDB,
    benchmark_0050_ret: Optional[float] = None,
    benchmark_twii_ret: Optional[float] = None,
) -> Dict[str, Any]:
    snaps = db.get_all_snapshots()
    trades = db.get_all_trades()

    if not snaps:
        return {"status": "EMPTY", "message": "尚無任何模擬交易紀錄。"}

    latest = snaps[-1]
    closed = [t for t in trades if t["status"] == "CLOSED"]
    open_tr = [t for t in trades if t["status"] == "OPEN"]

    wins = [t for t in closed if t["net_pnl"] > 0]
    losses = [t for t in closed if t["net_pnl"] < 0]
    breakeven = [t for t in closed if t["net_pnl"] == 0]

    total_closed = len(closed)
    win_rate = round((len(wins) / total_closed) * 100.0, 2) if total_closed > 0 else 0.0

    gross_profit = round(sum(t["net_pnl"] for t in wins), 2)
    gross_loss = round(abs(sum(t["net_pnl"] for t in losses)), 2)
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0)

    avg_win = round(gross_profit / len(wins), 2) if wins else 0.0
    avg_loss = round(-gross_loss / len(losses), 2) if losses else 0.0
    expectancy = round(((len(wins) / total_closed) * avg_win) + ((len(losses) / total_closed) * avg_loss), 2) if total_closed > 0 else 0.0

    sample_warning = (
        "目前交易樣本不足，無法證明策略具有穩定獲利能力。"
        if total_closed < config.MIN_SAMPLE_SIZE_WARNING
        else "已達基本樣本數門檻，仍建議搭配歷史回測持續驗證。"
    )

    return {
        "status": "OK",
        "period_start": snaps[0]["date"],
        "period_end": latest["date"],
        "trading_days": len(snaps),
        "initial_capital": config.INITIAL_CAPITAL,
        "final_equity": latest["total_equity"],
        "net_pnl": round(latest["total_equity"] - config.INITIAL_CAPITAL, 2),
        "total_return_pct": latest["cum_return_pct"],
        "realized_pnl": latest["realized_pnl"],
        "unrealized_pnl": latest["unrealized_pnl"],
        "closed_trades": total_closed,
        "open_trades": len(open_tr),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate_pct": win_rate,
        "expectancy_twd": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown_pct": latest["max_drawdown_pct"],
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "benchmark_0050_ret": benchmark_0050_ret,
        "benchmark_twii_ret": benchmark_twii_ret,
        "sample_warning": sample_warning,
    }
