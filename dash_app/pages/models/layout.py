# -*- coding: utf-8 -*-
"""
dash_app/pages/models - layout (tab builders + top-level layout()).

Builds every Options/Rates sub-tab and assembles the page. Adopts the shared
design system (dash_app.ui) for the page header + page surface; the dense,
strategy-specific tiles/sliders come from dash_app.pages.models.pricing.

Split out of the original monolithic models.py. Component IDs are unchanged.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html, dcc, dash_table

from dash_app import theme as T
from dash_app.ui import tokens as D, components as C

from dash_app.pages.models.pricing import _title, _tile, _slider


# ═══════════════════════════════════════════════════════════════════════════
# Options — European
# ═══════════════════════════════════════════════════════════════════════════

def _european_tab() -> html.Div:
    return dbc.Row([
        # Inputs
        dbc.Col([
            html.Div([
                _title("Inputs — Black-Scholes European"),
                _slider("eu-S",  "Spot S",     50, 500, 0.5, 100, ".2f"),
                _slider("eu-K",  "Strike K",   50, 500, 0.5, 100, ".2f"),
                _slider("eu-T",  "T (years)",  0.01, 5.0, 0.01, 1.0, ".2f"),
                _slider("eu-r",  "r",          -0.05, 0.20, 0.0005, 0.05, ".3%"),
                _slider("eu-q",  "q (div yld)", 0.0, 0.10, 0.0005, 0.0,  ".3%"),
                _slider("eu-sig","σ",          0.01, 1.50, 0.005, 0.20, ".2%"),
                dbc.RadioItems(
                    id="eu-cp", options=[{"label":"Call","value":"call"},
                                          {"label":"Put","value":"put"}],
                    value="call", inline=True, style={"marginTop": "6px"},
                ),
            ], style=T.STYLE_CARD),
        ], md=4),
        # Outputs
        dbc.Col([
            html.Div([
                _title("Price & Greeks"),
                dbc.Row([
                    dbc.Col(_tile("Price", "eu-price"), md=3),
                    dbc.Col(_tile("Delta", "eu-delta"), md=3),
                    dbc.Col(_tile("Gamma", "eu-gamma"), md=3),
                    dbc.Col(_tile("Vega",  "eu-vega", "/1 vol pt"), md=3),
                ], style={"marginBottom": "10px"}),
                dbc.Row([
                    dbc.Col(_tile("Theta", "eu-theta", "/yr"), md=3),
                    dbc.Col(_tile("Rho",   "eu-rho"),   md=3),
                    dbc.Col(_tile("Vanna", "eu-vanna"), md=3),
                    dbc.Col(_tile("Vomma", "eu-vomma"), md=3),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="eu-chart-price"), label="Price vs Spot"),
                dbc.Tab(dcc.Graph(id="eu-chart-greeks"), label="Greeks vs Spot"),
                dbc.Tab(dcc.Graph(id="eu-chart-gamma-surf"), label="Gamma Surface"),
                dbc.Tab(dcc.Graph(id="eu-chart-term"), label="Term Structure"),
                dbc.Tab(dcc.Graph(id="eu-chart-vol"),  label="Price vs σ"),
            ]),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Options — American (CRR)
# ═══════════════════════════════════════════════════════════════════════════

def _american_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Inputs — CRR American"),
                _slider("am-S",  "Spot S",     50, 500, 0.5, 100, ".2f"),
                _slider("am-K",  "Strike K",   50, 500, 0.5, 100, ".2f"),
                _slider("am-T",  "T (years)",  0.01, 5.0, 0.01, 1.0, ".2f"),
                _slider("am-r",  "r",          -0.05, 0.20, 0.0005, 0.05, ".3%"),
                _slider("am-q",  "q",          0.0, 0.10, 0.0005, 0.0, ".3%"),
                _slider("am-sig","σ",          0.01, 1.50, 0.005, 0.20, ".2%"),
                _slider("am-N",    "Binomial steps (pricing)", 50, 2000, 50, 500, ".0f"),
                _slider("am-Nviz", "Tree viz steps", 4, 30, 1, 14, ".0f"),
                dbc.RadioItems(
                    id="am-cp", options=[{"label":"Call","value":"call"},
                                          {"label":"Put","value":"put"}],
                    value="put", inline=True, style={"marginTop": "6px"},
                ),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Price & FD Greeks"),
                dbc.Row([
                    dbc.Col(_tile("Price (American)", "am-price"), md=3),
                    dbc.Col(_tile("Early-Exer. Premium", "am-eep"), md=3),
                    dbc.Col(_tile("Delta", "am-delta"), md=3),
                    dbc.Col(_tile("Gamma", "am-gamma"), md=3),
                ], style={"marginBottom": "10px"}),
                dbc.Row([
                    dbc.Col(_tile("Vega",  "am-vega"), md=3),
                    dbc.Col(_tile("Theta", "am-theta"), md=3),
                    dbc.Col(_tile("European Price", "am-euro"), md=3),
                    dbc.Col(_tile("BS Convergence N", "am-conv", "N"), md=3),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="am-chart-stock-tree"),  label="Stock Tree"),
                dbc.Tab(dcc.Graph(id="am-chart-option-tree"), label="Option Tree"),
                dbc.Tab(dcc.Graph(id="am-chart-boundary"),     label="Early-Exercise Boundary"),
                dbc.Tab(dcc.Graph(id="am-chart-price"),        label="Price vs Spot"),
                dbc.Tab(dcc.Graph(id="am-chart-conv"),         label="CRR Convergence"),
            ]),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Options — Black-76 (futures/forwards)
# ═══════════════════════════════════════════════════════════════════════════

def _black76_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Inputs — Black-76 (Futures/Forwards)"),
                _slider("b76-F",  "Forward F",  50, 500, 0.5, 100, ".2f"),
                _slider("b76-K",  "Strike K",   50, 500, 0.5, 100, ".2f"),
                _slider("b76-T",  "T (years)",  0.01, 5.0, 0.01, 1.0, ".2f"),
                _slider("b76-r",  "r",          -0.05, 0.20, 0.0005, 0.05, ".3%"),
                _slider("b76-sig","σ",          0.01, 1.50, 0.005, 0.20, ".2%"),
                dbc.RadioItems(
                    id="b76-cp", options=[{"label":"Call","value":"call"},
                                           {"label":"Put","value":"put"}],
                    value="call", inline=True, style={"marginTop": "6px"},
                ),
                html.Div("Black-76 is used for options on futures, swaptions, "
                         "caplets/floorlets — anywhere the underlying is a forward.",
                         style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                "fontStyle": "italic", "marginTop": "10px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Price & Greeks"),
                dbc.Row([
                    dbc.Col(_tile("Price", "b76-price"), md=3),
                    dbc.Col(_tile("Delta (dF)", "b76-delta"), md=3),
                    dbc.Col(_tile("Gamma", "b76-gamma"), md=3),
                    dbc.Col(_tile("Vega",  "b76-vega", "/1 vol pt"), md=3),
                ], style={"marginBottom": "10px"}),
                dbc.Row([
                    dbc.Col(_tile("Theta", "b76-theta", "/yr"), md=3),
                    dbc.Col(_tile("Rho",   "b76-rho"),   md=3),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="b76-chart-price"),  label="Price vs Forward"),
                dbc.Tab(dcc.Graph(id="b76-chart-greeks"), label="Greeks vs Forward"),
            ]),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Options — Barrier
# ═══════════════════════════════════════════════════════════════════════════

def _barrier_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Inputs — Barrier (Reiner-Rubinstein)"),
                _slider("br-S",   "Spot S",    50, 500, 0.5, 100, ".2f"),
                _slider("br-K",   "Strike K",  50, 500, 0.5, 100, ".2f"),
                _slider("br-H",   "Barrier H", 50, 500, 0.5, 120, ".2f"),
                _slider("br-T",   "T (years)", 0.01, 5.0, 0.01, 0.5, ".2f"),
                _slider("br-r",   "r",         -0.05, 0.20, 0.0005, 0.05, ".3%"),
                _slider("br-q",   "q",         0.0, 0.10, 0.0005, 0.0, ".3%"),
                _slider("br-sig", "σ",         0.01, 1.50, 0.005, 0.25, ".2%"),
                dbc.Row([
                    dbc.Col(dbc.RadioItems(id="br-cp",
                        options=[{"label":"Call","value":"call"},
                                  {"label":"Put","value":"put"}],
                        value="call", inline=True), md=6),
                    dbc.Col(dbc.RadioItems(id="br-io",
                        options=[{"label":"Knock-In","value":"in"},
                                  {"label":"Knock-Out","value":"out"}],
                        value="in", inline=True), md=6),
                ]),
                dbc.RadioItems(id="br-ud",
                    options=[{"label":"Up-barrier","value":"up"},
                              {"label":"Down-barrier","value":"down"}],
                    value="up", inline=True, style={"marginTop":"6px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Price & Hit Probability"),
                dbc.Row([
                    dbc.Col(_tile("Price (RR)",    "br-price"), md=3),
                    dbc.Col(_tile("MC Price",      "br-mc"),    md=3),
                    dbc.Col(_tile("MC ± SE",       "br-mc-se"), md=3),
                    dbc.Col(_tile("P(Hit H)",      "br-phit"),  md=3),
                ], style={"marginBottom": "10px"}),
                dbc.Row([
                    dbc.Col(_tile("Vanilla BS",    "br-vanilla"), md=3),
                    dbc.Col(_tile("IN+OUT Check",  "br-check"),   md=9),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="br-chart-price"),     label="Price vs Spot"),
                dbc.Tab(dcc.Graph(id="br-chart-phit-term"), label="Hit Prob vs T"),
            ]),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Options — Digital
# ═══════════════════════════════════════════════════════════════════════════

def _digital_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Inputs — Digital/Binary"),
                _slider("dg-S",   "Spot S",    50, 500, 0.5, 100, ".2f"),
                _slider("dg-K",   "Strike K",  50, 500, 0.5, 100, ".2f"),
                _slider("dg-T",   "T (years)", 0.01, 5.0, 0.01, 1.0, ".2f"),
                _slider("dg-r",   "r",         -0.05, 0.20, 0.0005, 0.05, ".3%"),
                _slider("dg-q",   "q",         0.0, 0.10, 0.0005, 0.0, ".3%"),
                _slider("dg-sig", "σ",         0.01, 1.50, 0.005, 0.20, ".2%"),
                _slider("dg-cash","Cash payoff", 0.0, 100.0, 0.5, 1.0, ".2f"),
                dbc.RadioItems(id="dg-cp",
                    options=[{"label":"Call","value":"call"},
                              {"label":"Put","value":"put"}],
                    value="call", inline=True, style={"marginTop":"6px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Digital Prices"),
                dbc.Row([
                    dbc.Col(_tile("Cash-or-Nothing",  "dg-cash-price"), md=4),
                    dbc.Col(_tile("Asset-or-Nothing", "dg-asset-price"), md=4),
                    dbc.Col(_tile("C+P (cash) = e⁻ᵣᵀ·cash", "dg-parity"), md=4),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="dg-chart-price"), label="Price vs Spot"),
            ]),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Options — Asian
# ═══════════════════════════════════════════════════════════════════════════

def _asian_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Inputs — Asian (Average Price)"),
                _slider("as-S",   "Spot S",    50, 500, 0.5, 100, ".2f"),
                _slider("as-K",   "Strike K",  50, 500, 0.5, 100, ".2f"),
                _slider("as-T",   "T (years)", 0.01, 5.0, 0.01, 1.0, ".2f"),
                _slider("as-r",   "r",         -0.05, 0.20, 0.0005, 0.05, ".3%"),
                _slider("as-q",   "q",         0.0, 0.10, 0.0005, 0.0, ".3%"),
                _slider("as-sig", "σ",         0.01, 1.50, 0.005, 0.30, ".2%"),
                _slider("as-n",   "# Fixings", 1, 252, 1, 12, ".0f"),
                dbc.RadioItems(id="as-cp",
                    options=[{"label":"Call","value":"call"},
                              {"label":"Put","value":"put"}],
                    value="call", inline=True, style={"marginTop":"6px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Prices"),
                dbc.Row([
                    dbc.Col(_tile("Geometric (Kemna-Vorst)", "as-geo"), md=4),
                    dbc.Col(_tile("Arithmetic (MC+CV)",      "as-arith"), md=4),
                    dbc.Col(_tile("European BS",             "as-euro"), md=4),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="as-chart-vs-spot"), label="Price vs Spot"),
                dbc.Tab(dcc.Graph(id="as-chart-vs-n"),    label="Price vs # Fixings"),
            ]),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Rates — Curve
# ═══════════════════════════════════════════════════════════════════════════

_DEFAULT_CURVE_ROWS = [
    {"tenor": 0.25, "rate": 4.30},
    {"tenor": 0.5,  "rate": 4.35},
    {"tenor": 1.0,  "rate": 4.25},
    {"tenor": 2.0,  "rate": 4.00},
    {"tenor": 5.0,  "rate": 3.95},
    {"tenor": 10.0, "rate": 4.10},
    {"tenor": 20.0, "rate": 4.25},
    {"tenor": 30.0, "rate": 4.30},
]


def _curve_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Zero Curve Input (editable)"),
                dash_table.DataTable(
                    id="rc-curve-table",
                    columns=[
                        {"name": "Tenor (y)", "id": "tenor", "type": "numeric"},
                        {"name": "Zero rate (%)", "id": "rate", "type": "numeric"},
                    ],
                    data=[dict(r) for r in _DEFAULT_CURVE_ROWS],
                    editable=True, row_deletable=True,
                    style_table={"backgroundColor": T.BG_CARD},
                    style_cell={"backgroundColor": T.BG_ELEVATED,
                                 "color": T.TEXT_PRIMARY, "border": f"1px solid {T.BORDER}",
                                 "fontSize": "12px"},
                    style_header={"backgroundColor": T.BG_CARD, "color": T.TEXT_SEC},
                ),
                dbc.Button("+ Add Row", id="rc-add-row", size="sm",
                           color="secondary", style={"marginTop": "8px",
                                                      "fontSize": "11px"}),
                html.Div([
                    html.Label("Interpolation:", style={"color": T.TEXT_SEC,
                                                         "fontSize":"11px",
                                                         "marginTop":"12px",
                                                         "marginRight":"8px"}),
                    dcc.Dropdown(id="rc-interp",
                        options=[{"label":"Log-DF linear","value":"log_df"},
                                  {"label":"Linear on zeros","value":"linear_zero"},
                                  {"label":"Monotone cubic","value":"cubic_zero"}],
                        value="log_df", clearable=False,
                        style={"backgroundColor": T.BG_ELEVATED,
                                "color": T.TEXT_PRIMARY, "fontSize": "12px"}),
                ]),
            ], style=T.STYLE_CARD),
        ], md=5),
        dbc.Col([
            html.Div([
                _title("Curve Analytics"),
                dbc.Row([
                    dbc.Col(_tile("Short rate z(3m)", "rc-short"), md=4),
                    dbc.Col(_tile("Mid  rate z(5y)",  "rc-mid"),   md=4),
                    dbc.Col(_tile("Long rate z(30y)", "rc-long"),  md=4),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="rc-chart-zero-fwd"), label="Zero + Forward"),
                dbc.Tab(dcc.Graph(id="rc-chart-df"),        label="Discount Factor"),
                dbc.Tab(dcc.Graph(id="rc-chart-fwd-surf"),  label="Forward Surface"),
            ]),
        ], md=7),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Rates — Bond + Duration
# ═══════════════════════════════════════════════════════════════════════════

def _bond_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Bond Parameters"),
                _slider("bd-face", "Face value",    1, 1000, 1, 100, ".0f"),
                _slider("bd-cpn",  "Coupon rate",   0.0, 0.15, 0.00125, 0.05, ".3%"),
                _slider("bd-mat",  "Maturity (y)",  0.25, 30, 0.25, 5.0, ".2f"),
                _slider("bd-ytm",  "YTM",           -0.02, 0.20, 0.0005, 0.05, ".3%"),
                html.Label("Coupon freq", style={"color": T.TEXT_SEC,
                                                   "fontSize": "12px",
                                                   "marginTop": "10px"}),
                dcc.Dropdown(id="bd-freq",
                    options=[{"label":"Annual","value":1},
                              {"label":"Semi-annual","value":2},
                              {"label":"Quarterly","value":4},
                              {"label":"Monthly","value":12}],
                    value=2, clearable=False,
                    style={"backgroundColor": T.BG_ELEVATED,
                            "color": T.TEXT_PRIMARY, "fontSize": "12px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Price · Duration · DV01"),
                dbc.Row([
                    dbc.Col(_tile("PV",        "bd-pv"), md=3),
                    dbc.Col(_tile("Macaulay",  "bd-mac", "yrs"), md=3),
                    dbc.Col(_tile("Modified",  "bd-mod", "yrs"), md=3),
                    dbc.Col(_tile("Convexity", "bd-conv", "y²"), md=3),
                ], style={"marginBottom": "10px"}),
                dbc.Row([
                    dbc.Col(_tile("DV01",      "bd-dv01", "$"), md=3),
                    dbc.Col(_tile("Par Yield", "bd-par"),       md=3),
                    dbc.Col(_tile("Accrued",   "bd-acc"),       md=3),
                    dbc.Col(_tile("Clean",     "bd-clean"),     md=3),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="bd-chart-cf"),    label="Cash Flows"),
                dbc.Tab(dcc.Graph(id="bd-chart-pvy"),   label="PV vs YTM (Convexity)"),
                dbc.Tab(dcc.Graph(id="bd-chart-dvmat"), label="Duration vs Maturity"),
            ]),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Rates — Swap (IRS)
# ═══════════════════════════════════════════════════════════════════════════

def _swap_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Swap Parameters"),
                _slider("sw-not",   "Notional ($M)",  1, 500, 1, 10, ".0f"),
                _slider("sw-rate",  "Fixed rate",     0.0, 0.10, 0.0005, 0.04, ".3%"),
                _slider("sw-tenor", "Tenor (y)",      0.25, 30, 0.25, 5.0, ".2f"),
                _slider("sw-curve", "Flat curve base",-0.02, 0.10, 0.0005, 0.04, ".3%"),
                html.Label("Fixed freq", style={"color": T.TEXT_SEC,
                                                 "fontSize":"12px","marginTop":"10px"}),
                dcc.Dropdown(id="sw-ff",
                    options=[{"label":"Annual","value":1},{"label":"Semi","value":2},
                              {"label":"Quarterly","value":4}],
                    value=2, clearable=False,
                    style={"backgroundColor": T.BG_ELEVATED,
                            "color": T.TEXT_PRIMARY, "fontSize": "12px"}),
                dbc.RadioItems(id="sw-side",
                    options=[{"label":"Pay Fixed","value":True},
                              {"label":"Receive Fixed","value":False}],
                    value=True, inline=True, style={"marginTop":"10px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Swap Analytics"),
                dbc.Row([
                    dbc.Col(_tile("NPV",      "sw-npv", "$"), md=3),
                    dbc.Col(_tile("Par Rate", "sw-par"),      md=3),
                    dbc.Col(_tile("DV01",     "sw-dv01", "$"),md=3),
                    dbc.Col(_tile("Fixed leg PV","sw-fxleg"), md=3),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="sw-chart-cf"),  label="Cashflow Ladder"),
                dbc.Tab(dcc.Graph(id="sw-chart-npv"), label="NPV vs Rate Shift"),
            ]),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Rates — Callable bond (Hull-White)
# ═══════════════════════════════════════════════════════════════════════════

def _callable_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Callable Bond (Hull-White Tree)"),
                _slider("cb-face", "Face",        1, 1000, 1, 100, ".0f"),
                _slider("cb-cpn",  "Coupon rate", 0.0, 0.15, 0.00125, 0.06, ".3%"),
                _slider("cb-mat",  "Maturity (y)",1, 15, 0.25, 5.0, ".2f"),
                _slider("cb-curve","Flat curve",  0.0, 0.12, 0.0005, 0.05, ".3%"),
                _slider("cb-sig",  "Short-rate σ",0.001, 0.05, 0.0005, 0.015, ".3f"),
                _slider("cb-a",    "Mean reversion a", 0.005, 0.5, 0.005, 0.10, ".3f"),
                _slider("cb-ct",   "Call time (y)",0.25, 10.0, 0.25, 2.0, ".2f"),
                _slider("cb-cp",   "Call price",   50, 200, 0.5, 100, ".2f"),
                _slider("cb-N",    "Tree steps",   20, 150, 5, 40, ".0f"),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Valuation"),
                dbc.Row([
                    dbc.Col(_tile("Straight Bond",  "cb-straight"), md=3),
                    dbc.Col(_tile("Callable Bond",  "cb-cbl"),      md=3),
                    dbc.Col(_tile("Call Option $",  "cb-opt"),      md=3),
                    dbc.Col(_tile("Eff. Duration",  "cb-dur", "yrs"),md=3),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="cb-chart-shift"),  label="Price vs Curve Shift"),
            ]),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Options — SABR implied-vol smile
# ═══════════════════════════════════════════════════════════════════════════

def _sabr_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("SABR (Hagan 2002) — Implied-Vol Smile"),
                _slider("sb-F",     "Forward F", 50, 500, 0.5, 100, ".2f"),
                _slider("sb-T",     "T (years)", 0.05, 5.0, 0.05, 1.0, ".2f"),
                _slider("sb-alpha", "α (level)", 0.05, 1.50, 0.01, 0.30, ".2%"),
                _slider("sb-beta",  "β (CEV)",   0.0, 1.0, 0.05, 0.5, ".2f"),
                _slider("sb-rho",   "ρ (skew)",  -0.95, 0.95, 0.05, -0.30, ".2f"),
                _slider("sb-nu",    "ν (volvol)", 0.05, 2.0, 0.05, 0.40, ".2f"),
                html.Div("α sets the ATM level, ρ tilts the skew, ν controls the "
                         "wings (convexity). β fixes the backbone shape.",
                         style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                "fontStyle": "italic", "marginTop": "10px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("ATM vol + skew"),
                dbc.Row([
                    dbc.Col(_tile("ATM σ (Black)", "sb-atm"), md=4),
                    dbc.Col(_tile("25Δ Put Skew",   "sb-skew"), md=4),
                    dbc.Col(_tile("σ(K=F±10%) Diff","sb-wing"), md=4),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dcc.Graph(id="sb-chart-smile"),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Options — Heston
# ═══════════════════════════════════════════════════════════════════════════

def _heston_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Heston — Stochastic Vol"),
                _slider("hs-S",     "Spot S",     50, 500, 0.5, 100, ".2f"),
                _slider("hs-K",     "Strike K",   50, 500, 0.5, 100, ".2f"),
                _slider("hs-T",     "T (years)",  0.05, 5.0, 0.05, 1.0, ".2f"),
                _slider("hs-r",     "r",          -0.05, 0.20, 0.0005, 0.05, ".3%"),
                _slider("hs-q",     "q",          0.0, 0.10, 0.0005, 0.0, ".3%"),
                _slider("hs-v0",    "v₀ (var)",   0.001, 0.25, 0.005, 0.04, ".3f"),
                _slider("hs-kappa", "κ (rev spd)",0.1, 10.0, 0.1, 2.0, ".2f"),
                _slider("hs-theta", "θ (long var)",0.001, 0.25, 0.005, 0.04, ".3f"),
                _slider("hs-sigv",  "σ_v (volvol)",0.05, 2.0, 0.05, 0.30, ".2f"),
                _slider("hs-rho",   "ρ",          -0.95, 0.95, 0.05, -0.70, ".2f"),
                dbc.RadioItems(id="hs-cp",
                    options=[{"label":"Call","value":"call"},
                              {"label":"Put","value":"put"}],
                    value="call", inline=True, style={"marginTop":"6px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Heston vs Black-Scholes"),
                dbc.Row([
                    dbc.Col(_tile("Heston Price",  "hs-price"), md=4),
                    dbc.Col(_tile("BS Price (σ=√v₀)", "hs-bs"),  md=4),
                    dbc.Col(_tile("Heston − BS", "hs-diff"),     md=4),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dcc.Graph(id="hs-chart-smile"),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Options — Variance swap
# ═══════════════════════════════════════════════════════════════════════════

def _varswap_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Variance Swap — log-contract replication"),
                _slider("vs-S",   "Spot S",    50, 500, 0.5, 100, ".2f"),
                _slider("vs-T",   "T (years)", 0.05, 3.0, 0.05, 1.0, ".2f"),
                _slider("vs-r",   "r",         -0.05, 0.20, 0.0005, 0.05, ".3%"),
                _slider("vs-q",   "q",         0.0, 0.10, 0.0005, 0.0, ".3%"),
                _slider("vs-atm", "ATM σ",     0.05, 1.5, 0.01, 0.20, ".2%"),
                _slider("vs-skew","Skew coef", -0.005, 0.005, 0.0001, -0.0015, ".4f"),
                html.Div("Skew coef linearly shifts IV with moneyness: "
                         "σ(K) = ATM + skew · (K − S). Negative skew = put skew.",
                         style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                "fontStyle": "italic", "marginTop": "10px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Fair Variance & Vol"),
                dbc.Row([
                    dbc.Col(_tile("Fair K_var",      "vs-kvar"), md=3),
                    dbc.Col(_tile("Fair vol √K_var", "vs-fvol"), md=3),
                    dbc.Col(_tile("ATM vol",         "vs-avol"), md=3),
                    dbc.Col(_tile("Skew premium",    "vs-premium"), md=3),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dcc.Graph(id="vs-chart-weights"),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Options — Margrabe / Kirk spread
# ═══════════════════════════════════════════════════════════════════════════

def _spread_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Spread Options — Margrabe & Kirk"),
                _slider("sp-S1", "Asset 1 S₁", 50, 500, 0.5, 100, ".2f"),
                _slider("sp-S2", "Asset 2 S₂", 50, 500, 0.5, 100, ".2f"),
                _slider("sp-K",  "Strike K",   -50, 50, 0.5, 0.0,  ".2f"),
                _slider("sp-T",  "T (years)",  0.05, 3.0, 0.05, 1.0, ".2f"),
                _slider("sp-r",  "r",          -0.05, 0.20, 0.0005, 0.05, ".3%"),
                _slider("sp-s1", "σ₁",         0.01, 1.5, 0.01, 0.25, ".2%"),
                _slider("sp-s2", "σ₂",         0.01, 1.5, 0.01, 0.20, ".2%"),
                _slider("sp-rho","ρ",          -0.99, 0.99, 0.02, 0.30, ".2f"),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Spread Option Prices"),
                dbc.Row([
                    dbc.Col(_tile("Margrabe (K=0)", "sp-marg"), md=4),
                    dbc.Col(_tile("Kirk (K≠0)",    "sp-kirk"),  md=4),
                    dbc.Col(_tile("ρ sensitivity (dPrice/dρ)", "sp-corrd"), md=4),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dcc.Graph(id="sp-chart-rho"),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Rates — Caps / Floors
# ═══════════════════════════════════════════════════════════════════════════

def _caps_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("Caps / Floors (Black-76 strip)"),
                _slider("cp-strike","Strike",   -0.02, 0.15, 0.0005, 0.04, ".3%"),
                _slider("cp-tenor", "Tenor (y)",0.5, 15, 0.25, 5.0, ".2f"),
                _slider("cp-sigma", "Flat vol", 0.05, 1.5, 0.02, 0.30, ".2%"),
                _slider("cp-curve", "Flat curve base",-0.02, 0.10, 0.0005, 0.04, ".3%"),
                _slider("cp-not",   "Notional ($M)",1, 500, 1, 10, ".0f"),
                html.Label("Payment freq", style={"color":T.TEXT_SEC,"fontSize":"12px",
                                                    "marginTop":"10px"}),
                dcc.Dropdown(id="cp-freq",
                    options=[{"label":"Quarterly","value":4},{"label":"Semi","value":2}],
                    value=4, clearable=False,
                    style={"backgroundColor":T.BG_ELEVATED,"color":T.TEXT_PRIMARY,
                            "fontSize":"12px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Cap & Floor Prices"),
                dbc.Row([
                    dbc.Col(_tile("Cap Price",    "cp-cap"), md=3),
                    dbc.Col(_tile("Floor Price",  "cp-floor"), md=3),
                    dbc.Col(_tile("Cap − Floor",  "cp-diff"), md=3),
                    dbc.Col(_tile("# Caplets",    "cp-n"),    md=3),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dcc.Graph(id="cp-chart-ladder"),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Rates — European Swaption
# ═══════════════════════════════════════════════════════════════════════════

def _swaption_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("European Swaption (Black)"),
                _slider("sp2-exp",  "Expiry (y)",   0.25, 10, 0.25, 1.0, ".2f"),
                _slider("sp2-ten",  "Swap tenor (y)", 0.5, 30, 0.25, 5.0, ".2f"),
                _slider("sp2-K",    "Strike rate",  -0.02, 0.15, 0.0005, 0.04, ".3%"),
                _slider("sp2-sig",  "Swap-rate σ",  0.05, 1.5, 0.02, 0.25, ".2%"),
                _slider("sp2-curve","Flat curve base",-0.02, 0.10, 0.0005, 0.04, ".3%"),
                _slider("sp2-not",  "Notional ($M)",1, 500, 1, 10, ".0f"),
                dbc.RadioItems(id="sp2-side",
                    options=[{"label":"Payer","value":True},
                              {"label":"Receiver","value":False}],
                    value=True, inline=True, style={"marginTop":"8px"}),
            ], style=T.STYLE_CARD),
        ], md=4),
        dbc.Col([
            html.Div([
                _title("Swaption Price"),
                dbc.Row([
                    dbc.Col(_tile("Price",           "sp2-price"), md=3),
                    dbc.Col(_tile("Fwd Swap Rate",   "sp2-fsr"),   md=3),
                    dbc.Col(_tile("Annuity (PVBP)",  "sp2-ann"),   md=3),
                    dbc.Col(_tile("Vega ($)",        "sp2-vega"),  md=3),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dcc.Graph(id="sp2-chart"),
        ], md=8),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Rates — DV01 Ladder (SOFR Futures + Treasury Bonds)
# ═══════════════════════════════════════════════════════════════════════════

_DV01_DEFAULTS = [
    # SOFR futures (3-month contracts — DV01 ≈ $25 per contract · 1M notional)
    {"instrument": "SOFR SR3-Z4 (3m)",   "type": "sofr_fut", "notional_M": 1.0, "tenor": 0.25, "coupon": 0.0,  "position": 100},
    {"instrument": "SOFR SR3-H5 (3m)",   "type": "sofr_fut", "notional_M": 1.0, "tenor": 0.25, "coupon": 0.0,  "position": 100},
    {"instrument": "SOFR SR3-M5 (3m)",   "type": "sofr_fut", "notional_M": 1.0, "tenor": 0.25, "coupon": 0.0,  "position": 100},
    {"instrument": "SOFR SR3-U5 (3m)",   "type": "sofr_fut", "notional_M": 1.0, "tenor": 0.25, "coupon": 0.0,  "position": 100},
    # Treasury bonds
    {"instrument": "UST 2y 4.5%",  "type": "treasury", "notional_M": 10.0, "tenor": 2.0,  "coupon": 4.5, "position": 1},
    {"instrument": "UST 5y 4.0%",  "type": "treasury", "notional_M": 10.0, "tenor": 5.0,  "coupon": 4.0, "position": 1},
    {"instrument": "UST 10y 4.1%", "type": "treasury", "notional_M": 10.0, "tenor": 10.0, "coupon": 4.1, "position": 1},
    {"instrument": "UST 30y 4.3%", "type": "treasury", "notional_M": 10.0, "tenor": 30.0, "coupon": 4.3, "position": 1},
]


def _dv01_ladder_tab() -> html.Div:
    return dbc.Row([
        dbc.Col([
            html.Div([
                _title("DV01 Ladder — Portfolio of SOFR Futures + USTs"),
                html.Div("SOFR futures: DV01 ≈ $25 × contracts per $1M notional per contract. "
                         "Treasuries: priced on the zero curve and bumped ±1bp for DV01.",
                         style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                "fontStyle": "italic", "marginBottom": "10px"}),
                dash_table.DataTable(
                    id="dv-table",
                    columns=[
                        {"name":"Instrument", "id":"instrument"},
                        {"name":"Type",       "id":"type",
                         "presentation":"dropdown"},
                        {"name":"Notional $M","id":"notional_M","type":"numeric"},
                        {"name":"Tenor (y)",  "id":"tenor",     "type":"numeric"},
                        {"name":"Coupon %",   "id":"coupon",    "type":"numeric"},
                        {"name":"Contracts/Notion","id":"position","type":"numeric"},
                    ],
                    dropdown={"type":{"options":[
                        {"label":"SOFR Futures","value":"sofr_fut"},
                        {"label":"Treasury","value":"treasury"},
                    ]}},
                    data=[dict(r) for r in _DV01_DEFAULTS],
                    editable=True, row_deletable=True,
                    style_table={"backgroundColor": T.BG_CARD,
                                  "overflowX": "auto"},
                    style_cell={"backgroundColor": T.BG_ELEVATED,
                                 "color": T.TEXT_PRIMARY,
                                 "border": f"1px solid {T.BORDER}",
                                 "fontSize": "11px",
                                 "minWidth": "80px"},
                    style_header={"backgroundColor": T.BG_CARD,
                                   "color": T.TEXT_SEC, "fontSize":"10px"},
                ),
                html.Div([
                    dbc.Button("+ Add Row", id="dv-add", size="sm",
                               color="secondary", style={"marginTop":"8px",
                                                          "fontSize":"11px"}),
                ]),
                html.Label("Zero curve base (flat):", style={"color":T.TEXT_SEC,
                                                                "fontSize":"11px",
                                                                "marginTop":"14px"}),
                dcc.Slider(id="dv-curve", min=0.0, max=0.10, step=0.0005, value=0.04,
                            tooltip={"placement":"top"}),
            ], style=T.STYLE_CARD),
        ], md=5),
        dbc.Col([
            html.Div([
                _title("Portfolio DV01"),
                dbc.Row([
                    dbc.Col(_tile("Total DV01",       "dv-total"), md=4),
                    dbc.Col(_tile("SOFR Futures DV01","dv-sofr"),  md=4),
                    dbc.Col(_tile("Treasury DV01",    "dv-ust"),   md=4),
                ]),
            ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
            dbc.Tabs([
                dbc.Tab(dcc.Graph(id="dv-chart-ladder"), label="DV01 by Instrument"),
                dbc.Tab(dcc.Graph(id="dv-chart-bucket"), label="DV01 by Tenor Bucket"),
            ]),
        ], md=7),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# Top-level page layout
# ═══════════════════════════════════════════════════════════════════════════

def layout() -> html.Div:
    return html.Div([
        C.page_header(
            "Models",
            "Interactive pricing workbench - options Greeks, barrier "
            "probability, bond duration, swap DV01, callable OAS.",
        ),

        dbc.Tabs([
            dbc.Tab(
                html.Div([
                    dbc.Tabs([
                        dbc.Tab(_european_tab(),  label="European",   tab_id="t-eu"),
                        dbc.Tab(_american_tab(),  label="American",   tab_id="t-am"),
                        dbc.Tab(_black76_tab(),   label="Black-76",   tab_id="t-b76"),
                        dbc.Tab(_barrier_tab(),   label="Barrier",    tab_id="t-br"),
                        dbc.Tab(_digital_tab(),   label="Digital",    tab_id="t-dg"),
                        dbc.Tab(_asian_tab(),     label="Asian",      tab_id="t-as"),
                        dbc.Tab(_sabr_tab(),      label="SABR",       tab_id="t-sb"),
                        dbc.Tab(_heston_tab(),    label="Heston",     tab_id="t-hs"),
                        dbc.Tab(_varswap_tab(),   label="Var Swap",   tab_id="t-vs"),
                        dbc.Tab(_spread_tab(),    label="Spread",     tab_id="t-sp"),
                    ], id="models-opt-tabs", active_tab="t-eu"),
                ], style={"paddingTop": "14px"}),
                label="Options", tab_id="models-options",
            ),
            dbc.Tab(
                html.Div([
                    dbc.Tabs([
                        dbc.Tab(_curve_tab(),    label="Curve",     tab_id="t-rc"),
                        dbc.Tab(_bond_tab(),     label="Bond",      tab_id="t-bd"),
                        dbc.Tab(_swap_tab(),     label="Swap",      tab_id="t-sw"),
                        dbc.Tab(_caps_tab(),     label="Caps/Floors",tab_id="t-cp"),
                        dbc.Tab(_swaption_tab(), label="Swaption",  tab_id="t-sp2"),
                        dbc.Tab(_callable_tab(), label="Callable",  tab_id="t-cb"),
                        dbc.Tab(_dv01_ladder_tab(), label="DV01 Ladder", tab_id="t-dv"),
                    ], id="models-rates-tabs", active_tab="t-rc"),
                ], style={"paddingTop": "14px"}),
                label="Rates", tab_id="models-rates",
            ),
        ], id="models-outer-tabs", active_tab="models-options"),
    ], style=D.PAGE)
