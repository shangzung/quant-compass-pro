"""
Quant Compass AI Ultimate V2.1
Premium Fintech + Apple Human Interface Design + TradingView Dark Mode
Mobile-First Responsive Web Platform (UI strictly separated from Trading Engine).
"""
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import config
from backtester import run_comparison_backtest, run_walk_forward_validation
from daily_runner import run_live_scan
from database import LedgerDB
from indicators import compute_indicators, compute_market_temperature
from news_analyzer import fetch_stock_news
from plain_explainer import answer_teacher_question, explain_indicators_plain
from reporter import generate_performance_report
from risk_manager import evaluate_portfolio_risk

st.set_page_config(
    page_title="Quant Compass AI Ultimate V2.1",
    page_icon="Q",
    layout="wide",
    initial_sidebar_state="auto",
)

# Premium Fintech Deep Navy-Black CSS (No excessive gradients or emojis)
st.markdown("""
<style>
    .stApp { background-color: #070B14; color: #E6EDF3; }
    header[data-testid="stHeader"] {
        background-color: rgba(7, 11, 20, 0.92) !important;
        backdrop-filter: blur(8px);
        z-index: 999;
    }
    [data-testid="stAppViewContainer"] {
        overflow-x: hidden;
    }
    [data-testid="stMainBlockContainer"],
    .block-container {
        padding-top: 4.5rem !important;
        padding-bottom: 2.5rem !important;
        max-width: 1240px;
    }
    div[data-testid="stMetric"] {
        background-color: #0F1624;
        border: 1px solid #1E293B;
        padding: 14px 16px;
        border-radius: 14px;
    }
    div[data-testid="stMetricLabel"] > div { color: #94A3B8 !important; font-weight: 500; font-size: 0.82rem; }
    div[data-testid="stMetricValue"] > div { color: #F8FAFC !important; font-weight: 700; font-size: 1.4rem; }
    .qc-ticker {
        background-color: #0D1422;
        border: 1px solid #1E293B;
        border-radius: 12px;
        padding: 10px 16px;
        margin-bottom: 16px;
        display: flex;
        flex-wrap: wrap;
        gap: 18px;
        align-items: center;
        justify-content: space-between;
        font-size: 0.86rem;
    }
    .qc-card {
        background-color: #0F1624;
        border: 1px solid #1E293B;
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 14px;
        transition: border-color 0.2s ease;
    }
    .qc-card:hover { border-color: #334155; }
    .qc-hero {
        background-color: #11192B;
        border: 1px solid #23324D;
        border-radius: 18px;
        padding: 22px 24px;
        margin-bottom: 18px;
    }
    .pill-green { background:#052E1F; color:#34D399; border:1px solid #059669; padding:3px 10px; border-radius:999px; font-weight:600; font-size:0.78rem; }
    .pill-yellow { background:#332206; color:#FBBF24; border:1px solid #D97706; padding:3px 10px; border-radius:999px; font-weight:600; font-size:0.78rem; }
    .pill-red { background:#360F15; color:#F87171; border:1px solid #DC2626; padding:3px 10px; border-radius:999px; font-weight:600; font-size:0.78rem; }
    .pill-grey { background:#1E293B; color:#CBD5E1; border:1px solid #475569; padding:3px 10px; border-radius:999px; font-weight:600; font-size:0.78rem; }
    .pill-grade { background:#102240; color:#60A5FA; border:1px solid #2563EB; padding:3px 9px; border-radius:6px; font-weight:700; font-size:0.78rem; }
    .qc-notice {
        background-color: #131B2E;
        border-left: 3px solid #2962FF;
        color: #CBD5E1;
        padding: 9px 14px;
        border-radius: 8px;
        font-size: 0.84rem;
        margin-bottom: 16px;
    }
    @media (max-width: 768px) {
        .qc-card, .qc-hero { padding: 14px 15px; border-radius: 14px; }
        .qc-ticker { gap: 10px; font-size: 0.8rem; }
    }
</style>
""", unsafe_allow_html=True)

# Session State Initialization
if "active_strategy" not in st.session_state:
    st.session_state["active_strategy"] = config.STRATEGY_AI_V2
if "scan_count" not in st.session_state:
    st.session_state["scan_count"] = 35
if "fetch_extra" not in st.session_state:
    st.session_state["fetch_extra"] = False
if "selected_symbol" not in st.session_state:
    st.session_state["selected_symbol"] = None
if "cancel_scan" not in st.session_state:
    st.session_state["cancel_scan"] = False
if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "今日市場"
if "is_scanning" not in st.session_state:
    st.session_state["is_scanning"] = False
if "dev_debug" not in st.session_state:
    st.session_state["dev_debug"] = False

db = LedgerDB(config.DB_PATH)
active_strategy = st.session_state["active_strategy"]

def light_pill(light: str) -> str:
    cls = {"綠燈": "pill-green", "黃燈": "pill-yellow", "紅燈": "pill-red"}.get(light, "pill-grey")
    return f"<span class='{cls}'>{light}</span>"

# ==============================================================================
# CLEAN PRODUCT SIDEBAR NAVIGATION (4 Categories — Engineering moved to Settings)
# ==============================================================================
st.sidebar.markdown("### Quant Compass AI")
st.sidebar.caption("Ultimate V2.1 · 智慧投資決策平台")

nav_groups = {
    "投資首頁": ["今日市場", "AI 今日推薦", "我的模擬投資"],
    "AI 投資中心": ["強勢股雷達", "AI 選股", "AI 老師", "新聞與基本面"],
    "交易與績效": ["模擬交易", "交易帳本", "策略回測", "策略驗證", "AI 績效追蹤"],
    "系統管理": ["資料品質", "策略版本", "系統設定"],
}

group_choice = st.sidebar.selectbox("主選單", list(nav_groups.keys()), label_visibility="collapsed")
page = st.sidebar.radio("頁面", nav_groups[group_choice], label_visibility="collapsed")

# Allow Stock Detail override when user clicks any stock card
if st.session_state.get("selected_symbol"):
    if st.sidebar.button("← 返回清單檢視", use_container_width=True):
        st.session_state["selected_symbol"] = None
        st.rerun()

# Load Data
snaps = db.get_all_snapshots(active_strategy)
latest_snap = snaps[-1] if snaps else None
open_trades = db.get_open_trades(active_strategy)
all_trades = db.get_all_trades(active_strategy)
today_sigs = db.get_signals(active_strategy, date_str=latest_snap["date"]) if latest_snap else []
cached_scan = st.session_state.get("last_scan")

# Market Temperature
if cached_scan:
    market_temp = compute_market_temperature(cached_scan.get("benchmark_df"), cached_scan.get("latest_date", latest_snap["date"] if latest_snap else ""), breadth=cached_scan.get("breadth"))
elif latest_snap:
    mt = float(latest_snap.get("market_temp", 50.0))
    st_lbl = "多頭" if mt >= 55 else ("空頭" if mt < 40 else "盤整")
    market_temp = {
        "temp": mt, "state": st_lbl,
        "risk": "高（空頭警戒）" if mt < 40 else ("中高（留意追高）" if mt >= 75 else "中低（可依紀律操作）"),
        "trend_desc": latest_snap.get("market_regime", "N/A"),
        "vol_change_pct": 0.0, "data_ok": True,
        "summary": f"目前市場溫度 {mt:.0f} 分，市場偏向{st_lbl}。請依燈號與停損紀律操作，不盲目追高。",
    }
else:
    market_temp = {
        "temp": 50.0, "state": "尚未更新", "risk": "等待市場資料",
        "trend_desc": "尚未取得最新交易日資料", "vol_change_pct": 0.0,
        "data_ok": False, "summary": "請點擊右上角「更新市場資料」取得最新台股真實行情與 AI 判斷。",
    }

# ==============================================================================
# A. TOP MARKET TICKER BAR + NON-BLOCKING SCAN TRIGGER
# ==============================================================================
top_c1, top_c2 = st.columns([5, 1.3])
with top_c1:
    if cached_scan and cached_scan.get("taiex"):
        tx = cached_scan["taiex"]
        br = cached_scan["breadth"]
        chg_color = "#EF4444" if tx["chg"] >= 0 else "#22C55E"
        st.markdown(f"""
        <div class="qc-ticker">
            <div><span style="color:#94A3B8;">台灣加權指數</span> <strong style="font-size:1.05rem;">{tx['close']:,.2f}</strong>
                <span style="color:{chg_color}; font-weight:600; margin-left:6px;">{tx['chg']:+.2f} ({tx['chg_pct']:+.2f}%)</span></div>
            <div><span style="color:#94A3B8;">掃描漲跌家數</span> <span style="color:#EF4444;">{br['advancers']} 漲</span> / <span style="color:#22C55E;">{br['decliners']} 跌</span></div>
            <div><span style="color:#94A3B8;">市場溫度</span> <strong>{market_temp['temp']:.0f} / 100</strong></div>
            <div><span style="color:#94A3B8;">更新時間</span> {cached_scan.get('updated_at', latest_snap['date'] if latest_snap else '未更新')}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        upd = latest_snap["date"] if latest_snap else "等待首次更新"
        st.markdown(f"""
        <div class="qc-ticker">
            <div><span style="color:#94A3B8;">台灣加權指數</span> <strong>{market_temp['state']}</strong></div>
            <div><span style="color:#94A3B8;">市場溫度</span> <strong>{market_temp['temp']:.0f} / 100</strong></div>
            <div><span style="color:#94A3B8;">帳本最新交易日</span> {upd}</div>
            <div><span style="color:#94A3B8;">策略版本</span> {active_strategy}</div>
        </div>
        """, unsafe_allow_html=True)

with top_c2:
    run_scan_clicked = st.button(
        "掃描中..." if st.session_state["is_scanning"] else "更新市場資料",
        type="primary",
        use_container_width=True,
        disabled=st.session_state["is_scanning"],
    )

# Non-blocking In-Place Progress Banner (preserves existing UI below)
if run_scan_clicked and not st.session_state["is_scanning"]:
    st.session_state["is_scanning"] = True
    st.session_state["cancel_scan"] = False
    status_box = st.status("正在更新市場資料與 AI 分析...", expanded=True)
    prog_bar = status_box.progress(0.0)
    stage_txt = status_box.empty()
    if status_box.button("取消掃描"):
        st.session_state["cancel_scan"] = True

    def _on_progress(pct, stage, item, done, total):
        prog_bar.progress(min(max(pct, 0.0), 1.0))
        stage_txt.markdown(f"**{stage}** · 目前處理：`{item}`（{done}/{total}）")

    try:
        out = run_live_scan(
            top_n=st.session_state["scan_count"],
            fetch_extra_factors=st.session_state["fetch_extra"],
            progress_callback=_on_progress,
            cancel_check=lambda: st.session_state.get("cancel_scan", False),
        )
    finally:
        st.session_state["is_scanning"] = False

    if out.get("status") == "OK":
        st.session_state["last_scan"] = out
        status_box.update(label=f"更新完成（{out['latest_date']} · 涵蓋率 {out['coverage_pct']:.1f}%）", state="complete", expanded=False)
        st.rerun()
    elif out.get("status") == "CANCELLED":
        status_box.update(label=out["message"], state="error", expanded=False)
    else:
        status_box.update(label=f"更新失敗：{out.get('message')}", state="error", expanded=True)
        if st.session_state.get("dev_debug") and out.get("traceback"):
            st.code(out["traceback"])

st.markdown(
    '<div class="qc-notice">模擬投資決策平台：僅使用虛擬資金進行策略驗證，不連接券商下單。符合綠燈條件不代表保證獲利，歷史測試結果不代表未來績效。</div>',
    unsafe_allow_html=True,
)

# ==============================================================================
# INDEPENDENT STOCK DETAIL PAGE (Triggered by clicking any stock)
# ==============================================================================
if st.session_state.get("selected_symbol"):
    sym = st.session_state["selected_symbol"]
    sig = next((s for s in today_sigs if s["symbol"] == sym), None)
    if not sig:
        st.warning("找不到該股票的最新分析紀錄。")
        st.session_state["selected_symbol"] = None
    else:
        col_back, col_title = st.columns([1, 6])
        if col_back.button("← 返回"):
            st.session_state["selected_symbol"] = None
            st.rerun()
        col_title.markdown(
            f"### {sig['name']} ({sig['symbol']}) &nbsp; {light_pill(sig['traffic_light'])} &nbsp; <span class='pill-grade'>AI 總評 {sig['quality_grade']} ({sig['quality_score']:.0f}分)</span>",
            unsafe_allow_html=True,
        )

        # Top KPI row
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("最新收盤價", f"{sig['signal_price']:.2f}", f"資料日 {sig['date']}")
        k2.metric("股票品質分數", f"{sig['quality_score']:.1f} / 100")
        k3.metric("交易訊號強度", f"{sig['signal_strength']:.1f} / 100")
        k4.metric("資料可信度", f"{sig['data_confidence']:.0f}%")

        # Price & Volume Chart (if cached)
        if cached_scan and sym in cached_scan.get("market_data", {}):
            _, _, raw_df, _ = cached_scan["market_data"][sym]
            ind_df = compute_indicators(raw_df, cached_scan.get("benchmark_df")).tail(90)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
            fig.add_trace(go.Candlestick(
                x=ind_df.index, open=ind_df["Open"], high=ind_df["High"],
                low=ind_df["Low"], close=ind_df["Close"], name="K線", increasing_line_color="#EF4444", decreasing_line_color="#22C55E"
            ), row=1, col=1)
            fig.add_trace(go.Scatter(x=ind_df.index, y=ind_df["MA20"], name="MA20", line=dict(color="#38BDF8", width=1.4)), row=1, col=1)
            fig.add_trace(go.Scatter(x=ind_df.index, y=ind_df["MA60"], name="MA60", line=dict(color="#F59E0B", width=1.4)), row=1, col=1)
            fig.add_trace(go.Bar(x=ind_df.index, y=ind_df["Volume"], name="成交量", marker_color="#334155"), row=2, col=1)
            fig.update_layout(
                template="plotly_dark", paper_bgcolor="#0F1624", plot_bgcolor="#0F1624",
                xaxis_rangeslider_visible=False, height=440, margin=dict(l=10, r=10, t=25, b=10)
            )
            st.plotly_chart(fig, use_container_width=True)

            # Plain-language indicators
            with st.expander("白話技術指標與法人解說", expanded=False):
                for ex in explain_indicators_plain(ind_df, cached_scan.get("chips_map", {}).get(sym)):
                    st.markdown(f"**{ex['indicator']}**（`{ex['value']}` · {ex['date']}）：{ex['impact']} → {ex['advice']}")

        # Actionable 10-Point Plan
        plan = json.loads(sig.get("plan_json") or "{}")
        if plan:
            st.markdown("#### AI 最終交易計畫")
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("建議買進區間", plan.get("ideal_entry_zone", "N/A"))
            p2.metric("停損價", f"{plan.get('stop_loss', 'N/A')}")
            p3.metric("第一 / 第二停利", f"{plan.get('tp1')} / {plan.get('tp2')}")
            p4.metric("風險報酬比", f"1 : {plan.get('rr_ratio', 0)}")
            st.markdown(f"""
            <div class="qc-card">
                <div><strong>建議股數 / 投入金額：</strong>{plan.get('suggested_shares', 0):,} 股（約 NT${plan.get('suggested_amount', 0):,.0f}）</div>
                <div><strong>最大可能虧損：</strong>NT${plan.get('max_possible_loss', 0):,.0f} ｜ <strong>預估交易成本：</strong>NT${plan.get('est_transaction_cost', 0):,.0f}</div>
                <div style="margin-top:6px; color:#FBBF24;"><strong>不建議買進條件 / 替代方案：</strong>{plan.get('fallback_plan')}</div>
            </div>
            """, unsafe_allow_html=True)

        # News on demand
        if st.button("載入該股最新財經新聞分析"):
            news_list = fetch_stock_news(sym, sig["name"], limit=4)
            if not news_list:
                st.info("目前無可追溯之最新新聞或網路受限。")
            else:
                for n in news_list:
                    st.markdown(f"- **[{n['sentiment']}]** [{n['title']}]({n['url']})（{n['source']} · {n['date']}）— {n['inference']}")
    st.stop()

# ==============================================================================
# MAIN VIEWS BY NAVIGATION
# ==============================================================================
greens = [s for s in today_sigs if s["traffic_light"] == "綠燈"]
yellows = [s for s in today_sigs if s["traffic_light"] == "黃燈"]
reds = [s for s in today_sigs if s["traffic_light"] == "紅燈"]
greys = [s for s in today_sigs if s["traffic_light"] == "灰燈"]

if page == "今日市場":
    # B. AI 今日市場判斷 (Core Hero Card)
    t_val = market_temp["temp"]
    t_col = "#EF4444" if t_val >= 55 else ("#22C55E" if t_val < 40 else "#FBBF24")
    st.markdown(f"""
    <div class="qc-hero">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px;">
            <div>
                <div style="color:#94A3B8; font-size:0.85rem; letter-spacing:0.5px;">AI 今日市場判斷</div>
                <div style="font-size:2rem; font-weight:800; color:{t_col}; margin-top:4px;">{market_temp['state']} · 市場溫度 {t_val:.0f}</div>
            </div>
            <div style="text-align:right;">
                <div style="color:#94A3B8; font-size:0.82rem;">市場風險評估</div>
                <div style="font-weight:600; color:#F8FAFC; margin-top:4px;">{market_temp['risk']}</div>
            </div>
        </div>
        <div style="margin-top:12px; color:#CBD5E1; font-size:0.95rem; line-height:1.55;">
            {market_temp['summary']}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # C. 今日投資決策 (Clickable Traffic Light Cards)
    st.markdown("#### 今日投資決策")
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("綠燈 · 符合買進", f"{len(greens)} 檔")
    d2.metric("黃燈 · 觀察等待", f"{len(yellows)} 檔")
    d3.metric("紅燈 · 建議避開", f"{len(reds)} 檔")
    d4.metric("灰燈 · 資料不足", f"{len(greys)} 檔")

    # D. AI 今日推薦股票 (Independent Actionable Cards)
    st.markdown("#### AI 今日推薦股票")
    if not greens:
        st.markdown('<div class="qc-card" style="color:#94A3B8;">目前適不適合買？<strong>暫不建議買進</strong>。今日無同時滿足趨勢、量能與 1:1.5 風報比的標的，保持現金耐心等待。</div>', unsafe_allow_html=True)
    else:
        for s in greens[:5]:
            with st.container(border=True):
                c_left, c_mid, c_right = st.columns([2.5, 3, 1.2])
                c_left.markdown(f"**{s['name']} ({s['symbol']})** &nbsp; {light_pill('綠燈')} &nbsp; <span class='pill-grade'>{s['quality_grade']}</span>", unsafe_allow_html=True)
                c_left.caption(f"現在適不適合買：符合策略條件（現價 {s['signal_price']:.2f} · 品質 {s['quality_score']:.0f} 分）")
                c_mid.markdown(f"進場 `{s['signal_price']:.2f}` ｜ 停損 `{s['stop_loss']}` ｜ 停利 `{s['take_profit']}` ｜ 風報比 `1:{s['rr_ratio']}`")
                c_mid.caption(s["reason"])
                if c_right.button("查看詳情", key=f"home_det_{s['symbol']}", use_container_width=True):
                    st.session_state["selected_symbol"] = s["symbol"]
                    st.rerun()

    # E. 我的模擬投資帳戶 & F. AI 風險警示
    col_acc, col_risk = st.columns([1.2, 1])
    with col_acc:
        st.markdown("#### 我的模擬投資帳戶（虛擬資金）")
        rep = generate_performance_report(db, active_strategy)
        cur_eq = latest_snap["total_equity"] if latest_snap else config.INITIAL_CAPITAL
        cur_cash = latest_snap["cash"] if latest_snap else config.INITIAL_CAPITAL
        cur_mv = latest_snap["market_value"] if latest_snap else 0.0
        a1, a2 = st.columns(2)
        a1.metric("目前總資產", f"NT${cur_eq:,.0f}", f"{latest_snap['cum_return_pct']:+.2f}%" if latest_snap else "0.00%")
        a2.metric("可用現金 / 持倉市值", f"NT${cur_cash:,.0f}", f"市值 NT${cur_mv:,.0f}")
    with col_risk:
        st.markdown("#### AI 風險警示")
        latest_prices = {s["symbol"]: s["signal_price"] for s in today_sigs}
        risk_info = evaluate_portfolio_risk(open_trades, cur_cash, cur_eq, market_temp, latest_prices)
        st.markdown(f"""
        <div class="qc-card">
            <div><strong>資金使用率：</strong>{risk_info['utilization_pct']:.1f}% ｜ <strong>總停損暴露：</strong>{risk_info['total_open_risk_pct']:.2f}%</div>
            <div style="margin-top:6px; color:{'#F87171' if risk_info['need_reduce'] else '#34D399'};">{risk_info['reduce_reason']}</div>
        </div>
        """, unsafe_allow_html=True)

elif page in ("AI 今日推薦", "AI 選股"):
    st.markdown(f"### {page}")
    tab_g, tab_y, tab_r = st.tabs([f"綠燈推薦 ({len(greens)})", f"黃燈觀察 ({len(yellows)})", f"紅燈避開 ({len(reds)})"])
    for tab, items, lbl in [(tab_g, greens, "綠燈"), (tab_y, yellows, "黃燈"), (tab_r, reds, "紅燈")]:
        with tab:
            if not items:
                st.caption(f"目前無{lbl}標的。")
            for s in items[:15]:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2.2, 3.5, 1.1])
                    c1.markdown(f"**{s['name']} ({s['symbol']})** {light_pill(lbl)}", unsafe_allow_html=True)
                    c1.caption(f"收盤 {s['signal_price']:.2f} · 品質 {s['quality_grade']} ({s['quality_score']:.0f}) · 可信度 {s['data_confidence']:.0f}%")
                    c2.write(s.get("missing_condition") or s["reason"])
                    if c3.button("詳細分析", key=f"sel_{lbl}_{s['symbol']}", use_container_width=True):
                        st.session_state["selected_symbol"] = s["symbol"]
                        st.rerun()

elif page in ("我的模擬投資", "模擬交易"):
    st.markdown("### 我的模擬投資帳戶（虛擬資金）")
    rep = generate_performance_report(db, active_strategy)
    if rep["status"] != "OK":
        st.info("尚無模擬帳戶紀錄，請點擊右上角「更新市場資料」啟動模擬交易。")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("總資產", f"NT${rep['final_equity']:,.0f}", f"{rep['total_return_pct']:+.2f}%")
        m2.metric("已實現 / 未實現損益", f"NT${rep['realized_pnl']:+,.0f}", f"未實現 NT${rep['unrealized_pnl']:+,.0f}")
        m3.metric("已平倉勝率", f"{rep['win_rate_pct']:.1f}%", f"{rep['closed_trades']} 筆已平倉")
        m4.metric("最大回撤 (MDD)", f"{rep['max_drawdown_pct']:.2f}%")

        df_eq = pd.DataFrame(snaps)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_eq["date"], y=df_eq["total_equity"], mode="lines+markers", line=dict(color="#2962FF", width=2.2), name="總資產"))
        fig.update_layout(template="plotly_dark", paper_bgcolor="#0F1624", plot_bgcolor="#0F1624", height=320, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### 目前持倉")
        if open_trades:
            st.dataframe(pd.DataFrame(open_trades)[["symbol", "name", "buy_date", "buy_price", "shares", "stop_loss", "take_profit", "buy_reason"]], use_container_width=True, hide_index=True)
        else:
            st.caption("目前空手，100% 持有現金。")

elif page == "強勢股雷達":
    st.markdown("### 強勢股雷達")
    if not today_sigs:
        st.info("請先點擊右上角「更新市場資料」。")
    else:
        for s in today_sigs[:12]:
            with st.container(border=True):
                a, b, c = st.columns([2.4, 3.2, 1.1])
                a.markdown(f"**{s['name']} ({s['symbol']})** &nbsp; {light_pill(s['traffic_light'])}", unsafe_allow_html=True)
                a.caption(f"RS20: {s['rs_20']:+.1f}% · 品質 {s['quality_grade']} ({s['quality_score']:.0f}) · 訊號 {s['signal_strength']:.0f}")
                b.caption(s["reason"])
                if c.button("詳情", key=f"radar_{s['symbol']}", use_container_width=True):
                    st.session_state["selected_symbol"] = s["symbol"]
                    st.rerun()

elif page == "AI 老師":
    st.markdown("### AI 老師模式")
    q = st.text_input("輸入問題（例如：為什麼買 2330？為什麼今天不能買？我持有的股票要賣嗎？）")
    if q:
        ans = answer_teacher_question(q, today_sigs, open_trades, market_temp)
        st.markdown(f"""
        <div class="qc-card">
            <div style="font-weight:700; color:#60A5FA; margin-bottom:8px;">結論：{ans['conclusion']}</div>
            <div style="margin-bottom:6px;"><strong>原因：</strong>{ans['reason']}</div>
            <div style="margin-bottom:6px; color:#F87171;"><strong>風險：</strong>{ans['risk']}</div>
            <div style="color:#34D399;"><strong>下一步：</strong>{ans['next_step']}</div>
        </div>
        """, unsafe_allow_html=True)

elif page == "新聞與基本面":
    st.markdown("### AI 新聞與基本面分析")
    sym_in = st.text_input("輸入台股代碼", value="2330")
    if st.button("查詢最新新聞", type="primary"):
        nm = next((s["name"] for s in today_sigs if s["symbol"] == sym_in), sym_in)
        news_list = fetch_stock_news(sym_in.strip(), nm, limit=6)
        if not news_list:
            st.warning("目前無法取得即時新聞，系統不會偽造新聞。")
        for n in news_list:
            st.markdown(f"""
            <div class="qc-card">
                <div><strong>[{n['sentiment']}] {n['title']}</strong></div>
                <div style="color:#94A3B8; font-size:0.82rem; margin:4px 0;">{n['source']} · {n['date']} · <a href="{n['url']}" target="_blank">原始連結</a></div>
                <div><strong>事實：</strong>{n['fact']}</div>
                <div><strong>推論：</strong>{n['inference']}</div>
                <div style="color:#FBBF24;"><strong>不確定性：</strong>{n['uncertainty']}</div>
            </div>
            """, unsafe_allow_html=True)

elif page == "交易帳本":
    st.markdown(f"### 交易帳本（{active_strategy}）")
    chain = db.verify_hash_chain(active_strategy)
    if chain["valid"]:
        st.success(f"SHA-256 雜湊鏈驗證通過（{chain['checked']} 筆快照完整無竄改）。")
    else:
        st.error(f"雜湊鏈異常：{chain['broken_date']}")
    if all_trades:
        st.dataframe(pd.DataFrame(all_trades)[["trade_id", "symbol", "name", "status", "buy_date", "buy_price", "shares", "sell_date", "sell_price", "total_cost", "net_pnl", "return_pct", "exit_reason"]], use_container_width=True, hide_index=True)
    else:
        st.caption("尚無模擬成交紀錄。")

elif page in ("策略回測", "策略驗證"):
    st.markdown("### 策略驗證中心（歷史回測與 Walk-Forward）")
    t_days = st.slider("回測交易日數", 30, 120, 60, 10)
    b1, b2 = st.columns(2)
    if b1.button("執行雙策略比較回測", type="primary", use_container_width=True):
        if not cached_scan:
            st.warning("請先點擊右上角「更新市場資料」取得真實歷史行情。")
        else:
            bt = run_comparison_backtest(cached_scan["market_data"], cached_scan.get("benchmark_df"), cached_scan.get("benchmark_0050_df"), test_days=t_days)
            if bt["status"] == "OK":
                st.dataframe(pd.DataFrame([bt["frozen"]["report"], bt["ai_v2"]["report"]])[["strategy_version", "total_trades", "closed_trades", "win_rate_pct", "profit_factor", "max_drawdown_pct", "total_return_pct", "benchmark_0050_ret", "total_transaction_costs"]], use_container_width=True, hide_index=True)
    if b2.button("執行 Walk-Forward 樣本外驗證", use_container_width=True):
        if not cached_scan:
            st.warning("請先點擊右上角「更新市場資料」。")
        else:
            wf = run_walk_forward_validation(cached_scan["market_data"], cached_scan.get("benchmark_df"), cached_scan.get("benchmark_0050_df"))
            if wf["status"] == "OK":
                st.dataframe(pd.DataFrame(wf["folds"]), use_container_width=True, hide_index=True)

elif page == "AI 績效追蹤":
    st.markdown("### AI 決策品質追蹤（5 / 10 / 20 日事後驗證）")
    preds = db.get_all_predictions(active_strategy)
    if not preds:
        st.info("尚未產生綠燈推薦紀錄。")
    else:
        st.dataframe(pd.DataFrame(preds)[["date", "symbol", "name", "rec_price", "ai_grade", "ret_5d", "ret_10d", "ret_20d", "hit_tp", "hit_sl", "outcome_status"]], use_container_width=True, hide_index=True)

elif page == "資料品質":
    st.markdown("### 資料品質監控")
    dq = db.get_latest_data_quality(15)
    if dq:
        st.dataframe(pd.DataFrame(dq)[["date", "module_name", "data_source", "status", "completeness_pct", "details", "updated_at"]], use_container_width=True, hide_index=True)
    else:
        st.caption("尚無資料品質紀錄。")

elif page == "策略版本":
    st.markdown("### 策略版本管理")
    choice = st.radio("切換目前檢視的獨立策略帳本", [config.STRATEGY_AI_V2, config.STRATEGY_FROZEN], index=0 if active_strategy == config.STRATEGY_AI_V2 else 1)
    if choice != active_strategy:
        st.session_state["active_strategy"] = choice
        st.rerun()
    st.caption("QC-PT-1.0-FROZEN 為鎖定基準版；QC-AI-2.0 為新版 AI 決策策略，兩者帳本完全隔離。")

elif page == "系統設定":
    st.markdown("### 系統進階設定（工程參數）")
    st.session_state["scan_count"] = st.slider("動態掃描台股檔數", 20, 60, st.session_state["scan_count"], 5)
    st.session_state["fetch_extra"] = st.checkbox("同步抓取財報與法人籌碼（較耗時）", value=st.session_state["fetch_extra"])
    st.session_state["dev_debug"] = st.checkbox("開發者除錯模式（於介面顯示完整錯誤堆疊）", value=st.session_state["dev_debug"])
    st.caption(f"SQLite 帳本：`{config.DB_PATH}` ｜ JSON 帳本：`{config.JSON_LEDGER_PATH}` ｜ 錯誤日誌：`quant_compass_errors.log`")
