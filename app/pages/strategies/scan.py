"""
app/pages/strategies/scan.py — screener scan engine + per-strategy scan callbacks.

Holds _run_scan (the per-strategy screener dispatcher) and _make_scan_callback
(the dynamically-generated scan / filter-toggle / reset callbacks). Importing this
module registers a scan callback set for every strategy. Depends on the leaf
modules display_rows / data_fetch / format / registry — never on the page package.
"""
from __future__ import annotations

import logging

import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, State, no_update, ALL

from app import theme as T, get_polygon_api_key
from app.pages.strategies.registry import (
    _STRATEGIES, _SPY_ONLY_SLUGS, _SECTOR_ONLY_SLUGS, _SECTOR_ETFS_LIST,
    _SCREENER_PARAMS,
)
from app.pages.strategies.format import _vix_banner
from app.pages.strategies.data_fetch import (
    _resolve_tickers, _fetch_data, _fetch_ic_strikes, _fetch_ps_strikes,
)
from app.pages.strategies.display_rows import (
    _status_pill_row,
    _display_row_trend, _display_row_ic, _display_row_vsf, _display_row_ivr,
    _display_row_va, _display_row_gex, _display_row_bwb, _display_row_cal,
    _display_row_earn, _display_row_wheel, _display_row_bps, _display_row_put_steal,
    _display_row_hmm, _display_row_emp, _display_row_ssd, _display_row_trp,
    _display_row_nsn,
)

logger = logging.getLogger(__name__)


def _run_scan(slug: str, universe: str, custom: str | None, api_key: str,
              param_overrides: dict | None = None):
    """
    Returns (row_data, status_children, vix_banner_children) or raises.
    All error handling is done by callers via try/except.
    """
    from engine.screener import (
        _score_ic_rules,
        _score_ic_ai,
        _score_vix_spike_fade,
        _score_ivr_credit_spread,
        _score_vol_arbitrage,
        _score_gex_positioning,
        _score_broken_wing_butterfly,
        _score_calendar_spread,
        _score_earnings_straddle,
        _score_wheel_strategy,
        _score_bull_put_spread,
        _score_put_steal,
        _score_hmm_regime,
        _score_expiry_max_pain,
        _score_short_squeeze_detector,
        _score_tail_risk_put_spread,
        _score_news_sentiment_nlp,
        _DEFAULT_PARAMS,
    )

    # Locked-universe strategies ignore the universe/custom inputs
    if slug in _SPY_ONLY_SLUGS:
        tickers = ["SPY"]
    elif slug in _SECTOR_ONLY_SLUGS:
        tickers = _SECTOR_ETFS_LIST
    else:
        tickers = _resolve_tickers(universe, custom)
    if not tickers:
        return [], html.P("No tickers in universe.", style={"color": T.WARNING}), html.Div()

    vix_series, price_dfs, iv_all = _fetch_data(tickers, api_key)
    params = {**_DEFAULT_PARAMS.get(slug, {}), **(param_overrides or {})}

    raw_rows: list[dict] = []

    if slug in ("iron_condor_rules", "iron_condor_ai"):
        ic_params = params or {"ivr_min": 0.20, "vix_min": 14.0, "vix_max": 45.0,
                               "adx_max": 35.0, "atr_pct_max": 0.030}
        # Rules: threshold gates. AI: same metrics, but Score/gate come from the
        # gradient-boosting model's P(range-bound) via _score_ic_ai.
        _scorer = _score_ic_ai if slug == "iron_condor_ai" else _score_ic_rules
        for ticker in price_dfs:
            r = _scorer(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                ic_params,
            )
            if r:
                # Fetch real options chain for real strikes
                chain, chain_err = _fetch_ic_strikes(
                    ticker, api_key,
                    spot=r["Price"],
                    adx_ok=r.get("adx_ok", True),
                )
                r["_chain"]     = chain
                r["_chain_err"] = chain_err
                raw_rows.append(r)

    elif slug in ("trend_following", "ts_momentum"):
        # Timing strategies: scan the universe for who is currently in an uptrend
        # (BUY) vs cash (HOLD). Needs ~200+ bars for the MA, so fetch long history
        # per ticker (the shared 60-bar price_dfs is too short).
        from strategies.timing_base import load_close
        from strategies.trend_following import current_trend_signal
        from strategies.ts_momentum import current_tsmom_signal
        for ticker in tickers:
            try:
                close = load_close(ticker, n_days=600)
                sig = (current_trend_signal(close) if slug == "trend_following"
                       else current_tsmom_signal(close))
                if sig.get("signal") in (None, "UNKNOWN"):
                    continue
                is_buy = sig.get("signal") == "BUY"
                if slug == "trend_following":
                    ref = f"{sig['rule']} = {sig['ma']}"
                    strength = sig["pct_vs_ma"]
                else:
                    ref = sig["rule"]
                    strength = sig["ret_lookback_pct"]
                raw_rows.append({
                    "Ticker": ticker, "Price": sig.get("price", 0),
                    "Signal": sig.get("signal"), "Reference": ref,
                    "Strength %": strength, "score": strength,
                    "all_pass": is_buy, "n_pass": 4 if is_buy else 0,
                })
            except Exception as _e:
                logger.warning(f"trend scan {ticker} failed: {_e}")

    elif slug == "vix_spike_fade":
        for ticker in price_dfs:
            r = _score_vix_spike_fade(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
            )
            if r:
                raw_rows.append(r)

    elif slug == "ivr_credit_spread":
        for ticker in price_dfs:
            r = _score_ivr_credit_spread(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params or {"ivr_min": 0.40, "vix_max": 50.0},
            )
            if r:
                raw_rows.append(r)

    elif slug == "vol_arbitrage":
        for ticker in price_dfs:
            r = _score_vol_arbitrage(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
            )
            if r:
                raw_rows.append(r)

    elif slug == "gex_positioning":
        raw_rows = _score_gex_positioning(
            tickers=list(price_dfs.keys()),
            api_key=api_key,
            vix_series=vix_series,
            price_dfs=price_dfs,
            params={},
        )

    elif slug == "broken_wing_butterfly":
        for ticker in price_dfs:
            r = _score_broken_wing_butterfly(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "calendar_spread":
        for ticker in price_dfs:
            r = _score_calendar_spread(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "earnings_straddle":
        for ticker in price_dfs:
            r = _score_earnings_straddle(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
                days_to_earnings=None,   # live days-to-earnings not yet wired
            )
            if r:
                raw_rows.append(r)

    elif slug == "wheel_strategy":
        for ticker in price_dfs:
            r = _score_wheel_strategy(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "bull_put_spread":
        for ticker in price_dfs:
            r = _score_bull_put_spread(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "put_steal":
        for ticker in price_dfs:
            r = _score_put_steal(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                # Fetch real Polygon options chain for actual strikes & mids
                chain, chain_err = _fetch_ps_strikes(
                    ticker, api_key,
                    spot=r["Price"],
                    itm_pct=params.get("itm_pct", 0.05),
                    wing_pct=0.04,
                )
                r["_chain"]     = chain
                r["_chain_err"] = chain_err
                raw_rows.append(r)

    elif slug == "hmm_regime":
        for ticker in price_dfs:
            r = _score_hmm_regime(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "expiry_max_pain":
        for ticker in price_dfs:
            r = _score_expiry_max_pain(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "short_squeeze_detector":
        for ticker in price_dfs:
            r = _score_short_squeeze_detector(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "tail_risk_put_spread":
        for ticker in price_dfs:
            r = _score_tail_risk_put_spread(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "news_sentiment_nlp":
        for ticker in price_dfs:
            r = _score_news_sentiment_nlp(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    # Format rows for AG Grid
    fmt_map = {
        "trend_following":      _display_row_trend,
        "ts_momentum":          _display_row_trend,
        "iron_condor_rules":    _display_row_ic,
        "iron_condor_ai":       _display_row_ic,
        "vix_spike_fade":       _display_row_vsf,
        "ivr_credit_spread":    _display_row_ivr,
        "vol_arbitrage":        _display_row_va,
        "gex_positioning":      _display_row_gex,
        "broken_wing_butterfly": _display_row_bwb,
        "calendar_spread":      _display_row_cal,
        "earnings_straddle":    _display_row_earn,
        "wheel_strategy":       _display_row_wheel,
        "bull_put_spread":      _display_row_bps,
        "put_steal":            _display_row_put_steal,
        # New strategies (2026-05-01)
        "hmm_regime":              _display_row_hmm,
        "expiry_max_pain":         _display_row_emp,
        "short_squeeze_detector":  _display_row_ssd,
        "tail_risk_put_spread":    _display_row_trp,
        "news_sentiment_nlp":      _display_row_nsn,
    }
    fmt_fn = fmt_map.get(slug, _display_row_ic)
    display_rows = [fmt_fn(r) for r in raw_rows]

    # Sort by score descending
    display_rows.sort(
        key=lambda r: (r.get("Score") or 0) if isinstance(r.get("Score"), (int, float)) else 0,
        reverse=True,
    )

    status_div   = _status_pill_row(display_rows)
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
# We generate callbacks dynamically to avoid 6× code duplication.

def _make_scan_callback(slug: str):
    grid_id      = f"str-{slug}-grid"
    status_id    = f"str-{slug}-status"
    vix_id       = f"str-{slug}-vix-banner"
    scan_id      = f"str-{slug}-scan-btn"
    universe_id  = f"str-{slug}-universe"
    custom_id    = f"str-{slug}-custom"
    params_spec  = _SCREENER_PARAMS.get(slug, [])
    param_ids    = [{"type": f"str-{slug}-param", "index": p["id"]} for p in params_spec]

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


# Register callbacks for all 6 strategies at module import time
for _slug in [s["value"] for s in _STRATEGIES]:
    _make_scan_callback(_slug)
