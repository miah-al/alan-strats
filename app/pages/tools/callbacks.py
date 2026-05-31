"""
app/pages/tools/callbacks.py -- all Tools callbacks (registered on import).

Importing this module registers every @callback with Dash (the decorator runs at
import), including the dynamically-registered per-symbol sync callbacks and the
tab-routing callback. The package __init__ imports it for that side effect.

Split verbatim from the original tools.py -- every id / Input / Output / State
is identical.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update

from app import theme as T, get_polygon_api_key
from app.ui import tokens as D, components as C

from app.pages.tools.tabs import _get_tab_builder
from app.pages.tools.data import (
    _run_sync, _build_coverage_tables, _build_validation, _running_badge,
    _metric_card, _get_px_client, _px_error, _px_df_grid,
    _rh_available, _rh_get_stock_price, _rh_get_option_ask,
    _SYNC_BUTTONS, _SYNC_ALL_STEPS, _SYNC_ALL_IDX,
)

logger = logging.getLogger(__name__)

_GUIDE_DIR = Path(__file__).parent.parent.parent / "guide_articles"


@callback(
    Output("tools-tab-content", "children"),
    Input("tools-tabs", "active_tab"),
    prevent_initial_call=True,
)
def _render_tools_tab(active):
    builder = _get_tab_builder(active)
    return builder() if builder else no_update


def _register_sync_callback(btn_id, st_id, cap_id, dtype):
    @callback(
        Output(st_id,  "children"),
        Output(cap_id, "children"),
        Input(btn_id,  "n_clicks"),
        State("tools-dm-ticker",    "value"),
        State("tools-dm-from-date", "value"),
        State("tools-dm-force-full","value"),
        State("tools-dm-av-key",    "value"),
        prevent_initial_call=True,
    )
    def _cb(n, ticker, from_date, force, av_key, _dt=dtype):
        if not n:
            return no_update, no_update
        t = (ticker or "").strip().upper()
        fd = from_date or "2020-01-01"
        av = av_key or ""
        status, cap = _run_sync(_dt, t, fd, force or [], av)
        return status, cap


for _btn, _st, _cap, _dt in _SYNC_BUTTONS:
    _register_sync_callback(_btn, _st, _cap, _dt)


@callback(
    Output("tools-dm-st-price",    "children", allow_duplicate=True),
    Output("tools-dm-st-news",     "children", allow_duplicate=True),
    Output("tools-dm-st-divs",     "children", allow_duplicate=True),
    Output("tools-dm-st-earnings", "children", allow_duplicate=True),
    Output("tools-dm-st-treasury", "children", allow_duplicate=True),
    Output("tools-dm-st-vix",      "children", allow_duplicate=True),
    Output("tools-dm-st-macro",    "children", allow_duplicate=True),
    Output("tools-dm-st-cpi",      "children", allow_duplicate=True),
    Output("tools-dm-st-fomc",     "children", allow_duplicate=True),
    Output("tools-dm-sync-all-state", "data"),
    Input("tools-dm-sync-all",        "n_clicks"),
    Input("tools-dm-sync-all-state",  "data"),
    State("tools-dm-ticker",          "value"),
    State("tools-dm-from-date",       "value"),
    State("tools-dm-force-full",      "value"),
    prevent_initial_call=True,
)
def _sync_all_progressive(n, state, ticker, from_date, force):
    """Runs Sync All one step at a time so the UI shows progress.

    Two triggers:
      * Button click → seed state, show step 0 as "Running…", others as "Queued".
      * Store change → execute state["idx"], mark it Done, advance to next.
    """
    from dash import ctx
    trig = ctx.triggered_id

    n_out = len(_SYNC_ALL_STEPS)

    # ── Phase 1: button click — seed state & show queued/running banners ──
    if trig == "tools-dm-sync-all":
        if not n:
            return [no_update] * n_out + [no_update]
        t  = (ticker or "").strip().upper()
        fd = from_date or "2020-01-01"
        fr = force or []
        if not t:
            # Ticker required for price/news/divs/earnings; free sources OK.
            # Seed anyway — the per-step runner will surface the warning per step.
            pass
        out = [html.Span("Queued", style={"color": T.TEXT_MUTED})
               for _ in range(n_out)]
        out[0] = _running_badge()
        new_state = {"idx": 0, "ticker": t, "fd": fd, "fr": fr}
        return out + [new_state]

    # ── Phase 2: state change — execute the current step and advance ──
    if not isinstance(state, dict) or "idx" not in state:
        return [no_update] * n_out + [no_update]

    idx = int(state["idx"])
    if idx >= n_out:
        return [no_update] * n_out + [None]     # finished — clear state

    step_name = _SYNC_ALL_STEPS[idx]
    status, _ = _run_sync(step_name, state.get("ticker", ""),
                          state.get("fd", "2020-01-01"),
                          state.get("fr", []))

    out = [no_update] * n_out
    out[idx] = status    # mark current step Done
    next_idx = idx + 1
    if next_idx < n_out:
        out[next_idx] = _running_badge()
        new_state = {**state, "idx": next_idx}
    else:
        new_state = None   # chain complete → stop re-triggering
    return out + [new_state]


@callback(
    Output("tools-dm-coverage-tables", "children"),
    Input("tools-dm-refresh-cov", "n_clicks"),
    prevent_initial_call=True,
)
def _refresh_coverage(n):
    if not n:
        return no_update
    return _build_coverage_tables()


@callback(
    Output("tools-dm-val-result", "children"),
    Input("tools-dm-validate-btn", "n_clicks"),
    State("tools-dm-val-ticker", "value"),
    prevent_initial_call=True,
)
def _validate(n, val_ticker):
    if not n:
        return no_update
    return _build_validation((val_ticker or "").strip().upper())


@callback(
    Output("tools-iv-content", "children"),
    Input("tools-iv-run-btn", "n_clicks"),
    State("tools-iv-tickers",  "value"),
    State("tools-iv-api-key",  "value"),
    prevent_initial_call=True,
)
def _run_iv_scan(n, tickers_str, user_api_key):
    if not n:
        return no_update

    api_key = get_polygon_api_key(user_api_key or "")
    if not api_key:
        return dbc.Alert("Polygon API key required — set in .env or enter above.",
                         color="warning", style={"fontSize": "13px"})

    raw = [t.strip().upper() for t in (tickers_str or "").split(",") if t.strip()]
    if not raw:
        return dbc.Alert("Enter at least one ticker.", color="warning",
                         style={"fontSize": "13px"})

    try:
        from engine.iv_metrics import get_iv_metrics_batch
        from engine.screener import _fetch_ohlcv

        price_dfs = {}
        for tk in raw:
            try:
                df = _fetch_ohlcv(tk, api_key)
                if df is not None and not df.empty:
                    price_dfs[tk] = df
            except Exception:
                pass

        metrics = get_iv_metrics_batch(
            tickers=raw,
            api_key=api_key,
            price_dfs=price_dfs,
            fetch_ivr_history=True,
        )
    except Exception as e:
        return dbc.Alert(f"IV scan error: {e}", color="danger",
                         style={"fontSize": "13px"})

    # ── Build summary table ───────────────────────────────────────────────────
    rows = []
    for tk in raw:
        m = metrics.get(tk, {})

        def _p(v):
            if v is None:
                return "—"
            try:
                return f"{float(v)*100:.1f}%"
            except Exception:
                return "—"

        def _f2(v):
            if v is None:
                return "—"
            try:
                return f"{float(v):.2f}"
            except Exception:
                return "—"

        rows.append({
            "Ticker":    tk,
            "ATM IV":    _p(m.get("atm_iv")),
            "IVR":       _p(m.get("ivr")),
            "HV20":      _p(m.get("hv20")),
            "VRP":       _p(m.get("vrp")),
            "IV/HV":     _f2(m.get("iv_over_hv")),
            "DTE":       str(m.get("dte_used") or "—"),
            "Strike":    _f2(m.get("atm_strike")),
            "Conf":      m.get("ivr_confidence", "—"),
            "Source":    m.get("iv_source", "—"),
            "Error":     m.get("error") or "",
        })

    tbl_cols = [
        {"field": "Ticker",  "width": 80,  "resizable": True, "sortable": True, "filter": True},
        {"field": "ATM IV",  "minWidth": 85,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "IVR",     "minWidth": 75,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "HV20",    "minWidth": 75,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "VRP",     "minWidth": 75,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "IV/HV",   "minWidth": 75,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "DTE",     "minWidth": 65,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "Strike",  "minWidth": 85,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "Conf",    "minWidth": 80,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "Source",  "minWidth": 160, "flex": 2, "resizable": True, "sortable": True, "filter": True},
        {"field": "Error",   "minWidth": 120, "flex": 2, "resizable": True, "sortable": True, "filter": True},
    ]

    summary_grid = dag.AgGrid(
        rowData=rows,
        columnDefs=tbl_cols,
        defaultColDef={"resizable": True},
        className=T.AGGRID_THEME,
        dashGridOptions={"suppressColumnVirtualisation": True},
        style={"height": str(60 + len(rows) * 42) + "px", "width": "100%",
               "marginBottom": "24px"},
    )

    # ── IV vs HV bar chart ────────────────────────────────────────────────────
    chart_tickers = [r["Ticker"] for r in rows]
    atm_ivs = []
    hv20s   = []
    for tk in chart_tickers:
        m = metrics[tk]
        atm_ivs.append(round(m["atm_iv"] * 100, 1) if m.get("atm_iv") is not None else None)
        hv20s.append(round(m["hv20"]   * 100, 1) if m.get("hv20")   is not None else None)

    fig_iv_hv = go.Figure()
    fig_iv_hv.add_trace(go.Bar(
        name="ATM IV",
        x=chart_tickers,
        y=atm_ivs,
        marker_color=T.ACCENT,
        opacity=0.85,
    ))
    fig_iv_hv.add_trace(go.Bar(
        name="HV20",
        x=chart_tickers,
        y=hv20s,
        marker_color=T.SUCCESS,
        opacity=0.75,
    ))
    fig_iv_hv.update_layout(**D.plotly_layout(
        height=300,
        barmode="group",
        title="ATM IV vs HV20 (%)",
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        yaxis={"title": "Volatility (%)", "gridcolor": D.COLOR.border},
        xaxis={"gridcolor": D.COLOR.border},
    ))

    # ── IVR bar chart ─────────────────────────────────────────────────────────
    ivr_vals = []
    ivr_colors = []
    for tk in chart_tickers:
        m = metrics[tk]
        ivr = m.get("ivr")
        ivr_vals.append(round(ivr * 100, 1) if ivr is not None else None)
        if ivr is None:
            ivr_colors.append(T.BORDER_BRT)
        elif ivr >= 0.7:
            ivr_colors.append(T.DANGER)
        elif ivr >= 0.5:
            ivr_colors.append(T.WARNING)
        else:
            ivr_colors.append(T.SUCCESS)

    fig_ivr = go.Figure()
    fig_ivr.add_trace(go.Bar(
        name="IVR",
        x=chart_tickers,
        y=ivr_vals,
        marker_color=ivr_colors,
        opacity=0.85,
    ))
    fig_ivr.add_hline(y=50, line_dash="dash", line_color=T.TEXT_MUTED,
                      annotation_text="50% threshold")
    fig_ivr.update_layout(**D.plotly_layout(
        height=280,
        title="IV Rank (IVR %)",
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        yaxis={"title": "IVR (%)", "range": [0, 110], "gridcolor": D.COLOR.border},
        xaxis={"gridcolor": D.COLOR.border},
    ))

    # ── VRP chart ─────────────────────────────────────────────────────────────
    vrp_vals = []
    vrp_colors = []
    for tk in chart_tickers:
        m = metrics[tk]
        vrp = m.get("vrp")
        vrp_vals.append(round(vrp * 100, 1) if vrp is not None else None)
        if vrp is None:
            vrp_colors.append(T.BORDER_BRT)
        elif vrp > 0:
            vrp_colors.append(T.SUCCESS)
        else:
            vrp_colors.append(T.DANGER)

    fig_vrp = go.Figure()
    fig_vrp.add_trace(go.Bar(
        name="VRP",
        x=chart_tickers,
        y=vrp_vals,
        marker_color=vrp_colors,
        opacity=0.85,
    ))
    fig_vrp.add_hline(y=0, line_color=T.TEXT_MUTED)
    fig_vrp.update_layout(**D.plotly_layout(
        height=260,
        title="Variance Risk Premium = IV − HV20 (%)",
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        yaxis={"title": "VRP (%)", "gridcolor": D.COLOR.border},
        xaxis={"gridcolor": D.COLOR.border},
    ))

    return html.Div([
        summary_grid,
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_iv_hv, config={"displayModeBar": False})),
                 style={**T.STYLE_CARD, "marginBottom": "16px"}),
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_ivr,   config={"displayModeBar": False})),
                 style={**T.STYLE_CARD, "marginBottom": "16px"}),
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_vrp,   config={"displayModeBar": False})),
                 style={**T.STYLE_CARD}),
    ])


@callback(
    Output("tools-guide-content", "children"),
    Input("tools-guide-select", "value"),
)
def _render_guide(slug):
    if not slug:
        return html.Div("Select an article above.",
                        style={"color": T.TEXT_MUTED, "fontSize": "13px"})
    md_path = _GUIDE_DIR / f"{slug}.md"
    if not md_path.exists():
        return html.Div(f"Article not found: {slug}",
                        style={"color": T.DANGER, "fontSize": "13px"})
    content = md_path.read_text(encoding="utf-8")

    md = dcc.Markdown(
        content,
        className="guide-md",
        style={"color": T.TEXT_PRIMARY, "fontSize": "14px", "lineHeight": "1.75"},
    )

    # ── Per-article interactive charts ────────────────────────────────────────
    _GUIDE_CHART_MODULES = {
        "vol_arbitrage":         "app.guide_charts.vol_arbitrage_charts",
        "iron_condor":           "app.guide_charts.iron_condor_charts",
        "iron_condor_weekly":    "app.guide_charts.iron_condor_charts",
        "iron_condor_rules":     "app.guide_charts.iron_condor_charts",
        "bull_put_spread":       "app.guide_charts.bull_put_spread_charts",
        "bear_call_spread":      "app.guide_charts.bull_put_spread_charts",
        "earnings_iv_crush":     "app.guide_charts.earnings_iv_crush_charts",
        "earnings_vol_crush":    "app.guide_charts.earnings_iv_crush_charts",
        "earnings_straddle":     "app.guide_charts.earnings_iv_crush_charts",
        "pairs_spy_qqq":         "app.guide_charts.pairs_spy_qqq_charts",
        "pairs_spy_iwm":         "app.guide_charts.pairs_spy_qqq_charts",
        "pairs_spy_dia":         "app.guide_charts.pairs_spy_qqq_charts",
        "stat_arb_etf_basket":   "app.guide_charts.stat_arb_etf_basket_charts",
        "vix_mean_reversion":    "app.guide_charts.vix_mean_reversion_charts",
        "vix_spike_fade":        "app.guide_charts.vix_mean_reversion_charts",
        "momentum_factor":       "app.guide_charts.momentum_factor_charts",
        "momentum_12_1":         "app.guide_charts.momentum_factor_charts",
        "momentum_cross_sector": "app.guide_charts.momentum_factor_charts",
        "hmm_regime":            "app.guide_charts.hmm_regime_charts",
    }

    extra: list = []
    module_path = _GUIDE_CHART_MODULES.get(slug)
    if module_path:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            extra.append(mod.render_charts())
        except Exception as e:
            logger.warning("Guide charts failed for %s: %s", slug, e)

    return html.Div([md, *extra])


@callback(
    Output("tools-px-test-result", "children"),
    Input("tools-px-test-btn", "n_clicks"),
    State("tools-px-api-key", "value"),
    prevent_initial_call=True,
)
def _px_test_key(n, api_key):
    if not n:
        return no_update
    try:
        client = _get_px_client(api_key)
        snap = client.get_snapshot("SPY")
        price = snap.get("day", {}).get("c") or snap.get("lastTrade", {}).get("p", "?")
        return html.Span(f"Key valid — SPY last: {price}",
                         style={"color": T.SUCCESS, "fontSize": "13px"})
    except Exception as e:
        return _px_error(f"Key test failed: {e}")


@callback(
    Output("tools-px-snap-content", "children"),
    Input("tools-px-snap-btn", "n_clicks"),
    State("tools-px-ticker", "value"),
    State("tools-px-api-key", "value"),
    prevent_initial_call=True,
)
def _px_snapshot(n, ticker, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        snap = client.get_snapshot(tk)
    except Exception as e:
        return _px_error(e)

    day  = snap.get("day", {}) or {}
    prev = snap.get("prevDay", {}) or {}
    chg_pct = snap.get("todaysChangePerc")
    price = day.get("c") or snap.get("lastTrade", {}).get("p", "—")
    vol   = day.get("v", "—")
    hi    = day.get("h", "—")
    lo    = day.get("l", "—")

    cards = html.Div([
        _metric_card("Price",   f"{price}"),
        _metric_card("Change%", f"{chg_pct:.2f}%" if chg_pct is not None else "—"),
        _metric_card("Volume",  f"{int(vol):,}"   if isinstance(vol, (int, float)) else str(vol)),
        _metric_card("High",    f"{hi}"),
        _metric_card("Low",     f"{lo}"),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "12px"})

    # flatten snap dict for table
    flat = {}
    for k, v in snap.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                flat[f"{k}.{k2}"] = v2
        else:
            flat[k] = v
    import pandas as pd
    df = pd.DataFrame([{"Key": k, "Value": str(v)} for k, v in flat.items()])
    return html.Div([cards, _px_df_grid(df, height=280)])


@callback(
    Output("tools-px-bars-content", "children"),
    Input("tools-px-bars-btn", "n_clicks"),
    State("tools-px-ticker",       "value"),
    State("tools-px-bars-mult",    "value"),
    State("tools-px-bars-timespan","value"),
    State("tools-px-bars-from",    "value"),
    State("tools-px-bars-to",      "value"),
    State("tools-px-api-key",      "value"),
    prevent_initial_call=True,
)
def _px_bars(n, ticker, mult, timespan, from_date, to_date, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        df = client.get_aggregates(
            ticker=tk,
            from_date=from_date or (date.today() - timedelta(days=30)).isoformat(),
            to_date=to_date or date.today().isoformat(),
            timespan=timespan or "day",
            multiplier=int(mult or 1),
        )
    except Exception as e:
        return _px_error(e)
    if df.empty:
        return _px_error("No data returned.")

    df = df.reset_index()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["date"].astype(str),
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name=tk,
    ))
    fig.update_layout(**D.plotly_layout(
        height=360,
        title=f"{tk} OHLCV ({timespan})",
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        xaxis_rangeslider_visible=False,
    ))
    return html.Div([
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
        _px_df_grid(df.tail(100), height=260),
    ])


@callback(
    Output("tools-px-ind-content", "children"),
    Input("tools-px-ind-btn", "n_clicks"),
    State("tools-px-ticker",      "value"),
    State("tools-px-ind-type",    "value"),
    State("tools-px-ind-window",  "value"),
    State("tools-px-ind-timespan","value"),
    State("tools-px-ind-from",    "value"),
    State("tools-px-ind-to",      "value"),
    State("tools-px-api-key",     "value"),
    prevent_initial_call=True,
)
def _px_indicators(n, ticker, ind_type, window, timespan, from_date, to_date, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        result = client.get_technical_indicator(
            ticker=tk,
            indicator=ind_type or "rsi",
            from_date=from_date or (date.today() - timedelta(days=30)).isoformat(),
            to_date=to_date or date.today().isoformat(),
            window=int(window or 14),
            timespan=timespan or "day",
        )
    except Exception as e:
        return _px_error(e)

    import pandas as pd
    if isinstance(result, pd.Series):
        df = result.reset_index()
        df.columns = ["date", ind_type or "value"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["date"].astype(str), y=df.iloc[:, 1],
                                  mode="lines", name=(ind_type or "value").upper(),
                                  line={"color": T.ACCENT}))
    elif isinstance(result, pd.DataFrame):
        df = result.reset_index()
        fig = go.Figure()
        for col in [c for c in df.columns if c != "date"]:
            fig.add_trace(go.Scatter(x=df["date"].astype(str), y=df[col],
                                      mode="lines", name=col))
    else:
        return _px_error("Unexpected result format.")

    fig.update_layout(**D.plotly_layout(
        height=300,
        title=f"{tk} {(ind_type or 'indicator').upper()}(window={window})",
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
    ))
    return html.Div([
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
        _px_df_grid(df.tail(100), height=240),
    ])


@callback(
    Output("tools-px-exp-content", "children"),
    Input("tools-px-exp-btn", "n_clicks"),
    State("tools-px-ticker",  "value"),
    State("tools-px-api-key", "value"),
    prevent_initial_call=True,
)
def _px_expirations(n, ticker, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        exps = client.get_expirations(tk, as_of=date.today().isoformat())
    except Exception as e:
        return _px_error(e)
    if not exps:
        return _px_error("No expirations found.")
    import pandas as pd
    df = pd.DataFrame({"Expiration": exps})
    return _px_df_grid(df, height=min(40 + len(exps) * 40, 400))


@callback(
    Output("tools-px-expirations-store", "data"),
    Input("tools-px-load-exp-btn", "n_clicks"),
    State("tools-px-ticker",  "value"),
    State("tools-px-api-key", "value"),
    prevent_initial_call=True,
)
def _px_load_expirations(n, ticker, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return []
    try:
        client = _get_px_client(api_key)
        return client.get_expirations(tk, as_of=date.today().isoformat())
    except Exception:
        return []


@callback(
    Output("tools-px-chain-exp", "options"),
    Output("tools-px-chain-exp", "value"),
    Input("tools-px-expirations-store", "data"),
    prevent_initial_call=True,
)
def _px_populate_exp_dropdown(exps):
    if not exps:
        return [], None
    opts = [{"label": e, "value": e} for e in exps]
    return opts, exps[0]


@callback(
    Output("tools-px-chain-content", "children"),
    Input("tools-px-chain-btn", "n_clicks"),
    State("tools-px-ticker",            "value"),
    State("tools-px-chain-exp",         "value"),
    State("tools-px-chain-type",        "value"),
    State("tools-px-chain-strike-range","value"),
    State("tools-px-chain-historical",  "value"),
    State("tools-px-chain-date",        "value"),
    State("tools-px-api-key",           "value"),
    prevent_initial_call=True,
)
def _px_chain(n, ticker, expiration, contract_type, strike_range,
              historical, hist_date, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    if not expiration:
        return _px_error("Load and select an expiration.")

    snapshot_date = hist_date if historical else None

    try:
        client = _get_px_client(api_key)
        # Get current spot to compute strike range
        snap = client.get_snapshot(tk)
        spot = (snap.get("day", {}) or {}).get("c") or (snap.get("lastTrade", {}) or {}).get("p")
        spot = float(spot) if spot else None

        kwargs = {"expiration_date": expiration}
        if snapshot_date:
            kwargs["snapshot_date"] = snapshot_date
        if spot and strike_range:
            lo_pct, hi_pct = strike_range
            kwargs["strike_price_gte"] = round(spot * lo_pct / 100, 2)
            kwargs["strike_price_lte"] = round(spot * hi_pct / 100, 2)

        df = client.get_options_chain(tk, **kwargs)
    except Exception as e:
        return _px_error(e)

    if df.empty:
        return _px_error("No chain data returned.")

    # Filter by contract type
    if contract_type and contract_type != "all":
        df = df[df["type"] == contract_type]

    import pandas as pd
    import numpy as np

    # ── Metric cards ─────────────────────────────────────────────────────────
    dte_val = df["dte"].median() if "dte" in df.columns and not df["dte"].isna().all() else None
    calls = df[df["type"] == "call"] if "type" in df.columns else pd.DataFrame()
    puts  = df[df["type"] == "put"]  if "type" in df.columns else pd.DataFrame()
    c_oi  = calls["open_interest"].sum() if not calls.empty and "open_interest" in calls.columns else 0
    p_oi  = puts["open_interest"].sum()  if not puts.empty  and "open_interest" in puts.columns  else 0
    pc_ratio = f"{p_oi/c_oi:.2f}" if c_oi else "—"

    # ATM IV
    atm_iv_c = atm_iv_p = None
    if spot and not calls.empty and "strike" in calls.columns and "iv" in calls.columns:
        c_atm = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]
        atm_iv_c = c_atm["iv"].values[0] if not c_atm.empty else None
    if spot and not puts.empty and "strike" in puts.columns and "iv" in puts.columns:
        p_atm = puts.iloc[(puts["strike"] - spot).abs().argsort()[:1]]
        atm_iv_p = p_atm["iv"].values[0] if not p_atm.empty else None
    atm_iv_str = (
        f"C {atm_iv_c*100:.1f}% / P {atm_iv_p*100:.1f}%"
        if atm_iv_c is not None and atm_iv_p is not None
        else "—"
    )

    # Max pain
    max_pain_strike = None
    if "strike" in df.columns and "open_interest" in df.columns:
        strikes = sorted(df["strike"].dropna().unique())
        pain = {}
        for s in strikes:
            c_pain = calls[calls["strike"] >= s]["open_interest"].fillna(0).sum() * (calls[calls["strike"] >= s]["strike"] - s).fillna(0).values
            p_pain = puts[puts["strike"] <= s]["open_interest"].fillna(0).sum() * (s - puts[puts["strike"] <= s]["strike"]).fillna(0).values
            pain[s] = float(np.sum(c_pain)) + float(np.sum(p_pain))
        if pain:
            max_pain_strike = min(pain, key=pain.get)

    cards = html.Div([
        _metric_card("Spot",        f"{spot:.2f}" if spot else "—"),
        _metric_card("DTE",         f"{int(dte_val)}" if dte_val is not None else "—"),
        _metric_card("P/C OI Ratio",pc_ratio),
        _metric_card("ATM IV (C/P)",atm_iv_str),
        _metric_card("Max Pain",    f"{max_pain_strike:.0f}" if max_pain_strike else "—"),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "16px"})

    # ── IV Smile chart ────────────────────────────────────────────────────────
    fig_smile = go.Figure()
    if not calls.empty and "strike" in calls.columns and "iv" in calls.columns:
        c_sorted = calls.dropna(subset=["strike", "iv"]).sort_values("strike")
        fig_smile.add_trace(go.Scatter(
            x=c_sorted["strike"], y=c_sorted["iv"] * 100,
            mode="lines+markers", name="Call IV",
            line={"color": T.SUCCESS},
        ))
    if not puts.empty and "strike" in puts.columns and "iv" in puts.columns:
        p_sorted = puts.dropna(subset=["strike", "iv"]).sort_values("strike")
        fig_smile.add_trace(go.Scatter(
            x=p_sorted["strike"], y=p_sorted["iv"] * 100,
            mode="lines+markers", name="Put IV",
            line={"color": T.DANGER},
        ))
    if spot:
        fig_smile.add_vline(x=spot, line_dash="dash", line_color=T.TEXT_MUTED,
                             annotation_text="Spot")
    fig_smile.update_layout(**D.plotly_layout(
        height=300,
        title=f"{tk} IV Smile — {expiration}",
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        xaxis={"title": "Strike", "gridcolor": D.COLOR.border},
        yaxis={"title": "IV (%)",  "gridcolor": D.COLOR.border},
    ))

    # ── OI chart ──────────────────────────────────────────────────────────────
    fig_oi = go.Figure()
    if not calls.empty and "strike" in calls.columns and "open_interest" in calls.columns:
        c_oi_df = calls.dropna(subset=["strike"]).sort_values("strike")
        fig_oi.add_trace(go.Bar(
            x=c_oi_df["strike"], y=c_oi_df["open_interest"].fillna(0),
            name="Call OI", marker_color=T.SUCCESS, opacity=0.7,
        ))
    if not puts.empty and "strike" in puts.columns and "open_interest" in puts.columns:
        p_oi_df = puts.dropna(subset=["strike"]).sort_values("strike")
        fig_oi.add_trace(go.Bar(
            x=p_oi_df["strike"], y=p_oi_df["open_interest"].fillna(0),
            name="Put OI", marker_color=T.DANGER, opacity=0.7,
        ))
    if max_pain_strike:
        fig_oi.add_vline(x=max_pain_strike, line_dash="dot", line_color=T.WARNING,
                          annotation_text=f"Max Pain {max_pain_strike:.0f}")
    fig_oi.update_layout(**D.plotly_layout(
        height=280,
        title=f"{tk} Open Interest — {expiration}",
        barmode="overlay",
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        xaxis={"title": "Strike", "gridcolor": D.COLOR.border},
        yaxis={"title": "Open Interest", "gridcolor": D.COLOR.border},
    )

    # ── Chain grid ────────────────────────────────────────────────────────────
    chain_display = df.copy()
    if "iv" in chain_display.columns:
        chain_display["IV%"] = chain_display["iv"].apply(
            lambda v: f"{v*100:.1f}%" if v is not None and not (isinstance(v, float) and np.isnan(v)) else "—"
        )
    for col in ["bid", "ask", "delta", "gamma", "theta", "vega"]:
        if col in chain_display.columns:
            chain_display[col] = chain_display[col].apply(
                lambda v: f"{v:.4f}" if v is not None and not (isinstance(v, float) and np.isnan(v)) else "—"
            )
    if "bid" in chain_display.columns and "ask" in chain_display.columns:
        chain_display["Mid"] = chain_display.apply(
            lambda r: f"{(float(r['bid'].replace('—','nan')) + float(r['ask'].replace('—','nan')))/2:.4f}"
            if r["bid"] != "—" and r["ask"] != "—" else "—", axis=1
        )
        chain_display["Spread"] = chain_display.apply(
            lambda r: f"{float(r['ask'].replace('—','nan')) - float(r['bid'].replace('—','nan')):.4f}"
            if r["bid"] != "—" and r["ask"] != "—" else "—", axis=1
        )

    display_cols_order = ["strike", "type", "bid", "ask", "Mid", "Spread",
                           "IV%", "delta", "gamma", "theta", "vega",
                           "open_interest", "volume"]
    display_cols_order = [c for c in display_cols_order if c in chain_display.columns]
    rename_map = {
        "strike": "Strike", "type": "Type", "bid": "Bid", "ask": "Ask",
        "delta": "Delta", "gamma": "Gamma", "theta": "Theta", "vega": "Vega",
        "open_interest": "OI", "volume": "Volume",
    }
    chain_display = chain_display[display_cols_order].rename(columns=rename_map)

    chain_cols = [{"field": c, "resizable": True, "sortable": True, "filter": True,
                   "minWidth": 70, "flex": 1} for c in chain_display.columns]
    chain_grid = dag.AgGrid(
        rowData=chain_display.astype(str).to_dict("records"),
        columnDefs=chain_cols,
        defaultColDef={"resizable": True},
        className=T.AGGRID_THEME,
        dashGridOptions={"suppressColumnVirtualisation": True},
        style={"height": "400px", "width": "100%"},
    )

    return html.Div([
        cards,
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_smile, config={"displayModeBar": False})),
                 style={**T.STYLE_CARD, "marginBottom": "12px"}),
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_oi, config={"displayModeBar": False})),
                 style={**T.STYLE_CARD, "marginBottom": "12px"}),
        chain_grid,
    ])


@callback(
    Output("tools-px-details-content", "children"),
    Input("tools-px-details-btn", "n_clicks"),
    State("tools-px-ticker",  "value"),
    State("tools-px-api-key", "value"),
    prevent_initial_call=True,
)
def _px_details(n, ticker, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        data = client._get(f"/v3/reference/tickers/{tk}")
        info = data.get("results", {})
    except Exception as e:
        return _px_error(e)
    if not info:
        return _px_error("No details found.")
    import pandas as pd
    df = pd.DataFrame([{"Field": k, "Value": str(v)} for k, v in info.items()])
    return _px_df_grid(df, height=min(40 + len(df) * 40, 500))


@callback(
    Output("tools-px-news-content", "children"),
    Input("tools-px-news-btn", "n_clicks"),
    State("tools-px-ticker",    "value"),
    State("tools-px-news-from", "value"),
    State("tools-px-news-to",   "value"),
    State("tools-px-news-max",  "value"),
    State("tools-px-api-key",   "value"),
    prevent_initial_call=True,
)
def _px_news(n, ticker, from_date, to_date, max_art, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        df = client.get_news(
            ticker=tk,
            from_date=from_date or (date.today() - timedelta(days=30)).isoformat(),
            to_date=to_date or date.today().isoformat(),
            limit=int(max_art or 20),
        )
    except Exception as e:
        return _px_error(e)
    if df.empty:
        return _px_error("No news found.")
    show_cols = [c for c in ["date", "published_utc", "title", "description"] if c in df.columns]
    return _px_df_grid(df[show_cols].head(int(max_art or 20)), height=360)


@callback(
    Output("tools-px-fin-content", "children"),
    Input("tools-px-fin-btn", "n_clicks"),
    State("tools-px-ticker",       "value"),
    State("tools-px-fin-timeframe","value"),
    State("tools-px-fin-periods",  "value"),
    State("tools-px-api-key",      "value"),
    prevent_initial_call=True,
)
def _px_financials(n, ticker, timeframe, periods, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        params = {
            "ticker": tk,
            "timeframe": timeframe or "quarterly",
            "limit": int(periods or 8),
            "order": "desc",
            "include_sources": "false",
        }
        data = client._get("/vX/reference/financials", params)
        results = data.get("results", [])
    except Exception as e:
        return _px_error(e)
    if not results:
        return _px_error("No financial data found.")

    import pandas as pd
    rows = []
    for r in results:
        fin = r.get("financials", {})
        ic  = fin.get("income_statement", {})
        row = {
            "Period":    r.get("fiscal_period"),
            "End Date":  r.get("end_date"),
            "Revenue":   ic.get("revenues", {}).get("value"),
            "Net Income":ic.get("net_income_loss", {}).get("value"),
            "EPS Basic": ic.get("basic_earnings_per_share", {}).get("value"),
            "EPS Diluted":ic.get("diluted_earnings_per_share", {}).get("value"),
        }
        rows.append(row)
    df = pd.DataFrame(rows)
    return _px_df_grid(df, height=min(40 + len(df) * 42, 400))


@callback(
    Output("tools-px-raw-content", "children"),
    Input("tools-px-raw-btn", "n_clicks"),
    State("tools-px-raw-path",   "value"),
    State("tools-px-raw-params", "value"),
    State("tools-px-api-key",    "value"),
    prevent_initial_call=True,
)
def _px_raw(n, path, params_json, api_key):
    if not n:
        return no_update
    if not path:
        return _px_error("Enter an endpoint path.")
    try:
        client = _get_px_client(api_key)
        try:
            params = json.loads(params_json or "{}")
        except Exception:
            params = {}
        data = client._get(path.strip(), params)
    except Exception as e:
        return _px_error(e)

    import pandas as pd
    # Try to render as a grid if there's a results list
    results = data.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        df = pd.DataFrame(results)
        return html.Div([
            html.Pre(json.dumps({k: v for k, v in data.items() if k != "results"},
                                indent=2),
                     style={"color": T.TEXT_SEC, "fontSize": "11px",
                            "marginBottom": "8px", "whiteSpace": "pre-wrap"}),
            _px_df_grid(df, height=400),
        ])
    # Otherwise show raw JSON
    return html.Pre(
        json.dumps(data, indent=2, default=str),
        style={"color": T.TEXT_PRIMARY, "fontSize": "12px",
               "backgroundColor": T.BG_ELEVATED,
               "border": f"1px solid {T.BORDER}",
               "borderRadius": "6px", "padding": "12px",
               "whiteSpace": "pre-wrap", "maxHeight": "500px",
               "overflowY": "auto"},
    )


@callback(
    Output("reg-detail-body", "children"),
    Input("reg-detail-select", "value"),
)
def _render_strategy_detail(slug: str):
    if not slug:
        return html.Div()
    try:
        from strategies.registry import STRATEGY_METADATA
    except ImportError:
        return dbc.Alert("Registry unavailable.", color="warning")

    meta = STRATEGY_METADATA.get(slug, {})

    _STATUS_COLOR = {
        "active": T.SUCCESS, "stub": T.WARNING,
        "inactive": T.TEXT_MUTED, "archived": T.DANGER,
    }
    _TYPE_COLOR = {"ai": "#a78bfa", "rule": T.ACCENT, "hybrid": T.WARNING}

    status_col = _STATUS_COLOR.get(meta.get("status", ""), T.TEXT_MUTED)
    type_col   = _TYPE_COLOR.get(meta.get("type", ""), T.TEXT_MUTED)

    def _badge(txt, color):
        return html.Span(txt, style={
            "background": f"{color}22", "color": color,
            "border": f"1px solid {color}55",
            "borderRadius": "10px", "padding": "2px 9px",
            "fontSize": "11px", "fontWeight": "600", "marginRight": "6px",
        })

    detail_rows = [
        ("Asset Class",  meta.get("asset_class", "—").replace("_", " ").title()),
        ("Typical Hold", f"{meta.get('typical_holding_days', '—')} days"),
        ("Target Sharpe", str(meta.get("target_sharpe", "—"))),
        ("ML Required",  "Yes" if meta.get("uses_ml") else "No"),
        ("Training Req", "Yes" if meta.get("requires_training") else "No"),
        ("Class Path",   meta.get("class_path") or "(stub)"),
    ]

    return dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.Div(meta.get("display_name", slug),
                         style={"color": T.TEXT_PRIMARY, "fontSize": "1.05rem",
                                "fontWeight": "700", "marginBottom": "8px"}),
                _badge(meta.get("type", "—").upper(), type_col),
                _badge(meta.get("status", "—").capitalize(), status_col),
            ], style={"marginBottom": "12px"}),
            html.P(meta.get("description", "No description."),
                   style={"color": T.TEXT_SEC, "fontSize": "13px",
                          "lineHeight": "1.6", "marginBottom": "16px"}),
            html.Table([
                html.Tr([
                    html.Td(label, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                          "fontWeight": "600", "textTransform": "uppercase",
                                          "letterSpacing": "0.06em", "padding": "6px 20px 6px 0",
                                          "whiteSpace": "nowrap"}),
                    html.Td(val, style={"color": T.ACCENT if label == "Class Path" else T.TEXT_SEC,
                                        "fontSize": "12px", "padding": "6px 0",
                                        "fontFamily": "JetBrains Mono, monospace"
                                        if label == "Class Path" else "inherit",
                                        "wordBreak": "break-all"}),
                ]) for label, val in detail_rows
            ], style={"width": "100%", "borderCollapse": "collapse"}),
        ]), style=T.STYLE_CARD), width=8),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div("Run a backtest in the Strategies tab to see live performance metrics.",
                     style={"color": T.TEXT_MUTED, "fontSize": "12px",
                            "lineHeight": "1.6", "textAlign": "center", "padding": "20px 0"}),
        ]), style=T.STYLE_CARD), width=4),
    ])


@callback(
    Output("tools-pc-rh-warning", "is_open"),
    Output("tools-pc-content", "children"),
    Input("tools-pc-run-btn", "n_clicks"),
    State("tools-pc-ticker",   "value"),
    State("tools-pc-expiry",   "value"),
    State("tools-pc-strike",   "value"),
    State("tools-pc-opt-type", "value"),
    prevent_initial_call=True,
)
def _run_price_check(n_clicks, ticker, expiry, strike, opt_type):
    from app import get_polygon_api_key
    ticker = (ticker or "SPY").upper().strip()
    api_key = get_polygon_api_key()

    rh_ok = _rh_available()
    show_warning = not rh_ok

    rows: list[html.Tr] = []

    def _flag(poly_val, rh_val, threshold: float) -> str:
        if poly_val is None or rh_val is None:
            return "—"
        diff = abs(poly_val - rh_val)
        return "✅" if diff <= threshold else f"⚠️ diff ${diff:.2f}"

    def _cell(txt, color=None, bold=False):
        s = {"fontSize": "13px", "padding": "6px 12px", "whiteSpace": "nowrap"}
        if color:
            s["color"] = color
        if bold:
            s["fontWeight"] = "700"
        return html.Td(txt, style=s)

    # ── Stock price row ────────────────────────────────────────────────────────
    poly_stock: float | None = None
    try:
        if api_key:
            from data.polygon_client import PolygonClient
            c = PolygonClient(api_key=api_key)
            snap = c._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}", {})
            day = snap.get("ticker", {}).get("day") or {}
            poly_stock = day.get("c") or None
    except Exception:
        pass

    rh_stock: float | None = _rh_get_stock_price(ticker) if rh_ok else None

    flag_s = _flag(poly_stock, rh_stock, 0.10)
    flag_color = T.SUCCESS if flag_s == "✅" else (T.WARNING if flag_s.startswith("⚠️") else T.TEXT_MUTED)
    rows.append(html.Tr([
        _cell("Stock last", bold=True),
        _cell(f"${poly_stock:.2f}" if poly_stock else "—"),
        _cell(f"${rh_stock:.2f}" if rh_stock else "—"),
        _cell(flag_s, color=flag_color),
        _cell("flag if diff > $0.10", color=T.TEXT_MUTED),
    ]))

    # ── Option mid / ask row ───────────────────────────────────────────────────
    if expiry and strike:
        poly_mid: float | None = None
        try:
            if api_key:
                from data.polygon_client import PolygonClient
                c = PolygonClient(api_key=api_key)
                sym_suffix = f"{expiry.replace('-', '')}{opt_type[0].upper()}{int(float(strike) * 1000):08d}"
                opt_sym = f"O:{ticker}{sym_suffix}"
                snap = c._get(f"/v3/snapshot/options/{ticker}/{opt_sym}", {})
                details = snap.get("results", {}) or {}
                day = details.get("day") or {}
                bid = day.get("bid") or 0
                ask = day.get("ask") or 0
                if bid and ask:
                    poly_mid = (bid + ask) / 2
        except Exception:
            pass

        rh_ask: float | None = _rh_get_option_ask(ticker, expiry, strike, opt_type) if rh_ok else None

        flag_o = _flag(poly_mid, rh_ask, 0.20)
        flag_o_color = T.SUCCESS if flag_o == "✅" else (T.WARNING if flag_o.startswith("⚠️") else T.TEXT_MUTED)
        rows.append(html.Tr([
            _cell(f"{opt_type.upper()} {strike} {expiry} mid/ask", bold=True),
            _cell(f"${poly_mid:.2f}" if poly_mid else "—"),
            _cell(f"${rh_ask:.2f}" if rh_ask else "—"),
            _cell(flag_o, color=flag_o_color),
            _cell("flag if diff > $0.20", color=T.TEXT_MUTED),
        ]))

    if not rh_ok:
        note = dbc.Alert(
            "Robinhood prices unavailable — showing Polygon only. Configure RH credentials to enable comparison.",
            color="secondary",
            style={"fontSize": "12px", "padding": "6px 12px", "marginBottom": "10px"},
        )
    else:
        note = html.Div()

    hdr_style = {"fontSize": "11px", "fontWeight": "700", "color": T.TEXT_MUTED,
                 "padding": "4px 12px", "borderBottom": f"1px solid {T.BORDER}",
                 "textTransform": "uppercase", "letterSpacing": "0.05em"}
    table = html.Table([
        html.Thead(html.Tr([
            html.Th("Instrument", style=hdr_style),
            html.Th("Polygon", style=hdr_style),
            html.Th("Robinhood", style=hdr_style),
            html.Th("Status", style=hdr_style),
            html.Th("Threshold", style=hdr_style),
        ])),
        html.Tbody(rows, style={"backgroundColor": T.BG_CARD}),
    ], style={"width": "100%", "borderCollapse": "collapse",
              "border": f"1px solid {T.BORDER}", "borderRadius": "6px"})

    return show_warning, html.Div([note, table])
