# -*- coding: utf-8 -*-
"""
dash_app/pages/models - pricing/figure helpers (pure logic).

Numerical model wrappers, the dark-theme figure defaults, the wireframe 3D
surface, the binomial-tree figure, and the small UI primitives
(_title/_tile/_slider) shared by layout.py and callbacks.py. No @callback here.

Split out of the original monolithic models.py.
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


# UI style helpers

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
