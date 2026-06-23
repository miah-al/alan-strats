"""
Polygon.io data fetching: OHLCV, options chains, news, indices.
"""

import os
import time
import json
import logging
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Polygon plans are per-asset-class. On this account the *stock* endpoints are
# the free Basic tier (5 req/min) while the *options* endpoints are paid
# (Options Starter — effectively unthrottled). So we keep two separate buckets:
# stock calls stay capped; options calls run fast. Override either via env.
_RPM         = int(os.environ.get("POLYGON_RPM", "5") or "5")
_OPTIONS_RPM = int(os.environ.get("POLYGON_OPTIONS_RPM", "100") or "100")


class RateLimitExceeded(Exception):
    """Raised when a slot can't be obtained within the caller's max_wait budget."""


class _RateLimiter:
    """Process-wide sliding-window limiter shared by every PolygonClient."""
    def __init__(self, max_calls: int, window: float = 60.0):
        self.max_calls = max(1, max_calls)
        self.window    = window
        self._times: deque[float] = deque()
        self._lock     = threading.Lock()

    def acquire(self, max_wait: float | None = None) -> None:
        """Block until a request slot is free. If max_wait is set and the next
        slot is further away than that, raise RateLimitExceeded instead of
        blocking — lets latency-sensitive callers fail fast and fall back."""
        while True:
            with self._lock:
                now = time.monotonic()
                while self._times and now - self._times[0] >= self.window:
                    self._times.popleft()
                if len(self._times) < self.max_calls:
                    self._times.append(now)
                    return
                wait = self.window - (now - self._times[0]) + 0.05
            if max_wait is not None and wait > max_wait:
                raise RateLimitExceeded(f"rate limit: next slot in {wait:.0f}s")
            time.sleep(min(wait, self.window))


class PolygonClient:
    BASE = "https://api.polygon.io"

    # Shared across all instances (callbacks create a fresh client per call).
    _stock_limiter   = _RateLimiter(_RPM)
    _options_limiter = _RateLimiter(_OPTIONS_RPM)
    _cache: dict[str, tuple[float, dict]] = {}
    _cache_lock = threading.Lock()
    CACHE_TTL = 45.0   # seconds; idempotent GETs are deduped within this window

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("POLYGON_API_KEY", "")
        if not self.api_key:
            raise ValueError("Set POLYGON_API_KEY env var or pass api_key")
        self.session = requests.Session()
        self.session.params = {"apiKey": self.api_key}

    @classmethod
    def _cache_get(cls, key: str):
        with cls._cache_lock:
            hit = cls._cache.get(key)
            if hit and time.monotonic() < hit[0]:
                return hit[1]
            if hit:
                cls._cache.pop(key, None)
        return None

    @classmethod
    def _cache_put(cls, key: str, value: dict) -> None:
        with cls._cache_lock:
            cls._cache[key] = (time.monotonic() + cls.CACHE_TTL, value)

    def _get(self, path: str, params: dict = None, retries: int = 3,
             use_cache: bool = True, max_wait: float | None = None) -> dict:
        url = self.BASE + path
        cache_key = path + "?" + json.dumps(params or {}, sort_keys=True)
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        # Options endpoints are on the paid tier — use the fast bucket; everything
        # else (stock aggregates/snapshots/grouped) uses the 5/min stock bucket.
        # Note options *aggregates* are /v2/aggs/ticker/O:... (no "/options/"), so
        # match the O: ticker too, else historical option bars hit the stock cap.
        is_options = ("/options/" in path) or ("/ticker/O:" in path)
        limiter = self._options_limiter if is_options else self._stock_limiter

        last_exc: Exception | None = None
        for attempt in range(retries):
            # max_wait lets latency-sensitive callers (e.g. live P&L on page load)
            # fail fast instead of blocking when the per-minute budget is spent.
            limiter.acquire(max_wait=max_wait)
            try:
                resp = self.session.get(url, params=params or {}, timeout=30)
                if resp.status_code == 429:
                    # Throttled despite the limiter — back off and retry.
                    time.sleep(12)
                    last_exc = requests.HTTPError("429 Too Many Requests", response=resp)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if use_cache:
                    self._cache_put(cache_key, data)
                return data
            except requests.RequestException as e:
                last_exc = e
                # Don't waste retries on an authorization failure — it won't change.
                if getattr(e, "response", None) is not None and e.response.status_code == 403:
                    raise
                if attempt == retries - 1:
                    raise
                time.sleep(2 ** attempt)
        # Loop exhausted (e.g. persistent 429) — surface it instead of returning None.
        raise last_exc or RuntimeError(f"Polygon request failed: {path}")

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
        max_wait: float | None = None,
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
            data = self._get(url, params, max_wait=max_wait)
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
