"""
Real Taiwan Financial News Fetcher & Structured Analyzer.
Uses Google News RSS (Taiwan Finance) — strictly traceable URLs, deduplicates identical headlines,
and separates Fact, Inference, and Uncertainty.
"""
from datetime import datetime
from email.utils import parsedate_to_datetime
import re
from typing import Any, Dict, List
import urllib.parse
import xml.etree.ElementTree as ET


POS_KEYWORDS = ["營收創高", "年增", "獲利", "法說", "擴產", "大單", "上調", "利多", "買超", "突破", "AI", "成長", "配息", "新高"]
NEG_KEYWORDS = ["衰退", "年減", "虧損", "下修", "裁員", "利空", "賣超", "重挫", "跌停", "違約", "調查", "訴訟", "警告", "疲軟"]


def classify_sentiment(title: str) -> Dict[str, str]:
    pos = sum(1 for k in POS_KEYWORDS if k in title)
    neg = sum(1 for k in NEG_KEYWORDS if k in title)
    if pos > neg:
        return {"sentiment": "利多", "impact": "中高" if pos >= 2 else "中", "horizon": "短中期 (1～4週)"}
    if neg > pos:
        return {"sentiment": "利空", "impact": "中高" if neg >= 2 else "中", "horizon": "短中期 (1～4週)"}
    return {"sentiment": "中性", "impact": "低～中", "horizon": "短期觀察"}


def fetch_stock_news(symbol: str, name: str, limit: int = 6) -> List[Dict[str, Any]]:
    """
    Fetches real Taiwan financial news via Google News RSS.
    Returns empty list gracefully if offline (never fabricates fake news).
    """
    try:
        import requests
        query = urllib.parse.quote(f"{name} {symbol} 台股")
        url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        return parse_rss_news(resp.text, symbol, name, limit=limit)
    except Exception:
        return []


def parse_rss_news(xml_text: str, symbol: str, name: str, limit: int = 6) -> List[Dict[str, Any]]:
    """
    Parses RSS XML, deduplicates identical/near-identical headlines,
    and separates Fact, Inference, and Uncertainty.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    seen_norm = set()
    results: List[Dict[str, Any]] = []

    for item in root.findall(".//item"):
        raw_title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if (source_el is not None and source_el.text) else "新聞來源"

        # Remove trailing " - SourceName" from Google News titles
        clean_title = re.sub(r"\s*-\s*[^-]+$", "", raw_title).strip() or raw_title
        norm_key = re.sub(r"\W+", "", clean_title).lower()[:24]
        if not norm_key or norm_key in seen_norm:
            continue
        seen_norm.add(norm_key)

        try:
            pub_date = parsedate_to_datetime(pub_raw).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pub_date = pub_raw or datetime.now().strftime("%Y-%m-%d")

        meta = classify_sentiment(clean_title)
        sentiment = meta["sentiment"]
        if sentiment == "利多":
            inference = f"標題出現正向基本面或訂單關鍵字，可能提升市場對 {name}({symbol}) 的短線關注度。"
        elif sentiment == "利空":
            inference = f"標題出現負向業績或風險關鍵字，短線可能造成 {name}({symbol}) 賣壓或波動擴大。"
        else:
            inference = f"屬於一般產業或公司動態資訊，對 {name}({symbol}) 股價的直接方向性尚不明顯。"

        results.append({
            "title": clean_title,
            "date": pub_date,
            "source": source,
            "symbol": symbol,
            "name": name,
            "sentiment": sentiment,
            "impact": meta["impact"],
            "horizon": meta["horizon"],
            "fact": f"媒體「{source}」於 {pub_date} 報導：{clean_title}。",
            "inference": inference,
            "uncertainty": "單一新聞標題未包含完整財務細節，且市場可能已提前反應，仍須搭配實際量價與停損紀律。",
            "url": link,
        })
        if len(results) >= limit:
            break

    return results
