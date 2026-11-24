"""
SQLite Append-Only Ledger (Multi-Strategy Isolated) + SHA-256 Integrity + JSON Ledger Sync.
Supports both QC-PT-1.0-FROZEN and QC-AI-2.0 independently without overwriting history.
"""
from contextlib import contextmanager
import hashlib
import json
import os
import sqlite3
from typing import Any, Dict, Iterator, List, Optional

import config


class LedgerDB:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self._init_db()
        self._migrate_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trade_signals (
                    signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    sector TEXT DEFAULT '其他',
                    signal_type TEXT NOT NULL,
                    traffic_light TEXT DEFAULT 'WAIT',
                    signal_price REAL NOT NULL,
                    quality_score REAL DEFAULT 0.0,
                    quality_grade TEXT DEFAULT 'N/A',
                    signal_strength REAL DEFAULT 0.0,
                    data_confidence REAL DEFAULT 0.0,
                    rs_20 REAL DEFAULT 0.0,
                    ma20 REAL,
                    ma60 REAL,
                    rsi REAL,
                    atr REAL,
                    volume REAL,
                    suggested_shares INTEGER DEFAULT 0,
                    stop_loss REAL,
                    take_profit REAL,
                    take_profit_2 REAL,
                    rr_ratio REAL,
                    reason TEXT NOT NULL,
                    missing_condition TEXT DEFAULT '',
                    scores_json TEXT DEFAULT '{}',
                    plan_json TEXT DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    strategy_version TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    sector TEXT DEFAULT '其他',
                    buy_date TEXT NOT NULL,
                    buy_price REAL NOT NULL,
                    shares INTEGER NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    capital_used REAL NOT NULL,
                    max_estimated_loss REAL NOT NULL,
                    estimated_rr REAL NOT NULL,
                    ai_score REAL DEFAULT 0.0,
                    market_env TEXT DEFAULT '',
                    buy_reason TEXT DEFAULT '',
                    sell_date TEXT,
                    sell_price REAL,
                    buy_cost REAL NOT NULL,
                    sell_cost REAL DEFAULT 0.0,
                    total_cost REAL NOT NULL,
                    net_pnl REAL DEFAULT 0.0,
                    return_pct REAL DEFAULT 0.0,
                    holding_days INTEGER DEFAULT 0,
                    exit_reason TEXT,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    strategy_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    cash REAL NOT NULL,
                    market_value REAL NOT NULL,
                    total_equity REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    cum_return_pct REAL NOT NULL,
                    max_drawdown_pct REAL NOT NULL,
                    market_temp REAL DEFAULT 50.0,
                    market_regime TEXT DEFAULT 'UNKNOWN',
                    benchmark_0050_close REAL,
                    ledger_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(date, strategy_version)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_predictions (
                    pred_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    rec_price REAL NOT NULL,
                    ai_quality_score REAL NOT NULL,
                    ai_grade TEXT NOT NULL,
                    signal_strength REAL NOT NULL,
                    data_confidence REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    direction TEXT NOT NULL DEFAULT 'LONG',
                    horizon_days INTEGER NOT NULL DEFAULT 20,
                    market_regime TEXT DEFAULT '',
                    ret_5d REAL,
                    ret_10d REAL,
                    ret_20d REAL,
                    hit_sl INTEGER DEFAULT 0,
                    hit_tp INTEGER DEFAULT 0,
                    outcome_status TEXT DEFAULT 'TRACKING',
                    created_at TEXT NOT NULL,
                    UNIQUE(date, symbol, strategy_version)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exec_time TEXT NOT NULL,
                    data_date TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    processed_count INTEGER NOT NULL DEFAULT 0,
                    scanned_count INTEGER NOT NULL DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    coverage_pct REAL DEFAULT 0.0,
                    error_message TEXT,
                    data_source TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS data_quality_logs (
                    dq_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    module_name TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    completeness_pct REAL NOT NULL,
                    details TEXT,
                    updated_at TEXT NOT NULL
                )
            """)


    def _migrate_schema(self) -> None:
        """
        Safe, non-destructive automatic schema migration for legacy SQLite DBs.
        Fixes `sqlite3.OperationalError: no such column: strategy_version` when upgrading
        from Quant Compass Pro v1/v2 without losing any historical records.
        """
        with self._connect() as conn:
            cur = conn.cursor()
            # 1. Check portfolio_snapshots
            cols = {r["name"] for r in cur.execute("PRAGMA table_info(portfolio_snapshots)").fetchall()}
            if cols and "strategy_version" not in cols:
                # Rebuild table to support UNIQUE(date, strategy_version) while preserving all legacy rows
                cur.execute("ALTER TABLE portfolio_snapshots RENAME TO portfolio_snapshots_legacy")
                cur.execute("""
                    CREATE TABLE portfolio_snapshots (
                        snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        strategy_version TEXT NOT NULL,
                        cash REAL NOT NULL,
                        market_value REAL NOT NULL,
                        total_equity REAL NOT NULL,
                        realized_pnl REAL NOT NULL,
                        unrealized_pnl REAL NOT NULL,
                        cum_return_pct REAL NOT NULL,
                        max_drawdown_pct REAL NOT NULL,
                        market_temp REAL DEFAULT 50.0,
                        market_regime TEXT DEFAULT 'UNKNOWN',
                        benchmark_0050_close REAL,
                        ledger_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(date, strategy_version)
                    )
                """)
                has_regime = "market_regime" in cols
                regime_expr = "market_regime" if has_regime else "'UNKNOWN'"
                cur.execute(f"""
                    INSERT INTO portfolio_snapshots (
                        date, strategy_version, cash, market_value, total_equity,
                        realized_pnl, unrealized_pnl, cum_return_pct, max_drawdown_pct,
                        market_temp, market_regime, ledger_hash, created_at
                    )
                    SELECT
                        date, '{config.STRATEGY_FROZEN}', cash, market_value, total_equity,
                        realized_pnl, unrealized_pnl, cum_return_pct, max_drawdown_pct,
                        50.0, {regime_expr}, ledger_hash, created_at
                    FROM portfolio_snapshots_legacy
                """)
                cur.execute("DROP TABLE portfolio_snapshots_legacy")

            # 2. Safely add any missing columns to trade_signals, trades, execution_logs
            table_migrations = {
                "trade_signals": [
                    ("sector", "TEXT DEFAULT '其他'"),
                    ("traffic_light", "TEXT DEFAULT '黃燈'"),
                    ("quality_score", "REAL DEFAULT 0.0"),
                    ("quality_grade", "TEXT DEFAULT 'N/A'"),
                    ("signal_strength", "REAL DEFAULT 0.0"),
                    ("data_confidence", "REAL DEFAULT 0.0"),
                    ("rs_20", "REAL DEFAULT 0.0"),
                    ("take_profit_2", "REAL"),
                    ("missing_condition", "TEXT DEFAULT ''"),
                    ("scores_json", "TEXT DEFAULT '{}'"),
                    ("plan_json", "TEXT DEFAULT '{}'"),
                    ("strategy_version", f"TEXT NOT NULL DEFAULT '{config.STRATEGY_FROZEN}'"),
                ],
                "trades": [
                    ("sector", "TEXT DEFAULT '其他'"),
                    ("ai_score", "REAL DEFAULT 0.0"),
                    ("market_env", "TEXT DEFAULT ''"),
                    ("buy_reason", "TEXT DEFAULT ''"),
                    ("strategy_version", f"TEXT NOT NULL DEFAULT '{config.STRATEGY_FROZEN}'"),
                ],
                "execution_logs": [
                    ("strategy_version", f"TEXT NOT NULL DEFAULT '{config.STRATEGY_FROZEN}'"),
                    ("processed_count", "INTEGER NOT NULL DEFAULT 0"),
                    ("scanned_count", "INTEGER NOT NULL DEFAULT 0"),
                    ("failed_count", "INTEGER DEFAULT 0"),
                    ("coverage_pct", "REAL DEFAULT 0.0"),
                ],
            }
            for tbl, col_defs in table_migrations.items():
                existing = {r["name"] for r in cur.execute(f"PRAGMA table_info({tbl})").fetchall()}
                if not existing:
                    continue
                for col_name, col_type in col_defs:
                    if col_name not in existing:
                        cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col_name} {col_type}")

    # --- Signals ---
    def insert_signal(self, data: Dict[str, Any]) -> int:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO trade_signals (
                    date, symbol, name, sector, signal_type, traffic_light, signal_price,
                    quality_score, quality_grade, signal_strength, data_confidence, rs_20,
                    ma20, ma60, rsi, atr, volume, suggested_shares, stop_loss, take_profit,
                    take_profit_2, rr_ratio, reason, missing_condition, scores_json,
                    plan_json, status, strategy_version, data_source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["date"], data["symbol"], data["name"], data.get("sector", "其他"),
                data["signal_type"], data.get("traffic_light", "黃燈"), data["signal_price"],
                data.get("quality_score", 0.0), data.get("quality_grade", "N/A"),
                data.get("signal_strength", 0.0), data.get("data_confidence", 0.0),
                data.get("rs_20", 0.0), data.get("ma20"), data.get("ma60"),
                data.get("rsi"), data.get("atr"), data.get("volume"),
                data.get("suggested_shares", 0), data.get("stop_loss"),
                data.get("take_profit"), data.get("take_profit_2"),
                data.get("rr_ratio"), data["reason"], data.get("missing_condition", ""),
                json.dumps(data.get("scores", {}), ensure_ascii=False),
                json.dumps(data.get("plan", {}), ensure_ascii=False),
                data.get("status", "PENDING"), data["strategy_version"],
                data["data_source"], data["created_at"]
            ))
            return cur.lastrowid

    def update_signal_status(self, signal_id: int, new_status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE trade_signals SET status = ? WHERE signal_id = ?", (new_status, signal_id))

    def has_signal_for_date_symbol(self, date_str: str, symbol: str, strategy_version: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM trade_signals WHERE date = ? AND symbol = ? AND strategy_version = ?",
                (date_str, symbol, strategy_version)
            ).fetchone()
            return row is not None

    def get_pending_buy_signals(self, before_date: str, strategy_version: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM trade_signals
                WHERE signal_type = 'BUY' AND status = 'PENDING'
                  AND date < ? AND strategy_version = ?
                ORDER BY date ASC, signal_strength DESC, quality_score DESC, signal_id ASC
            """, (before_date, strategy_version)).fetchall()
            return [dict(r) for r in rows]

    def get_signals(self, strategy_version: str, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if date_str:
                rows = conn.execute("""
                    SELECT * FROM trade_signals
                    WHERE strategy_version = ? AND date = ?
                    ORDER BY signal_strength DESC, quality_score DESC
                """, (strategy_version, date_str)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM trade_signals
                    WHERE strategy_version = ?
                    ORDER BY date DESC, signal_strength DESC
                """, (strategy_version,)).fetchall()
            return [dict(r) for r in rows]

    # --- Trades ---
    def insert_trade(self, data: Dict[str, Any]) -> int:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO trades (
                    signal_id, symbol, name, sector, buy_date, buy_price, shares,
                    stop_loss, take_profit, capital_used, max_estimated_loss,
                    estimated_rr, ai_score, market_env, buy_reason,
                    buy_cost, total_cost, status, strategy_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            """, (
                data.get("signal_id"), data["symbol"], data["name"], data.get("sector", "其他"),
                data["buy_date"], data["buy_price"], data["shares"],
                data["stop_loss"], data["take_profit"], data["capital_used"],
                data["max_estimated_loss"], data["estimated_rr"],
                data.get("ai_score", 0.0), data.get("market_env", ""), data.get("buy_reason", ""),
                data["buy_cost"], data["buy_cost"], data["strategy_version"], data["created_at"]
            ))
            return cur.lastrowid

    def close_trade(
        self, trade_id: int, sell_date: str, sell_price: float,
        sell_cost: float, net_pnl: float, return_pct: float,
        holding_days: int, exit_reason: str
    ) -> None:
        with self._connect() as conn:
            conn.execute("""
                UPDATE trades
                SET sell_date = ?, sell_price = ?, sell_cost = ?,
                    total_cost = buy_cost + ?, net_pnl = ?, return_pct = ?,
                    holding_days = ?, exit_reason = ?, status = 'CLOSED'
                WHERE trade_id = ? AND status = 'OPEN'
            """, (
                sell_date, sell_price, sell_cost, sell_cost,
                net_pnl, return_pct, holding_days, exit_reason, trade_id
            ))

    def get_open_trades(self, strategy_version: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'OPEN' AND strategy_version = ? ORDER BY buy_date ASC",
                (strategy_version,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_trades(self, strategy_version: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE strategy_version = ? ORDER BY trade_id DESC",
                (strategy_version,)
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Snapshots & SHA-256 Chain ---
    def get_latest_snapshot(self, strategy_version: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM portfolio_snapshots WHERE strategy_version = ? ORDER BY date DESC LIMIT 1",
                (strategy_version,)
            ).fetchone()
            return dict(row) if row else None

    def get_all_snapshots(self, strategy_version: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM portfolio_snapshots WHERE strategy_version = ? ORDER BY date ASC",
                (strategy_version,)
            ).fetchall()
            return [dict(r) for r in rows]

    def has_snapshot_for_date(self, date_str: str, strategy_version: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM portfolio_snapshots WHERE date = ? AND strategy_version = ?",
                (date_str, strategy_version)
            ).fetchone()
            return row is not None

    def insert_snapshot(self, data: Dict[str, Any]) -> str:
        strat = data["strategy_version"]
        prev = self.get_latest_snapshot(strat)
        prev_hash = prev["ledger_hash"] if prev else f"GENESIS_{strat}"
        payload = {
            "strategy_version": strat,
            "cash": round(data["cash"], 2),
            "market_value": round(data["market_value"], 2),
            "total_equity": round(data["total_equity"], 2),
            "realized_pnl": round(data["realized_pnl"], 2),
            "unrealized_pnl": round(data["unrealized_pnl"], 2),
        }
        raw = f"{prev_hash}|{data['date']}|{json.dumps(payload, sort_keys=True, ensure_ascii=False)}"
        ledger_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        with self._connect() as conn:
            conn.execute("""
                INSERT INTO portfolio_snapshots (
                    date, strategy_version, cash, market_value, total_equity,
                    realized_pnl, unrealized_pnl, cum_return_pct, max_drawdown_pct,
                    market_temp, market_regime, benchmark_0050_close, ledger_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["date"], strat, data["cash"], data["market_value"],
                data["total_equity"], data["realized_pnl"], data["unrealized_pnl"],
                data["cum_return_pct"], data["max_drawdown_pct"],
                data.get("market_temp", 50.0), data.get("market_regime", "UNKNOWN"),
                data.get("benchmark_0050_close"), ledger_hash, data["created_at"]
            ))
        return ledger_hash

    def verify_hash_chain(self, strategy_version: str) -> Dict[str, Any]:
        snaps = self.get_all_snapshots(strategy_version)
        prev_hash = f"GENESIS_{strategy_version}"
        for s in snaps:
            payload = {
                "strategy_version": strategy_version,
                "cash": round(s["cash"], 2),
                "market_value": round(s["market_value"], 2),
                "total_equity": round(s["total_equity"], 2),
                "realized_pnl": round(s["realized_pnl"], 2),
                "unrealized_pnl": round(s["unrealized_pnl"], 2),
            }
            raw = f"{prev_hash}|{s['date']}|{json.dumps(payload, sort_keys=True, ensure_ascii=False)}"
            expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if expected != s["ledger_hash"]:
                return {"valid": False, "broken_date": s["date"], "checked": len(snaps)}
            prev_hash = expected
        return {"valid": True, "broken_date": None, "checked": len(snaps)}

    # --- Immutable AI Predictions Tracking ---
    def insert_prediction(self, data: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO ai_predictions (
                    date, symbol, name, strategy_version, rec_price,
                    ai_quality_score, ai_grade, signal_strength, data_confidence,
                    stop_loss, take_profit, direction, horizon_days, market_regime, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["date"], data["symbol"], data["name"], data["strategy_version"],
                data["rec_price"], data["ai_quality_score"], data["ai_grade"],
                data["signal_strength"], data["data_confidence"],
                data["stop_loss"], data["take_profit"], data.get("direction", "LONG"),
                data.get("horizon_days", 20), data.get("market_regime", ""), data["created_at"]
            ))

    def update_prediction_outcomes(
        self, pred_id: int, ret_5d: Optional[float], ret_10d: Optional[float],
        ret_20d: Optional[float], hit_sl: int, hit_tp: int, outcome_status: str
    ) -> None:
        # Strictly updates ONLY outcome verification fields, NEVER original prediction values
        with self._connect() as conn:
            conn.execute("""
                UPDATE ai_predictions
                SET ret_5d = ?, ret_10d = ?, ret_20d = ?,
                    hit_sl = ?, hit_tp = ?, outcome_status = ?
                WHERE pred_id = ?
            """, (ret_5d, ret_10d, ret_20d, hit_sl, hit_tp, outcome_status, pred_id))

    def get_all_predictions(self, strategy_version: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if strategy_version:
                rows = conn.execute(
                    "SELECT * FROM ai_predictions WHERE strategy_version = ? ORDER BY date DESC, pred_id DESC",
                    (strategy_version,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ai_predictions ORDER BY date DESC, pred_id DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    # --- Execution & Data Quality Logs ---
    def insert_execution_log(
        self, exec_time: str, data_date: str, strategy_version: str, status: str,
        scanned_count: int, failed_count: int, coverage_pct: float,
        error_message: Optional[str], data_source: str,
        processed_count: Optional[int] = None,
    ) -> None:
        safe_scanned = int(scanned_count) if scanned_count is not None else 0
        safe_processed = int(processed_count) if processed_count is not None else safe_scanned
        safe_failed = int(failed_count) if failed_count is not None else 0
        safe_cov = float(coverage_pct) if coverage_pct is not None else 0.0
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO execution_logs (
                    exec_time, data_date, strategy_version, status,
                    processed_count, scanned_count, failed_count,
                    coverage_pct, error_message, data_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exec_time, data_date, strategy_version, status,
                safe_processed, safe_scanned, safe_failed,
                safe_cov, error_message, data_source
            ))

    def get_execution_logs(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_logs ORDER BY log_id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def insert_data_quality_log(
        self, date_str: str, module_name: str, data_source: str,
        status: str, completeness_pct: float, details: str, updated_at: str
    ) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO data_quality_logs (
                    date, module_name, data_source, status, completeness_pct, details, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (date_str, module_name, data_source, status, completeness_pct, details, updated_at))

    def get_latest_data_quality(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM data_quality_logs ORDER BY dq_id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # --- JSON Paper Ledger Sync (/QuantCompass/quant_compass_paper_ledger.json) ---
    def export_json_ledger(self, json_path: str = config.JSON_LEDGER_PATH) -> str:
        os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
        payload = {"strategies": {}}
        for strat in [config.STRATEGY_FROZEN, config.STRATEGY_AI_V2]:
            snaps = self.get_all_snapshots(strat)
            latest = snaps[-1] if snaps else None
            trades = self.get_all_trades(strat)
            open_pos = self.get_open_trades(strat)
            recent_sigs = self.get_signals(strat, date_str=latest["date"]) if latest else []
            payload["strategies"][strat] = {
                "strategy_version": strat,
                "initial_capital": config.INITIAL_CAPITAL,
                "cash": latest["cash"] if latest else config.INITIAL_CAPITAL,
                "realized_pnl": latest["realized_pnl"] if latest else 0.0,
                "unrealized_pnl": latest["unrealized_pnl"] if latest else 0.0,
                "positions": open_pos,
                "trades": trades,
                "daily_equity": snaps,
                "candidate_checks_latest": recent_sigs[:50],
                "benchmark_0050_series": [
                    {"date": s["date"], "close": s["benchmark_0050_close"]}
                    for s in snaps if s.get("benchmark_0050_close") is not None
                ],
                "hash_verification": self.verify_hash_chain(strat),
            }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return json_path
