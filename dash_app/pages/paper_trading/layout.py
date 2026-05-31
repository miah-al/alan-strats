"""
dash_app/pages/paper_trading/layout.py — the Paper Trading view.

Header, metric row, the five tabs (Open/Closed/Transactions/Performance/Risk),
the three modals (position detail, close-confirm, delete-confirm) and the
stores + refresh interval. Every component id is preserved byte-identically.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html, dcc

from dash_app import theme as T

from dash_app.pages.paper_trading.builders import (
    _grid, _OPEN_COLS, _CLOSED_COLS, _TXNS_COLS,
)


# ── Layout ────────────────────────────────────────────────────────────────────

def layout() -> html.Div:
    modal = dbc.Modal([
        dbc.ModalHeader(
            dbc.ModalTitle(id="pt-modal-title", children="Position Detail"),
            style={"backgroundColor": T.BG_ELEVATED, "borderBottom": f"1px solid {T.BORDER}"},
            close_button=True,
        ),
        dbc.ModalBody(
            dcc.Loading(
                html.Div(id="pt-modal-body"),
                type="circle", color=T.ACCENT,
            ),
            style={"backgroundColor": T.BG_BASE, "padding": "20px"},
        ),
        dbc.ModalFooter([
            dbc.Button(
                "Close Position", id="pt-close-btn", color="danger", size="sm",
                style={"marginRight": "8px"},
            ),
            dbc.Button(
                "Dismiss", id="pt-modal-dismiss", color="secondary", size="sm",
            ),
        ], style={"backgroundColor": T.BG_ELEVATED, "borderTop": f"1px solid {T.BORDER}"}),
    ], id="pt-modal", size="xl", is_open=False, scrollable=True)

    return html.Div([
        html.Div([
            html.Div([
                html.H2("Paper Trading", style={
                    "color": T.TEXT_PRIMARY, "fontSize": "1.35rem",
                    "fontWeight": "700", "marginBottom": "0",
                }),
            ]),
            dbc.Button(
                "Refresh", id="pt-refresh-btn", size="sm", outline=True,
                style={"borderColor": T.BORDER, "color": T.TEXT_SEC, "fontSize": "12px"},
            ),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "center", "marginBottom": "16px"}),

        html.Div(id="pt-metric-row", style={"marginBottom": "16px"}),

        dbc.Tabs([
            dbc.Tab(label="Open Positions", tab_id="open", children=[
                html.Div(style={"height": "12px"}),
                html.P(
                    "Click a row to view position detail and payoff chart.",
                    style={"color": T.TEXT_MUTED, "fontSize": "12px", "marginBottom": "4px"},
                ),
                dcc.Loading(_grid("pt-open-grid", _OPEN_COLS),
                            type="circle", color=T.ACCENT),
            ]),
            dbc.Tab(label="Closed Positions", tab_id="closed", children=[
                html.Div(style={"height": "12px"}),
                html.Div(id="pt-closed-chart", style={"marginBottom": "16px"}),
                dcc.Loading(_grid("pt-closed-grid", _CLOSED_COLS),
                            type="circle", color=T.ACCENT),
            ]),
            dbc.Tab(label="Transactions", tab_id="txns", children=[
                html.Div(style={"height": "12px"}),
                # Delete controls
                dbc.Row([
                    dbc.Col(dbc.Card(dbc.CardBody([
                        html.Div("Delete by date", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                                           "fontWeight": "600", "marginBottom": "8px"}),
                        dcc.Dropdown(id="pt-del-date-picker", placeholder="Select date…",
                                     clearable=True, className="dash-dropdown",
                                     style={"fontSize": "12px", "marginBottom": "8px",
                                            "backgroundColor": T.BG_ELEVATED}),
                        dbc.Button("Delete this date", id="pt-del-date-btn", color="danger",
                                   size="sm", outline=True, style={"width": "100%", "fontSize": "12px"}),
                    ]), style={**T.STYLE_CARD, "padding": "12px"}), width=4),
                    dbc.Col(dbc.Card(dbc.CardBody([
                        html.Div("Delete today only", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                                              "fontWeight": "600", "marginBottom": "8px"}),
                        html.Div(id="pt-del-today-count",
                                 style={"color": T.TEXT_MUTED, "fontSize": "12px", "marginBottom": "8px"}),
                        dbc.Button("Delete today's trades", id="pt-del-today-btn", color="danger",
                                   size="sm", outline=True, style={"width": "100%", "fontSize": "12px"}),
                    ]), style={**T.STYLE_CARD, "padding": "12px"}), width=4),
                    dbc.Col(dbc.Card(dbc.CardBody([
                        html.Div("Delete everything", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                                              "fontWeight": "600", "marginBottom": "8px"}),
                        html.Div(id="pt-del-all-count",
                                 style={"color": T.TEXT_MUTED, "fontSize": "12px", "marginBottom": "8px"}),
                        dbc.Button("Delete ALL transactions", id="pt-del-all-btn", color="danger",
                                   size="sm", style={"width": "100%", "fontSize": "12px"}),
                    ]), style={**T.STYLE_CARD, "padding": "12px"}), width=4),
                ], className="g-2", style={"marginBottom": "12px"}),
                html.Div(id="pt-delete-status-msg", style={"marginBottom": "8px"}),
                # Cash record form
                dbc.Card(dbc.CardBody([
                    html.Div("Record Cash Movement", style={
                        "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                        "textTransform": "uppercase", "marginBottom": "10px",
                    }),
                    dbc.Row([
                        dbc.Col(dbc.Select(
                            id="pt-cash-dir",
                            options=[{"label": "Deposit", "value": "DEPOSIT"},
                                     {"label": "Withdrawal", "value": "WITHDRAWAL"}],
                            value="DEPOSIT",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                                   "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY},
                        ), width=3),
                        dbc.Col(dbc.Input(
                            id="pt-cash-amount", type="number", placeholder="Amount",
                            min=0, step=100,
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                                   "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY},
                        ), width=3),
                        dbc.Col(dbc.Input(
                            id="pt-cash-notes", type="text", placeholder="Notes (optional)",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                                   "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY},
                        ), width=4),
                        dbc.Col(dbc.Button(
                            "Record", id="pt-cash-save", color="primary", size="sm",
                            style={"backgroundColor": T.ACCENT, "border": "none",
                                   "fontSize": "13px", "width": "100%"},
                        ), width=2),
                    ], align="center"),
                    html.Div(id="pt-cash-status", style={"marginTop": "6px"}),
                ]), style={**T.STYLE_CARD, "marginBottom": "12px"}),
                # Filters
                dbc.Card(dbc.CardBody([
                    dbc.Row([
                        dbc.Col(dbc.Input(
                            id="pt-txn-search", type="text",
                            placeholder="Search symbol / strategy / notes…",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                                   "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY},
                        ), width=4),
                        dbc.Col(dcc.Dropdown(
                            id="pt-txn-filter-type", placeholder="Security Type",
                            clearable=True, className="dash-dropdown",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED},
                        ), width=2),
                        dbc.Col(dcc.Dropdown(
                            id="pt-txn-filter-dir", placeholder="Direction",
                            clearable=True, className="dash-dropdown",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED},
                        ), width=2),
                        dbc.Col(dcc.Dropdown(
                            id="pt-txn-filter-strat", placeholder="Strategy",
                            clearable=True, className="dash-dropdown",
                            style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED},
                        ), width=4),
                    ], align="center"),
                ]), style={**T.STYLE_CARD, "marginBottom": "8px", "padding": "8px"}),
                html.Div(id="pt-txn-count", style={
                    "color": T.TEXT_MUTED, "fontSize": "12px", "marginBottom": "4px",
                }),
                dcc.Loading(_grid("pt-txns-grid", _TXNS_COLS),
                            type="circle", color=T.ACCENT),
            ]),
            dbc.Tab(label="Performance", tab_id="perf", children=[
                html.Div(style={"height": "12px"}),
                dcc.Loading(
                    html.Div(id="pt-perf-chart"),
                    type="circle", color=T.ACCENT,
                ),
                html.Div(style={"height": "16px"}),
                dcc.Loading(
                    html.Div(id="pt-equity-curve"),
                    type="circle", color=T.ACCENT,
                ),
            ]),
            dbc.Tab(label="Risk", tab_id="risk", children=[
                html.Div(style={"height": "12px"}),
                # ── Config row ───────────────────────────────────────────────
                dbc.Card(dbc.CardBody([
                    html.Div([
                        html.Div([
                            html.Label("Step size", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                "fontWeight": "600", "marginBottom": "4px"}),
                            dbc.Input(id="pt-risk-step", type="number", value=2, min=1, max=10, step=1,
                                      style={"width": "80px", "fontSize": "12px",
                                             "backgroundColor": T.BG_ELEVATED, "color": "#e5e7eb",
                                             "border": f"1px solid {T.BORDER}"}),
                        ]),
                        html.Div([
                            html.Label("Vol Up %", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                "fontWeight": "600", "marginBottom": "4px"}),
                            dbc.Input(id="pt-risk-vol-up", type="number", value=25, min=1, max=200,
                                      style={"width": "80px", "fontSize": "12px",
                                             "backgroundColor": T.BG_ELEVATED, "color": "#e5e7eb",
                                             "border": f"1px solid {T.BORDER}"}),
                        ]),
                        html.Div([
                            html.Label("Vol Down %", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                "fontWeight": "600", "marginBottom": "4px"}),
                            dbc.Input(id="pt-risk-vol-down", type="number", value=25, min=1, max=200,
                                      style={"width": "80px", "fontSize": "12px",
                                             "backgroundColor": T.BG_ELEVATED, "color": "#e5e7eb",
                                             "border": f"1px solid {T.BORDER}"}),
                        ]),
                        html.Div([
                            html.Label("Default IV %", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                "fontWeight": "600", "marginBottom": "4px"}),
                            dbc.Input(id="pt-risk-iv-default", type="number", value=20, min=1, max=300,
                                      style={"width": "80px", "fontSize": "12px",
                                             "backgroundColor": T.BG_ELEVATED, "color": "#e5e7eb",
                                             "border": f"1px solid {T.BORDER}"}),
                        ]),
                        html.Div([
                            html.Label("Rate %", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                "fontWeight": "600", "marginBottom": "4px"}),
                            dbc.Input(id="pt-risk-rate", type="number", value=4.3, min=0, max=20, step=0.1,
                                      style={"width": "80px", "fontSize": "12px",
                                             "backgroundColor": T.BG_ELEVATED, "color": "#e5e7eb",
                                             "border": f"1px solid {T.BORDER}"}),
                        ]),
                        html.Div([
                            html.Label("\u00a0", style={"fontSize": "11px", "marginBottom": "4px",
                                                         "display": "block"}),
                            dbc.Button("Calculate", id="pt-risk-calc-btn", size="sm",
                                       color="primary", style={"fontSize": "12px"}),
                        ]),
                    ], style={"display": "flex", "gap": "16px", "alignItems": "flex-end",
                               "flexWrap": "wrap"}),
                ]), style={**T.STYLE_CARD, "marginBottom": "12px"}),

                dcc.Store(id="pt-risk-position", data="__all__"),
                dcc.Store(id="pt-risk-leg",      data="__all__"),

                # Row 1: position pills
                html.Div(id="pt-risk-pos-pills", style={"marginBottom": "6px"}),
                # Row 2: leg pills (shown only when a position is selected)
                html.Div(id="pt-risk-leg-pills", style={"marginBottom": "10px"}),

                dcc.Loading(
                    html.Div(id="pt-risk-matrix"),
                    type="circle", color=T.ACCENT,
                ),
            ]),
        ], id="pt-tabs", active_tab="open",
           style={"borderBottom": f"1px solid {T.BORDER}"}),

        # Modal for position detail
        modal,

        # ── Close-trade confirmation modal ────────────────────────────────────
        dbc.Modal([
            dbc.ModalHeader(
                dbc.ModalTitle("Confirm Close Position"),
                style={"backgroundColor": T.BG_ELEVATED, "borderBottom": f"1px solid {T.BORDER}"},
            ),
            dbc.ModalBody([
                dbc.Alert(
                    "Each leg will close at its entry price (no live prices loaded). "
                    "Refresh live prices first for accurate fills.",
                    color="warning",
                    style={"fontSize": "12px", "marginBottom": "12px"},
                ),
                html.Div(id="pt-close-confirm-body"),
            ], style={"backgroundColor": T.BG_BASE}),
            dbc.ModalFooter([
                dbc.Button("Confirm Close", id="pt-close-confirm-btn", color="danger", size="sm",
                           style={"marginRight": "8px"}),
                dbc.Button("Cancel", id="pt-close-cancel-btn", color="secondary", size="sm"),
            ], style={"backgroundColor": T.BG_ELEVATED, "borderTop": f"1px solid {T.BORDER}"}),
        ], id="pt-close-confirm-modal", size="lg", is_open=False),

        # ── Delete confirmation modal ─────────────────────────────────────────
        dbc.Modal([
            dbc.ModalHeader(
                dbc.ModalTitle("Confirm Delete"),
                style={"backgroundColor": T.BG_ELEVATED, "borderBottom": f"1px solid {T.BORDER}"},
            ),
            dbc.ModalBody(
                html.Div(id="pt-delete-confirm-body"),
                style={"backgroundColor": T.BG_BASE},
            ),
            dbc.ModalFooter([
                dbc.Button("Confirm Delete", id="pt-delete-confirm-btn", color="danger", size="sm",
                           style={"marginRight": "8px"}),
                dbc.Button("Cancel", id="pt-delete-cancel-btn", color="secondary", size="sm"),
            ], style={"backgroundColor": T.BG_ELEVATED, "borderTop": f"1px solid {T.BORDER}"}),
        ], id="pt-delete-modal", size="md", is_open=False),

        # Stores
        dcc.Store(id="pt-selected-tgid",    data=""),
        dcc.Store(id="pt-delete-action",    data=""),   # "date:{d}", "today", "all"
        dcc.Store(id="pt-delete-status",    data=""),

        dcc.Interval(id="pt-refresh", interval=60_000, n_intervals=0),
        dcc.Location(id="pt-url", refresh=False),
    ], style=T.STYLE_PAGE)
