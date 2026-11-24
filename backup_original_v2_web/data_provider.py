"""
Real Taiwan Stock Market Data Provider:
- Dynamic Active Universe via TWSE OpenAPI (Top turnover / strong movers)
- Historical OHLCV via yfinance (primary) & FinMind (fallback)
"""
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import pandas as pd
import pytz
import config


class MarketDataProvider:
    def __init__(self, finmind_token: Optional[str] = None):
        self.finmind_token = finmind_token
        self.tz = pytz.timezone(config.TIMEZONE)

    def fetch_dynamic_tw_universe(self, top_n: int = 60) -> List[Tuple[str, str, str]]:
        """
        Queries TWSE OpenAPI STOCK_DAY_ALL to dynamically pick top active/strong stocks
        by daily trading value (excluding ETFs/warrants/penny stocks).
        Falls back to config.DEFAULT_TW_UNIVERSE if offline or API changes.
        """
        try:
            import requests
            url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
            resp = requests.get(url, timeout=12)
            rows = resp.json()
            candidates = []
            for r in rows:
                code = str(r.get("Code", "")).strip()
                name = str(r.get("Name", "")).strip()
                # Regular 4-digit Taiwan common stocks (exclude 00xx ETFs & 91xx DRs)
                if len(code) != 4 or not code.isdigit() or code.startswith("00") or code.startswith("91"):
                    continue
                try:
                    close = float(str(r.get("ClosingPrice", "0")).replace(",", ""))
                    val = float(str(r.get("TradeValue", "0")).replace(",", ""))
                except ValueError:
                    continue
                if close >= config.MIN_PRICE and val > 0:
                    candidates.append((code, name, "TW", val))

            candidates.sort(key=lambda x: x[3], reverse=True)
            top_list = [(c[0], c[1], c[2]) for c in candidates[:top_n]]
            # Merge with key TPEx leaders from default list
            seen = {x[0] for x in top_list}
            for sym, nm, mkt in config.DEFAULT_TW_UNIVERSE:
                if mkt == "TWO" and sym not in seen:
                    top_list.append((sym, nm, mkt))
            return top_list if top_list else list(config.DEFAULT_TW_UNIVERSE)
        except Exception:
            return list(config.DEFAULT_TW_UNIVERSE)

    def fetch_history(
        self, symbol: str, market: str = "TW", lookback_days: int = 200
    ) -> Tuple[Optional[pd.DataFrame], str, str]:
        ts = datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S %Z")
        df = self._fetch_yfinance(symbol, market, lookback_days)
        if df is not None and not df.empty:
            return df, "yfinance", ts

        if not symbol.startswith("^"):
            df_fm = self._fetch_finmind(symbol, lookback_days)
            if df_fm is not None and not df_fm.empty:
                return df_fm, "FinMind", ts

        return None, "UNAVAILABLE", ts

    def _fetch_yfinance(self, symbol: str, market: str, lookback_days: int) -> Optional[pd.DataFrame]:
        try:
            import yfinance as yf
            ticker = symbol if symbol.startswith("^") else f"{symbol}.{market}"
            end_dt = datetime.now(self.tz) + timedelta(days=1)
            start_dt = end_dt - timedelta(days=lookback_days)
            df = yf.download(
                ticker,
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=False,
            )
            if df is None or df.empty:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
            df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
            return df.sort_index()
        except Exception:
            return None

    def _fetch_finmind(self, symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
        try:
            import requests
            start_date = (datetime.now(self.tz) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
            url = "https://api.finmindtrade.com/api/v4/data"
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": symbol,
                "start_date": start_date,
            }
            if self.finmind_token:
                params["token"] = self.finmind_token
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json().get("data", [])
            if not data:
                return None
            df = pd.DataFrame(data)
            df = df.rename(columns={
                "open": "Open", "max": "High", "min": "Low",
                "close": "Close", "Trading_Volume": "Volume", "date": "Date"
            })
            df = df.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]].astype(float).dropna()
            return df.sort_index()
        except Exception:
            return None
