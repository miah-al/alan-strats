"""
dash_app/pages/backtest.py
Backtest page — run any active strategy over a historical date range.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import (
    ALL, Input, Output, State, callback, dcc, html, no_update
)

from dash_app import theme as T

logger = logging.getLogger(__name__)

# ── Strategy registry ─────────────────────────────────────────────────────────

def _load_active_strategies() -> list[dict]:
    """Return [{label, value}, ...] for all active strategies."""
    try:
        from strategies.registry import STRATEGY_METADATA
        opts = []
        for slug, meta in STRATEGY_METADATA.items():
            if meta.get("status") == "active":
                icon = meta.get("icon", "")
                name = meta.get("display_name", slug)
                opts.append({"label": f"{icon} {name}".strip(), "value": slug})
        return opts
    except Exception:
        return []


_STRATEGY_OPTIONS = _load_active_strategies()
_DEFAULT_SLUG = _STRATEGY_OPTIONS[0]["value"] if _STRATEGY_OPTIONS else None

# ── Backtest runner (built by parallel agent) ─────────────────────────────────

def _run_backtest(slug: str, ticker: str, from_date: str, to_date: str,
                  params: dict) -> dict:
    try:
        from dash_app.backtest_runner import run_backtest
        return run_backtest(slug, ticker, from_date, to_date, params)
    except ImportError:
        return {"ok": False, "error": "backtest_runner not available yet"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

# ── Metric card (matches blotter.py pattern) ──────────────────────────────────

def _metric_card(label: str, value: str, subtitle: str, color: str) -> dbc.Col:
    return dbc.Col(
        dbc.Card(
            dbc.CardBody([
                html.Div(label, style={
                    "color": T.TEXT_MUTED, "fontSize": "10px", "fontWeight": "700",
                    "textTransform": "uppercase", "letterSpacing": "0.08em",
                }),
                html.Div(value, style={
                    "color": color, "fontSize": "1.8rem", "fontWeight": "700",
                    "fontFamily": "JetBrains Mono, monospace", "lineHeight": "1.2",
                    "marginTop": "4px",
                }),
                html.Div(subtitle, style={
                    "color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "4px",
                }),
            ]),
            style={**T.STYLE_CARD, "borderLeft": f"3px solid {color}", "padding": "0"},
        ),
        xs=12, sm=6, lg=3,
    )


# ── Param panel builder ───────────────────────────────────────────────────────

def _build_param_control(p: dict) -> html.Div:
    """Build a single param control wrapped in a labelled div."""
    key = p["key"]
    label = p.get("label", key)
    ptype = p.get("type", "slider")
    default = p.get("default")
    help_text = p.get("help", "")
    ctrl_id = {"type": "bt-param", "index": key}

    label_el = html.Label(
        label,
        style={"color": T.TEXT_SEC, "fontSize": "12px",
               "fontWeight": "500", "marginBottom": "4px"},
    )

    if ptype == "checkbox":
        ctrl = dbc.Checklist(
            options=[{"label": "", "value": "checked"}],
            value=["checked"] if default else [],
            id=ctrl_id,
            switch=True,
            style={"marginTop": "4px"},
        )
    elif ptype == "select_slider":
        options = p.get("options", [])
        ctrl = dcc.Slider(
            id=ctrl_id,
            min=0,
            max=len(options) - 1,
            step=1,
            value=options.index(default) if default in options else 0,
            marks={i: str(v) for i, v in enumerate(options)},
            tooltip={"always_visible": False},
        )
    elif ptype in ("int", "float"):
        mn = p.get("min", 0)
        mx = p.get("max", 100)
        step = p.get("step", 1 if ptype == "int" else 0.01)
        ctrl = dcc.Slider(
            id=ctrl_id,
            min=mn,
            max=mx,
            step=step,
            value=default if default is not None else mn,
            tooltip={"placement": "bottom", "always_visible": False},
        )
    else:
        # default: slider
        mn = p.get("min", 0)
        mx = p.get("max", 1)
        step = p.get("step", 0.05)
        ctrl = dcc.Slider(
            id=ctrl_id,
            min=mn,
            max=mx,
            step=step,
            value=default if default is not None else mn,
            tooltip={"placement": "bottom", "always_visible": False},
        )

    children = [label_el, ctrl]
    if help_text:
        children.append(html.Div(
            help_text,
            style={"color": T.TEXT_MUTED, "fontSize": "10px", "marginTop": "3px",
                   "lineHeight": "1.4"},
        ))

    return html.Div(children, style={"marginBottom": "8px"})


def _render_params_panel(slug: str | None) -> html.Div:
    """Render all param controls for a strategy slug."""
    if not slug:
        return html.Div(
            "Select a strategy to see parameters.",
            style={"color": T.TEXT_MUTED, "fontSize": "13px"},
        )
    try:
        from strategies.registry import get_strategy
        strategy = get_strategy(slug)
        params = strategy.get_backtest_ui_params()
    except Exception as exc:
        return html.Div(
            f"Could not load params: {exc}",
            style={"color": T.WARNING, "fontSize": "12px"},
        )

    if not params:
        return html.Div(
            "No configurable parameters for this strategy.",
            style={"color": T.TEXT_MUTED, "fontSize": "13px"},
        )

    # Group by row
    rows: dict[int, list[dict]] = {}
    for p in params:
        r = p.get("row", 0)
        rows.setdefault(r, []).append(p)

    row_els = []
    for row_idx in sorted(rows.keys()):
        cols = []
        for p in sorted(rows[row_idx], key=lambda x: x.get("col", 0)):
            cols.append(dbc.Col(
                _build_param_control(p),
                xs=12, sm=6, md=4, lg=3,
            ))
        row_els.append(dbc.Row(cols, className="g-3"))

    return html.Div(row_els)


# ── Results renderer ──────────────────────────────────────────────────────────

def _safe_fmt(v: Any, fmt: str = ".2f", suffix: str = "",
              prefix: str = "") -> tuple[str, str]:
    """Return (formatted_string, color)."""
    try:
        fv = float(v)
        s = f"{prefix}{fv:{fmt}}{suffix}"
        color = T.SUCCESS if fv >= 0 else T.DANGER
        return s, color
    except Exception:
        return str(v) if v is not None else "—", T.TEXT_PRIMARY


def _render_results(data: dict) -> html.Div:
    if not data:
        return html.Div()

    if not data.get("ok"):
        return dbc.Alert(
            [html.Strong("Backtest failed: "), data.get("error", "Unknown error")],
            color="danger",
            style={"marginTop": "16px"},
        )

    metrics = data.get("metrics") or {}
    trades = data.get("trades") or []
    equity = data.get("equity_curve") or []

    # ── Metric cards ──────────────────────────────────────────────────────────
    total_return = metrics.get("total_return", 0)
    tr_str, tr_color = _safe_fmt(total_return * 100, ".1f", "%")

    sharpe = metrics.get("sharpe", 0)
    sh_str, sh_color = _safe_fmt(sharpe, ".2f")
    sh_color = T.SUCCESS if sharpe >= 1 else (T.WARNING if sharpe >= 0 else T.DANGER)

    max_dd = metrics.get("max_drawdown", 0)
    dd_str = f"{abs(max_dd) * 100:.1f}%"
    dd_color = T.DANGER if abs(max_dd) > 0.15 else T.WARNING

    win_rate = metrics.get("win_rate", 0)
    wr_str = f"{win_rate * 100:.1f}%"
    wr_color = T.SUCCESS if win_rate >= 0.5 else T.DANGER

    pf = metrics.get("profit_factor", 0)
    pf_str, pf_color = _safe_fmt(pf, ".2f")
    pf_color = T.SUCCESS if pf >= 1.5 else (T.WARNING if pf >= 1 else T.DANGER)

    cards = dbc.Row([
        _metric_card("TOTAL RETURN", tr_str,
                     f"{len(trades)} trades", tr_color),
        _metric_card("SHARPE RATIO", sh_str,
                     "Annualised", sh_color),
        _metric_card("MAX DRAWDOWN", dd_str,
                     "Peak-to-trough", dd_color),
        _metric_card("WIN RATE", wr_str,
                     f"{int(win_rate * len(trades))} / {len(trades)} wins", wr_color),
        _metric_card("PROFIT FACTOR", pf_str,
                     "Gross profit / gross loss", pf_color),
    ], className="g-3", style={"marginBottom": "20px"})

    # ── Equity curve ──────────────────────────────────────────────────────────
    equity_section = html.Div()
    if equity:
        dates = [e.get("date") for e in equity]
        values = [e.get("equity") for e in equity]
        final = values[-1] if values else 1.0
        line_color = T.SUCCESS if final >= (values[0] if values else 1.0) else T.DANGER

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates, y=values,
            mode="lines",
            line={"color": line_color, "width": 2},
            fill="tozeroy",
            fillcolor=line_color.replace(")", ", 0.08)").replace("rgb(", "rgba(")
                      if line_color.startswith("rgb") else
                      f"rgba(16,185,129,0.08)" if line_color == T.SUCCESS else
                      f"rgba(239,68,68,0.08)",
            name="Equity",
        ))
        fig.update_layout(
            paper_bgcolor=T.BG_CARD,
            plot_bgcolor=T.BG_ELEVATED,
            font={"color": T.TEXT_PRIMARY, "family": "Inter, sans-serif", "size": 12},
            margin={"t": 8, "b": 40, "l": 60, "r": 16},
            xaxis={"gridcolor": T.BORDER, "linecolor": T.BORDER},
            yaxis={"gridcolor": T.BORDER, "linecolor": T.BORDER, "title": "Equity ($)"},
            showlegend=False,
            height=280,
        )
        equity_section = dbc.Card(
            dbc.CardBody([
                html.Div("Equity Curve", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                    "textTransform": "uppercase", "letterSpacing": "0.08em",
                    "marginBottom": "8px",
                }),
                dcc.Graph(figure=fig, config={"displayModeBar": False}),
            ]),
            style={**T.STYLE_CARD, "marginBottom": "20px"},
        )

    # ── Trades table ──────────────────────────────────────────────────────────
    trades_section = html.Div()
    if trades:
        col_defs = [
            {"field": "date",        "headerName": "Entry Date",  "width": 120},
            {"field": "exit_date",   "headerName": "Exit Date",   "width": 120},
            {"field": "ticker",      "headerName": "Ticker",      "width": 90},
            {"field": "spread_type", "headerName": "Type",        "flex": 1, "minWidth": 120},
            {"field": "pnl",         "headerName": "P&L ($)",     "width": 100,
             "type": "numericColumn",
             "valueFormatter": {"function": "params.value != null ? '$' + params.value.toFixed(2) : '—'"},
             "cellStyle": {"function":
                 "params.value >= 0 ? {'color': '" + T.SUCCESS + "'} : {'color': '" + T.DANGER + "'}"}},
            {"field": "pnl_pct",     "headerName": "P&L %",       "width": 90,
             "type": "numericColumn",
             "valueFormatter": {"function": "params.value != null ? (params.value*100).toFixed(1) + '%' : '—'"},
             "cellStyle": {"function":
                 "params.value >= 0 ? {'color': '" + T.SUCCESS + "'} : {'color': '" + T.DANGER + "'}"}},
            {"field": "entry_value", "headerName": "Entry Val",   "width": 100,
             "type": "numericColumn",
             "valueFormatter": {"function": "params.value != null ? '$' + params.value.toFixed(2) : '—'"}},
            {"field": "exit_value",  "headerName": "Exit Val",    "width": 100,
             "type": "numericColumn",
             "valueFormatter": {"function": "params.value != null ? '$' + params.value.toFixed(2) : '—'"}},
        ]
        # Add label column if any trade has it
        if any("label" in t for t in trades):
            col_defs.append({"field": "label", "headerName": "Label", "flex": 1, "minWidth": 80})

        trades_section = dbc.Card(
            dbc.CardBody([
                html.Div("Trades", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                    "textTransform": "uppercase", "letterSpacing": "0.08em",
                    "marginBottom": "8px",
                }),
                dag.AgGrid(
                    rowData=trades,
                    columnDefs=col_defs,
                    defaultColDef={"resizable": True, "sortable": True, "filter": True},
                    className=T.AGGRID_THEME,
                    style={"height": "380px"},
                    dashGridOptions={"pagination": True, "paginationPageSize": 20},
                ),
            ]),
            style={**T.STYLE_CARD},
        )

    return html.Div([
        html.Hr(style={"borderColor": T.BORDER, "marginBottom": "20px"}),
        cards,
        equity_section,
        trades_section,
    ])


# ── Shared control styles ─────────────────────────────────────────────────────

_LBL = {"color": T.TEXT_SEC, "fontSize": "12px", "fontWeight": "600",
        "marginBottom": "4px", "display": "block"}
_INPUT = {"backgroundColor": T.BG_ELEVATED, "border": f"1px solid {T.BORDER}",
          "color": T.TEXT_PRIMARY, "fontSize": "13px"}


# ── Page layout ───────────────────────────────────────────────────────────────

def layout() -> html.Div:
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    return html.Div([
        # ── Header ─────────────────────────────────────────────────────────
        html.Div([
            html.H2("Backtest", style={
                "color": T.TEXT_PRIMARY, "fontWeight": "700",
                "fontSize": "1.5rem", "margin": "0",
            }),
            html.Div(
                "Run any active strategy over a historical date range.",
                style={"color": T.TEXT_MUTED, "fontSize": "13px", "marginTop": "4px"},
            ),
        ], style={"marginBottom": "24px"}),

        # ── Config card ────────────────────────────────────────────────────
        dbc.Card(
            dbc.CardBody([
                # Single row: strategy | ticker | start | end | run
                dbc.Row([
                    dbc.Col([
                        html.Label("Strategy", style=_LBL),
                        dbc.Select(
                            id="bt-strategy",
                            options=_STRATEGY_OPTIONS,
                            value=_DEFAULT_SLUG,
                            style={**T.STYLE_DROPDOWN},
                        ),
                    ], xs=12, md=4),
                    dbc.Col([
                        html.Label("Ticker", style=_LBL),
                        dbc.Input(
                            id="bt-ticker",
                            value="SPY",
                            placeholder="SPY",
                            style=_INPUT,
                        ),
                    ], xs=6, md=2),
                    dbc.Col([
                        html.Label("Start", style=_LBL),
                        dbc.Input(
                            id="bt-start",
                            type="date",
                            value="2022-01-01",
                            style=_INPUT,
                        ),
                    ], xs=6, md=2),
                    dbc.Col([
                        html.Label("End", style=_LBL),
                        dbc.Input(
                            id="bt-end",
                            type="date",
                            value=yesterday,
                            style=_INPUT,
                        ),
                    ], xs=6, md=2),
                    dbc.Col([
                        html.Label("\u00a0", style=_LBL),
                        dbc.Button(
                            "▶ Run",
                            id="bt-run-btn",
                            color="primary",
                            style={
                                "backgroundColor": T.ACCENT,
                                "borderColor": T.ACCENT,
                                "fontWeight": "600",
                                "fontSize": "13px",
                                "width": "100%",
                            },
                        ),
                    ], xs=6, md=2),
                ], className="g-3", align="end", style={"marginBottom": "20px"}),

                # Params
                html.Div([
                    html.Div("Parameters", style={
                        "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                        "textTransform": "uppercase", "letterSpacing": "0.06em",
                        "marginBottom": "12px",
                        "borderBottom": f"1px solid {T.BORDER}",
                        "paddingBottom": "6px",
                    }),
                    dcc.Loading(
                        html.Div(id="bt-params-panel"),
                        type="circle",
                        color=T.ACCENT,
                    ),
                ]),
            ]),
            style=T.STYLE_CARD,
        ),

        # ── Result store + spinner ─────────────────────────────────────────
        dcc.Store(id="bt-result-store"),
        dcc.Loading(
            html.Div(id="bt-results"),
            type="dot",
            color=T.ACCENT,
            style={"minHeight": "40px"},
        ),
    ], style=T.STYLE_PAGE)


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("bt-params-panel", "children"),
    Input("bt-strategy", "value"),
)
def update_params_panel(slug: str | None):
    return _render_params_panel(slug)


@callback(
    Output("bt-result-store", "data"),
    Input("bt-run-btn", "n_clicks"),
    State("bt-strategy", "value"),
    State("bt-ticker", "value"),
    State("bt-start", "date"),
    State("bt-end", "date"),
    State({"type": "bt-param", "index": ALL}, "value"),
    State({"type": "bt-param", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def run_backtest_cb(n_clicks, slug, ticker, start, end, param_values, param_ids):
    if not slug:
        return {"ok": False, "error": "No strategy selected."}
    if not ticker:
        return {"ok": False, "error": "No ticker entered."}

    # Reconstruct param dict
    # For checkbox: value is a list; non-empty means True
    params: dict[str, Any] = {}
    for pid, pval in zip(param_ids, param_values):
        key = pid["index"]
        # Checkbox returns list of selected values
        if isinstance(pval, list):
            params[key] = len(pval) > 0
        else:
            # select_slider: value is index, resolve back to option value
            params[key] = pval

    # Resolve select_slider indices to actual option values
    try:
        from strategies.registry import get_strategy
        strategy = get_strategy(slug)
        spec_list = strategy.get_backtest_ui_params()
        spec_map = {p["key"]: p for p in spec_list}
        for key, val in list(params.items()):
            spec = spec_map.get(key, {})
            if spec.get("type") == "select_slider":
                opts = spec.get("options", [])
                try:
                    params[key] = opts[int(val)]
                except (IndexError, TypeError):
                    pass
    except Exception:
        pass

    result = _run_backtest(slug, ticker.upper().strip(), start, end, params)
    return result


@callback(
    Output("bt-results", "children"),
    Input("bt-result-store", "data"),
)
def render_results(data):
    if not data:
        return html.Div()
    return _render_results(data)
