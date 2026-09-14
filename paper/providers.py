"""Quote and bar providers for the paper runner.

A provider answers three questions every minute: what time is it (ET, naive), what did the
underlying do this minute (a 1-minute bar), and what is the two-sided quote for a given
vertical on today's expiry. Two implementations:

  TastytradeProvider  real time, from the tastytrade REST market-data endpoint (OAuth session
                      from TT_SECRET / TT_REFRESH in .env), option chain from the same API
  ReplayProvider      a stored session from the platform database (mkt.MinuteBar for the
                      underlying, mkt.OptionMinuteBar prints for the legs, bid/ask = print -/+ a
                      half spread), for tests and dry runs; runs as fast as the loop lets it
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from typing import Optional

import pandas as pd

from strategy_api.live import Quote

logger = logging.getLogger("paper.providers")
ET = "US/Eastern"


def now_et() -> datetime:
    """Naive US/Eastern wall-clock time."""
    return pd.Timestamp.now(tz=ET).tz_localize(None).to_pydatetime()


@dataclass
class Bar:
    ts: datetime          # bar START (naive ET)
    open: float
    high: float
    low: float
    close: float


@dataclass
class LegQuote:
    symbol: str
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    last_time: Optional[datetime]     # naive ET
    updated: Optional[datetime]       # naive ET


def vertical_quote(long_leg: LegQuote, short_leg: LegQuote, now: datetime, carry_min: int = 30) -> Optional[Quote]:
    """Two-sided quote of a LONG vertical from its legs: bid = bid(long) - ask(short),
    ask = ask(long) - bid(short), last = last(long) - last(short) (falls back to the mid when a
    leg has not printed), age = minutes since the older of the two legs' last prints/updates."""
    if long_leg.bid is None or long_leg.ask is None or short_leg.bid is None or short_leg.ask is None:
        return None
    bid = float(long_leg.bid) - float(short_leg.ask)
    ask = float(long_leg.ask) - float(short_leg.bid)
    mid = (bid + ask) / 2.0
    lasts, ages = [], []
    for leg in (long_leg, short_leg):
        ref = leg.last_time or leg.updated
        ages.append(int((now - ref).total_seconds() // 60) if ref is not None else carry_min + 1)
        lasts.append(float(leg.last) if leg.last is not None else None)
    last = (lasts[0] - lasts[1]) if (lasts[0] is not None and lasts[1] is not None) else mid
    age = max(0, max(ages))
    if age > carry_min:
        return None
    return Quote(bid=bid, ask=ask, last=last, age=age)


# ── replay ────────────────────────────────────────────────────────────────────

class ReplayProvider:
    """Serves a stored session minute by minute. ``half_spread`` brackets each print into a
    bid/ask, the same assumption the market-priced backtest uses, so a replay run of the
    runner must reproduce the backtest's fills for that day."""

    name = "replay"

    def __init__(self, engine, underlying: str, day: date, half_spread: float = 0.5, carry_min: int = 30, root: str = "NDXP"):
        from db.client import get_minute_bars, get_option_minute_bars
        self.day = day
        self.underlying = underlying.upper()
        self.root = root
        self.h = float(half_spread)
        self.carry = int(carry_min)
        bars = get_minute_bars(engine, self.underlying, day, day)
        if bars.empty:
            raise RuntimeError(f"no {self.underlying} minute bars stored for {day}")
        self.bars = bars.sort_values("ts").reset_index(drop=True)
        prints = get_option_minute_bars(engine, self.underlying, day, day, expiry=day)
        self._prints: dict[tuple[str, float], tuple[list[int], list[float]]] = {}
        if len(prints):
            prints = prints.copy()
            ts = pd.to_datetime(prints["ts"])
            prints["m"] = (ts.dt.hour * 60 + ts.dt.minute + 1).astype(int)
            for (r, k), g in prints.groupby([prints["right"].str.upper().str[0], prints["strike"].astype(float)]):
                g = g.sort_values("m").drop_duplicates("m", keep="last")
                self._prints[(r, float(k))] = (g["m"].tolist(), g["close"].astype(float).tolist())
        self._i = -1
        self.expiry = day

    def has_option_data(self) -> bool:
        return bool(self._prints)

    # the clock: each call to next_bar advances one minute
    def next_bar(self) -> Optional[Bar]:
        self._i += 1
        if self._i >= len(self.bars):
            return None
        r = self.bars.iloc[self._i]
        return Bar(ts=pd.Timestamp(r.ts).to_pydatetime(), open=float(r.open), high=float(r.high), low=float(r.low), close=float(r.close))

    def is_last_bar(self) -> bool:
        return self._i >= len(self.bars) - 1

    def _leg(self, right: str, K: float, minute: int) -> Optional[tuple[float, int]]:
        arr = self._prints.get((right, float(K)))
        if arr is None:
            return None
        mins, px = arr
        import bisect
        i = bisect.bisect_right(mins, minute) - 1
        if i < 0:
            return None
        age = minute - mins[i]
        if age > self.carry:
            return None
        return px[i], age

    def quote_vertical(self, kind: str, k_low: float, k_high: float, minute: int) -> Optional[Quote]:
        """Same valuation as the backtest's MarketPricer: the fresher of the two sides, parity for the other."""
        width = float(k_high - k_low)
        same = "C" if kind == "call" else "P"; other = "P" if same == "C" else "C"
        cands = []
        a, b = self._leg(same, k_low, minute), self._leg(same, k_high, minute)
        if a and b:
            v = (a[0] - b[0]) if same == "C" else (b[0] - a[0]); cands.append((v, max(a[1], b[1])))
        a, b = self._leg(other, k_low, minute), self._leg(other, k_high, minute)
        if a and b:
            v = (a[0] - b[0]) if other == "C" else (b[0] - a[0]); cands.append((width - v, max(a[1], b[1])))
        if not cands:
            return None
        v, age = min(cands, key=lambda t: t[1])
        v = min(width, max(0.0, v))
        return Quote(bid=v - self.h, ask=v + self.h, last=v, age=int(age))

    def leg_symbols(self, kind: str, k_low: float, k_high: float) -> tuple[str, str]:
        """OCC-style symbols for the ledger (long leg, short leg)."""
        cp = "C" if kind == "call" else "P"
        long_k, short_k = (k_low, k_high) if kind == "call" else (k_high, k_low)
        occ = lambda k: f"{self.root}{self.day.strftime('%y%m%d')}{cp}{int(round(k * 1000)):08d}"
        return occ(long_k), occ(short_k)


# ── tastytrade ────────────────────────────────────────────────────────────────

class TastytradeProvider:
    """Real-time quotes through the tastytrade API. Needs TT_SECRET and TT_REFRESH (OAuth) in the
    environment or .env; ``is_test`` selects the certification environment. Polls the REST
    market-data endpoint; one call returns the underlying and every leg it is asked for."""

    name = "tastytrade"

    def __init__(self, underlying: str = "NDX", root: str = "NDXP", is_test: bool = False, poll_seconds: int = 15):
        self.underlying = underlying.upper()
        self.root = root.upper()
        self.poll_seconds = int(poll_seconds)
        try:
            from app import _load_env                     # the platform's own .env reader (no python-dotenv needed)
            _load_env()
        except Exception:
            pass
        secret, refresh = os.environ.get("TT_SECRET"), os.environ.get("TT_REFRESH")
        if not secret or not refresh:
            raise RuntimeError("tastytrade credentials missing: set TT_SECRET and TT_REFRESH in .env (OAuth provider secret and refresh token)")
        from tastytrade import Session
        self.session = Session(secret, refresh, is_test=is_test)
        self._chain: dict = {}
        self._samples: list[tuple[datetime, float]] = []
        self.expiry: Optional[date] = None

    # chain for today's expiry
    def load_chain(self, day: date) -> int:
        from tastytrade.instruments import get_option_chain
        chain = get_option_chain(self.session, self.underlying)
        opts = [o for o in chain.get(day, []) if str(o.root_symbol).upper() == self.root]
        if not opts:                                   # third Fridays before mid-2025 listed only the AM root
            opts = list(chain.get(day, []))
        self._chain = {(str(o.option_type.value if hasattr(o.option_type, "value") else o.option_type)[0].upper(), float(o.strike_price)): o
                       for o in opts}
        self.expiry = day
        return len(self._chain)

    def _symbol(self, cp: str, K: float) -> Optional[str]:
        o = self._chain.get((cp, float(K)))
        return o.symbol if o is not None else None

    def leg_symbols(self, kind: str, k_low: float, k_high: float) -> tuple[Optional[str], Optional[str]]:
        cp = "C" if kind == "call" else "P"
        long_k, short_k = (k_low, k_high) if kind == "call" else (k_high, k_low)
        return self._symbol(cp, long_k), self._symbol(cp, short_k)

    # one REST call: the underlying plus every option symbol requested
    def fetch(self, option_symbols: list[str]) -> dict[str, LegQuote]:
        from tastytrade.market_data import get_market_data_by_type
        rows = get_market_data_by_type(self.session, indices=[self.underlying], options=[s for s in option_symbols if s])
        out: dict[str, LegQuote] = {}

        def et(ts):
            if ts is None:
                return None
            t = pd.Timestamp(ts)
            t = t.tz_convert(ET) if t.tzinfo is not None else t.tz_localize("UTC").tz_convert(ET)
            return t.tz_localize(None).to_pydatetime()

        for r in rows:
            out[str(r.symbol)] = LegQuote(symbol=str(r.symbol), bid=(float(r.bid) if r.bid is not None else None),
                                          ask=(float(r.ask) if r.ask is not None else None),
                                          last=(float(r.last) if r.last is not None else None),
                                          last_time=et(getattr(r, "last_trade_time", None)), updated=et(getattr(r, "updated_at", None)))
        return out

    def sample_underlying(self, quotes: dict[str, LegQuote], when: datetime) -> Optional[float]:
        q = quotes.get(self.underlying)
        if q is None:
            return None
        px = q.last if q.last is not None else (((q.bid or 0) + (q.ask or 0)) / 2.0 if q.bid and q.ask else None)
        if px is not None:
            self._samples.append((when, float(px)))
        return px

    def close_minute(self, minute_start: datetime) -> Optional[Bar]:
        """Build the 1-minute bar for ``minute_start`` from the samples taken during it."""
        end = minute_start + timedelta(minutes=1)
        s = [px for t, px in self._samples if minute_start <= t < end]
        self._samples = [(t, px) for t, px in self._samples if t >= end]
        if not s:
            return None
        return Bar(ts=minute_start, open=s[0], high=max(s), low=min(s), close=s[-1])

    def quote_vertical(self, kind: str, k_low: float, k_high: float, quotes: dict[str, LegQuote], now: datetime, carry_min: int = 30) -> Optional[Quote]:
        ls, ss = self.leg_symbols(kind, k_low, k_high)
        if not ls or not ss or ls not in quotes or ss not in quotes:
            return None
        return vertical_quote(quotes[ls], quotes[ss], now, carry_min)
