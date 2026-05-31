"""
app/pages/backtest_loaders.py

Per-strategy auxiliary-data loaders for the Backtest tab.

Extracted from `strategies.py:3264-3406`. Each loader is a pure function:

    loader(engine, ticker, fd, td, *, price_data) -> LoaderResult

LoaderResult is a small NamedTuple with two fields:
  - aux_updates : dict to merge into auxiliary_data, OR None on failure
  - alert       : a dash_bootstrap_components.Alert to surface to the user
                  (e.g. "no earnings data found, sync first") OR None to
                  proceed silently. If alert is non-None and is_blocking is
                  True, the dispatcher should return it instead of running
                  the backtest.

Each loader is responsible for:
  - logging warnings on transient failures (DB unreachable, no rows)
  - returning a friendly Alert when required data is missing
  - shaping the data into the form the strategy expects under the right
    auxiliary_data key

LOADERS_BY_SLUG maps each slug to a list of loaders to run in order. The
dispatcher iterates the list, merging aux_updates and surfacing the first
blocking alert.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

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

def load_option_snapshots(engine, ticker, fd, td, *, price_data, slug):
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
        logger.warning(f"{slug}: option_snapshots load failed: {exc}")
        df = pd.DataFrame()

    if df.empty:
        alert = dbc.Alert([
            html.Strong(f"{slug} requires options chain data. "), html.Br(),
            f"No OptionSnapshot rows found for {ticker!r} in the selected window. ",
            "Sync options data first via Tools → Data Manager → Options.",
        ], color="warning")
        return LoaderResult(aux_updates={"option_snapshots": df},
                            alert=alert, is_blocking=True)
    return LoaderResult(aux_updates={"option_snapshots": df})


def load_sector_etfs(engine, ticker, fd, td, *, price_data, slug):
    """Load all 11 SPDR sector ETF price series for rs_credit_spread."""
    from db.client import get_price_bars
    from strategies.rs_credit_spread import SECTOR_ETFS

    sectors: dict[str, pd.DataFrame] = {}
    for etf in SECTOR_ETFS:
        try:
            df = get_price_bars(engine, etf, fd, td)
            if not df.empty:
                df.index = pd.to_datetime(df["date"])
                sectors[etf] = df
        except Exception:
            pass

    if len(sectors) < 3:
        missing = [e for e in SECTOR_ETFS if e not in sectors]
        alert = dbc.Alert([
            html.Strong("RS Credit Spread requires sector ETF data. "), html.Br(),
            f"Found {len(sectors)}/{len(SECTOR_ETFS)} sector ETFs in DB. "
            "Please sync these tickers first: ",
            html.Code(", ".join(missing)),
        ], color="warning")
        return LoaderResult(aux_updates={"sectors": sectors},
                            alert=alert, is_blocking=True)
    return LoaderResult(aux_updates={"sectors": sectors})


def load_earnings_calendar(engine, ticker, fd, td, *, price_data, slug):
    """Load earnings rows from mkt.Earnings.

    Date precedence inside the loader: AnnouncementDate (Alpha Vantage
    reportedDate) ▸ FiledDate (SEC filing) ▸ PeriodOfReport (fiscal end).

    Output mounted under TWO keys:
      - earnings_calendar : DataFrame (new strategies use this)
      - earnings          : same DataFrame (legacy earnings_iv_crush /
                            _post_drift / _vol_crush use this)

    For news_sentiment_nlp, earnings_calendar is replaced with a Series
    indexed by release_date (the strategy-specific format).
    """
    try:
        from db.client import get_earnings_calendar as _get
        ec_df = _get(engine, ticker, fd, td)
    except Exception as exc:
        logger.warning(f"{slug}: earnings_calendar load failed: {exc}")
        ec_df = pd.DataFrame()

    if ec_df.empty and slug != "news_sentiment_nlp":
        alert = dbc.Alert([
            html.Strong(f"{slug} requires earnings calendar data. "), html.Br(),
            f"No earnings rows found for {ticker!r} in the selected window. ",
            "Sync via Tools → Data Manager → Earnings + EPS Estimates ",
            "(EPS Estimates populates the announcement date used for trade timing).",
        ], color="warning")
        return LoaderResult(alert=alert, is_blocking=True)

    aux: dict = {"earnings_calendar": ec_df, "earnings": ec_df}

    # news_sentiment_nlp expects a Series, not a DataFrame
    if slug == "news_sentiment_nlp" and not ec_df.empty:
        aux["earnings_calendar"] = pd.Series(
            1.0, index=pd.to_datetime(ec_df["release_date"])
        )

    # Legacy earnings strategies look up per-ticker prices
    if slug in ("earnings_iv_crush", "earnings_post_drift", "earnings_vol_crush"):
        aux["stock_prices"] = {ticker.upper(): price_data}

    return LoaderResult(aux_updates=aux)


def load_news_sentiment(engine, ticker, fd, td, *, price_data, slug):
    """Daily-aggregated news sentiment for news_sentiment_nlp.

    Missing data is non-blocking — the strategy runs in degenerate-fallback
    mode when sentiment is empty (sentiment fixed at 0).
    """
    try:
        from db.client import get_news_sentiment_daily
        ns_df = get_news_sentiment_daily(engine, ticker, fd, td)
    except Exception as exc:
        logger.warning(f"{slug}: news_sentiment load failed: {exc}")
        ns_df = pd.DataFrame()
    return LoaderResult(aux_updates={"news_sentiment": ns_df})


def load_short_interest_and_spy(engine, ticker, fd, td, *, price_data, slug):
    """Optional short-interest data + SPY market-context for
    short_squeeze_detector.

    Both are optional. Missing SI → strategy falls back to its 7-feature
    options-only model. Missing SPY → ret_spy_5d feature defaults to 0.
    """
    aux: dict = {}

    try:
        from db.client import get_short_interest
        si_df = get_short_interest(engine, ticker, fd, td)
    except Exception as exc:
        logger.warning(f"{slug}: short_interest load failed: {exc}")
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


# ── Per-slug loader registry ──────────────────────────────────────────────────

LoaderFn = Callable[..., LoaderResult]

LOADERS_BY_SLUG: dict[str, list[LoaderFn]] = {
    # Options-chain strategies
    "dealer_gamma_regime":          [load_option_snapshots],
    "gamma_flip_breakout":          [load_option_snapshots],
    "oi_imbalance_put_fade":        [load_option_snapshots],
    "short_squeeze_vol_expansion":  [load_option_snapshots],
    "iv_skew_momentum":             [load_option_snapshots],
    "vol_term_structure_regime":    [load_option_snapshots],
    "short_squeeze_detector":       [load_option_snapshots, load_short_interest_and_spy],

    # Sector-rotation
    "rs_credit_spread":             [load_sector_etfs],

    # Earnings strategies (note: load_news_sentiment is a no-op aux merge for
    # earnings strategies; only news_sentiment_nlp needs it)
    "earnings_pin_risk":            [load_earnings_calendar],
    "earnings_iv_crush":            [load_earnings_calendar],
    "earnings_post_drift":          [load_earnings_calendar],
    "earnings_vol_crush":           [load_earnings_calendar],
    "news_sentiment_nlp":           [load_earnings_calendar, load_news_sentiment],
}


def run_loaders_for(slug: str, engine, ticker: str, fd, td, *, price_data):
    """Run every loader registered for `slug`, merging aux_updates and
    surfacing the first blocking alert.

    Returns:
      (aux_data: dict, blocking_alert: dbc.Alert | None)

    The caller uses `blocking_alert` if non-None and skips the backtest.
    """
    aux: dict = {}
    for fn in LOADERS_BY_SLUG.get(slug, []):
        result = fn(engine, ticker, fd, td, price_data=price_data, slug=slug)
        aux.update(result.aux_updates)
        if result.is_blocking and result.alert is not None:
            return aux, result.alert
    return aux, None
