"""
api/services/gex_history.py — a daily dealer-GEX history from the stored option snapshots.

The only stored option chains are SPY's end-of-day snapshots (mkt.OptionSnapshot: 2024-08-01 onward,
expiries 7–88 days out, strikes ±25% of spot) — with implied vol, gamma and daily volume but **no open
interest**. So open interest is proxied by each contract's volume summed over the last ``OI_WINDOW``
trading days (the contracts' recent turnover, which accumulates like open interest while a contract
is live), and the same dealer arithmetic as ``/api/market/gex`` is applied to it:
``analytics.gex_engine.compute_dealer_gex`` (calls +, puts −; $ per 1% move), its flip level, walls
and three-way regime. Spot is read from the snapshot itself (put-call parity at the nearest expiry),
because the stored daily closes are dividend-adjusted while strikes are not.

What this cannot see: contracts under 7 days (0DTE and weeklies, today the largest share of index
gamma), true open interest (a volume proxy cannot tell opening from closing trades), and who is long.
Treat it as a proxy regime, not a dealer book.
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
import threading
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("alan_trader.api.gex_history")

OI_WINDOW = 20
RISK_FREE = 0.045
UNITS = "$ per 1% move (dealer-signed: calls +, puts -)"
METHOD = (f"open interest proxied by each contract's {OI_WINDOW}-day volume; expiries 7-88 days "
          "(mkt.OptionSnapshot); spot from put-call parity")

_CACHE: dict[str, tuple[_dt.date, pd.DataFrame]] = {}
_LOCK = threading.Lock()


class NoHistory(LookupError):
    pass


def load_snapshots(ticker: str, since: Optional[_dt.date] = None) -> pd.DataFrame:
    from sqlalchemy import text
    from api.services.db import require_db
    sql = """
        SELECT o.SnapshotDate, o.ExpirationDate, o.Strike, o.ContractType, o.ImpliedVol, o.Gamma, o.Volume, o.Mid,
               o.Bid, o.Ask
        FROM mkt.OptionSnapshot o JOIN mkt.Ticker t ON t.TickerId = o.TickerId
        WHERE t.Symbol = :s""" + (" AND o.SnapshotDate >= :d" if since else "")
    with require_db().connect() as c:
        rows = c.execute(text(sql), {"s": ticker, "d": since}).fetchall()
    df = pd.DataFrame(rows, columns=["day", "expiry", "strike", "type", "iv", "gamma", "volume", "mid", "bid", "ask"])
    if df.empty:
        return df
    for col in ("strike", "iv", "gamma", "volume", "mid", "bid", "ask"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["day"] = pd.to_datetime(df["day"])
    df["expiry"] = pd.to_datetime(df["expiry"])
    df["type"] = np.where(df["type"].astype(str).str.upper().str.startswith("C"), "call", "put")
    df["dte"] = (df["expiry"] - df["day"]).dt.days
    return df


def add_oi_proxy(df: pd.DataFrame, window: int = OI_WINDOW) -> pd.DataFrame:
    """Each contract's volume summed over the last ``window`` snapshot days (missing days count as zero)."""
    days = np.sort(df["day"].unique())
    idx = {d: i for i, d in enumerate(days)}
    df = df.copy()
    df["di"] = df["day"].map(idx)
    df = df.sort_values(["expiry", "strike", "type", "di"])
    key = ["expiry", "strike", "type"]
    vol = df["volume"].fillna(0.0).to_numpy()
    di = df["di"].to_numpy()
    grp = df.groupby(key, sort=False).ngroup().to_numpy()
    out = np.zeros(len(df))
    start = 0
    n = len(df)
    while start < n:                                   # per contract: a sliding window over snapshot-day index
        end = start
        while end < n and grp[end] == grp[start]:
            end += 1
        cs = np.concatenate([[0.0], np.cumsum(vol[start:end])])
        d = di[start:end]
        lo = np.searchsorted(d, d - window + 1, side="left")
        out[start:end] = cs[np.arange(1, end - start + 1)] - cs[lo]
        start = end
    df["oi_proxy"] = out
    return df.drop(columns=["di"])


def parity_spot(day_rows: pd.DataFrame, r: float = RISK_FREE) -> Optional[float]:
    """S = C - P + K e^{-rT} at the nearest expiry, averaged over the three strikes where |C - P| is smallest."""
    if day_rows.empty:
        return None
    e = day_rows["expiry"].min()
    x = day_rows[day_rows["expiry"] == e]
    piv = x.pivot_table(index="strike", columns="type", values="mid", aggfunc="first").dropna()
    if piv.empty or not {"call", "put"} <= set(piv.columns):
        return None
    T = max((e - day_rows["day"].iloc[0]).days, 1) / 365.0
    piv["diff"] = (piv["call"] - piv["put"]).abs()
    best = piv.nsmallest(3, "diff")
    s = best["call"] - best["put"] + best.index.to_numpy() * math.exp(-r * T)
    return float(s.mean())


def implied_move_1d(day_rows: pd.DataFrame, spot: float) -> tuple[Optional[float], Optional[float]]:
    """(the ATM straddle's implied 1-day expected |move| as a fraction of spot, the nearest expiry's ATM IV)."""
    e = day_rows["expiry"].min()
    x = day_rows[day_rows["expiry"] == e]
    k = x.iloc[(x["strike"] - spot).abs().argsort()[:2]]["strike"].min() if len(x) else None
    if k is None:
        return None, None
    atm = x[x["strike"] == k]
    c = atm[atm["type"] == "call"]["mid"]
    p = atm[atm["type"] == "put"]["mid"]
    if c.empty or p.empty:
        return None, None
    dte = max((e - day_rows["day"].iloc[0]).days, 1)
    trading = max(dte * 252.0 / 365.0, 1.0)
    straddle = float(c.iloc[0] + p.iloc[0])
    iv = float(atm["iv"].mean()) if atm["iv"].notna().any() else None
    return straddle / math.sqrt(trading) / spot, iv


def build(ticker: str = "SPY", since: Optional[_dt.date] = None) -> pd.DataFrame:
    """One row per snapshot day: net_gex, call_gex, put_gex, flip, call_wall, put_wall, spot, dist_to_flip_pct,
    regime, implied_move_1d, atm_iv_near, contracts."""
    from analytics.gex_engine import classify_regime, compute_dealer_gex
    raw = load_snapshots(ticker, since)
    if raw.empty:
        raise NoHistory(f"no stored option snapshots for {ticker} (mkt.OptionSnapshot)")
    df = add_oi_proxy(raw)
    rows = []
    for day, g in df.groupby("day", sort=True):
        spot = parity_spot(g)
        if not spot:
            continue
        chain = pd.DataFrame({"strike": g["strike"].to_numpy(), "option_type": g["type"].to_numpy(),
                              "gamma": g["gamma"].to_numpy(), "open_interest": g["oi_proxy"].to_numpy(),
                              "iv": g["iv"].to_numpy(), "dte": g["dte"].to_numpy(),
                              "expiry": g["expiry"].to_numpy()})
        chain = chain[chain["open_interest"] > 0]
        if len(chain) < 20:
            continue
        try:
            snap = compute_dealer_gex(chain, spot)
        except Exception as exc:  # noqa: BLE001
            logger.debug("gex %s %s failed: %s", ticker, day, exc)
            continue
        from api.services.market import flip_and_regime
        flip, regime, _note = flip_and_regime(snap)
        im, iv = implied_move_1d(g, spot)
        rows.append({"date": day.date(), "spot": round(spot, 4), "net_gex": snap.net_gex, "call_gex": snap.call_gex,
                     "put_gex": snap.put_gex, "flip": flip, "call_wall": snap.call_wall, "put_wall": snap.put_wall,
                     "dist_to_flip_pct": snap.dist_to_flip_pct if flip is not None else None,
                     "regime": regime,
                     "implied_move_1d": im, "atm_iv_near": iv, "contracts": int(len(chain))})
    out = pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()
    if out.empty:
        raise NoHistory(f"no usable GEX days for {ticker}")
    return out


def history(ticker: str) -> pd.DataFrame:
    """The full history, built once a day per ticker."""
    t = ticker.upper()
    today = _dt.date.today()
    with _LOCK:
        hit = _CACHE.get(t)
    if hit is not None and hit[0] == today:
        return hit[1]
    h = build(t)
    with _LOCK:
        _CACHE[t] = (today, h)
    return h


LIVE_METHOD = ("recorded by the service from the live chain (/api/market/gex?source=hub): broker-streamed or "
               "yfinance open interest, first-week expiries and Fridays to 60 days")


def points(ticker: str, days: int = 365, interval: str = "1d") -> dict:
    """Recorded live GEX (app.GexHistory: ``1d`` = the end-of-day rows, ``30m`` = the intraday ones) and, for a
    ticker with stored option snapshots, the daily snapshot proxy before the recording began."""
    from api.serialize import to_jsonable
    from api.services import gex_recorder as REC
    t = ticker.upper()
    since = _dt.date.today() - _dt.timedelta(days=int(days))
    live = REC.history_rows(t, "eod" if interval == "1d" else "intraday", since)
    pts, sources = [], []
    first_live = None
    if not live.empty:
        first_live = pd.Timestamp(live["SlotTs"].min()).date()
        for r in live.itertuples(index=False):
            pts.append({"date": pd.Timestamp(r.SlotTs).date() if interval == "1d" else pd.Timestamp(r.SlotTs),
                        "net_gex": r.NetGex, "flip": r.Flip, "call_wall": r.CallWall, "put_wall": r.PutWall,
                        "spot": r.Spot, "regime": r.Regime, "dist_to_flip_pct": r.DistToFlipPct,
                        "call_gex": r.CallGex, "put_gex": r.PutGex, "max_pain": r.MaxPain,
                        "contracts": r.Contracts, "source": "live"})
        sources.append("live")
    caveats = []
    if interval == "1d":
        try:
            h = history(t)
        except NoHistory:
            h = None
        if h is not None:
            h = h[h.index >= since]
            if first_live is not None:
                h = h[h.index < first_live]
            proxy = [{"date": d, "net_gex": r.net_gex, "flip": r.flip, "call_wall": r.call_wall,
                      "put_wall": r.put_wall, "spot": r.spot, "regime": r.regime,
                      "dist_to_flip_pct": r.dist_to_flip_pct, "call_gex": r.call_gex, "put_gex": r.put_gex,
                      "implied_move_1d": r.implied_move_1d, "contracts": r.contracts, "source": "snapshot_proxy"}
                     for d, r in h.iterrows()]
            if proxy:
                sources.append("snapshot_proxy")
                caveats += ["snapshot_proxy points: no stored open interest (a 20-day volume proxy), monthly "
                            "expiries only, 7-88 days out"]
            pts = proxy + pts
    if not pts:
        raise NoHistory(f"no GEX history for {t} yet: nothing stored and nothing recorded (the service records "
                        f"it daily; see /api/market/gex/{t} for today's)")
    if "live" in sources:
        caveats.append("live points are comparable with each other; the snapshot proxy is on a different basis")
    dates = [p["date"] for p in pts]
    return to_jsonable({"ticker": t, "interval": interval, "units": UNITS, "sources": sources,
                        "method": {"live": LIVE_METHOD, "snapshot_proxy": METHOD}, "points": pts,
                        "first": min(dates), "last": max(dates), "days": len(pts), "caveats": caveats})
