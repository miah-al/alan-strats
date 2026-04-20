"""
dash_app/pages/models.py — Models workbench.

Interactive pricing + greeks + risk for:
  Options sub-tabs:  European, American (CRR), Barrier, Black-76, Asian, Digital
  Rates sub-tabs:    Curve, Bond (+ DV01/Duration), Swap (IRS), Callable

Every slider triggers live recomputation. Charts re-render on release.
"""
from __future__ import annotations

import math

import dash_bootstrap_components as dbc
import numpy as np
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update, dash_table

from dash_app import theme as T
from models import (
    bs_price, bs_greeks, black76_price, black76_greeks,
    crr_american, crr_greeks_fd, american_exercise_boundary,
    digital_cash_price, digital_asset_price,
    asian_geometric_price, asian_arithmetic_mc,
    rr_barrier, barrier_mc, prob_hit_barrier,
    ZeroCurve, flat_curve, bootstrap_from_swaps,
    bond_price_ytm, bond_price_curve, ytm_solve, durations, effective_duration,
    key_rate_durations,
    swap_npv, par_swap_rate, swap_dv01, swap_cashflows,
    price_callable_bond,
    sabr_implied_vol, sabr_smile, heston_price, variance_swap_fair_variance,
    margrabe_exchange, kirk_spread,
    cap_price, european_swaption, forward_swap_rate,
)


# ── UI style helpers ────────────────────────────────────────────────────────

def _title(text: str) -> html.Div:
    return html.Div(text, style={
        "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
        "letterSpacing": "0.08em", "textTransform": "uppercase",
        "marginBottom": "10px",
    })


def _tile(label: str, value_id: str, unit: str = "") -> html.Div:
    return html.Div([
        html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                               "fontWeight": "600", "letterSpacing": "0.05em",
                               "textTransform": "uppercase", "marginBottom": "4px"}),
        html.Div([
            html.Span(id=value_id, style={"color": T.TEXT_PRIMARY,
                                           "fontSize": "16px", "fontWeight": "700"}),
            html.Span(unit, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                    "marginLeft": "3px"}) if unit else None,
        ]),
    ], style={**T.STYLE_CARD, "padding": "10px 12px"})


def _slider(id_: str, label: str, mn: float, mx: float, step: float,
            default: float, fmt: str = ".2f") -> html.Div:
    return html.Div([
        html.Div([
            html.Span(label, style={"color": T.TEXT_SEC, "fontSize": "12px"}),
            html.Span(f"{default:{fmt}}", id=f"{id_}-readout",
                      style={"color": T.ACCENT, "fontSize": "12px",
                             "float": "right", "fontWeight": "600"}),
        ]),
        dcc.Slider(id=id_, min=mn, max=mx, step=step, value=default,
                   marks=None, tooltip={"always_visible": False, "placement": "top"},
                   updatemode="mouseup"),
    ], style={"marginBottom": "18px"})


def _dark_fig() -> dict:
    return dict(
        template="plotly_dark",
        plot_bgcolor=T.BG_CARD, paper_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_PRIMARY, size=11),
        margin=dict(l=50, r=20, t=30, b=40),
        hovermode="x unified",
    )


# ── Wireframe 3D surface (matches Market Data tab style) ────────────────────

_WIRE_COLOR = "#6366f1"
_WIRE_HL    = "#10b981"


def _wire_surface(x_grid: np.ndarray, y_grid: np.ndarray, Z: np.ndarray,
                  x_title: str, y_title: str, z_title: str,
                  title: str = "", x_fmt: str = ".2f", z_fmt: str = ".3f",
                  highlight_x: float | None = None) -> go.Figure:
    """Wireframe 3D surface — traces along both grid directions.
    Optional `highlight_x` draws the line at that x-value in green."""
    fig = go.Figure()
    # Lines along x-axis (one per y row)
    for i, y_val in enumerate(y_grid):
        fig.add_trace(go.Scatter3d(
            x=x_grid.tolist(), y=[float(y_val)]*len(x_grid), z=Z[i].tolist(),
            mode="lines", line=dict(color=_WIRE_COLOR, width=2), showlegend=False,
            hovertemplate=f"{y_title} %{{y:{x_fmt}}} — {x_title} %{{x:{x_fmt}}} — {z_title} %{{z:{z_fmt}}}<extra></extra>",
        ))
    # Lines along y-axis (one per x column)
    for j, x_val in enumerate(x_grid):
        is_hl = (highlight_x is not None and abs(float(x_val) - highlight_x) <
                 (x_grid.max() - x_grid.min()) / (2 * len(x_grid)))
        fig.add_trace(go.Scatter3d(
            x=[float(x_val)]*len(y_grid), y=y_grid.tolist(), z=Z[:, j].tolist(),
            mode="lines",
            line=dict(color=_WIRE_HL if is_hl else _WIRE_COLOR,
                      width=5 if is_hl else 2),
            showlegend=False,
            hovertemplate=(("⚡ " if is_hl else "") +
                f"{x_title} %{{x:{x_fmt}}} — {y_title} %{{y:{x_fmt}}} — {z_title} %{{z:{z_fmt}}}<extra></extra>"),
        ))
    _ax = dict(gridcolor="#2a3050", backgroundcolor="#0c1020",
               color=T.TEXT_PRIMARY, showbackground=True,
               tickfont=dict(color="#c0c8d8", size=11))
    fig.update_layout(
        paper_bgcolor="#0e1117",
        font=dict(color=T.TEXT_PRIMARY, family="monospace", size=12),
        title=dict(text=title, font=dict(size=14, color=T.TEXT_PRIMARY)),
        scene=dict(
            xaxis=dict(**_ax, title=dict(text=x_title, font=dict(color=T.TEXT_PRIMARY, size=12))),
            yaxis=dict(**_ax, title=dict(text=y_title, font=dict(color=T.TEXT_PRIMARY, size=12))),
            zaxis=dict(**_ax, title=dict(text=z_title, font=dict(color=T.TEXT_PRIMARY, size=12))),
            bgcolor="#0c1020",
            camera=dict(eye=dict(x=1.6, y=-1.6, z=0.9)),
            aspectmode="manual", aspectratio=dict(x=2.0, y=1.0, z=0.6),
        ),
        height=550, margin=dict(l=0, r=0, t=50, b=0),
    )
    return fig


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


def _binomial_tree_fig(S0: float, K: float, Tau: float, r: float, q: float,
                       sigma: float, cp: str, N_viz: int = 20,
                       tree_kind: str = "stock") -> go.Figure:
    """
    Build a 2D scatter-with-lines plot of the binomial tree.
    tree_kind='stock'  → nodes colored/labeled with spot price
    tree_kind='option' → nodes colored/labeled with option value
                         (with intrinsic > continuation highlighted green = exercise)
    """
    dt = Tau / N_viz
    u  = math.exp(sigma * math.sqrt(dt))
    d  = 1.0 / u

    if tree_kind == "option":
        _, tree = crr_american(S0, K, Tau, r, q, sigma, cp, N=N_viz, return_tree=True)
    else:
        tree = None

    w  = 1 if cp.lower().startswith("c") else -1

    # Node coordinates and values
    xs, ys, vals, colors, texts = [], [], [], [], []
    line_x, line_y = [], []
    for step in range(N_viz + 1):
        for j in range(step + 1):
            S_node = S0 * (u ** (step - j)) * (d ** j)
            t_node = step * dt
            xs.append(t_node)
            ys.append(S_node)
            if tree_kind == "stock":
                vals.append(S_node)
                colors.append(_WIRE_COLOR)
                texts.append(f"S={S_node:.2f}")
            else:
                V = float(tree[j, step])
                intrinsic = max(w * (S_node - K), 0.0)
                early = intrinsic > 1e-6 and abs(V - intrinsic) < 1e-4 and step < N_viz
                vals.append(V)
                colors.append(_WIRE_HL if early else _WIRE_COLOR)
                texts.append(f"V={V:.2f}")
            # Branches
            if step < N_viz:
                up_S   = S_node * u
                down_S = S_node * d
                up_t   = (step + 1) * dt
                line_x.extend([t_node, up_t,   None, t_node, up_t,   None])
                line_y.extend([S_node, up_S,   None, S_node, down_S, None])

    fig = go.Figure()
    # Branches (underlying gray lines)
    fig.add_trace(go.Scatter(
        x=line_x, y=line_y, mode="lines",
        line=dict(color="#2a3050", width=1), showlegend=False, hoverinfo="skip",
    ))
    # Nodes
    if tree_kind == "stock":
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers+text",
            marker=dict(size=9, color=_WIRE_COLOR, line=dict(color=T.ACCENT, width=1)),
            text=[f"{v:.1f}" for v in vals] if N_viz <= 18 else None,
            textposition="middle right", textfont=dict(size=9, color=T.TEXT_SEC),
            hovertemplate="t=%{x:.3f}y<br>S=%{y:.2f}<extra></extra>",
            showlegend=False,
        ))
    else:
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers+text",
            marker=dict(size=9, color=colors, line=dict(color=T.ACCENT, width=1)),
            text=[f"{v:.2f}" for v in vals] if N_viz <= 18 else None,
            textposition="middle right", textfont=dict(size=9, color=T.TEXT_SEC),
            customdata=vals,
            hovertemplate="t=%{x:.3f}y<br>S=%{y:.2f}<br>V=%{customdata:.4f}<extra></extra>",
            showlegend=False,
        ))
    fig.add_hline(y=K, line=dict(color=T.WARNING, dash="dash"),
                   annotation_text=f"K={K:.0f}", annotation_position="right")
    title = ("Stock-price tree — CRR" if tree_kind == "stock"
             else f"Option-value tree — CRR ({cp.title()}) — 🟢 = early exercise optimal")
    fig.update_layout(
        **_dark_fig(),
        title=title,
        xaxis_title="Time to maturity (years)",
        yaxis_title="Spot" if tree_kind == "stock" else "Spot (marker position)",
        height=520,
    )
    return fig


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
        html.H1("Models", style={"color": T.TEXT_PRIMARY, "fontSize": "22px",
                                  "fontWeight": "700", "marginBottom": "6px"}),
        html.Div("Interactive pricing workbench — options Greeks, barrier probability, "
                 "bond duration, swap DV01, callable OAS.",
                 style={"color": T.TEXT_SEC, "fontSize": "13px",
                        "marginBottom": "20px"}),

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
    ], style=T.STYLE_PAGE)


# ═══════════════════════════════════════════════════════════════════════════
# Slider-readout wiring (reusable)
# ═══════════════════════════════════════════════════════════════════════════

def _register_readouts(pairs: list[tuple[str, str]]):
    """For each (slider_id, fmt) pair, wire a callback that updates
    #{slider_id}-readout with the current value formatted."""
    for sid, fmt in pairs:
        @callback(Output(f"{sid}-readout", "children"),
                  Input(sid, "value"),
                  prevent_initial_call=False)
        def _rd(v, _fmt=fmt):
            try:
                return f"{float(v):{_fmt}}"
            except Exception:
                return str(v)


_READOUT_FMTS = [
    # European
    ("eu-S", ".2f"), ("eu-K", ".2f"), ("eu-T", ".2f"),
    ("eu-r", ".3%"), ("eu-q", ".3%"), ("eu-sig", ".2%"),
    # American
    ("am-S", ".2f"), ("am-K", ".2f"), ("am-T", ".2f"),
    ("am-r", ".3%"), ("am-q", ".3%"), ("am-sig", ".2%"),
    ("am-N", ".0f"), ("am-Nviz", ".0f"),
    # Black-76
    ("b76-F", ".2f"), ("b76-K", ".2f"), ("b76-T", ".2f"),
    ("b76-r", ".3%"), ("b76-sig", ".2%"),
    # Barrier
    ("br-S", ".2f"), ("br-K", ".2f"), ("br-H", ".2f"), ("br-T", ".2f"),
    ("br-r", ".3%"), ("br-q", ".3%"), ("br-sig", ".2%"),
    # Digital
    ("dg-S", ".2f"), ("dg-K", ".2f"), ("dg-T", ".2f"),
    ("dg-r", ".3%"), ("dg-q", ".3%"), ("dg-sig", ".2%"), ("dg-cash", ".2f"),
    # Asian
    ("as-S", ".2f"), ("as-K", ".2f"), ("as-T", ".2f"),
    ("as-r", ".3%"), ("as-q", ".3%"), ("as-sig", ".2%"), ("as-n", ".0f"),
    # SABR
    ("sb-F", ".2f"), ("sb-T", ".2f"), ("sb-alpha", ".2%"),
    ("sb-beta", ".2f"), ("sb-rho", ".2f"), ("sb-nu", ".2f"),
    # Heston
    ("hs-S",".2f"), ("hs-K",".2f"), ("hs-T",".2f"), ("hs-r",".3%"), ("hs-q",".3%"),
    ("hs-v0",".3f"), ("hs-kappa",".2f"), ("hs-theta",".3f"),
    ("hs-sigv",".2f"), ("hs-rho",".2f"),
    # Variance swap
    ("vs-S",".2f"), ("vs-T",".2f"), ("vs-r",".3%"), ("vs-q",".3%"),
    ("vs-atm",".2%"), ("vs-skew",".4f"),
    # Spread
    ("sp-S1",".2f"), ("sp-S2",".2f"), ("sp-K",".2f"), ("sp-T",".2f"),
    ("sp-r",".3%"), ("sp-s1",".2%"), ("sp-s2",".2%"), ("sp-rho",".2f"),
    # Caps
    ("cp-strike",".3%"), ("cp-tenor",".2f"), ("cp-sigma",".2%"),
    ("cp-curve",".3%"),  ("cp-not",".0f"),
    # Swaption
    ("sp2-exp",".2f"),  ("sp2-ten",".2f"),  ("sp2-K",".3%"),
    ("sp2-sig",".2%"),  ("sp2-curve",".3%"),("sp2-not",".0f"),
    # Bond
    ("bd-face", ".0f"), ("bd-cpn", ".3%"), ("bd-mat", ".2f"), ("bd-ytm", ".3%"),
    # Swap
    ("sw-not", ".0f"), ("sw-rate", ".3%"), ("sw-tenor", ".2f"), ("sw-curve", ".3%"),
    # Callable
    ("cb-face", ".0f"), ("cb-cpn", ".3%"), ("cb-mat", ".2f"), ("cb-curve", ".3%"),
    ("cb-sig",  ".3f"), ("cb-a",   ".3f"), ("cb-ct", ".2f"),  ("cb-cp", ".2f"),
    ("cb-N",    ".0f"),
]
_register_readouts(_READOUT_FMTS)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — European
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("eu-price","children"), Output("eu-delta","children"),
    Output("eu-gamma","children"), Output("eu-vega","children"),
    Output("eu-theta","children"), Output("eu-rho","children"),
    Output("eu-vanna","children"), Output("eu-vomma","children"),
    Output("eu-chart-price","figure"), Output("eu-chart-greeks","figure"),
    Output("eu-chart-gamma-surf","figure"),
    Output("eu-chart-term","figure"), Output("eu-chart-vol","figure"),
    Input("eu-S","value"), Input("eu-K","value"), Input("eu-T","value"),
    Input("eu-r","value"), Input("eu-q","value"), Input("eu-sig","value"),
    Input("eu-cp","value"),
)
def _eu_update(S, K, Tau, r, q, sig, cp):
    S, K, Tau, r, q, sig = float(S), float(K), float(Tau), float(r), float(q), float(sig)
    price = bs_price(S, K, Tau, r, q, sig, cp)
    g = bs_greeks(S, K, Tau, r, q, sig, cp)

    # Price vs spot
    spots = np.linspace(max(5, S*0.5), S*1.5, 80)
    prices = [bs_price(s, K, Tau, r, q, sig, cp) for s in spots]
    fig_p = go.Figure(go.Scatter(x=spots, y=prices, mode="lines",
                                  line=dict(color=T.ACCENT, width=2), name="Price"))
    fig_p.add_vline(x=S, line=dict(color=T.WARNING, width=1, dash="dash"),
                    annotation_text=f"S={S:.2f}", annotation_position="top")
    fig_p.update_layout(**_dark_fig(), title="Price vs Spot", height=620,
                         xaxis_title="Spot", yaxis_title="Price")

    # Greeks vs spot
    delta_l = [bs_greeks(s, K, Tau, r, q, sig, cp)["delta"] for s in spots]
    gamma_l = [bs_greeks(s, K, Tau, r, q, sig, cp)["gamma"] for s in spots]
    vega_l  = [bs_greeks(s, K, Tau, r, q, sig, cp)["vega"]  for s in spots]
    fig_g = go.Figure()
    fig_g.add_trace(go.Scatter(x=spots, y=delta_l, name="Delta", line=dict(color="#10b981")))
    fig_g.add_trace(go.Scatter(x=spots, y=np.array(gamma_l)*100, name="Gamma (×100)", line=dict(color="#f59e0b")))
    fig_g.add_trace(go.Scatter(x=spots, y=np.array(vega_l)/10,  name="Vega (÷10)",  line=dict(color="#60a5fa")))
    fig_g.update_layout(**_dark_fig(), title="Greeks vs Spot", height=620)

    # Gamma surface over (S, T) — wireframe style (matches Market Data tab)
    S_grid = np.linspace(max(5, S*0.7), S*1.3, 24)
    T_grid = np.linspace(max(0.05, Tau*0.1), Tau*2.0 if Tau else 2.0, 20)
    Gm = np.zeros((len(T_grid), len(S_grid)))
    for i, tt in enumerate(T_grid):
        for j, ss in enumerate(S_grid):
            Gm[i, j] = bs_greeks(ss, K, tt, r, q, sig, cp)["gamma"]
    fig_s = _wire_surface(S_grid, T_grid, Gm,
                          x_title="Spot", y_title="T (yrs)", z_title="Gamma",
                          title="Gamma Surface (Spot × Time)",
                          x_fmt=".1f", z_fmt=".4f", highlight_x=S)

    # Term structure
    T_l = np.linspace(0.01, max(Tau*3, 3.0), 60)
    p_T = [bs_price(S, K, tt, r, q, sig, cp) for tt in T_l]
    fig_t = go.Figure(go.Scatter(x=T_l, y=p_T, mode="lines", line=dict(color=T.ACCENT)))
    fig_t.add_vline(x=Tau, line=dict(color=T.WARNING, dash="dash"))
    fig_t.update_layout(**_dark_fig(), title="Price vs Time to Expiry", height=620,
                         xaxis_title="T (years)", yaxis_title="Price")

    # Vol sweep
    sig_l = np.linspace(0.01, 1.0, 60)
    p_sig = [bs_price(S, K, Tau, r, q, s, cp) for s in sig_l]
    fig_v = go.Figure(go.Scatter(x=sig_l, y=p_sig, mode="lines", line=dict(color=T.ACCENT)))
    fig_v.add_vline(x=sig, line=dict(color=T.WARNING, dash="dash"))
    fig_v.update_layout(**_dark_fig(), title="Price vs Volatility", height=620,
                         xaxis_title="σ", yaxis_title="Price")

    def _f(v, fmt=".4f"): return f"{v:{fmt}}"
    return (
        _f(price, ".4f"),  _f(g["delta"], ".4f"), _f(g["gamma"], ".5f"),
        _f(g["vega"]/100,  ".4f"),
        _f(g["theta"], ".4f"), _f(g["rho"],   ".4f"),
        _f(g["vanna"], ".4f"), _f(g["vomma"], ".4f"),
        fig_p, fig_g, fig_s, fig_t, fig_v,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — American (CRR)
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("am-price","children"), Output("am-eep","children"),
    Output("am-delta","children"), Output("am-gamma","children"),
    Output("am-vega","children"),  Output("am-theta","children"),
    Output("am-euro","children"),  Output("am-conv","children"),
    Output("am-chart-stock-tree","figure"),
    Output("am-chart-option-tree","figure"),
    Output("am-chart-boundary","figure"),
    Output("am-chart-price","figure"),
    Output("am-chart-conv","figure"),
    Input("am-S","value"),   Input("am-K","value"),   Input("am-T","value"),
    Input("am-r","value"),   Input("am-q","value"),   Input("am-sig","value"),
    Input("am-N","value"),   Input("am-Nviz","value"),
    Input("am-cp","value"),
)
def _am_update(S, K, Tau, r, q, sig, N, N_viz, cp):
    S, K, Tau, r, q, sig = float(S), float(K), float(Tau), float(r), float(q), float(sig)
    N = int(N)
    am = crr_american(S, K, Tau, r, q, sig, cp, N=N)
    eu = bs_price(S, K, Tau, r, q, sig, cp)
    eep = am - eu
    fd  = crr_greeks_fd(S, K, Tau, r, q, sig, cp, N=max(100, min(N, 400)))

    # Boundary
    tt, bd = american_exercise_boundary(S, K, Tau, r, q, sig, cp, N=min(200, max(50, N//2)))
    fig_b = go.Figure()
    if len(tt) > 0:
        fig_b.add_trace(go.Scatter(x=tt, y=bd, mode="lines+markers",
                                    line=dict(color=T.DANGER, width=2),
                                    marker=dict(size=4),
                                    name="Critical S*(t)"))
    fig_b.add_hline(y=K, line=dict(color=T.WARNING, dash="dash"),
                     annotation_text="K")
    fig_b.update_layout(**_dark_fig(),
                         title=f"Early-Exercise Boundary — {cp.title()}",
                         xaxis_title="Time to expiry (years)", yaxis_title="Critical S*",
                         height=620)

    # Price vs Spot (American vs European)
    sp = np.linspace(max(5, S*0.5), S*1.5, 40)
    a_l = [crr_american(s, K, Tau, r, q, sig, cp, N=min(N, 200)) for s in sp]
    e_l = [bs_price(s, K, Tau, r, q, sig, cp) for s in sp]
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=sp, y=a_l, name="American", line=dict(color=T.ACCENT)))
    fig_p.add_trace(go.Scatter(x=sp, y=e_l, name="European", line=dict(color=T.SUCCESS, dash="dot")))
    fig_p.add_vline(x=S, line=dict(color=T.WARNING, dash="dash"))
    fig_p.update_layout(**_dark_fig(), title="American vs European", height=620,
                         xaxis_title="Spot", yaxis_title="Price")

    # CRR convergence plot
    N_list = [20, 40, 60, 100, 150, 200, 300, 500, 800, 1200]
    c_list = [crr_american(S, K, Tau, r, q, sig, cp, N=n_) for n_ in N_list]
    fig_c = go.Figure()
    fig_c.add_trace(go.Scatter(x=N_list, y=c_list, mode="lines+markers",
                                line=dict(color=T.ACCENT), name="CRR price"))
    fig_c.add_hline(y=eu, line=dict(color=T.SUCCESS, dash="dot"),
                     annotation_text=f"European = {eu:.4f}")
    fig_c.update_layout(**_dark_fig(), title="CRR Price Convergence in N",
                         xaxis_title="Binomial steps N", yaxis_title="Price", height=620)

    # Suggested N for convergence within 1e-3
    conv_N = next((n for n, p_ in zip(N_list, c_list)
                    if abs(p_ - c_list[-1]) < 1e-3), N_list[-1])

    # Stock & Option trees — controlled by independent N_viz slider
    nviz = int(max(4, min(30, int(N_viz))))
    fig_st = _binomial_tree_fig(S, K, Tau, r, q, sig, cp, N_viz=nviz, tree_kind="stock")
    fig_op = _binomial_tree_fig(S, K, Tau, r, q, sig, cp, N_viz=nviz, tree_kind="option")

    return (
        f"{am:.4f}", f"{eep:+.4f}",
        f"{fd['delta']:.4f}", f"{fd['gamma']:.5f}",
        f"{fd['vega']:.4f}",  f"{fd['theta']:.4f}",
        f"{eu:.4f}", f"{conv_N}",
        fig_st, fig_op, fig_b, fig_p, fig_c,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Black-76
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("b76-price","children"), Output("b76-delta","children"),
    Output("b76-gamma","children"), Output("b76-vega","children"),
    Output("b76-theta","children"), Output("b76-rho","children"),
    Output("b76-chart-price","figure"), Output("b76-chart-greeks","figure"),
    Input("b76-F","value"), Input("b76-K","value"), Input("b76-T","value"),
    Input("b76-r","value"), Input("b76-sig","value"), Input("b76-cp","value"),
)
def _b76_update(F, K, Tau, r, sig, cp):
    F, K, Tau, r, sig = float(F), float(K), float(Tau), float(r), float(sig)
    p = black76_price(F, K, Tau, r, sig, cp)
    g = black76_greeks(F, K, Tau, r, sig, cp)

    Fg = np.linspace(max(5, F*0.5), F*1.5, 80)
    prices = [black76_price(f, K, Tau, r, sig, cp) for f in Fg]
    deltas = [black76_greeks(f, K, Tau, r, sig, cp)["delta"] for f in Fg]
    gammas = [black76_greeks(f, K, Tau, r, sig, cp)["gamma"] for f in Fg]

    fig_p = go.Figure(go.Scatter(x=Fg, y=prices, line=dict(color=T.ACCENT)))
    fig_p.add_vline(x=F, line=dict(color=T.WARNING, dash="dash"))
    fig_p.update_layout(**_dark_fig(), title="Price vs Forward",
                         xaxis_title="Forward F", yaxis_title="Price", height=620)

    fig_g = go.Figure()
    fig_g.add_trace(go.Scatter(x=Fg, y=deltas, name="Delta (dF)", line=dict(color=T.SUCCESS)))
    fig_g.add_trace(go.Scatter(x=Fg, y=np.array(gammas)*100, name="Gamma ×100", line=dict(color=T.WARNING)))
    fig_g.update_layout(**_dark_fig(), title="Greeks vs Forward", height=620)

    return (f"{p:.4f}", f"{g['delta']:.4f}", f"{g['gamma']:.5f}",
            f"{g['vega']/100:.4f}", f"{g['theta']:.4f}", f"{g['rho']:.4f}",
            fig_p, fig_g)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Barrier
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("br-price","children"), Output("br-mc","children"),
    Output("br-mc-se","children"), Output("br-phit","children"),
    Output("br-vanilla","children"), Output("br-check","children"),
    Output("br-chart-price","figure"), Output("br-chart-phit-term","figure"),
    Input("br-S","value"), Input("br-K","value"), Input("br-H","value"),
    Input("br-T","value"), Input("br-r","value"), Input("br-q","value"),
    Input("br-sig","value"), Input("br-cp","value"),
    Input("br-io","value"), Input("br-ud","value"),
)
def _br_update(S, K, H, Tau, r, q, sig, cp, io, ud):
    S, K, H, Tau, r, q, sig = map(float, (S, K, H, Tau, r, q, sig))
    try:
        rr = rr_barrier(S, K, H, Tau, r, q, sig, cp, io, ud)
    except Exception as e:
        rr = float("nan")
    try:
        mc, se = barrier_mc(S, K, H, Tau, r, q, sig, cp, io, ud,
                             paths=6000, steps=120, seed=42)
    except Exception:
        mc, se = float("nan"), 0.0
    phit = prob_hit_barrier(S, H, Tau, r, q, sig, up=(ud == "up"))
    vanilla = bs_price(S, K, Tau, r, q, sig, cp)

    other_io = "out" if io == "in" else "in"
    try:
        other = rr_barrier(S, K, H, Tau, r, q, sig, cp, other_io, ud)
    except Exception:
        other = float("nan")
    check = f"{rr:.4f} + {other:.4f} = {rr+other:.4f}  (vanilla = {vanilla:.4f})"

    # Price vs spot
    sp = np.linspace(max(5, S*0.5), max(S, H)*1.3, 80)
    prices = []
    for s in sp:
        try:
            prices.append(rr_barrier(s, K, H, Tau, r, q, sig, cp, io, ud))
        except Exception:
            prices.append(float("nan"))
    fig_p = go.Figure(go.Scatter(x=sp, y=prices, line=dict(color=T.ACCENT)))
    fig_p.add_vline(x=S, line=dict(color=T.WARNING, dash="dash"),
                     annotation_text=f"S={S:.0f}")
    fig_p.add_vline(x=H, line=dict(color=T.DANGER, dash="dot"),
                     annotation_text=f"H={H:.0f}")
    fig_p.update_layout(**_dark_fig(), title=f"{cp.title()} {ud}-{io} Barrier — Price",
                         xaxis_title="Spot", yaxis_title="Price", height=620)

    # Hit probability vs T
    Tg = np.linspace(0.01, max(Tau*3, 2.0), 50)
    p_hit = [prob_hit_barrier(S, H, tt, r, q, sig, up=(ud == "up")) for tt in Tg]
    fig_h = go.Figure(go.Scatter(x=Tg, y=p_hit, line=dict(color=T.DANGER),
                                   fill="tozeroy"))
    fig_h.add_vline(x=Tau, line=dict(color=T.WARNING, dash="dash"))
    fig_h.update_layout(**_dark_fig(), title="P(Hit Barrier) vs T",
                         xaxis_title="T (years)", yaxis_title="Probability",
                         yaxis=dict(range=[0, 1]), height=620)

    return (f"{rr:.4f}", f"{mc:.4f}", f"±{2*se:.4f}", f"{phit:.3%}",
            f"{vanilla:.4f}", check, fig_p, fig_h)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Digital
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("dg-cash-price","children"), Output("dg-asset-price","children"),
    Output("dg-parity","children"),
    Output("dg-chart-price","figure"),
    Input("dg-S","value"), Input("dg-K","value"), Input("dg-T","value"),
    Input("dg-r","value"), Input("dg-q","value"), Input("dg-sig","value"),
    Input("dg-cash","value"), Input("dg-cp","value"),
)
def _dg_update(S, K, Tau, r, q, sig, cash, cp):
    S, K, Tau, r, q, sig, cash = map(float, (S, K, Tau, r, q, sig, cash))
    cash_p  = digital_cash_price(S, K, Tau, r, q, sig, cp, cash=cash)
    asset_p = digital_asset_price(S, K, Tau, r, q, sig, cp)
    opp = "put" if cp == "call" else "call"
    cash_o = digital_cash_price(S, K, Tau, r, q, sig, opp, cash=cash)
    parity = f"{cash_p:.4f} + {cash_o:.4f} = {cash_p + cash_o:.4f}  (target {cash*math.exp(-r*Tau):.4f})"

    sp = np.linspace(max(5, S*0.5), S*1.5, 80)
    prices = [digital_cash_price(s, K, Tau, r, q, sig, cp, cash=cash) for s in sp]
    fig = go.Figure(go.Scatter(x=sp, y=prices, line=dict(color=T.ACCENT)))
    fig.add_vline(x=S, line=dict(color=T.WARNING, dash="dash"))
    fig.add_vline(x=K, line=dict(color=T.DANGER, dash="dot"),
                   annotation_text=f"K={K:.0f}")
    fig.update_layout(**_dark_fig(), title=f"Cash-or-Nothing {cp.title()} vs Spot",
                       xaxis_title="Spot", yaxis_title="Price", height=620)
    return (f"{cash_p:.4f}", f"{asset_p:.4f}", parity, fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Asian
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("as-geo","children"), Output("as-arith","children"),
    Output("as-euro","children"),
    Output("as-chart-vs-spot","figure"), Output("as-chart-vs-n","figure"),
    Input("as-S","value"), Input("as-K","value"), Input("as-T","value"),
    Input("as-r","value"), Input("as-q","value"), Input("as-sig","value"),
    Input("as-n","value"), Input("as-cp","value"),
)
def _as_update(S, K, Tau, r, q, sig, n, cp):
    S, K, Tau, r, q, sig = map(float, (S, K, Tau, r, q, sig))
    n = int(n)
    geo  = asian_geometric_price(S, K, Tau, r, q, sig, cp, n_fix=n)
    arith, se = asian_arithmetic_mc(S, K, Tau, r, q, sig, cp, n_fix=n,
                                     paths=4000, seed=42)
    eu = bs_price(S, K, Tau, r, q, sig, cp)

    sp = np.linspace(max(5, S*0.5), S*1.5, 40)
    g_l = [asian_geometric_price(s, K, Tau, r, q, sig, cp, n_fix=n) for s in sp]
    e_l = [bs_price(s, K, Tau, r, q, sig, cp) for s in sp]
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=sp, y=g_l, name="Geometric Asian", line=dict(color=T.ACCENT)))
    fig_p.add_trace(go.Scatter(x=sp, y=e_l, name="European",       line=dict(color=T.SUCCESS, dash="dot")))
    fig_p.add_vline(x=S, line=dict(color=T.WARNING, dash="dash"))
    fig_p.update_layout(**_dark_fig(), title="Asian vs European", height=620,
                         xaxis_title="Spot", yaxis_title="Price")

    ns = [2, 4, 6, 12, 24, 52, 100, 252]
    p_n = [asian_geometric_price(S, K, Tau, r, q, sig, cp, n_fix=m) for m in ns]
    fig_n = go.Figure(go.Scatter(x=ns, y=p_n, mode="lines+markers",
                                  line=dict(color=T.ACCENT)))
    fig_n.add_hline(y=eu, line=dict(color=T.SUCCESS, dash="dot"),
                     annotation_text=f"European = {eu:.4f}")
    fig_n.update_layout(**_dark_fig(), title="Price vs # Fixings (Geometric)",
                         xaxis_title="Fixings", yaxis_title="Price",
                         xaxis_type="log", height=620)
    return (f"{geo:.4f}", f"{arith:.4f} ±{2*se:.3f}", f"{eu:.4f}", fig_p, fig_n)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Curve
# ═══════════════════════════════════════════════════════════════════════════

@callback(Output("rc-curve-table","data", allow_duplicate=True),
          Input("rc-add-row","n_clicks"),
          State("rc-curve-table","data"),
          prevent_initial_call=True)
def _rc_add_row(n, data):
    if not n:
        return no_update
    data = list(data or [])
    last_t = data[-1]["tenor"] if data else 1
    last_r = data[-1]["rate"]  if data else 4.0
    data.append({"tenor": float(last_t) + 1.0, "rate": float(last_r)})
    return data


@callback(
    Output("rc-short","children"), Output("rc-mid","children"),
    Output("rc-long","children"),
    Output("rc-chart-zero-fwd","figure"), Output("rc-chart-df","figure"),
    Output("rc-chart-fwd-surf","figure"),
    Input("rc-curve-table","data"), Input("rc-interp","value"),
)
def _rc_update(data, interp):
    if not data:
        empty = go.Figure().update_layout(**_dark_fig(), title="No data")
        return "—","—","—", empty, empty, empty
    try:
        tenors = [float(r["tenor"]) for r in data if r.get("tenor") is not None]
        rates  = [float(r["rate"])/100 for r in data if r.get("rate") is not None]
        curve  = ZeroCurve(tenors, rates, interp=interp)
    except Exception as e:
        empty = go.Figure().update_layout(**_dark_fig(), title=f"Error: {e}")
        return "—","—","—", empty, empty, empty

    tg = np.linspace(0.25, max(30, max(tenors)), 80)
    zeros = np.array([float(curve.zero(t)) for t in tg])
    fwds  = np.zeros(len(tg)-1)
    for i in range(len(tg)-1):
        fwds[i] = curve.forward(tg[i], tg[i+1])

    fig_zf = go.Figure()
    fig_zf.add_trace(go.Scatter(x=tg, y=zeros*100, name="Zero rate", line=dict(color=T.ACCENT)))
    fig_zf.add_trace(go.Scatter(x=tg[:-1], y=fwds*100, name="Inst. forward",
                                  line=dict(color=T.SUCCESS, dash="dot")))
    fig_zf.update_layout(**_dark_fig(), title="Zero + Forward Curve",
                          xaxis_title="Tenor (y)", yaxis_title="Rate (%)", height=620)

    dfs = np.array([float(curve.df(t)) for t in tg])
    fig_df = go.Figure(go.Scatter(x=tg, y=dfs, line=dict(color=T.ACCENT)))
    fig_df.update_layout(**_dark_fig(), title="Discount Factor",
                          xaxis_title="Tenor", yaxis_title="DF", height=620)

    # Forward surface — wireframe style
    starts = np.linspace(0.25, min(10, max(tenors)*0.7), 16)
    taus   = np.linspace(0.25, min(10, max(tenors)*0.7), 16)
    Z = np.zeros((len(starts), len(taus)))
    for i, s in enumerate(starts):
        for j, tau in enumerate(taus):
            try:
                Z[i, j] = curve.forward(s, s + tau) * 100
            except Exception:
                Z[i, j] = np.nan
    fig_s = _wire_surface(taus, starts, Z,
                          x_title="τ (years)", y_title="Start (y)",
                          z_title="Forward (%)",
                          title="Forward Rate Surface",
                          x_fmt=".1f", z_fmt=".2f")

    def _f(t_): return f"{float(curve.zero(t_))*100:.3f}%"
    return (_f(0.25), _f(5.0), _f(min(30, max(tenors))),
            fig_zf, fig_df, fig_s)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Bond
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("bd-pv","children"),  Output("bd-mac","children"),
    Output("bd-mod","children"), Output("bd-conv","children"),
    Output("bd-dv01","children"),Output("bd-par","children"),
    Output("bd-acc","children"), Output("bd-clean","children"),
    Output("bd-chart-cf","figure"),  Output("bd-chart-pvy","figure"),
    Output("bd-chart-dvmat","figure"),
    Input("bd-face","value"), Input("bd-cpn","value"),
    Input("bd-mat","value"),  Input("bd-ytm","value"),
    Input("bd-freq","value"),
)
def _bd_update(face, cpn, mat, ytm, freq):
    face, cpn, mat, ytm = map(float, (face, cpn, mat, ytm))
    freq = int(freq)
    r  = bond_price_ytm(face, cpn, freq, mat, ytm)
    d  = durations(face, cpn, freq, mat, ytm)

    # Cash-flow chart
    times, amounts = r["times"], r["amounts"]
    fig_cf = go.Figure(go.Bar(x=times, y=amounts, marker_color=T.ACCENT))
    fig_cf.update_layout(**_dark_fig(), title="Bond Cash Flows",
                          xaxis_title="Year", yaxis_title="Cashflow", height=620)

    # PV vs YTM with linear approx
    ys = np.linspace(max(-0.02, ytm - 0.05), ytm + 0.05, 60)
    pvs = [bond_price_ytm(face, cpn, freq, mat, y)["pv"] for y in ys]
    lin = [r["pv"] - d["modified"] * r["pv"] * (y - ytm) for y in ys]
    fig_py = go.Figure()
    fig_py.add_trace(go.Scatter(x=ys*100, y=pvs, name="Actual PV",  line=dict(color=T.ACCENT)))
    fig_py.add_trace(go.Scatter(x=ys*100, y=lin, name="Linear (mod dur)",
                                  line=dict(color=T.DANGER, dash="dot")))
    fig_py.add_vline(x=ytm*100, line=dict(color=T.WARNING, dash="dash"))
    fig_py.update_layout(**_dark_fig(), title="PV vs YTM — Convexity Visible",
                          xaxis_title="YTM (%)", yaxis_title="PV", height=620)

    # Duration vs maturity
    mats = np.linspace(0.5, 30, 60)
    durs = [durations(face, cpn, freq, m, ytm)["modified"] for m in mats]
    fig_dm = go.Figure(go.Scatter(x=mats, y=durs, line=dict(color=T.ACCENT)))
    fig_dm.add_vline(x=mat, line=dict(color=T.WARNING, dash="dash"))
    fig_dm.update_layout(**_dark_fig(), title="Modified Duration vs Maturity",
                          xaxis_title="Maturity (y)", yaxis_title="Mod. duration (y)", height=620)

    # Par yield: coupon where price=face
    try:
        par_yield = ytm_solve(face, face, cpn, freq, mat)
    except Exception:
        par_yield = ytm
    return (
        f"{r['pv']:.4f}", f"{d['macaulay']:.3f}",
        f"{d['modified']:.3f}", f"{d['convexity']:.2f}",
        f"{d['dv01']:.4f}", f"{par_yield:.3%}",
        f"{r['accrued']:.4f}", f"{r['clean']:.4f}",
        fig_cf, fig_py, fig_dm,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Swap
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("sw-npv","children"), Output("sw-par","children"),
    Output("sw-dv01","children"),Output("sw-fxleg","children"),
    Output("sw-chart-cf","figure"), Output("sw-chart-npv","figure"),
    Input("sw-not","value"),   Input("sw-rate","value"),
    Input("sw-tenor","value"), Input("sw-curve","value"),
    Input("sw-ff","value"),    Input("sw-side","value"),
)
def _sw_update(notM, rate, tenor, base, ff, pay_fixed):
    notional = float(notM) * 1_000_000
    rate, tenor, base = float(rate), float(tenor), float(base)
    ff = int(ff)
    curve = flat_curve(base)
    npv = swap_npv(curve, notional, rate, tenor, ff, 4, bool(pay_fixed))
    par = par_swap_rate(curve, tenor, ff)
    dv01 = swap_dv01(curve, notional, rate, tenor, ff, 4, bool(pay_fixed))
    cf = swap_cashflows(curve, notional, rate, tenor, ff, 4, bool(pay_fixed))

    # Fixed leg PV
    fix_pv = float(sum(cf["fixed_amounts"][i] * curve.df(cf["fixed_times"][i])
                        for i in range(len(cf["fixed_amounts"]))))

    # Cashflow ladder
    fig_cf = go.Figure()
    fig_cf.add_trace(go.Bar(x=cf["fixed_times"], y=cf["fixed_amounts"]/1_000_000,
                              name="Fixed (pay)", marker_color=T.DANGER, opacity=0.7))
    fig_cf.add_trace(go.Bar(x=cf["float_times"], y=cf["float_amounts"]/1_000_000,
                              name="Float (receive)", marker_color=T.SUCCESS, opacity=0.7))
    fig_cf.update_layout(**_dark_fig(), title="Swap Cashflows ($ millions)",
                          xaxis_title="Year", yaxis_title="CF ($M)",
                          barmode="group", height=620)

    # NPV vs parallel shift
    shifts = np.linspace(-100, 100, 41)
    npvs = [swap_npv(curve.shift(b), notional, rate, tenor, ff, 4, bool(pay_fixed))
            for b in shifts]
    fig_npv = go.Figure(go.Scatter(x=shifts, y=np.array(npvs)/1_000, line=dict(color=T.ACCENT)))
    fig_npv.add_hline(y=0, line=dict(color=T.TEXT_MUTED, dash="dot"))
    fig_npv.update_layout(**_dark_fig(), title="NPV vs Curve Shift (bp)",
                           xaxis_title="Parallel shift (bp)",
                           yaxis_title="NPV ($k)", height=620)

    return (f"{npv:,.0f}", f"{par:.3%}", f"{dv01:,.0f}", f"{fix_pv:,.0f}",
            fig_cf, fig_npv)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Callable bond (Hull-White)
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("cb-straight","children"), Output("cb-cbl","children"),
    Output("cb-opt","children"),      Output("cb-dur","children"),
    Output("cb-chart-shift","figure"),
    Input("cb-face","value"),  Input("cb-cpn","value"),
    Input("cb-mat","value"),   Input("cb-curve","value"),
    Input("cb-sig","value"),   Input("cb-a","value"),
    Input("cb-ct","value"),    Input("cb-cp","value"),
    Input("cb-N","value"),
)
def _cb_update(face, cpn, mat, base, sig, a, ct, cp, N):
    face, cpn, mat, base = map(float, (face, cpn, mat, base))
    sig, a, ct, cp = map(float, (sig, a, ct, cp))
    N = int(N)
    curve = flat_curve(base)
    try:
        res = price_callable_bond(
            curve, face=face, coupon_rate=cpn, freq=2, maturity=mat,
            call_schedule=[(ct, cp)],
            sigma=sig, a=a, steps=max(20, min(N, 80)),
        )
        callable_p = res["callable_price"]
        straight_p = res["straight_price"]
        opt_val    = res["call_option_value"]
        dur        = res["effective_duration"]
    except Exception as e:
        return "—","—","—", f"error: {e}", go.Figure().update_layout(**_dark_fig())

    # Shift chart
    shifts = np.linspace(-200, 200, 17)
    cb_prices = []
    st_prices = []
    for b in shifts:
        try:
            r2 = price_callable_bond(
                curve.shift(b), face=face, coupon_rate=cpn, freq=2, maturity=mat,
                call_schedule=[(ct, cp)],
                sigma=sig, a=a, steps=max(20, min(N, 50)),
            )
            cb_prices.append(r2["callable_price"])
            st_prices.append(r2["straight_price"])
        except Exception:
            cb_prices.append(float("nan"))
            st_prices.append(float("nan"))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=shifts, y=st_prices, name="Straight",
                               line=dict(color=T.SUCCESS, dash="dot")))
    fig.add_trace(go.Scatter(x=shifts, y=cb_prices, name="Callable",
                               line=dict(color=T.ACCENT)))
    fig.update_layout(**_dark_fig(), title="Price vs Parallel Curve Shift",
                       xaxis_title="Shift (bp)", yaxis_title="Price", height=620)

    return (f"{straight_p:.4f}", f"{callable_p:.4f}",
            f"{opt_val:.4f}", f"{dur:.3f}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — SABR
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("sb-atm","children"), Output("sb-skew","children"),
    Output("sb-wing","children"),
    Output("sb-chart-smile","figure"),
    Input("sb-F","value"),     Input("sb-T","value"),
    Input("sb-alpha","value"), Input("sb-beta","value"),
    Input("sb-rho","value"),   Input("sb-nu","value"),
)
def _sb_update(F, Tau, alpha, beta, rho, nu):
    F, Tau, alpha, beta, rho, nu = map(float, (F, Tau, alpha, beta, rho, nu))
    Ks = np.linspace(F*0.7, F*1.3, 61)
    smile = sabr_smile(F, Tau, Ks, alpha, beta, rho, nu)
    atm = sabr_implied_vol(F, F, Tau, alpha, beta, rho, nu)
    put_25d = sabr_implied_vol(F, F*0.90, Tau, alpha, beta, rho, nu)
    call_25d = sabr_implied_vol(F, F*1.10, Tau, alpha, beta, rho, nu)
    skew = put_25d - call_25d
    wing_diff = sabr_implied_vol(F, F*0.90, Tau, alpha, beta, rho, nu) - sabr_implied_vol(F, F*1.10, Tau, alpha, beta, rho, nu)

    fig = go.Figure(go.Scatter(x=Ks, y=smile*100, line=dict(color=T.ACCENT, width=2)))
    fig.add_vline(x=F, line=dict(color=T.WARNING, dash="dash"),
                   annotation_text=f"F={F:.0f}")
    fig.update_layout(**_dark_fig(),
                       title="SABR Implied-Vol Smile",
                       xaxis_title="Strike K", yaxis_title="σ_B (%)", height=620)
    return (f"{atm:.2%}", f"{skew:+.2%}", f"{wing_diff:+.2%}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Heston
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("hs-price","children"), Output("hs-bs","children"),
    Output("hs-diff","children"),
    Output("hs-chart-smile","figure"),
    Input("hs-S","value"),  Input("hs-K","value"),  Input("hs-T","value"),
    Input("hs-r","value"),  Input("hs-q","value"),  Input("hs-v0","value"),
    Input("hs-kappa","value"), Input("hs-theta","value"),
    Input("hs-sigv","value"),  Input("hs-rho","value"),
    Input("hs-cp","value"),
)
def _hs_update(S, K, Tau, r, q, v0, kappa, theta, sigv, rho, cp):
    S, K, Tau, r, q, v0, kappa, theta, sigv, rho = map(
        float, (S, K, Tau, r, q, v0, kappa, theta, sigv, rho))
    try:
        hp = heston_price(S, K, Tau, r, q, v0, kappa, theta, sigv, rho, cp)
    except Exception as e:
        hp = float("nan")
    bs = bs_price(S, K, Tau, r, q, math.sqrt(max(v0, 1e-8)), cp)
    diff = hp - bs

    # Implied smile: reprice across strikes, invert to BS vol
    from models import implied_vol_bs
    Ks = np.linspace(S*0.75, S*1.25, 25)
    ivs = []
    for K_ in Ks:
        try:
            p = heston_price(S, K_, Tau, r, q, v0, kappa, theta, sigv, rho, "call")
            iv = implied_vol_bs(p, S, K_, Tau, r, q, "call")
        except Exception:
            iv = float("nan")
        ivs.append(iv)
    ivs = np.array(ivs)
    mask = ~np.isnan(ivs)
    fig = go.Figure()
    if mask.any():
        fig.add_trace(go.Scatter(x=Ks[mask], y=ivs[mask]*100, line=dict(color=T.ACCENT, width=2),
                                  name="Heston-implied σ"))
    fig.add_hline(y=math.sqrt(max(v0, 1e-8))*100,
                   line=dict(color=T.SUCCESS, dash="dot"),
                   annotation_text=f"√v₀ = {math.sqrt(max(v0, 1e-8))*100:.1f}%")
    fig.update_layout(**_dark_fig(), title="Heston → BS Implied Smile",
                       xaxis_title="Strike", yaxis_title="σ (%)", height=620)
    return (f"{hp:.4f}", f"{bs:.4f}", f"{diff:+.4f}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Variance swap
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("vs-kvar","children"), Output("vs-fvol","children"),
    Output("vs-avol","children"), Output("vs-premium","children"),
    Output("vs-chart-weights","figure"),
    Input("vs-S","value"), Input("vs-T","value"), Input("vs-r","value"),
    Input("vs-q","value"), Input("vs-atm","value"), Input("vs-skew","value"),
)
def _vs_update(S, Tau, r, q, atm, skew):
    S, Tau, r, q, atm, skew = map(float, (S, Tau, r, q, atm, skew))
    Ks = np.linspace(S*0.5, S*1.5, 81)
    ivs = atm + skew * (Ks - S)
    ivs = np.clip(ivs, 0.02, 2.0)
    kvar = variance_swap_fair_variance(S, Tau, r, q, Ks, ivs)
    fvol = math.sqrt(max(kvar, 0))
    premium = fvol - atm

    # Show replication weights 1/K²
    weights = 1.0 / (Ks * Ks)
    weights = weights / weights.max()   # normalised
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=Ks, y=weights, line=dict(color=T.ACCENT, width=2),
                              name="1/K² weight (norm)", yaxis="y1"))
    fig.add_trace(go.Scatter(x=Ks, y=ivs*100, line=dict(color=T.SUCCESS, dash="dot", width=2),
                              name="Input σ (%)", yaxis="y2"))
    fig.update_layout(
        **_dark_fig(),
        title="Var-Swap Replication Weights (1/K²) + Input Smile",
        xaxis_title="Strike",
        yaxis=dict(title="Norm weight", side="left"),
        yaxis2=dict(title="σ (%)", overlaying="y", side="right"),
        height=620,
    )
    return (f"{kvar:.4f}", f"{fvol:.2%}", f"{atm:.2%}", f"{premium:+.3%}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Spread (Margrabe + Kirk)
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("sp-marg","children"), Output("sp-kirk","children"),
    Output("sp-corrd","children"),
    Output("sp-chart-rho","figure"),
    Input("sp-S1","value"), Input("sp-S2","value"), Input("sp-K","value"),
    Input("sp-T","value"),  Input("sp-r","value"),
    Input("sp-s1","value"), Input("sp-s2","value"), Input("sp-rho","value"),
)
def _sp_update(S1, S2, K, Tau, r, s1, s2, rho):
    S1, S2, K, Tau, r, s1, s2, rho = map(float, (S1, S2, K, Tau, r, s1, s2, rho))
    marg = margrabe_exchange(S1, S2, Tau, s1, s2, rho)
    kirk = kirk_spread(S1, S2, K if abs(K) > 1e-6 else 1e-6, Tau, r, s1, s2, rho)
    # Correlation sensitivity dPrice/dρ (central FD)
    d_rho = 0.05
    k_up = kirk_spread(S1, S2, K if abs(K) > 1e-6 else 1e-6, Tau, r, s1, s2, min(rho + d_rho, 0.99))
    k_dn = kirk_spread(S1, S2, K if abs(K) > 1e-6 else 1e-6, Tau, r, s1, s2, max(rho - d_rho, -0.99))
    corr_d = (k_up - k_dn) / (2 * d_rho)

    rhos = np.linspace(-0.95, 0.95, 40)
    marg_l = [margrabe_exchange(S1, S2, Tau, s1, s2, rr) for rr in rhos]
    kirk_l = [kirk_spread(S1, S2, K if abs(K) > 1e-6 else 1e-6, Tau, r, s1, s2, rr) for rr in rhos]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rhos, y=marg_l, line=dict(color=T.SUCCESS), name="Margrabe (K=0)"))
    fig.add_trace(go.Scatter(x=rhos, y=kirk_l, line=dict(color=T.ACCENT),  name="Kirk"))
    fig.add_vline(x=rho, line=dict(color=T.WARNING, dash="dash"))
    fig.update_layout(**_dark_fig(), title="Spread Price vs Correlation ρ",
                       xaxis_title="ρ", yaxis_title="Price", height=620)
    return (f"{marg:.4f}", f"{kirk:.4f}", f"{corr_d:+.4f}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Caps/Floors
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("cp-cap","children"),  Output("cp-floor","children"),
    Output("cp-diff","children"), Output("cp-n","children"),
    Output("cp-chart-ladder","figure"),
    Input("cp-strike","value"), Input("cp-tenor","value"),
    Input("cp-sigma","value"),  Input("cp-curve","value"),
    Input("cp-not","value"),    Input("cp-freq","value"),
)
def _cp_update(strike, tenor, sigma, base, notM, freq):
    strike, tenor, sigma, base = map(float, (strike, tenor, sigma, base))
    notional = float(notM) * 1_000_000
    freq = int(freq)
    curve = flat_curve(base)
    cap = cap_price(curve, strike, tenor, freq, sigma, notional)
    from models.caps import floor_price as _floor
    fl  = _floor(curve, strike, tenor, freq, sigma, notional)
    n_caplets = len(cap["caplet_prices"])

    fig = go.Figure()
    fig.add_trace(go.Bar(x=cap["caplet_times"], y=cap["caplet_prices"],
                          name="Caplet price", marker_color=T.ACCENT, opacity=0.7))
    fig.add_trace(go.Bar(x=fl["floorlet_times"], y=fl["floorlet_prices"],
                          name="Floorlet price", marker_color=T.SUCCESS, opacity=0.7))
    fig.update_layout(**_dark_fig(), title="Caplet / Floorlet Price Ladder",
                       xaxis_title="Expiry (y)", yaxis_title="Price",
                       barmode="group", height=620)
    return (f"{cap['total_price']:,.0f}", f"{fl['total_price']:,.0f}",
            f"{cap['total_price'] - fl['total_price']:+,.0f}", f"{n_caplets}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — European Swaption
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("sp2-price","children"), Output("sp2-fsr","children"),
    Output("sp2-ann","children"),   Output("sp2-vega","children"),
    Output("sp2-chart","figure"),
    Input("sp2-exp","value"),   Input("sp2-ten","value"),
    Input("sp2-K","value"),     Input("sp2-sig","value"),
    Input("sp2-curve","value"), Input("sp2-not","value"),
    Input("sp2-side","value"),
)
def _sp2_update(expiry, tenor, K, sig, base, notM, payer):
    expiry, tenor, K, sig, base = map(float, (expiry, tenor, K, sig, base))
    notional = float(notM) * 1_000_000
    curve = flat_curve(base)
    r = european_swaption(curve, expiry, tenor, K, sig, notional, freq=2, payer=bool(payer))
    # Vega via ±1% vol bump
    r_up = european_swaption(curve, expiry, tenor, K, sig + 0.01, notional, freq=2, payer=bool(payer))
    vega = r_up["price"] - r["price"]

    # Price vs strike
    Ks = np.linspace(max(base - 0.02, 0.001), base + 0.05, 40)
    prices = [european_swaption(curve, expiry, tenor, k_, sig, notional,
                                 freq=2, payer=bool(payer))["price"] for k_ in Ks]
    fig = go.Figure(go.Scatter(x=Ks*100, y=prices, line=dict(color=T.ACCENT)))
    fig.add_vline(x=K*100, line=dict(color=T.WARNING, dash="dash"),
                   annotation_text=f"K={K:.2%}")
    fig.add_vline(x=r["forward_swap_rate"]*100, line=dict(color=T.SUCCESS, dash="dot"),
                   annotation_text=f"F={r['forward_swap_rate']:.2%}")
    fig.update_layout(**_dark_fig(), title="Swaption Price vs Strike",
                       xaxis_title="Strike rate (%)", yaxis_title="Price ($)",
                       height=620)
    return (f"{r['price']:,.0f}", f"{r['forward_swap_rate']:.3%}",
            f"{r['annuity']:.4f}", f"{vega:,.0f}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — DV01 Ladder (SOFR Futures + Treasury Bonds)
# ═══════════════════════════════════════════════════════════════════════════

@callback(Output("dv-table","data", allow_duplicate=True),
          Input("dv-add","n_clicks"),
          State("dv-table","data"),
          prevent_initial_call=True)
def _dv_add_row(n, data):
    if not n: return no_update
    data = list(data or [])
    data.append({"instrument":"New", "type":"treasury", "notional_M":10.0,
                 "tenor":5.0, "coupon":4.0, "position":1})
    return data


@callback(
    Output("dv-total","children"), Output("dv-sofr","children"),
    Output("dv-ust","children"),
    Output("dv-chart-ladder","figure"), Output("dv-chart-bucket","figure"),
    Input("dv-table","data"), Input("dv-curve","value"),
)
def _dv_update(data, base):
    if not data:
        empty = go.Figure().update_layout(**_dark_fig(), title="No data")
        return "—","—","—", empty, empty
    curve = flat_curve(float(base or 0.04))
    rows = []
    sofr_total = 0.0
    ust_total  = 0.0
    for row in data:
        try:
            name   = str(row.get("instrument", ""))
            typ    = str(row.get("type", "treasury"))
            notM   = float(row.get("notional_M") or 0)
            tenor  = float(row.get("tenor") or 0)
            coupon = float(row.get("coupon") or 0) / 100.0
            pos    = float(row.get("position") or 0)
        except Exception:
            continue
        if typ == "sofr_fut":
            # SOFR futures DV01 = $25 × notional_M × position per 1bp
            dv = 25.0 * notM * pos
            sofr_total += dv
        else:
            # Treasury: bond price on curve, parallel ±1bp
            try:
                p0 = bond_price_curve(curve,           notM * 1_000_000, coupon, 2, tenor)["pv"]
                p_up = bond_price_curve(curve.shift(+1), notM * 1_000_000, coupon, 2, tenor)["pv"]
                p_dn = bond_price_curve(curve.shift(-1), notM * 1_000_000, coupon, 2, tenor)["pv"]
                dv = (p_dn - p_up) / 2 * pos
            except Exception:
                dv = 0.0
            ust_total += dv
        rows.append({"name": name, "type": typ, "tenor": tenor, "dv01": dv})

    total = sofr_total + ust_total

    # Ladder chart: per-instrument DV01
    labels = [r["name"] for r in rows]
    dvs    = [r["dv01"] for r in rows]
    colors = [T.WARNING if r["type"] == "sofr_fut" else T.ACCENT for r in rows]
    fig_l = go.Figure(go.Bar(x=labels, y=dvs, marker_color=colors))
    fig_l.update_layout(**_dark_fig(), title="DV01 by Instrument ($ per 1bp)",
                         xaxis_title="", yaxis_title="DV01 ($)", height=620)

    # Bucket chart: DV01 grouped by tenor bucket
    buckets = [(0, 1, "0-1y"), (1, 3, "1-3y"), (3, 7, "3-7y"),
                (7, 15, "7-15y"), (15, 50, "15y+")]
    bucket_dvs = []
    bucket_labels = [b[2] for b in buckets]
    for lo, hi, _ in buckets:
        bdv = sum(r["dv01"] for r in rows if lo <= r["tenor"] < hi)
        bucket_dvs.append(bdv)
    fig_b = go.Figure(go.Bar(x=bucket_labels, y=bucket_dvs, marker_color=T.ACCENT))
    fig_b.update_layout(**_dark_fig(), title="DV01 by Tenor Bucket",
                         xaxis_title="Tenor bucket", yaxis_title="DV01 ($)", height=620)

    return (f"${total:,.0f}", f"${sofr_total:,.0f}", f"${ust_total:,.0f}",
            fig_l, fig_b)
