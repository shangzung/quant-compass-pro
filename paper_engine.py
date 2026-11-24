"""
Quant Compass AI Ultimate V2.0 — Multi-Strategy Paper Trading Engine.
Executes QC-PT-1.0-FROZEN and QC-AI-2.0 independently on the same causal market data,
tracks immutable AI prediction outcomes (5d/10d/20d), and syncs JSON & SQLite ledgers.
"""
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import pandas as pd
import pytz

import config
from database import LedgerDB
from data_provider import check_stock_data_quality
from indicators import compute_indicators, compute_market_temperature
from risk_manager import calculate_buy_cost, calculate_position_size, calculate_sell_cost
from strategy import check_exit_conditions, evaluate_ai_v2, evaluate_frozen_v1


class PaperTradingEngine:
    def __init__(self, db: LedgerDB):
        self.db = db
        self.tz = pytz.timezone(config.TIMEZONE)

    def _now_str(self) -> str:
        return datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S")

    def _get_state(self, strategy_version: str) -> Tuple[float, float, float]:
        snap = self.db.get_latest_snapshot(strategy_version)
        if not snap:
            return config.INITIAL_CAPITAL, 0.0, config.INITIAL_CAPITAL
        snaps = self.db.get_all_snapshots(strategy_version)
        peak = max(s["total_equity"] for s in snaps)
        return snap["cash"], snap["realized_pnl"], max(peak, config.INITIAL_CAPITAL)

    def _update_prediction_outcomes(
        self, trade_date: str, enriched: Dict[str, Tuple[str, str, pd.DataFrame, str]]
    ) -> None:
        preds = self.db.get_all_predictions()
        for p in preds:
            if p["outcome_status"] == "COMPLETED" or p["date"] >= trade_date:
                continue
            sym = p["symbol"]
            if sym not in enriched:
                continue
            _, _, df, _ = enriched[sym]
            after = df.loc[df.index > p["date"]]
            if after.empty:
                continue
            rec_p = float(p["rec_price"])
            ret_5d = round((float(after.iloc[4]["Close"]) / rec_p - 1.0) * 100.0, 2) if len(after) >= 5 else p["ret_5d"]
            ret_10d = round((float(after.iloc[9]["Close"]) / rec_p - 1.0) * 100.0, 2) if len(after) >= 10 else p["ret_10d"]
            ret_20d = round((float(after.iloc[19]["Close"]) / rec_p - 1.0) * 100.0, 2) if len(after) >= 20 else p["ret_20d"]
            window = after.iloc[:20]
            hit_sl = 1 if (window["Low"] <= float(p["stop_loss"])).any() else 0
            hit_tp = 1 if (window["High"] >= float(p["take_profit"])).any() else 0
            status = "COMPLETED" if len(after) >= 20 else "TRACKING"
            self.db.update_prediction_outcomes(p["pred_id"], ret_5d, ret_10d, ret_20d, hit_sl, hit_tp, status)

    def run_strategy_cycle(
        self,
        strategy_version: str,
        trade_date: str,
        market_data: Dict[str, Tuple[str, str, pd.DataFrame, str]],
        benchmark_df: Optional[pd.DataFrame] = None,
        benchmark_0050_df: Optional[pd.DataFrame] = None,
        fundamentals_map: Optional[Dict[str, Dict[str, Any]]] = None,
        chips_map: Optional[Dict[str, Dict[str, Any]]] = None,
        total_universe_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        market_data: {symbol: (name, sector, df, data_source)}
        """
        if self.db.has_snapshot_for_date(trade_date, strategy_version):
            return {"status": "SKIPPED", "strategy": strategy_version, "message": f"{trade_date} 已執行過"}

        cash, realized_pnl, peak_equity = self._get_state(strategy_version)
        now_str = self._now_str()
        fundamentals_map = fundamentals_map or {}
        chips_map = chips_map or {}

        market_temp = compute_market_temperature(benchmark_df, trade_date)
        bm_sliced = benchmark_df.loc[benchmark_df.index <= trade_date].copy() if (benchmark_df is not None and not benchmark_df.empty) else None

        bm_0050_close = None
        if benchmark_0050_df is not None and not benchmark_0050_df.empty:
            s0050 = benchmark_0050_df.loc[benchmark_0050_df.index <= trade_date]
            if not s0050.empty:
                bm_0050_close = float(s0050.iloc[-1]["Close"])

        enriched: Dict[str, Tuple[str, str, pd.DataFrame, str]] = {}
        failed_count = 0
        for sym, (name, sector, raw_df, src) in market_data.items():
            df_sliced = raw_df.loc[raw_df.index <= trade_date].copy()
            ok, _ = check_stock_data_quality(df_sliced, trade_date)
            if not ok:
                failed_count += 1
                continue
            enriched[sym] = (name, sector, compute_indicators(df_sliced, bm_sliced), src)

        denom = total_universe_count or max(len(market_data), 1)
        coverage_pct = round(len(enriched) / denom * 100.0, 1)

        if not enriched:
            self.db.insert_execution_log(
                now_str, trade_date, strategy_version, "FAILED", 0, failed_count, 0.0,
                "無有效行情資料", "NONE"
            )
            return {"status": "FAILED", "strategy": strategy_version, "message": "無有效行情資料"}

        # 1. Check Exits for OPEN trades
        for tr in self.db.get_open_trades(strategy_version):
            sym = tr["symbol"]
            if sym not in enriched:
                continue
            _, _, df, _ = enriched[sym]
            today_bar = df.iloc[-1]
            prev_bar = df.iloc[-2] if len(df) >= 2 else None
            holding_days = int((df.index > tr["buy_date"]).sum())
            should_exit, exec_price, reason = check_exit_conditions(tr, today_bar, prev_bar, holding_days)
            if should_exit and exec_price is not None:
                sell_cost = calculate_sell_cost(exec_price, tr["shares"])
                net_proceeds = exec_price * tr["shares"] - sell_cost
                net_pnl = round(net_proceeds - (tr["capital_used"] + tr["buy_cost"]), 2)
                ret_pct = round((net_pnl / (tr["capital_used"] + tr["buy_cost"])) * 100.0, 2)
                self.db.close_trade(
                    tr["trade_id"], trade_date, exec_price, sell_cost,
                    net_pnl, ret_pct, holding_days, reason
                )
                cash += net_proceeds
                realized_pnl += net_pnl

        # 2. Execute Pending BUY Signals from Previous Trading Day at Today's Open
        pending = self.db.get_pending_buy_signals(before_date=trade_date, strategy_version=strategy_version)
        current_open = self.db.get_open_trades(strategy_version)
        held_symbols = {t["symbol"] for t in current_open}

        for sig in pending:
            sym = sig["symbol"]
            if len(current_open) >= config.MAX_POSITIONS:
                self.db.update_signal_status(sig["signal_id"], "CANCELLED_MAX_POS")
                continue
            if sym in held_symbols:
                self.db.update_signal_status(sig["signal_id"], "CANCELLED_DUPLICATE")
                continue
            if sym not in enriched:
                self.db.update_signal_status(sig["signal_id"], "CANCELLED_NO_DATA")
                continue

            _, sector, df, _ = enriched[sym]
            today_open = float(df.iloc[-1]["Open"])
            if today_open > float(sig["signal_price"]) * (1.0 + config.MAX_OPEN_CHASE_PCT):
                self.db.update_signal_status(sig["signal_id"], "CANCELLED_CHASE_LIMIT")
                continue

            atr = float(sig["atr"])
            stop_loss = round(today_open - config.STOP_LOSS_ATR_MULT * atr, 2)
            take_profit = round(today_open + config.TAKE_PROFIT_ATR_MULT * atr, 2)

            mv_temp = sum(
                float(enriched[t["symbol"]][2].iloc[-1]["Close"]) * t["shares"]
                if t["symbol"] in enriched else t["capital_used"]
                for t in current_open
            )
            sizing = calculate_position_size(cash + mv_temp, cash, today_open, stop_loss)
            shares = int(sizing["shares"])
            if shares <= 0:
                self.db.update_signal_status(sig["signal_id"], "CANCELLED_NO_CASH")
                continue

            buy_cost = calculate_buy_cost(today_open, shares)
            total_outflow = sizing["capital_used"] + buy_cost
            if total_outflow > cash:
                self.db.update_signal_status(sig["signal_id"], "CANCELLED_NO_CASH")
                continue

            rr = round((take_profit - today_open) / (today_open - stop_loss), 2)
            self.db.insert_trade({
                "signal_id": sig["signal_id"], "symbol": sym, "name": sig["name"], "sector": sector,
                "buy_date": trade_date, "buy_price": today_open, "shares": shares,
                "stop_loss": stop_loss, "take_profit": take_profit,
                "capital_used": sizing["capital_used"], "max_estimated_loss": sizing["max_loss"],
                "estimated_rr": rr, "ai_score": sig.get("quality_score", 0.0),
                "market_env": f"{market_temp['state']} ({market_temp['temp']:.0f}分)",
                "buy_reason": sig["reason"], "buy_cost": buy_cost,
                "strategy_version": strategy_version, "created_at": now_str,
            })
            self.db.update_signal_status(sig["signal_id"], "EXECUTED")
            cash -= total_outflow
            held_symbols.add(sym)
            current_open = self.db.get_open_trades(strategy_version)

        # 3. EOD Mark-to-Market & Generate New Signals
        open_eod = self.db.get_open_trades(strategy_version)
        held_eod = {t["symbol"] for t in open_eod}
        market_value, unrealized_pnl = 0.0, 0.0
        for tr in open_eod:
            sym = tr["symbol"]
            last_close = float(enriched[sym][2].iloc[-1]["Close"]) if sym in enriched else tr["buy_price"]
            mv = last_close * tr["shares"]
            market_value += mv
            unrealized_pnl += (mv - tr["capital_used"] - tr["buy_cost"])

        total_equity = round(cash + market_value, 2)

        for sym, (name, sector, df, src) in enriched.items():
            if self.db.has_signal_for_date_symbol(trade_date, sym, strategy_version):
                continue

            if strategy_version == config.STRATEGY_FROZEN:
                res = evaluate_frozen_v1(df, sym, name, total_equity, cash)
            else:
                res = evaluate_ai_v2(
                    df, sym, name, market_temp,
                    fundamentals=fundamentals_map.get(sym),
                    chips=chips_map.get(sym),
                    total_equity=total_equity, available_cash=cash,
                )

            decision = "HOLD" if sym in held_eod else res["decision"]
            light = res["traffic_light"]

            self.db.insert_signal({
                "date": trade_date, "symbol": sym, "name": name, "sector": sector,
                "signal_type": decision, "traffic_light": light,
                "signal_price": res.get("signal_price", float(df.iloc[-1]["Close"])),
                "quality_score": res.get("quality_score", 0.0),
                "quality_grade": res.get("quality_grade", "N/A"),
                "signal_strength": res.get("signal_strength", 0.0),
                "data_confidence": res.get("data_confidence", 0.0),
                "rs_20": res.get("rs_20", 0.0),
                "ma20": res.get("ma20"), "ma60": res.get("ma60"),
                "rsi": res.get("rsi"), "atr": res.get("atr"), "volume": res.get("volume"),
                "suggested_shares": res.get("suggested_shares", 0),
                "stop_loss": res.get("stop_loss"), "take_profit": res.get("take_profit"),
                "take_profit_2": res.get("take_profit_2"), "rr_ratio": res.get("rr_ratio"),
                "reason": res["reason"], "missing_condition": res.get("missing_condition", ""),
                "scores": res.get("scores", {}), "plan": res.get("plan", {}),
                "status": "PENDING" if decision == "BUY" else "INFO",
                "strategy_version": strategy_version, "data_source": src, "created_at": now_str,
            })

            # Record immutable AI prediction whenever BUY (Green Light) is generated
            if decision == "BUY" and res.get("stop_loss") and res.get("take_profit"):
                self.db.insert_prediction({
                    "date": trade_date, "symbol": sym, "name": name,
                    "strategy_version": strategy_version,
                    "rec_price": res["signal_price"],
                    "ai_quality_score": res.get("quality_score", 0.0),
                    "ai_grade": res.get("quality_grade", "N/A"),
                    "signal_strength": res.get("signal_strength", 0.0),
                    "data_confidence": res.get("data_confidence", 0.0),
                    "stop_loss": res["stop_loss"], "take_profit": res["take_profit"],
                    "market_regime": f"{market_temp['state']} ({market_temp['temp']:.0f})",
                    "created_at": now_str,
                })

        # Update prediction verification outcomes
        self._update_prediction_outcomes(trade_date, enriched)

        # 4. Save Snapshot & Hash
        peak_equity = max(peak_equity, total_equity)
        mdd_pct = round(((total_equity - peak_equity) / peak_equity) * 100.0, 2)
        prev_snaps = self.db.get_all_snapshots(strategy_version)
        worst_mdd = min([mdd_pct] + [s["max_drawdown_pct"] for s in prev_snaps])
        cum_ret_pct = round(((total_equity - config.INITIAL_CAPITAL) / config.INITIAL_CAPITAL) * 100.0, 2)

        ledger_hash = self.db.insert_snapshot({
            "date": trade_date, "strategy_version": strategy_version,
            "cash": round(cash, 2), "market_value": round(market_value, 2),
            "total_equity": total_equity, "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2), "cum_return_pct": cum_ret_pct,
            "max_drawdown_pct": worst_mdd, "market_temp": market_temp["temp"],
            "market_regime": f"{market_temp['state']} ({market_temp['temp']:.0f}分)",
            "benchmark_0050_close": bm_0050_close, "created_at": now_str,
        })

        self.db.insert_execution_log(
            now_str, trade_date, strategy_version, "SUCCESS",
            len(enriched), failed_count, coverage_pct, None, "MULTI"
        )
        return {
            "status": "SUCCESS", "strategy": strategy_version, "date": trade_date,
            "total_equity": total_equity, "market_temp": market_temp,
            "scanned": len(enriched), "failed": failed_count,
            "coverage_pct": coverage_pct, "ledger_hash": ledger_hash,
        }

    def run_all_strategies(
        self,
        trade_date: str,
        market_data: Dict[str, Tuple[str, str, pd.DataFrame, str]],
        benchmark_df: Optional[pd.DataFrame] = None,
        benchmark_0050_df: Optional[pd.DataFrame] = None,
        fundamentals_map: Optional[Dict[str, Dict[str, Any]]] = None,
        chips_map: Optional[Dict[str, Dict[str, Any]]] = None,
        total_universe_count: Optional[int] = None,
        export_json: bool = True,
    ) -> Dict[str, Any]:
        res_frozen = self.run_strategy_cycle(
            config.STRATEGY_FROZEN, trade_date, market_data,
            benchmark_df, benchmark_0050_df, fundamentals_map, chips_map, total_universe_count
        )
        res_ai = self.run_strategy_cycle(
            config.STRATEGY_AI_V2, trade_date, market_data,
            benchmark_df, benchmark_0050_df, fundamentals_map, chips_map, total_universe_count
        )
        json_path = self.db.export_json_ledger() if export_json else None
        return {"frozen": res_frozen, "ai_v2": res_ai, "json_ledger": json_path}
