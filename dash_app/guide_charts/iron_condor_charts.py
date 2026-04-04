"""Interactive Plotly charts for the Iron Condor guide article."""
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


# ── Chart 1: Iron Condor Payoff Diagram ──────────────────────────────────────

def _payoff_chart() -> go.Figure:
    """SPY 580/585 call spread + 555/550 put spread, $2.15 net credit."""
    S = np.linspace(530, 605, 600)

    short_put_k = 555.0
    long_put_k  = 550.0
    short_call_k = 580.0
    long_call_k  = 585.0
    credit = 2.15
    multiplier = 100

    # Per-share P&L at expiry
    put_spread_pnl  = np.where(
        S >= short_put_k,  credit / 2,
        np.where(S <= long_put_k, credit / 2 - (short_put_k - long_put_k),
                 credit / 2 - (short_put_k - S))
    )
    call_spread_pnl = np.where(
        S <= short_call_k, credit / 2,
        np.where(S >= long_call_k, credit / 2 - (long_call_k - short_call_k),
                 credit / 2 - (S - short_call_k))
    )
    total_pnl = (put_spread_pnl + call_spread_pnl) * multiplier

    be_lower = short_put_k - credit
    be_upper = short_call_k + credit
    max_profit = credit * multiplier
    max_loss   = ((short_put_k - long_put_k) - credit) * multiplier

    fig = go.Figure()

    # Max loss zones (shaded)
    fig.add_vrect(x0=530, x1=be_lower, fillcolor=T.DANGER, opacity=0.08, line_width=0,
                  annotation_text="Max Loss Zone", annotation_font_color=T.DANGER,
                  annotation_font_size=10, annotation_position="top right")
    fig.add_vrect(x0=be_upper, x1=605, fillcolor=T.DANGER, opacity=0.08, line_width=0,
                  annotation_text="Max Loss Zone", annotation_font_color=T.DANGER,
                  annotation_font_size=10, annotation_position="top left")

    # Max profit zone (shaded)
    fig.add_vrect(x0=be_lower, x1=be_upper, fillcolor=T.SUCCESS, opacity=0.06, line_width=0,
                  annotation_text="Max Profit Zone", annotation_font_color=T.SUCCESS,
                  annotation_font_size=10, annotation_position="top left")

    fig.add_trace(go.Scatter(
        x=S, y=total_pnl, mode="lines", name="Iron Condor P&L",
        line={"color": T.ACCENT, "width": 3},
    ))

    # Strike verticals
    for k, label in [(long_put_k, "Long Put $550"), (short_put_k, "Short Put $555"),
                     (short_call_k, "Short Call $580"), (long_call_k, "Long Call $585")]:
        fig.add_vline(x=k, line_dash="dash", line_color="#475569", opacity=0.6,
                      annotation_text=f"  {label}", annotation_font_color="#94a3b8",
                      annotation_font_size=10)

    # Break-even lines
    fig.add_vline(x=be_lower, line_dash="dot", line_color=T.WARNING, opacity=0.8,
                  annotation_text=f"  BE ${be_lower:.2f}", annotation_font_color=T.WARNING)
    fig.add_vline(x=be_upper, line_dash="dot", line_color=T.WARNING, opacity=0.8,
                  annotation_text=f"  BE ${be_upper:.2f}", annotation_font_color=T.WARNING)
    fig.add_hline(y=0, line_color="#475569", opacity=0.5)

    # Annotations
    fig.add_annotation(x=567.5, y=max_profit + 5,
                       text=f"Max Profit: ${max_profit:.0f}", showarrow=False,
                       font={"color": T.SUCCESS, "size": 12})
    fig.add_annotation(x=540, y=max_loss - 15,
                       text=f"Max Loss: ${max_loss:.0f}", showarrow=False,
                       font={"color": T.DANGER, "size": 12})

    fig.update_layout(
        **_LAYOUT,
        height=400,
        title={"text": "Iron Condor Payoff — SPY 550/555 Put Spread + 580/585 Call Spread, $2.15 Credit", "x": 0.02},
        xaxis={"title": "SPY Price at Expiry ($)", "gridcolor": T.BORDER},
        yaxis={"title": "P&L ($)", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.99, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


# ── Chart 2: IVR Entry Zone ───────────────────────────────────────────────────

def _ivr_chart() -> go.Figure:
    tickers = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMZN", "IWM", "GLD"]
    ivr     = [68, 53, 41, 82, 29, 55, 71, 18]
    colors  = [T.SUCCESS if v >= 50 else T.WARNING if v >= 30 else T.DANGER for v in ivr]

    fig = go.Figure(go.Bar(
        x=tickers, y=ivr,
        marker_color=colors, marker_line_width=0,
        text=[f"{v}%" for v in ivr], textposition="outside",
    ))

    fig.add_hline(y=50, line_dash="dash", line_color=T.SUCCESS, opacity=0.8,
                  annotation_text=" IVR 50% — Entry Threshold", annotation_font_color=T.SUCCESS)
    fig.add_hline(y=30, line_dash="dash", line_color=T.WARNING, opacity=0.6,
                  annotation_text=" IVR 30% — Caution", annotation_font_color=T.WARNING)

    fig.update_layout(
        **_LAYOUT,
        height=340,
        title={"text": "IVR Screener — Entry Zone by Ticker", "x": 0.02},
        xaxis={"title": "Ticker", "gridcolor": T.BORDER},
        yaxis={"title": "IV Rank (%)", "gridcolor": T.BORDER, "range": [0, 105]},
        showlegend=False,
    )
    return fig


# ── Chart 3: Theta Decay Curve ────────────────────────────────────────────────

def _theta_decay_chart() -> go.Figure:
    t_range = np.linspace(0, 45, 300)  # DTE from 45 down to 0
    dte_axis = 45 - t_range            # DTE decreasing

    # Time value = premium * sqrt(DTE/45) — simplified theta model
    base_premium = 3.50

    def tv(dte_start, premium):
        dtes = np.linspace(dte_start, 0, 300)
        return dtes, premium * np.sqrt(dtes / dte_start)

    colors = [T.ACCENT, T.SUCCESS, T.WARNING, T.DANGER]
    labels = ["45 DTE (entry)", "30 DTE", "21 DTE", "7 DTE (exit zone)"]
    starts = [45, 30, 21, 7]

    fig = go.Figure()
    for start, label, color in zip(starts, labels, colors):
        dtes, vals = tv(start, base_premium * np.sqrt(start / 45))
        fig.add_trace(go.Scatter(
            x=dtes, y=vals, mode="lines", name=label,
            line={"color": color, "width": 2},
        ))

    # Highlight the acceleration zone
    fig.add_vrect(x0=0, x1=21, fillcolor=T.DANGER, opacity=0.06, line_width=0,
                  annotation_text="Theta Acceleration Zone\n(hold through here)",
                  annotation_font_color=T.DANGER, annotation_font_size=10,
                  annotation_position="top right")

    fig.add_vline(x=21, line_dash="dash", line_color=T.WARNING, opacity=0.7,
                  annotation_text="  21 DTE — Consider Exit", annotation_font_color=T.WARNING)

    fig.update_layout(
        **_LAYOUT,
        height=360,
        title={"text": "Theta Decay — Time Value Erosion Accelerates Near Expiry", "x": 0.02},
        xaxis={"title": "Days to Expiry (DTE)", "gridcolor": T.BORDER, "autorange": "reversed"},
        yaxis={"title": "Remaining Time Value ($)", "gridcolor": T.BORDER},
        legend={"x": 0.75, "y": 0.99, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


# ── Chart 4: Win Rate by IVR Zone ─────────────────────────────────────────────

def _win_rate_ivr_chart() -> go.Figure:
    zones    = ["0–30% IVR", "30–50% IVR", "50–70% IVR", "70%+ IVR"]
    win_rate = [38, 55, 74, 81]
    avg_pnl  = [-320, 90, 410, 590]
    colors_wr  = [T.DANGER if w < 50 else T.WARNING if w < 65 else T.SUCCESS for w in win_rate]
    colors_pnl = [T.DANGER if p < 0 else T.SUCCESS for p in avg_pnl]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Win Rate by IVR Band (%)", "Avg P&L per Trade ($)"),
        horizontal_spacing=0.12,
    )

    fig.add_trace(go.Bar(
        x=zones, y=win_rate, marker_color=colors_wr, marker_line_width=0,
        text=[f"{w}%" for w in win_rate], textposition="outside",
        name="Win Rate", showlegend=False,
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=zones, y=avg_pnl, marker_color=colors_pnl, marker_line_width=0,
        text=[f"${p:+,}" for p in avg_pnl], textposition="outside",
        name="Avg P&L", showlegend=False,
    ), row=1, col=2)

    fig.add_hline(y=50, line_dash="dash", line_color=T.TEXT_SEC, opacity=0.5,
                  row=1, col=1, annotation_text=" 50% breakeven",
                  annotation_font_color=T.TEXT_SEC, annotation_font_size=10)
    fig.add_hline(y=0, line_color=T.TEXT_SEC, opacity=0.4, row=1, col=2)

    fig.update_layout(
        **_LAYOUT,
        height=360,
        yaxis={"title": "Win Rate (%)", "range": [0, 105], "gridcolor": T.BORDER},
        yaxis2={"title": "P&L ($)", "gridcolor": T.BORDER},
        xaxis={"gridcolor": T.BORDER},
        xaxis2={"gridcolor": T.BORDER},
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
            "Iron Condor Payoff at Expiry — SPY 550/555/580/585",
            _payoff_chart(),
            "Short strangle wrapped in wings. Max profit $215 is collected if SPY stays between $552.85 and $582.15 "
            "at expiry. Max loss $285 per side if price runs through a wing. Risk/reward ~1.3:1 — win rate must exceed 57% to be profitable.",
        ),
        _card(
            "IVR Screener — Which Tickers Are in the Entry Zone?",
            _ivr_chart(),
            "Green bars (IVR >= 50%) are prime iron condor candidates: IV is elevated relative to its 52-week range, "
            "making premium rich. Red bars (IVR < 30%) indicate low-IV environments where premium is too thin.",
        ),
        _card(
            "Theta Decay — Time Value Erosion by Starting DTE",
            _theta_decay_chart(),
            "The curve flattens at high DTE and steepens approaching expiry. Entering at 45 DTE captures the "
            "steepening phase. The 21 DTE rule: close or roll before entering the rapid-decay zone where gamma risk spikes.",
        ),
        _card(
            "Win Rate & Avg P&L by IVR Band",
            _win_rate_ivr_chart(),
            "Iron condors entered in high-IVR environments (50-70%+) show significantly better outcomes. "
            "Low IVR trades (< 30%) underperform — the premium collected does not compensate for the risk taken.",
        ),
    ], style={"marginTop": "8px"})
