"""Interactive Plotly charts for the SPY/QQQ Pairs Trading guide article."""
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


def _simulate_ratio(n_days=504, mean=3.20, theta=0.03, sigma=0.018, seed=42):
    """Ornstein-Uhlenbeck mean-reverting ratio process."""
    rng = np.random.default_rng(seed)
    ratio = np.zeros(n_days)
    ratio[0] = mean
    for i in range(1, n_days):
        ratio[i] = ratio[i-1] + theta * (mean - ratio[i-1]) + sigma * rng.normal()
    return ratio


# ── Chart 1: QQQ/SPY Ratio with Entry/Exit Signals ───────────────────────────

def _ratio_chart() -> go.Figure:
    n = 504  # ~2 trading years
    dates = np.arange(n)
    ratio = _simulate_ratio(n)

    # Rolling stats for z-score
    window = 60
    roll_mean = np.array([ratio[max(0,i-window):i+1].mean() for i in range(n)])
    roll_std  = np.array([ratio[max(0,i-window):i+1].std() if i >= window else 0.018 for i in range(n)])
    zscore    = np.where(roll_std > 0, (ratio - roll_mean) / roll_std, 0)

    # Entry/exit: z > 2 => ratio too high => short QQQ/long SPY; z < -2 => long QQQ/short SPY
    entries_high = np.where((zscore > 2.0) & (np.roll(zscore, 1) <= 2.0))[0]
    entries_low  = np.where((zscore < -2.0) & (np.roll(zscore, 1) >= -2.0))[0]
    exits_high   = np.where((zscore < 0.5) & (np.roll(zscore, 1) >= 0.5) &
                             (np.arange(n) > (entries_high.min() if len(entries_high) else 0)))[0]
    exits_low    = np.where((zscore > -0.5) & (np.roll(zscore, 1) <= -0.5) &
                             (np.arange(n) > (entries_low.min() if len(entries_low) else 0)))[0]

    fig = go.Figure()

    # Ratio line
    fig.add_trace(go.Scatter(
        x=dates, y=ratio, mode="lines", name="QQQ/SPY Ratio",
        line={"color": T.ACCENT, "width": 2},
    ))

    # Mean line
    fig.add_hline(y=3.20, line_dash="dash", line_color=T.TEXT_SEC, opacity=0.6,
                  annotation_text=" Long-run mean (3.20)",
                  annotation_font_color=T.TEXT_SEC, annotation_font_size=10)

    # Upper/lower bands (2 std)
    upper = roll_mean + 2 * roll_std
    lower = roll_mean - 2 * roll_std

    fig.add_trace(go.Scatter(
        x=dates, y=upper, mode="lines", name="+2 STD Band",
        line={"color": T.DANGER, "width": 1, "dash": "dot"},
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=lower, mode="lines", name="-2 STD Band",
        line={"color": T.SUCCESS, "width": 1, "dash": "dot"},
        fill="tonexty", fillcolor="rgba(99,102,241,0.04)",
    ))

    # Entry signals (ratio too high — short QQQ/long SPY)
    if len(entries_high):
        fig.add_trace(go.Scatter(
            x=entries_high[:4], y=ratio[entries_high[:4]],
            mode="markers", name="Enter: Short QQQ / Long SPY",
            marker={"color": T.DANGER, "size": 12, "symbol": "triangle-down"},
        ))

    # Entry signals (ratio too low — long QQQ/short SPY)
    if len(entries_low):
        fig.add_trace(go.Scatter(
            x=entries_low[:4], y=ratio[entries_low[:4]],
            mode="markers", name="Enter: Long QQQ / Short SPY",
            marker={"color": T.SUCCESS, "size": 12, "symbol": "triangle-up"},
        ))

    fig.update_layout(
        **_LAYOUT,
        height=380,
        title={"text": "QQQ/SPY Price Ratio — 2-Year Simulated Mean-Reverting Series", "x": 0.02},
        xaxis={"title": "Trading Days", "gridcolor": T.BORDER},
        yaxis={"title": "QQQ / SPY Ratio", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.99, "bgcolor": "rgba(0,0,0,0)", "font": {"size": 11}},
    )
    return fig


# ── Chart 2: Z-Score Chart with Entry/Exit Bands ─────────────────────────────

def _zscore_chart() -> go.Figure:
    n = 504
    dates = np.arange(n)
    ratio = _simulate_ratio(n)

    window = 60
    roll_mean = np.array([ratio[max(0,i-window):i+1].mean() for i in range(n)])
    roll_std  = np.array([ratio[max(0,i-window):i+1].std() if i >= window else 0.018 for i in range(n)])
    zscore    = np.where(roll_std > 0, (ratio - roll_mean) / roll_std, 0)

    # Color the z-score trace by zone
    colors_above = "rgba(239,68,68,0.15)"
    colors_below = "rgba(16,185,129,0.15)"

    fig = go.Figure()

    # Fill above +2 and below -2
    fig.add_hrect(y0=2, y1=5, fillcolor=T.DANGER, opacity=0.08, line_width=0,
                  annotation_text="Short QQQ / Long SPY zone",
                  annotation_font_color=T.DANGER, annotation_font_size=10,
                  annotation_position="top right")
    fig.add_hrect(y0=-5, y1=-2, fillcolor=T.SUCCESS, opacity=0.08, line_width=0,
                  annotation_text="Long QQQ / Short SPY zone",
                  annotation_font_color=T.SUCCESS, annotation_font_size=10,
                  annotation_position="bottom right")

    fig.add_trace(go.Scatter(
        x=dates, y=zscore, mode="lines", name="Z-Score (60d rolling)",
        line={"color": T.ACCENT, "width": 2},
        fill="tozeroy", fillcolor="rgba(99,102,241,0.06)",
    ))

    # Reference lines
    for level, color, label in [(2, T.DANGER, "Entry: +2 STD"),
                                  (-2, T.SUCCESS, "Entry: -2 STD"),
                                  (0.5, "#475569", "Exit: +0.5"),
                                  (-0.5, "#475569", "Exit: -0.5")]:
        fig.add_hline(y=level, line_dash="dash", line_color=color, opacity=0.7,
                      annotation_text=f" {label}", annotation_font_color=color,
                      annotation_font_size=10)

    fig.update_layout(
        **_LAYOUT,
        height=340,
        title={"text": "Rolling Z-Score of QQQ/SPY Ratio (60-day window)", "x": 0.02},
        xaxis={"title": "Trading Days", "gridcolor": T.BORDER},
        yaxis={"title": "Z-Score (standard deviations)", "gridcolor": T.BORDER,
               "range": [-4.5, 4.5]},
        showlegend=False,
    )
    return fig


# ── Chart 3: SPY vs QQQ Daily Return Scatter ─────────────────────────────────

def _scatter_chart() -> go.Figure:
    rng = np.random.default_rng(99)
    n = 504

    # Simulate correlated daily returns (correlation ~0.92)
    spy_ret = rng.normal(0.04, 1.0, n)
    qqq_ret = 1.15 * spy_ret + rng.normal(0, 0.35, n)  # beta ~1.15, some idio

    # Identify "deviation" days (residual > 1 std)
    residual = qqq_ret - 1.15 * spy_ret
    res_std  = residual.std()
    deviation = np.abs(residual) > 1.5 * res_std

    # OLS line
    m, b = np.polyfit(spy_ret, qqq_ret, 1)
    x_fit = np.array([spy_ret.min(), spy_ret.max()])
    y_fit = m * x_fit + b

    fig = go.Figure()

    # Normal correlation days
    fig.add_trace(go.Scatter(
        x=spy_ret[~deviation], y=qqq_ret[~deviation],
        mode="markers", name="Correlated days",
        marker={"color": T.ACCENT, "size": 5, "opacity": 0.5,
                "line": {"width": 0}},
    ))

    # Deviation days
    fig.add_trace(go.Scatter(
        x=spy_ret[deviation], y=qqq_ret[deviation],
        mode="markers", name="Deviation (pairs entry signal)",
        marker={"color": T.WARNING, "size": 8, "symbol": "circle-open",
                "line": {"width": 2, "color": T.WARNING}},
    ))

    # Regression line
    fig.add_trace(go.Scatter(
        x=x_fit, y=y_fit, mode="lines",
        name=f"Regression (beta={m:.2f})",
        line={"color": T.SUCCESS, "width": 2, "dash": "dash"},
    ))

    fig.add_hline(y=0, line_color="#475569", opacity=0.3)
    fig.add_vline(x=0, line_color="#475569", opacity=0.3)

    # Correlation annotation
    corr = np.corrcoef(spy_ret, qqq_ret)[0, 1]
    fig.add_annotation(
        x=0.02, y=0.96, xref="paper", yref="paper",
        text=f"Correlation: {corr:.3f}  |  Beta: {m:.2f}  |  "
             f"Deviation days: {deviation.sum()} ({deviation.mean()*100:.0f}%)",
        showarrow=False, font={"color": T.TEXT_SEC, "size": 11},
        bgcolor=T.BG_CARD, bordercolor=T.BORDER,
    )

    fig.update_layout(
        **_LAYOUT,
        height=400,
        title={"text": "SPY vs QQQ Daily Returns — Correlation & Deviation Analysis", "x": 0.02},
        xaxis={"title": "SPY Daily Return (%)", "gridcolor": T.BORDER},
        yaxis={"title": "QQQ Daily Return (%)", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.99, "bgcolor": "rgba(0,0,0,0)"},
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
            "QQQ/SPY Ratio — 2-Year Mean-Reverting Series with Entry Signals",
            _ratio_chart(),
            "The QQQ/SPY ratio fluctuates around a long-run mean (~3.20). "
            "Triangles mark entry signals when the ratio stretches beyond ±2 standard deviations from its 60-day moving average. "
            "Mean-reversion typically occurs within 5-15 trading days.",
        ),
        _card(
            "Rolling Z-Score — Entry and Exit Thresholds",
            _zscore_chart(),
            "The z-score normalizes the ratio deviation by its rolling standard deviation. "
            "Entries at z > +2 (short QQQ, long SPY) or z < -2 (long QQQ, short SPY). "
            "Exits when z reverts to within ±0.5 of the mean. Red/green zones highlight active trade regions.",
        ),
        _card(
            "SPY vs QQQ Daily Returns — Correlation Structure",
            _scatter_chart(),
            "Near-perfect correlation (r > 0.92) in normal markets. Orange circles mark 'deviation days' where "
            "one leg diverges significantly from the regression line. These are the entry catalysts for the pairs trade. "
            "Beta ~1.15 means QQQ amplifies SPY moves — hedge ratio must account for this.",
        ),
    ], style={"marginTop": "8px"})
