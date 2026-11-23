"""
Strong-Stock Swing Strategy (Causal Evaluation + Market Regime + Trailing Stop Option).
"""
from typing import Any, Dict, Optional, Tuple
import pandas as pd
import config


def evaluate_entry_signal(
    df: pd.DataFrame,
    symbol: str,
    name: str,
    market_bullish: bool = True,
) -> Dict[str, Any]:
    if df is None or len(df) < config.MA_LONG + 5:
        return {"decision": "WAIT", "strength_score": 0.0, "rs_20": 0.0, "reason": "歷史資料不足"}

    row = df.iloc[-1]
    required = ["Close", "Volume", "MA20", "MA60", "RSI14", "ATR14", "VolMA20"]
    if any(pd.isna(row[c]) for c in required):
        return {"decision": "WAIT", "strength_score": 0.0, "rs_20": 0.0, "reason": "指標資料缺失"}

    close = float(row["Close"])
    vol = float(row["Volume"])
    ma20 = float(row["MA20"])
    ma60 = float(row["MA60"])
    rsi = float(row["RSI14"])
    atr = float(row["ATR14"])
    vol_ma20 = float(row["VolMA20"])
    score = float(row.get("StrengthScore", 0.0))
    rs_20 = float(row.get("RS20", 0.0))

    if close < config.MIN_PRICE or atr <= 0 or vol <= 0:
        return {"decision": "WAIT", "strength_score": score, "rs_20": rs_20, "reason": "低價股或數值異常"}

    if vol_ma20 < config.MIN_AVG_VOLUME_SHARES:
        return {"decision": "WAIT", "strength_score": score, "rs_20": rs_20, "reason": "流動性不足 (<500張/日)"}

    stop_loss = round(close - config.STOP_LOSS_ATR_MULT * atr, 2)
    take_profit = round(close + config.TAKE_PROFIT_ATR_MULT * atr, 2)
    risk = close - stop_loss
    rr_ratio = round((take_profit - close) / risk, 2) if risk > 0 else 0.0

    if config.USE_MARKET_REGIME_FILTER and not market_bullish:
        return {
            "decision": "WAIT", "signal_price": close, "strength_score": score, "rs_20": rs_20,
            "ma20": ma20, "ma60": ma60, "rsi": rsi, "atr": atr, "volume": vol,
            "stop_loss": stop_loss, "take_profit": take_profit, "rr_ratio": rr_ratio,
            "reason": "大盤處於空頭/整理濾網 (加權指數 < MA20)，暫停新進場"
        }

    checks = [
        (close > ma20, f"收盤({close:.2f}) > MA20({ma20:.2f})"),
        (ma20 > ma60, f"MA20({ma20:.2f}) > MA60({ma60:.2f})"),
        (config.RSI_MIN <= rsi <= config.RSI_MAX, f"RSI({rsi:.1f}) 強勢區間"),
        (vol >= vol_ma20, f"量增 ({vol/vol_ma20:.2f}x)"),
        (rr_ratio >= config.MIN_RISK_REWARD_RATIO, f"RR({rr_ratio:.2f}) >= 1.5"),
    ]

    failed = [desc for ok, desc in checks if not ok]
    if failed:
        return {
            "decision": "WAIT", "signal_price": close, "strength_score": score, "rs_20": rs_20,
            "ma20": ma20, "ma60": ma60, "rsi": rsi, "atr": atr, "volume": vol,
            "stop_loss": stop_loss, "take_profit": take_profit, "rr_ratio": rr_ratio,
            "reason": "未達進場: " + "; ".join(failed)
        }

    return {
        "decision": "BUY", "signal_price": close, "strength_score": score, "rs_20": rs_20,
        "ma20": ma20, "ma60": ma60, "rsi": rsi, "atr": atr, "volume": vol,
        "stop_loss": stop_loss, "take_profit": take_profit, "rr_ratio": rr_ratio,
        "reason": f"強勢股達標 (強度 {score:.1f} / RS20 {rs_20:+.1f}%): " + "; ".join(d for _, d in checks)
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
            return True, open_p, "趨勢出場 (前日收盤跌破 MA20，次日開盤出場)"

    if holding_days >= config.MAX_HOLDING_TRADING_DAYS:
        return True, open_p, f"時間出場 (持有滿 {holding_days} 個交易日)"

    if open_p <= sl:
        return True, open_p, f"停損出場 (跳空跌破停損價 {sl:.2f}，開盤價 {open_p:.2f} 成交)"

    hit_sl = low_p <= sl
    hit_tp = high_p >= tp

    if hit_sl and hit_tp:
        return True, sl, f"停損出場 (同日觸及停損與停利，保守原則以停損價 {sl:.2f} 成交)"
    if hit_sl:
        return True, sl, f"停損出場 (盤中觸及 {sl:.2f})"
    if hit_tp:
        return True, tp, f"停利出場 (盤中觸及 {tp:.2f})"

    return False, None, None
