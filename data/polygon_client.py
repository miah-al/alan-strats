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

    def get_options_chain(
        self,
        underlying: str,
        expiration_date: str = None,
        snapshot_date: str = None,
        expiration_date_gte: str = None,
        expiration_date_lte: str = None,
        strike_price_gte: float = None,
        strike_price_lte: float = None,
    ) -> pd.DataFrame:
        """
        Fetch options chain.
        snapshot_date:        historical EOD snapshot (YYYY-MM-DD); omit for today.
        expiration_date:      exact expiry filter.
        expiration_date_gte/lte: date range filter — use these to limit DTE window
                              and avoid fetching thousands of contracts.
        strike_price_gte/lte: strike range filter — pass spot ± N% to stay near-the-money.
        """
        results = []
        url = f"/v3/snapshot/options/{underlying}"
        params = {"limit": 250}
        if expiration_date:
            params["expiration_date"] = expiration_date
        if snapshot_date:
            params["date"] = snapshot_date
        if expiration_date_gte:
            params["expiration_date.gte"] = expiration_date_gte
        if expiration_date_lte:
            params["expiration_date.lte"] = expiration_date_lte
        if strike_price_gte is not None:
            params["strike_price.gte"] = strike_price_gte
        if strike_price_lte is not None:
            params["strike_price.lte"] = strike_price_lte
        while url:
            data = self._get(url, params)
            results.extend(data.get("results", []))
            url = (data.get("next_url") or "").replace(self.BASE, "") or None
            params = {}

        if not results:
            return pd.DataFrame()

        # DTE must be relative to the snapshot date, not today — otherwise historical
        # rows get wrong DTE (e.g. a 30-DTE option fetched 2 years ago would show -700).
        snap_ts = pd.Timestamp(snapshot_date) if snapshot_date else pd.Timestamp.today()
        snap_ts = snap_ts.normalize()
        rows = []
        for r in results:
            d = r.get("details", {})
            g = r.get("greeks", {}) or {}
            exp_str = d.get("expiration_date")
            try:
                dte = (pd.Timestamp(exp_str) - snap_ts).days if exp_str else None
            except Exception:
                dte = None
            lq  = r.get("last_quote", {}) or {}
            day = r.get("day", {}) or {}
            bid = lq.get("bid")
            ask = lq.get("ask")
            # Historical snapshots (date= param) don't populate last_quote bid/ask —
            # fall back to day.vwap → day.close as the mid price proxy.
            if bid is None and ask is None:
                mid_proxy = day.get("vwap") or day.get("close")
                if mid_proxy is not None:
                    iv_val = r.get("implied_volatility")
                    # Estimate a realistic spread: wider for low-priced / illiquid options
                    spread_pct = 0.04 if mid_proxy < 1 else 0.02
                    spread = max(0.01, float(mid_proxy) * spread_pct)
                    bid = float(mid_proxy) - spread / 2
                    ask = float(mid_proxy) + spread / 2
            rows.append({
                "strike":       d.get("strike_price"),
                "type":         d.get("contract_type"),
                "expiration":   exp_str,
                "dte":          dte,
                "bid":          float(bid) if bid is not None else float("nan"),
                "ask":          float(ask) if ask is not None else float("nan"),
                "iv":           r.get("implied_volatility"),
                "delta":        g.get("delta"),
                "gamma":        g.get("gamma"),
                "theta":        g.get("theta"),
                "vega":         g.get("vega"),
                "open_interest":r.get("open_interest"),
                "volume":       r.get("day", {}).get("volume"),
            })
        return pd.DataFrame(rows)

    def get_expirations(self, underlying: str, as_of: str = None) -> list[str]:
        """Get available expiration dates via options snapshot."""
        # Use the snapshot endpoint — reference/options requires a specific contract ticker
        params = {"limit": 250}
        if as_of:
            params["expiration_date.gte"] = as_of
        data = self._get(f"/v3/snapshot/options/{underlying}", params)
        exps = sorted(set(
            r.get("details", {}).get("expiration_date", "")
            for r in data.get("results", [])
            if r.get("details", {}).get("expiration_date")
        ))
        return exps

    def get_news(
        self,
        ticker: str,
        from_date: str,
        to_date: str,
        limit: int = 5000,
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
