"""
Quant Compass Pro v2.0 — Daily Paper Trading Engine.
Prioritizes highest StrengthScore BUY candidates & enforces Market Regime Filter.
"""
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import pandas as pd
import pytz

import config
from database import LedgerDB
from indicators import compute_indicators
from risk_manager import calculate_buy_cost, calculate_position_size, calculate_sell_cost
from strategy import check_exit_conditions, evaluate_entry_signal


class PaperTradingEngine:
    def __init__(self, db: LedgerDB):
        self.db = db
        self.tz = pytz.timezone(config.TIMEZONE)

    def _now_str(self) -> str:
        return datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S")

    def _get_state(self) -> Tuple[float, float, float]:
        snap = self.db.get_latest_snapshot()
        if not snap:
            return config.INITIAL_CAPITAL, 0.0, config.INITIAL_CAPITAL
        snaps = self.db.get_all_snapshots()
        peak = max(s["total_equity"] for s in snaps)
        return snap["cash"], snap["realized_pnl"], max(peak, config.INITIAL_CAPITAL)

    def run_daily_cycle(
        self,
        trade_date: str,
        market_data: Dict[str, Tuple[str, pd.DataFrame, str]],
        benchmark_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        if self.db.has_snapshot_for_date(trade_date):
            return {"status": "SKIPPED", "message": f"{trade_date} 已執行過，避免重複計算。"}

        cash, realized_pnl, peak_equity = self._get_state()
        now_str = self._now_str()

        # Market Regime Check (TAIEX Close > MA20)
        market_bullish = True
        regime_label = "BULL (多頭)"
        bm_sliced = None
        if benchmark_df is not None and not benchmark_df.empty:
            bm_sliced = benchmark_df.loc[benchmark_df.index <= trade_date].copy()
            if len(bm_sliced) >= config.MA_SHORT:
                bm_ma20 = bm_sliced["Close"].rolling(config.MA_SHORT).mean().iloc[-1]
                bm_close = bm_sliced["Close"].iloc[-1]
                market_bullish = bool(bm_close >= bm_ma20)
                regime_label = "BULL (大盤站上月線)" if market_bullish else "BEAR/CHOP (大盤跌破月線)"

        enriched: Dict[str, Tuple[str, pd.DataFrame, str]] = {}
        for sym, (name, raw_df, src) in market_data.items():
            df_sliced = raw_df.loc[raw_df.index <= trade_date].copy()
            if df_sliced.empty or df_sliced.index[-1] != trade_date:
                continue
            enriched[sym] = (name, compute_indicators(df_sliced, bm_sliced), src)

        if not enriched:
            self.db.insert_execution_log(
                now_str, trade_date, "FAILED", 0, "無有效行情資料", "NONE", config.STRATEGY_VERSION
            )
            return {"status": "FAILED", "message": "無有效行情資料"}

        # 1. Check Exits for OPEN trades
        for tr in self.db.get_open_trades():
            sym = tr["symbol"]
            if sym not in enriched:
                continue
            _, df, _ = enriched[sym]
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

        # 2. Execute Pending BUY signals (sorted by StrengthScore DESC) at Today's Open
        pending = self.db.get_pending_buy_signals(before_date=trade_date)
        current_open = self.db.get_open_trades()
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

            _, df, _ = enriched[sym]
            today_open = float(df.iloc[-1]["Open"])
            if today_open > float(sig["signal_price"]) * (1.0 + config.MAX_OPEN_CHASE_PCT):
                self.db.update_signal_status(sig["signal_id"], "CANCELLED_CHASE_LIMIT")
                continue

            atr = float(sig["atr"])
            stop_loss = round(today_open - config.STOP_LOSS_ATR_MULT * atr, 2)
            take_profit = round(today_open + config.TAKE_PROFIT_ATR_MULT * atr, 2)

            mv_temp = sum(
                float(enriched[t["symbol"]][1].iloc[-1]["Close"]) * t["shares"]
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
                "signal_id": sig["signal_id"], "symbol": sym, "name": sig["name"],
                "buy_date": trade_date, "buy_price": today_open, "shares": shares,
                "stop_loss": stop_loss, "take_profit": take_profit,
                "capital_used": sizing["capital_used"], "max_estimated_loss": sizing["max_loss"],
                "estimated_rr": rr, "buy_cost": buy_cost,
                "strategy_version": config.STRATEGY_VERSION, "created_at": now_str,
            })
            self.db.update_signal_status(sig["signal_id"], "EXECUTED")
            cash -= total_outflow
            held_symbols.add(sym)
            current_open = self.db.get_open_trades()

        # 3. EOD Mark-to-Market & Scan for Next-Day Strong-Stock Signals
        open_eod = self.db.get_open_trades()
        held_eod = {t["symbol"] for t in open_eod}
        market_value, unrealized_pnl = 0.0, 0.0
        for tr in open_eod:
            sym = tr["symbol"]
            last_close = float(enriched[sym][1].iloc[-1]["Close"]) if sym in enriched else tr["buy_price"]
            mv = last_close * tr["shares"]
            market_value += mv
            unrealized_pnl += (mv - tr["capital_used"] - tr["buy_cost"])

        total_equity = round(cash + market_value, 2)

        for sym, (name, df, src) in enriched.items():
            if self.db.has_signal_for_date_symbol(trade_date, sym):
                continue
            res = evaluate_entry_signal(df, sym, name, market_bullish=market_bullish)
            decision = "HOLD" if sym in held_eod else res["decision"]
            sug_shares = 0
            if decision == "BUY":
                sizing = calculate_position_size(total_equity, cash, res["signal_price"], res["stop_loss"])
                sug_shares = int(sizing["shares"])

            self.db.insert_signal({
                "date": trade_date, "symbol": sym, "name": name, "signal_type": decision,
                "signal_price": res.get("signal_price", float(df.iloc[-1]["Close"])),
                "strength_score": res.get("strength_score", 0.0), "rs_20": res.get("rs_20", 0.0),
                "ma20": res.get("ma20"), "ma60": res.get("ma60"), "rsi": res.get("rsi"),
                "atr": res.get("atr"), "volume": res.get("volume"),
                "suggested_shares": sug_shares, "stop_loss": res.get("stop_loss"),
                "take_profit": res.get("take_profit"), "rr_ratio": res.get("rr_ratio"),
                "reason": res["reason"], "status": "PENDING" if decision == "BUY" else "INFO",
                "strategy_version": config.STRATEGY_VERSION, "data_source": src,
                "created_at": now_str,
            })

        # 4. Save Snapshot
        peak_equity = max(peak_equity, total_equity)
        mdd_pct = round(((total_equity - peak_equity) / peak_equity) * 100.0, 2)
        prev_snaps = self.db.get_all_snapshots()
        worst_mdd = min([mdd_pct] + [s["max_drawdown_pct"] for s in prev_snaps])
        cum_ret_pct = round(((total_equity - config.INITIAL_CAPITAL) / config.INITIAL_CAPITAL) * 100.0, 2)

        ledger_hash = self.db.insert_snapshot({
            "date": trade_date, "cash": round(cash, 2), "market_value": round(market_value, 2),
            "total_equity": total_equity, "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2), "cum_return_pct": cum_ret_pct,
            "max_drawdown_pct": worst_mdd, "market_regime": regime_label, "created_at": now_str,
        })
        self.db.insert_execution_log(
            now_str, trade_date, "SUCCESS", len(enriched), None, "MULTI", config.STRATEGY_VERSION
        )
        return {
            "status": "SUCCESS", "date": trade_date, "total_equity": total_equity,
            "market_regime": regime_label, "processed": len(enriched), "ledger_hash": ledger_hash
        }
