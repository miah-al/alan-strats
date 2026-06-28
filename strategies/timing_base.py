"""
Shared helpers for the equity-timing strategies (trend-following, momentum).

These overlays own a single liquid index when "in", cash when "out". The pieces
common to both — data loading, the equity simulation, and turning an in/out
position series into discrete trades — live here so each strategy file holds only
its own signal rule (one Strategy class per file, matching the slug).
"""
from __future__ import annotations

import pandas as pd

_TRADING_DAYS = 252


def load_close(ticker: str, n_days: int = 7500) -> pd.Series:
    """Real daily closes from yfinance, date-indexed (deduped, sorted)."""
    from alan_trader.data.stock_data import yf_daily_bars
    df = yf_daily_bars(ticker, n_days=n_days)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    s = pd.Series(df["close"].values, index=pd.to_datetime(df["date"])).sort_index()
    return s[~s.index.duplicated(keep="last")]


def equity_from_position(close: pd.Series, pos: pd.Series,
                         cash_yield: float, starting_capital: float) -> pd.Series:
    """pos ∈ [0,1] per day (already shifted to avoid look-ahead). Days out of the
    market earn the daily cash yield."""
    ret = close.pct_change()
    cash_daily = cash_yield / _TRADING_DAYS
    strat_ret = pos * ret + (1.0 - pos) * cash_daily
    return starting_capital * (1.0 + strat_ret.fillna(0.0)).cumprod()


def episodes_to_trades(close: pd.Series, pos: pd.Series) -> pd.DataFrame:
    """Turn an in/out position series into discrete long episodes (a 'trade' = one
    stretch of being long), with real entry/exit prices and % P&L."""
    rows = []
    in_pos = False
    entry_d = entry_px = None
    for d, p in pos.items():
        long_now = p > 0
        if long_now and not in_pos:
            in_pos, entry_d, entry_px = True, d, float(close.loc[d])
        elif not long_now and in_pos:
            exit_px = float(close.loc[d])
            pnl_pct = (exit_px / entry_px - 1.0) * 100.0
            rows.append({"entry_date": entry_d.date(), "exit_date": d.date(),
                         "entry_px": round(entry_px, 2), "exit_px": round(exit_px, 2),
                         "pnl": round(pnl_pct, 2), "winner": pnl_pct > 0})
            in_pos = False
    if in_pos and entry_d is not None:   # still open at end
        exit_px = float(close.iloc[-1])
        pnl_pct = (exit_px / entry_px - 1.0) * 100.0
        rows.append({"entry_date": entry_d.date(), "exit_date": close.index[-1].date(),
                     "entry_px": round(entry_px, 2), "exit_px": round(exit_px, 2),
                     "pnl": round(pnl_pct, 2), "winner": pnl_pct > 0})
    return pd.DataFrame(rows)


def close_from_inputs(price_data, ticker: str) -> pd.Series:
    """Prefer the DB price_data passed by the Backtest tab; fall back to yfinance."""
    if price_data is not None and not price_data.empty and "close" in price_data.columns:
        s = price_data.copy()
        s.index = pd.to_datetime(s.index)
        return pd.Series(s["close"].astype(float).values, index=s.index).sort_index()
    return load_close(ticker)
