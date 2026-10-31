"""
api/services/intraday.py — a session's 1-minute bars, as current as the service can make them.

``GET /api/market/intraday/{ticker}``: the vendor's 1-minute bars for the session (yfinance: ^NDX / ^SPX for the
indices, the ticker itself for stocks and ETFs; Polygon's minute aggregates as a stock's fallback) — each fetched
through the request gate at most once a minute per symbol — then, for the minutes after the vendor's last bar, bars built
from the market-data hub's live quotes (an index at its level, a stock at its mid). The hub's minutes exist only
for a symbol the service has been watching: asking for a symbol watches it for 20 minutes, and only while the
broker's stream is up (a stream costs no request budget; a polling fallback would, so it is not asked).

The session is today once the market has opened on a trading day, else the last trading day.
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
import time
from typing import Optional

import pandas as pd

logger = logging.getLogger("alan_trader.api.intraday")

NY = "America/New_York"
OPEN, CLOSE = _dt.time(9, 30), _dt.time(16, 0)
VENDOR_TTL = 60.0
WATCH_FOR_S = 20 * 60.0
OWNER = "intraday"


def session_day(now: pd.Timestamp) -> _dt.date:
    from api.services.gex_recorder import previous_trading_day, trading_day
    d = now.date()
    if trading_day(d) and now.time() >= OPEN:
        return d
    return previous_trading_day(d)


class MinuteAggregator:
    """Today's 1-minute bars from the hub's quotes (any symbol whose quotes flow; the ones asked for are watched
    while the broker streams)."""

    def __init__(self, hub, clock=None):
        self.hub = hub
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self._lock = threading.Lock()
        self._bars: dict[str, dict[pd.Timestamp, list]] = {}     # symbol -> minute -> [o, h, l, c, vol]
        self._cum: dict[str, float] = {}                          # symbol -> the last cumulative day volume seen
        self._wanted: dict[str, float] = {}                       # symbol -> monotonic time asked
        self._watching: set[str] = set()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self.hub is not None:
            self.hub.listeners.append(self.on_quote)
        self._thread = threading.Thread(target=self._run, name="intraday-minutes", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.hub is not None:
            try:
                self.hub.listeners.remove(self.on_quote)
            except ValueError:
                pass
            self.hub.unwatch_all(OWNER)

    def _streaming(self) -> bool:
        p = getattr(self.hub, "by_name", {}).get("tastytrade") if self.hub is not None else None
        return bool(p is not None and getattr(p, "connected", False))

    def want(self, symbol: str) -> None:
        from api.marketdata import symbols as SYM
        try:
            symbol = SYM.normalize(symbol)
        except ValueError:
            return
        with self._lock:
            self._wanted[symbol] = time.monotonic()
        self._sync_watch()

    def _sync_watch(self) -> None:
        if self.hub is None:
            return
        now = time.monotonic()
        with self._lock:
            live = {s for s, t in self._wanted.items() if now - t < WATCH_FOR_S}
            for s in [s for s in self._wanted if s not in live]:
                self._wanted.pop(s, None)
        want = live if self._streaming() else set()
        add, drop = want - self._watching, self._watching - want
        if add:
            self.hub.watch(OWNER, sorted(add))
        if drop:
            self.hub.unwatch(OWNER, sorted(drop))
        self._watching = want

    def _run(self) -> None:
        while not self._stop.wait(30.0):
            try:
                self._sync_watch()
                self._prune()
            except Exception:
                logger.debug("intraday watch sync failed", exc_info=True)

    def _prune(self) -> None:
        cutoff = self.clock().normalize() - pd.Timedelta(days=1)
        with self._lock:
            for s, bars in self._bars.items():
                for k in [k for k in bars if k < cutoff]:
                    bars.pop(k, None)

    @staticmethod
    def price_of(symbol: str, msg: dict) -> Optional[float]:
        from api.marketdata import symbols as SYM
        order = ("last", "mid") if SYM.is_index(symbol) else ("mid", "last")
        for k in order:
            v = msg.get(k)
            if v is not None:
                return float(v)
        return None

    def on_quote(self, symbol: str, msg: dict) -> None:
        with self._lock:
            tracked = symbol in self._wanted
        if not tracked:
            return
        px = self.price_of(symbol, msg)
        if px is None or px <= 0:
            return
        t = msg.get("time")
        ts = pd.Timestamp(t).tz_convert(NY) if t else self.clock()
        self.add(symbol, ts, px, msg.get("volume"))

    def add(self, symbol: str, ts: pd.Timestamp, px: float, cum_volume: Optional[float] = None) -> None:
        if not (OPEN <= ts.time() < CLOSE):
            return
        m = ts.floor("min")
        with self._lock:
            bars = self._bars.setdefault(symbol, {})
            dv = None
            if cum_volume is not None:
                prev = self._cum.get(symbol)
                dv = max(float(cum_volume) - prev, 0.0) if prev is not None and cum_volume >= prev else None
                self._cum[symbol] = float(cum_volume)
            b = bars.get(m)
            if b is None:
                bars[m] = [px, px, px, px, dv]
            else:
                b[1], b[2], b[3] = max(b[1], px), min(b[2], px), px
                if dv is not None:
                    b[4] = (b[4] or 0.0) + dv

    def frame(self, symbol: str, day: _dt.date) -> pd.DataFrame:
        with self._lock:
            items = sorted((k, list(v)) for k, v in (self._bars.get(symbol) or {}).items() if k.date() == day)
        if not items:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        return pd.DataFrame([{"ts": k, "open": v[0], "high": v[1], "low": v[2], "close": v[3], "volume": v[4]}
                             for k, v in items])


# ── the vendors' bars (through the request gate, cached a minute) ─────────────

def _rth(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    t = df["ts"].dt.time
    return df[(t >= OPEN) & (t < CLOSE)].reset_index(drop=True)


def _yf_minutes(symbol: str, day: _dt.date) -> pd.DataFrame:
    import yfinance as yf
    from api.marketdata import symbols as SYM
    h = yf.Ticker(SYM.to_yfinance(symbol)).history(start=day.isoformat(),
                                                   end=(day + _dt.timedelta(days=1)).isoformat(),
                                                   interval="1m", prepost=False, auto_adjust=False)
    if h is None or h.empty:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    idx = pd.DatetimeIndex(h.index)
    idx = idx.tz_localize(NY) if idx.tz is None else idx.tz_convert(NY)
    df = pd.DataFrame({"ts": idx, "open": h["Open"].values, "high": h["High"].values, "low": h["Low"].values,
                       "close": h["Close"].values, "volume": h["Volume"].values})
    df = df[df["ts"].dt.date == day]
    return _rth(df)


def _polygon_minutes(symbol: str, day: _dt.date) -> pd.DataFrame:
    from api.services.market import _polygon_aggs
    df = _polygon_aggs(symbol, day, day, "minute")
    if df is None or df.empty:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    return _rth(df[["ts", "open", "high", "low", "close", "volume"]].copy())


_REFUSED: dict[str, _dt.date] = {}          # vendor -> the day it refused (403) same-day minutes


def vendor_minutes(symbol: str, day: _dt.date) -> tuple[pd.DataFrame, str, list[str]]:
    """(bars, vendor, notes). yfinance first (it serves the session's minutes, indices included); for a stock or
    ETF Polygon's minute aggregates next — unless Polygon refused them earlier today (its plan here does not
    cover the current session), which is remembered for the day instead of asked again."""
    from api.marketdata import symbols as SYM
    from api.marketdata.cache import cached
    from api.redact import redact
    notes: list[str] = []
    order = ["yfinance"] if SYM.is_index(symbol) else ["yfinance", "polygon"]
    for v in order:
        if _REFUSED.get(v) == day:
            notes.append(f"{v}: refused this session's minutes earlier today")
            continue
        try:
            fn = _yf_minutes if v == "yfinance" else _polygon_minutes
            df = cached(("intraday", v, symbol, day), VENDOR_TTL, lambda fn=fn: fn(symbol, day))
            if df is not None and not df.empty:
                return df, v, notes
            notes.append(f"{v}: no minutes for {day}")
        except Exception as exc:  # noqa: BLE001 — the next vendor, then the hub's own minutes
            if "403" in str(exc):
                _REFUSED[v] = day
            notes.append(redact(f"{v}: {type(exc).__name__}: {str(exc).split('?')[0][:120]}"))
    return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"]), "", notes


def prev_close(symbol: str, day: _dt.date, hub=None) -> Optional[float]:
    """The previous session's close: the hub's streamed prev_close (today's session only), else the stored daily
    bars, else yfinance's daily history."""
    from api.services.gex_recorder import previous_trading_day
    prev = previous_trading_day(day)
    if hub is not None and day == pd.Timestamp.now(tz=NY).date():
        q = getattr(hub, "quotes", {}).get(symbol)
        v = q.values.get("prev_close") if q is not None else None
        if v:
            return float(v)
    try:
        from api.services.db import require_db
        from db.client import get_price_bars
        df = get_price_bars(require_db(), symbol, prev, prev)
        if df is not None and not df.empty:
            return float(df["close"].iloc[-1])
    except Exception:
        pass
    try:
        import yfinance as yf
        from api.marketdata import symbols as SYM
        from api.marketdata.cache import cached

        def daily():
            return yf.Ticker(SYM.to_yfinance(symbol)).history(start=(prev - _dt.timedelta(days=5)).isoformat(),
                                                             end=day.isoformat(), interval="1d", auto_adjust=False)
        h = cached(("intraday-prev", symbol, day), 3600.0, daily)
        if h is not None and not h.empty:
            return float(h["Close"].iloc[-1])
    except Exception:
        pass
    return None


def intraday(symbol: str, minutes: int = 390, interval: int = 1, hub=None, agg: Optional[MinuteAggregator] = None,
             now: Optional[pd.Timestamp] = None) -> dict:
    from api.marketdata import symbols as SYM
    from api.services.market import _ohlcv
    sym = SYM.normalize(symbol)
    if SYM.is_option(sym):
        raise ValueError("an option has no intraday bars here")
    if interval not in (1, 2, 5, 10, 15, 30):
        raise ValueError("interval must be 1, 2, 5, 10, 15 or 30 minutes")
    now = now or pd.Timestamp.now(tz=NY)
    day = session_day(now)
    if agg is not None:
        agg.want(sym)
    vend, vendor, notes = vendor_minutes(sym, day)
    vendor_last = vend["ts"].max() if not vend.empty else None
    live = agg.frame(sym, day) if agg is not None else pd.DataFrame()
    hub_n = 0
    if live is not None and not live.empty:
        if vendor_last is not None:
            live = live[live["ts"] > vendor_last]
        hub_n = len(live)
    df = pd.concat([x for x in (vend, live) if x is not None and not x.empty], ignore_index=True) \
        if (not vend.empty or hub_n) else vend
    if interval > 1 and not df.empty:
        r = df.set_index("ts").resample(f"{interval}min", label="left", closed="left")
        df = pd.DataFrame({"open": r["open"].first(), "high": r["high"].max(), "low": r["low"].min(),
                           "close": r["close"].last(), "volume": r["volume"].sum(min_count=1)}).dropna(
            subset=["close"]).reset_index()
    if not df.empty and minutes:
        df = df[df["ts"] >= df["ts"].max() - pd.Timedelta(minutes=int(minutes) - 1)].reset_index(drop=True)
    out = _ohlcv(sym, "1m", "+".join(x for x in (vendor, "hub" if hub_n else "")
                                                                        if x) or "none", df, "ts")
    out["interval"] = f"{interval}m"
    end = min(now, pd.Timestamp(_dt.datetime.combine(day, CLOSE)).tz_localize(NY)) if day == now.date() else \
        pd.Timestamp(_dt.datetime.combine(day, CLOSE)).tz_localize(NY)

    def lag(last) -> Optional[int]:
        if last is None or pd.isna(last):
            return None
        return max(int((end - (pd.Timestamp(last) + pd.Timedelta(minutes=1))).total_seconds() // 60), 0)

    last_all = df["ts"].max() if not df.empty else None
    out.update(prev_close=prev_close(sym, day, hub), session=day, delayed_minutes=lag(last_all),
               vendor=vendor or None, vendor_delayed_minutes=lag(vendor_last), hub_minutes=hub_n,
               live=bool(hub_n), notes=notes)
    from api.serialize import to_jsonable
    return to_jsonable(out)
