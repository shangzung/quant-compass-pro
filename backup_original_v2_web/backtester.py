"""
Strictly Causal Historical Backtester & Automated Strategy Diagnostic Engine.
Allows users to verify Win Rate, Expectancy, Profit Factor & MDD over real past months.
"""
import tempfile
import os
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from database import LedgerDB
from paper_engine import PaperTradingEngine
from reporter import generate_performance_report


def run_historical_backtest(
    market_data: Dict[str, Tuple[str, pd.DataFrame, str]],
    benchmark_df: Optional[pd.DataFrame] = None,
    test_days: int = 60,
) -> Dict[str, Any]:
    if not market_data:
        return {"status": "EMPTY", "message": "無行情資料可供回測。"}

    # Collect union of available trading dates
    all_dates = sorted(set().union(*(df.index.tolist() for _, df, _ in market_data.values())))
    if len(all_dates) < 70:
        return {"status": "EMPTY", "message": "歷史資料長度不足 (需至少 70 個交易日)。"}

    sim_dates = all_dates[-test_days:]

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    try:
        db = LedgerDB(tmp.name)
        engine = PaperTradingEngine(db)
        for d in sim_dates:
            engine.run_daily_cycle(d, market_data, benchmark_df=benchmark_df)

        report = generate_performance_report(db)
        snaps = db.get_all_snapshots()
        trades = db.get_all_trades()
        diagnosis = diagnose_strategy(report)
        return {
            "status": "OK",
            "report": report,
            "snapshots": snaps,
            "trades": trades,
            "diagnosis": diagnosis,
        }
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)


def diagnose_strategy(report: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    if report.get("status") != "OK":
        return ["尚無足夠回測結果可進行診斷。"]

    closed = report.get("closed_trades", 0)
    win_rate = report.get("win_rate_pct", 0.0) / 100.0
    avg_win = report.get("avg_win", 0.0)
    avg_loss = abs(report.get("avg_loss", 0.0))
    pf = report.get("profit_factor", 0.0)
    mdd = report.get("max_drawdown_pct", 0.0)

    if closed < 10:
        notes.append(f"⚠️ 樣本數偏少 (僅 {closed} 筆已平倉交易)，勝率波動大，建議拉長回測天數或擴大選股池。")

    expectancy = (win_rate * avg_win) - ((1.0 - win_rate) * avg_loss)
    if expectancy > 0:
        notes.append(f"✅ 正期望值策略：平均每筆交易預期淨賺 **${expectancy:+,.0f} TWD** (勝率 {win_rate*100:.1f}%，賺賠比 {avg_win/avg_loss:.2f}x)。" if avg_loss > 0 else f"✅ 正期望值策略：平均每筆賺 **${expectancy:+,.0f} TWD**。")
    else:
        notes.append(f"❌ 目前為負期望值 (**${expectancy:+,.0f} TWD/筆**)：建議檢查是否停損過窄（易被洗出場）或大盤處於盤整震盪期。")

    if win_rate < 0.40 and avg_loss > 0 and (avg_win / avg_loss) < 1.8:
        notes.append("🔧 改進建議：勝率低於 40% 且平均賺賠比不足 1.8，可嘗試提高強勢股門檻（例如僅買 RS20 > 0 或加入法人籌碼濾網）。")
    elif pf >= 1.5:
        notes.append(f"🚀 Profit Factor 達 **{pf:.2f}**，具備良好盈虧結構，可持續進行實盤模擬追蹤。")

    if mdd <= -10.0:
        notes.append(f"🛡️ 風控提醒：最大回撤達 **{mdd:.2f}%**，建議啟用大盤濾網或降低單筆風險至 0.5%~0.8%。")

    return notes
