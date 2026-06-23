"""
data/stock_data.py — yfinance-backed stock data (quotes, daily bars, intraday).

Free, no per-minute cap, and includes intraday — used for the *stock* side of the
app. Polygon is kept for *options* analytics (greeks/IV/chains), which is the data
that's hard to get cheaply. yfinance is ~15-min delayed and unofficial, which is
fine for this dashboard.

All helpers return frames/dicts in the same shape the Polygon helpers used, so the
callbacks didn't need to change their downstream logic.
"""
from __future__ import annotations

import datetime as _dt
import logging

import pandas as pd

logger = logging.getLogger(__name__)


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten yfinance columns to lowercase open/high/low/close/volume."""
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    return df


def _add_date_col(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index()
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    dcol = next((c for c in ("date", "datetime", "index") if c in df.columns), df.columns[0])
    df["date"] = pd.to_datetime(df[dcol]).dt.date
    return df


def yf_daily_bars(ticker: str, n_days: int = 504) -> pd.DataFrame:
    """Daily OHLCV with a 'date' column and a vwap proxy. Empty frame on failure."""
    import yfinance as yf
    days  = int(max(n_days, 5) * 1.5) + 10
    start = (_dt.date.today() - _dt.timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        raw = yf.download(ticker, start=start, interval="1d",
                          auto_adjust=True, progress=False, threads=False)
    except Exception as e:
        logger.warning("yf daily %s failed: %s", ticker, e)
        return pd.DataFrame()
    raw = _normalize_ohlcv(raw)
    if raw.empty:
        return pd.DataFrame()
    raw = _add_date_col(raw)
    if "vwap" not in raw.columns:
        raw["vwap"] = raw[["high", "low", "close"]].mean(axis=1)
    cols = [c for c in ("date", "open", "high", "low", "close", "volume", "vwap") if c in raw.columns]
    return raw[cols].dropna(subset=["close"]).reset_index(drop=True)


def yf_intraday(ticker: str) -> pd.DataFrame:
    """Today's 1-minute bars with a tz-aware 'datetime' column (America/New_York)."""
    import yfinance as yf
    try:
        raw = yf.download(ticker, period="1d", interval="1m",
                          auto_adjust=True, progress=False, threads=False)
    except Exception as e:
        logger.warning("yf intraday %s failed: %s", ticker, e)
        return pd.DataFrame()
    raw = _normalize_ohlcv(raw)
    if raw.empty:
        return pd.DataFrame()
    raw = raw.reset_index()
    raw = raw.rename(columns={c: str(c).lower() for c in raw.columns})
    tcol = next((c for c in ("datetime", "date", "index") if c in raw.columns), raw.columns[0])
    dt = pd.to_datetime(raw[tcol])
    try:
        dt = dt.dt.tz_localize("UTC") if dt.dt.tz is None else dt
        dt = dt.dt.tz_convert("America/New_York")
    except Exception:
        pass
    raw["datetime"] = dt
    if "vwap" not in raw.columns:
        raw["vwap"] = raw[["high", "low", "close"]].mean(axis=1)
    cols = [c for c in ("datetime", "open", "high", "low", "close", "volume", "vwap") if c in raw.columns]
    return raw[cols].dropna(subset=["close"]).reset_index(drop=True)


def _fi_get(fi, *names):
    for n in names:
        try:
            v = getattr(fi, n)
            if v is not None:
                return v
        except Exception:
            pass
        try:
            v = fi[n]
            if v is not None:
                return v
        except Exception:
            pass
    return None


def yf_quote(ticker: str) -> dict | None:
    """Normalized quote (same shape as the old Polygon _fetch_quote).

    Uses yfinance fast_info for a live-ish (≈15-min delayed) price during the
    session, falling back to the last daily bar. Returns None if nothing loads.
    """
    import yfinance as yf
    close = open_ = high = low = prev_c = None
    vol = 0
    live = False
    try:
        fi = yf.Ticker(ticker).fast_info
        close  = _fi_get(fi, "last_price", "lastPrice")
        prev_c = _fi_get(fi, "previous_close", "previousClose")
        open_  = _fi_get(fi, "open")
        high   = _fi_get(fi, "day_high", "dayHigh")
        low    = _fi_get(fi, "day_low", "dayLow")
        vol    = _fi_get(fi, "last_volume", "lastVolume") or 0
        close  = float(close) if close else None
        prev_c = float(prev_c) if prev_c else None
        live   = close is not None
    except Exception as e:
        logger.warning("yf fast_info %s failed: %s", ticker, e)

    asof = _dt.date.today().isoformat()
    if not close or not prev_c:
        df = yf_daily_bars(ticker, 10)
        if df.empty:
            return None
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else None
        if not close:
            close = float(last["close"]); open_ = float(last["open"])
            high = float(last["high"]); low = float(last["low"])
            vol = int(last["volume"]); live = False
            asof = str(last["date"])
        if not prev_c:
            prev_c = float(prev["close"]) if prev is not None else float(last["close"])

    chg     = (close - prev_c) if (close and prev_c) else 0.0
    chg_pct = (chg / prev_c * 100) if prev_c else 0.0
    return {
        "close": float(close or 0), "open": float(open_ or 0),
        "high": float(high or 0), "low": float(low or 0),
        "volume": int(vol or 0), "vwap": 0.0,
        "prev_close": float(prev_c or 0), "change": chg, "change_pct": chg_pct,
        "asof": asof, "live": bool(live),
    }


def yf_stock_price(ticker: str) -> float | None:
    """Latest available price for a single symbol (fast_info → last daily close)."""
    q = yf_quote(ticker)
    return q["close"] if q and q.get("close") else None


def yf_batch_daily(tickers: list[str], n_days: int = 60) -> dict[str, pd.DataFrame]:
    """Daily OHLCV for many tickers in one download. {ticker: DataFrame(date,ohlcv)}.

    One network call for the whole universe — the screener's biggest win vs. the
    old per-ticker Polygon fan-out against the 5/min cap.
    """
    import yfinance as yf
    tickers = list(tickers)
    if not tickers:
        return {}
    days  = int(max(n_days, 5) * 1.7) + 10
    start = (_dt.date.today() - _dt.timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        raw = yf.download(tickers, start=start, interval="1d", auto_adjust=True,
                          progress=False, threads=True, group_by="ticker")
    except Exception as e:
        logger.warning("yf batch daily failed: %s", e)
        return {}
    if raw is None or raw.empty:
        return {}
    multi = isinstance(raw.columns, pd.MultiIndex)
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            sub = raw[t].copy() if multi else raw.copy()
            sub = _normalize_ohlcv(sub)
            if sub.empty:
                continue
            sub = _add_date_col(sub)
            cols = [c for c in ("date", "open", "high", "low", "close", "volume") if c in sub.columns]
            sub = sub[cols].dropna(subset=["close"]).reset_index(drop=True)
            if not sub.empty:
                out[t] = sub
        except Exception:
            continue
    return out
