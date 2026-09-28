"""
api/marketdata/providers/yfinance.py — the batched polling fallback.

Equities and indices: one ``yf.download`` of recent daily bars for the whole batch per poll (today's
partial bar is the live-ish last and volume, the prior bar the previous close; no bid/ask).
Options: one ``option_chain`` request per underlying and expiry (bid, ask, last, IV, open interest,
volume), greeks computed with Black-Scholes on the quoted IV. Every request passes the service's
request gate (yfinance's own request function is wrapped), and the hub polls no faster than once
per ``poll_interval`` per batch.
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
from collections import defaultdict
from datetime import date
from typing import Optional

import pandas as pd

from api.marketdata import symbols as SYM
from api.marketdata.limits import ProviderLimits
from api.marketdata.providers.base import Provider
from api.marketdata.providers.polygon import pick_strikes

logger = logging.getLogger("alan_trader.api.marketdata.yfinance")
RISK_FREE = 0.045
TICKER_TTL_S = 900.0


class YFinanceProvider(Provider):
    name = "yfinance"
    streaming = False
    poll_interval = 15.0
    capabilities = frozenset({"quotes", "options", "chain"})
    #: where this provider ranks per chain field group (api/marketdata/options.py; lower first)
    chain_ranks = {"skeleton": 1, "quotes": 1, "greeks": 2, "sizes": 2}

    def __init__(self, limits: ProviderLimits):
        super().__init__(limits)
        # one yfinance Ticker per underlying for a while: it keeps the expirations list it fetched, so
        # each option_chain() call is one request rather than two
        self._tickers: dict[str, tuple[float, object]] = {}
        try:
            import yfinance  # noqa: F401
        except Exception:
            limits.disable("yfinance not installed")

    def supports(self, symbol: str) -> bool:
        return self.available()

    # ── quotes ────────────────────────────────────────────────────────────────
    def poll(self, symbols: list[str]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        opts = [s for s in symbols if SYM.is_option(s)]
        plain = [s for s in symbols if not SYM.is_option(s)]
        if plain:
            out.update(self._daily(plain))
        groups: dict[tuple[str, date], list] = defaultdict(list)
        for s in opts:
            o = SYM.parse_option(s)
            groups[(o.underlying, o.expiry)].append(o)
        for (und, exp), legs in groups.items():
            calls, puts = self._option_frames(und, exp)
            spot = None
            for o in legs:
                df = calls if o.right == "C" else puts
                if df is None or df.empty:
                    continue
                row = df[df["contractSymbol"].astype(str).str.upper() == o.occ]
                if row.empty:
                    row = df[(pd.to_numeric(df["strike"], errors="coerce") - o.strike).abs() < 1e-6]
                if row.empty:
                    continue
                if spot is None:
                    spot = self._spot(und)
                out[o.occ] = {"fields": _option_fields(row.iloc[0], o.type, o.strike, exp, spot), "time": None}
        return out

    def _daily(self, syms: list[str]) -> dict[str, dict]:
        import yfinance as yf
        ymap = {SYM.to_yfinance(s): s for s in syms}
        raw = yf.download(list(ymap), period="5d", interval="1d", auto_adjust=False, progress=False,
                          threads=False, group_by="ticker")
        out: dict[str, dict] = {}
        if raw is None or raw.empty:
            return out
        multi = isinstance(raw.columns, pd.MultiIndex)
        for ysym, sym in ymap.items():
            try:
                sub = raw[ysym] if multi else raw
                sub = sub.dropna(subset=["Close"])
                if sub.empty:
                    continue
                last, prev = sub.iloc[-1], (sub.iloc[-2] if len(sub) > 1 else None)
                out[sym] = {"fields": {"last": last["Close"], "open": last.get("Open"), "high": last.get("High"),
                                       "low": last.get("Low"), "volume": last.get("Volume"),
                                       "prev_close": prev["Close"] if prev is not None else None},
                            "time": None}
            except Exception:
                continue
        return out

    def _spot(self, underlying: str) -> Optional[float]:
        q = self._daily([underlying]).get(underlying)
        return float(q["fields"]["last"]) if q and q["fields"].get("last") is not None else None

    def _ticker(self, underlying: str):
        import time as _time
        import yfinance as yf
        hit = self._tickers.get(underlying)
        if hit is not None and _time.monotonic() - hit[0] < TICKER_TTL_S:
            return hit[1]
        t = yf.Ticker(SYM.to_yfinance(underlying))
        self._tickers[underlying] = (_time.monotonic(), t)
        return t

    def _option_frames(self, underlying: str, expiry: date):
        try:
            ch = self._ticker(underlying).option_chain(expiry.isoformat())
            return ch.calls, ch.puts
        except Exception as exc:
            logger.debug("yfinance option chain %s %s failed: %s", underlying, expiry, exc)
            return None, None

    # ── chains ────────────────────────────────────────────────────────────────
    def expirations(self, underlying: str, spot: Optional[float] = None) -> list[date]:
        exps = self._ticker(underlying).options or ()
        return sorted(d for d in (_dt.date.fromisoformat(e) for e in exps) if d >= _dt.date.today())

    def chain(self, underlying: str, expiry: date, spot: Optional[float], strikes: int) -> Optional[dict]:
        calls, puts = self._option_frames(underlying, expiry)
        if (calls is None or calls.empty) and (puts is None or puts.empty):
            return None
        by_k: dict[float, dict] = defaultdict(dict)
        for side, df in (("call", calls), ("put", puts)):
            if df is None or df.empty:
                continue
            for _, r in df.iterrows():
                k = float(r["strike"])
                q = _option_fields(r, side, k, expiry, spot)
                q["symbol"] = SYM.normalize(str(r["contractSymbol"])) if SYM.is_option(str(r["contractSymbol"])) else None
                by_k[k][side] = q
        return {"rows": pick_strikes(by_k, spot, strikes), "source": self.name}


def _option_fields(r, otype: str, strike: float, expiry: date, spot: Optional[float]) -> dict:
    def num(x):
        try:
            f = float(x)
            return f if math.isfinite(f) else None
        except (TypeError, ValueError):
            return None
    iv = num(r.get("impliedVolatility"))
    bid, ask = num(r.get("bid")), num(r.get("ask"))
    two_sided = ask is not None and ask > 0 and bid is not None and bid <= ask     # 0 bid / 0.05 ask is a quote
    f = {"bid": bid if two_sided else None, "ask": ask if two_sided else None,
         "last": num(r.get("lastPrice")), "volume": num(r.get("volume")), "oi": num(r.get("openInterest")),
         "iv": iv if iv and iv > 0.0001 else None}
    if spot and f["iv"]:
        from paper.views import _bs_full
        t = max((expiry - _dt.date.today()).days, 0) / 365.0 + 1.0 / 365.0
        _px, delta, gamma, vega, theta, _vanna = _bs_full(float(spot), float(strike), t, RISK_FREE, f["iv"], otype)
        f.update(delta=float(delta), gamma=float(gamma), vega=float(vega), theta=float(theta))
    return f
