"""Interactive Plotly charts for the Stat Arb / ETF Basket guide article."""
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


# ── Chart 1: Basket Spread Z-Score ────────────────────────────────────────────

def _basket_zscore_chart() -> go.Figure:
    """XLF vs sector basket spread — mean-reverting OU process."""
    rng = np.random.default_rng(17)
    n   = 252
    days = np.arange(n)

    # OU process: spread z-score
    z = np.zeros(n)
    z[0] = 0.0
    for i in range(1, n):
        z[i] = z[i-1] * 0.97 + rng.normal(0, 0.18)

    # Entry/exit signals
    entry_threshold = 2.0
    exit_threshold  = 0.3

    in_trade = False
    entry_days_long  = []
    entry_days_short = []
    exit_days        = []
    trade_type       = None

    for i in range(1, n):
        if not in_trade:
            if z[i] > entry_threshold:
                entry_days_short.append(i)
                in_trade = True
                trade_type = "short"
            elif z[i] < -entry_threshold:
                entry_days_long.append(i)
                in_trade = True
                trade_type = "long"
        else:
            if trade_type == "short" and z[i] < exit_threshold:
                exit_days.append(i)
                in_trade = False
            elif trade_type == "long" and z[i] > -exit_threshold:
                exit_days.append(i)
                in_trade = False

    fig = go.Figure()

    # Background shading for extreme zones
    fig.add_hrect(y0=2, y1=5, fillcolor=T.DANGER, opacity=0.07, line_width=0,
                  annotation_text="Short Spread Zone",
                  annotation_font_color=T.DANGER, annotation_font_size=10,
                  annotation_position="top right")
    fig.add_hrect(y0=-5, y1=-2, fillcolor=T.SUCCESS, opacity=0.07, line_width=0,
                  annotation_text="Long Spread Zone",
                  annotation_font_color=T.SUCCESS, annotation_font_size=10,
                  annotation_position="bottom right")

    # Z-score line
    fig.add_trace(go.Scatter(
        x=days, y=z, mode="lines", name="Spread Z-Score",
        line={"color": T.ACCENT, "width": 2},
        fill="tozeroy", fillcolor="rgba(99,102,241,0.06)",
    ))

    # Threshold lines
    for level, color, label in [(2, T.DANGER, "+2σ entry"),
                                  (-2, T.SUCCESS, "−2σ entry"),
                                  (0.3, "#475569", "exit"),
                                  (-0.3, "#475569", "exit")]:
        fig.add_hline(y=level, line_dash="dash", line_color=color, opacity=0.6,
                      annotation_text=f" {label}", annotation_font_color=color,
                      annotation_font_size=10)

    # Entry markers
    if entry_days_short:
        fig.add_trace(go.Scatter(
            x=entry_days_short[:5], y=z[entry_days_short[:5]],
            mode="markers", name="Enter Short Spread",
            marker={"color": T.DANGER, "size": 12, "symbol": "triangle-down"},
        ))
    if entry_days_long:
        fig.add_trace(go.Scatter(
            x=entry_days_long[:5], y=z[entry_days_long[:5]],
            mode="markers", name="Enter Long Spread",
            marker={"color": T.SUCCESS, "size": 12, "symbol": "triangle-up"},
        ))
    if exit_days:
        fig.add_trace(go.Scatter(
            x=exit_days[:8], y=z[exit_days[:8]],
            mode="markers", name="Exit (mean revert)",
            marker={"color": T.WARNING, "size": 10, "symbol": "diamond"},
        ))

    fig.update_layout(
        **_LAYOUT,
        height=380,
        title={"text": "XLF vs Sector Basket — Spread Z-Score with Entry/Exit Signals", "x": 0.02},
        xaxis={"title": "Trading Days", "gridcolor": T.BORDER},
        yaxis={"title": "Z-Score (σ)", "gridcolor": T.BORDER, "range": [-4.5, 4.5]},
        legend={"x": 0.01, "y": 0.99, "bgcolor": "rgba(0,0,0,0)", "font": {"size": 11}},
    )
    return fig


# ── Chart 2: Correlation Heatmap ──────────────────────────────────────────────

def _correlation_heatmap() -> go.Figure:
    tickers = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLV", "XLK"]
    n_tickers = len(tickers)

    # Realistic correlation matrix
    corr = np.array([
        [1.00, 0.93, 0.87, 0.79, 0.62, 0.71, 0.91],
        [0.93, 1.00, 0.80, 0.72, 0.55, 0.63, 0.96],
        [0.87, 0.80, 1.00, 0.76, 0.59, 0.67, 0.78],
        [0.79, 0.72, 0.76, 1.00, 0.48, 0.60, 0.70],
        [0.62, 0.55, 0.59, 0.48, 1.00, 0.41, 0.52],
        [0.71, 0.63, 0.67, 0.60, 0.41, 1.00, 0.61],
        [0.91, 0.96, 0.78, 0.70, 0.52, 0.61, 1.00],
    ])

    # Text annotations
    text = [[f"{corr[i][j]:.2f}" for j in range(n_tickers)] for i in range(n_tickers)]

    fig = go.Figure(go.Heatmap(
        z=corr,
        x=tickers, y=tickers,
        text=text, texttemplate="%{text}",
        colorscale=[
            [0.0, "#1e3a5f"],
            [0.4, "#1f2937"],
            [0.7, "#3b4f6b"],
            [0.85, T.ACCENT],
            [1.0, T.SUCCESS],
        ],
        zmin=0.3, zmax=1.0,
        colorbar={"title": "Correlation", "tickformat": ".2f",
                  "title_font": {"color": T.TEXT_SEC},
                  "tickfont": {"color": T.TEXT_SEC}},
        showscale=True,
    ))

    fig.update_layout(
        **_LAYOUT,
        height=400,
        title={"text": "ETF Basket Correlation Heatmap — 1-Year Daily Returns", "x": 0.02},
        xaxis={"gridcolor": T.BORDER},
        yaxis={"gridcolor": T.BORDER, "autorange": "reversed"},
    )
    return fig


# ── Chart 3: P&L Attribution Stacked Bar ─────────────────────────────────────

def _pnl_attribution_chart() -> go.Figure:
    rng = np.random.default_rng(55)
    n_trades = 12
    trade_labels = [f"T{i+1}" for i in range(n_trades)]

    # Two legs per trade: long basket leg and short XLF leg
    long_pnl  = rng.uniform(-400, 800, n_trades)
    short_pnl = rng.uniform(-500, 600, n_trades)
    total_pnl = long_pnl + short_pnl

    colors_long  = [T.SUCCESS if v > 0 else T.DANGER for v in long_pnl]
    colors_short = [T.ACCENT  if v > 0 else T.WARNING for v in short_pnl]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name="Long Basket Leg P&L",
        x=trade_labels, y=long_pnl,
        marker_color=colors_long, marker_line_width=0,
    ))
    fig.add_trace(go.Bar(
        name="Short XLF Leg P&L",
        x=trade_labels, y=short_pnl,
        marker_color=colors_short, marker_line_width=0,
    ))

    # Total line
    fig.add_trace(go.Scatter(
        x=trade_labels, y=total_pnl, mode="markers+lines",
        name="Net P&L", marker={"color": T.TEXT_PRIMARY, "size": 8, "symbol": "diamond"},
        line={"color": T.TEXT_PRIMARY, "width": 2, "dash": "dot"},
    ))

    fig.add_hline(y=0, line_color="#475569", opacity=0.5)

    cumsum = np.cumsum(total_pnl)
    fig.add_annotation(
        x=trade_labels[-1], y=total_pnl[-1] + 50,
        text=f"Cumulative: ${cumsum[-1]:+,.0f}",
        showarrow=False, font={"color": T.SUCCESS if cumsum[-1] > 0 else T.DANGER, "size": 12},
    )

    fig.update_layout(
        **_LAYOUT,
        height=380,
        barmode="relative",
        title={"text": "P&L Attribution — 12 Stat Arb Trades (Long Basket vs Short XLF)", "x": 0.02},
        xaxis={"title": "Trade", "gridcolor": T.BORDER},
        yaxis={"title": "P&L ($)", "gridcolor": T.BORDER},
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
            "Basket Spread Z-Score — XLF vs Sector Basket",
            _basket_zscore_chart(),
            "The z-score of the XLF/basket spread follows a mean-reverting process. "
            "Entries at ±2σ have historically provided edge with typical reversion in 3-8 days. "
            "The exit threshold of ±0.3σ captures most of the move while avoiding overstaying.",
        ),
        _card(
            "ETF Basket Correlation Heatmap",
            _correlation_heatmap(),
            "High within-sector correlations confirm the arbitrage premise. XLE (energy) is the least correlated member "
            "— divergences from the basket are more persistent. XLK and QQQ are near-perfect substitutes (r=0.96), "
            "making them prime candidates for tight spread trading.",
        ),
        _card(
            "P&L Attribution — 12 Trades Across Two Legs",
            _pnl_attribution_chart(),
            "Stacked bars show the contribution of each leg separately. The pairs structure means one leg often loses "
            "while the other gains. The net P&L (diamond markers) shows the true edge. Trades where both legs lose "
            "indicate a structural break — review position sizing and correlation stability.",
        ),
    ], style={"marginTop": "8px"})
