"""
Quant Compass Pro v2.0 — Web-Operated Strong-Stock Screener & Paper Trading System
Fixed Dark/Light Mode contrast + One-Click Web Execution + Backtest & Strategy Diagnosis.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from backtester import run_historical_backtest
from daily_runner import run_live_scan
from database import LedgerDB
from reporter import generate_performance_report

st.set_page_config(
    page_title="Quant Compass Pro v2 — 台股強勢股與模擬交易系統",
    page_icon="🧭",
    layout="wide",
)

# Theme-safe high-contrast CSS (works in both Dark Mode & Light Mode)
st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.25);
        padding: 16px 20px;
        border-radius: 14px;
    }
    div[data-testid="stMetricLabel"] > div {
        color: var(--text-color) !important;
        opacity: 0.85;
        font-weight: 600;
    }
    div[data-testid="stMetricValue"] > div {
        color: var(--text-color) !important;
        font-weight: 700;
    }
    .disclaimer-box {
        background-color: rgba(245, 158, 11, 0.15);
        border-left: 4px solid #F59E0B;
        color: var(--text-color);
        padding: 12px 16px;
        border-radius: 8px;
        font-size: 14px;
        margin-bottom: 18px;
    }
    .badge-BUY { background:#166534; color:#DCFCE7; padding:4px 10px; border-radius:999px; font-weight:600; font-size:12px; }
    .badge-HOLD { background:#1E40AF; color:#DBEAFE; padding:4px 10px; border-radius:999px; font-weight:600; font-size:12px; }
    .badge-WAIT { background:#854D0E; color:#FEF9C3; padding:4px 10px; border-radius:999px; font-weight:600; font-size:12px; }
    .badge-SELL { background:#991B1B; color:#FEE2E2; padding:4px 10px; border-radius:999px; font-weight:600; font-size:12px; }
</style>
""", unsafe_allow_html=True)

db = LedgerDB(config.DB_PATH)
report = generate_performance_report(db)
snaps = db.get_all_snapshots()
trades = db.get_all_trades()

st.title("🧭 Quant Compass Pro v2.0 (Web)")
st.caption(f"台股動態強勢股雷達 × 自動模擬交易 × 策略勝率診斷 | 版本：{config.STRATEGY_VERSION}")

st.markdown(
    '<div class="disclaimer-box">⚠️ <strong>重要聲明：</strong>本系統僅供模擬交易與量化策略研究，非真實投資建議或券商委託紀錄。</div>',
    unsafe_allow_html=True,
)

# Sidebar Controls (Pure Web Operation)
st.sidebar.header("⚡ 雲端 / Web 操作中心")
scan_count = st.sidebar.slider("動態掃描活躍台股檔數", min_value=20, max_value=80, value=40, step=10)

if st.sidebar.button("🚀 立即掃描台股並執行今日模擬交易", type="primary", use_container_width=True):
    prog = st.progress(0.0, text="正在連線取得台灣加權指數與活躍強勢股名單...")
    def _cb(pct, msg):
        prog.progress(min(pct, 1.0), text=msg)
    out = run_live_scan(top_n=scan_count, progress_callback=_cb)
    prog.empty()
    if out.get("status") == "ERROR":
        st.error(out["message"])
    else:
        st.session_state["last_market_data"] = out["market_data"]
        st.session_state["last_benchmark_df"] = out["benchmark_df"]
        res = out["result"]
        if res["status"] == "SUCCESS":
            st.success(f"✅ {res['date']} 掃描完成！處理 {res['processed']} 檔台股，大盤狀態：{res['market_regime']}。")
        else:
            st.info(f"ℹ️ {res.get('message', res)}")
        st.rerun()

page = st.sidebar.radio(
    "導覽選單",
    ["今日模擬交易總覽", "🔥 強勢股雷達排行", "🧪 歷史回測與勝率診斷", "📜 歷史交易與帳本驗證"],
)

if page == "今日模擬交易總覽":
    latest = snaps[-1] if snaps else None
    prev = snaps[-2] if len(snaps) >= 2 else None
    today_pnl = (latest["total_equity"] - prev["total_equity"]) if (latest and prev) else (latest["total_equity"] - config.INITIAL_CAPITAL if latest else 0.0)
    open_trades = db.get_open_trades()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("虛擬總資產 (TWD)", f"${latest['total_equity']:,.0f}" if latest else f"${config.INITIAL_CAPITAL:,.0f}")
    c2.metric("今日損益", f"${today_pnl:+,.0f}")
    c3.metric("累積報酬率", f"{latest['cum_return_pct']:+.2f}%" if latest else "0.00%")
    c4.metric("現金餘額", f"${latest['cash']:,.0f}" if latest else f"${config.INITIAL_CAPITAL:,.0f}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("持有股票數", f"{len(open_trades)} / {config.MAX_POSITIONS}")
    c6.metric("已平倉勝率", f"{report.get('win_rate_pct', 0.0):.1f}%" if report["status"] == "OK" else "0.0%")
    c7.metric("每筆期望值", f"${report.get('expectancy_twd', 0.0):+,.0f}" if report["status"] == "OK" else "$0")
    c8.metric("最大回撤 (MDD)", f"{latest['max_drawdown_pct']:.2f}%" if latest else "0.00%")

    if latest:
        st.caption(f"最新交易日：{latest['date']} ｜ 大盤濾網狀態：**{latest.get('market_regime', 'N/A')}**")

    st.subheader("今日 AI 交易建議 (依強勢分數排序)")
    if latest:
        today_sigs = db.get_all_signals(date_str=latest["date"])
        actionable = [s for s in today_sigs if s["signal_type"] in ("BUY", "HOLD", "SELL")]
        if not actionable:
            st.info(f"{latest['date']} 無符合所有風控與大盤濾網的 BUY / HOLD 標的，系統維持觀望 (WAIT)。您可至「🔥 強勢股雷達排行」查看當日最強個股分數。")
        else:
            for s in actionable[:10]:
                with st.container(border=True):
                    a, b, c = st.columns([2, 2, 3])
                    a.markdown(f"### {s['name']} ({s['symbol']})")
                    a.caption(f"收盤: {s['signal_price']:.2f} | 強度: **{s['strength_score']:.1f}** | RS20: **{s['rs_20']:+.1f}%**")
                    b.markdown(f"<span class='badge-{s['signal_type']}'>{s['signal_type']}</span>", unsafe_allow_html=True)
                    b.caption(f"建議股數: {s['suggested_shares']:,} 股 | RR: {s['rr_ratio']}")
                    c.write(f"停損: **{s['stop_loss']}** ｜ 停利: **{s['take_profit']}**")
                    c.caption(s["reason"])
    else:
        st.info("尚未執行掃描。請點擊左側「🚀 立即掃描台股並執行今日模擬交易」開始！")

elif page == "🔥 強勢股雷達排行":
    st.subheader("台股強勢股綜合評分排行 (Strength Score + RS20)")
    latest = snaps[-1] if snaps else None
    if not latest:
        st.info("請先點擊左側按鈕執行掃描。")
    else:
        sigs = db.get_all_signals(date_str=latest["date"])
        df_s = pd.DataFrame(sigs)[[
            "symbol", "name", "signal_type", "strength_score", "rs_20",
            "signal_price", "rsi", "stop_loss", "take_profit", "reason"
        ]]
        df_s.columns = ["代碼", "名稱", "決策", "強勢分數(0-100)", "20日相對強度RS(%)", "收盤價", "RSI14", "停損價", "停利價", "判斷理由"]
        st.dataframe(df_s, use_container_width=True, hide_index=True)

elif page == "🧪 歷史回測與勝率診斷":
    st.subheader("策略歷史回測與自動勝率/期望值診斷")
    st.write("直接用剛抓到的真實台股歷史資料，回測過去數十個交易日的模擬買賣表現，驗證策略是否具備正期望值。")
    test_days = st.slider("回測交易日數", min_value=20, max_value=90, value=60, step=10)

    if st.button("▶️ 執行真實行情歷史回測", type="primary"):
        mdata = st.session_state.get("last_market_data")
        bmdf = st.session_state.get("last_benchmark_df")
        if not mdata:
            with st.spinner("尚無快取行情，正在抓取台股資料..."):
                out = run_live_scan(top_n=scan_count)
                if out.get("status") == "ERROR":
                    st.error(out["message"])
                    st.stop()
                mdata, bmdf = out["market_data"], out["benchmark_df"]
                st.session_state["last_market_data"] = mdata
                st.session_state["last_benchmark_df"] = bmdf

        with st.spinner(f"正在以嚴格無未來函數模式回測過去 {test_days} 個交易日..."):
            bt = run_historical_backtest(mdata, benchmark_df=bmdf, test_days=test_days)

        if bt["status"] != "OK":
            st.warning(bt["message"])
        else:
            r = bt["report"]
            st.markdown("### 🧠 AI 策略診斷結論")
            for note in bt["diagnosis"]:
                st.markdown(f"- {note}")

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("回測總報酬率", f"{r['total_return_pct']:+.2f}%")
            k2.metric("已平倉勝率", f"{r['win_rate_pct']:.1f}% ({r['wins']}勝/{r['losses']}敗)")
            k3.metric("每筆期望值", f"${r['expectancy_twd']:+,.0f}")
            k4.metric("最大回撤 (MDD)", f"{r['max_drawdown_pct']:.2f}%")

            df_eq = pd.DataFrame(bt["snapshots"])
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_eq["date"], y=df_eq["total_equity"], mode="lines", name="策略淨值 (TWD)"))
            fig.update_layout(title="歷史回測資產淨值曲線", template="plotly_dark", xaxis_title="日期", yaxis_title="TWD")
            st.plotly_chart(fig, use_container_width=True)

            if bt["trades"]:
                st.markdown("### 回測成交明細")
                st.dataframe(pd.DataFrame(bt["trades"])[[
                    "symbol", "name", "status", "buy_date", "buy_price", "shares",
                    "sell_date", "sell_price", "total_cost", "net_pnl", "return_pct", "exit_reason"
                ]], use_container_width=True, hide_index=True)

elif page == "📜 歷史交易與帳本驗證":
    st.subheader("模擬交易明細")
    if trades:
        st.dataframe(pd.DataFrame(trades)[[
            "trade_id", "symbol", "name", "status", "buy_date", "buy_price",
            "shares", "sell_date", "sell_price", "total_cost", "net_pnl",
            "return_pct", "holding_days", "exit_reason"
        ]], use_container_width=True, hide_index=True)
    else:
        st.info("目前尚無模擬成交紀錄。")

    st.subheader("每日帳本 SHA-256 完整性驗證")
    if snaps:
        st.dataframe(pd.DataFrame(snaps)[["date", "total_equity", "market_regime", "ledger_hash", "created_at"]], use_container_width=True, hide_index=True)
