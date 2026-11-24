"""
CLI / GitHub Actions Entrypoint for Automated Daily Execution.
"""
import os
import sys
import config
from database import LedgerDB
from data_provider import MarketDataProvider
from paper_engine import PaperTradingEngine


def run_live_scan(top_n: int = 50, progress_callback=None):
    token = os.environ.get("FINMIND_TOKEN")
    provider = MarketDataProvider(finmind_token=token)
    db = LedgerDB(config.DB_PATH)
    engine = PaperTradingEngine(db)

    bm_df, _, _ = provider.fetch_history("^TWII", market="", lookback_days=200)
    if bm_df is None or bm_df.empty:
        return {"status": "ERROR", "message": "無法取得台灣加權指數 (^TWII) 行情，請檢查網路。"}

    latest_date = str(bm_df.index[-1])
    universe = provider.fetch_dynamic_tw_universe(top_n=top_n)
    market_data = {}
    total = len(universe)

    for idx, (sym, name, market) in enumerate(universe):
        if progress_callback:
            progress_callback((idx + 1) / total, f"掃描中 ({idx+1}/{total})：{sym} {name}")
        df, src, _ = provider.fetch_history(sym, market=market, lookback_days=200)
        if df is not None and not df.empty and latest_date in df.index:
            market_data[sym] = (name, df, src)

    result = engine.run_daily_cycle(latest_date, market_data, benchmark_df=bm_df)
    return {"result": result, "market_data": market_data, "benchmark_df": bm_df, "latest_date": latest_date}


def main():
    out = run_live_scan(top_n=50)
    print(out.get("result", out))
    if out.get("status") == "ERROR":
        sys.exit(1)


if __name__ == "__main__":
    main()
