"""
dash_app/pages/screener.py
Strategy Screener — runs scoring via engine/screener.py.
Requires a Polygon API key entered by the user.
"""
from __future__ import annotations

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
from dash import html, dcc, callback, Input, Output, State, no_update

from dash_app import theme as T, get_polygon_api_key
from engine.screener import UNIVERSES

_STRATEGIES = [
    {"label": "Iron Condor (Rules)", "value": "iron_condor_rules"},
    {"label": "Iron Condor (AI)",    "value": "iron_condor_ai"},
    {"label": "VIX Spike Fade",      "value": "vix_spike_fade"},
    {"label": "IVR Credit Spread",   "value": "ivr_credit_spread"},
    {"label": "Vol Arbitrage",       "value": "vol_arbitrage"},
    {"label": "GEX Positioning",     "value": "gex_positioning"},
]

_UNIVERSE_OPTIONS = [{"label": k, "value": k} for k in UNIVERSES]

_RESULT_COLS = [
    {"field": "Ticker",   "width": 90,  "pinned": "left"},
    {"field": "Score",    "width": 80,  "type": "numericColumn", "sort": "desc"},
    {"field": "Signal",   "flex": 1,    "minWidth": 160},
    {"field": "VIX",      "width": 80},
    {"field": "IVR",      "width": 80},
    {"field": "HV20",     "width": 80},
    {"field": "ATR%",     "width": 80},
    {"field": "ADX",      "width": 75},
]


def layout() -> html.Div:
    return html.Div([
        html.H2("Strategy Screener", style={
            "color": T.TEXT_PRIMARY, "fontSize": "1.35rem",
            "fontWeight": "700", "marginBottom": "4px",
        }),
        html.P("Score tickers against a strategy using live Polygon data.",
               style={"color": T.TEXT_MUTED, "fontSize": "13px", "marginBottom": "20px"}),

        # ── Controls ──────────────────────────────────────────────────────────
        dbc.Card(dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Label("Strategy", style={"color": T.TEXT_SEC, "fontSize": "12px",
                                                   "fontWeight": "600", "marginBottom": "4px"}),
                    dbc.Select(
                        id="scr-strategy",
                        options=_STRATEGIES,
                        value="iron_condor_rules",
                        style={**T.STYLE_DROPDOWN},
                    ),
                ], width=4),
                dbc.Col([
                    html.Label("Universe", style={"color": T.TEXT_SEC, "fontSize": "12px",
                                                   "fontWeight": "600", "marginBottom": "4px"}),
                    dbc.Select(
                        id="scr-universe",
                        options=_UNIVERSE_OPTIONS,
                        value=list(UNIVERSES.keys())[0],
                        style={**T.STYLE_DROPDOWN},
                    ),
                ], width=3),
                dbc.Col([
                    html.Label("Polygon API Key", style={"color": T.TEXT_SEC, "fontSize": "12px",
                                                          "fontWeight": "600", "marginBottom": "4px"}),
                    dbc.Input(id="scr-apikey", type="password",
                              placeholder="Leave blank to use env/config key" +
                                          (" ✓ key loaded" if get_polygon_api_key() else ""),
                              style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                                     "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY}),
                ], width=3),
                dbc.Col([
                    html.Label("\u00a0", style={"display": "block", "marginBottom": "4px"}),
                    dbc.Button("Run Scan", id="scr-run", color="primary",
                               style={"backgroundColor": T.ACCENT, "border": "none",
                                      "fontSize": "13px", "fontWeight": "600",
                                      "width": "100%"}),
                ], width=2),
            ], align="end"),
        ]), style={**T.STYLE_CARD, "marginBottom": "16px"}),

        # ── Status + Results ──────────────────────────────────────────────────
        html.Div(id="scr-status", style={"marginBottom": "12px"}),

        dcc.Loading(
            dag.AgGrid(
                id="scr-grid",
                columnDefs=_RESULT_COLS,
                rowData=[],
                defaultColDef={"resizable": True, "sortable": True, "filter": True},
                dashGridOptions={"domLayout": "autoHeight", "animateRows": True},
                className=T.AGGRID_THEME,
                style={"width": "100%"},
            ),
            type="circle", color=T.ACCENT,
        ),
    ], style=T.STYLE_PAGE)


@callback(
    Output("scr-grid",   "rowData"),
    Output("scr-status", "children"),
    Input("scr-run",     "n_clicks"),
    State("scr-strategy", "value"),
    State("scr-universe", "value"),
    State("scr-apikey",   "value"),
    prevent_initial_call=True,
)
def run_scan(n_clicks, strategy, universe, api_key):
    api_key = get_polygon_api_key(api_key or "")
    if not api_key:
        return no_update, html.P("No Polygon API key found. Set POLYGON_API_KEY env var or enter above.",
                                 style={"color": T.WARNING, "fontSize": "13px"})

    tickers = UNIVERSES.get(universe, [])
    if not tickers:
        return [], html.P("No tickers in universe.", style={"color": T.WARNING})

    from engine.screener import (
        _fetch_ohlcv, _vix_ivr, _atr, _adx,
        _score_ic_rules, _score_vix_spike_fade,
        _score_ivr_credit_spread, _score_vol_arbitrage,
        _score_gex_positioning, _score_generic,
    )
    from db.client import get_engine, get_vix_bars
    from datetime import date, timedelta

    try:
        engine     = get_engine()
        vix_df     = get_vix_bars(engine, date.today() - timedelta(days=400), date.today())
        vix_series = vix_df["close"].astype(float) if not vix_df.empty else None
    except Exception as e:
        return [], html.P(f"DB error: {e}", style={"color": T.DANGER, "fontSize": "13px"})

    score_fn = {
        "iron_condor_rules": _score_ic_rules,
        "iron_condor_ai":    _score_ic_rules,
        "vix_spike_fade":    _score_vix_spike_fade,
        "ivr_credit_spread": _score_ivr_credit_spread,
        "vol_arbitrage":     _score_vol_arbitrage,
        "gex_positioning":   _score_gex_positioning,
    }.get(strategy, _score_generic)

    rows = []
    for ticker in tickers:
        try:
            df = _fetch_ohlcv(ticker, api_key)
            if df.empty:
                continue
            vix_now = float(vix_series.iloc[-1]) if not vix_series.empty else None
            ivr_val = _vix_ivr(vix_series)
            atr_pct = _atr(df["high"], df["low"], df["close"]) / float(df["close"].iloc[-1]) * 100
            adx_val = _adx(df["high"], df["low"], df["close"])

            result = score_fn(ticker, df, vix_series, api_key)
            if result is None:
                continue

            rows.append({
                "Ticker":  ticker,
                "Score":   round(result.get("score", 0), 1),
                "Signal":  result.get("signal", ""),
                "VIX":     f"{vix_now:.1f}" if vix_now else "—",
                "IVR":     f"{ivr_val:.0%}",
                "HV20":    f"{result.get('hv20', 0)*100:.1f}%" if result.get("hv20") else "—",
                "ATR%":    f"{atr_pct:.1f}%",
                "ADX":     f"{adx_val:.0f}",
            })
        except Exception:
            continue

    rows.sort(key=lambda r: r["Score"], reverse=True)
    status = html.P(
        f"Scanned {len(tickers)} tickers · {len(rows)} signals",
        style={"color": T.TEXT_MUTED, "fontSize": "12px"},
    )
    return rows, status
