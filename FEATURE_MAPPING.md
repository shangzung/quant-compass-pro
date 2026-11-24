# 原有功能與新版功能對照表（保護原有系統升級報告）

原始專案備份位置：`backup_original_v2_web/`（可隨時完整還原）。

| 模組 / 功能 | 原版 Quant Compass Pro v2 | 升級版 Quant Compass AI Ultimate V2.0 | 保護狀態 |
| :--- | :--- | :--- | :--- |
| 基準策略 | 單一策略寫死在 `strategy.py` | 完整鎖定為 `QC-PT-1.0-FROZEN`，與新版 `QC-AI-2.0` 獨立平行運作與比較 | ✅ 完整保留並隔離 |
| 強勢股雷達 | 表格列出 StrengthScore 與 RS20 | 保留雷達並升級為「6 大評分 + 品質/訊號/可信度分離 + 10 項交易計畫」 | ✅ 保留並升級 |
| 歷史回測 | 單策略歷史回測 | 升級為雙策略比較（Frozen vs AI-2.0 vs 0050）+ 12 項完整驗證指標 | ✅ 保留並升級 |
| Walk-Forward 回測 | 無 | 新增分段樣本外（Out-of-Sample）Walk-Forward 驗證引擎 | 🆕 新增 |
| 模擬交易與帳本 | 單策略 SQLite + SHA-256 | 雙策略獨立 SQLite + SHA-256 鏈驗證 + 同步輸出 `QuantCompass/quant_compass_paper_ledger.json` | ✅ 保留並升級 |
| 首頁 Dashboard | 指標卡 + 表格 | 升級為 Mobile-First 卡片式 6 區首頁（市場溫度、四色燈號、推薦/觀察/避開、風險警示） | 🆕 升級 |
| AI 白話解說與老師模式 | 無 | 新增 5 要素指標白話解說引擎 + 4 段式 AI 老師問答 | 🆕 新增 |
| AI 新聞分析 | 無 | 新增 Google News RSS 即時抓取、標題去重、事實/推論/不確定性分離 | 🆕 新增 |
| AI 決策品質追蹤 | 無 | 新增不可竄改 `ai_predictions` 表，自動追蹤 5/10/20 日真實表現與停損停利 | 🆕 新增 |
| 資料品質監控 | 簡單 log | 新增 `data_quality_logs` 與缺失資料降級警示（灰燈暫停交易） | 🆕 新增 |
