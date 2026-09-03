"""
app/pages/strategies/scan.py — screener scan engine + per-strategy scan callbacks.

`_run_scan` is generic: it resolves the universe, fetches prices / VIX / IV
metrics once, and hands a `ScanContext` to the strategy's UI hook
(`StrategyUI.scan`), then formats rows through `StrategyUI.display_row`.
Importing this module registers a scan callback set for every visible strategy.
"""
from __future__ import annotations

import logging

import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, State, no_update, ALL

from app import theme as T, get_polygon_api_key
from alan_trader.strategy_api.registry import get_ui
from alan_trader.strategy_api.ui import ScanContext
from app.pages.strategies.registry import slugs as _slugs
from app.pages.strategies.format import _vix_banner, _status_pills
from app.pages.strategies.data_fetch import _resolve_tickers, _fetch_data

logger = logging.getLogger(__name__)


def _run_scan(slug: str, universe: str, custom: str | None, api_key: str,
              param_overrides: dict | None = None):
    """
    Returns (row_data, status_children, vix_banner_children) or raises.
    All error handling is done by callers via try/except.
    """
    ui = get_ui(slug)

    # Locked-universe strategies ignore the universe/custom inputs
    if ui.locked_tickers:
        tickers = list(ui.locked_tickers)
    else:
        tickers = _resolve_tickers(universe, custom)
    if not tickers:
        return [], html.P("No tickers in universe.", style={"color": T.WARNING}), html.Div()

    vix_series, price_dfs, iv_all = _fetch_data(tickers, api_key)
    params = {**(ui.default_params or {}), **(param_overrides or {})}

    ctx = ScanContext(slug=slug, tickers=tickers, price_dfs=price_dfs,
                      vix_series=vix_series, iv_all=iv_all, api_key=api_key,
                      params=params)
    raw_rows = list(ui.scan(ctx) or [])
    display_rows = [ui.display_row(r) for r in raw_rows]

    # Sort by score descending
    display_rows.sort(
        key=lambda r: (r.get("Score") or 0) if isinstance(r.get("Score"), (int, float)) else 0,
        reverse=True,
    )

    status_div   = _status_pills(display_rows)
    vix_banner   = _vix_banner(vix_series, slug)

    # IVR fallback warning: if any ticker used VIX proxy instead of real options IVR
    ivr_fallback_count = sum(
        1 for r in raw_rows
        if str(r.get("ivr_confidence", "")).startswith("low")
    )
    if ivr_fallback_count > 0:
        ivr_warn = dbc.Alert(
            [
                html.Strong("IVR data quality warning: "),
                f"{ivr_fallback_count}/{len(raw_rows)} ticker(s) are using VIX proxy IVR — "
                "real options bid/ask unavailable. Rescan on a market day for accurate IVR values.",
            ],
            color="warning",
            style={"fontSize": "12px", "padding": "8px 12px", "marginBottom": "8px"},
        )
        vix_banner = html.Div([ivr_warn, vix_banner])

    return display_rows, status_div, vix_banner


# ── Callbacks — one per strategy ──────────────────────────────────────────────

def _make_scan_callback(slug: str):
    grid_id      = f"str-{slug}-grid"
    status_id    = f"str-{slug}-status"
    vix_id       = f"str-{slug}-vix-banner"
    scan_id      = f"str-{slug}-scan-btn"
    universe_id  = f"str-{slug}-universe"
    custom_id    = f"str-{slug}-custom"
    params_spec  = list(get_ui(slug).screener_params or [])

    @callback(
        Output(grid_id,   "data"),    # MRT uses `data` for rows
        Output(status_id, "children"),
        Output(vix_id,    "children"),
        Input(scan_id,    "n_clicks"),
        State(universe_id, "value"),
        State(custom_id,   "value"),
        *([State({"type": f"str-{slug}-param", "index": ALL}, "value")] if params_spec else []),
        prevent_initial_call=True,
    )
    def _scan(n_clicks, universe, custom, *args):
        param_vals = args[0] if args else []
        overrides  = {p["id"]: v for p, v in zip(params_spec, param_vals) if v is not None}
        api_key = get_polygon_api_key()
        if not api_key:
            msg = html.P(
                "No Polygon API key found. Set POLYGON_API_KEY env var.",
                style={"color": T.WARNING, "fontSize": "13px"},
            )
            return no_update, msg, no_update

        try:
            rows, status_div, vix_div = _run_scan(slug, universe or "ETF Core", custom, api_key,
                                                   param_overrides=overrides)
            return rows, status_div, vix_div
        except Exception as exc:
            logger.exception(f"Scan error for {slug}: {exc}")
            err = html.P(f"Scan error: {exc}", style={"color": T.DANGER, "fontSize": "13px"})
            return [], err, no_update

    _scan.__name__ = f"_scan_{slug}"

    # Filter toggle
    if params_spec:
        filter_tog = f"str-{slug}-filter-toggle"
        filter_col = f"str-{slug}-filter-collapse"
        reset_id   = f"str-{slug}-param-reset"

        @callback(
            Output(filter_col, "is_open"),
            Input(filter_tog,  "n_clicks"),
            State(filter_col,  "is_open"),
            prevent_initial_call=True,
        )
        def _toggle_filters(n, is_open):
            return not is_open
        _toggle_filters.__name__ = f"_toggle_filters_{slug}"

        @callback(
            Output({"type": f"str-{slug}-param", "index": ALL}, "value"),
            Input(reset_id, "n_clicks"),
            prevent_initial_call=True,
        )
        def _reset_params(_):
            return [p["default"] for p in params_spec]
        _reset_params.__name__ = f"_reset_params_{slug}"

    return _scan


# Register callbacks for every visible strategy at module import time
for _slug in _slugs():
    _make_scan_callback(_slug)
