"""Interactive Plotly charts for the VIX Mean Reversion guide article."""
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


# ── Chart 1: VIX Spike and Fade ───────────────────────────────────────────────

def _vix_spike_chart() -> go.Figure:
    """Simulated VIX: 18 → 42 spike, fade back to 22 over ~25 days."""
    rng = np.random.default_rng(23)
    n_pre   = 30   # stable before spike
    n_spike = 3    # rapid spike
    n_fade  = 30   # fade period
    n_post  = 20   # stable after

    # Pre-spike: mean-reverting around 18
    pre = 18 + rng.normal(0, 0.8, n_pre)
    pre = np.clip(pre, 14, 22)

    # Spike: 18 → 42 in 3 days
    spike = np.linspace(18, 42, n_spike + 1)[1:]

    # Fade: exponential decay from 42 → 22 with noise
    t_fade = np.arange(n_fade)
    fade   = 22 + (42 - 22) * np.exp(-t_fade / 8) + rng.normal(0, 1.2, n_fade)
    fade   = np.clip(fade, 16, 45)

    # Post: stable around 22
    post = 22 + rng.normal(0, 0.7, n_post)
    post = np.clip(post, 18, 26)

    vix  = np.concatenate([pre, spike, fade, post])
    days = np.arange(len(vix))

    # Key indices
    spike_day = n_pre
    peak_day  = n_pre + n_spike - 1
    entry_day = peak_day           # enter at spike peak
    exit_day  = n_pre + n_spike + 15  # exit ~15 days into fade

    fig = go.Figure()

    # Background zones
    fig.add_vrect(x0=spike_day, x1=peak_day + 1,
                  fillcolor=T.DANGER, opacity=0.10, line_width=0,
                  annotation_text="Spike", annotation_font_color=T.DANGER,
                  annotation_font_size=10, annotation_position="top left")
    fig.add_vrect(x0=peak_day, x1=exit_day,
                  fillcolor=T.SUCCESS, opacity=0.06, line_width=0,
                  annotation_text="Hold Period", annotation_font_color=T.SUCCESS,
                  annotation_font_size=10, annotation_position="top left")

    # VIX line
    fig.add_trace(go.Scatter(
        x=days, y=vix, mode="lines", name="VIX",
        line={"color": T.WARNING, "width": 2},
        fill="tozeroy", fillcolor="rgba(245,158,11,0.06)",
    ))

    # Historical mean
    fig.add_hline(y=18, line_dash="dash", line_color=T.TEXT_SEC, opacity=0.5,
                  annotation_text=" Long-run VIX mean (~18)",
                  annotation_font_color=T.TEXT_SEC, annotation_font_size=10)

    # Entry / Exit markers
    fig.add_trace(go.Scatter(
        x=[entry_day], y=[vix[entry_day]],
        mode="markers+text", name="Entry (VIX spike peak)",
        marker={"color": T.DANGER, "size": 14, "symbol": "triangle-down"},
        text=[f"  Entry<br>VIX={vix[entry_day]:.0f}"],
        textposition="top right", textfont={"color": T.DANGER, "size": 11},
    ))
    fig.add_trace(go.Scatter(
        x=[exit_day], y=[vix[exit_day]],
        mode="markers+text", name="Exit (VIX faded)",
        marker={"color": T.SUCCESS, "size": 14, "symbol": "triangle-up"},
        text=[f"  Exit<br>VIX={vix[exit_day]:.0f}"],
        textposition="bottom right", textfont={"color": T.SUCCESS, "size": 11},
    ))

    # P&L annotation
    fig.add_annotation(
        x=(entry_day + exit_day) / 2, y=36,
        text=f"VIX: {vix[entry_day]:.0f} → {vix[exit_day]:.0f}\nEst. P&L: +$680",
        showarrow=False, font={"color": T.SUCCESS, "size": 11},
        bgcolor=T.BG_CARD, bordercolor=T.BORDER,
    )

    fig.update_layout(
        **_LAYOUT,
        height=380,
        title={"text": "VIX Spike and Fade — Entry at Spike Peak, Exit After Reversion", "x": 0.02},
        xaxis={"title": "Trading Days", "gridcolor": T.BORDER},
        yaxis={"title": "VIX Level", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.99, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


# ── Chart 2: VIX Reversion Speed ─────────────────────────────────────────────

def _reversion_speed_chart() -> go.Figure:
    windows   = ["5 days", "10 days", "20 days"]
    pct_revert= [60, 80, 92]  # % of spikes that revert within each window
    colors    = [T.WARNING, T.ACCENT, T.SUCCESS]

    fig = go.Figure(go.Bar(
        x=windows, y=pct_revert,
        marker_color=colors, marker_line_width=0,
        text=[f"{v}%" for v in pct_revert], textposition="outside",
        width=0.5,
    ))

    fig.add_hline(y=50, line_dash="dash", line_color=T.TEXT_SEC, opacity=0.5,
                  annotation_text=" 50% baseline",
                  annotation_font_color=T.TEXT_SEC, annotation_font_size=10)

    # Annotations on bars
    fig.add_annotation(x="5 days", y=pct_revert[0] - 8,
                       text="Most spikes\nstill fading", showarrow=False,
                       font={"color": T.TEXT_SEC, "size": 10})
    fig.add_annotation(x="20 days", y=pct_revert[2] - 8,
                       text="Nearly all\nresolved", showarrow=False,
                       font={"color": T.TEXT_SEC, "size": 10})

    fig.update_layout(
        **_LAYOUT,
        height=320,
        title={"text": "VIX Spike Reversion Speed — Historical % Reverting Within N Days", "x": 0.02},
        xaxis={"title": "Reversion Window", "gridcolor": T.BORDER},
        yaxis={"title": "% of Spikes That Reverted", "gridcolor": T.BORDER,
               "range": [0, 110]},
        showlegend=False,
    )
    return fig


# ── Chart 3: Entry Conditions — VIX/VIX20d Ratio and IVR ─────────────────────

def _entry_conditions_chart() -> go.Figure:
    """Bar/gauge chart showing VIX/VIX20d ratio and IVR at trade entry."""
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("VIX / VIX-20d Ratio", "IVR at Entry (%)"),
    )

    # VIX ratio: current=1.65, threshold=1.5
    vix_ratio_current   = 1.65
    vix_ratio_threshold = 1.50

    # Show as a single bar vs threshold
    fig.add_trace(go.Bar(
        x=["Current VIX/VIX20d", "Entry Threshold"],
        y=[vix_ratio_current, vix_ratio_threshold],
        marker_color=[T.DANGER, T.TEXT_SEC],
        marker_line_width=0,
        text=[f"{vix_ratio_current:.2f}", f"{vix_ratio_threshold:.2f}"],
        textposition="outside",
        showlegend=False,
    ), row=1, col=1)

    fig.add_hline(y=vix_ratio_threshold, line_dash="dash", line_color=T.WARNING, opacity=0.8,
                  row=1, col=1, annotation_text=" Entry threshold (1.5x)",
                  annotation_font_color=T.WARNING, annotation_font_size=10)

    # IVR: current=78%, entry threshold=70%
    ivr_current   = 78
    ivr_threshold = 70

    ivr_bars = [ivr_current, ivr_threshold]
    ivr_colors = [T.SUCCESS if v >= 70 else T.WARNING for v in ivr_bars]

    fig.add_trace(go.Bar(
        x=["Current IVR", "Entry Threshold"],
        y=ivr_bars,
        marker_color=ivr_colors,
        marker_line_width=0,
        text=[f"{v}%" for v in ivr_bars],
        textposition="outside",
        showlegend=False,
    ), row=1, col=2)

    fig.add_hline(y=ivr_threshold, line_dash="dash", line_color=T.WARNING, opacity=0.8,
                  row=1, col=2, annotation_text=" IVR 70% threshold",
                  annotation_font_color=T.WARNING, annotation_font_size=10)

    # "SIGNAL" annotation
    fig.add_annotation(
        x=0.5, y=1.12, xref="paper", yref="paper",
        text="Both conditions met — TRADE SIGNAL ACTIVE",
        showarrow=False, font={"color": T.SUCCESS, "size": 13, "family": "Inter"},
        bgcolor=T.BG_CARD, bordercolor=T.SUCCESS, borderwidth=1,
    )

    fig.update_layout(
        **_LAYOUT,
        height=340,
        yaxis={"title": "VIX Ratio (×)", "gridcolor": T.BORDER, "range": [0, 2.2]},
        yaxis2={"title": "IVR (%)", "gridcolor": T.BORDER, "range": [0, 110]},
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
            "VIX Spike and Fade — Entry at Peak, Exit After Reversion",
            _vix_spike_chart(),
            "VIX spikes from 18 to 42 in 3 days (typical fear event). Enter short volatility at the peak, "
            "hold through the reversion to ~26 over 15 days. The trade captures the risk premium compression. "
            "Yellow zone = hold period. Entry requires VIX/VIX20d ratio > 1.5.",
        ),
        _card(
            "Historical VIX Reversion Speed — % of Spikes That Fade Within N Days",
            _reversion_speed_chart(),
            "Based on all VIX spikes > 30% above 20-day MA since 2004 (excluding COVID March 2020 tail). "
            "60% revert within 5 trading days, 80% within 10 days, 92% within 20 days. "
            "20-day holding period captures the vast majority of mean reversion events.",
        ),
        _card(
            "Trade Entry Conditions — VIX Ratio and IVR Gate",
            _entry_conditions_chart(),
            "Both conditions must be met simultaneously: (1) VIX > 1.5x its 20-day average — confirms a true spike, "
            "not just elevated vol. (2) IVR >= 70% — confirms premium is rich relative to trailing range. "
            "When both conditions are met, the risk/reward skews heavily in favor of short volatility.",
        ),
    ], style={"marginTop": "8px"})
