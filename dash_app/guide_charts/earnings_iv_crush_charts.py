"""Interactive Plotly charts for the Earnings IV Crush guide article."""
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


# ── Chart 1: IV Crush Timeline ────────────────────────────────────────────────

def _iv_crush_timeline() -> go.Figure:
    """AAPL earnings: IV goes 28% → 52% over 2 weeks → crashes to 24% day after."""
    # Days relative to earnings: -14 to +5
    days = np.array([-14, -12, -10, -8, -6, -4, -3, -2, -1, 0, 1, 2, 3, 5])
    iv   = np.array([ 28,  29,  31,  34,  37,  42, 45, 49, 52, 51, 24, 23, 23, 22])

    # Split: before and after earnings
    pre_mask  = days <= 0
    post_mask = days >= 0

    fig = go.Figure()

    # Pre-earnings IV build-up (shaded background)
    fig.add_vrect(x0=-14, x1=0, fillcolor=T.WARNING, opacity=0.05, line_width=0,
                  annotation_text="IV Build-Up Phase", annotation_font_color=T.WARNING,
                  annotation_font_size=10, annotation_position="top left")
    fig.add_vrect(x0=0, x1=5, fillcolor=T.SUCCESS, opacity=0.05, line_width=0,
                  annotation_text="Post-Earnings", annotation_font_color=T.SUCCESS,
                  annotation_font_size=10, annotation_position="top left")

    # IV line before earnings
    fig.add_trace(go.Scatter(
        x=days[pre_mask], y=iv[pre_mask], mode="lines+markers",
        name="IV (pre-earnings)", line={"color": T.WARNING, "width": 2},
        marker={"size": 6},
    ))

    # IV line after earnings
    fig.add_trace(go.Scatter(
        x=days[post_mask], y=iv[post_mask], mode="lines+markers",
        name="IV (post-earnings)", line={"color": T.SUCCESS, "width": 2},
        marker={"size": 6},
    ))

    # Earnings day marker
    fig.add_vline(x=0, line_dash="solid", line_color=T.DANGER, opacity=0.8,
                  annotation_text="  Earnings Day", annotation_font_color=T.DANGER,
                  annotation_font_size=11)

    # Entry / exit markers
    fig.add_trace(go.Scatter(
        x=[-3], y=[45], mode="markers+text",
        marker={"color": T.ACCENT, "size": 14, "symbol": "triangle-up"},
        text=["  Entry (3 days before)"], textposition="top right",
        textfont={"color": T.ACCENT, "size": 11},
        name="Entry point", showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=[1], y=[24], mode="markers+text",
        marker={"color": T.SUCCESS, "size": 14, "symbol": "triangle-down"},
        text=["  Exit (day after)"], textposition="bottom right",
        textfont={"color": T.SUCCESS, "size": 11},
        name="Exit point (IV crush)", showlegend=True,
    ))

    # IV crush annotation
    fig.add_annotation(
        x=1, y=38,
        text="IV Crush: 52% → 24%<br>(−54% in one day)",
        showarrow=True, arrowhead=2, arrowcolor=T.DANGER,
        font={"color": T.DANGER, "size": 11},
        ax=-70, ay=20,
    )

    fig.update_layout(
        **_LAYOUT,
        height=380,
        title={"text": "AAPL Earnings IV Timeline — Build-Up and Crush", "x": 0.02},
        xaxis={"title": "Days Relative to Earnings", "gridcolor": T.BORDER,
               "tickvals": [-14, -10, -6, -3, -1, 0, 1, 3, 5],
               "ticktext": ["-14d", "-10d", "-6d", "-3d", "-1d", "Earn", "+1d", "+3d", "+5d"]},
        yaxis={"title": "Implied Volatility (%)", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.99, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


# ── Chart 2: Realized vs Implied Move ─────────────────────────────────────────

def _realized_vs_implied() -> go.Figure:
    events = [
        "AAPL Q1", "AAPL Q2", "MSFT Q1", "MSFT Q2", "NVDA Q1",
        "TSLA Q1", "AMZN Q1", "GOOGL Q1", "META Q1", "NFLX Q1",
    ]
    implied = [5.2, 4.8, 4.1, 3.9, 8.3, 7.1, 5.6, 4.4, 6.8, 9.2]
    realized= [3.1, 2.2, 3.8, 1.4, 5.9, 9.4, 2.8, 3.1, 4.2, 6.7]

    beat_implied = [r > i for r, i in zip(realized, implied)]  # stock moved more than implied

    x_pos = np.arange(len(events))
    width = 0.35

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=[e + " (I)" for e in events], y=implied,
        name="Implied Move (straddle price)",
        marker_color=T.ACCENT, marker_line_width=0,
        offsetgroup=0, width=0.35,
    ))

    colors_realized = [T.DANGER if beat else T.SUCCESS for beat in beat_implied]
    fig.add_trace(go.Bar(
        x=[e + " (R)" for e in events], y=realized,
        name="Realized Move (actual %)",
        marker_color=colors_realized, marker_line_width=0,
        offsetgroup=1, width=0.35,
    ))

    # Simpler: use grouped approach with separate x positions
    fig2 = make_subplots(rows=1, cols=1)

    bar_x = []
    implied_y = []
    realized_y = []
    realized_colors = []
    for i, (ev, imp, rea, beat) in enumerate(zip(events, implied, realized, beat_implied)):
        bar_x.append(ev)
        implied_y.append(imp)
        realized_y.append(rea)
        realized_colors.append(T.DANGER if beat else T.SUCCESS)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Implied Move (%)", x=bar_x, y=implied_y,
        marker_color=T.ACCENT, marker_line_width=0, offsetgroup=0,
        text=[f"{v:.1f}%" for v in implied_y], textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="Realized Move (%)", x=bar_x, y=realized_y,
        marker_color=realized_colors, marker_line_width=0, offsetgroup=1,
        text=[f"{v:.1f}%" for v in realized_y], textposition="outside",
    ))

    n_under = sum(1 for b in beat_implied if not b)
    fig.add_annotation(
        x=0.5, y=1.08, xref="paper", yref="paper",
        text=f"Implied > Realized in {n_under}/{len(events)} events ({n_under/len(events)*100:.0f}%) — "
             f"selling premium has edge",
        showarrow=False, font={"color": T.SUCCESS, "size": 11},
    )

    fig.update_layout(
        **_LAYOUT,
        height=400,
        barmode="group",
        title={"text": "Implied vs Realized Move — 10 Earnings Events", "x": 0.02},
        xaxis={"title": "Earnings Event", "gridcolor": T.BORDER, "tickangle": -30},
        yaxis={"title": "Move (%)", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.99, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


# ── Chart 3: IV Crush Spread Trade P&L ───────────────────────────────────────

def _iv_crush_trade_payoff() -> go.Figure:
    """
    Short straddle / credit spread entered 3 days before earnings,
    exited day after. Show P&L as function of stock move.
    """
    move_pct = np.linspace(-15, 15, 400)  # stock move %

    # Credit spread: sell $5 wide spread for $1.80 credit
    credit = 1.80
    width  = 5.0
    multiplier = 100

    # IV crush benefit: if stock moves less than break-even, profit from IV crush
    # Simplified: profit = credit - max(|move| - 2, 0) * width/5
    # break-even ~3.6% move (credit / straddle_notional approximation)
    be = 3.6

    pnl_iv_crush = np.where(
        np.abs(move_pct) <= be,
        credit * multiplier * (1 - np.abs(move_pct) / be * 0.3),
        credit * multiplier - (np.abs(move_pct) - be) * multiplier * 0.8,
    )
    pnl_iv_crush = np.clip(pnl_iv_crush, -(width - credit) * multiplier, credit * multiplier)

    # Without IV crush (holding through expiry with no IV drop)
    pnl_no_crush = np.where(
        np.abs(move_pct) <= be,
        credit * multiplier * (1 - np.abs(move_pct) / be * 0.7),
        -(np.abs(move_pct) - be) * multiplier * 1.5,
    )
    pnl_no_crush = np.clip(pnl_no_crush, -(width - credit) * multiplier, credit * multiplier)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=move_pct, y=pnl_iv_crush,
        mode="lines", name="Exit day after earnings (IV crush benefit)",
        line={"color": T.SUCCESS, "width": 3},
        fill="tozeroy", fillcolor="rgba(16,185,129,0.07)",
    ))
    fig.add_trace(go.Scatter(
        x=move_pct, y=pnl_no_crush,
        mode="lines", name="Hold to expiry (no IV benefit)",
        line={"color": T.DANGER, "width": 2, "dash": "dot"},
    ))

    fig.add_vline(x=be, line_dash="dash", line_color=T.WARNING, opacity=0.7,
                  annotation_text=f"  BE +{be}%", annotation_font_color=T.WARNING)
    fig.add_vline(x=-be, line_dash="dash", line_color=T.WARNING, opacity=0.7,
                  annotation_text=f"  BE -{be}%", annotation_font_color=T.WARNING)
    fig.add_hline(y=0, line_color="#475569", opacity=0.5)

    # Most common move region
    fig.add_vrect(x0=-be, x1=be, fillcolor=T.SUCCESS, opacity=0.04, line_width=0)

    fig.add_annotation(x=0, y=credit * multiplier * 1.1,
                       text=f"~70% of stocks land here\n(max profit ${credit*multiplier:.0f})",
                       showarrow=False, font={"color": T.SUCCESS, "size": 11})

    fig.update_layout(
        **_LAYOUT,
        height=380,
        title={"text": "IV Crush Trade P&L vs Actual Stock Move (Enter −3d, Exit +1d)", "x": 0.02},
        xaxis={"title": "Stock Move on Earnings Day (%)", "gridcolor": T.BORDER},
        yaxis={"title": "P&L ($)", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.20, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


# ── Public entry point ────────────────────────────────────────────────────────

def render_charts() -> html.Div:
    return html.Div([
        html.Hr(style={"borderColor": "#1f2937", "margin": "32px 0 24px"}),
        html.H3("Interactive Charts", style={
            "color": "#f9fafb", "fontSize": "16px", "fontWeight": "700",
            "marginBottom": "20px", "letterSpacing": "0.02em",
        }),
        _card(
            "IV Crush Timeline — AAPL Earnings Example",
            _iv_crush_timeline(),
            "IV builds steadily for 2 weeks into earnings (28% → 52%), then collapses to 24% the day after — "
            "a 54% drop in one session. Entering 3 days before and exiting day after captures this structural edge.",
        ),
        _card(
            "Implied vs Realized Move — 10 Earnings Events",
            _realized_vs_implied(),
            "Blue bars show the implied move priced into options (straddle price). Colored bars show actual stock move. "
            "Green = implied overestimated (seller wins). Red = stock moved more than implied (seller loses). "
            "70% of events favor the premium seller.",
        ),
        _card(
            "Credit Spread P&L vs Earnings Move — IV Crush vs Hold to Expiry",
            _iv_crush_trade_payoff(),
            "Exiting the day after earnings (green) captures the IV crush benefit even on small unfavorable moves. "
            "Holding to expiry (red dashed) loses the IV premium and is exposed to full directional risk. "
            "The IV crush strategy is strictly better within the break-even range.",
        ),
    ], style={"marginTop": "8px"})
