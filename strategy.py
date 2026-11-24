"""
Dual Strategy Engine:
1. QC-PT-1.0-FROZEN (Locked original baseline: Close > MA20 > MA60, RSI 45-70, Vol >= VolMA20, RR >= 1.5)
2. QC-AI-2.0 (Traffic Light: 綠燈/黃燈/紅燈/灰燈 + 6-Factor Score + Market Temperature + 10-Point Plan)
"""
from typing import Any, Dict, Optional, Tuple
import pandas as pd
import config
from risk_manager import calculate_buy_cost, calculate_position_size, calculate_sell_cost
from scoring_engine import evaluate_six_factors


def build_actionable_plan(
    close: float,
    atr: float,
    total_equity: float,
    available_cash: float,
    decision: str,
    missing_cond: str = "",
) -> Dict[str, Any]:
    """
    Produces the complete 10-point actionable trading plan.
    """
    entry_low = round(close - 0.3 * atr, 2)
    entry_high = round(close + 0.3 * atr, 2)
    stop_loss = round(close - config.STOP_LOSS_ATR_MULT * atr, 2)
    tp1 = round(close + config.TAKE_PROFIT_ATR_MULT * atr, 2)
    tp2 = round(close + config.TP2_ATR_MULT * atr, 2)

    sizing = calculate_position_size(total_equity, available_cash, close, stop_loss)
    shares = int(sizing["shares"])
    buy_cost = calculate_buy_cost(close, shares) if shares > 0 else 0.0
    sell_cost_tp1 = calculate_sell_cost(tp1, shares) if shares > 0 else 0.0
    est_total_cost = round(buy_cost + sell_cost_tp1, 2)
    max_loss = sizing["max_loss"]
    est_reward = round(max(0.0, (tp1 - close) * shares - est_total_cost), 2) if shares > 0 else 0.0
    rr_ratio = round((tp1 - close) / (close - stop_loss), 2) if (close - stop_loss) > 0 else 0.0

    fallback = (
        "若隔日開盤跳空超過 4%（追高風險），則取消進場並等待拉回月線附近。"
        if decision == "BUY"
        else f"目前不建議買進，等待下一次機會。（{missing_cond or '條件尚未完全滿足'}）"
    )

    return {
        "buy_condition": "收盤站上 MA20、MA20 > MA60、RSI 健康區間、量增且風險報酬比 >= 1.5",
        "ideal_entry_zone": f"{entry_low:.2f} ～ {entry_high:.2f}",
        "entry_price": round(close, 2),
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "suggested_shares": shares,
        "suggested_amount": sizing["capital_used"],
        "est_transaction_cost": est_total_cost,
        "max_possible_loss": max_loss,
        "expected_reward": est_reward,
        "rr_ratio": rr_ratio,
        "holding_horizon": "5～20 個交易日（波段）",
        "invalidation": f"收盤跌破 MA20 或觸及停損價 {stop_loss:.2f}",
        "fallback_plan": fallback,
    }


def evaluate_frozen_v1(
    df: pd.DataFrame,
    symbol: str,
    name: str,
    total_equity: float = config.INITIAL_CAPITAL,
    available_cash: float = config.INITIAL_CAPITAL,
) -> Dict[str, Any]:
    """
    QC-PT-1.0-FROZEN — Exact original baseline strategy (DO NOT ALTER RULES).
    """
    if df is None or len(df) < config.MA_LONG:
        return {
            "decision": "WAIT", "traffic_light": "灰燈", "reason": "資料不足，暫停判斷",
            "missing_condition": "歷史資料不足 60 日", "quality_score": 0.0, "quality_grade": "N/A",
            "signal_strength": 0.0, "data_confidence": 0.0, "scores": {}, "plan": {},
        }

    row = df.iloc[-1]
    req = ["Close", "Volume", "MA20", "MA60", "RSI14", "ATR14", "VolMA20"]
    if any(pd.isna(row[c]) for c in req):
        return {
            "decision": "WAIT", "traffic_light": "灰燈", "reason": "資料異常，暫停交易判斷。",
            "missing_condition": "指標欄位缺失", "quality_score": 0.0, "quality_grade": "N/A",
            "signal_strength": 0.0, "data_confidence": 0.0, "scores": {}, "plan": {},
        }

    close = float(row["Close"])
    vol = float(row["Volume"])
    ma20 = float(row["MA20"])
    ma60 = float(row["MA60"])
    rsi = float(row["RSI14"])
    atr = float(row["ATR14"])
    vol_ma20 = float(row["VolMA20"])
    rs20 = float(row.get("RS20", 0.0))

    if close <= 0 or atr <= 0 or vol <= 0:
        return {
            "decision": "WAIT", "traffic_light": "灰燈", "reason": "資料異常，暫停交易判斷。",
            "missing_condition": "價格或量能異常", "quality_score": 0.0, "quality_grade": "N/A",
            "signal_strength": 0.0, "data_confidence": 0.0, "scores": {}, "plan": {},
        }

    plan = build_actionable_plan(close, atr, total_equity, available_cash, "WAIT")
    rr = plan["rr_ratio"]

    checks = [
        (vol_ma20 >= config.MIN_AVG_VOLUME_SHARES, "20日均量 >= 500張"),
        (close > ma20, f"收盤({close:.2f}) > MA20({ma20:.2f})"),
        (ma20 > ma60, f"MA20({ma20:.2f}) > MA60({ma60:.2f})"),
        (config.RSI_MIN_FROZEN <= rsi <= config.RSI_MAX_FROZEN, f"RSI({rsi:.1f}) 介於 45-70"),
        (vol >= vol_ma20, "當日量 >= 20日均量"),
        (rr >= config.MIN_RISK_REWARD_RATIO, f"風險報酬比({rr:.2f}) >= 1.5"),
    ]
    failed = [desc for ok, desc in checks if not ok]

    if not failed:
        plan = build_actionable_plan(close, atr, total_equity, available_cash, "BUY")
        return {
            "decision": "BUY", "traffic_light": "綠燈", "signal_price": close,
            "ma20": ma20, "ma60": ma60, "rsi": rsi, "atr": atr, "volume": vol, "rs_20": rs20,
            "stop_loss": plan["stop_loss"], "take_profit": plan["tp1"], "take_profit_2": plan["tp2"],
            "rr_ratio": rr, "suggested_shares": plan["suggested_shares"],
            "quality_score": float(row.get("StrengthScore", 70.0)), "quality_grade": "A",
            "signal_strength": float(row.get("StrengthScore", 80.0)), "data_confidence": 100.0,
            "reason": "QC-PT-1.0-FROZEN 全部條件達標：" + "、".join(d for _, d in checks),
            "missing_condition": "", "scores": {}, "plan": plan,
        }

    light = "黃燈" if len(failed) == 1 else "紅燈"
    return {
        "decision": "WAIT", "traffic_light": light, "signal_price": close,
        "ma20": ma20, "ma60": ma60, "rsi": rsi, "atr": atr, "volume": vol, "rs_20": rs20,
        "stop_loss": plan["stop_loss"], "take_profit": plan["tp1"], "take_profit_2": plan["tp2"],
        "rr_ratio": rr, "suggested_shares": 0,
        "quality_score": float(row.get("StrengthScore", 50.0)), "quality_grade": "B",
        "signal_strength": float(row.get("StrengthScore", 40.0)), "data_confidence": 100.0,
        "reason": "未達基準進場條件：" + "；".join(failed),
        "missing_condition": f"目前尚差：{failed[0]}" if len(failed) == 1 else "；".join(failed),
        "scores": {}, "plan": plan,
    }


def evaluate_ai_v2(
    df: pd.DataFrame,
    symbol: str,
    name: str,
    market_temp: Dict[str, Any],
    fundamentals: Optional[Dict[str, Any]] = None,
    chips: Optional[Dict[str, Any]] = None,
    total_equity: float = config.INITIAL_CAPITAL,
    available_cash: float = config.INITIAL_CAPITAL,
) -> Dict[str, Any]:
    """
    QC-AI-2.0 — Next-Gen AI Strategy with 6-Factor Scoring, Traffic Light & 10-Point Plan.
    """
    score_res = evaluate_six_factors(df, fundamentals=fundamentals, chips=chips)

    # Strict Data Integrity Gate -> Grey Light if data insufficient
    if df is None or len(df) < config.MA_LONG or score_res["data_confidence"] < config.AI_MIN_DATA_CONFIDENCE:
        return {
            "decision": "WAIT", "traffic_light": "灰燈",
            "signal_price": float(df.iloc[-1]["Close"]) if (df is not None and not df.empty) else 0.0,
            "quality_score": score_res["quality_score"], "quality_grade": score_res["quality_grade"],
            "signal_strength": score_res["signal_strength"], "data_confidence": score_res["data_confidence"],
            "reason": "資料異常或完整度不足，暫停交易判斷。",
            "missing_condition": score_res.get("confidence_warning", "資料不足"),
            "scores": score_res, "plan": {},
        }

    row = df.iloc[-1]
    close = float(row["Close"])
    vol = float(row["Volume"])
    ma20 = float(row["MA20"])
    ma60 = float(row["MA60"])
    rsi = float(row["RSI14"])
    atr = float(row["ATR14"])
    vol_ma20 = float(row["VolMA20"])
    rs20 = float(row.get("RS20", 0.0))

    if close < config.MIN_PRICE or atr <= 0 or vol <= 0:
        return {
            "decision": "WAIT", "traffic_light": "紅燈", "signal_price": close,
            "quality_score": score_res["quality_score"], "quality_grade": score_res["quality_grade"],
            "signal_strength": 0.0, "data_confidence": score_res["data_confidence"],
            "reason": "低價股或價格/波動異常，建議避開。", "missing_condition": "不符合流動性與價格門檻",
            "scores": score_res, "plan": {},
        }

    plan = build_actionable_plan(close, atr, total_equity, available_cash, "WAIT")
    rr = plan["rr_ratio"]

    checks = [
        (market_temp.get("temp", 50.0) >= config.AI_MIN_MARKET_TEMP, f"大盤溫度({market_temp.get('temp', 50):.0f}) >= {config.AI_MIN_MARKET_TEMP:.0f}"),
        (vol_ma20 >= config.MIN_AVG_VOLUME_SHARES, "成交量充足 (20日均量 >= 500張)"),
        (close > ma20, f"站上月線 MA20({ma20:.2f})"),
        (ma20 > ma60, f"中期多頭 MA20 > MA60({ma60:.2f})"),
        (config.RSI_MIN_AI <= rsi <= config.RSI_MAX_AI, f"RSI({rsi:.1f}) 未過熱且偏強"),
        (vol >= vol_ma20, "成交量溫和放大 (>= 20日均量)"),
        (rr >= config.MIN_RISK_REWARD_RATIO, f"風險報酬比({rr:.2f}) >= 1.5"),
        (score_res["quality_score"] >= config.AI_MIN_QUALITY_SCORE, f"品質評分({score_res['quality_score']:.1f}) >= {config.AI_MIN_QUALITY_SCORE:.0f}"),
    ]

    failed = [desc for ok, desc in checks if not ok]

    if not failed:
        plan = build_actionable_plan(close, atr, total_equity, available_cash, "BUY")
        return {
            "decision": "BUY", "traffic_light": "綠燈", "signal_price": close,
            "ma20": ma20, "ma60": ma60, "rsi": rsi, "atr": atr, "volume": vol, "rs_20": rs20,
            "stop_loss": plan["stop_loss"], "take_profit": plan["tp1"], "take_profit_2": plan["tp2"],
            "rr_ratio": rr, "suggested_shares": plan["suggested_shares"],
            "quality_score": score_res["quality_score"], "quality_grade": score_res["quality_grade"],
            "signal_strength": score_res["signal_strength"], "data_confidence": score_res["data_confidence"],
            "reason": f"符合綠燈買進條件（品質 {score_res['quality_grade']} 級 / RS20 {rs20:+.1f}%），風報比 {rr:.2f}。",
            "missing_condition": "", "scores": score_res, "plan": plan,
        }

    # Yellow Light: Close to entry (missing 1-2 conditions, trend still intact above MA60)
    if len(failed) <= 2 and close > ma60 and vol_ma20 >= config.MIN_AVG_VOLUME_SHARES:
        missing_str = "目前差：" + "、".join(failed)
        plan = build_actionable_plan(close, atr, total_equity, available_cash, "WAIT", missing_str)
        return {
            "decision": "WAIT", "traffic_light": "黃燈", "signal_price": close,
            "ma20": ma20, "ma60": ma60, "rsi": rsi, "atr": atr, "volume": vol, "rs_20": rs20,
            "stop_loss": plan["stop_loss"], "take_profit": plan["tp1"], "take_profit_2": plan["tp2"],
            "rr_ratio": rr, "suggested_shares": 0,
            "quality_score": score_res["quality_score"], "quality_grade": score_res["quality_grade"],
            "signal_strength": score_res["signal_strength"], "data_confidence": score_res["data_confidence"],
            "reason": f"體質或中期趨勢尚可，但進場時機未成熟（{missing_str}）。",
            "missing_condition": missing_str, "scores": score_res, "plan": plan,
        }

    # Red Light: Avoid
    missing_str = "；".join(failed[:3])
    plan = build_actionable_plan(close, atr, total_equity, available_cash, "WAIT", missing_str)
    return {
        "decision": "WAIT", "traffic_light": "紅燈", "signal_price": close,
        "ma20": ma20, "ma60": ma60, "rsi": rsi, "atr": atr, "volume": vol, "rs_20": rs20,
        "stop_loss": plan["stop_loss"], "take_profit": plan["tp1"], "take_profit_2": plan["tp2"],
        "rr_ratio": rr, "suggested_shares": 0,
        "quality_score": score_res["quality_score"], "quality_grade": score_res["quality_grade"],
        "signal_strength": score_res["signal_strength"], "data_confidence": score_res["data_confidence"],
        "reason": f"趨勢轉弱或風險偏高，不建議買進（{missing_str}）。",
        "missing_condition": missing_str, "scores": score_res, "plan": plan,
    }


def check_exit_conditions(
    trade: Dict[str, Any],
    today_bar: pd.Series,
    prev_bar: Optional[pd.Series],
    holding_days: int
) -> Tuple[bool, Optional[float], Optional[str]]:
    open_p = float(today_bar["Open"])
    high_p = float(today_bar["High"])
    low_p = float(today_bar["Low"])
    sl = float(trade["stop_loss"])
    tp = float(trade["take_profit"])

    if prev_bar is not None and not pd.isna(prev_bar.get("MA20")):
        if float(prev_bar["Close"]) < float(prev_bar["MA20"]):
            return True, open_p, "趨勢出場（前日收盤跌破 MA20，次日開盤出場）"

    if holding_days >= config.MAX_HOLDING_TRADING_DAYS:
        return True, open_p, f"時間出場（持有滿 {holding_days} 個交易日）"

    if open_p <= sl:
        return True, open_p, f"停損出場（跳空跌破停損 {sl:.2f}，以開盤價 {open_p:.2f} 成交）"

    hit_sl = low_p <= sl
    hit_tp = high_p >= tp
    if hit_sl and hit_tp:
        return True, sl, f"停損出場（同日觸及停損與停利，保守原則以停損價 {sl:.2f} 成交）"
    if hit_sl:
        return True, sl, f"停損出場（盤中觸及 {sl:.2f}）"
    if hit_tp:
        return True, tp, f"停利出場（盤中觸及 {tp:.2f}）"

    return False, None, None
