"""
api/services/volstats.py — a volatility dashboard row per symbol (``/api/market/vol-stats``).

Per symbol, from three expiries of its option chain (the two bracketing 30 days, the one nearest 90)
merged across providers exactly as ``/api/options/{u}/chain`` does — the broker's stream, else
yfinance's quotes and Polygon's greeks — plus stored daily bars and the IV history:

  iv30, iv90         constant-maturity ATM IV (total variance interpolated between expiries), vol points
  skew_25d           30-day 25Δ put IV − 25Δ call IV (vol points)
  term_slope         iv90 − iv30
  em_30d_abs / _pct  the 30-day ATM straddle (mid), in dollars and % of spot
  atm_spread_pct     the ATM call's and put's bid-ask as % of mid (the 30-day expiry), averaged
  oi_total           open interest of the sampled contracts (those three expiries, the strikes around spot)
  hv20, hv60         close-to-close realised vol, annualised, vol points (stored bars, else yfinance)
  iv_hv              iv30 − hv20
  iv_rank, iv_pct    1-year IV rank and percentile of iv30 against the stored IV history (the service's
                     own daily record in app.IvHistory plus the ATM ~30-day IV mkt.OptionSnapshot holds);
                     null with a reason under 60 daily observations
  beta_spy           1-year daily beta to SPY from stored bars (yfinance closes when none are stored)
  next_earnings      yfinance's calendar (cached a day)

Each symbol is computed on a small worker pool and cached 10 minutes (60 while the market is closed);
a request waits up to 20 s and answers ``status: pending`` for the symbols still computing — they are
ready for the next request. Every upstream call goes through the request gate (the workers queue for
a slot rather than fail), and streamed contracts are released as soon as a symbol is done.
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

import numpy as np
import pandas as pd

from api.marketdata import symbols as SYM
from api.serialize import table_from_rows, to_jsonable

logger = logging.getLogger("alan_trader.api.volstats")

TTL_OPEN_S = 600.0
TTL_CLOSED_S = 3600.0
WAIT_S = 20.0
MAX_SYMBOLS = 40
MIN_HISTORY = 60
WORKERS = 3
STRIKES_30 = 30          # strikes either side of spot at the 30-day expiries (reaches 25Δ on a $1 grid)
STRIKES_90 = 8

FIELDS = ["symbol", "status", "spot", "iv30", "iv_rank", "iv_pct", "iv_history_days", "hv20", "hv60", "iv_hv",
          "skew_25d", "iv90", "term_slope", "em_30d_abs", "em_30d_pct", "next_earnings", "beta_spy",
          "atm_spread_pct", "oi_total", "asof", "source", "notes"]
_HEADERS = {"symbol": "Symbol", "status": "Status", "spot": "Spot", "iv30": "IV30", "iv_rank": "IV Rank",
            "iv_pct": "IV %ile", "iv_history_days": "IV Hist Days", "hv20": "HV20", "hv60": "HV60", "iv_hv": "IV−HV",
            "skew_25d": "25Δ Skew", "iv90": "IV90", "term_slope": "Term Slope", "em_30d_abs": "EM 30d $",
            "em_30d_pct": "EM 30d %", "next_earnings": "Next Earnings", "beta_spy": "Beta (SPY)",
            "atm_spread_pct": "ATM Spread %", "oi_total": "OI (sampled)", "asof": "As Of", "source": "Source",
            "notes": "Notes"}
_FORMATS = {"spot": "price", "iv30": "pct", "iv90": "pct", "hv20": "pct", "hv60": "pct", "iv_hv": "pct",
            "skew_25d": "pct", "term_slope": "pct", "em_30d_abs": "price", "em_30d_pct": "pct", "iv_rank": "pct",
            "iv_pct": "pct", "atm_spread_pct": "pct", "oi_total": "int", "iv_history_days": "int"}
_TYPES = {"symbol": "string", "status": "string", "next_earnings": "date", "asof": "datetime", "source": "string",
          "notes": "string", "oi_total": "integer", "iv_history_days": "integer"}


def _market_open() -> bool:
    now = pd.Timestamp.now(tz="America/New_York")
    return now.weekday() < 5 and _dt.time(9, 30) <= now.time() < _dt.time(16, 0)


# ── the maths (pure, tested on their own) ─────────────────────────────────────

def _otm_smile(rows: list[dict], spot: float) -> tuple[np.ndarray, np.ndarray]:
    pts: dict[float, list] = {}
    for r in rows:
        k = float(r["strike"])
        for side, ok in (("put", k <= spot), ("call", k >= spot)):
            iv = (r.get(side) or {}).get("iv")
            if ok and iv is not None and 0 < float(iv) < 5:
                pts.setdefault(k, []).append(float(iv))
    ks = np.array(sorted(pts))
    return ks, np.array([sum(pts[k]) / len(pts[k]) for k in ks])


def atm_iv(rows: list[dict], spot: float) -> Optional[float]:
    ks, ivs = _otm_smile(rows, spot)
    if len(ks) < 2 or not (ks[0] <= spot <= ks[-1]):
        return None
    return float(np.interp(spot, ks, ivs))


def delta_iv(rows: list[dict], side: str, target: float) -> Optional[float]:
    """IV at ``target`` delta on one side (puts negative), interpolated in delta."""
    pts = sorted((float((r.get(side) or {}).get("delta")), float((r.get(side) or {}).get("iv")))
                 for r in rows if (r.get(side) or {}).get("delta") is not None and (r.get(side) or {}).get("iv"))
    if len(pts) < 2:
        return None
    ds, ivs = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
    if not (ds[0] <= target <= ds[-1]):
        return None
    return float(np.interp(target, ds, ivs))


def straddle(rows: list[dict], spot: float) -> Optional[tuple[float, float]]:
    """(ATM straddle mid, its average bid-ask as % of mid) at the strike nearest spot."""
    best = min(rows, key=lambda r: abs(float(r["strike"]) - spot), default=None)
    if best is None:
        return None
    mids, spreads = [], []
    for side in ("call", "put"):
        q = best.get(side) or {}
        b, a = q.get("bid"), q.get("ask")
        if b is None or a is None or a <= 0 or a < b:
            return None
        m = (b + a) / 2.0
        mids.append(m)
        spreads.append((a - b) / m * 100.0 if m > 0 else None)
    sp = [x for x in spreads if x is not None]
    return sum(mids), (sum(sp) / len(sp) if sp else None)


def interp_variance(points: list[tuple[int, float]], dte: int) -> Optional[float]:
    """A vol at ``dte`` days from (dte, vol) points: total variance interpolated linearly in time,
    no extrapolation beyond the points (a single point within 10 days stands in for it)."""
    pts = sorted((d, v) for d, v in points if v is not None and d > 0)
    if not pts:
        return None
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= dte <= d1:
            w0, w1 = v0 * v0 * d0, v1 * v1 * d1
            w = w0 + (w1 - w0) * (dte - d0) / (d1 - d0) if d1 != d0 else w0
            return math.sqrt(max(w, 0.0) / dte)
    nearest = min(pts, key=lambda p: abs(p[0] - dte))
    return nearest[1] if abs(nearest[0] - dte) <= 10 else None


def interp_linear(points: list[tuple[int, float]], dte: int, reach: int = 10) -> Optional[float]:
    pts = sorted((d, v) for d, v in points if v is not None)
    if not pts:
        return None
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= dte <= d1:
            return v0 + (v1 - v0) * (dte - d0) / (d1 - d0) if d1 != d0 else v0
    nearest = min(pts, key=lambda p: abs(p[0] - dte))
    return nearest[1] if abs(nearest[0] - dte) <= reach else None


def rank_and_percentile(history: pd.Series, current: float) -> tuple[Optional[float], Optional[float], int, Optional[str]]:
    h = pd.to_numeric(history, errors="coerce").dropna()
    n = int(len(h))
    if n < MIN_HISTORY:
        return None, None, n, f"{n} days of IV history (needs {MIN_HISTORY})"
    lo, hi = float(h.min()), float(h.max())
    rank = 100.0 * (current - lo) / (hi - lo) if hi > lo else 50.0
    pct = 100.0 * float((h < current).sum()) / n
    return round(min(max(rank, 0.0), 100.0), 1), round(pct, 1), n, None


def realised_vol(closes: pd.Series, window: int) -> Optional[float]:
    c = pd.to_numeric(closes, errors="coerce").dropna()
    if len(c) < window + 1:
        return None
    r = np.log(c / c.shift(1)).dropna().iloc[-window:]
    v = float(r.std(ddof=1) * math.sqrt(252))
    return v if math.isfinite(v) and v > 0 else None


def pick_expiries(exps: list[tuple[_dt.date, int]]) -> dict[str, Optional[tuple[_dt.date, int]]]:
    """The expiries bracketing 30 days (at least 7 out) and the one nearest 90."""
    usable = [(e, d) for e, d in exps if d >= 7]
    below = [x for x in usable if x[1] <= 30]
    above = [x for x in usable if x[1] > 30]
    return {"lo30": below[-1] if below else None, "hi30": above[0] if above else None,
            "e90": min(usable, key=lambda x: abs(x[1] - 90)) if usable else None}


# ── IV history ────────────────────────────────────────────────────────────────

_HIST_LOCK = threading.Lock()
_HIST_CACHE: dict[str, tuple[_dt.date, pd.Series]] = {}


def _snapshot_history(symbol: str) -> pd.Series:
    """Daily ATM ~30-day IV (percent) from the stored option snapshots (mkt.OptionSnapshot), last year."""
    from sqlalchemy import text
    from api.services.db import engine
    since = _dt.date.today() - _dt.timedelta(days=366)
    sql = text("""
        SELECT o.SnapshotDate, DATEDIFF(day, o.SnapshotDate, o.ExpirationDate) AS dte, o.Strike, o.ContractType,
               o.ImpliedVol, pb.[Close]
        FROM mkt.OptionSnapshot o
        JOIN mkt.Ticker t ON t.TickerId = o.TickerId
        JOIN mkt.PriceBar pb ON pb.TickerId = o.TickerId AND pb.BarDate = o.SnapshotDate
        WHERE t.Symbol = :s AND o.SnapshotDate >= :d AND o.ImpliedVol > 0
          AND DATEDIFF(day, o.SnapshotDate, o.ExpirationDate) BETWEEN 10 AND 60
          AND o.Strike BETWEEN pb.[Close] * 0.97 AND pb.[Close] * 1.03""")
    try:
        with engine().connect() as c:
            df = pd.DataFrame(c.execute(sql, {"s": symbol, "d": since}).fetchall(),
                              columns=["day", "dte", "strike", "type", "iv", "close"])
    except Exception as exc:
        logger.info("IV history from snapshots for %s unavailable: %s", symbol, exc)
        return pd.Series(dtype=float)
    if df.empty:
        return pd.Series(dtype=float)
    out = {}
    for day, g in df.groupby("day"):
        spot = float(g["close"].iloc[0])
        pts = []
        for dte, e in g.groupby("dte"):
            rows = [{"strike": float(k), ("call" if str(t).upper().startswith("C") else "put"): {"iv": float(v)}}
                    for k, t, v in zip(e["strike"], e["type"], e["iv"])]
            a = atm_iv(rows, spot)
            if a is not None:
                pts.append((int(dte), a))
        v = interp_variance(pts, 30)
        if v is not None:
            out[pd.Timestamp(day)] = v * 100.0
    return pd.Series(out).sort_index()


def _service_history(symbol: str) -> pd.Series:
    from sqlalchemy import text
    from api.services import appdb
    from api.services.db import engine
    try:
        if not appdb.exists("IvHistory"):
            return pd.Series(dtype=float)
        with engine().connect() as c:
            rows = c.execute(text("SELECT TradeDate, Iv30 FROM app.IvHistory WHERE Symbol = :s AND TradeDate >= :d"),
                             {"s": symbol, "d": _dt.date.today() - _dt.timedelta(days=366)}).fetchall()
    except Exception:
        return pd.Series(dtype=float)
    return pd.Series({pd.Timestamp(r[0]): float(r[1]) for r in rows}).sort_index()


def iv_history(symbol: str) -> pd.Series:
    """One year of daily iv30 (percent): the service's record over the stored snapshots' where both exist."""
    today = _dt.date.today()
    with _HIST_LOCK:
        hit = _HIST_CACHE.get(symbol)
    if hit is not None and hit[0] == today:
        snap = hit[1]
    else:
        snap = _snapshot_history(symbol)
        with _HIST_LOCK:
            _HIST_CACHE[symbol] = (today, snap)
    svc = _service_history(symbol)
    s = pd.concat([snap[~snap.index.isin(svc.index)], svc]).sort_index() if not svc.empty else snap
    return s[s.index >= pd.Timestamp(today - _dt.timedelta(days=365))]


def record_iv(symbol: str, iv30_pct: float) -> None:
    """Today's iv30 into app.IvHistory (a trading day, once the session has begun; the last value wins)."""
    from sqlalchemy import text
    from api.services import appdb
    from api.services.db import require_db
    now = pd.Timestamp.now(tz="America/New_York")
    if now.weekday() >= 5 or now.time() < _dt.time(9, 45):
        return
    try:
        appdb.ensure("IvHistory")
        with require_db().begin() as c:
            n = c.execute(text("UPDATE app.IvHistory SET Iv30 = :v, UpdatedAt = SYSUTCDATETIME() "
                               "WHERE Symbol = :s AND TradeDate = :d"),
                          {"v": float(iv30_pct), "s": symbol, "d": now.date()}).rowcount
            if n == 0:
                c.execute(text("INSERT INTO app.IvHistory (Symbol, TradeDate, Iv30) VALUES (:s, :d, :v)"),
                          {"v": float(iv30_pct), "s": symbol, "d": now.date()})
    except Exception as exc:
        logger.info("iv30 for %s not recorded: %s", symbol, exc)


# ── prices ────────────────────────────────────────────────────────────────────

_PX_CACHE: dict[str, tuple[_dt.date, pd.Series, str]] = {}


def closes(symbol: str) -> tuple[pd.Series, str]:
    """~15 months of daily closes: stored bars, else yfinance (one download, cached a day)."""
    from api.services.risk import daily_closes
    today = _dt.date.today()
    hit = _PX_CACHE.get(symbol)
    if hit is not None and hit[0] == today:
        return hit[1], hit[2]
    s, src = daily_closes(symbol, 460), "db"
    if len(s) < 60 or (today - s.index[-1].date()).days > 7:
        try:
            from data.stock_data import yf_daily_bars
            df = yf_daily_bars(SYM.to_yfinance(symbol), n_days=320)
            if df is not None and not df.empty:
                s = pd.Series(pd.to_numeric(df["close"], errors="coerce").values, index=pd.to_datetime(df["date"])).dropna()
                src = "yfinance"
        except Exception as exc:
            logger.info("closes for %s unavailable: %s", symbol, exc)
    _PX_CACHE[symbol] = (today, s, src)
    return s, src


def beta_to_spy(sym_closes: pd.Series, spy_closes: pd.Series) -> Optional[float]:
    cutoff = pd.Timestamp(_dt.date.today() - _dt.timedelta(days=365))
    r = pd.concat([sym_closes, spy_closes], axis=1, join="inner")
    r = r[r.index >= cutoff].pct_change().dropna()
    if len(r) < 120 or r.iloc[:, 1].var() <= 0:
        return None
    return round(float(np.cov(r.iloc[:, 0], r.iloc[:, 1])[0, 1] / r.iloc[:, 1].var()), 3)


# ── one symbol ────────────────────────────────────────────────────────────────

def compute(hub, symbol: str) -> dict:
    from api.marketdata import options as O
    from api.marketdata.limits import patience
    from api.services.earnings import next_earnings
    sym = SYM.normalize(symbol)
    notes: list[str] = []
    row: dict = {"symbol": sym, "status": "ok"}
    with patience(120.0):
        spot = hub.price(sym, wait=5.0)
        row["spot"] = spot
        exps = []
        try:
            e = O.expirations(hub, sym)
            exps = [(_dt.date.fromisoformat(x["expiry"]), int(x["dte"])) for x in e["expirations"]]
        except Exception as exc:  # noqa: BLE001
            notes.append(f"no option expirations: {exc}")
        chosen = pick_expiries(exps) if exps else {}
        chains: dict[_dt.date, tuple[int, list[dict]]] = {}
        used: set[str] = set()
        if spot:
            for key, (n) in (("lo30", STRIKES_30), ("hi30", STRIKES_30), ("e90", STRIKES_90)):
                pick = chosen.get(key)
                if pick is None or pick[0] in chains:
                    continue
                cn: list[str] = []
                rows, srcs = O.merged_chain(hub, sym, pick[0], spot, n, cn, linger=False)
                if rows:
                    chains[pick[0]] = (pick[1], rows)
                    used.update(srcs)
                else:
                    notes.append(f"no chain for {pick[0]}: {'; '.join(cn)[:120]}")
        elif not notes:
            notes.append("no spot price")
        atm_pts = [(d, atm_iv(rows, spot)) for d, rows in chains.values()]
        iv30 = interp_variance(atm_pts, 30)
        iv90 = interp_variance(atm_pts, 90)
        near = [(d, rows) for d, rows in chains.values() if d <= 60]
        put25 = interp_variance([(d, delta_iv(r, "put", -0.25)) for d, r in near], 30)
        call25 = interp_variance([(d, delta_iv(r, "call", 0.25)) for d, r in near], 30)
        strad = [(d, straddle(r, spot)) for d, r in near]
        em = interp_variance([(d, s[0] / math.sqrt(d)) for d, s in strad if s], 30)   # straddle ∝ √T
        spread = interp_linear([(d, s[1]) for d, s in strad if s and s[1] is not None], 30, reach=45)
        oi = sum(float((r.get(side) or {}).get("oi") or 0) for _d, rows in chains.values() for r in rows
                 for side in ("call", "put"))
        pc, pc_src = closes(sym)
        spy_c, _ = closes("SPY") if sym != "SPY" else (pc, pc_src)
        hv20, hv60 = realised_vol(pc, 20), realised_vol(pc, 60)
        row.update({
            "iv30": round(iv30 * 100, 2) if iv30 else None,
            "iv90": round(iv90 * 100, 2) if iv90 else None,
            "term_slope": round((iv90 - iv30) * 100, 2) if (iv30 and iv90) else None,
            "skew_25d": round((put25 - call25) * 100, 2) if (put25 and call25) else None,
            "em_30d_abs": round(em * math.sqrt(30), 2) if em else None,
            "atm_spread_pct": round(spread, 2) if spread is not None else None,
            "oi_total": int(oi) if chains else None,
            "hv20": round(hv20 * 100, 2) if hv20 else None,
            "hv60": round(hv60 * 100, 2) if hv60 else None,
            "beta_spy": 1.0 if sym == "SPY" else beta_to_spy(pc, spy_c),
        })
        row["em_30d_pct"] = round(row["em_30d_abs"] / spot * 100, 2) if (row["em_30d_abs"] and spot) else None
        row["iv_hv"] = round(row["iv30"] - row["hv20"], 2) if (row["iv30"] is not None and row["hv20"] is not None) else None
        if row["iv30"] is not None:
            record_iv(sym, row["iv30"])
            hist = iv_history(sym)
            rank, pct, n, why = rank_and_percentile(hist, row["iv30"])
            row.update(iv_rank=rank, iv_pct=pct, iv_history_days=n)
            if why:
                notes.append(why)
        else:
            row.update(iv_rank=None, iv_pct=None, iv_history_days=None)
            notes.append("no ATM IV around 30 days")
        if row["skew_25d"] is None and chains:
            notes.append("no 25-delta IVs in the sampled strikes")
        if row["em_30d_abs"] is None and chains:
            notes.append("no two-sided ATM quotes for the straddle")
        if row["beta_spy"] is None:
            notes.append("too little price history for beta")
        try:
            row["next_earnings"] = next_earnings(sym)
        except Exception:
            row["next_earnings"] = None
    missing = [k for k in ("iv30", "hv20", "skew_25d", "em_30d_abs") if row.get(k) is None]
    row["status"] = "ok" if not missing else ("partial" if row.get("hv20") is not None or row.get("iv30") is not None
                                              else "error")
    row["source"] = ", ".join(sorted(used)) or None
    row["price_source"] = pc_src
    row["asof"] = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
    row["notes"] = "; ".join(notes)
    return row


# ── the engine: cache, workers, deadline ──────────────────────────────────────

class VolStats:
    def __init__(self, hub, workers: int = WORKERS):
        self.hub = hub
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="volstats")
        self._cache: dict[str, tuple[float, dict]] = {}
        self._flights: dict[str, Future] = {}
        self._lock = threading.Lock()

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _ttl(self) -> float:
        return TTL_OPEN_S if _market_open() else TTL_CLOSED_S

    def _run(self, sym: str) -> dict:
        try:
            r = compute(self.hub, sym)
        except Exception as exc:  # noqa: BLE001
            logger.warning("vol stats for %s failed: %s", sym, exc)
            r = {"symbol": sym, "status": "error", "notes": f"{type(exc).__name__}: {exc}"[:300],
                 "asof": _dt.datetime.now().astimezone().isoformat(timespec="seconds")}
        with self._lock:
            self._cache[sym] = (time.monotonic(), r)
            self._flights.pop(sym, None)
        return r

    def get(self, symbols: list[str], wait: float = WAIT_S) -> dict:
        syms, bad = [], []
        for s in symbols:
            try:
                c = SYM.normalize(s)
            except ValueError:
                bad.append(str(s))
                continue
            if SYM.is_option(c):
                bad.append(str(s))
            elif c not in syms:
                syms.append(c)
        if bad:
            raise ValueError(f"not stock / index symbols: {bad}")
        if not syms:
            raise ValueError("give at least one symbol")
        if len(syms) > MAX_SYMBOLS:
            raise ValueError(f"at most {MAX_SYMBOLS} symbols")
        ttl = self._ttl()
        futures: dict[str, Future] = {}
        ready: dict[str, dict] = {}
        with self._lock:
            for s in syms:
                hit = self._cache.get(s)
                if hit is not None and time.monotonic() - hit[0] < ttl:
                    ready[s] = hit[1]
                    continue
                f = self._flights.get(s)
                if f is None:
                    f = self._flights[s] = self._pool.submit(self._run, s)
                futures[s] = f
        end = time.monotonic() + wait
        for s, f in futures.items():
            try:
                ready[s] = f.result(timeout=max(0.0, end - time.monotonic()))
            except Exception:
                with self._lock:
                    stale = self._cache.get(s)
                ready[s] = dict(stale[1], status="stale") if stale else \
                    {"symbol": s, "status": "pending", "notes": "computing; ask again shortly"}
        rows = [{f: ready[s].get(f) for f in FIELDS} for s in syms]
        table = table_from_rows(rows, field_order=FIELDS, headers=_HEADERS, formats=_FORMATS, types=_TYPES)
        pending = sum(1 for r in rows if r["status"] in ("pending", "stale"))
        return to_jsonable({"asof": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                            "units": {"vol": "pct (vol points)", "em_30d_abs": "dollars", "iv_rank": "0-100"},
                            "pending": pending, "cache_ttl_s": ttl, **table})
