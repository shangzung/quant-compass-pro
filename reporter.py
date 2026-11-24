"""
Strategy Performance & Validation Reporter.
Computes all 12 required metrics:
1. Total trades, 2. Win rate, 3. Avg win, 4. Avg loss, 5. Profit Factor,
6. Max Drawdown, 7. Avg holding days, 8. Total return, 9. Annualized return,
10. 0050 benchmark return, 11. Total transaction costs, 12. Sample size.
"""
from typing import Any, Dict, List, Optional
import config
from database import LedgerDB


def generate_performance_report(
    db: LedgerDB,
    strategy_version: str,
    benchmark_0050_ret: Optional[float] = None,
) -> Dict[str, Any]:
    snaps = db.get_all_snapshots(strategy_version)
    trades = db.get_all_trades(strategy_version)

    if not snaps:
        return {"status": "EMPTY", "strategy_version": strategy_version, "message": "尚無模擬交易紀錄。"}

    latest = snaps[-1]
    closed = [t for t in trades if t["status"] == "CLOSED"]
    open_tr = [t for t in trades if t["status"] == "OPEN"]

    wins = [t for t in closed if t["net_pnl"] > 0]
    losses = [t for t in closed if t["net_pnl"] < 0]
    total_closed = len(closed)
    win_rate = round((len(wins) / total_closed) * 100.0, 2) if total_closed > 0 else 0.0

    gross_profit = round(sum(t["net_pnl"] for t in wins), 2)
    gross_loss = round(abs(sum(t["net_pnl"] for t in losses)), 2)
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0)

    avg_win = round(gross_profit / len(wins), 2) if wins else 0.0
    avg_loss = round(-gross_loss / len(losses), 2) if losses else 0.0
    avg_hold = round(sum(t["holding_days"] for t in closed) / total_closed, 1) if total_closed > 0 else 0.0
    total_costs = round(sum(t["total_cost"] for t in trades), 2)

    expectancy = round(((len(wins) / total_closed) * avg_win) + ((len(losses) / total_closed) * avg_loss), 2) if total_closed > 0 else 0.0

    # Annualized return (252 trading days/year)
    n_days = max(len(snaps), 1)
    tot_ret_dec = (latest["total_equity"] / config.INITIAL_CAPITAL) - 1.0
    if n_days >= 5 and (1.0 + tot_ret_dec) > 0:
        ann_ret_pct = round((((1.0 + tot_ret_dec) ** (252.0 / n_days)) - 1.0) * 100.0, 2)
    else:
        ann_ret_pct = round(tot_ret_dec * 100.0, 2)

    # Derive 0050 benchmark return from snapshot series if not explicitly supplied
    if benchmark_0050_ret is None:
        bm_vals = [s["benchmark_0050_close"] for s in snaps if s.get("benchmark_0050_close")]
        if len(bm_vals) >= 2 and bm_vals[0] > 0:
            benchmark_0050_ret = round(((bm_vals[-1] / bm_vals[0]) - 1.0) * 100.0, 2)

    # Strategy degradation / warning detector
    warnings: List[str] = []
    if total_closed < config.MIN_SAMPLE_SIZE_WARNING:
        warnings.append(f"目前交易樣本不足（僅 {total_closed} 筆已平倉），無法證明策略具有穩定獲利能力。")
    if len(closed) >= 3 and all(t["net_pnl"] < 0 for t in closed[:3]):
        warnings.append("⚠️ 策略警告：最近連續 3 筆交易虧損，請檢視市場環境是否改變（系統不會自動修改正式策略）。")
    if latest["max_drawdown_pct"] <= -10.0:
        warnings.append(f"⚠️ 回撤警告：最大回撤已達 {latest['max_drawdown_pct']:.2f}%，建議降低風險暴露。")

    return {
        "status": "OK",
        "strategy_version": strategy_version,
        "period_start": snaps[0]["date"],
        "period_end": latest["date"],
        "trading_days": n_days,
        "initial_capital": config.INITIAL_CAPITAL,
        "final_equity": latest["total_equity"],
        "net_pnl": round(latest["total_equity"] - config.INITIAL_CAPITAL, 2),
        "total_return_pct": latest["cum_return_pct"],
        "annualized_return_pct": ann_ret_pct,
        "benchmark_0050_ret": benchmark_0050_ret,
        "realized_pnl": latest["realized_pnl"],
        "unrealized_pnl": latest["unrealized_pnl"],
        "total_trades": len(trades),
        "closed_trades": total_closed,
        "open_trades": len(open_tr),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy_twd": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown_pct": latest["max_drawdown_pct"],
        "avg_holding_days": avg_hold,
        "total_transaction_costs": total_costs,
        "warnings": warnings,
        "disclaimer": "歷史測試結果不代表未來績效。",
    }
