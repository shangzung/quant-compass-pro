"""
SQLite Append-Only Ledger with SHA-256 Integrity Hashing (Windows-Safe).
"""
from contextlib import contextmanager
import hashlib
import json
import sqlite3
from typing import Any, Dict, Iterator, List, Optional

import config


class LedgerDB:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self._init_db()

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
                    signal_type TEXT NOT NULL,
                    signal_price REAL NOT NULL,
                    strength_score REAL DEFAULT 0.0,
                    rs_20 REAL DEFAULT 0.0,
                    ma20 REAL,
                    ma60 REAL,
                    rsi REAL,
                    atr REAL,
                    volume REAL,
                    suggested_shares INTEGER DEFAULT 0,
                    stop_loss REAL,
                    take_profit REAL,
                    rr_ratio REAL,
                    reason TEXT NOT NULL,
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
                    buy_date TEXT NOT NULL,
                    buy_price REAL NOT NULL,
                    shares INTEGER NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    capital_used REAL NOT NULL,
                    max_estimated_loss REAL NOT NULL,
                    estimated_rr REAL NOT NULL,
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
                    date TEXT NOT NULL UNIQUE,
                    cash REAL NOT NULL,
                    market_value REAL NOT NULL,
                    total_equity REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    cum_return_pct REAL NOT NULL,
                    max_drawdown_pct REAL NOT NULL,
                    market_regime TEXT DEFAULT 'UNKNOWN',
                    ledger_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS execution_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exec_time TEXT NOT NULL,
                    data_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    processed_count INTEGER NOT NULL,
                    error_message TEXT,
                    data_source TEXT NOT NULL,
                    strategy_version TEXT NOT NULL
                )
            """)

    def insert_signal(self, data: Dict[str, Any]) -> int:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO trade_signals (
                    date, symbol, name, signal_type, signal_price, strength_score, rs_20,
                    ma20, ma60, rsi, atr, volume, suggested_shares, stop_loss, take_profit,
                    rr_ratio, reason, status, strategy_version, data_source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["date"], data["symbol"], data["name"], data["signal_type"],
                data["signal_price"], data.get("strength_score", 0.0), data.get("rs_20", 0.0),
                data.get("ma20"), data.get("ma60"), data.get("rsi"), data.get("atr"),
                data.get("volume"), data.get("suggested_shares", 0), data.get("stop_loss"),
                data.get("take_profit"), data.get("rr_ratio"), data["reason"],
                data.get("status", "PENDING"), data["strategy_version"],
                data["data_source"], data["created_at"]
            ))
            return cur.lastrowid

    def update_signal_status(self, signal_id: int, new_status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE trade_signals SET status = ? WHERE signal_id = ?",
                (new_status, signal_id)
            )

    def get_pending_buy_signals(self, before_date: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM trade_signals
                WHERE signal_type = 'BUY' AND status = 'PENDING' AND date < ?
                ORDER BY date ASC, strength_score DESC, signal_id ASC
            """, (before_date,)).fetchall()
            return [dict(r) for r in rows]

    def has_signal_for_date_symbol(self, date_str: str, symbol: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM trade_signals WHERE date = ? AND symbol = ?",
                (date_str, symbol)
            ).fetchone()
            return row is not None

    def insert_trade(self, data: Dict[str, Any]) -> int:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO trades (
                    signal_id, symbol, name, buy_date, buy_price, shares,
                    stop_loss, take_profit, capital_used, max_estimated_loss,
                    estimated_rr, buy_cost, total_cost, status, strategy_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            """, (
                data.get("signal_id"), data["symbol"], data["name"],
                data["buy_date"], data["buy_price"], data["shares"],
                data["stop_loss"], data["take_profit"], data["capital_used"],
                data["max_estimated_loss"], data["estimated_rr"],
                data["buy_cost"], data["buy_cost"], data["strategy_version"],
                data["created_at"]
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

    def get_open_trades(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY buy_date ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_trades(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY trade_id DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_signals(self, date_str: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if date_str:
                rows = conn.execute(
                    "SELECT * FROM trade_signals WHERE date = ? ORDER BY strength_score DESC, signal_id DESC",
                    (date_str,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trade_signals ORDER BY date DESC, strength_score DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY date DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def get_all_snapshots(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY date ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def has_snapshot_for_date(self, date_str: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM portfolio_snapshots WHERE date = ?", (date_str,)
            ).fetchone()
            return row is not None

    def insert_snapshot(self, data: Dict[str, Any]) -> str:
        prev = self.get_latest_snapshot()
        prev_hash = prev["ledger_hash"] if prev else "GENESIS"
        payload = {
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
                    date, cash, market_value, total_equity, realized_pnl,
                    unrealized_pnl, cum_return_pct, max_drawdown_pct,
                    market_regime, ledger_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data["date"], data["cash"], data["market_value"],
                data["total_equity"], data["realized_pnl"], data["unrealized_pnl"],
                data["cum_return_pct"], data["max_drawdown_pct"],
                data.get("market_regime", "UNKNOWN"), ledger_hash, data["created_at"]
            ))
        return ledger_hash

    def insert_execution_log(
        self, exec_time: str, data_date: str, status: str,
        processed_count: int, error_message: Optional[str],
        data_source: str, strategy_version: str
    ) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO execution_logs (
                    exec_time, data_date, status, processed_count,
                    error_message, data_source, strategy_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                exec_time, data_date, status, processed_count,
                error_message, data_source, strategy_version
            ))

    def get_execution_logs(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_logs ORDER BY log_id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
