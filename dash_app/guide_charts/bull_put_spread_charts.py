"""Interactive Plotly charts for the Bull Put Spread guide article."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash_bootstrap_components as dbc
from dash import html, dcc

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
try:
    from dash_app import theme as T
except Exception:
    class T:
        BG_BASE = "#0a0e1a"; BG_CARD = "#111827"; ACCENT = "#6366f1"
        SUCCESS = "#10b981"; DANGER = "#ef4444"; WARNING = "#f59e0b"
        TEXT_PRIMARY = "#f9fafb"; TEXT_SEC = "#9ca3af"; BORDER = "#1f2937"
        STYLE_CARD = {"backgroundColor": "#111827", "border": "1px solid #1f2937",
                      "borderRadius": "10px", "padding": "16px"}

_LAYOUT = dict(
    paper_bgcolor=T.BG_CARD,
    plot_bgcolor=T.BG_CARD,
    font={"color": T.TEXT_PRIMARY, "family": "Inter, sans-serif", "size": 12},
    margin={"t": 50, "b": 50, "l": 60, "r": 30},
)


def _card(title: str, fig, caption: str = "") -> dbc.Card:
    children = [dcc.Graph(figure=fig, config={"displayModeBar": False})]
    if caption:
        children.append(html.P(caption, style={"color": T.TEXT_SEC, "fontSize": "12px",
                                                "margin": "8px 0 0 0", "fontStyle": "italic"}))
    return dbc.Card(
        [dbc.CardHeader(html.Strong(title, style={"fontSize": "13px", "color": T.TEXT_PRIMARY})),
         dbc.CardBody(children)],
        style={**T.STYLE_CARD, "marginBottom": "20px"},
    )


# ── Chart 1: Bull Put Spread Payoff ──────────────────────────────────────────

def _payoff_chart() -> go.Figure:
    """SPY short $560 put / long $555 put, $1.85 credit."""
    S = np.linspace(535, 585, 500)

    short_put = 560.0
    long_put  = 555.0
    credit    = 1.85
    width     = short_put - long_put  # 5 pts
    multiplier = 100

    # Per-share P&L at expiry
    pnl_per_share = np.where(
        S >= short_put,  credit,
        np.where(S <= long_put, credit - width,
                 credit - (short_put - S))
    )
    pnl = pnl_per_share * multiplier
    be  = short_put - credit  # 558.15

    max_profit = credit * multiplier
    max_loss   = (width - credit) * multiplier

    fig = go.Figure()

    fig.add_vrect(x0=535, x1=be, fillcolor=T.DANGER, opacity=0.07, line_width=0,
                  annotation_text="Loss Zone", annotation_font_color=T.DANGER,
                  annotation_font_size=10, annotation_position="top right")
    fig.add_vrect(x0=be, x1=585, fillcolor=T.SUCCESS, opacity=0.06, line_width=0,
                  annotation_text="Profit Zone", annotation_font_color=T.SUCCESS,
                  annotation_font_size=10, annotation_position="top left")

    fig.add_trace(go.Scatter(
        x=S, y=pnl, mode="lines", name="Bull Put Spread P&L",
        line={"color": T.ACCENT, "width": 3},
    ))

    fig.add_vline(x=long_put, line_dash="dash", line_color="#475569", opacity=0.6,
                  annotation_text=f"  Long Put ${long_put:.0f}", annotation_font_color="#94a3b8",
                  annotation_font_size=10)
    fig.add_vline(x=short_put, line_dash="dash", line_color="#475569", opacity=0.6,
                  annotation_text=f"  Short Put ${short_put:.0f}", annotation_font_color="#94a3b8",
                  annotation_font_size=10)
    fig.add_vline(x=be, line_dash="dot", line_color=T.WARNING, opacity=0.9,
                  annotation_text=f"  Break-Even ${be:.2f}", annotation_font_color=T.WARNING)
    fig.add_hline(y=0, line_color="#475569", opacity=0.5)

    fig.add_annotation(x=575, y=max_profit + 4,
                       text=f"Max Profit: ${max_profit:.0f}", showarrow=False,
                       font={"color": T.SUCCESS, "size": 12})
    fig.add_annotation(x=541, y=max_loss - 12,
                       text=f"Max Loss: ${max_loss:.0f}", showarrow=False,
                       font={"color": T.DANGER, "size": 12})

    fig.update_layout(
        **_LAYOUT,
        height=380,
        title={"text": "Bull Put Spread Payoff — SPY Short $560P / Long $555P, $1.85 Credit", "x": 0.02},
        xaxis={"title": "SPY Price at Expiry ($)", "gridcolor": T.BORDER},
        yaxis={"title": "P&L ($)", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.50, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


# ── Chart 2: Credit vs Width Ratio ────────────────────────────────────────────

def _credit_width_chart() -> go.Figure:
    rng = np.random.default_rng(7)
    n   = 60

    # Simulate trades across 3 IV environments
    widths_low  = rng.uniform(3, 10, n // 3)
    widths_med  = rng.uniform(3, 10, n // 3)
    widths_high = rng.uniform(3, 10, n - 2 * (n // 3))

    # Credit as fraction of width: low IV ~18%, med ~28%, high ~38%
    credits_low  = widths_low  * rng.uniform(0.12, 0.25, len(widths_low))
    credits_med  = widths_med  * rng.uniform(0.22, 0.35, len(widths_med))
    credits_high = widths_high * rng.uniform(0.30, 0.48, len(widths_high))

    def meets_rule(credits, widths):
        return credits / widths >= 1 / 3

    fig = go.Figure()

    for widths, credits, label, color in [
        (widths_low,  credits_low,  "Low IV",  "#94a3b8"),
        (widths_med,  credits_med,  "Med IV",  T.WARNING),
        (widths_high, credits_high, "High IV", T.SUCCESS),
    ]:
        mask = meets_rule(credits, widths)
        # Passing trades
        fig.add_trace(go.Scatter(
            x=widths[mask], y=credits[mask],
            mode="markers", name=f"{label} (passes 1/3 rule)",
            marker={"color": color, "size": 9, "symbol": "circle",
                    "line": {"width": 1, "color": "#1f2937"}},
        ))
        # Failing trades
        if not mask.all():
            fig.add_trace(go.Scatter(
                x=widths[~mask], y=credits[~mask],
                mode="markers", name=f"{label} (fails 1/3 rule)",
                marker={"color": color, "size": 9, "symbol": "x",
                        "line": {"width": 2, "color": color}, "opacity": 0.4},
            ))

    # 1/3 rule threshold line
    x_line = np.array([3, 10])
    fig.add_trace(go.Scatter(
        x=x_line, y=x_line / 3, mode="lines",
        name="1/3 Rule Threshold",
        line={"color": T.ACCENT, "width": 2, "dash": "dash"},
    ))

    fig.update_layout(
        **_LAYOUT,
        height=380,
        title={"text": "Credit vs Spread Width — 1/3 Rule by IV Environment", "x": 0.02},
        xaxis={"title": "Spread Width ($)", "gridcolor": T.BORDER},
        yaxis={"title": "Credit Received ($)", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.99, "bgcolor": "rgba(0,0,0,0)", "font": {"size": 11}},
    )
    return fig


# ── Chart 3: P&L Over Time — Winning vs Losing Trade ─────────────────────────

def _pnl_timeline_chart() -> go.Figure:
    days = np.arange(0, 46)
    dte  = 45 - days

    # Winning trade: IV drops, price stays stable — collect theta steadily
    # P&L rises from 0 → $185 (max credit)
    win_pnl = 185 * (1 - np.exp(-days / 20)) + rng_noise(days, seed=1, scale=8)
    win_pnl = np.clip(win_pnl, -50, 185)

    # Losing trade: price falls through spread around day 15
    lose_pnl = np.where(
        days < 15,
        40 * (1 - np.exp(-days / 10)),
        40 * np.exp(-(days - 15) * 0.18) - (days - 15) * 10
    ) + rng_noise(days, seed=2, scale=5)
    lose_pnl = np.clip(lose_pnl, -315, 185)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=days, y=win_pnl, mode="lines", name="Winning trade (IV drop + price stable)",
        line={"color": T.SUCCESS, "width": 2},
        fill="tozeroy", fillcolor="rgba(16,185,129,0.07)",
    ))
    fig.add_trace(go.Scatter(
        x=days, y=lose_pnl, mode="lines", name="Losing trade (price falls through spread)",
        line={"color": T.DANGER, "width": 2},
        fill="tozeroy", fillcolor="rgba(239,68,68,0.06)",
    ))

    fig.add_hline(y=0, line_color="#475569", opacity=0.5)
    fig.add_hline(y=185 * 0.5, line_dash="dash", line_color=T.SUCCESS, opacity=0.5,
                  annotation_text=" 50% profit target — consider closing",
                  annotation_font_color=T.SUCCESS, annotation_font_size=10)
    fig.add_hline(y=-315 * 0.5, line_dash="dash", line_color=T.DANGER, opacity=0.5,
                  annotation_text=" 2x credit loss — stop-loss level",
                  annotation_font_color=T.DANGER, annotation_font_size=10)

    fig.add_annotation(x=15, y=lose_pnl[15] - 20,
                       text="Price breaks below<br>short put strike",
                       showarrow=True, arrowhead=2, arrowcolor=T.DANGER,
                       font={"color": T.DANGER, "size": 10}, ax=40, ay=-30)

    fig.update_layout(
        **_LAYOUT,
        height=380,
        title={"text": "P&L Evolution: Winning vs Losing Bull Put Spread (45 DTE, $1.85 Credit)", "x": 0.02},
        xaxis={"title": "Days Since Entry", "gridcolor": T.BORDER},
        yaxis={"title": "Unrealized P&L ($)", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.20, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


def rng_noise(arr, seed=0, scale=5):
    rng = np.random.default_rng(seed)
    return rng.normal(0, scale, len(arr))


# ── Public entry point ────────────────────────────────────────────────────────

def render_charts() -> html.Div:
    return html.Div([
        html.Hr(style={"borderColor": "#1f2937", "margin": "32px 0 24px"}),
        html.H3("Interactive Charts", style={
            "color": "#f9fafb", "fontSize": "16px", "fontWeight": "700",
            "marginBottom": "20px", "letterSpacing": "0.02em",
        }),
        _card(
            "Bull Put Spread Payoff at Expiry — SPY $555/$560",
            _payoff_chart(),
            "Short $560 put + long $555 put for $1.85 credit. Max profit $185 if SPY stays above $560. "
            "Break-even at $558.15. Max loss $315 if SPY closes below $555. Risk/reward 1.7:1 — requires ~63% win rate.",
        ),
        _card(
            "Credit vs Spread Width — Does the Trade Meet the 1/3 Rule?",
            _credit_width_chart(),
            "The 1/3 rule: credit received must be >= 1/3 of spread width. X markers fail this filter. "
            "High-IV environments (green) consistently produce qualifying credits. Low-IV (grey) trades rarely qualify.",
        ),
        _card(
            "P&L Evolution from Entry to Expiry",
            _pnl_timeline_chart(),
            "The winning trade collects theta steadily as IV compresses and price remains stable above the short strike. "
            "The losing trade initially gains but suffers when price falls through the spread around day 15 — "
            "exit at 2x credit loss ($370) prevents catastrophic drawdown.",
        ),
    ], style={"marginTop": "8px"})
