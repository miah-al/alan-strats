"""
app/pages/backtest_loaders.py — the Dash side of the backtest auxiliary-data loaders.

The loaders themselves are headless and live in ``engine/backtest_loaders.py`` (the service's
backtest jobs use them too). This module re-exports them for the Backtest / Performance tabs
and turns a loader's headless ``LoaderAlert`` into the ``dbc.Alert`` the page shows.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from engine import backtest_loaders as _headless
from engine.backtest_loaders import (  # noqa: F401  (re-exported for the pages and scripts)
    BR, LOADERS, Code, LoaderAlert, LoaderFn, LoaderResult, Strong, parse_loader_spec,
    load_atm_iv, load_daily_close, load_earnings_calendar, load_event_calendar, load_macro,
    load_minute_bars, load_news_sentiment, load_option_minute_bars, load_option_snapshots,
    load_sector_etfs, load_short_interest_and_spy, load_stock_bond_iv,
)


def to_dash_alert(alert: LoaderAlert | None):
    """A loader's headless alert as the dbc.Alert the page has always rendered."""
    if alert is None:
        return None
    parts = []
    for part in alert.children:
        if isinstance(part, Strong):
            parts.append(html.Strong(part.children))
        elif isinstance(part, Code):
            parts.append(html.Code(part.children))
        elif part is BR:
            parts.append(html.Br())
        else:
            parts.append(part)
    return dbc.Alert(parts, color=alert.color)


def run_loaders_for(slug: str, engine, ticker: str, fd, td, *, price_data):
    """``engine.backtest_loaders.run_loaders_for`` with the blocking alert rendered for Dash.

    Returns:
      (aux_data: dict, blocking_alert: dbc.Alert | None)
    """
    aux, block = _headless.run_loaders_for(slug, engine, ticker, fd, td, price_data=price_data)
    return aux, to_dash_alert(block)
