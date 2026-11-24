"""
Strictly Causal Technical Indicators & Market Temperature Engine.
All indicators at index t depend ONLY on data <= t.
"""
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
import config


def compute_indicators(
    df: pd.DataFrame,
    benchmark_df: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    out = df.copy()
    out["MA20"] = out["Close"].rolling(window=config.MA_SHORT, min_periods=config.MA_SHORT).mean()
    out["MA60"] = out["Close"].rolling(window=config.MA_LONG, min_periods=config.MA_LONG).mean()
    out["VolMA20"] = out["Volume"].rolling(window=config.VOL_MA_PERIOD, min_periods=config.VOL_MA_PERIOD).mean()
    out["VolRatio"] = out["Volume"] / out["VolMA20"].replace(0, np.nan)

    # Wilder's RSI(14)
    delta = out["Close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / config.RSI_PERIOD, min_periods=config.RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / config.RSI_PERIOD, min_periods=config.RSI_PERIOD, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out["RSI14"] = 100.0 - (100.0 / (1.0 + rs))
    out.loc[(avg_loss == 0) & (avg_gain > 0), "RSI14"] = 100.0
    out.loc[(avg_loss == 0) & (avg_gain == 0), "RSI14"] = 50.0

    # Wilder's ATR(14)
    prev_close = out["Close"].shift(1)
    tr1 = out["High"] - out["Low"]
    tr2 = (out["High"] - prev_close).abs()
    tr3 = (out["Low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    out["ATR14"] = tr.ewm(alpha=1.0 / config.ATR_PERIOD, min_periods=config.ATR_PERIOD, adjust=False).mean()
    out["ATR_Pct"] = (out["ATR14"] / out["Close"].replace(0, np.nan)) * 100.0

    # MACD (12, 26, 9)
    ema12 = out["Close"].ewm(span=12, adjust=False).mean()
    ema26 = out["Close"].ewm(span=26, adjust=False).mean()
    out["MACD_DIF"] = ema12 - ema26
    out["MACD_DEA"] = out["MACD_DIF"].ewm(span=9, adjust=False).mean()
    out["MACD_HIST"] = out["MACD_DIF"] - out["MACD_DEA"]

    # KD (9, 3, 3)
    low9 = out["Low"].rolling(window=9, min_periods=9).min()
    high9 = out["High"].rolling(window=9, min_periods=9).max()
    rsv = ((out["Close"] - low9) / (high9 - low9).replace(0, np.nan)) * 100.0
    rsv = rsv.fillna(50.0)
    k_vals = np.full(len(out), 50.0)
    d_vals = np.full(len(out), 50.0)
    rsv_arr = rsv.to_numpy()
    for i in range(1, len(out)):
        k_vals[i] = (2.0 / 3.0) * k_vals[i - 1] + (1.0 / 3.0) * rsv_arr[i]
        d_vals[i] = (2.0 / 3.0) * d_vals[i - 1] + (1.0 / 3.0) * k_vals[i]
    out["K9"] = k_vals
    out["D9"] = d_vals

    # 20-day & 60-day Return + Relative Strength vs TAIEX
    out["Ret20"] = out["Close"].pct_change(20) * 100.0
    out["Ret60"] = out["Close"].pct_change(60) * 100.0
    out["High60"] = out["High"].rolling(window=60, min_periods=20).max()
    out["Drawdown60"] = ((out["Close"] - out["High60"]) / out["High60"].replace(0, np.nan)) * 100.0

    if benchmark_df is not None and not benchmark_df.empty:
        bm_ret20 = benchmark_df["Close"].pct_change(20) * 100.0
        aligned_bm = bm_ret20.reindex(out.index).ffill().fillna(0.0)
        out["RS20"] = (out["Ret20"] - aligned_bm).fillna(0.0)
    else:
        out["RS20"] = out["Ret20"].fillna(0.0)

    # Legacy StrengthScore (0-100) preserved for compatibility
    trend_pts = np.where((out["Close"] > out["MA20"]) & (out["MA20"] > out["MA60"]), 30.0,
                np.where(out["Close"] > out["MA20"], 15.0, 0.0))
    rs_pts = np.clip((out["RS20"] + 5.0) / 25.0, 0.0, 1.0) * 30.0
    vol_pts = np.clip((out["VolRatio"].fillna(0.0) - 0.8) / 1.7, 0.0, 1.0) * 20.0
    rsi_pts = np.where((out["RSI14"] >= 50) & (out["RSI14"] <= 68), 20.0,
              np.where((out["RSI14"] >= 45) & (out["RSI14"] <= 72), 12.0, 4.0))
    out["StrengthScore"] = np.round(trend_pts + rs_pts + vol_pts + rsi_pts, 1)
    return out


def compute_market_temperature(benchmark_df: Optional[pd.DataFrame], trade_date: str, breadth: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """
    Computes Market Temperature (0-100), Market State (多頭/空頭/盤整),
    Risk Level, Volume Change, and Plain-Language AI Market Summary.
    """
    if benchmark_df is None or benchmark_df.empty:
        return {
            "temp": 50.0, "state": "資料不足", "risk": "未知（暫停積極進場）",
            "trend_desc": "無法取得加權指數資料", "vol_change_pct": 0.0,
            "bullish": False, "data_ok": False,
            "summary": "目前無法取得台灣加權指數最新資料，市場溫度暫停計算，建議保持觀望。"
        }

    bm = benchmark_df.loc[benchmark_df.index <= trade_date].copy()
    if len(bm) < config.MA_LONG:
        return {
            "temp": 50.0, "state": "資料不足", "risk": "中（歷史資料偏短）",
            "trend_desc": "加權指數歷史長度不足 60 日", "vol_change_pct": 0.0,
            "bullish": False, "data_ok": False,
            "summary": "大盤歷史資料不足 60 個交易日，無法完整計算多空溫度，暫停積極判斷。"
        }

    bm_ind = compute_indicators(bm)
    row = bm_ind.iloc[-1]
    close = float(row["Close"])
    ma20 = float(row["MA20"])
    ma60 = float(row["MA60"])
    rsi = float(row["RSI14"])
    vol_ratio = float(row["VolRatio"]) if not pd.isna(row["VolRatio"]) else 1.0
    vol_chg_pct = round((vol_ratio - 1.0) * 100.0, 1)

    # Deterministic 0-100 Temperature
    score = 50.0
    if close > ma20 and ma20 > ma60:
        score += 25.0
        state = "多頭"
        trend_desc = f"加權指數 ({close:,.0f}) 站上月線 ({ma20:,.0f}) 且月線高於季線 ({ma60:,.0f})"
    elif close < ma20 and ma20 < ma60:
        score -= 28.0
        state = "空頭"
        trend_desc = f"加權指數 ({close:,.0f}) 跌破月線 ({ma20:,.0f}) 且月線低於季線 ({ma60:,.0f})"
    else:
        score += 5.0 if close >= ma20 else -8.0
        state = "盤整"
        trend_desc = f"加權指數 ({close:,.0f}) 位於均線糾結區間（月線 {ma20:,.0f} / 季線 {ma60:,.0f}）"

    # RSI contribution (-15 to +15)
    score += float(np.clip((rsi - 50.0) * 0.6, -15.0, 15.0))
    # Volume momentum (-10 to +10); ignore if intraday volume is 0
    if vol_ratio > 0.05:
        score += float(np.clip((vol_ratio - 1.0) * 15.0, -10.0, 10.0))
    # Short-term daily momentum (-12 to +18) so major rallies/drops are reflected
    if len(bm_ind) >= 2:
        prev_c = float(bm_ind.iloc[-2]["Close"])
        day_chg_pct = ((close - prev_c) / prev_c * 100.0) if prev_c > 0 else 0.0
        score += float(np.clip(day_chg_pct * 4.0, -12.0, 18.0))
    # Market breadth contribution (-10 to +12) if available
    if breadth and breadth.get("total", 0) > 0:
        adv_ratio = breadth.get("advancers", 0) / breadth["total"]
        score += float(np.clip((adv_ratio - 0.5) * 24.0, -10.0, 12.0))
        if state == "空頭" and adv_ratio >= 0.75:
            state = "空頭反彈"
    temp = round(float(np.clip(score, 0.0, 100.0)), 1)

    if temp >= 75:
        risk = "中高（短線偏熱，留意追高回檔）"
        summary = f"目前市場溫度 {temp:.0f} 分，市場偏向{state}，但短線漲幅較大，不建議盲目追高，應嚴守進場區間與停損。"
    elif temp >= 55:
        risk = "中低（多頭健康，可依紀律選股）"
        summary = f"目前市場溫度 {temp:.0f} 分，市場呈現{state}格局，資金動能相對穩定，可依交易計畫布局綠燈標的。"
    elif temp >= 40:
        risk = "中（震盪整理，精選強勢股）"
        summary = f"目前市場溫度 {temp:.0f} 分，大盤處於{state}階段，輪動較快，建議控制部位並等待明確突破訊號。"
    else:
        risk = "高（空頭警戒，建議降低持倉）"
        summary = f"目前市場溫度 {temp:.0f} 分，大盤轉弱為{state}格局，系統性風險偏高，建議暫停新進場並嚴格執行停損。"

    return {
        "temp": temp,
        "state": state,
        "risk": risk,
        "trend_desc": trend_desc,
        "vol_change_pct": vol_chg_pct,
        "bullish": bool(close >= ma20),
        "close": close,
        "ma20": ma20,
        "ma60": ma60,
        "rsi": round(rsi, 1),
        "data_ok": True,
        "summary": summary,
    }
