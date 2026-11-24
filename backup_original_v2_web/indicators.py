"""
Strictly Causal Technical Indicators + Relative Strength (RS) & Multi-Factor Score.
All indicators at index t depend ONLY on data <= t.
"""
from typing import Optional
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

    # 20-day Return & Relative Strength (RS20) vs Benchmark (TAIEX)
    out["Ret20"] = out["Close"].pct_change(20) * 100.0
    if benchmark_df is not None and not benchmark_df.empty:
        bm_ret20 = benchmark_df["Close"].pct_change(20) * 100.0
        aligned_bm = bm_ret20.reindex(out.index).ffill().fillna(0.0)
        out["RS20"] = (out["Ret20"] - aligned_bm).fillna(0.0)
    else:
        out["RS20"] = out["Ret20"].fillna(0.0)

    # Composite Strong-Stock Score (0 - 100, strictly causal)
    # 1. Trend Alignment (30 pts): Close > MA20 > MA60
    trend_pts = np.where((out["Close"] > out["MA20"]) & (out["MA20"] > out["MA60"]), 30.0,
                np.where(out["Close"] > out["MA20"], 15.0, 0.0))
    # 2. Relative Strength RS20 (30 pts): clipped [-10%, +20%] mapped to 0..30
    rs_pts = np.clip((out["RS20"] + 5.0) / 25.0, 0.0, 1.0) * 30.0
    # 3. Volume Expansion (20 pts): VolRatio 1.0..2.5 mapped to 0..20
    vol_pts = np.clip((out["VolRatio"].fillna(0.0) - 0.8) / 1.7, 0.0, 1.0) * 20.0
    # 4. RSI Sweet Spot (20 pts): peak at RSI 55-65
    rsi_pts = np.where((out["RSI14"] >= 50) & (out["RSI14"] <= 68), 20.0,
              np.where((out["RSI14"] >= 45) & (out["RSI14"] <= 72), 12.0, 4.0))

    out["StrengthScore"] = np.round(trend_pts + rs_pts + vol_pts + rsi_pts, 1)
    return out
