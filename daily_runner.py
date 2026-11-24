"""
Daily Live Scan & Dual-Strategy Paper Trading Runner (V2.1.1 Fixed).
- Concurrent batch fetching via ThreadPoolExecutor
- Accurate progress milestones (never shows 100% before SQLite & JSON writes succeed)
- Unified error handling with full traceback logged to `quant_compass_errors.log`
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import os
import sys
from typing import Any, Callable, Dict, Optional
import pytz

import config
from database import LedgerDB
from data_provider import MarketDataProvider
from error_handler import log_exception, log_info
from paper_engine import PaperTradingEngine


def run_live_scan(
    top_n: int = 35,
    fetch_extra_factors: bool = False,
    progress_callback: Optional[Callable[[float, str, str, int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    stage = "初始化系統與資料庫"
    try:
        token = os.environ.get("FINMIND_TOKEN")
        provider = MarketDataProvider(finmind_token=token)
        db = LedgerDB(config.DB_PATH)
        engine = PaperTradingEngine(db)
        tz = pytz.timezone(config.TIMEZONE)
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

        stage = "取得大盤基準行情 (^TWII & 0050)"
        if progress_callback:
            progress_callback(0.05, "正在取得市場資料", "台灣加權指數 (^TWII) & 0050", 0, top_n)

        bm_df, bm_src, _ = provider.fetch_history("^TWII", market="", lookback_days=240)
        if bm_df is None or bm_df.empty:
            return {"status": "ERROR", "stage": stage, "message": "無法取得台灣加權指數 (^TWII) 行情，請檢查網路或 API 連線。", "traceback": ""}
        latest_date = str(bm_df.index[-1])

        bm_0050_df, _, _ = provider.fetch_history("0050", market="TW", lookback_days=240)
        universe, univ_src = provider.fetch_dynamic_tw_universe(top_n=top_n)
        total = len(universe)

        market_data: Dict[str, Any] = {}
        fundamentals_map: Dict[str, Dict[str, Any]] = {}
        chips_map: Dict[str, Dict[str, Any]] = {}

        def _fetch_one(item):
            sym, name, market, sector = item
            df, src, _ = provider.fetch_history(sym, market=market, lookback_days=240)
            fund = provider.fetch_fundamentals(sym, market=market) if (fetch_extra_factors and df is not None) else {}
            chip = provider.fetch_institutional_chips(sym) if (fetch_extra_factors and df is not None) else {}
            return sym, name, market, sector, df, src, fund, chip

        stage = "批次掃描台股行情"
        completed = 0
        cancelled = False
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(_fetch_one, item): item for item in universe}
            for fut in as_completed(futures):
                if cancel_check and cancel_check():
                    cancelled = True
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                completed += 1
                try:
                    sym, name, market, sector, df, src, fund, chip = fut.result(timeout=20)
                    st_lbl = "正在分析上市股票" if market == "TW" else "正在分析上櫃股票"
                    if progress_callback:
                        pct = 0.08 + 0.67 * (completed / max(total, 1))
                        progress_callback(pct, st_lbl, f"{sym} {name}", completed, total)
                    if df is not None and not df.empty:
                        market_data[sym] = (name, sector, df, src)
                        if fetch_extra_factors:
                            fundamentals_map[sym] = fund
                            chips_map[sym] = chip
                except Exception:
                    continue

        if cancelled:
            log_info(f"Scan cancelled by user at {completed}/{total}.")
            return {"status": "CANCELLED", "stage": stage, "message": f"使用者已取消掃描（已完成 {completed}/{total} 檔，未寫入不完整帳本）。"}

        if not market_data:
            return {"status": "ERROR", "stage": stage, "message": "未成功取得任何有效個股行情資料，暫停更新帳本。", "traceback": ""}

        stage = "記錄資料品質並執行雙策略模擬"
        if progress_callback:
            progress_callback(0.80, "正在計算 AI 評分與產生交易計畫", "雙策略引擎運算中", len(market_data), total)

        coverage = round(len(market_data) / max(total, 1) * 100.0, 1)
        db.insert_data_quality_log(
            latest_date, "台股日線行情", f"{univ_src} / yfinance+FinMind",
            "OK" if coverage >= 70 else "DEGRADED", coverage,
            f"成功 {len(market_data)} / {total} 檔（加權指數來源：{bm_src}）", now_str
        )

        stage = "寫入 SQLite 帳本與匯出 JSON"
        if progress_callback:
            progress_callback(0.90, "正在更新模擬交易帳本", "寫入 SQLite & JSON 帳本", len(market_data), total)

        out = engine.run_all_strategies(
            latest_date, market_data, benchmark_df=bm_df, benchmark_0050_df=bm_0050_df,
            fundamentals_map=fundamentals_map, chips_map=chips_map,
            total_universe_count=total, export_json=True
        )

        # Real market breadth from scanned stocks
        advancers, decliners = 0, 0
        for sym, (_, _, df, _) in market_data.items():
            if len(df) >= 2:
                chg = float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2])
                if chg > 0:
                    advancers += 1
                elif chg < 0:
                    decliners += 1

        taiex_close = float(bm_df["Close"].iloc[-1])
        taiex_prev = float(bm_df["Close"].iloc[-2]) if len(bm_df) >= 2 else taiex_close
        taiex_chg = round(taiex_close - taiex_prev, 2)
        taiex_chg_pct = round((taiex_chg / taiex_prev * 100.0), 2) if taiex_prev > 0 else 0.0

        # Only report 100% AFTER SQLite & JSON writes have succeeded
        if progress_callback:
            progress_callback(1.0, "完成", "所有分析、SQLite 與 JSON 帳本已成功保存", len(market_data), total)

        log_info(f"Scan succeeded for {latest_date}: {len(market_data)}/{total} stocks.")
        return {
            "status": "OK",
            "latest_date": latest_date,
            "updated_at": now_str,
            "coverage_pct": coverage,
            "taiex": {"close": taiex_close, "chg": taiex_chg, "chg_pct": taiex_chg_pct},
            "breadth": {"advancers": advancers, "decliners": decliners, "total": len(market_data)},
            "result": out,
            "market_data": market_data,
            "benchmark_df": bm_df,
            "benchmark_0050_df": bm_0050_df,
            "fundamentals_map": fundamentals_map,
            "chips_map": chips_map,
        }
    except Exception as exc:
        summary, tb = log_exception(stage, exc)
        return {"status": "ERROR", "stage": stage, "message": summary, "traceback": tb}


def main():
    out = run_live_scan(top_n=35, fetch_extra_factors=False)
    print(out.get("result", out))
    if out.get("status") == "ERROR":
        sys.exit(1)


if __name__ == "__main__":
    main()
