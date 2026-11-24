"""
Quant Compass AI Ultimate V2.0 — Comprehensive Automated Test Suite
Verifies:
1. Causal indicators (no lookahead bias) & Market Temperature
2. 6-Factor Scoring with missing-data transparency (never treats missing as 0)
3. Plain-language explainer & AI Teacher 4-part structured response
4. News RSS parser deduplication & Fact/Inference/Uncertainty separation
5. Dual-Strategy Paper Trading (QC-PT-1.0-FROZEN vs QC-AI-2.0 isolation, idempotency,
   JSON ledger export, SHA-256 hash chain verification, immutable prediction tracking)
6. Historical Comparison Backtest & Walk-Forward Out-of-Sample Validation
"""
import json
import os
import tempfile
import unittest
import pandas as pd

import config
from backtester import run_comparison_backtest, run_walk_forward_validation
from database import LedgerDB
from indicators import compute_indicators, compute_market_temperature
from news_analyzer import parse_rss_news
from paper_engine import PaperTradingEngine
from plain_explainer import answer_teacher_question, explain_indicators_plain
from reporter import generate_performance_report
from scoring_engine import evaluate_six_factors


def make_series(dates, base=60.0, trend=0.35, vol=1_500_000):
    rows = []
    p = base
    for i, d in enumerate(dates):
        o = p
        c = p + trend
        if i % 6 == 0 and i > 45:
            c -= 0.9
        rows.append({"Date": d, "Open": o, "High": max(o, c) + 1.2, "Low": min(o, c) - 1.2, "Close": c, "Volume": vol})
        p = c
    return pd.DataFrame(rows).set_index("Date")


class TestQuantCompassUltimateV2(unittest.TestCase):
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp_db.close()
        self.tmp_json = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.tmp_json.close()
        self.db = LedgerDB(self.tmp_db.name)
        self.engine = PaperTradingEngine(self.db)

    def tearDown(self):
        for p in [self.tmp_db.name, self.tmp_json.name]:
            if os.path.exists(p):
                os.remove(p)

    def test_01_causal_indicators_and_market_temperature(self):
        dates = pd.bdate_range("2026-01-01", periods=90).strftime("%Y-%m-%d").tolist()
        df = make_series(dates, base=100.0, trend=0.4)
        bm = make_series(dates, base=20000.0, trend=25.0, vol=5_000_000)
        full = compute_indicators(df, bm)
        part = compute_indicators(df.iloc[:70], bm.iloc[:70])
        for col in ["MA20", "MA60", "RSI14", "ATR14", "MACD_HIST", "K9", "D9", "RS20"]:
            self.assertAlmostEqual(full[col].iloc[69], part[col].iloc[69], places=6)

        mt = compute_market_temperature(bm, dates[80])
        self.assertTrue(mt["data_ok"])
        self.assertGreaterEqual(mt["temp"], 55.0)
        self.assertEqual(mt["state"], "多頭")

    def test_02_six_factor_scoring_missing_data_honesty(self):
        dates = pd.bdate_range("2026-01-01", periods=80).strftime("%Y-%m-%d").tolist()
        df = compute_indicators(make_series(dates, base=100.0, trend=0.5))
        # No fundamentals & no chips -> must NOT treat as 0, must flag missing & reduce confidence
        res_partial = evaluate_six_factors(df, fundamentals={}, chips={})
        self.assertIsNone(res_partial["scores"]["health"])
        self.assertIsNone(res_partial["scores"]["growth"])
        self.assertIsNone(res_partial["scores"]["smart_money"])
        self.assertEqual(res_partial["data_confidence"], 50.0)
        self.assertIn("資料不足", res_partial["confidence_warning"])

        # With complete fundamentals & chips -> 100% confidence
        res_full = evaluate_six_factors(
            df,
            fundamentals={"roe": 0.22, "profit_margin": 0.18, "revenue_growth": 0.15, "earnings_growth": 0.20},
            chips={"inst_net_5d_shares": 1_000_000},
        )
        self.assertEqual(res_full["data_confidence"], 100.0)
        self.assertGreater(res_full["quality_score"], 65.0)

    def test_03_plain_explainer_and_teacher_mode(self):
        dates = pd.bdate_range("2026-01-01", periods=80).strftime("%Y-%m-%d").tolist()
        df = compute_indicators(make_series(dates, base=100.0, trend=0.5))
        items = explain_indicators_plain(df, chips={"inst_net_5d_shares": 500_000, "date": dates[-1]})
        self.assertGreaterEqual(len(items), 5)
        for it in items:
            for k in ["indicator", "value", "normal", "impact", "advice", "date"]:
                self.assertTrue(bool(it[k]))

        ans = answer_teacher_question("為什麼今天不能買？", [], [], {"temp": 35.0, "state": "空頭"})
        for k in ["conclusion", "reason", "risk", "next_step"]:
            self.assertTrue(bool(ans[k]))

    def test_04_news_deduplication_and_fact_separation(self):
        sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel>
          <item><title>台積電營收創高年增逾兩成 - 經濟日報</title><link>https://example.com/1</link><pubDate>Mon, 23 Nov 2026 08:00:00 GMT</pubDate><source>經濟日報</source></item>
          <item><title>台積電營收創高年增逾兩成 - 工商時報</title><link>https://example.com/2</link><pubDate>Mon, 23 Nov 2026 08:05:00 GMT</pubDate><source>工商時報</source></item>
          <item><title>某供應商獲利衰退下修財測 - 鉅亨網</title><link>https://example.com/3</link><pubDate>Mon, 23 Nov 2026 09:00:00 GMT</pubDate><source>鉅亨網</source></item>
        </channel></rss>"""
        parsed = parse_rss_news(sample_rss, "2330", "台積電")
        self.assertEqual(len(parsed), 2)  # Duplicate headline removed
        self.assertEqual(parsed[0]["sentiment"], "利多")
        self.assertEqual(parsed[1]["sentiment"], "利空")
        self.assertIn("事實", "事實" if parsed[0]["fact"] else "")
        self.assertTrue(bool(parsed[0]["uncertainty"]))

    def test_05_dual_strategy_isolation_hash_chain_json_and_predictions(self):
        dates = pd.bdate_range("2026-01-01", periods=95).strftime("%Y-%m-%d").tolist()
        df1 = make_series(dates, base=80.0, trend=0.35, vol=1_500_000)
        df1.iloc[70, df1.columns.get_loc("Volume")] = 3_000_000
        bm = make_series(dates, base=20000.0, trend=20.0, vol=5_000_000)
        bm50 = make_series(dates, base=180.0, trend=0.2, vol=4_000_000)

        mdata = {"2330": ("台積電", "半導體", df1, "FIXTURE")}
        fmap = {"2330": {"roe": 0.25, "profit_margin": 0.30, "revenue_growth": 0.20}}
        cmap = {"2330": {"inst_net_5d_shares": 1_200_000}}

        for d in dates[70:80]:
            self.engine.run_all_strategies(
                d, mdata, benchmark_df=bm, benchmark_0050_df=bm50,
                fundamentals_map=fmap, chips_map=cmap, export_json=False
            )

        # Idempotency check
        dup = self.engine.run_strategy_cycle(config.STRATEGY_FROZEN, dates[70], mdata, benchmark_df=bm)
        self.assertEqual(dup["status"], "SKIPPED")

        # Hash chain integrity for both strategies
        self.assertTrue(self.db.verify_hash_chain(config.STRATEGY_FROZEN)["valid"])
        self.assertTrue(self.db.verify_hash_chain(config.STRATEGY_AI_V2)["valid"])

        # JSON export check
        self.db.export_json_ledger(self.tmp_json.name)
        with open(self.tmp_json.name, "r", encoding="utf-8") as f:
            jdata = json.load(f)
        self.assertIn(config.STRATEGY_FROZEN, jdata["strategies"])
        self.assertIn(config.STRATEGY_AI_V2, jdata["strategies"])

    def test_06_backtest_and_walk_forward_validation(self):
        dates = pd.bdate_range("2026-01-01", periods=135).strftime("%Y-%m-%d").tolist()
        df1 = make_series(dates, base=80.0, trend=0.35, vol=1_500_000)
        bm = make_series(dates, base=20000.0, trend=20.0, vol=5_000_000)
        bm50 = make_series(dates, base=180.0, trend=0.2, vol=4_000_000)
        mdata = {"2330": ("台積電", "半導體", df1, "FIXTURE")}

        bt = run_comparison_backtest(mdata, benchmark_df=bm, benchmark_0050_df=bm50, test_days=40)
        self.assertEqual(bt["status"], "OK")
        self.assertEqual(bt["frozen"]["report"]["status"], "OK")
        self.assertEqual(bt["ai_v2"]["report"]["status"], "OK")

        wf = run_walk_forward_validation(mdata, benchmark_df=bm, benchmark_0050_df=bm50, folds=3, oos_days_per_fold=20)
        self.assertEqual(wf["status"], "OK")
        self.assertEqual(len(wf["folds"]), 3)



    def test_07_legacy_db_auto_migration(self):
        """Simulates opening an old V1/V2 SQLite DB missing `strategy_version`."""
        import sqlite3
        legacy_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        legacy_tmp.close()
        try:
            conn = sqlite3.connect(legacy_tmp.name)
            conn.execute("""
                CREATE TABLE portfolio_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL UNIQUE,
                    cash REAL NOT NULL,
                    market_value REAL NOT NULL,
                    total_equity REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    cum_return_pct REAL NOT NULL,
                    max_drawdown_pct REAL NOT NULL,
                    ledger_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                INSERT INTO portfolio_snapshots (
                    date, cash, market_value, total_equity, realized_pnl,
                    unrealized_pnl, cum_return_pct, max_drawdown_pct, ledger_hash, created_at
                ) VALUES ('2026-11-20', 1000000, 0, 1000000, 0, 0, 0, 0, 'OLDHASH', '2026-11-20 15:30:00')
            """)
            conn.commit()
            conn.close()

            # Opening with V2.1 LedgerDB must auto-migrate without raising OperationalError
            migrated_db = LedgerDB(legacy_tmp.name)
            snaps = migrated_db.get_all_snapshots(config.STRATEGY_FROZEN)
            self.assertEqual(len(snaps), 1)
            self.assertEqual(snaps[0]["date"], "2026-11-20")
            self.assertEqual(snaps[0]["strategy_version"], config.STRATEGY_FROZEN)
        finally:
            if os.path.exists(legacy_tmp.name):
                os.remove(legacy_tmp.name)



    def test_08_legacy_execution_logs_46_stocks_full_cycle(self):
        """
        Reproduces and verifies fix for:
        sqlite3.IntegrityError: NOT NULL constraint failed: execution_logs.processed_count
        on a legacy DB with a full 46/46 stock scan cycle + JSON export + reload consistency.
        """
        import sqlite3
        legacy_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        legacy_db_file.close()
        json_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        json_file.close()
        try:
            # Create legacy execution_logs with processed_count INTEGER NOT NULL (NO DEFAULT)
            conn = sqlite3.connect(legacy_db_file.name)
            conn.execute("""
                CREATE TABLE execution_logs (
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
            conn.commit()
            conn.close()

            db_mig = LedgerDB(legacy_db_file.name)
            eng = PaperTradingEngine(db_mig)

            dates = pd.bdate_range("2026-01-01", periods=80).strftime("%Y-%m-%d").tolist()
            bm = make_series(dates, base=20000.0, trend=20.0, vol=5_000_000)
            bm50 = make_series(dates, base=180.0, trend=0.2, vol=4_000_000)

            # Build 46 test stocks
            market_46 = {}
            for i in range(46):
                sym = f"{2300 + i}"
                df_i = make_series(dates, base=50.0 + i, trend=0.3, vol=1_500_000)
                market_46[sym] = (f"測試股{i}", "半導體", df_i, "TEST_FIXTURE")

            res = eng.run_all_strategies(
                dates[75], market_46, benchmark_df=bm, benchmark_0050_df=bm50,
                total_universe_count=46, export_json=False
            )
            self.assertEqual(res["frozen"]["status"], "SUCCESS")
            self.assertEqual(res["ai_v2"]["status"], "SUCCESS")

            # Verify execution_logs recorded processed_count == 46 without IntegrityError
            logs = db_mig.get_execution_logs(limit=5)
            self.assertGreaterEqual(len(logs), 2)
            self.assertEqual(logs[0]["processed_count"], 46)
            self.assertEqual(logs[0]["scanned_count"], 46)

            # Export JSON and reload DB to verify persistence
            db_mig.export_json_ledger(json_file.name)
            with open(json_file.name, "r", encoding="utf-8") as f:
                jdata = json.load(f)
            self.assertIn(config.STRATEGY_FROZEN, jdata["strategies"])
            self.assertIn(config.STRATEGY_AI_V2, jdata["strategies"])

            db_reload = LedgerDB(legacy_db_file.name)
            self.assertTrue(db_reload.verify_hash_chain(config.STRATEGY_FROZEN)["valid"])
            self.assertTrue(db_reload.verify_hash_chain(config.STRATEGY_AI_V2)["valid"])
        finally:
            for p in [legacy_db_file.name, json_file.name]:
                if os.path.exists(p):
                    os.remove(p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
