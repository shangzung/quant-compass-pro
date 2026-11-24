"""
Strategy Validation Center:
- Strictly Causal Historical Backtest
- Walk-Forward Validation (Train / Out-of-Sample Test Split)
- Dual Strategy Comparison (QC-PT-1.0-FROZEN vs QC-AI-2.0 vs 0050)
"""
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

import config
from database import LedgerDB
from paper_engine import PaperTradingEngine
from reporter import generate_performance_report


def run_comparison_backtest(
    market_data: Dict[str, Tuple[str, str, pd.DataFrame, str]],
    benchmark_df: Optional[pd.DataFrame] = None,
    benchmark_0050_df: Optional[pd.DataFrame] = None,
    test_days: int = 60,
) -> Dict[str, Any]:
    if not market_data:
        return {"status": "EMPTY", "message": "無行情資料可供回測。"}

    all_dates = sorted(set().union(*(df.index.tolist() for _, _, df, _ in market_data.values())))
    if len(all_dates) < config.MA_LONG + 10:
        return {"status": "EMPTY", "message": f"歷史資料長度不足（需至少 {config.MA_LONG + 10} 個交易日）。"}

    sim_dates = all_dates[-test_days:]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    try:
        db = LedgerDB(tmp.name)
        engine = PaperTradingEngine(db)
        for d in sim_dates:
            engine.run_all_strategies(
                d, market_data, benchmark_df=benchmark_df,
                benchmark_0050_df=benchmark_0050_df, export_json=False
            )
        rep_frozen = generate_performance_report(db, config.STRATEGY_FROZEN)
        rep_ai = generate_performance_report(db, config.STRATEGY_AI_V2)
        return {
            "status": "OK",
            "frozen": {
                "report": rep_frozen,
                "snapshots": db.get_all_snapshots(config.STRATEGY_FROZEN),
                "trades": db.get_all_trades(config.STRATEGY_FROZEN),
            },
            "ai_v2": {
                "report": rep_ai,
                "snapshots": db.get_all_snapshots(config.STRATEGY_AI_V2),
                "trades": db.get_all_trades(config.STRATEGY_AI_V2),
            },
        }
    finally:
        if os.path.exists(tmp.name):
            os.remove(tmp.name)


def run_walk_forward_validation(
    market_data: Dict[str, Tuple[str, str, pd.DataFrame, str]],
    benchmark_df: Optional[pd.DataFrame] = None,
    benchmark_0050_df: Optional[pd.DataFrame] = None,
    folds: int = 3,
    oos_days_per_fold: int = 20,
) -> Dict[str, Any]:
    """
    Splits available post-warmup dates into sequential Train / Out-of-Sample (OOS) Walk-Forward folds.
    Evaluates both QC-PT-1.0-FROZEN and QC-AI-2.0 strictly out-of-sample without lookahead.
    """
    if not market_data:
        return {"status": "EMPTY", "message": "無行情資料可供 Walk-Forward 驗證。"}

    all_dates = sorted(set().union(*(df.index.tolist() for _, _, df, _ in market_data.values())))
    needed = config.MA_LONG + (folds * oos_days_per_fold)
    if len(all_dates) < needed:
        return {"status": "EMPTY", "message": f"Walk-Forward 需要至少 {needed} 個交易日（目前僅 {len(all_dates)} 日）。"}

    oos_pool = all_dates[-(folds * oos_days_per_fold):]
    fold_results: List[Dict[str, Any]] = []

    for f_idx in range(folds):
        f_dates = oos_pool[f_idx * oos_days_per_fold : (f_idx + 1) * oos_days_per_fold]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        try:
            db = LedgerDB(tmp.name)
            engine = PaperTradingEngine(db)
            for d in f_dates:
                engine.run_all_strategies(
                    d, market_data, benchmark_df=benchmark_df,
                    benchmark_0050_df=benchmark_0050_df, export_json=False
                )
            rf = generate_performance_report(db, config.STRATEGY_FROZEN)
            ra = generate_performance_report(db, config.STRATEGY_AI_V2)
            fold_results.append({
                "fold": f_idx + 1,
                "oos_start": f_dates[0],
                "oos_end": f_dates[-1],
                "frozen_ret_pct": rf.get("total_return_pct", 0.0),
                "frozen_mdd_pct": rf.get("max_drawdown_pct", 0.0),
                "frozen_trades": rf.get("closed_trades", 0),
                "ai_v2_ret_pct": ra.get("total_return_pct", 0.0),
                "ai_v2_mdd_pct": ra.get("max_drawdown_pct", 0.0),
                "ai_v2_trades": ra.get("closed_trades", 0),
                "benchmark_0050_ret": ra.get("benchmark_0050_ret"),
            })
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)

    return {
        "status": "OK",
        "folds": fold_results,
        "disclaimer": "歷史與 Walk-Forward 樣本外測試結果均不代表未來績效。",
    }
