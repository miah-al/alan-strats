"""
api/services/market.py — market data: the database first, the network where the
Market page goes to it.

  tickers / bars      mkt.PriceBar, mkt.MinuteBar (Polygon aggregates when the DB has none)
  quote               the market-data hub (tastytrade streamer / polling fallbacks), else yfinance,
                      DB last closes as the last resort

Every network call here passes the service's request gate (api/marketdata/limits.py).
  movers              Polygon grouped daily (``data.movers``)
  yield curve         mkt.MacroBar (FRED via ``data.treasury_curve`` as fallback)
  IV                  engine.iv_metrics (Polygon option snapshots) on DB / yfinance bars
  GEX                 analytics.gex_engine on the latest stored mkt.OptionSnapshot chain
                      (Polygon's live snapshot, as the Market page uses, when none is stored)
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
from typing import Optional

import numpy as np
import pandas as pd

from api.serialize import table_from_df, table_from_rows, to_jsonable
from api.services.db import require_db

logger = logging.getLogger("alan_trader.api.market")

NY = "America/New_York"
_VIX_ALIASES = {"VIX", "^VIX", "I:VIX"}
_MAX_MINUTE_DAYS = 31


class MissingData(LookupError):
    """No data for the request; routers answer 422 with the reason."""


class NeedsApiKey(RuntimeError):
    pass


def _api_key(required: bool = True) -> str:
    from engine.env import get_polygon_api_key
    key = get_polygon_api_key()
    if required and not key:
        raise NeedsApiKey("No Polygon API key configured (POLYGON_API_KEY in .env).")
    return key


def _d(s: Optional[str], default: _dt.date) -> _dt.date:
    if not s:
        return default
    return _dt.date.fromisoformat(str(s)[:10])


# ── Tickers ───────────────────────────────────────────────────────────────────

def tickers() -> list[dict]:
    from sqlalchemy import text
    with require_db().connect() as c:
        rows = c.execute(text("""
            SELECT t.Symbol, MIN(pb.BarDate), MAX(pb.BarDate), COUNT(*)
            FROM   mkt.PriceBar pb
            JOIN   mkt.Ticker t ON t.TickerId = pb.TickerId
            GROUP BY t.Symbol
            ORDER BY t.Symbol
        """)).fetchall()
    return to_jsonable([{"ticker": r[0], "first": r[1], "last": r[2], "bars": int(r[3])} for r in rows])


# ── Bars ──────────────────────────────────────────────────────────────────────

def _ohlcv(ticker: str, interval: str, source: str, df: pd.DataFrame, tcol: str) -> dict:
    t = df[tcol]
    if interval == "1m":
        ts = pd.to_datetime(t)
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward")
        else:
            ts = ts.dt.tz_convert(NY)
        tv = [x.isoformat() if not pd.isna(x) else None for x in ts]
    else:
        tv = [pd.Timestamp(x).date().isoformat() for x in t]

    def col(name):
        if name not in df.columns:
            return [None] * len(df)
        return [to_jsonable(v) for v in pd.to_numeric(df[name], errors="coerce").tolist()]

    return {"ticker": ticker, "interval": interval, "source": source, "t": tv,
            "o": col("open"), "h": col("high"), "l": col("low"), "c": col("close"), "v": col("volume")}


def _polygon_aggs(ticker: str, fd: _dt.date, td: _dt.date, timespan: str) -> pd.DataFrame:
    from data.polygon_client import PolygonClient
    c = PolygonClient(api_key=_api_key())
    data = c._get(f"/v2/aggs/ticker/{ticker}/range/1/{timespan}/{fd}/{td}",
                  {"adjusted": "true", "sort": "asc", "limit": 50000})
    res = data.get("results", []) or []
    if not res:
        return pd.DataFrame()
    df = pd.DataFrame(res).rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    if timespan == "minute":
        df["ts"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(NY)
    else:
        df["ts"] = pd.to_datetime(df["t"], unit="ms").dt.date
    return df


def bars(ticker: str, from_date: Optional[str], to_date: Optional[str], interval: str = "1d") -> dict:
    from db.client import get_minute_bars, get_price_bars, get_vix_bars
    ticker = ticker.upper().strip()
    if interval not in ("1d", "1m"):
        raise ValueError("interval must be 1d or 1m")
    td = _d(to_date, _dt.date.today())
    fd = _d(from_date, td - _dt.timedelta(days=5 if interval == "1m" else 365))
    if fd > td:
        raise ValueError("from must not be after to")
    eng = require_db()
    topped = None
    if interval == "1d" and ticker not in _VIX_ALIASES:
        from api.services.bars_topup import top_up
        topped = top_up(ticker, td)                       # stale or missing stored bars: pull the missing days first
    if interval == "1d":
        df = get_price_bars(eng, ticker, fd, td)
        if (df is None or df.empty) and ticker in _VIX_ALIASES:
            v = get_vix_bars(eng, fd, td)
            if not v.empty:
                df = v.reset_index()
        if df is not None and not df.empty:
            out = _ohlcv(ticker, interval, "db", df, "date")
            if topped is not None:
                out["topped_up"] = {k: v for k, v in topped.items() if k in ("status", "rows", "detail")}
            return out
        pdf = _polygon_aggs(ticker if ticker not in _VIX_ALIASES else "I:VIX", fd, td, "day")
        if pdf.empty:
            raise MissingData(f"No daily bars for {ticker} between {fd} and {td}: none stored in "
                              f"mkt.PriceBar and Polygon returned none.")
        return _ohlcv(ticker, interval, "polygon", pdf, "ts")
    if (td - fd).days > _MAX_MINUTE_DAYS:
        raise ValueError(f"1m bars are limited to {_MAX_MINUTE_DAYS} days per request")
    df = get_minute_bars(eng, ticker, fd, td)
    if df is not None and not df.empty:
        return _ohlcv(ticker, interval, "db", df, "ts")
    pdf = _polygon_aggs(ticker, fd, td, "minute")
    if pdf.empty:
        raise MissingData(f"No 1-minute bars for {ticker} between {fd} and {td}: none stored in "
                          f"mkt.MinuteBar and Polygon returned none.")
    return _ohlcv(ticker, interval, "polygon", pdf, "ts")


# ── Quote ─────────────────────────────────────────────────────────────────────

def quote(ticker: str, hub=None) -> dict:
    """The v1 quote shape. From the market-data hub when it can price the symbol (the tastytrade
    streamer, else the polling fallbacks), with the hub's quote fields added; otherwise yfinance
    (through the request gate, cached 5 s) and the last stored daily bars."""
    ticker = ticker.upper().strip()
    if hub is not None and hub.providers:
        m = hub.quote(ticker, wait=3.0)
        px = m.get("last") if m.get("last") is not None else m.get("mid")
        if px is not None:
            extra = {k: v for k, v in m.items() if k not in ("type", "symbol", "change", "change_pct", "prev_close",
                                                              "volume", "source", "open", "high", "low")}
            return to_jsonable({"ticker": ticker, "source": m.get("source"), "close": px, "open": m.get("open"),
                                "high": m.get("high"), "low": m.get("low"), "volume": m.get("volume"), "vwap": None,
                                "prev_close": m.get("prev_close"), "change": m.get("change"),
                                "change_pct": m.get("change_pct"), "asof": m.get("time"), "live": True, **extra})
    from api.marketdata.cache import cached
    return cached(("quote-v1", ticker), 5.0, lambda: _quote_fallback(ticker), cache_errors=(MissingData,), error_ttl=15.0)


def _quote_fallback(ticker: str) -> dict:
    q = None
    try:
        from data.stock_data import yf_quote
        q = yf_quote(ticker)
    except Exception as exc:
        logger.warning("yfinance quote %s failed: %s", ticker, exc)
    if q:
        return to_jsonable({"ticker": ticker, "source": "yfinance", **q})
    from db.client import get_price_bars
    df = get_price_bars(require_db(), ticker, _dt.date.today() - _dt.timedelta(days=14), _dt.date.today())
    if df is None or df.empty:
        raise MissingData(f"No quote for {ticker}: yfinance returned nothing and no bars are stored.")
    last = df.iloc[-1]
    prev = float(df["close"].iloc[-2]) if len(df) > 1 else float(last["close"])
    close = float(last["close"])
    return to_jsonable({"ticker": ticker, "source": "db", "close": close, "open": last.get("open"),
                        "high": last.get("high"), "low": last.get("low"), "volume": last.get("volume"),
                        "vwap": last.get("vwap"), "prev_close": prev, "change": close - prev,
                        "change_pct": (close - prev) / prev * 100 if prev else 0.0,
                        "asof": last["date"], "live": False})


# ── Movers ────────────────────────────────────────────────────────────────────

def movers(top_n: int = 12) -> dict:
    from data.movers import fetch_grouped_movers
    mv = fetch_grouped_movers(_api_key(), top_n=top_n)
    if not mv:
        raise MissingData("Polygon grouped daily returned no sessions in the last 8 days.")
    rows = ([{**r, "side": "gainer"} for r in mv["gainers"]] +
            [{**r, "side": "loser"} for r in mv["losers"]])
    t = table_from_rows(rows, field_order=["ticker", "price", "change_pct", "volume", "side"],
                        headers={"ticker": "Ticker", "price": "Price", "change_pct": "Change %",
                                 "volume": "Volume", "side": "Side"},
                        formats={"price": "price", "change_pct": "pct", "volume": "int"})
    t.update({"asof": mv.get("asof"), "universe": len(mv.get("all") or [])})
    return t


# ── Yield curve ───────────────────────────────────────────────────────────────

_TENORS = [("3M", 0.25, "rate_3m"), ("6M", 0.5, "rate_6m"), ("1Y", 1.0, "rate_1y"), ("2Y", 2.0, "rate_2y"),
           ("5Y", 5.0, "rate_5y"), ("10Y", 10.0, "rate_10y"), ("30Y", 30.0, "rate_30y")]


def yield_curve() -> dict:
    from db.client import get_macro_bars
    try:
        m = get_macro_bars(require_db(), _dt.date.today() - _dt.timedelta(days=30), _dt.date.today())
    except Exception as exc:
        logger.warning("macro bars unavailable: %s", exc)
        m = pd.DataFrame()
    if m is not None and not m.empty:
        cols = [c for _, _, c in _TENORS if c in m.columns]
        m = m.dropna(subset=cols, how="all")
        if not m.empty:
            row = m.iloc[-1]
            ten = [(t, y, c) for t, y, c in _TENORS if c in m.columns and pd.notna(row.get(c))]
            return to_jsonable({"asof": m.index[-1], "tenors": [t for t, _, _ in ten],
                                "yields": [float(row[c]) * 100.0 for _, _, c in ten],
                                "years": [y for _, y, _ in ten], "units": "pct", "source": "db"})
    from data.treasury_curve import load_treasury_curve
    df = load_treasury_curve()
    if df is None or df.empty:
        raise MissingData("No yield curve: mkt.MacroBar is empty and FRED returned nothing.")
    cols = [c for _, _, c in _TENORS if c in df.columns]
    df = df.dropna(subset=cols, how="all")
    row = df.iloc[-1]
    ten = [(t, y, c) for t, y, c in _TENORS if c in df.columns and pd.notna(row.get(c))]
    return to_jsonable({"asof": row["date"], "tenors": [t for t, _, _ in ten],
                        "yields": [float(row[c]) for _, _, c in ten], "years": [y for _, y, _ in ten],
                        "units": "pct", "source": "fred"})


# ── IV metrics ────────────────────────────────────────────────────────────────

def iv(ticker: str) -> dict:
    from db.client import get_price_bars
    from engine.iv_metrics import get_ticker_iv_metrics
    ticker = ticker.upper().strip()
    df = get_price_bars(require_db(), ticker, _dt.date.today() - _dt.timedelta(days=120), _dt.date.today())
    price_source = "db"
    if df is None or df.empty:
        from engine.screener import _fetch_ohlcv
        df = _fetch_ohlcv(ticker, "", bars=60)
        price_source = "yfinance"
        if df is None or df.empty:
            raise MissingData(f"No price history for {ticker} (DB and yfinance empty).")
    else:
        df = df.set_index(pd.to_datetime(df["date"])).sort_index()
    m = get_ticker_iv_metrics(ticker, _api_key(), price_df=df)
    spot = float(df["close"].iloc[-1])
    return to_jsonable({"ticker": ticker, "spot": spot, "spot_asof": df.index[-1],
                        "price_source": price_source, **m})


# ── GEX ───────────────────────────────────────────────────────────────────────

def _db_chain(ticker: str):
    """(chain, spot, snapshot date) from the latest stored option snapshot, or None."""
    from db.client import get_option_coverage, get_option_snapshots, get_price_bars
    eng = require_db()
    cov = get_option_coverage(eng, ticker)
    if not cov:
        return None
    snap_day = cov[1]
    chain = get_option_snapshots(eng, ticker, snap_day)
    if chain is None or chain.empty:
        return None
    px = get_price_bars(eng, ticker, snap_day - _dt.timedelta(days=10), snap_day)
    if px is None or px.empty:
        return None
    spot = float(px["close"].iloc[-1])
    chain = chain.rename(columns={"expiration": "expiry"})
    chain["expiry"] = pd.to_datetime(chain["expiry"])
    chain["dte"] = (chain["expiry"] - pd.Timestamp(snap_day)).dt.days
    chain["open_interest"] = pd.to_numeric(chain["open_interest"], errors="coerce")
    chain["volume"] = pd.to_numeric(chain.get("volume"), errors="coerce")
    chain = chain[(chain["dte"] >= 0) & (chain["dte"] <= 60)
                  & (chain["strike"] >= spot * 0.85) & (chain["strike"] <= spot * 1.15)]
    return (chain, spot, snap_day) if not chain.empty else None


def flip_and_regime(snap) -> tuple[Optional[float], str, Optional[str]]:
    """(flip, regime, note). The engine answers the spot itself when net GEX never crosses zero within ±20%,
    which would read as "near flip": that is no flip at all, and the regime is the sign of net GEX."""
    from analytics.gex_engine import classify_regime
    f = snap.flip_level
    if f is None or not math.isfinite(f):
        return None, "unknown", None
    if abs(f - snap.spot) <= 1e-9 * max(abs(snap.spot), 1.0):
        return None, ("positive" if snap.net_gex > 0 else "negative"), \
            "net GEX does not cross zero within ±20% of spot: no flip level; regime from its sign"
    return float(f), classify_regime(snap), None


def gex_spot(ticker: str, hub=None) -> Optional[float]:
    """The underlying's price for GEX: the market-data hub (an index at its last level — the broker's index
    quote, or the session's last one after hours), else yfinance, else the last stored close."""
    from api.marketdata import symbols as SYM
    if hub is not None and getattr(hub, "providers", None):
        try:
            px = hub.price(ticker, wait=3.0)
            if px:
                return float(px)
        except Exception as exc:
            logger.info("hub price for %s unavailable: %s", ticker, exc)
    try:
        from data.stock_data import yf_stock_price
        px = yf_stock_price(SYM.to_yfinance(SYM.normalize(ticker)))
        if px:
            return float(px)
    except Exception:
        pass
    try:
        from db.client import get_price_bars
        df = get_price_bars(require_db(), ticker, _dt.date.today() - _dt.timedelta(days=10), _dt.date.today())
        if df is not None and not df.empty:
            return float(df["close"].iloc[-1])
    except Exception:
        pass
    return None


#: the live chain for GEX: every strike within ±1.5% of spot, a sample out to ±8%, at most 90 per expiry;
#: every expiry in the first week, then Fridays to 60 days, at most 10 expiries
GEX_BAND = (0.015, 0.08, 90)
GEX_MAX_EXPIRIES = 10
GEX_MAX_DTE = 60


def _gex_expiries(exps: list[tuple[_dt.date, int]]) -> list[tuple[_dt.date, int]]:
    near = [e for e in exps if 0 <= e[1] <= 7]
    later = [e for e in exps if 7 < e[1] <= GEX_MAX_DTE and e[0].weekday() == 4]
    room = max(GEX_MAX_EXPIRIES - len(near), 0)
    if len(later) > room:
        monthly = [e for e in later if 15 <= e[0].day <= 21]            # third Fridays first
        rest = [e for e in later if e not in monthly]
        later = sorted((monthly + rest)[:room])
    return (near + later)[:GEX_MAX_EXPIRIES]


def _hub_chain(ticker: str, hub, spot: float, notes: list[str]):
    """(chain, spot, today, sources) from the market-data hub's merged chains (the broker's streamed OI and
    greeks where connected; yfinance / Polygon otherwise), or None."""
    from concurrent.futures import ThreadPoolExecutor
    from api.marketdata import options as O
    from api.marketdata import symbols as SYM
    u, root = SYM.underlying_and_root(ticker)
    e = O.expirations(hub, ticker)
    exps = [(_dt.date.fromisoformat(str(x["expiry"])[:10]), int(x["dte"])) for x in e["expirations"]]
    chosen = _gex_expiries(exps)
    if not chosen:
        return None
    today = _dt.date.today()
    used: set[str] = set()

    def one(ed):
        n: list[str] = []
        rows, src = O.merged_chain(hub, u, ed[0], spot, 60, n, linger=False, root=root, band=GEX_BAND)
        return ed, rows, src, n

    out = []
    with ThreadPoolExecutor(max_workers=min(len(chosen), 6), thread_name_prefix="gex-chain") as pool:
        for (exp, dte), rows, src, n in pool.map(one, chosen):
            used.update(src)
            if not rows:
                notes.append(f"{exp}: no chain ({'; '.join(n)[:100]})")
                continue
            for r in rows:
                for side in ("call", "put"):
                    q = r.get(side) or {}
                    oi = q.get("oi")
                    if oi is None or float(oi) <= 0 or (q.get("gamma") is None and q.get("iv") is None):
                        continue
                    out.append({"strike": float(r["strike"]), "contract_type": side, "expiry": pd.Timestamp(exp),
                                "gamma": q.get("gamma"), "open_interest": float(oi), "iv": q.get("iv"), "dte": dte})
    if not out:
        notes.append("the live chain carried no open interest with greeks / IV")
        return None
    notes.append(f"live chain: {len(chosen)} expiries to {chosen[-1][1]} days, strikes within ±1.5% of spot "
                 f"and a sample to ±8% ({len(out)} contracts)")
    chain = pd.DataFrame(out)
    chain["gamma"] = pd.to_numeric(chain["gamma"], errors="coerce")
    return chain, float(spot), today, sorted(used)


def _polygon_chain(ticker: str, spot: Optional[float] = None):
    """The Market page's GEX source: Polygon's option snapshot, 0-60 DTE, spot ±15%."""
    from data.polygon_client import PolygonClient
    c = PolygonClient(api_key=_api_key())
    spot = spot or gex_spot(ticker)
    if not spot:
        raise MissingData(f"Could not fetch spot price for {ticker}.")
    today = _dt.date.today()
    results, url = [], f"/v3/snapshot/options/{ticker}"
    params = {"expiration_date.gte": str(today),
              "expiration_date.lte": str(today + _dt.timedelta(days=60)),
              "strike_price.gte": round(spot * 0.85, 0), "strike_price.lte": round(spot * 1.15, 0),
              "limit": 250}
    while url:
        data = c._get(url, params)
        results.extend(data.get("results", []))
        nxt = (data.get("next_url") or "").replace(c.BASE, "")
        url, params = (nxt or None), {}
    rows = []
    for r in results:
        det = r.get("details") or {}
        if not det.get("strike_price"):
            continue
        rows.append({"strike": float(det["strike_price"]), "contract_type": str(det.get("contract_type", "")).lower(),
                     "expiry": det.get("expiration_date"), "gamma": (r.get("greeks") or {}).get("gamma"),
                     "open_interest": r.get("open_interest") or 0, "iv": r.get("implied_volatility")})
    if not rows:
        return None
    chain = pd.DataFrame(rows)
    chain["expiry"] = pd.to_datetime(chain["expiry"])
    chain["dte"] = (chain["expiry"] - pd.Timestamp(today)).dt.days
    return chain, float(spot), today


#: A stored chain older than this is not "the market now"; auto mode goes to Polygon instead.
GEX_DB_MAX_AGE_DAYS = 5


def gex(ticker: str, source: str = "auto", hub=None) -> dict:
    """``source``: ``auto`` — a recent stored chain; else, for an index (NDX, SPX, RUT …; NDXP / SPXW name
    the root), the market-data hub's live chain, and for anything else Polygon's snapshot with the hub's
    chain as the fallback; else a stale stored chain with a warning. ``db``, ``polygon`` or ``hub`` force one."""
    from analytics.gex_engine import _compute_gamma_column, _normalize_chain, compute_dealer_gex, _GEX_NOTIONAL_SCALE
    from api.marketdata import symbols as SYM
    ticker = ticker.upper().strip()
    try:
        und, root = SYM.underlying_and_root(ticker)
    except ValueError as exc:
        raise MissingData(str(exc))
    index = SYM.is_index(und)
    notes: list[str] = []
    got, used = None, None
    stale = None
    if source in ("auto", "db"):
        got, used = _db_chain(und), "db"
        if got is not None and source == "auto" and (_dt.date.today() - got[2]).days > GEX_DB_MAX_AGE_DAYS:
            stale, got = got, None
    spot = None
    have_hub = hub is not None and getattr(hub, "providers", None)
    if got is None and source in ("auto", "polygon", "hub"):
        spot = gex_spot(und, hub)
        if not spot:
            raise MissingData(f"No spot price for {und}: the market-data hub, yfinance and the stored bars "
                              f"have none.")
    if got is None and source == "polygon" or (got is None and source == "auto" and not index):
        try:
            live = _polygon_chain(und, spot) if _api_key(required=False) else None
        except Exception as exc:  # noqa: BLE001 — the hub's chain is next
            if source == "polygon":
                raise
            notes.append(f"polygon: {type(exc).__name__}: {str(exc)[:120]}")
            live = None
        if live is not None:
            got, used = live, "polygon"
    if got is None and source in ("auto", "hub") and have_hub:
        live = _hub_chain(ticker if root else und, hub, spot, notes)
        if live is not None:
            chain_, spot_, asof_, srcs = live
            got, used = (chain_, spot_, asof_), "hub:" + "+".join(srcs)
    if got is None and stale is not None:
        got, used = stale, "db"
        notes.append(f"stored chain is {(_dt.date.today() - stale[2]).days} days old (no live chain)")
    if got is None:
        raise MissingData(f"No option chain for {ticker} (source={source}): nothing usable stored in "
                          f"mkt.OptionSnapshot and no live chain from Polygon or the market-data hub.")
    chain, spot, asof = got
    source = used
    snap = compute_dealer_gex(chain, spot)

    # per-strike call / put split, on the same gamma and OI the engine used
    cols = _normalize_chain(chain)
    g = pd.to_numeric(chain[cols["gamma"]], errors="coerce") if cols["gamma"] else None
    gamma = (g.fillna(0.0).to_numpy() if g is not None and g.notna().any() and (g.abs() > 0).any()
             else _compute_gamma_column(chain, cols, spot, 0.045))
    oi = pd.to_numeric(chain[cols["oi"]], errors="coerce").fillna(0.0).to_numpy() if cols["oi"] else np.zeros(len(chain))
    is_call = chain[cols["type"]].astype(str).str.lower().str.startswith("c").to_numpy()
    per = gamma * oi * 100 * spot * spot * _GEX_NOTIONAL_SCALE
    df = pd.DataFrame({"strike": pd.to_numeric(chain[cols["strike"]], errors="coerce"),
                       "call_gex": np.where(is_call, per, 0.0), "put_gex": np.where(~is_call, -per, 0.0),
                       "call_oi": np.where(is_call, oi, 0.0), "put_oi": np.where(~is_call, oi, 0.0)})
    agg = df.groupby("strike", as_index=False).sum().sort_values("strike")
    agg["net_gex"] = agg["call_gex"] + agg["put_gex"]
    agg = agg[["strike", "call_gex", "put_gex", "net_gex", "call_oi", "put_oi"]]
    table = table_from_df(agg, headers={"strike": "Strike", "call_gex": "Call GEX", "put_gex": "Put GEX",
                                        "net_gex": "Net GEX", "call_oi": "Call OI", "put_oi": "Put OI"},
                          formats={"strike": "price", "call_gex": "money", "put_gex": "money",
                                   "net_gex": "money", "call_oi": "int", "put_oi": "int"})
    flip, regime_, flip_note = flip_and_regime(snap)
    if flip_note:
        notes.append(flip_note)

    # per-expiry split (dealer-signed, same notional)
    exp_col = cols.get("expiry") or ("expiry" if "expiry" in chain.columns else None)
    by_expiry = None
    if exp_col is not None:
        ex = pd.DataFrame({"expiry": pd.to_datetime(chain[exp_col], errors="coerce").dt.date,
                           "call_gex": np.where(is_call, per, 0.0), "put_gex": np.where(~is_call, -per, 0.0),
                           "oi": oi})
        ex = ex.dropna(subset=["expiry"]).groupby("expiry", as_index=False).sum().sort_values("expiry")
        ex["net_gex"] = ex["call_gex"] + ex["put_gex"]
        ex["dte"] = [(d - (asof if isinstance(asof, _dt.date) else _dt.date.today())).days for d in ex["expiry"]]
        by_expiry = table_from_df(ex[["expiry", "dte", "call_gex", "put_gex", "net_gex", "oi"]],
                                  headers={"expiry": "Expiry", "dte": "DTE", "call_gex": "Call GEX", "put_gex": "Put GEX",
                                           "net_gex": "Net GEX", "oi": "Open interest"},
                                  formats={"call_gex": "money", "put_gex": "money", "net_gex": "money", "oi": "int", "dte": "int"})

    try:
        from analytics.gex_engine import classify_regime, compute_max_pain
        regime = regime_
        max_pain = float(compute_max_pain(chain, spot))
    except Exception:
        regime, max_pain = "unknown", None

    return to_jsonable({
        "ticker": ticker, "underlying": und, "root": root, "spot": spot, "flip": flip, "table": table,
        "asof": asof, "source": source, "net_gex": snap.net_gex, "call_gex": snap.call_gex,
        "put_gex": snap.put_gex, "call_wall": snap.call_wall, "put_wall": snap.put_wall,
        "net_gex_0dte": snap.net_gex_0dte, "dist_to_flip_pct": snap.dist_to_flip_pct,
        "units": "$ per 1% move (dealer-signed)", "contracts": int(len(chain)),
        "regime": regime, "max_pain": max_pain, "by_expiry": by_expiry,
        "profile": _gex_profile(chain, cols, spot, gamma_fallback=gamma, oi=oi, is_call=is_call),
        "warnings": list(snap.warnings) + notes,
    })


def _gex_profile(chain: pd.DataFrame, cols: dict, spot: float, *, gamma_fallback, oi, is_call,
                 r: float = 0.045, span: float = 0.10, n: int = 61) -> Optional[dict]:
    """Dealer net GEX if spot moved to S (spot ±10%), with each contract's gamma recomputed at S (Black–Scholes on its
    own IV and time to expiry). Where it crosses zero is where dealer hedging flips from damping to amplifying moves."""
    iv_col, dte_col = cols.get("iv"), cols.get("dte")
    if iv_col is None or dte_col is None:
        return None
    k = pd.to_numeric(chain[cols["strike"]], errors="coerce").to_numpy(dtype=float)
    iv = pd.to_numeric(chain[iv_col], errors="coerce").to_numpy(dtype=float)
    t = np.maximum(pd.to_numeric(chain[dte_col], errors="coerce").to_numpy(dtype=float), 0.5) / 365.0
    ok = np.isfinite(k) & np.isfinite(iv) & (iv > 0) & (k > 0) & (oi > 0)
    if ok.sum() < 10:
        return None
    k, iv, t, w = k[ok], iv[ok], t[ok], np.where(is_call[ok], 1.0, -1.0) * oi[ok]
    s = np.linspace(spot * (1 - span), spot * (1 + span), n)
    sqrt_t = np.sqrt(t)
    out = []
    for S in s:
        d1 = (np.log(S / k) + (r + 0.5 * iv * iv) * t) / (iv * sqrt_t)
        gamma = np.exp(-0.5 * d1 * d1) / (math.sqrt(2 * math.pi) * S * iv * sqrt_t)
        out.append(float(np.sum(w * gamma) * 100 * S * S * _GEX_NOTIONAL_SCALE_PROFILE))
    return {"s": [round(float(x), 4) for x in s], "gex": out}


_GEX_NOTIONAL_SCALE_PROFILE = 0.01   # $ per 1% move, as analytics.gex_engine
