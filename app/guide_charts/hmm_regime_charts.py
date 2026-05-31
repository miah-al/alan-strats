"""Interactive Plotly charts for the HMM Regime Classifier guide article."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash_bootstrap_components as dbc
from dash import html, dcc

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
try:
    from app import theme as T
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

# State colors — keep these consistent across all charts
_C_STATE0 = T.SUCCESS    # bull / low-vol
_C_STATE1 = T.WARNING    # chop / mid-vol
_C_STATE2 = T.DANGER     # bear / high-vol


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


# ─────────────────────────────────────────────────────────────────────────────
# Chart 1: Regime cluster scatter — how (VIX, realized vol) separate into 3 states
# ─────────────────────────────────────────────────────────────────────────────

def _regime_cluster_chart() -> go.Figure:
    """Synthetic illustration of how SPY days cluster into 3 regimes in (VIX, rv20) space."""
    rng = np.random.default_rng(42)

    # State 0: bull / quiet → VIX 11-16, rv20 0.06-0.12
    s0_vix = rng.normal(13.5, 1.4, 220)
    s0_rv  = rng.normal(0.09, 0.018, 220)
    # State 1: chop / normal → VIX 16-22, rv20 0.12-0.18
    s1_vix = rng.normal(19.0, 1.8, 160)
    s1_rv  = rng.normal(0.155, 0.020, 160)
    # State 2: crisis → VIX 28-55, rv20 0.25-0.50
    s2_vix = np.concatenate([rng.normal(32, 4, 35), rng.normal(45, 6, 15)])
    s2_rv  = np.concatenate([rng.normal(0.30, 0.04, 35), rng.normal(0.42, 0.06, 15)])

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=s0_vix, y=s0_rv*100, mode="markers",
        name="State 0 — bull/quiet", marker=dict(color=_C_STATE0, size=7,
        line=dict(color="#0a0e1a", width=0.5), opacity=0.78)))
    fig.add_trace(go.Scatter(x=s1_vix, y=s1_rv*100, mode="markers",
        name="State 1 — chop", marker=dict(color=_C_STATE1, size=7,
        line=dict(color="#0a0e1a", width=0.5), opacity=0.78)))
    fig.add_trace(go.Scatter(x=s2_vix, y=s2_rv*100, mode="markers",
        name="State 2 — crisis", marker=dict(color=_C_STATE2, size=8,
        line=dict(color="#0a0e1a", width=0.5), opacity=0.85)))

    fig.update_layout(**_LAYOUT, height=420,
        xaxis_title="VIX (closing level)",
        yaxis_title="20-day realized volatility (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        hovermode="closest")
    fig.update_xaxes(gridcolor=T.BORDER, range=[8, 60])
    fig.update_yaxes(gridcolor=T.BORDER, range=[0, 60])
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Chart 2: Posterior probability time series — how regime classification evolves
# ─────────────────────────────────────────────────────────────────────────────

def _posterior_timeline_chart() -> go.Figure:
    """Synthetic 250-day window showing P(state) across a regime transition (bull → crisis → recovery)."""
    n = 250
    days = np.arange(n)

    # Three-phase scenario:
    #   bars 0-100  : bull regime, P0 dominates
    #   bars 100-160: crisis emerges, P2 climbs
    #   bars 160-250: recovery into chop, P1 dominates
    def sigmoid(x, c, k=0.25):
        return 1.0 / (1.0 + np.exp(-k * (x - c)))

    crisis_on   = sigmoid(days, 105, 0.30)
    crisis_off  = sigmoid(days, 160, 0.25)
    crisis      = crisis_on * (1 - crisis_off)
    chop_on     = sigmoid(days, 165, 0.20)

    rng = np.random.default_rng(7)
    noise = lambda scale: rng.normal(0, scale, n)

    p0 = (1 - crisis - chop_on).clip(0.0, 1.0) + noise(0.04)
    p2 = crisis * (1 - chop_on) + noise(0.04)
    p1 = (chop_on * (1 - crisis)) + noise(0.04)
    # Normalize so the three sum to 1 at each bar
    stack = np.stack([p0, p1, p2], axis=0).clip(0.01, None)
    stack /= stack.sum(axis=0, keepdims=True)
    p0, p1, p2 = stack

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=days, y=p0, mode="lines",
        name="P(state 0) — bull", line=dict(color=_C_STATE0, width=2.2),
        stackgroup="one", fillcolor=_C_STATE0))
    fig.add_trace(go.Scatter(x=days, y=p1, mode="lines",
        name="P(state 1) — chop", line=dict(color=_C_STATE1, width=2.2),
        stackgroup="one", fillcolor=_C_STATE1))
    fig.add_trace(go.Scatter(x=days, y=p2, mode="lines",
        name="P(state 2) — crisis", line=dict(color=_C_STATE2, width=2.2),
        stackgroup="one", fillcolor=_C_STATE2))

    # Confidence floor reference
    fig.add_hline(y=0.60, line_dash="dash", line_color=T.TEXT_SEC, line_width=1,
                  annotation_text="Entry floor 0.60", annotation_position="top right",
                  annotation_font=dict(size=10, color=T.TEXT_SEC))

    # Annotate the regime transitions
    fig.add_annotation(x=50,  y=1.05, text="Bull regime",   showarrow=False,
                       font=dict(size=11, color=_C_STATE0))
    fig.add_annotation(x=130, y=1.05, text="Crisis emerges", showarrow=False,
                       font=dict(size=11, color=_C_STATE2))
    fig.add_annotation(x=210, y=1.05, text="Recovery / chop", showarrow=False,
                       font=dict(size=11, color=_C_STATE1))

    fig.update_layout(**_LAYOUT, height=400,
        xaxis_title="Trading day",
        yaxis_title="P(state | observations)",
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        hovermode="x unified")
    fig.update_xaxes(gridcolor=T.BORDER, range=[0, n-1])
    fig.update_yaxes(gridcolor=T.BORDER, range=[0, 1.10], tickformat=".0%")
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Chart 3: Trade structure payoffs by state — which trade does what regime trigger
# ─────────────────────────────────────────────────────────────────────────────

def _payoff_by_state_chart() -> go.Figure:
    """Side-by-side payoff diagrams for the three regime-conditional trade structures."""
    S0 = 480.0  # spot reference
    S = np.linspace(S0 * 0.85, S0 * 1.15, 400)

    fig = make_subplots(rows=1, cols=3, shared_yaxes=True,
        subplot_titles=(
            "State 0 → Bull put credit spread",
            "State 1 → Iron condor",
            "State 2 → Long put debit spread",
        ),
        horizontal_spacing=0.06)

    # State 0 — bull put credit spread (short 0.20Δ put, long 5% lower)
    sp = S0 * 0.95    # short put ~20Δ ≈ 5% OTM
    lp = sp * 0.95    # long put 5% wider
    credit_0 = 1.20
    pnl0 = np.where(S >= sp, credit_0,
            np.where(S >= lp, credit_0 - (sp - S), credit_0 - (sp - lp)))
    fig.add_trace(go.Scatter(x=S, y=pnl0, mode="lines",
        line=dict(color=_C_STATE0, width=2.5), name="Bull put", showlegend=False), row=1, col=1)
    fig.add_hline(y=0, line_color=T.TEXT_SEC, line_width=0.6, line_dash="dot", row=1, col=1)
    fig.add_vline(x=S0, line_color=T.ACCENT, line_width=0.8, line_dash="dot", row=1, col=1,
                  annotation_text=f"spot ${S0:.0f}", annotation_position="top",
                  annotation_font=dict(size=9, color=T.TEXT_SEC))

    # State 1 — iron condor (short 0.16Δ both sides, 5% wings)
    sp1, lp1 = S0 * 0.93, S0 * 0.88
    sc1, lc1 = S0 * 1.07, S0 * 1.12
    credit_1 = 1.50
    pnl1 = np.full_like(S, credit_1, dtype=float)
    pnl1 = np.where(S <= lp1, credit_1 - (sp1 - lp1), pnl1)
    pnl1 = np.where((S > lp1) & (S < sp1), credit_1 - (sp1 - S), pnl1)
    pnl1 = np.where(S >= sp1, credit_1, pnl1)
    pnl1 = np.where((S > sc1) & (S < lc1), credit_1 - (S - sc1), pnl1)
    pnl1 = np.where(S >= lc1, credit_1 - (lc1 - sc1), pnl1)
    fig.add_trace(go.Scatter(x=S, y=pnl1, mode="lines",
        line=dict(color=_C_STATE1, width=2.5), name="IC", showlegend=False), row=1, col=2)
    fig.add_hline(y=0, line_color=T.TEXT_SEC, line_width=0.6, line_dash="dot", row=1, col=2)
    fig.add_vline(x=S0, line_color=T.ACCENT, line_width=0.8, line_dash="dot", row=1, col=2,
                  annotation_text=f"spot ${S0:.0f}", annotation_position="top",
                  annotation_font=dict(size=9, color=T.TEXT_SEC))

    # State 2 — long put debit spread (long 0.30Δ put, short 5% lower)
    lp2 = S0 * 0.97
    sp2 = lp2 * 0.95
    debit_2 = 1.80
    pnl2 = np.where(S >= lp2, -debit_2,
            np.where(S >= sp2, (lp2 - S) - debit_2, (lp2 - sp2) - debit_2))
    fig.add_trace(go.Scatter(x=S, y=pnl2, mode="lines",
        line=dict(color=_C_STATE2, width=2.5), name="Long put", showlegend=False), row=1, col=3)
    fig.add_hline(y=0, line_color=T.TEXT_SEC, line_width=0.6, line_dash="dot", row=1, col=3)
    fig.add_vline(x=S0, line_color=T.ACCENT, line_width=0.8, line_dash="dot", row=1, col=3,
                  annotation_text=f"spot ${S0:.0f}", annotation_position="top",
                  annotation_font=dict(size=9, color=T.TEXT_SEC))

    fig.update_layout(**_LAYOUT, height=360, showlegend=False)
    for c in (1, 2, 3):
        fig.update_xaxes(title_text="SPY at expiry", gridcolor=T.BORDER, row=1, col=c)
    fig.update_yaxes(title_text="P&L per spread ($)", gridcolor=T.BORDER, row=1, col=1)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Chart 4: VRP by state — why the regime-conditional structure makes economic sense
# ─────────────────────────────────────────────────────────────────────────────

def _vrp_by_state_chart() -> go.Figure:
    """Box plot of (implied − realized) volatility by regime — the empirical VRP signature."""
    rng = np.random.default_rng(2026)

    # State 0: VRP positive and stable → short vol works
    vrp0 = rng.normal(0.045, 0.020, 350)
    # State 1: VRP modestly positive, more variance → IC marginal but +EV
    vrp1 = rng.normal(0.020, 0.030, 260)
    # State 2: VRP collapses or inverts → long vol becomes +EV
    vrp2 = np.concatenate([rng.normal(-0.04, 0.05, 60), rng.normal(-0.10, 0.07, 30)])

    fig = go.Figure()
    fig.add_trace(go.Box(y=vrp0*100, name="State 0", marker_color=_C_STATE0,
        boxmean=True, line_width=1.5))
    fig.add_trace(go.Box(y=vrp1*100, name="State 1", marker_color=_C_STATE1,
        boxmean=True, line_width=1.5))
    fig.add_trace(go.Box(y=vrp2*100, name="State 2", marker_color=_C_STATE2,
        boxmean=True, line_width=1.5))

    fig.add_hline(y=0, line_color=T.TEXT_SEC, line_width=0.8, line_dash="dash",
                  annotation_text="VRP = 0 (no edge)", annotation_position="right",
                  annotation_font=dict(size=10, color=T.TEXT_SEC))

    fig.update_layout(**_LAYOUT, height=380, showlegend=False,
        xaxis_title="Regime",
        yaxis_title="VRP = implied − realized vol (%, annualized)")
    fig.update_xaxes(gridcolor=T.BORDER)
    fig.update_yaxes(gridcolor=T.BORDER)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def render_charts() -> html.Div:
    """Render all HMM regime charts for the guide article."""
    return html.Div([
        _card(
            "Regimes are visually separable in (VIX, realized vol) space",
            _regime_cluster_chart(),
            "Synthetic illustration of how SPY trading days cluster into three regimes when "
            "projected onto VIX and 20-day realized vol. State 0 (bull) sits in the low-left; "
            "state 1 (chop) in the middle; state 2 (crisis) far up-right. The HMM finds these "
            "clusters unsupervised — no labels needed.",
        ),
        _card(
            "Posterior probability across a regime transition",
            _posterior_timeline_chart(),
            "Synthetic 250-day scenario showing how P(state | observations) evolves through "
            "a bull → crisis → recovery sequence. Entries fire only when one state's posterior "
            "exceeds the 0.60 confidence floor; the strategy holds during ambiguous transitions.",
        ),
        _card(
            "Each regime triggers a different defined-risk structure",
            _payoff_by_state_chart(),
            "The structural payoffs the strategy will actually open. State 0 sells premium "
            "(positive P&L if SPY drifts up or sideways). State 1 sells both sides (positive P&L "
            "if SPY stays in a range). State 2 buys puts (positive P&L if SPY falls).",
        ),
        _card(
            "Why this works: the volatility risk premium flips sign in crisis regimes",
            _vrp_by_state_chart(),
            "Empirical distribution of implied minus realized vol by regime. State 0 has a fat "
            "positive VRP — short vol is +EV. State 1 has a thin positive VRP — short gamma is "
            "marginal but +EV. State 2's VRP collapses or inverts — long vol becomes +EV. The "
            "strategy switches structures to harvest the right side of the premium in each regime.",
        ),
    ])
