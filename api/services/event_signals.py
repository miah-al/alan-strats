"""
api/services/event_signals.py — the event desk's daily signals: crude, USO, OVX, VIX, VIX3M, BTC, IBIT.

For each instrument: the last price, the day's change, the level's z-score against the 20- and 60-session
mean / sd, the day's move as a z-score against the last 20 daily changes ("a 2σ move"), the up-close streak,
the distance from the 20-session mean and the last 60 closes.

Data (daily, one row per completed session):
  USO, IBIT   the service's stored daily bars (mkt.PriceBar, topped up on demand as /api/market/bars does);
              yfinance when nothing is stored
  VIX         the stored CBOE closes (mkt.VixBar); yfinance when behind
  CL, OVX, VIX3M, BTC   yfinance only (``CL=F`` — the front WTI future, ``^OVX``, ``^VIX3M``, ``BTC-USD``):
              nothing in the service's tables carries them. One batched ``yf.download`` for all of them,
              through the request gate, cached for 20 minutes.
Today's partial daily row from yfinance (during the session; always for BTC, which never closes) is not a
close: it stands in as the "last" mark when the hub has none.

Live marks: the market-data hub for the symbols it can stream — USO, VIX, IBIT. Crude, OVX, VIX3M and BTC
are daily-only (no hub provider carries a future, the OVX index or spot bitcoin): their "last" is the
latest daily close or yfinance's partial day.

Conventions: ``change_pct`` is the move of ``last`` against the close before it (a live mark against the last
close; a close against the prior close); ``z20`` / ``z60`` are (last − mean) / sd over the N closes preceding
the point scored (sd with one degree of freedom; null with fewer than N closes or a zero sd); ``move_z20``
is ``change_pct`` against the mean / sd of the 20 daily changes before it; ``higher_streak`` counts closes
above the previous close at the end of the daily series (a live mark never extends it).
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
import threading
import time
from typing import Callable, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("alan_trader.api.event_signals")

NY = "America/New_York"

SYMBOLS = (
    ("CL", "CL=F", "Crude (WTI front)"),
    ("USO", "USO", "USO (crude ETF)"),
    ("OVX", "^OVX", "Crude vol (OVX)"),
    ("VIX", "^VIX", "VIX"),
    ("VIX3M", "^VIX3M", "VIX 3-month"),
    ("BTC", "BTC-USD", "Bitcoin"),
    ("IBIT", "IBIT", "IBIT (bitcoin ETF)"),
)
KEYS = tuple(k for k, _, _ in SYMBOLS)
YF = {k: y for k, y, _ in SYMBOLS}
NAMES = {k: n for k, _, n in SYMBOLS}
LIVE = ("USO", "VIX", "IBIT")            # the hub can stream / poll these; the rest are daily-only
STORED_BARS = ("USO", "IBIT")            # mkt.PriceBar
STORED_VIX = ("VIX",)                    # mkt.VixBar
ALWAYS_OPEN = ("BTC",)                   # 24/7: the latest daily row is always the partial day
HISTORY = 60
FETCH_DAYS = 120                         # sessions fetched: 60 closes of history plus the baselines before them
MIN_STORED = 70                          # a stored series shorter than this is topped up from yfinance instead
TTL_S = 1200.0


# ── the math (pure) ───────────────────────────────────────────────────────────

def _f(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _z(point: Optional[float], window: np.ndarray, n: int) -> Optional[float]:
    if point is None or len(window) < n:
        return None
    w = window[-n:].astype(float)
    sd = float(np.std(w, ddof=1))
    if not sd or not math.isfinite(sd):
        return None
    return round((point - float(np.mean(w))) / sd, 2)


def _mean(window: np.ndarray, n: int) -> Optional[float]:
    if len(window) < n:
        return None
    return round(float(np.mean(window[-n:].astype(float))), 4)


def _sd(window: np.ndarray, n: int) -> Optional[float]:
    if len(window) < n:
        return None
    sd = float(np.std(window[-n:].astype(float), ddof=1))
    return round(sd, 4) if math.isfinite(sd) else None


def clean_closes(closes) -> pd.Series:
    """A float series indexed by date, ascending, without gaps of NaN or duplicate days."""
    if closes is None or len(closes) == 0:
        return pd.Series(dtype=float)
    s = pd.Series(closes).copy()
    s.index = pd.to_datetime(s.index).date if not isinstance(s.index[0], _dt.date) else s.index
    s = pd.to_numeric(s, errors="coerce").dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.astype(float)


def higher_streak(closes: pd.Series) -> int:
    c = clean_closes(closes).values
    n = 0
    for i in range(len(c) - 1, 0, -1):
        if c[i] > c[i - 1]:
            n += 1
        else:
            break
    return n


def compute(key: str, closes, last: Optional[float] = None, last_asof: Optional[str] = None,
            mark_source: Optional[str] = None, source: Optional[str] = None) -> dict:
    """One instrument's signal row. ``closes``: completed daily closes (date -> close). ``last``: a live mark
    (or the day's partial close) scored against the last close; None scores the last close itself."""
    s = clean_closes(closes)
    c = s.values
    dates = list(s.index)
    live = last is not None and _f(last) is not None
    out = {"symbol": key, "name": NAMES.get(key, key), "last": None, "close": None, "close_date": None,
           "prev_close": None, "change_pct": None, "move_z20": None, "z20": None, "z60": None, "mean20": None,
           "mean60": None, "sd20_pct": None, "dist_mean20_pct": None, "higher_streak": 0,
           "source": source or ("live" if live else "daily"), "mark_source": mark_source,
           "as_of": last_asof if live else (dates[-1].isoformat() if dates else None),
           "sessions": int(len(c)), "history": [[d.isoformat(), round(float(v), 4)] for d, v in
                                                 zip(dates[-HISTORY:], c[-HISTORY:])]}
    if not len(c):
        return out
    close = float(c[-1])
    out["close"], out["close_date"] = round(close, 4), dates[-1].isoformat()
    if live:
        point, ref, level_win, chg_scored_idx = float(last), close, c, None
    else:
        point, ref = close, (float(c[-2]) if len(c) > 1 else None)
        level_win = c[:-1]
    out["last"] = round(point, 4)
    out["prev_close"] = round(ref, 4) if ref is not None else None
    if ref:
        out["change_pct"] = round((point / ref - 1.0) * 100.0, 3)
    out["z20"], out["z60"] = _z(point, level_win, 20), _z(point, level_win, 60)
    out["mean20"], out["mean60"] = _mean(level_win, 20), _mean(level_win, 60)
    if out["mean20"]:
        out["dist_mean20_pct"] = round((point / out["mean20"] - 1.0) * 100.0, 3)
    chg = (pd.Series(c).pct_change() * 100.0).dropna().values          # daily changes of the closes
    base = chg if live else chg[:-1]                                    # the changes before the one scored
    out["move_z20"] = _z(out["change_pct"], base, 20)
    out["sd20_pct"] = _sd(base, 20)
    out["higher_streak"] = higher_streak(s)
    return out


def recent_spike(closes, threshold_pct: float = 2.0, z: float = 2.0, lookback: int = 5) -> Optional[dict]:
    """The most recent session in the last ``lookback`` whose close was up ≥ ``threshold_pct`` % or whose move
    was ≥ ``z`` sd of the 20 changes before it, with what the closes did since: ``sessions_ago``,
    ``down_close_since`` (a close below its previous close after the spike), ``first_down_close`` (its date)
    and ``closes_since`` (dates + closes after the spike day)."""
    s = clean_closes(closes)
    c, dates = s.values, list(s.index)
    if len(c) < 3:
        return None
    chg = (pd.Series(c).pct_change() * 100.0).values                      # chg[i] = close i vs i-1
    n = len(c)
    for i in range(n - 1, max(n - 1 - lookback, 0), -1):
        ch = chg[i]
        if not math.isfinite(ch):
            continue
        base = chg[max(1, i - 20):i]
        mz = _z(float(ch), base[np.isfinite(base)], 20) if i > 1 else None
        if ch >= threshold_pct or (mz is not None and mz >= z):
            after = [(dates[j], float(c[j])) for j in range(i + 1, n)]
            downs = [dates[j] for j in range(i + 1, n) if c[j] < c[j - 1]]
            return {"date": dates[i].isoformat(), "close": round(float(c[i]), 4),
                    "prev_close": round(float(c[i - 1]), 4), "change_pct": round(float(ch), 3), "move_z20": mz,
                    "sessions_ago": n - 1 - i, "down_close_since": bool(downs),
                    "first_down_close": downs[0].isoformat() if downs else None,
                    "closes_since": [[d.isoformat(), round(v, 4)] for d, v in after]}
    return None


# ── daily closes (the service's tables, then yfinance) ───────────────────────

class DailyCloses:
    """Completed daily closes per key, cached for ``ttl_s``. ``get(key)`` -> {"closes": Series(date -> close),
    "source": "db" | "yfinance", "partial": today's not-yet-closed price or None, "partial_asof", "error"}."""

    def __init__(self, ttl_s: float = TTL_S, clock: Optional[Callable[[], pd.Timestamp]] = None):
        self.ttl_s = ttl_s
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get(self, key: str, force: bool = False) -> dict:
        return self.get_many([key], force)[key]

    def get_many(self, keys, force: bool = False) -> dict[str, dict]:
        keys = [k for k in keys if k in YF]
        now_m = time.monotonic()
        with self._lock:
            need = [k for k in keys if force or k not in self._cache
                    or now_m - self._cache[k]["fetched"] > self.ttl_s]
        if need:
            got = self._fetch(need)
            with self._lock:
                for k in need:
                    entry = got.get(k)
                    if entry is None:                                 # keep the stale copy, note the failure
                        old = self._cache.get(k)
                        entry = dict(old, error=old.get("error") or "refresh failed") if old else \
                            {"closes": pd.Series(dtype=float), "source": "none", "partial": None,
                             "partial_asof": None, "error": "no data"}
                    entry["fetched"] = now_m
                    self._cache[k] = entry
        with self._lock:
            return {k: dict(self._cache[k]) for k in keys}

    # ── fetching ─────────────────────────────────────────────────────────────
    def _fetch(self, keys: list[str]) -> dict[str, dict]:
        now = self.clock()
        today = now.date()
        out: dict[str, dict] = {}
        rest = []
        for k in keys:
            entry = None
            if k in STORED_BARS or k in STORED_VIX:
                try:
                    entry = self._stored(k, today)
                except Exception as exc:  # noqa: BLE001 — yfinance instead
                    logger.info("stored closes for %s unavailable: %s", k, exc)
            if entry is not None:
                out[k] = entry
            else:
                rest.append(k)
        if rest:
            try:
                frames = self._yfinance(rest)
            except Exception as exc:  # noqa: BLE001
                logger.warning("yfinance daily closes failed: %s", exc)
                frames = {}
            for k in rest:
                df = frames.get(YF[k])
                if df is None or df.empty:
                    out[k] = {"closes": pd.Series(dtype=float), "source": "yfinance", "partial": None,
                              "partial_asof": None, "error": f"yfinance returned nothing for {YF[k]}"}
                    continue
                out[k] = self._split_partial(k, df, now, "yfinance")
        return out

    def _split_partial(self, key: str, df: pd.DataFrame, now: pd.Timestamp, source: str) -> dict:
        s = pd.Series(pd.to_numeric(df["close"], errors="coerce").values,
                      index=pd.to_datetime(df["date"]).dt.date)
        s = clean_closes(s)
        partial, asof = None, None
        if len(s):
            last_day = s.index[-1]
            session_open = now.time() < _dt.time(16, 0)
            if last_day >= now.date() and (key in ALWAYS_OPEN or session_open):
                partial, asof = float(s.iloc[-1]), f"{last_day.isoformat()} (partial)"
                s = s.iloc[:-1]
        return {"closes": s, "source": source, "partial": partial, "partial_asof": asof, "error": None}

    def _stored(self, key: str, today: _dt.date) -> Optional[dict]:
        """The service's own daily closes when they are long enough and current (else None)."""
        from api.services.db import require_db
        from api.services.gex_recorder import previous_trading_day
        from db.client import get_price_bars, get_vix_bars
        eng = require_db()
        start = today - _dt.timedelta(days=int(FETCH_DAYS * 1.6))
        prev = previous_trading_day(today)
        if key in STORED_VIX:
            v = get_vix_bars(eng, start, today)
            if v is None or len(v) < MIN_STORED:
                return None
            s = pd.Series(pd.to_numeric(v["close"], errors="coerce").values, index=pd.to_datetime(v.index).date)
        else:
            try:
                from api.services.bars_topup import top_up
                top_up(key, prev)
            except Exception as exc:  # noqa: BLE001
                logger.info("%s daily bars not topped up: %s", key, exc)
            df = get_price_bars(eng, key, start, today)
            if df is None or df.empty or len(df) < MIN_STORED:
                return None
            s = pd.Series(pd.to_numeric(df["close"], errors="coerce").values, index=pd.to_datetime(df["date"]).dt.date)
        s = clean_closes(s)
        if not len(s) or s.index[-1] < prev:
            return None                                                  # behind: yfinance has the missing days
        return {"closes": s, "source": "db", "partial": None, "partial_asof": None, "error": None}

    @staticmethod
    def _yfinance(keys: list[str]) -> dict[str, pd.DataFrame]:
        from api.marketdata.limits import patience
        from data.stock_data import yf_batch_daily
        with patience(60.0):                                             # the request gate, waiting out a backoff
            return yf_batch_daily([YF[k] for k in keys], n_days=FETCH_DAYS)


# ── live marks from the hub ───────────────────────────────────────────────────

class LiveMarks:
    def __init__(self, hub):
        self.hub = hub

    def get(self, keys) -> dict[str, tuple[float, Optional[str], str]]:
        """{key: (price, quote time, "hub:<provider>")} for the streamable keys the hub can price now."""
        want = [k for k in keys if k in LIVE]
        if self.hub is None or not getattr(self.hub, "providers", None) or not want:
            return {}
        try:
            quotes = {q.get("symbol"): q for q in self.hub.snapshot(want, wait=2.0)}
        except Exception as exc:  # noqa: BLE001
            logger.info("hub marks unavailable: %s", exc)
            return {}
        out = {}
        for k in want:
            q = quotes.get(k) or {}
            order = ("last", "mid") if k == "VIX" else ("mid", "last")
            px = next((q[f] for f in order if q.get(f) is not None), None)
            if px is not None:
                out[k] = (float(px), q.get("time"), f"hub:{q.get('source') or '?'}")
        return out


# ── the signals ───────────────────────────────────────────────────────────────

class Signals:
    def __init__(self, daily: Optional[DailyCloses] = None, live: Optional[LiveMarks] = None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None, live_hub=None):
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self.daily = daily or DailyCloses(clock=self.clock)
        self.live = live or LiveMarks(live_hub)

    def closes(self, key: str, force: bool = False) -> pd.Series:
        return self.daily.get(key, force)["closes"]

    def snapshot(self, keys=KEYS, force: bool = False, live: bool = True) -> dict[str, dict]:
        """{key: signal row} for ``keys`` (the order kept), each with ``warnings``."""
        keys = list(keys)
        daily = self.daily.get_many(keys, force)
        marks = self.live.get(keys) if live else {}
        out = {}
        for k in keys:
            d = daily[k]
            warnings = [d["error"]] if d.get("error") else []
            if k in marks:
                px, asof, src = marks[k]
                row = compute(k, d["closes"], px, asof, src, "live")
            elif d.get("partial") is not None:
                row = compute(k, d["closes"], d["partial"], d["partial_asof"], f"{d['source']} partial day", "daily")
            else:
                row = compute(k, d["closes"], None, None, d["source"], "daily")
            if row["sessions"] < 61:
                warnings.append(f"{row['sessions']} sessions of history (60 wanted)")
            row["warnings"] = warnings
            out[k] = row
        return out
