"""
Polygon.io data fetching: OHLCV, options chains, news, indices.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)


class PolygonClient:
    BASE = "https://api.polygon.io"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("POLYGON_API_KEY", "")
        if not self.api_key:
            raise ValueError("Set POLYGON_API_KEY env var or pass api_key")
        self.session = requests.Session()
        self.session.params = {"apiKey": self.api_key}

    def _get(self, path: str, params: dict = None) -> dict:
        url = self.BASE + path
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params or {}, timeout=30)
                if resp.status_code == 429:
                    time.sleep(12)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def get_aggregates(
        self,
        ticker: str,
        from_date: str,
        to_date: str,
        timespan: str = "day",
        multiplier: int = 1,
    ) -> pd.DataFrame:
        """Fetch OHLCV bars. Returns DataFrame indexed by date."""
        results = []
        url = f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        params = {"adjusted": "true", "sort": "asc", "limit": 50000}

        while url:
            data = self._get(url, params)
            results.extend(data.get("results", []))
            url = data.get("next_url", "").replace(self.BASE, "") or None
            params = {}  # next_url includes all params

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["t"], unit="ms").dt.date
        df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "vw": "vwap"})
        df = df.set_index("date")[["open", "high", "low", "close", "volume", "vwap"]]
        return df

    def get_options_chain(self, underlying: str, expiration_date: str = None,
                          snapshot_date: str = None) -> pd.DataFrame:
        """
        Fetch options chain.
        snapshot_date: historical EOD snapshot date (YYYY-MM-DD). Omit for today.
        expiration_date: filter by specific expiry (optional).
        """
        results = []
        url = f"/v3/snapshot/options/{underlying}"
        params = {"limit": 250}
        if expiration_date:
            params["expiration_date"] = expiration_date
        if snapshot_date:
            params["date"] = snapshot_date
        while url:
            data = self._get(url, params)
            results.extend(data.get("results", []))
            url = (data.get("next_url") or "").replace(self.BASE, "") or None
            params = {}

        if not results:
            return pd.DataFrame()

        rows = []
        for r in results:
            d = r.get("details", {})
            g = r.get("greeks", {})
            rows.append({
                "strike": d.get("strike_price"),
                "type": d.get("contract_type"),
                "expiration": d.get("expiration_date"),
                "bid": r.get("last_quote", {}).get("bid"),
                "ask": r.get("last_quote", {}).get("ask"),
                "iv": r.get("implied_volatility"),
                "delta": g.get("delta"),
                "gamma": g.get("gamma"),
                "theta": g.get("theta"),
                "vega": g.get("vega"),
                "open_interest": r.get("open_interest"),
                "volume": r.get("day", {}).get("volume"),
            })
        return pd.DataFrame(rows)

    def get_expirations(self, underlying: str, as_of: str = None) -> list[str]:
        """Get available expiration dates."""
        params = {"limit": 100}
        if as_of:
            params["expiration_date.gte"] = as_of
        data = self._get(f"/v3/reference/options/{underlying}", params)
        exps = sorted(set(r["expiration_date"] for r in data.get("results", [])))
        return exps

    def get_news(
        self,
        ticker: str,
        from_date: str,
        to_date: str,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """Fetch news articles. Returns DataFrame with published_utc, title, description."""
        results = []
        url = "/v2/reference/news"
        params = {
            "ticker": ticker,
            "published_utc.gte": from_date,
            "published_utc.lte": to_date,
            "order": "asc",
            "limit": 1000,
        }
        while url and len(results) < limit:
            data = self._get(url, params)
            results.extend(data.get("results", []))
            url = (data.get("next_url") or "").replace(self.BASE, "") or None
            params = {}

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)[["published_utc", "title", "description", "keywords"]]
        df["date"] = pd.to_datetime(df["published_utc"]).dt.date
        return df

    def get_snapshot(self, ticker: str) -> dict:
        """Get current snapshot (latest price, greeks, etc.) for a ticker."""
        data = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}")
        return data.get("ticker", {})

    def get_technical_indicator(
        self,
        ticker: str,
        indicator: str,
        from_date: str,
        to_date: str,
        window: int = 14,
        timespan: str = "day",
    ) -> pd.Series:
        """
        Fetch built-in Polygon technical indicators.
        indicator: 'rsi', 'macd', 'sma', 'ema'
        """
        url = f"/v1/indicators/{indicator}/{ticker}"
        params = {
            "timespan": timespan,
            "adjusted": "true",
            "window": window,
            "series_type": "close",
            "from": from_date,
            "to": to_date,
            "limit": 5000,
            "order": "asc",
        }
        data = self._get(url, params)
        results = data.get("results", {}).get("values", [])
        if not results:
            return pd.Series(dtype=float)

        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.date
        df = df.set_index("date")

        if indicator == "macd":
            return df[["value", "signal", "histogram"]]
        return df["value"].rename(f"{indicator}_{window}")
