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
MAX_SPREAD_PTS = 20.0        # a vertical quoted wider than this (points) is treated as unquoted
# Where the cross-process count of broker requests is kept for the day. A module setting rather than a
# hard-coded path so the test suite can point it at a temporary folder: tests must neither read the live
# runner's count (and fail against their own small caps) nor add to it (and spend its budget).
BUDGET_STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paper_state")


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


def vertical_quote(long_leg: LegQuote, short_leg: LegQuote, now: datetime, carry_min: int = 30,
                   max_width: Optional[float] = None) -> Optional[Quote]:
    """Two-sided quote of a LONG vertical from its legs: bid = bid(long) - ask(short),
    ask = ask(long) - bid(short), last = the midpoint, age = minutes since the older leg updated.

    ``last`` is deliberately NOT last(long) - last(short). The two legs' prints happen at different
    times -- the snapshot feed carries no trade timestamp at all, so a leg that has not traded for an
    hour still reports one -- and subtracting them produces numbers that cannot exist: measured on
    2026-09-23, that construction valued a 50-wide vertical at 226 points. The midpoint is both
    well defined and, on that day's evidence, where spreads actually transact: of 1,458 two-leg
    verticals rebuilt from the day's multi-leg prints, the median filled at the derived mid, and
    whoever crossed paid about 1.2 points with the long leg 25+ points in the money, about 0.1
    nearer. So the mid is a live vertical's price (a strategy that crosses adds its own cost to
    it), and a synthetic "last" is not."""
    if long_leg.bid is None or long_leg.ask is None or short_leg.bid is None or short_leg.ask is None:
        return None
    for leg in (long_leg, short_leg):                       # a crossed, empty or one-sided leg quote is no quote
        if leg.ask <= 0 or leg.bid < 0 or leg.ask < leg.bid:
            return None
    bid = float(long_leg.bid) - float(short_leg.ask)
    ask = float(long_leg.ask) - float(short_leg.bid)
    # A derived width is the two legs' widths ADDED, not a spread anyone quotes, and it is widest
    # exactly when one leg is deep in the money -- which is this structure by design. A flat 20-point
    # cap threw away good quotes at the worst moment: with no quote the engine cannot check the target,
    # the adds or the stop on that bar. On 2026-09-23 the strategy's own 50-wide verticals quoted up
    # to 22.2 points wide at two of its target exits (median 7.5, p99 16.2 across 127 polls), so 20
    # would have blocked both.
    #
    # The cap scales with the structure instead: 60% of the strike width, 30 points on a 50-wide. That
    # leaves a third of headroom over anything observed, and still refuses a quote so wide that its
    # midpoint says nothing -- a leg quoted 0/100 would otherwise produce a mark that could fire a
    # target on its own.
    cap = max(float(MAX_SPREAD_PTS), 0.6 * float(max_width)) if max_width else float(MAX_SPREAD_PTS)
    if ask - bid > cap:
        return None
    # A long vertical is worth between nothing and the distance between its strikes -- that is
    # arbitrage, not an assumption. Leg quotes that disagree can in principle produce a midpoint
    # outside those bounds (a safeguard: no live mark has been seen to do it), and every decision
    # reads that midpoint: the target through ``last``, and the engine's own mark, add trigger and
    # daily loss cap through (bid + ask) / 2.
    #
    # So the MIDPOINT is what gets bounded, and the quote is shifted so that (bid + ask) / 2 lands
    # exactly on it, width unchanged. Clamping bid and ask separately -- the first version of this
    # -- is wrong: it drags the mid toward the middle of the range, so a raw 44/58 on a 50-wide
    # (mid 51, fairly worth at most 50) came out at 47, understating exactly the near-max marks
    # where targets are hit. A quote whose midpoint is already in range is left untouched.
    mid = (bid + ask) / 2.0
    if max_width:
        w = float(max_width)
        bounded = min(max(mid, 0.0), w)
        if bounded != mid:
            shift = bounded - mid
            bid, ask, mid = bid + shift, ask + shift, bounded
    ages = []
    for leg in (long_leg, short_leg):
        ref = leg.last_time or leg.updated
        ages.append(int((now - ref).total_seconds() // 60) if ref is not None else carry_min + 1)
    last = mid
    age = max(0, max(ages))
    if age > carry_min:
        return None
    legs = tuple((float(leg.bid), float(leg.ask), max(0, a)) for leg, a in zip((long_leg, short_leg), ages))
    return Quote(bid=bid, ask=ask, last=last, age=age, legs=legs)


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

_SDK_LOOP = None            # one loop for the whole process: asyncio.run() per call closes the SDK's
                            # pooled connections under it and the next call dies on "Event loop is closed"


def _sdk_loop():
    import asyncio
    global _SDK_LOOP
    if _SDK_LOOP is None or _SDK_LOOP.is_closed():
        _SDK_LOOP = asyncio.new_event_loop()
    return _SDK_LOOP


def _sdk_call(fn, *args, **kwargs):
    """Call a tastytrade SDK function and return its result, awaiting it when the installed SDK made it a
    coroutine (13.x did); a synchronous SDK or a test fake passes straight through. Every await runs on
    one long-lived loop, so the SDK's HTTP connection pool survives between calls."""
    import asyncio
    import inspect
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _sdk_loop().run_until_complete(result)
        raise RuntimeError("TastytradeProvider is synchronous and cannot be driven from inside a running event loop")
    return result


_CRED_HINT = ("tastytrade rejected the credentials ({why}). TT_SECRET is the Client Secret shown once when the OAuth "
              "application is created (not the Client ID); TT_REFRESH is the refresh token from Create Grant on that "
              "same application. A regenerated application needs both values replaced.")


def _credential_error(exc: Exception) -> Optional[RuntimeError]:
    msg = str(exc)
    low = msg.lower()
    if any(k in low for k in ("invalid_grant", "secret mismatch", "invalid_client", "invalid_grant_type")):
        return RuntimeError(_CRED_HINT.format(why=msg.strip()[:160]))
    return None


class RequestBudget:
    """A hard ceiling on calls to the broker's API, enforced where the request is made so no caller
    can exceed it: a floor between calls, a cap per minute and a cap per session day. tastytrade
    publishes no per-endpoint quota and suggests 50/s as a client-side ceiling; the paper runner
    needs about 4 a minute, so these are set far below what would ever draw a 429."""

    def __init__(self, min_interval_s: float = 5.0, per_minute: int = 20, per_day: int = 3000, clock=None, sleep=None,
                 shared_path: Optional["Path"] = None):
        import time as _time
        self.min_interval_s = float(min_interval_s); self.per_minute = int(per_minute); self.per_day = int(per_day)
        self._clock = clock or _time.monotonic; self._sleep = sleep or _time.sleep
        self._last: Optional[float] = None
        self._minute: list[float] = []            # monotonic times of calls in the last 60 s
        self.calls_today = 0
        self.waits = 0
        # The day's cap has to hold across PROCESSES, not just within one: a paper session, a streamer
        # and an ad-hoc script each counting to 3000 privately is three times the intended ceiling.
        # A small shared file keeps one running total for the day; if it cannot be used the budget
        # still works, just per process, so a filesystem problem never blocks trading.
        if shared_path is None:
            from pathlib import Path as _Path
            shared_path = _Path(BUDGET_STATE_DIR) / f"broker_calls_{date.today().isoformat()}.json"
        self.shared_path = shared_path
        self.shared_calls = 0

    def _bump_shared(self) -> int:
        """Add one to the day's cross-process total and return it (0 when the file is unusable)."""
        import json
        import os
        try:
            self.shared_path.parent.mkdir(parents=True, exist_ok=True)
            lock = self.shared_path.with_suffix(".lock")
            for _ in range(50):                       # a brief spin: every writer holds the lock for microseconds
                try:
                    fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    break
                except FileExistsError:
                    self._sleep(0.01)
            else:
                try:                                  # a stale lock from a killed process must not wedge the day
                    os.unlink(str(lock))
                except OSError:
                    pass
                return self.shared_calls
            try:
                total = 0
                if self.shared_path.exists():
                    try:
                        total = int(json.loads(self.shared_path.read_text(encoding="utf-8")).get("calls", 0))
                    except (ValueError, OSError):
                        total = 0
                total += 1
                self.shared_path.write_text(json.dumps({"date": date.today().isoformat(), "calls": total}), encoding="utf-8")
                self.shared_calls = total
                return total
            finally:
                os.close(fd)
                try:
                    os.unlink(str(lock))
                except OSError:
                    pass
        except OSError:
            return self.shared_calls

    def take(self) -> None:
        """Block until a call is allowed, then count it. Raises when the day's budget is spent."""
        if self.calls_today >= self.per_day:
            raise RuntimeError(f"tastytrade request budget spent: {self.calls_today} calls today (cap {self.per_day}); not calling again today")
        if self.shared_calls >= self.per_day:
            raise RuntimeError(f"tastytrade request budget spent across all processes: {self.shared_calls} calls today "
                               f"(cap {self.per_day}); not calling again today")
        now = self._clock()
        if self._last is not None and now - self._last < self.min_interval_s:
            self._sleep(self.min_interval_s - (now - self._last)); self.waits += 1; now = self._clock()
        self._minute = [x for x in self._minute if now - x < 60.0]
        if len(self._minute) >= self.per_minute:
            self._sleep(60.0 - (now - self._minute[0]) + 0.01); self.waits += 1; now = self._clock()
            self._minute = [x for x in self._minute if now - x < 60.0]
        self._last = now; self._minute.append(now); self.calls_today += 1
        self._bump_shared()


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
        self._creds = (secret, refresh, is_test)
        self.session = Session(secret, refresh, is_test=is_test)
        self._chain: dict = {}
        self._samples: list[tuple[datetime, float]] = []
        self.expiry: Optional[date] = None
        self.budget = RequestBudget()                 # every REST call goes through it (see RequestBudget)

    # chain for today's expiry
    def load_chain(self, day: date) -> int:
        from tastytrade.instruments import get_option_chain
        self.budget.take()
        try:
            chain = _sdk_call(get_option_chain, self.session, self.underlying)
        except Exception as exc:
            err = _credential_error(exc)
            if err is not None:
                raise err from None
            raise
        # only the configured (PM-settled) root: an AM-settled monthly on a third Friday settles on the
        # open and cannot be traded as a same-day expiry, so a day without the root is a blocked day
        opts = [o for o in chain.get(day, []) if str(o.root_symbol).upper() == self.root]
        self._chain = {(str(o.option_type.value if hasattr(o.option_type, "value") else o.option_type)[0].upper(), float(o.strike_price)): o
                       for o in opts}
        self.expiry = day
        return len(self._chain)

    def near_the_money_vertical(self, spot: float, width: float, itm_offset: float, kind: str = "call") -> tuple[Optional[str], Optional[str], float, float]:
        """The strategy's own structure at ``spot``: strikes on the loaded chain's grid, the long leg
        ``itm_offset`` past the mid-strike. Returns (long_symbol, short_symbol, k_low, k_high)."""
        cp = "C" if kind == "call" else "P"
        strikes = sorted(K for (c, K) in self._chain if c == cp)
        if len(strikes) < 2:
            return None, None, 0.0, 0.0
        mid_target = spot - itm_offset if kind == "call" else spot + itm_offset
        k_low = min(strikes, key=lambda K: abs((K + width / 2) - mid_target))
        k_high = k_low + width
        if (cp, k_high) not in self._chain:                 # the grid may skip a strike: take the nearest one listed
            k_high = min(strikes, key=lambda K: abs(K - (k_low + width)))
        long_sym, short_sym = self.leg_symbols(kind, k_low, k_high)
        return long_sym, short_sym, k_low, k_high

    def _symbol(self, cp: str, K: float) -> Optional[str]:
        o = self._chain.get((cp, float(K)))
        return o.symbol if o is not None else None

    def leg_symbols(self, kind: str, k_low: float, k_high: float) -> tuple[Optional[str], Optional[str]]:
        cp = "C" if kind == "call" else "P"
        long_k, short_k = (k_low, k_high) if kind == "call" else (k_high, k_low)
        return self._symbol(cp, long_k), self._symbol(cp, short_k)

    def _relogin(self) -> None:
        """A fresh OAuth session (the access token expires during a long day)."""
        from tastytrade import Session
        secret, refresh, is_test = self._creds
        self.session = Session(secret, refresh, is_test=is_test)
        logger.info("tastytrade session re-created")

    # one REST call: the underlying plus every option symbol requested
    def fetch(self, option_symbols: list[str]) -> dict[str, LegQuote]:
        from tastytrade.market_data import get_market_data_by_type
        syms = [s for s in option_symbols if s]
        if len(syms) > 100:                            # the endpoint takes up to 100 symbols per call; more would mean two
            raise RuntimeError(f"{len(syms)} option symbols in one fetch; the paper runner watches a handful, this is a bug")
        self.budget.take()
        try:
            rows = _sdk_call(get_market_data_by_type, self.session, indices=[self.underlying], options=syms)
        except Exception as exc:                       # 401 / expired token / dropped connection: one re-login, one retry
            err = _credential_error(exc)               # a wrong secret is not fixed by logging in again
            if err is not None:
                raise err from None
            msg = str(exc).lower()
            if any(k in msg for k in ("401", "unauthor", "token", "expired", "forbidden", "connection")):
                self._relogin()
                self.budget.take()
                rows = _sdk_call(get_market_data_by_type, self.session, indices=[self.underlying], options=syms)
            else:
                raise
        out: dict[str, LegQuote] = {}

        def et(ts):
            if ts is None:
                return None
            t = pd.Timestamp(ts)
            t = t.tz_convert(ET) if t.tzinfo is not None else t.tz_localize("UTC").tz_convert(ET)
            return t.tz_localize(None).to_pydatetime()

        self._last_rows = {str(r.symbol): r for r in rows}        # the SDK rows, for anything that wants sizes or volume
        for r in rows:
            out[str(r.symbol)] = LegQuote(symbol=str(r.symbol), bid=(float(r.bid) if r.bid is not None else None),
                                          ask=(float(r.ask) if r.ask is not None else None),
                                          last=(float(r.last) if r.last is not None else None),
                                          last_time=et(getattr(r, "last_trade_time", None)), updated=et(getattr(r, "updated_at", None)))
        return out

    def last_row(self, symbol):
        """The raw SDK row from the most recent fetch (bid and ask sizes, volume, last trade), or None."""
        return getattr(self, "_last_rows", {}).get(str(symbol)) if symbol else None

    def sample_underlying(self, quotes: dict[str, LegQuote], when: datetime) -> Optional[float]:
        q = quotes.get(self.underlying)
        if q is None:
            return None
        px = q.last if q.last is not None else (((q.bid or 0) + (q.ask or 0)) / 2.0 if q.bid and q.ask else None)
        if px is not None:
            self._samples.append((when, float(px)))
        return px

    def backfill_bars(self, day: date, until: datetime) -> list[Bar]:
        """Today's earlier 1-minute bars, for a runner that starts after 09:30: the engine's 30-minute
        lookback needs them, and without them it cannot signal until it has polled its own history.

        The broker's own candle feed, deliberately and only. A live session takes every number from
        the venue it trades on, so its bars cannot disagree with its quotes; Polygon belongs to
        backtests and stored history, not here. Returns the bars strictly before ``until``."""
        bars = self._backfill_from_stream(day, until)
        if bars:
            logger.info("backfilled %d bars from the broker's candle feed (%s to %s)",
                        len(bars), bars[0].ts.strftime("%H:%M"), bars[-1].ts.strftime("%H:%M"))
        return bars

    def _backfill_from_stream(self, day: date, until: datetime) -> list[Bar]:
        """Today's 1-minute candles over DXLink. Costs no REST budget: it is a market-data subscription
        that replays from ``fromTime``, then goes quiet once it has sent what it holds."""
        async def _pull() -> list[Bar]:
            import anyio
            from tastytrade import DXLinkStreamer
            from tastytrade.dxfeed import Candle
            start = datetime.combine(day, dtime(9, 30))
            out: dict[datetime, Bar] = {}
            async with DXLinkStreamer(self.session) as st:
                await st.subscribe_candle([self.underlying], "1m", start_time=start)
                quiet = 0
                while quiet < 12 and len(out) < 500:      # stop after ~3 s with nothing new
                    await anyio.sleep(0.25)
                    fresh = False
                    c = st.get_event_nowait(Candle)
                    while c is not None:
                        if c.time and c.close:
                            ts = datetime.fromtimestamp(c.time / 1000)
                            if start <= ts < until:
                                out[ts] = Bar(ts=ts, open=float(c.open), high=float(c.high),
                                              low=float(c.low), close=float(c.close))
                                fresh = True
                        c = st.get_event_nowait(Candle)
                    quiet = 0 if fresh else quiet + 1
            return [out[k] for k in sorted(out)]

        try:
            return _sdk_loop().run_until_complete(_pull())
        except Exception as exc:
            logger.warning("backfill from the broker's candle feed failed: %s", exc)
            return []

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
        # the strikes give the arbitrage bound on how wide this vertical's quote can sensibly be
        return vertical_quote(quotes[ls], quotes[ss], now, carry_min, max_width=abs(float(k_high) - float(k_low)))
