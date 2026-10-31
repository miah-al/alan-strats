"""
app/pages/strategies/data_fetch.py — shared market-data fetch helpers.

Leaf module (no callbacks). The VIX / OHLCV / IV fetches every screener scan
needs now live in the headless ``engine.strategy_scan`` (shared with the service
API); these are the page's historical names for them. Strategy-specific chain
lookups and payoff previews live with the strategies, in their plugin UI modules.
"""
from __future__ import annotations

from engine.strategy_scan import (  # noqa: F401  (re-exported under the page's names)
    UNIVERSE_TICKERS as _UNIVERSE_TICKERS,
    get_vix_series as _get_vix_series,
    resolve_tickers as _resolve_tickers,
)


def _fetch_data(tickers: list[str], api_key: str):
    """Returns (vix_series, price_dfs, iv_all). Raises on fatal error."""
    from engine.strategy_scan import fetch_scan_data
    return fetch_scan_data(tickers, api_key)
