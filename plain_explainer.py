"""
AI Plain-Language Explainer Engine & AI Teacher Mode.
Translates technical indicators into plain Chinese with all 5 required elements:
1. Current Value, 2. Normal Meaning, 3. Impact, 4. Actionable Advice, 5. Data Date.
AI Teacher Mode strictly answers in 4-part format: Conclusion, Reason, Risk, Next Step.
"""
from typing import Any, Dict, List, Optional
import pandas as pd


def explain_indicators_plain(
    df: pd.DataFrame,
    chips: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    if df is None or df.empty:
        return []
    row = df.iloc[-1]
    data_date = str(df.index[-1])
    items: List[Dict[str, str]] = []

    # 1. RSI
    rsi = row.get("RSI14")
    if rsi is not None and not pd.isna(rsi):
        r = float(rsi)
        if r > 70:
            impact = "這檔股票最近漲得比較快，短時間內可能有休息或回檔的機會。"
            advice = "不要急著追高，等股價拉回靠近支撐區再觀察。"
        elif r >= 45:
            impact = "買盤力道健康且還沒過熱，屬於相對舒服的上漲節奏。"
            advice = "可搭配趨勢與停損位置評估進場計畫。"
        else:
            impact = "近期賣壓較重，上漲動能偏弱。"
            advice = "先觀望，等股價重新站回均線且動能轉強再說。"
        items.append({
            "indicator": "RSI (14日相對強弱)",
            "value": f"{r:.1f}",
            "normal": "45～70 為健康偏強區間；超過 70 偏熱、低於 45 偏弱。",
            "impact": impact,
            "advice": advice,
            "date": data_date,
        })

    # 2. MACD
    dif, hist = row.get("MACD_DIF"), row.get("MACD_HIST")
    if dif is not None and hist is not None and not pd.isna(hist):
        h = float(hist)
        if h > 0:
            impact = "目前股價上漲的力量正在增強。"
            advice = "趨勢偏向多方，若持有可續抱並守好停損。"
        else:
            impact = "目前上漲力道減弱或偏向空方整理。"
            advice = "不宜貿然搶進，等待柱狀體翻紅確認動能回溫。"
        items.append({
            "indicator": "MACD 動能趨勢",
            "value": f"DIF {float(dif):+.2f} / 柱狀 {h:+.2f}",
            "normal": "柱狀大於 0 代表多方動能佔優勢；小於 0 代表動能轉弱。",
            "impact": impact,
            "advice": advice,
            "date": data_date,
        })

    # 3. KD
    k_val, d_val = row.get("K9"), row.get("D9")
    if k_val is not None and d_val is not None and not pd.isna(k_val):
        k, d = float(k_val), float(d_val)
        if k > 80:
            impact = "這檔股票短期漲幅比較大，要注意是否追高。"
            advice = "避免在短線過熱時一次重壓，可等震盪整理。"
        elif k > d:
            impact = "短線買氣占上風，價格維持偏強走勢。"
            advice = "若其他條件配合，可留意拉回不破支撐的買點。"
        else:
            impact = "短線處於修正或整理狀態。"
            advice = "先觀察是否止跌回穩，不必急著進場。"
        items.append({
            "indicator": "KD 隨機指標 (9,3,3)",
            "value": f"K={k:.1f} / D={d:.1f}",
            "normal": "K > D 偏強、K < D 偏弱；80 以上為短線過熱區。",
            "impact": impact,
            "advice": advice,
            "date": data_date,
        })

    # 4. Moving Averages
    close, ma20, ma60 = row.get("Close"), row.get("MA20"), row.get("MA60")
    if ma20 is not None and ma60 is not None and not pd.isna(ma20) and not pd.isna(ma60):
        c, m20, m60 = float(close), float(ma20), float(ma60)
        if c > m20 and m20 > m60:
            impact = "目前股價站在近期平均價格之上，且短中期趨勢同步向上，代表近期走勢相對強勢。"
            advice = "屬於多頭架構，可作為優先關注對象，並以月線或 ATR 作為防守點。"
        elif c > m20:
            impact = "股價剛站回月線之上，短線轉強但中期趨勢仍在整理。"
            advice = "可列入觀察名單，確認量能與季線方向後再行動。"
        else:
            impact = "股價低於近一個月平均成本，代表近期買進的人多數處於套牢。"
            advice = "上方解套賣壓較重，目前不建議買進。"
        items.append({
            "indicator": "均線趨勢 (月線 MA20 / 季線 MA60)",
            "value": f"收盤 {c:.2f}｜MA20 {m20:.2f}｜MA60 {m60:.2f}",
            "normal": "股價 > MA20 > MA60 為標準多頭排列。",
            "impact": impact,
            "advice": advice,
            "date": data_date,
        })

    # 5. Institutional Chips
    if chips and chips.get("inst_net_5d_shares") is not None:
        net_lots = int(chips["inst_net_5d_shares"] // 1000)
        chip_date = chips.get("date", data_date)
        if net_lots > 0:
            impact = "大型投資機構最近正在買進，代表有較多機構資金進場，但不代表未來一定上漲。"
            advice = "籌碼面加分，仍需配合停損與合理進場價位。"
        elif net_lots < 0:
            impact = "大型投資機構近期偏向賣出調節，短線籌碼較凌亂。"
            advice = "留意法人持續賣壓風險，勿逆勢攤平。"
        else:
            impact = "機構進出大致平衡，目前由市場一般買盤主導。"
            advice = "回歸技術趨勢與風險報酬比判斷。"
        items.append({
            "indicator": "法人籌碼 (三大法人近5日)",
            "value": f"{net_lots:+,} 張",
            "normal": "正數代表機構淨買超、負數代表機構淨賣超。",
            "impact": impact,
            "advice": advice,
            "date": chip_date,
        })

    return items


def answer_teacher_question(
    question: str,
    signals: List[Dict[str, Any]],
    open_trades: List[Dict[str, Any]],
    market_temp: Dict[str, Any],
) -> Dict[str, str]:
    """
    Deterministic, data-grounded AI Teacher Mode.
    Always returns 4 structured parts: conclusion, reason, risk, next_step.
    Never predicts future stock prices.
    """
    q = question.strip()
    # Try to find a 4-digit stock code or stock name mentioned in the question
    target_sig = None
    for s in signals:
        if s["symbol"] in q or s["name"] in q:
            target_sig = s
            break

    target_pos = None
    for tr in open_trades:
        if tr["symbol"] in q or tr["name"] in q:
            target_pos = tr
            break

    # Case 1: Asking about holding / selling existing positions
    if ("持有" in q or "賣掉" in q or "賣出" in q) and not target_sig:
        if not open_trades:
            return {
                "conclusion": "您目前沒有任何模擬持倉，不需要執行賣出動作。",
                "reason": "模擬帳戶目前 100% 為現金狀態，無持股暴露於市場波動中。",
                "risk": f"目前大盤溫度為 {market_temp.get('temp', 50):.0f} 分（{market_temp.get('state', '未知')}），需留意市場整體波動。",
                "next_step": "請查看首頁的「今日推薦股票（綠燈）」，若無合適標的就保持空手等待。",
            }
        pos_names = "、".join(f"{t['name']}({t['symbol']})" for t in open_trades)
        return {
            "conclusion": f"目前持有 {len(open_trades)} 檔股票（{pos_names}），請依照停損價與月線紀律決定是否賣出，不靠感覺操作。",
            "reason": "系統每日收盤會自動檢查：1. 是否觸及 ATR 停損價；2. 是否跌破 MA20 月線；3. 是否觸及停利目標或滿 20 個交易日。",
            "risk": "若跌破停損還不賣出，小虧損可能擴大成無法承受的大虧損。",
            "next_step": "前往「📜 模擬交易帳本」檢查每檔持股距離停損價的安全空間，若未觸發出場條件就耐心續抱。",
        }

    # Case 2: Asking if a stock will keep going up ("還會漲嗎")
    if "還會漲嗎" in q or "會漲嗎" in q or "目標價" in q:
        if target_sig:
            return {
                "conclusion": f"沒有任何系統能保證 {target_sig['name']}({target_sig['symbol']}) 未來一定會上漲；目前系統對它的燈號為【{target_sig['traffic_light']}】。",
                "reason": f"依據最新收盤資料（{target_sig['date']}），它的品質評分為 {target_sig['quality_score']:.1f} 分（{target_sig['quality_grade']} 級），交易訊號強度 {target_sig['signal_strength']:.1f} 分，{target_sig['reason']}。",
                "risk": f"就算趨勢偏強，股價隨時可能受大盤或消息面反轉，因此必須預先設定停損價 {target_sig.get('stop_loss')} 元來鎖定最大虧損。",
                "next_step": "不要預測漲跌，而是檢查「風險報酬比」是否划算：綠燈才照計畫分批進場，黃燈或紅燈就耐心等待。",
            }
        return {
            "conclusion": "AI 無法預測未來股價一定上漲或下跌，量化投資靠的是「有利的風險報酬比」與「嚴格停損」。",
            "reason": "股市短期充滿隨機雜訊，任何宣稱能 100% 預測漲跌的模型都不可信。",
            "risk": "若憑感覺猜漲跌而沒有停損計畫，單次看錯就可能重傷本金。",
            "next_step": "請輸入具體股票代碼（例如「為什麼買 2330？」），我會直接列出它的燈號、支撐停損與交易計畫。",
        }

    # Case 3: Specific stock question (Why buy / Why S grade / Why wait)
    if target_sig:
        light = target_sig["traffic_light"]
        if light == "綠燈":
            conc = f"{target_sig['name']}({target_sig['symbol']}) 目前為【綠燈：符合策略買進條件】，但符合條件不代表保證獲利。"
            nxt = f"若要在下一交易日開盤模擬進場，請遵守停損價 {target_sig.get('stop_loss')} 元、第一停利 {target_sig.get('take_profit')} 元，建議股數 {target_sig.get('suggested_shares', 0):,} 股（嚴控單筆風險 ≤ 1%）。"
        elif light == "黃燈":
            conc = f"{target_sig['name']}({target_sig['symbol']}) 目前為【黃燈：等待更好的進場時機】，暫時不建議現在追進。"
            nxt = f"目前尚未完全達標（{target_sig.get('missing_condition') or target_sig['reason']}），建議加入觀察名單，等條件補齊再動作。"
        elif light == "灰燈":
            conc = f"{target_sig['name']}({target_sig['symbol']}) 目前為【灰燈：資料不足，暫停判斷】。"
            nxt = "資料完整度不足時不可冒險交易，請等待資料源更新完整後再重新評估。"
        else:
            conc = f"{target_sig['name']}({target_sig['symbol']}) 目前為【紅燈：不建議買進】。"
            nxt = "目前趨勢偏弱或風險過高，建議避開，把資金留給體質與趨勢更好的標的。"

        return {
            "conclusion": conc,
            "reason": f"資料日期 {target_sig['date']}：品質評分 {target_sig['quality_score']:.1f} 分（{target_sig['quality_grade']} 級）、訊號強度 {target_sig['signal_strength']:.1f} 分、資料可信度 {target_sig['data_confidence']:.0f}%。判斷依據：{target_sig['reason']}。",
            "risk": f"目前大盤溫度 {market_temp.get('temp', 50):.0f} 分（{market_temp.get('state')}）；若該股開盤跳空過大（>4%）或跌破停損 {target_sig.get('stop_loss')} 元，都代表原先假設失效。",
            "next_step": nxt,
        }

    # Case 4: General "Why can't I buy today?"
    greens = [s for s in signals if s["traffic_light"] == "綠燈"]
    if not greens:
        return {
            "conclusion": "今天沒有出現任何【綠燈】買進標的，所以系統建議先空手觀望。",
            "reason": f"目前市場溫度為 {market_temp.get('temp', 50):.0f} 分（{market_temp.get('state')}），加上今日掃描的股票中沒有同時滿足「多頭趨勢 + 合理 RSI + 量能放大 + 風險報酬比 ≥ 1.5」的標的。",
            "risk": "在沒有好機會時硬要買股票（過度交易），是散戶最常虧錢的原因。",
            "next_step": "可以到首頁「今日觀察股票（黃燈）」看看哪些股票只差一個條件，耐心等待市場給出好位置。",
        }
    top_g = greens[0]
    return {
        "conclusion": f"今日共有 {len(greens)} 檔【綠燈】標的，首選為 {top_g['name']}({top_g['symbol']})（品質 {top_g['quality_grade']} 級 / 訊號 {top_g['signal_strength']:.0f} 分）。",
        "reason": f"目前市場溫度 {market_temp.get('temp', 50):.0f} 分，且這些標的同時通過趨勢、量能與 1:1.5 以上風險報酬比檢驗。",
        "risk": "綠燈只代表「勝算與賠率結構較佳」，絕非穩賺不賠，必須嚴守單筆 1% 風險上限。",
        "next_step": f"您可以直接輸入「為什麼買 {top_g['symbol']}？」查看它的完整 10 項交易計畫與白話指標解說。",
    }
