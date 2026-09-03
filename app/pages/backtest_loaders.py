"""
app/pages/backtest_loaders.py

Auxiliary-data loaders for the Backtest / Performance tabs.

Each loader is a pure function:

    loader(engine, ticker, fd, td, *, price_data, label, **options) -> LoaderResult

LoaderResult is a small dataclass with two fields:
  - aux_updates : dict to merge into auxiliary_data, OR None on failure
  - alert       : a dash_bootstrap_components.Alert to surface to the user
                  (e.g. "no earnings data found, sync first") OR None to
                  proceed silently. If alert is non-None and is_blocking is
                  True, the dispatcher should return it instead of running
                  the backtest.

Which loaders run for a strategy is declared by the strategy plugin
(``StrategyUI.loaders()`` → metadata ``loaders``), as a list of loader names
or ``(name, options)`` pairs. The platform knows the loaders, never the
strategies. Final reshaping of the auxiliary dict for a particular strategy is
the plugin's job (``StrategyUI.prepare_aux``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pandas as pd
import dash_bootstrap_components as dbc
from dash import html
from sqlalchemy import text as sql_text

logger = logging.getLogger(__name__)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class LoaderResult:
    aux_updates:  dict = field(default_factory=dict)
    alert:        Optional[object] = None  # dbc.Alert or None
    is_blocking:  bool = False             # if True, dispatcher returns alert and skips backtest


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_option_snapshots(engine, ticker, fd, td, *, price_data, label, **_):
    """Load OptionSnapshot rows from `mkt.OptionSnapshot`.

    Required by every options-chain-driven strategy. Empty result blocks
    the backtest with a friendly Alert pointing to Tools → Data Manager.
    """
    try:
        from db.client import get_ticker_id

        tid = get_ticker_id(engine, ticker)
        if tid is None:
            df = pd.DataFrame()
        else:
            with engine.connect() as conn:
                rows = conn.execute(sql_text("""
                    SELECT s.SnapshotDate, s.Strike AS StrikePrice,
                           s.ContractType AS OptionType, s.ImpliedVol AS iv,
                           s.OpenInterest, s.Delta, s.Gamma, s.Bid, s.Ask,
                           DATEDIFF(day, s.SnapshotDate, s.ExpirationDate) AS DTE,
                           s.ExpirationDate
                    FROM   mkt.OptionSnapshot s
                    WHERE  s.TickerId = :tid
                      AND  s.SnapshotDate BETWEEN :f AND :t
                    ORDER  BY s.SnapshotDate, s.ExpirationDate, s.Strike
                """), {"tid": tid, "f": fd, "t": td}).fetchall()
            cols = ["SnapshotDate", "StrikePrice", "OptionType", "iv",
                    "OpenInterest", "Delta", "Gamma", "Bid", "Ask",
                    "DTE", "ExpirationDate"]
            df = pd.DataFrame(rows, columns=cols)
    except Exception as exc:
        logger.warning(f"{label}: option_snapshots load failed: {exc}")
        df = pd.DataFrame()

    if df.empty:
        alert = dbc.Alert([
            html.Strong(f"{label} requires options chain data. "), html.Br(),
            f"No OptionSnapshot rows found for {ticker!r} in the selected window. ",
            "Sync options data first via Tools → Data Manager → Options.",
        ], color="warning")
        return LoaderResult(aux_updates={"option_snapshots": df},
                            alert=alert, is_blocking=True)
    return LoaderResult(aux_updates={"option_snapshots": df})


def load_sector_etfs(engine, ticker, fd, td, *, price_data, label,
                     tickers: list[str], min_count: int = 3, key: str = "sectors", **_):
    """Load a basket of ETF price series (e.g. the 11 SPDR sectors) under `key`."""
    from db.client import get_price_bars

    sectors: dict[str, pd.DataFrame] = {}
    for etf in tickers:
        try:
            df = get_price_bars(engine, etf, fd, td)
            if not df.empty:
                df.index = pd.to_datetime(df["date"])
                sectors[etf] = df
        except Exception:
            pass

    if len(sectors) < min_count:
        missing = [e for e in tickers if e not in sectors]
        alert = dbc.Alert([
            html.Strong(f"{label} requires ETF basket data. "), html.Br(),
            f"Found {len(sectors)}/{len(tickers)} ETFs in DB. "
            "Please sync these tickers first: ",
            html.Code(", ".join(missing)),
        ], color="warning")
        return LoaderResult(aux_updates={key: sectors},
                            alert=alert, is_blocking=True)
    return LoaderResult(aux_updates={key: sectors})


def load_earnings_calendar(engine, ticker, fd, td, *, price_data, label,
                           optional: bool = False, as_series: bool = False,
                           stock_prices: bool = False, **_):
    """Load earnings rows from mkt.Earnings.

    Date precedence inside the loader: AnnouncementDate (Alpha Vantage
    reportedDate) ▸ FiledDate (SEC filing) ▸ PeriodOfReport (fiscal end).

    Output mounted under TWO keys:
      - earnings_calendar : DataFrame (or, with ``as_series``, a 1.0-valued
                            Series indexed by release_date)
      - earnings          : the DataFrame (legacy key)

    Options:
      optional      missing data does not block the backtest
      stock_prices  also mount {TICKER: price_data} under 'stock_prices'
    """
    try:
        from db.client import get_earnings_calendar as _get
        ec_df = _get(engine, ticker, fd, td)
    except Exception as exc:
        logger.warning(f"{label}: earnings_calendar load failed: {exc}")
        ec_df = pd.DataFrame()

    if ec_df.empty and not optional:
        alert = dbc.Alert([
            html.Strong(f"{label} requires earnings calendar data. "), html.Br(),
            f"No earnings rows found for {ticker!r} in the selected window. ",
            "Sync via Tools → Data Manager → Earnings + EPS Estimates ",
            "(EPS Estimates populates the announcement date used for trade timing).",
        ], color="warning")
        return LoaderResult(alert=alert, is_blocking=True)

    aux: dict = {"earnings_calendar": ec_df, "earnings": ec_df}

    if as_series and not ec_df.empty:
        aux["earnings_calendar"] = pd.Series(
            1.0, index=pd.to_datetime(ec_df["release_date"])
        )

    if stock_prices:
        aux["stock_prices"] = {ticker.upper(): price_data}

    return LoaderResult(aux_updates=aux)


def load_news_sentiment(engine, ticker, fd, td, *, price_data, label, **_):
    """Daily-aggregated news sentiment under 'news_sentiment'.

    Missing data is non-blocking — strategies run in degenerate-fallback mode
    when sentiment is empty.
    """
    try:
        from db.client import get_news_sentiment_daily
        ns_df = get_news_sentiment_daily(engine, ticker, fd, td)
    except Exception as exc:
        logger.warning(f"{label}: news_sentiment load failed: {exc}")
        ns_df = pd.DataFrame()
    return LoaderResult(aux_updates={"news_sentiment": ns_df})


def load_short_interest_and_spy(engine, ticker, fd, td, *, price_data, label, **_):
    """Optional short-interest data + SPY market-context.

    Both are optional. Missing SI → the strategy falls back to an options-only
    model. Missing SPY → market-context features default to 0.
    """
    aux: dict = {}

    try:
        from db.client import get_short_interest
        si_df = get_short_interest(engine, ticker, fd, td)
    except Exception as exc:
        logger.warning(f"{label}: short_interest load failed: {exc}")
        si_df = pd.DataFrame()
    aux["short_interest"] = si_df

    if ticker.upper() != "SPY":
        try:
            from db.client import get_price_bars
            spy_df = get_price_bars(engine, "SPY", fd, td)
            if not spy_df.empty:
                spy_df.index = pd.to_datetime(spy_df["date"])
                aux["spy_price"] = spy_df
        except Exception:
            pass

    return LoaderResult(aux_updates=aux)


def _atm_iv_series(engine, ticker, fd, td, spot, dte_lo=7, dte_hi=21) -> pd.Series:
    """Daily ATM implied vol from mkt.OptionSnapshot: per snapshot date, the
    median real reconstructed IV of the strikes nearest spot, within [dte_lo,
    dte_hi] DTE. Returns an empty Series if no usable IV. (No proxy: pure chain
    IV. NB: this reconstructed IV is noisy — see the strategy guides.)"""
    try:
        from db.client import get_ticker_id
        tid = get_ticker_id(engine, ticker)
        if tid is None:
            return pd.Series(dtype=float)
        with engine.connect() as conn:
            rows = conn.execute(sql_text("""
                SELECT s.SnapshotDate, s.Strike, s.ImpliedVol,
                       DATEDIFF(day, s.SnapshotDate, s.ExpirationDate) AS DTE
                FROM   mkt.OptionSnapshot s
                WHERE  s.TickerId = :tid
                  AND  s.SnapshotDate BETWEEN :f AND :t
                  AND  s.ImpliedVol IS NOT NULL
            """), {"tid": tid, "f": fd, "t": td}).fetchall()
    except Exception as exc:
        logger.warning(f"atm_iv load failed for {ticker}: {exc}")
        return pd.Series(dtype=float)
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["date", "strike", "iv", "dte"])
    df["date"] = pd.to_datetime(df["date"])
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df["iv"] = pd.to_numeric(df["iv"], errors="coerce")
    df = df[(df["dte"] >= dte_lo) & (df["dte"] <= dte_hi)
            & (df["iv"] > 0.01) & (df["iv"] < 3.0)].dropna(subset=["strike", "iv"])
    if df.empty:
        return pd.Series(dtype=float)
    sp = pd.Series(spot).copy()
    sp.index = pd.to_datetime(sp.index)
    out: dict = {}
    for d, g in df.groupby("date"):
        s = sp.reindex([d]).ffill()
        s = float(s.iloc[0]) if len(s) and np.isfinite(s.iloc[0]) else float(g["strike"].median())
        near = (g["strike"] - s).abs().nsmallest(6).index
        out[d] = float(g.loc[near, "iv"].median())
    return pd.Series(out).sort_index()


def load_atm_iv(engine, ticker, fd, td, *, price_data, label, **_):
    """Supply the real reconstructed ATM-IV series under 'atm_iv'.
    Blocks with a friendly Alert if no option IV exists for the ticker/window."""
    spot = price_data["close"] if "close" in getattr(price_data, "columns", []) else price_data.iloc[:, 0]
    iv = _atm_iv_series(engine, ticker, fd, td, spot)
    if iv.dropna().empty:
        alert = dbc.Alert([
            html.Strong(f"{label} requires reconstructed option IV. "), html.Br(),
            f"No usable ImpliedVol rows in mkt.OptionSnapshot for {ticker!r} in the "
            "selected window. Sync options first via Tools → Data Manager → Options.",
        ], color="warning")
        return LoaderResult(aux_updates={"atm_iv": iv}, alert=alert, is_blocking=True)
    return LoaderResult(aux_updates={"atm_iv": iv})


def load_macro(engine, ticker, fd, td, *, price_data, label, **_):
    """Mount the treasury-yield macro panel under 'macro'.

    get_macro_bars already returns feature-ready columns (rate_2y, rate_10y,
    rate_3m, rate_5y, …) indexed by date. The default backtest path mounts this
    frame under 'rate10y' only; strategies that read it under 'macro' declare
    this loader.
    """
    try:
        from db.client import get_macro_bars
        macro = get_macro_bars(engine, fd, td)
    except Exception as exc:
        logger.warning(f"{label}: macro load failed: {exc}")
        macro = pd.DataFrame()

    if macro is None or macro.empty:
        alert = dbc.Alert([
            html.Strong(f"{label} requires treasury-yield macro data. "), html.Br(),
            "No mkt.MacroBar rows found in the selected window. ",
            "Sync via Tools → Data Manager → Macro / Treasury.",
        ], color="warning")
        return LoaderResult(alert=alert, is_blocking=True)
    macro = macro.copy()
    macro.index = pd.to_datetime(macro.index)
    return LoaderResult(aux_updates={"macro": macro})


def load_stock_bond_iv(engine, ticker, fd, td, *, price_data, label,
                       bond_ticker: str = "TLT", **_):
    """Supply bond-leg prices + both equity & bond real ATM-IV series for a
    stock/bond rotation. Expects the selected ticker to be the equity leg;
    its IV is computed from price_data, the bond leg is loaded explicitly."""
    from db.client import get_price_bars
    spy_spot = price_data["close"] if "close" in getattr(price_data, "columns", []) else price_data.iloc[:, 0]
    iv_spy = _atm_iv_series(engine, ticker, fd, td, spy_spot)

    try:
        tlt_df = get_price_bars(engine, bond_ticker, fd, td)
    except Exception as exc:
        logger.warning(f"{label}: {bond_ticker} price load failed: {exc}")
        tlt_df = pd.DataFrame()
    if tlt_df is None or tlt_df.empty:
        return LoaderResult(alert=dbc.Alert([
            html.Strong(f"{label} requires {bond_ticker} price data. "), html.Br(),
            f"No {bond_ticker} PriceBar rows in the selected window. Sync it via Tools → Data Manager.",
        ], color="warning"), is_blocking=True)
    tlt_df = tlt_df.copy()
    tlt_df.index = pd.to_datetime(tlt_df["date"]) if "date" in tlt_df.columns else pd.to_datetime(tlt_df.index)
    iv_tlt = _atm_iv_series(engine, bond_ticker, fd, td, tlt_df["close"])

    if iv_spy.dropna().empty or iv_tlt.dropna().empty:
        missing = ticker if iv_spy.dropna().empty else bond_ticker
        return LoaderResult(alert=dbc.Alert([
            html.Strong(f"{label} requires option IV for BOTH legs. "),
            html.Br(), f"No reconstructed ATM IV found for {missing} in the selected "
            "window. Sync its options via Tools → Data Manager → Options.",
        ], color="warning"), is_blocking=True)
    return LoaderResult(aux_updates={"tlt": tlt_df, "atm_iv_spy": iv_spy, "atm_iv_tlt": iv_tlt})


# ── Loader registry ───────────────────────────────────────────────────────────

LoaderFn = Callable[..., LoaderResult]

LOADERS: dict[str, LoaderFn] = {
    "option_snapshots":       load_option_snapshots,
    "sector_etfs":            load_sector_etfs,
    "earnings_calendar":      load_earnings_calendar,
    "news_sentiment":         load_news_sentiment,
    "short_interest_and_spy": load_short_interest_and_spy,
    "atm_iv":                 load_atm_iv,
    "macro":                  load_macro,
    "stock_bond_iv":          load_stock_bond_iv,
}


def parse_loader_spec(spec) -> tuple[str, dict]:
    """Normalise a loader spec (``"name"`` or ``("name", {...})``)."""
    if isinstance(spec, str):
        return spec, {}
    name, opts = spec
    return str(name), dict(opts or {})


def run_loaders_for(slug: str, engine, ticker: str, fd, td, *, price_data):
    """Run every loader the strategy declares, merging aux_updates and
    surfacing the first blocking alert.

    Returns:
      (aux_data: dict, blocking_alert: dbc.Alert | None)

    The caller uses `blocking_alert` if non-None and skips the backtest.
    """
    from alan_trader.strategy_api.registry import get_ui
    ui = get_ui(slug)
    aux: dict = {}
    for spec in ui.loaders():
        name, opts = parse_loader_spec(spec)
        fn = LOADERS.get(name)
        if fn is None:
            logger.warning(f"{slug}: unknown loader {name!r} — skipped")
            continue
        result = fn(engine, ticker, fd, td, price_data=price_data, label=ui.label, **opts)
        aux.update(result.aux_updates)
        if result.is_blocking and result.alert is not None:
            return aux, result.alert
    aux = ui.prepare_aux(aux, ticker, price_data)
    return aux, None
