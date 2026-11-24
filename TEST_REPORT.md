# Quant Compass AI Ultimate V2.0 — 功能測試報告

## 實際執行自動化測試 (`python test_suite.py`)
- 執行結果：**6 / 6 項全部通過 (OK)**
- 驗證項目：
  1. `test_01_causal_indicators_and_market_temperature`：驗證 MA20/MA60/RSI14/ATR14/MACD/KD/RS20 嚴格無未來函數，並正確計算市場溫度（0–100）與多頭判斷。
  2. `test_02_six_factor_scoring_missing_data_honesty`：驗證 6 大評分在財報/籌碼缺失時不補零分，明確降低可信度並輸出「資料不足，評分可信度降低。」警語。
  3. `test_03_plain_explainer_and_teacher_mode`：驗證 5 要素白話指標解說與 AI 老師 4 段式結構回覆。
  4. `test_04_news_deduplication_and_fact_separation`：驗證 RSS 新聞去重（同標題不重複計算）、情緒分類與事實/推論/不確定性分離。
  5. `test_05_dual_strategy_isolation_hash_chain_json_and_predictions`：驗證 `QC-PT-1.0-FROZEN` 與 `QC-AI-2.0` 雙策略獨立帳本、防重複成交冪等性、SHA-256 雜湊鏈驗證與 `quant_compass_paper_ledger.json` 匯出。
  6. `test_06_backtest_and_walk_forward_validation`：驗證雙策略歷史比較回測與 3-Fold Walk-Forward 樣本外驗證。

## 需於本機/雲端連網環境驗證之項目
- 即時連網抓取 TWSE OpenAPI、yfinance、FinMind 籌碼與 Google News RSS（沙盒環境無對外網路權限）。
- Streamlit 響應式介面於手機、平板與桌面瀏覽器之實際渲染。
