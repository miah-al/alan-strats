"""
app/pages/strategies/data_fetch.py — shared market-data fetch helpers.

Leaf module (no callbacks). Holds the VIX / OHLCV / IV fetches every screener
scan needs. Strategy-specific chain lookups and payoff previews live with the
strategies, in their plugin UI modules.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.pages.strategies.registry import _UNIVERSE_TICKERS


def _get_vix_series(api_key: str | None = None):
    """Load VIX close series — DB first, Polygon fallback."""
    # Try DB first
    try:
        from db.client import get_engine, get_vix_bars
        engine = get_engine()
        vix_df = get_vix_bars(engine, date.today() - timedelta(days=400), date.today())
        if not vix_df.empty:
            return vix_df["close"].astype(float)
    except Exception:
        pass

    # Polygon fallback — fetch VIX as a ticker (^VIX / VIXW)
    if api_key:
        try:
            from engine.screener import _fetch_ohlcv
            for sym in ["I:VIX", "VIX"]:
                df = _fetch_ohlcv(sym, api_key, bars=400)
                if not df.empty and "close" in df.columns:
                    return df["close"].astype(float)
        except Exception:
            pass

    return None


def _resolve_tickers(universe: str, custom: str | None) -> list[str]:
    # If user typed anything in the custom field, always use it (overrides dropdown)
    if custom and custom.strip():
        return [t.strip().upper() for t in custom.split(",") if t.strip()]
    return _UNIVERSE_TICKERS.get(universe, [])


def _fetch_data(tickers: list[str], api_key: str):
    """Returns (vix_series, price_dfs, iv_all). Raises on fatal error."""
    from engine.screener import _fetch_ohlcv
    from engine.iv_metrics import get_iv_metrics_batch

    vix_series = _get_vix_series(api_key)
    if vix_series is None:
        raise RuntimeError("No VIX data available (DB offline and Polygon VIX fetch failed).")

    price_dfs: dict = {}
    for ticker in tickers:
        df = _fetch_ohlcv(ticker, api_key)
        if not df.empty:
            price_dfs[ticker] = df

    if not price_dfs:
        raise RuntimeError("No price data returned for any ticker. Check API key.")

    iv_all = get_iv_metrics_batch(
        tickers=list(price_dfs.keys()),
        api_key=api_key,
        price_dfs=price_dfs,
    )
    return vix_series, price_dfs, iv_all
