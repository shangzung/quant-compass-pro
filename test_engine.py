"""
Automated Verification Suite for Quant Compass Pro v2.0 (Windows-Safe).
"""
import os
import tempfile
import unittest
import pandas as pd

from backtester import run_historical_backtest
from database import LedgerDB
from indicators import compute_indicators
from paper_engine import PaperTradingEngine


def make_series(dates, base=50.0, trend=0.35, vol=1_200_000):
    rows = []
    p = base
    for d in dates:
        o = p
        c = p + trend
        rows.append({"Date": d, "Open": o, "High": max(o, c) + 1.0, "Low": min(o, c) - 1.0, "Close": c, "Volume": vol})
        p = c
    return pd.DataFrame(rows).set_index("Date")


class TestQuantCompassV2(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.db = LedgerDB(self.tmp.name)
        self.engine = PaperTradingEngine(self.db)

    def tearDown(self):
        if os.path.exists(self.tmp.name):
            os.remove(self.tmp.name)

    def test_01_causal_indicators_and_rs_score(self):
        dates = pd.bdate_range("2026-01-01", periods=85).strftime("%Y-%m-%d").tolist()
        df = make_series(dates, base=100.0, trend=0.5)
        bm = make_series(dates, base=20000.0, trend=10.0)
        full = compute_indicators(df, bm)
        part = compute_indicators(df.iloc[:70], bm.iloc[:70])
        for col in ["MA20", "MA60", "RSI14", "ATR14", "RS20", "StrengthScore"]:
            self.assertAlmostEqual(full[col].iloc[69], part[col].iloc[69], places=6)

    def test_02_backtester_and_diagnosis(self):
        dates = pd.bdate_range("2026-01-01", periods=95).strftime("%Y-%m-%d").tolist()
        df1 = make_series(dates, base=50.0, trend=0.25, vol=1_200_000)
        for idx in range(50, 90, 4):
            df1.iloc[idx, df1.columns.get_loc("Close")] -= 1.0
        df1.iloc[70, df1.columns.get_loc("Volume")] = 2_500_000
        bm = make_series(dates, base=20000.0, trend=20.0)

        bt = run_historical_backtest({"2330": ("台積電", df1, "FIXTURE")}, benchmark_df=bm, test_days=25)
        self.assertEqual(bt["status"], "OK")
        self.assertTrue(len(bt["diagnosis"]) > 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
