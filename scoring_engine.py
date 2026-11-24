"""
Deterministic 6-Factor AI Stock Scoring Engine.
Strictly separates:
1. Stock Quality Score (0-100 & Grade S+/S/A+/A/B/C)
2. Trade Signal Strength (0-100)
3. Data Confidence / Completeness (0-100%)
NEVER treats missing fundamental/chip data as 0; re-weights available factors and flags reduced confidence.
"""
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import config


def score_to_grade(score: float) -> str:
    if score >= 90:
        return "S+"
    if score >= 85:
        return "S"
    if score >= 80:
        return "A+"
    if score >= 70:
        return "A"
    if score >= 60:
        return "B"
    return "C"


def evaluate_six_factors(
    df: pd.DataFrame,
    fundamentals: Optional[Dict[str, Any]] = None,
    chips: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Computes 6 deterministic scores (0-100 each) + Quality Score + Signal Strength + Data Confidence.
    """
    fundamentals = fundamentals or {}
    chips = chips or {}
    missing_fields: List[str] = []

    if df is None or len(df) < config.MA_LONG:
        return {
            "scores": {k: None for k in config.SCORE_WEIGHTS},
            "quality_score": 0.0,
            "quality_grade": "N/A",
            "signal_strength": 0.0,
            "data_confidence": 0.0,
            "data_completeness": 0.0,
            "missing_fields": ["歷史日線行情不足 60 日"],
            "confidence_warning": "資料不足，評分可信度降低。",
            "basis": {},
        }

    row = df.iloc[-1]
    close = float(row["Close"])
    ma20 = float(row["MA20"]) if not pd.isna(row["MA20"]) else None
    ma60 = float(row["MA60"]) if not pd.isna(row["MA60"]) else None
    rsi = float(row["RSI14"]) if not pd.isna(row["RSI14"]) else None
    atr_pct = float(row["ATR_Pct"]) if not pd.isna(row["ATR_Pct"]) else None
    vol_ratio = float(row["VolRatio"]) if not pd.isna(row["VolRatio"]) else None
    macd_hist = float(row["MACD_HIST"]) if not pd.isna(row["MACD_HIST"]) else None
    rs20 = float(row["RS20"]) if not pd.isna(row["RS20"]) else 0.0
    dd60 = float(row["Drawdown60"]) if not pd.isna(row["Drawdown60"]) else 0.0
    ret60 = float(row["Ret60"]) if not pd.isna(row["Ret60"]) else 0.0
    vol_ma20 = float(row["VolMA20"]) if not pd.isna(row["VolMA20"]) else 0.0

    scores: Dict[str, Optional[float]] = {}
    basis: Dict[str, str] = {}

    # 1. 健康度 (Health - 20%): ROE / Profit Margin / Debt-to-Equity if available
    roe = fundamentals.get("roe")
    margin = fundamentals.get("profit_margin")
    if roe is not None or margin is not None:
        pts = 50.0
        parts = []
        if roe is not None:
            pts += float(np.clip((roe * 100.0 - 8.0) * 2.0, -25.0, 30.0))
            parts.append(f"ROE {roe*100:.1f}%")
        if margin is not None:
            pts += float(np.clip((margin * 100.0 - 5.0) * 1.2, -20.0, 20.0))
            parts.append(f"淨利率 {margin*100:.1f}%")
        scores["health"] = round(float(np.clip(pts, 0.0, 100.0)), 1)
        basis["health"] = "依實際財報計算：" + "、".join(parts)
    else:
        scores["health"] = None
        missing_fields.append("財務健康度 (ROE/淨利率)")
        basis["health"] = "缺少財報資料（不以零分取代）"

    # 2. 成長性 (Growth - 20%): Revenue Growth YoY if available, else None (do not fake)
    rev_growth = fundamentals.get("revenue_growth")
    earn_growth = fundamentals.get("earnings_growth")
    if rev_growth is not None or earn_growth is not None:
        pts = 55.0
        parts = []
        if rev_growth is not None:
            pts += float(np.clip(rev_growth * 100.0 * 1.2, -35.0, 30.0))
            parts.append(f"營收成長 {rev_growth*100:+.1f}%")
        if earn_growth is not None:
            pts += float(np.clip(earn_growth * 100.0 * 0.6, -20.0, 15.0))
            parts.append(f"盈餘成長 {earn_growth*100:+.1f}%")
        scores["growth"] = round(float(np.clip(pts, 0.0, 100.0)), 1)
        basis["growth"] = "依實際成長數據計算：" + "、".join(parts)
    else:
        scores["growth"] = None
        missing_fields.append("基本面成長性 (營收/盈餘年增率)")
        basis["growth"] = "缺少營收/盈餘成長資料（不以零分取代）"

    # 3. 安全性 (Safety - 20%): ATR volatility, 60d drawdown, liquidity
    if atr_pct is not None and vol_ma20 > 0:
        vol_pen = float(np.clip((atr_pct - 2.0) * 10.0, 0.0, 40.0))
        dd_pen = float(np.clip(abs(dd60) * 1.2, 0.0, 30.0))
        liq_bonus = 15.0 if vol_ma20 >= 2_000_000 else (8.0 if vol_ma20 >= config.MIN_AVG_VOLUME_SHARES else -15.0)
        safety_s = float(np.clip(85.0 - vol_pen - dd_pen + liq_bonus, 0.0, 100.0))
        scores["safety"] = round(safety_s, 1)
        basis["safety"] = f"波動率 ATR {atr_pct:.2f}%、距60日高點回撤 {dd60:.1f}%、20日均量 {int(vol_ma20//1000):,} 張"
    else:
        scores["safety"] = None
        missing_fields.append("波動與流動性資料")
        basis["safety"] = "缺少波動或均量資料"

    # 4. 人氣度 (Popularity - 10%): Volume expansion & liquidity activity
    if vol_ratio is not None and vol_ma20 > 0:
        pop_s = 40.0 + float(np.clip((vol_ratio - 0.8) * 35.0, -25.0, 45.0)) + (15.0 if vol_ma20 >= 3_000_000 else 5.0)
        scores["popularity"] = round(float(np.clip(pop_s, 0.0, 100.0)), 1)
        basis["popularity"] = f"今日量比 {vol_ratio:.2f}x（20日均量 {int(vol_ma20//1000):,} 張）"
    else:
        scores["popularity"] = None
        missing_fields.append("成交量人氣資料")
        basis["popularity"] = "缺少量比資料"

    # 5. 主力資金 (Smart Money - 10%): 5-day Institutional Net Buy/Sell (Foreign + Trust)
    inst_net_5d = chips.get("inst_net_5d_shares")
    if inst_net_5d is not None and vol_ma20 > 0:
        ratio = inst_net_5d / max(vol_ma20, 1.0)
        sm_s = 50.0 + float(np.clip(ratio * 120.0, -45.0, 50.0))
        scores["smart_money"] = round(float(np.clip(sm_s, 0.0, 100.0)), 1)
        basis["smart_money"] = f"近5日三大法人合計買賣超 {int(inst_net_5d // 1000):+,} 張"
    else:
        scores["smart_money"] = None
        missing_fields.append("三大法人籌碼資料")
        basis["smart_money"] = "尚未取得最新法人籌碼（不以零分取代）"

    # 6. 技術趨勢 (Technical Trend - 20%): MA20/60, RS20, MACD, RSI
    if ma20 is not None and ma60 is not None and rsi is not None:
        t_pts = 0.0
        if close > ma20 and ma20 > ma60:
            t_pts += 40.0
        elif close > ma20:
            t_pts += 22.0
        elif close > ma60:
            t_pts += 12.0
        t_pts += float(np.clip((rs20 + 5.0) / 25.0, 0.0, 1.0) * 30.0)
        if macd_hist is not None and macd_hist > 0:
            t_pts += 15.0
        if 45.0 <= rsi <= 70.0:
            t_pts += 15.0
        elif 70.0 < rsi <= 78.0:
            t_pts += 8.0
        scores["trend"] = round(float(np.clip(t_pts, 0.0, 100.0)), 1)
        basis["trend"] = f"收盤 {close:.2f} / MA20 {ma20:.2f} / MA60 {ma60:.2f} / RS20 {rs20:+.1f}% / RSI {rsi:.1f}"
    else:
        scores["trend"] = None
        missing_fields.append("技術趨勢指標")
        basis["trend"] = "缺少技術均線資料"

    # Weighted Quality Score (re-normalized ONLY over available factors, never substituting 0)
    avail_weight = sum(w for k, w in config.SCORE_WEIGHTS.items() if scores[k] is not None)
    if avail_weight > 0:
        quality_score = round(
            sum(scores[k] * config.SCORE_WEIGHTS[k] for k in config.SCORE_WEIGHTS if scores[k] is not None) / avail_weight,
            1,
        )
    else:
        quality_score = 0.0

    # Data completeness & confidence
    data_completeness = round(avail_weight * 100.0, 1)
    # Technical price data gives base 55% confidence if complete; fundamentals + chips add remaining 45%
    data_confidence = data_completeness
    confidence_warning = ""
    if missing_fields:
        confidence_warning = f"資料不足，評分可信度降低。（缺少：{', '.join(missing_fields)}）"

    # Separate Trade Signal Strength (0-100): Purely timing/setup quality (NOT company quality)
    sig_pts = 0.0
    if ma20 is not None and ma60 is not None and rsi is not None and vol_ratio is not None:
        if close > ma20:
            sig_pts += 25.0
        if ma20 > ma60:
            sig_pts += 20.0
        if 45.0 <= rsi <= 70.0:
            sig_pts += 20.0
        elif rsi > 75.0:
            sig_pts -= 10.0  # Chase penalty
        if vol_ratio >= 1.0:
            sig_pts += 20.0
        if rs20 > 0:
            sig_pts += 15.0
    signal_strength = round(float(np.clip(sig_pts, 0.0, 100.0)), 1)

    return {
        "scores": scores,
        "quality_score": quality_score,
        "quality_grade": score_to_grade(quality_score) if avail_weight > 0 else "N/A",
        "signal_strength": signal_strength,
        "data_confidence": data_confidence,
        "data_completeness": data_completeness,
        "missing_fields": missing_fields,
        "confidence_warning": confidence_warning,
        "basis": basis,
    }
