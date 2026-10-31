"""
api/services/structure.py — term structures, headless (no Dash imports).

  curve_history   Treasury curve now and 1W / 1M / 3M / 6M / 1Y ago, and the 2s10s / 3m10y spreads
                  (mkt.MacroBar; FRED when the table is empty)
  curve_surface   the curve through time, date x tenor, sampled per day / week / month
  vix_term        the CBOE constant-maturity VIX indices (9D, 30D, 3M, 6M, 1Y) now, a week and a month ago,
                  with the VIX / VIX3M ratio history (yfinance; VIX alone from mkt.VixBar as a fallback)
  iv_term         a ticker's ATM implied volatility by expiry, 30/60/90-day constant-maturity IV
                  (variance-interpolated) and realised HV20 for the premium (stored chain, else Polygon live)
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
from typing import Optional

import numpy as np
import pandas as pd

from api.serialize import to_jsonable
from api.services.db import require_db
from api.services.market import MissingData, _api_key

logger = logging.getLogger("alan_trader.api.structure")

TENORS = [("3M", 0.25, "rate_3m"), ("6M", 0.5, "rate_6m"), ("1Y", 1.0, "rate_1y"), ("2Y", 2.0, "rate_2y"),
          ("5Y", 5.0, "rate_5y"), ("10Y", 10.0, "rate_10y"), ("30Y", 30.0, "rate_30y")]
_FRED_IDS = {"rate_3m": "DGS3MO", "rate_6m": "DGS6MO", "rate_1y": "DGS1", "rate_2y": "DGS2",
             "rate_5y": "DGS5", "rate_10y": "DGS10", "rate_30y": "DGS30"}
_SNAPSHOTS = [("Today", 0), ("1W ago", 7), ("1M ago", 30), ("3M ago", 91), ("6M ago", 182), ("1Y ago", 365)]


# ── Treasury curve ────────────────────────────────────────────────────────────

def _curve_frame(days: int) -> tuple[pd.DataFrame, str]:
    """Yields in percent, date-indexed, one column per tenor."""
    cols = [c for _, _, c in TENORS]
    today = _dt.date.today()
    try:
        from db.client import get_macro_bars
        m = get_macro_bars(require_db(), today - _dt.timedelta(days=days), today)
        if m is not None and not m.empty and "rate_10y" in m.columns and m["rate_10y"].notna().sum() >= 20:
            present = [c for c in cols if c in m.columns]
            df = m[present].dropna(how="all") * 100.0      # stored as fractions
            df.index = pd.to_datetime(df.index)
            return df.sort_index(), "db"
    except Exception as exc:
        logger.warning("macro bars unavailable: %s", exc)

    import requests
    from io import StringIO
    frames = []
    for col, sid in _FRED_IDS.items():
        try:
            r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=10)
            r.raise_for_status()
            f = pd.read_csv(StringIO(r.text))
            f.columns = ["date", col]
            f["date"] = pd.to_datetime(f["date"], errors="coerce")
            f[col] = pd.to_numeric(f[col], errors="coerce")
            frames.append(f.dropna(subset=["date"]).set_index("date"))
        except Exception as exc:
            logger.warning("FRED %s failed: %s", sid, exc)
    if not frames:
        raise MissingData("No Treasury yields: mkt.MacroBar is empty and FRED returned nothing.")
    df = pd.concat(frames, axis=1).sort_index()
    df = df[df.index >= pd.Timestamp(today - _dt.timedelta(days=days))].dropna(how="all")
    return df, "fred"


def curve_history(days: int = 400) -> dict:
    df, source = _curve_frame(max(days, 380))
    if df.empty:
        raise MissingData("No Treasury yields in the window.")
    tenors = [(t, y, c) for t, y, c in TENORS if c in df.columns and df[c].notna().any()]
    latest = df.index[-1]
    curves = []
    for label, back in _SNAPSHOTS:
        target = latest - pd.Timedelta(days=back)
        prior = df[df.index <= target]
        if prior.empty:
            continue
        row = prior.ffill().iloc[-1]
        curves.append({"label": label, "date": prior.index[-1],
                       "yields": [None if pd.isna(row.get(c)) else round(float(row[c]), 4) for _, _, c in tenors]})
    spreads = []
    for name, long_c, short_c in (("2s10s", "rate_10y", "rate_2y"), ("3m10y", "rate_10y", "rate_3m")):
        if long_c in df.columns and short_c in df.columns:
            s = (df[long_c] - df[short_c]).dropna()
            spreads.append({"name": name, "t": [d.date().isoformat() for d in s.index], "v": [round(float(x), 4) for x in s]})
    last = df.ffill().iloc[-1]
    s2s10s = float(last["rate_10y"] - last["rate_2y"]) if {"rate_10y", "rate_2y"} <= set(df.columns) else None
    s3m10y = float(last["rate_10y"] - last["rate_3m"]) if {"rate_10y", "rate_3m"} <= set(df.columns) else None
    return to_jsonable({"asof": latest, "source": source, "units": "pct",
                        "tenors": [t for t, _, _ in tenors], "years": [y for _, y, _ in tenors],
                        "curves": curves, "spreads": spreads,
                        "spread_2s10s": s2s10s, "spread_3m10y": s3m10y,
                        "inverted_2s10s": s2s10s is not None and s2s10s < 0,
                        "inverted_3m10y": s3m10y is not None and s3m10y < 0})


# ── Treasury curve surface (date x tenor) ─────────────────────────────────────

#: step -> pandas period frequency of the buckets (each bucket keeps its last observed day)
SURFACE_STEPS = {"1d": "D", "1w": "W-FRI", "1m": "M"}
SURFACE_MAX_ROWS = 800
SURFACE_FFILL_DAYS = 5


def surface_rows(df: pd.DataFrame, step: str = "1w", max_rows: int = SURFACE_MAX_ROWS,
                 ffill_days: int = SURFACE_FFILL_DAYS) -> pd.DataFrame:
    """One row per ``step`` bucket: the last day in the bucket that has an observation, with each
    tenor's gaps forward-filled from at most ``ffill_days`` calendar days earlier (a longer gap stays
    missing). Keeps the most recent ``max_rows`` rows. ``df`` is date-indexed, one column per tenor."""
    if step not in SURFACE_STEPS:
        raise ValueError(f"step must be one of {sorted(SURFACE_STEPS)}")
    d = df.sort_index()
    d = d[~d.index.duplicated(keep="last")].dropna(how="all")
    if d.empty:
        return d
    d.index = pd.to_datetime(d.index).normalize()
    cal = pd.date_range(d.index.min(), d.index.max(), freq="D")
    filled = d.reindex(cal).ffill(limit=int(ffill_days)).reindex(d.index)
    buckets = d.index.to_period(SURFACE_STEPS[step])
    last_days = pd.Series(d.index, index=d.index).groupby(buckets).max()
    out = filled.loc[pd.DatetimeIndex(last_days.values)]
    return out.iloc[-int(max_rows):] if len(out) > max_rows else out


def curve_surface(days: int = 730, step: str = "1w") -> dict:
    """The Treasury curve through time: dates x tenors of yields in percent (null when missing)."""
    if step not in SURFACE_STEPS:
        raise ValueError(f"step must be one of {sorted(SURFACE_STEPS)}")
    df, source = _curve_frame(days)
    if df.empty:
        raise MissingData("No Treasury yields in the window.")
    tenors = [(t, y, c) for t, y, c in TENORS if c in df.columns and df[c].notna().any()]
    rows = surface_rows(df[[c for _, _, c in tenors]], step)
    if rows.empty:
        raise MissingData("No Treasury yields in the window.")
    return to_jsonable({
        "asof": df.index[-1], "source": source, "units": "pct", "step": step,
        "tenors": [t for t, _, _ in tenors], "years": [y for _, y, _ in tenors],
        "dates": [d.date().isoformat() for d in rows.index],
        "yields": [[None if pd.isna(v) else round(float(v), 4) for v in r] for r in rows.itertuples(index=False)],
    })


# ── VIX term structure ────────────────────────────────────────────────────────

VIX_INDICES = [("VIX9D", "^VIX9D", 9), ("VIX", "^VIX", 30), ("VIX3M", "^VIX3M", 93),
               ("VIX6M", "^VIX6M", 183), ("VIX1Y", "^VIX1Y", 365)]


def _closes_yf(symbols: list[str]) -> dict[str, pd.Series]:
    import yfinance as yf
    raw = yf.download(symbols, period="4mo", interval="1d", auto_adjust=False, progress=False, group_by="ticker", threads=True)
    out: dict[str, pd.Series] = {}
    if raw is None or raw.empty:
        return out
    multi = isinstance(raw.columns, pd.MultiIndex)
    for s in symbols:
        try:
            sub = raw[s] if multi else raw
            close = pd.to_numeric(sub["Close"], errors="coerce").dropna()
            if not close.empty:
                close.index = pd.to_datetime(close.index).tz_localize(None) if getattr(close.index, "tz", None) else pd.to_datetime(close.index)
                out[s] = close
        except Exception:
            continue
    return out


def vix_term() -> dict:
    notes: list[str] = []
    closes: dict[str, pd.Series] = {}
    try:
        closes = _closes_yf([sym for _, sym, _ in VIX_INDICES])
    except Exception as exc:
        notes.append(f"yfinance failed: {type(exc).__name__}")
    if "^VIX" not in closes:
        try:
            from db.client import get_vix_bars
            v = get_vix_bars(require_db(), _dt.date.today() - _dt.timedelta(days=130), _dt.date.today())
            if v is not None and not v.empty:
                col = "close" if "close" in v.columns else v.columns[-1]
                s = pd.to_numeric(v[col], errors="coerce").dropna()
                s.index = pd.to_datetime(s.index)
                closes["^VIX"] = s
                notes.append("VIX from the database; the other maturities were unavailable")
        except Exception as exc:
            logger.warning("VIX bars unavailable: %s", exc)
    if not closes:
        raise MissingData("No VIX term structure: yfinance returned nothing and no VIX bars are stored.")

    def at(s: pd.Series, sessions_back: int) -> Optional[float]:
        return float(s.iloc[-1 - sessions_back]) if len(s) > sessions_back else None

    points = []
    for name, sym, days in VIX_INDICES:
        s = closes.get(sym)
        if s is None:
            continue
        points.append({"name": name, "symbol": sym, "days": days, "value": at(s, 0),
                       "week_ago": at(s, 5), "month_ago": at(s, 21), "asof": s.index[-1]})
    by = {p["name"]: p["value"] for p in points}
    ratio = by["VIX"] / by["VIX3M"] if by.get("VIX") and by.get("VIX3M") else None
    front = by.get("VIX9D") or by.get("VIX")
    back = by.get("VIX3M") or by.get("VIX6M")
    shape = None
    if front and back:
        shape = "backwardation" if front > back * 1.01 else "contango" if front < back * 0.99 else "flat"
    ratio_series = None
    if "^VIX" in closes and "^VIX3M" in closes:
        r = (closes["^VIX"] / closes["^VIX3M"]).dropna()
        ratio_series = {"name": "VIX/VIX3M", "t": [d.date().isoformat() for d in r.index], "v": [round(float(x), 4) for x in r]}
    return to_jsonable({"asof": max(p["asof"] for p in points) if points else None, "points": points,
                        "ratio_vix_vix3m": ratio, "shape": shape, "ratio_history": ratio_series,
                        "source": "yfinance", "warnings": notes})


# ── Implied-vol term structure ────────────────────────────────────────────────

def _spot(ticker: str) -> tuple[float, str]:
    try:
        from data.stock_data import yf_stock_price
        p = yf_stock_price(ticker)
        if p:
            return float(p), "yfinance"
    except Exception:
        pass
    from db.client import get_price_bars
    df = get_price_bars(require_db(), ticker, _dt.date.today() - _dt.timedelta(days=10), _dt.date.today())
    if df is None or df.empty:
        raise MissingData(f"No spot for {ticker}.")
    return float(df["close"].iloc[-1]), "db"


def _stored_iv_chain(ticker: str):
    from db.client import get_option_coverage, get_option_snapshots
    eng = require_db()
    cov = get_option_coverage(eng, ticker)
    if not cov:
        return None
    day = cov[1]
    chain = get_option_snapshots(eng, ticker, day)
    if chain is None or chain.empty or "iv" not in chain.columns:
        return None
    chain = chain.rename(columns={"expiration": "expiry", "contract_type": "type", "option_type": "type"})
    return chain, day


def _live_iv_chain(ticker: str, spot: float, max_dte: int):
    from data.polygon_client import PolygonClient
    c = PolygonClient(api_key=_api_key())
    today = _dt.date.today()
    results, url = [], f"/v3/snapshot/options/{ticker}"
    params = {"expiration_date.gte": str(today), "expiration_date.lte": str(today + _dt.timedelta(days=max_dte)),
              "strike_price.gte": round(spot * 0.97, 2), "strike_price.lte": round(spot * 1.03, 2), "limit": 250}
    while url:
        data = c._get(url, params)
        results.extend(data.get("results", []))
        nxt = (data.get("next_url") or "").replace(c.BASE, "")
        url, params = (nxt or None), {}
    rows = [{"strike": float(d["strike_price"]), "type": str(d.get("contract_type", "")).lower(),
             "expiry": d.get("expiration_date"), "iv": r.get("implied_volatility")}
            for r in results if (d := r.get("details") or {}).get("strike_price")]
    return (pd.DataFrame(rows), today) if rows else None


def _interp_iv(points: list[dict], days: int) -> Optional[float]:
    """Constant-maturity IV by linear interpolation of total variance (iv² · t) between expiries."""
    pts = sorted((p["dte"], p["atm_iv"]) for p in points if p["atm_iv"] and p["dte"] > 0)
    if len(pts) < 2 or not (pts[0][0] <= days <= pts[-1][0]):
        return None
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= days <= d1:
            w0, w1 = v0 * v0 * d0, v1 * v1 * d1
            w = w0 + (w1 - w0) * (days - d0) / (d1 - d0) if d1 > d0 else w0
            return round(math.sqrt(max(w, 0) / days), 4)
    return None


def iv_term(ticker: str, source: str = "auto", max_dte: int = 180) -> dict:
    from engine.iv_metrics import _extract_atm_iv_from_expiry, _compute_hv20
    ticker = ticker.upper().strip()
    spot, spot_source = _spot(ticker)
    notes: list[str] = []
    got, used = None, None
    if source in ("auto", "db"):
        got, used = _stored_iv_chain(ticker), "db"
        if got is not None and source == "auto" and (_dt.date.today() - got[1]).days > 5:
            notes.append(f"stored chain is {(_dt.date.today() - got[1]).days} days old; using Polygon live")
            got = None
    if got is None and source in ("auto", "polygon"):
        got, used = _live_iv_chain(ticker, spot, max_dte), "polygon"
    if got is None:
        raise MissingData(f"No option chain with implied vols for {ticker}.")
    chain, asof = got
    chain["expiry"] = pd.to_datetime(chain["expiry"])
    chain["dte"] = (chain["expiry"] - pd.Timestamp(asof)).dt.days
    chain["iv"] = pd.to_numeric(chain["iv"], errors="coerce")
    chain["strike"] = pd.to_numeric(chain["strike"], errors="coerce")
    chain["type"] = chain["type"].astype(str).str.lower().map(lambda t: "call" if t.startswith("c") else "put")
    chain = chain.dropna(subset=["iv", "strike"])
    chain = chain[(chain["dte"] >= 1) & (chain["dte"] <= max_dte) & (chain["iv"] > 0.01) & (chain["iv"] < 5)]

    points = []
    for exp, g in chain.groupby("expiry"):
        atm_iv, k = _extract_atm_iv_from_expiry(g, spot)
        if atm_iv is None:
            continue
        at_k = g[g["strike"] == k]
        c = at_k[at_k["type"] == "call"]["iv"]
        p = at_k[at_k["type"] == "put"]["iv"]
        points.append({"expiry": exp.date(), "dte": int(g["dte"].iloc[0]), "atm_iv": round(float(atm_iv), 4),
                       "atm_strike": k, "call_iv": float(c.iloc[0]) if len(c) else None,
                       "put_iv": float(p.iloc[0]) if len(p) else None})
    points.sort(key=lambda p: p["dte"])
    if not points:
        raise MissingData(f"{ticker}: the chain had no usable at-the-money implied vols.")

    iv30, iv60, iv90 = (_interp_iv(points, d) for d in (30, 60, 90))
    hv20 = None
    try:
        from db.client import get_price_bars
        px = get_price_bars(require_db(), ticker, _dt.date.today() - _dt.timedelta(days=60), _dt.date.today())
        if px is not None and not px.empty:
            hv20 = _compute_hv20(px.set_index(pd.to_datetime(px["date"])).sort_index())
    except Exception as exc:
        logger.info("hv20 for %s unavailable: %s", ticker, exc)
    slope = (iv90 - iv30) if iv30 is not None and iv90 is not None else None
    shape = None if slope is None else "contango" if slope > 0.005 else "backwardation" if slope < -0.005 else "flat"
    return to_jsonable({"ticker": ticker, "spot": spot, "spot_source": spot_source, "asof": asof, "source": used,
                        "points": points, "iv_30": iv30, "iv_60": iv60, "iv_90": iv90, "hv20": hv20,
                        "slope_30_90": slope, "shape": shape, "units": "fraction", "warnings": notes})
