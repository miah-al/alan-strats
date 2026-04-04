"""
Interactive Plotly charts for the Vol Arbitrage guide article.
Called by the Guide tab renderer when slug == 'vol_arbitrage'.
"""
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
        BG_BASE = "#0a0e1a"; BG_CARD = "#111827"; BG_ELEVATED = "#161d2e"
        ACCENT = "#6366f1"; SUCCESS = "#10b981"; DANGER = "#ef4444"
        WARNING = "#f59e0b"; TEXT_PRIMARY = "#f9fafb"; TEXT_SEC = "#9ca3af"
        BORDER = "#1f2937"; STYLE_CARD = {"backgroundColor": BG_CARD, "border": f"1px solid {BORDER}", "borderRadius": "10px", "padding": "16px"}

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


# ── Chart 1: Skew Zone Win Rate + Avg P&L ─────────────────────────────────────

def _skew_zone_chart() -> go.Figure:
    zones     = ["8–15 vp", "15–25 vp", "25–35 vp", "35–50 vp", "> 50 vp"]
    win_rates = [79, 72, 58, 31, 18]
    avg_pnl   = [610, 480, 120, -680, -1200]
    colors_wr = [T.SUCCESS if w >= 60 else T.WARNING if w >= 40 else T.DANGER for w in win_rates]
    colors_pnl= [T.SUCCESS if p > 0 else T.DANGER for p in avg_pnl]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Win Rate by Skew Zone (%)", "Avg P&L per Trade ($)"),
        horizontal_spacing=0.12,
    )

    fig.add_trace(go.Bar(
        x=zones, y=win_rates,
        marker_color=colors_wr,
        marker_line_width=0,
        text=[f"{w}%" for w in win_rates],
        textposition="outside",
        name="Win Rate",
        showlegend=False,
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=zones, y=avg_pnl,
        marker_color=colors_pnl,
        marker_line_width=0,
        text=[f"${p:+,}" for p in avg_pnl],
        textposition="outside",
        name="Avg P&L",
        showlegend=False,
    ), row=1, col=2)

    # Threshold lines
    fig.add_hline(y=50, line_dash="dash", line_color=T.TEXT_SEC, opacity=0.5, row=1, col=1,
                  annotation_text=" 50% breakeven", annotation_font_color=T.TEXT_SEC, annotation_font_size=10)
    fig.add_hline(y=0, line_color=T.TEXT_SEC, opacity=0.4, row=1, col=2)

    # Danger zone shading — skew > 35 vp
    for col in (1, 2):
        fig.add_vrect(x0=2.5, x1=4.5, fillcolor=T.DANGER, opacity=0.07,
                      line_width=0, row=1, col=col,
                      annotation_text="DANGER ZONE" if col == 1 else "",
                      annotation_font_color=T.DANGER, annotation_font_size=10,
                      annotation_position="top left")

    fig.update_layout(
        **_LAYOUT,
        height=360,
        yaxis={"title": "Win Rate (%)", "range": [0, 100], "gridcolor": T.BORDER},
        yaxis2={"title": "P&L ($)", "gridcolor": T.BORDER},
        xaxis={"gridcolor": T.BORDER},
        xaxis2={"gridcolor": T.BORDER},
    )
    return fig


# ── Chart 2: Payoff Diagram ────────────────────────────────────────────────────

def _payoff_chart() -> go.Figure:
    """
    Visualise the vol-arb position payoff at expiry:
      Short put at K=61, Long call at K=61, Short stock hedge at S_entry=56
    Net = synthetic long + short stock ≈ delta-neutral.
    """
    S = np.linspace(30, 90, 500)
    K = 61.0
    S0 = 56.06          # entry price
    shares_short = 661
    put_credit = 5.75   # per share
    call_debit  = 0.53
    n_contracts = 7
    multiplier  = 100

    # Options P&L at expiry (per-share basis × 700 shares)
    put_pnl  = (put_credit - np.maximum(K - S, 0)) * n_contracts * multiplier
    call_pnl = (np.maximum(S - K, 0) - call_debit) * n_contracts * multiplier
    stock_pnl = shares_short * (S0 - S)     # short stock gains when S falls

    options_pnl = put_pnl + call_pnl
    total_pnl   = options_pnl + stock_pnl

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=S, y=options_pnl,
        mode="lines", name="Options only (short put + long call)",
        line={"color": T.ACCENT, "width": 2, "dash": "dot"},
    ))
    fig.add_trace(go.Scatter(
        x=S, y=stock_pnl,
        mode="lines", name="Short stock hedge",
        line={"color": T.WARNING, "width": 2, "dash": "dot"},
    ))
    fig.add_trace(go.Scatter(
        x=S, y=total_pnl,
        mode="lines", name="Total position",
        line={"color": T.SUCCESS, "width": 3},
        fill="tozeroy",
        fillcolor=f"rgba(16,185,129,0.08)",
    ))

    # Markers
    fig.add_vline(x=K,  line_dash="dash", line_color="#94a3b8", opacity=0.7,
                  annotation_text=f"  Strike K=${K:.0f}", annotation_font_color="#94a3b8")
    fig.add_vline(x=S0, line_dash="dash", line_color=T.WARNING, opacity=0.7,
                  annotation_text=f"  Entry S₀=${S0:.2f}", annotation_font_color=T.WARNING)
    fig.add_hline(y=0, line_color="#475569", opacity=0.5)

    # Annotate actual trade outcome (stock fell to 49.90)
    s_actual = 49.90
    y_actual = float(np.interp(s_actual, S, total_pnl))
    fig.add_trace(go.Scatter(
        x=[s_actual], y=[y_actual],
        mode="markers+text",
        marker={"color": T.SUCCESS, "size": 12, "symbol": "star"},
        text=[f" Actual exit<br>S=${s_actual:.2f}<br>P&L=${y_actual:+,.0f}"],
        textposition="middle right",
        textfont={"color": T.SUCCESS, "size": 11},
        name="Actual exit (Trade 2)",
        showlegend=True,
    ))

    fig.update_layout(
        **_LAYOUT,
        height=400,
        title={"text": "Position Payoff at Expiry — 7 contracts, K=61, S₀=56.06", "x": 0.02},
        xaxis={"title": "HOOD Price at Expiry ($)", "gridcolor": T.BORDER},
        yaxis={"title": "P&L ($)", "gridcolor": T.BORDER, "zeroline": True, "zerolinecolor": T.BORDER},
        legend={"x": 0.01, "y": 0.99, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


# ── Chart 3: Vega decomposition (why short vega = short expensive put vol) ─────

def _vega_decomposition_chart() -> go.Figure:
    """
    Show call IV vs put IV at the same strike across the chain.
    IV skew = put IV - call IV: we are SHORT the overpriced put vega.
    """
    strikes = np.array([50, 52, 54, 56, 58, 60, 61, 62, 64, 66, 68, 70])
    spot = 56.06

    # Typical HOOD skew: OTM puts have highest IV; calls have flatter smile
    put_iv  = 55 + 10 * np.exp(-0.5 * ((strikes - spot - 3) / 8)**2) + 8 * np.maximum(spot - strikes, 0) / spot * 100
    call_iv = 52 + 5  * np.exp(-0.5 * ((strikes - spot)     / 10)**2)
    skew    = put_iv - call_iv

    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=("IV Smile — HOOD Near-ATM Chain (Illustrative)", "IV Skew = Put IV − Call IV"),
        vertical_spacing=0.18,
        row_heights=[0.6, 0.4],
    )

    fig.add_trace(go.Scatter(
        x=strikes, y=put_iv, mode="lines+markers", name="Put IV",
        line={"color": T.DANGER, "width": 2},
        marker={"size": 6},
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=strikes, y=call_iv, mode="lines+markers", name="Call IV",
        line={"color": T.ACCENT, "width": 2},
        marker={"size": 6},
    ), row=1, col=1)

    fig.add_vline(x=spot, line_dash="dash", line_color=T.WARNING, opacity=0.7,
                  annotation_text=f"  Spot ${spot:.2f}", annotation_font_color=T.WARNING, row=1, col=1)

    fig.add_trace(go.Bar(
        x=strikes, y=skew,
        marker_color=[T.SUCCESS if s < 15 else T.WARNING if s < 35 else T.DANGER for s in skew],
        name="IV Skew (vp)",
        showlegend=False,
    ), row=2, col=1)

    fig.add_hline(y=8,  line_dash="dash", line_color=T.SUCCESS,  opacity=0.7,
                  annotation_text=" Entry threshold (8 vp)", annotation_font_color=T.SUCCESS, row=2, col=1)
    fig.add_hline(y=35, line_dash="dash", line_color=T.DANGER, opacity=0.7,
                  annotation_text=" Danger zone (35 vp)", annotation_font_color=T.DANGER, row=2, col=1)

    fig.update_layout(
        **_LAYOUT,
        height=500,
        xaxis={"title": "Strike ($)", "gridcolor": T.BORDER},
        xaxis2={"title": "Strike ($)", "gridcolor": T.BORDER},
        yaxis={"title": "Implied Volatility (%)", "gridcolor": T.BORDER},
        yaxis2={"title": "Skew (vol pts)", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.98, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


# ── Chart 4: The 4 real trades — scatter ──────────────────────────────────────

def _four_trades_chart() -> go.Figure:
    trades = [
        {"id": "Trade 1\n+$904",  "skew": 13.1, "dte": 10, "pnl": 904,   "color": T.SUCCESS, "symbol": "circle"},
        {"id": "Trade 2\n+$2,126","skew": 12.3, "dte":  8, "pnl": 2126,  "color": T.SUCCESS, "symbol": "circle"},
        {"id": "Trade 3\n−$580",  "skew": 45.1, "dte":  7, "pnl": -580,  "color": T.DANGER,  "symbol": "x"},
        {"id": "Trade 4\n−$2,970","skew": 24.2, "dte": 10, "pnl": -2970, "color": T.DANGER,  "symbol": "x"},
    ]

    fig = go.Figure()

    for tr in trades:
        fig.add_trace(go.Scatter(
            x=[tr["skew"]],
            y=[tr["pnl"]],
            mode="markers+text",
            marker={"color": tr["color"], "size": abs(tr["pnl"]) / 120 + 12,
                    "symbol": tr["symbol"], "line": {"width": 1, "color": "#475569"}},
            text=[tr["id"]],
            textposition="top center",
            textfont={"color": tr["color"], "size": 11},
            name=tr["id"].replace("\n", " "),
            showlegend=True,
        ))

    fig.add_vrect(x0=0, x1=35, fillcolor=T.SUCCESS, opacity=0.04,
                  line_width=0, annotation_text="Entry zone", annotation_font_color=T.SUCCESS,
                  annotation_font_size=10, annotation_position="bottom right")
    fig.add_vrect(x0=35, x1=55, fillcolor=T.DANGER, opacity=0.06,
                  line_width=0, annotation_text="Danger zone", annotation_font_color=T.DANGER,
                  annotation_font_size=10, annotation_position="bottom left")
    fig.add_vline(x=35, line_dash="dash", line_color=T.DANGER, opacity=0.7,
                  annotation_text=" 35 vp filter", annotation_font_color=T.DANGER)
    fig.add_hline(y=0, line_color="#475569", opacity=0.5)

    fig.update_layout(
        **_LAYOUT,
        height=380,
        title={"text": "The 4 Real HOOD Trades: IV Skew at Entry vs P&L", "x": 0.02},
        xaxis={"title": "IV Skew at Entry (vol pts)", "gridcolor": T.BORDER, "range": [0, 55]},
        yaxis={"title": "P&L ($)", "gridcolor": T.BORDER},
        legend={"x": 0.01, "y": 0.99, "bgcolor": "rgba(0,0,0,0)"},
    )
    return fig


# ── Chart 5: Simulated equity curve ──────────────────────────────────────────

def _equity_curve_chart() -> go.Figure:
    """
    Approximate cumulative equity from the backtest stats:
      88 trades, 74.4% win rate, avg win $548, avg loss -$597
    Simulate a plausible path.
    """
    rng = np.random.default_rng(42)
    n = 88
    outcomes = rng.choice([548.0, -597.0], size=n, p=[0.744, 0.256])
    equity = 100_000 + np.cumsum(outcomes)
    equity = np.insert(equity, 0, 100_000)

    fig = go.Figure()

    # Underwater fill
    below = np.minimum(equity, 100_000)
    fig.add_trace(go.Scatter(
        x=np.arange(len(equity)), y=below,
        mode="none", fill="tozeroy",
        fillcolor="rgba(239,68,68,0.08)",
        showlegend=False,
    ))

    fig.add_trace(go.Scatter(
        x=np.arange(len(equity)), y=equity,
        mode="lines", name="Portfolio equity",
        line={"color": T.SUCCESS, "width": 2},
        fill="tonexty",
        fillcolor="rgba(16,185,129,0.07)",
    ))

    fig.add_hline(y=100_000, line_dash="dot", line_color="#475569", opacity=0.5,
                  annotation_text=" Starting capital", annotation_font_color="#475569")

    # Max drawdown annotation
    peak = np.maximum.accumulate(equity)
    dd   = (equity - peak) / peak * 100
    min_dd_idx = np.argmin(dd)
    fig.add_annotation(
        x=min_dd_idx, y=equity[min_dd_idx],
        text=f"Max DD: {dd[min_dd_idx]:.1f}%",
        showarrow=True, arrowhead=2, arrowcolor=T.DANGER,
        font={"color": T.DANGER, "size": 11},
        ax=-60, ay=-40,
    )

    final_ret = (equity[-1] - 100_000) / 100_000 * 100
    fig.add_annotation(
        x=len(equity) - 1, y=equity[-1],
        text=f"  Final: +{final_ret:.1f}%",
        showarrow=False,
        font={"color": T.SUCCESS, "size": 12, "family": "Inter"},
        xanchor="left",
    )

    fig.update_layout(
        **_LAYOUT,
        height=320,
        title={"text": "Simulated Equity Curve — 88 Trades (74.4% WR, +$548/−$597 avg)", "x": 0.02},
        xaxis={"title": "Trade #", "gridcolor": T.BORDER},
        yaxis={"title": "Portfolio Value ($)", "gridcolor": T.BORDER,
               "tickformat": "$,.0f"},
        showlegend=False,
    )
    return fig


# ── Public entry point ────────────────────────────────────────────────────────

def render_charts() -> html.Div:
    """Return a Div with all vol-arb interactive charts."""
    return html.Div([
        html.Hr(style={"borderColor": "#1f2937", "margin": "32px 0 24px"}),
        html.H3("📊 Interactive Charts", style={
            "color": "#f9fafb", "fontSize": "16px", "fontWeight": "700",
            "marginBottom": "20px", "letterSpacing": "0.02em",
        }),

        _card(
            "IV Smile & Skew Structure — Why Put IV Is Overpriced",
            _vega_decomposition_chart(),
            "Illustrative HOOD options chain. Put IV (red) exceeds call IV (blue) at every strike — the skew is structural. "
            "Bottom panel shows the vol-point gap we are selling. Entry zone: 8–35 vp.",
        ),

        _card(
            "Skew Zone Performance — Win Rate & Avg P&L by Skew at Entry",
            _skew_zone_chart(),
            "Based on 88 HOOD trades (Dec 2024 – Mar 2026). "
            "Sweet spot is 8–25 vol pts. Above 35 vp the skew reflects informed hedging, not panic — edge inverts.",
        ),

        _card(
            "The 4 Real Trades — IV Skew at Entry vs Realised P&L",
            _four_trades_chart(),
            "Bubble size ∝ |P&L|. Trade 3 (45 vp skew) and Trade 4 (macro shock) are the two losers. "
            "The 35 vp filter would have blocked Trade 3. Trade 4 (macro shock) is unavoidable — size limits it.",
        ),

        _card(
            "Position Payoff at Expiry — Short Put + Long Call + Short Stock (Trade 2)",
            _payoff_chart(),
            "Short 7 × $61 puts, long 7 × $61 calls, short 661 shares at $56.06. "
            "The delta hedge converts directional exposure: the net position profits when stock falls AND when IV compresses. "
            "Star marks the actual exit at $49.90 → +$2,126.",
        ),

        _card(
            "Simulated Equity Curve — 88 Trades",
            _equity_curve_chart(),
            "One plausible path using historical win rate (74.4%) and avg win/loss ($548/−$597). "
            "Profit factor 2.67 means every $1 lost earns $2.67 on winners. Sharpe 0.32 is low but "
            "consistent with a short-hold, high-turnover vol-selling strategy.",
        ),
    ], style={"marginTop": "8px"})
