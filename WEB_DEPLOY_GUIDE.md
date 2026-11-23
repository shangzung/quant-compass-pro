# 如何免費部署到 Web（手機與電腦隨時透過瀏覽器操作）

1. 將整個 `Quant_Compass_Pro_v2_Web` 資料夾上傳到您的 **GitHub** 儲存庫（Repository）。
2. 前往 [Streamlit Community Cloud](https://share.streamlit.io/) 並使用 GitHub 登入。
3. 點選 **New app** → 選擇剛剛上傳的 Repository，Main file path 填 `app.py` → 點選 **Deploy!**。
4. 幾分鐘後就會獲得一個專屬網址（`https://你的專案.streamlit.app`），以後無論在電腦或手機打開瀏覽器即可一鍵掃描台股、查看強勢股排行、執行回測與追蹤模擬帳本。
5. （選用）若希望每天台股收盤後 15:30 **全自動背景跑完模擬交易並存檔**，專案內已附 `.github/workflows/daily_paper_trade.yml`，在 GitHub Repository 的 **Actions** 啟用即可免費每天定時自動執行。
