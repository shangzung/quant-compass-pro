"""
Real Taiwan Stock Data Provider & Data Quality Monitor (Hybrid Dynamic Screener).
- Dynamic TWSE (上市) Hybrid Pool: 50% Top Turnover (主流資金) + 50% Top Momentum Liquid Stocks (強勢中小型股)
- Dynamic TPEx (上櫃) Pool via official TPEx OpenAPI (replaces static OTC list; falls back safely if offline)
- Historical OHLCV via yfinance (primary, with retry) + FinMind (fallback, including TAIEX for ^TWII)
- Fundamentals via yfinance info (optional) & Institutional Chips via FinMind (optional)
NEVER fabricates fake/random market prices or missing metrics.
"""
from datetime import datetime, timedelta
import time
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import pytz
import config


SECTOR_MAP = {sym: sec for sym, _, _, sec in config.DEFAULT_TW_UNIVERSE}


class MarketDataProvider:
    def __init__(self, finmind_token: Optional[str] = None):
        self.finmind_token = finmind_token
        self.tz = pytz.timezone(config.TIMEZONE)

    def _fetch_tpex_dynamic(self, max_otc: int = 12) -> List[Tuple[str, str, str, str]]:
        """Fetches dynamic active & strong TPEx (上櫃) common stocks via official TPEx OpenAPI."""
        try:
            import requests
            url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
            resp = requests.get(url, timeout=12)
            rows = resp.json()
            candidates = []
            for r in rows:
                code = str(r.get("SecuritiesCompanyCode", "")).strip()
                name = str(r.get("CompanyName", "")).strip()
                if len(code) != 4 or not code.isdigit() or code.startswith("00") or code.startswith("91"):
                    continue
                try:
                    close = float(str(r.get("Close", "0")).replace(",", ""))
                    chg = float(str(r.get("Change", "0")).replace(",", "").replace("+", ""))
                    vol = float(str(r.get("TradingShares", "0")).replace(",", ""))
                    val = float(str(r.get("TransactionAmount", "0")).replace(",", ""))
                except ValueError:
                    continue
                prev = close - chg
                chg_pct = (chg / prev * 100.0) if prev > 0 else 0.0
                # Filter liquid OTC stocks (>= 800 lots & price >= MIN_PRICE)
                if close >= config.MIN_PRICE and vol >= 800_000 and val > 0:
                    candidates.append((code, name, "TWO", SECTOR_MAP.get(code, "上櫃活躍股"), val, chg_pct))

            if not candidates:
                return []

            half = max(max_otc // 2, 1)
            by_val = sorted(candidates, key=lambda x: x[4], reverse=True)[:half]
            seen = {c[0] for c in by_val}
            by_mom = [c for c in sorted(candidates, key=lambda x: x[5], reverse=True) if c[0] not in seen][: (max_otc - len(by_val))]
            picked = by_val + by_mom
            return [(c[0], c[1], c[2], c[3]) for c in picked]
        except Exception:
            return []

    def fetch_dynamic_tw_universe(self, top_n: int = 50) -> Tuple[List[Tuple[str, str, str, str]], str]:
        """
        Builds a Hybrid Dynamic Taiwan Stock Pool:
        - TWSE (上市): 50% Top Trading Value (主流大資金) + 50% Top Daily Momentum Liquid Stocks (強勢中小型股)
        - TPEx (上櫃): Dynamic OTC Active + Momentum stocks via TPEx OpenAPI
        Returns (universe_list, source_label).
        Each item: (symbol, name, market, sector).
        """
        twse_picked: List[Tuple[str, str, str, str]] = []
        try:
            import requests
            url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
            resp = requests.get(url, timeout=12)
            rows = resp.json()
            all_valid = []
            for r in rows:
                code = str(r.get("Code", "")).strip()
                name = str(r.get("Name", "")).strip()
                if len(code) != 4 or not code.isdigit() or code.startswith("00") or code.startswith("91"):
                    continue
                try:
                    close = float(str(r.get("ClosingPrice", "0")).replace(",", ""))
                    chg = float(str(r.get("Change", "0")).replace(",", "").replace("+", ""))
                    vol = float(str(r.get("TradeVolume", "0")).replace(",", ""))
                    val = float(str(r.get("TradeValue", "0")).replace(",", ""))
                except ValueError:
                    continue
                if close >= config.MIN_PRICE and val > 0 and vol > 0:
                    prev = close - chg
                    chg_pct = (chg / prev * 100.0) if prev > 0 else 0.0
                    all_valid.append((code, name, "TW", SECTOR_MAP.get(code, "上市動態股"), val, vol, chg_pct))

            if all_valid:
                half_val = max(top_n // 2, 1)
                # 1) Top Trading Value (Mainstream institutional flow)
                top_val = sorted(all_valid, key=lambda x: x[4], reverse=True)[:half_val]
                seen = {c[0] for c in top_val}

                # 2) Top Momentum among liquid stocks (>= 1,000 lots & >= NT$100M turnover)
                liquid_pool = [c for c in all_valid if c[0] not in seen and c[5] >= 1_000_000 and c[4] >= 100_000_000]
                top_mom = sorted(liquid_pool, key=lambda x: x[6], reverse=True)[: (top_n - len(top_val))]
                for c in top_mom:
                    seen.add(c[0])

                # Backfill if momentum pool was smaller than quota
                if len(top_val) + len(top_mom) < top_n:
                    rem = [c for c in sorted(all_valid, key=lambda x: x[4], reverse=True) if c[0] not in seen]
                    top_mom.extend(rem[: (top_n - len(top_val) - len(top_mom))])

                twse_picked = [(c[0], c[1], c[2], c[3]) for c in (top_val + top_mom)]
        except Exception:
            twse_picked = []

        # 3) Dynamic TPEx (OTC) pool
        otc_quota = max(10, top_n // 3)
        tpex_picked = self._fetch_tpex_dynamic(max_otc=otc_quota)

        if twse_picked:
            seen_all = {x[0] for x in twse_picked}
            if tpex_picked:
                for item in tpex_picked:
                    if item[0] not in seen_all:
                        twse_picked.append(item)
                        seen_all.add(item[0])
                return twse_picked, "TWSE_Hybrid+TPEx_OpenAPI"
            else:
                for sym, nm, mkt, sec in config.DEFAULT_TW_UNIVERSE:
                    if mkt == "TWO" and sym not in seen_all:
                        twse_picked.append((sym, nm, mkt, sec))
                        seen_all.add(sym)
                return twse_picked, "TWSE_Hybrid+TPEx_Fallback"

        return list(config.DEFAULT_TW_UNIVERSE), "DEFAULT_UNIVERSE_FALLBACK"

    def fetch_history(
        self, symbol: str, market: str = "TW", lookback_days: int = 240
    ) -> Tuple[Optional[pd.DataFrame], str, str]:
        ts = datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S %Z")
        df = self._fetch_yfinance(symbol, market, lookback_days)
        if df is not None and not df.empty:
            return df, "yfinance", ts

        # Fallback to FinMind (maps ^TWII -> TAIEX so benchmark never lacks a fallback)
        fm_symbol = "TAIEX" if symbol == "^TWII" else symbol
        if not fm_symbol.startswith("^"):
            df_fm = self._fetch_finmind(fm_symbol, lookback_days)
            if df_fm is not None and not df_fm.empty:
                return df_fm, "FinMind", ts

        return None, "UNAVAILABLE", ts

    def _fetch_yfinance(self, symbol: str, market: str, lookback_days: int) -> Optional[pd.DataFrame]:
        try:
            import yfinance as yf
            ticker = symbol if symbol.startswith("^") else f"{symbol}.{market}"
            end_dt = datetime.now(self.tz) + timedelta(days=1)
            start_dt = end_dt - timedelta(days=lookback_days)

            for attempt in range(2):
                try:
                    df = yf.download(
                        ticker,
                        start=start_dt.strftime("%Y-%m-%d"),
                        end=end_dt.strftime("%Y-%m-%d"),
                        progress=False,
                        auto_adjust=False,
                    )
                    if df is None or df.empty:
                        df = yf.Ticker(ticker).history(period=f"{lookback_days}d", auto_adjust=False)
                    if df is not None and not df.empty:
                        if isinstance(df.columns, pd.MultiIndex):
                            df.columns = df.columns.get_level_values(0)
                        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
                        return df.sort_index()
                except Exception:
                    pass
                if attempt == 0:
                    time.sleep(0.8)
            return None
        except Exception:
            return None

    def _fetch_finmind(self, symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
        try:
            import requests
            start_date = (datetime.now(self.tz) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            url = "https://api.finmindtrade.com/api/v4/data"
            params = {"dataset": "TaiwanStockPrice", "data_id": symbol, "start_date": start_date}
            if self.finmind_token:
                params["token"] = self.finmind_token
            resp = requests.get(url, params=params, timeout=12)
            data = resp.json().get("data", [])
            if not data:
                return None
            df = pd.DataFrame(data).rename(columns={
                "open": "Open", "max": "High", "min": "Low",
                "close": "Close", "Trading_Volume": "Volume", "date": "Date"
            })
            return df.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]].astype(float).dropna().sort_index()
        except Exception:
            return None

    def fetch_fundamentals(self, symbol: str, market: str = "TW") -> Dict[str, Any]:
        """Fetches real fundamental ratios via yfinance. Returns empty dict if unavailable."""
        try:
            import yfinance as yf
            info = yf.Ticker(f"{symbol}.{market}").info or {}
            out = {}
            if info.get("returnOnEquity") is not None:
                out["roe"] = float(info["returnOnEquity"])
            if info.get("profitMargins") is not None:
                out["profit_margin"] = float(info["profitMargins"])
            if info.get("revenueGrowth") is not None:
                out["revenue_growth"] = float(info["revenueGrowth"])
            if info.get("earningsGrowth") is not None:
                out["earnings_growth"] = float(info["earningsGrowth"])
            return out
        except Exception:
            return {}

    def fetch_institutional_chips(self, symbol: str, lookback_days: int = 15) -> Dict[str, Any]:
        """Fetches real 5-day institutional net buy/sell via FinMind. Returns empty dict if unavailable."""
        try:
            import requests
            start_date = (datetime.now(self.tz) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            url = "https://api.finmindtrade.com/api/v4/data"
            params = {
                "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
                "data_id": symbol,
                "start_date": start_date,
            }
            if self.finmind_token:
                params["token"] = self.finmind_token
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json().get("data", [])
            if not data:
                return {}
            df = pd.DataFrame(data)
            df["net"] = df["buy"].astype(float) - df["sell"].astype(float)
            daily = df.groupby("date")["net"].sum().sort_index()
            last_5 = daily.tail(5)
            return {
                "inst_net_5d_shares": float(last_5.sum()),
                "date": str(last_5.index[-1]),
                "source": "FinMind",
            }
        except Exception:
            return {}


def check_stock_data_quality(df: Optional[pd.DataFrame], expected_date: str) -> Tuple[bool, str]:
    if df is None or df.empty:
        return False, "無行情資料"
    if len(df) < config.MA_LONG:
        return False, f"歷史交易日不足 ({len(df)} < {config.MA_LONG})"
    if str(df.index[-1]) != expected_date:
        return False, f"資料延遲或停牌（最新日 {df.index[-1]} != {expected_date}）"
    row = df.iloc[-1]
    if any(pd.isna(row[c]) for c in ["Open", "High", "Low", "Close", "Volume"]):
        return False, "當日 OHLCV 欄位缺失"
    if float(row["Close"]) <= 0 or float(row["Volume"]) <= 0:
        return False, "價格或成交量異常 (<= 0)"
    return True, "OK"
