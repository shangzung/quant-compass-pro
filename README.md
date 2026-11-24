# Quant Compass AI Ultimate V2.0

下一世代台股 AI 智慧投資決策平台：透過紅燈、黃燈、綠燈、灰燈與白話解說，幫助投資人看懂市場溫度、篩選強勢好股、計算進出場與停損風險，並以雙版本獨立模擬帳本與 Walk-Forward 回測驗證策略有效性。

> ⚠️ **免責聲明**：本系統僅供模擬交易與量化研究，不連接券商執行真實下單。符合策略條件不代表保證獲利，歷史測試結果不代表未來績效。

## 安裝與啟動
1. 安裝套件：
   ```bash
   pip install -r requirements.txt
   ```
2. 執行自動化測試套件：
   ```bash
   python test_suite.py
   ```
3. 啟動 Web 介面（桌面與手機響應式）：
   ```bash
   python -m streamlit run app.py
   ```
   或直接雙擊 `run_ui.bat`。
4. 執行每日排程腳本（同時更新 `QC-PT-1.0-FROZEN` 與 `QC-AI-2.0` 雙帳本）：
   ```bash
   python daily_runner.py
   ```
