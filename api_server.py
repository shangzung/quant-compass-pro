"""
Quant Compass AI Ultimate — Phase 2/3 FastAPI Backend Foundation
Exposes read-only REST APIs reusing the exact same LedgerDB & Reporter without touching trading logic.
Run: uvicorn api_server:app --reload --port 8000
"""
from fastapi import FastAPI
import config
from database import LedgerDB
from reporter import generate_performance_report

app = FastAPI(title="Quant Compass AI Ultimate API", version="2.1.0")
db = LedgerDB(config.DB_PATH)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "2.1.0",
        "frozen_hash_valid": db.verify_hash_chain(config.STRATEGY_FROZEN)["valid"],
        "ai_v2_hash_valid": db.verify_hash_chain(config.STRATEGY_AI_V2)["valid"],
    }


@app.get("/api/portfolio/{strategy_version}")
def get_portfolio(strategy_version: str = config.STRATEGY_AI_V2):
    return {
        "report": generate_performance_report(db, strategy_version),
        "open_trades": db.get_open_trades(strategy_version),
        "snapshots": db.get_all_snapshots(strategy_version),
    }


@app.get("/api/signals/{strategy_version}")
def get_signals(strategy_version: str = config.STRATEGY_AI_V2):
    latest = db.get_latest_snapshot(strategy_version)
    if not latest:
        return {"date": None, "signals": []}
    return {"date": latest["date"], "signals": db.get_signals(strategy_version, date_str=latest["date"])}
