"""
app/pages/market/guides.py - static illustrative guide builders.

Pure synthetic figures + explanatory copy; no API calls. These power the
collapsible guide panels (GEX, vol surface, momentum, yield curve).
Split verbatim from the original market.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import html, dcc

from app import theme as T


def _gex_guide() -> html.Div:
    """Static illustrative section — no API calls, pure synthetic examples."""

    _bg  = "#111827"
    _grd = "#1f2937"
    _fnt = dict(family="Inter, sans-serif", color="#9ca3af", size=10)
    _cfg = {"displayModeBar": False, "responsive": True}

    def _base_layout(title, height=300):
        return dict(
            paper_bgcolor=_bg, plot_bgcolor=_bg, font=_fnt,
            height=height, barmode="overlay",
            title=dict(text=title, font=dict(size=12, color="#d1d5db"), x=0),
            xaxis=dict(tickprefix="$", gridcolor=_grd, color="#9ca3af"),
            yaxis=dict(title="GEX ($B)", gridcolor=_grd, zeroline=False, color="#9ca3af"),
            legend=dict(orientation="h", x=0, y=1.12, font=dict(size=10),
                        bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=50, r=20, t=55, b=30),
        )

    def _bars_and_levels(strikes, calls, puts, spot, zero_g, g1, g2,
                         sig_hi=None, sig_lo=None):
        nets = [c + p for c, p in zip(calls, puts)]
        y_rng = max(max(calls), abs(min(puts))) * 1.4
        fig = go.Figure()
        # dealer cluster shading
        if g1 is not None and sig_hi is not None:
            fig.add_hrect(y0=-y_rng, y1=y_rng,
                          x0=min(g1, sig_hi), x1=max(g1, sig_hi),
                          fillcolor="rgba(239,68,68,0.08)", line_width=0)
        if g2 is not None and sig_lo is not None:
            fig.add_hrect(y0=-y_rng, y1=y_rng,
                          x0=min(g2, sig_lo), x1=max(g2, sig_lo),
                          fillcolor="rgba(16,185,129,0.08)", line_width=0)
        fig.add_trace(go.Bar(x=strikes, y=calls, name="Call GEX",
                             marker_color=T.SUCCESS, opacity=0.8,
                             hovertemplate="$%{x}  Call: %{y:.1f}B<extra></extra>"))
        fig.add_trace(go.Bar(x=strikes, y=puts, name="Put GEX",
                             marker_color=T.DANGER, opacity=0.8,
                             hovertemplate="$%{x}  Put: %{y:.1f}B<extra></extra>"))
        fig.add_trace(go.Bar(x=strikes, y=nets, name="Net GEX",
                             marker_color=[T.ACCENT if v >= 0 else "#7c3aed" for v in nets],
                             opacity=0.5,
                             hovertemplate="$%{x}  Net: %{y:.1f}B<extra></extra>"))
        fig.add_vline(x=spot,   line=dict(color="#fbbf24", width=1.5, dash="dash"),
                      annotation_text=f"Spot ${spot}", annotation_font_color="#fbbf24",
                      annotation_font_size=10, annotation_position="top right")
        if zero_g:
            fig.add_vline(x=zero_g, line=dict(color="#fb923c", width=1.2, dash="dot"),
                          annotation_text=f"ZERO G ${zero_g}",
                          annotation_font_color="#fb923c", annotation_font_size=10,
                          annotation_position="bottom left")
        if g1:
            fig.add_vline(x=g1, line=dict(color="#ef4444", width=1.2, dash="dot"),
                          annotation_text=f"G1 ${g1}",
                          annotation_font_color="#ef4444", annotation_font_size=10,
                          annotation_position="top left")
        if g2:
            fig.add_vline(x=g2, line=dict(color="#10b981", width=1.2, dash="dot"),
                          annotation_text=f"G2 ${g2}",
                          annotation_font_color="#10b981", annotation_font_size=10,
                          annotation_position="bottom left")
        if sig_hi:
            fig.add_vline(x=sig_hi, line=dict(color="#8b5cf6", width=1, dash="dot"),
                          annotation_text=f"σ ${sig_hi}",
                          annotation_font_color="#8b5cf6", annotation_font_size=10,
                          annotation_position="top right")
        if sig_lo:
            fig.add_vline(x=sig_lo, line=dict(color="#8b5cf6", width=1, dash="dot"),
                          annotation_text=f"σ ${sig_lo}",
                          annotation_font_color="#8b5cf6", annotation_font_size=10,
                          annotation_position="bottom right")
        fig.add_hline(y=0, line=dict(color="#374151", width=1))
        return fig

    # ── Scenario 1: Positive GEX, spot between G2 and G1 — pinning ────────────
    st1 = list(range(520, 591, 5))
    c1  = [max(0, 40 * np.exp(-((s - 565)**2) / 180)) for s in st1]
    p1  = [-max(0, 12 * np.exp(-((s - 535)**2) / 250)) for s in st1]
    fig1 = _bars_and_levels(st1, c1, p1, spot=554, zero_g=540, g1=565, g2=535,
                             sig_hi=578, sig_lo=522)
    fig1.update_layout(**_base_layout(
        "① Positive GEX — Spot between G2 ($535) and G1 ($565)  ·  ZERO G at $540"))

    # ── Scenario 2: Negative GEX, spot below ZERO G — amplification ────────────
    st2 = list(range(520, 591, 5))
    c2  = [max(0, 6  * np.exp(-((s - 575)**2) / 400)) for s in st2]
    p2  = [-max(0, 20 * np.exp(-((s - 548)**2) / 150)) for s in st2]
    fig2 = _bars_and_levels(st2, c2, p2, spot=552, zero_g=568, g1=575, g2=548,
                             sig_hi=585, sig_lo=530)
    fig2.update_layout(**_base_layout(
        "② Negative GEX — Spot BELOW ZERO G ($568)  ·  Amplification regime"))

    # ── Scenario 3: Spot just crossed ZERO G from below — regime flip ──────────
    st3 = list(range(520, 591, 5))
    c3  = [max(0, 15 * np.exp(-((s - 568)**2) / 280)) for s in st3]
    p3  = [-max(0, 10 * np.exp(-((s - 553)**2) / 280)) for s in st3]
    fig3 = _bars_and_levels(st3, c3, p3, spot=563, zero_g=560, g1=568, g2=553,
                             sig_hi=580, sig_lo=538)
    fig3.update_layout(**_base_layout(
        "③ Regime Flip — Spot ($563) just crossed above ZERO G ($560)  ·  Entry window"))

    def _rule(title, body, color=T.ACCENT):
        return html.Div([
            html.Span(title, style={"color": color, "fontWeight": "700",
                                    "fontSize": "12px"}),
            html.Span(f"  {body}", style={"color": "#9ca3af", "fontSize": "12px"}),
        ], style={"marginBottom": "6px"})

    pill_style = lambda c: {
        "display": "inline-block", "padding": "2px 10px", "borderRadius": "12px",
        "backgroundColor": c, "color": "#fff", "fontSize": "11px",
        "fontWeight": "600", "marginRight": "6px", "marginBottom": "4px",
    }

    return html.Div([
        # ── Level reference ───────────────────────────────────────────────────
        html.Div([
            html.Div("Key Levels", style={"color": T.TEXT_SEC, "fontSize": "11px",
                                          "fontWeight": "700", "textTransform": "uppercase",
                                          "marginBottom": "10px"}),
            html.Div([
                html.Span("Spot",   style=pill_style("#fbbf24")),
                html.Span("G1 — upper gamma wall", style=pill_style("#ef4444")),
                html.Span("ZERO G — flip point",   style=pill_style("#fb923c")),
                html.Span("G2 — lower gamma wall", style=pill_style("#10b981")),
                html.Span("σ — 1 std dev implied move", style=pill_style("#8b5cf6")),
            ], style={"marginBottom": "10px"}),
            html.Div([
                _rule("G1 (red):", "Strike above spot with highest absolute Net GEX. Mechanical ceiling — dealers sell every rally into it. Use for short call strikes."),
                _rule("ZERO G (orange):", "Where cumulative GEX crosses zero. Above = dampening (sell premium). Below = amplifying (protect positions). The single most important level.", "#fb923c"),
                _rule("G2 (green):", "Strike below spot with highest absolute Net GEX. Mechanical floor — dealers buy every dip into it. Use for short put strikes.", "#10b981"),
                _rule("σ (purple):", "One standard deviation implied move from nearest ATM IV. Beyond σ = dealer positioning thins out, moves can extend freely.", "#8b5cf6"),
                _rule("Dealer Clusters (shaded):", "Red band (G1→σ upper) and green band (G2→σ lower). Dense dealer positioning inside these zones — price moves slowly, tends to revert."),
            ]),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "12px 16px"}),

        # ── OI panel note ─────────────────────────────────────────────────────
        html.Div([
            html.Div("Open Interest Panel (right chart)", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("Green bars (right):", "Call OI per strike. Large call OI wall above spot reinforces G1 as resistance."),
            _rule("Red bars (left):", "Put OI per strike, mirrored. Large put OI near G2 reinforces it as support.", T.DANGER),
            _rule("OI + GEX agreement:", "When G1 aligns with the tallest call OI bar, that level is double-confirmed — highest conviction for short call placement.", T.SUCCESS),
            _rule("Put OI >> Call OI:", "Indicates negative GEX regime. Dealers are short the overall book — amplification risk is elevated.", T.WARNING),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "12px 16px"}),

        # ── Example charts ────────────────────────────────────────────────────
        html.Div("Example Scenarios", style={
            "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "marginBottom": "10px",
        }),

        html.Div([
            dcc.Graph(figure=fig1, config=_cfg),
            html.Div([
                _rule("Regime:", "Dampening. Spot is above ZERO G, trapped between G2 ($535) and G1 ($565). Dealer clusters visible on both sides.", T.SUCCESS),
                _rule("Trade:", "Iron condor: short put at G2 ($535), short call at G1 ($565). Both short legs sit at mechanical walls with dealer backing.", T.SUCCESS),
                _rule("Caution:", "If spot breaks below ZERO G ($540), close the short put side immediately — regime will flip to amplifying.", T.WARNING),
            ], style={"padding": "8px 4px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "14px"}),

        html.Div([
            dcc.Graph(figure=fig2, config=_cfg),
            html.Div([
                _rule("Regime:", "Amplifying. Spot ($552) is below ZERO G ($568). Put GEX dominates. Dealers must sell into any decline.", T.DANGER),
                _rule("Trade:", "Exit all premium-selling positions. Buy long puts or VIX calls. Size all trades at 50% of normal. Tighten stops to 1–1.5× ATR.", T.DANGER),
                _rule("Watch for:", "Net GEX transitioning from −$2B toward zero over 3–5 days. That transition + a spot close above ZERO G = the entry window.", "#fb923c"),
            ], style={"padding": "8px 4px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "14px"}),

        html.Div([
            dcc.Graph(figure=fig3, config=_cfg),
            html.Div([
                _rule("Regime:", "Transitioning. Spot ($563) just crossed above ZERO G ($560). Call and put GEX now roughly balanced. Net GEX turning positive.", "#fb923c"),
                _rule("Trade:", "Wait one full daily close above ZERO G for confirmation. Then enter condors with short call at G1 ($568) and short put at G2 ($553).", T.SUCCESS),
                _rule("Don't jump early:", "An intraday touch above ZERO G without a close is not confirmation. The regime can flip back below on the same session.", T.WARNING),
            ], style={"padding": "8px 4px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "0", "padding": "14px"}),
    ], style={"marginTop": "16px"})


def _vol_surface_guide() -> html.Div:
    """Static illustrative guide for the IV volatility surface."""
    _bg  = "#111827"
    _grd = "#1f2937"
    _fnt = dict(family="Inter, sans-serif", color="#9ca3af", size=10)
    _cfg = {"displayModeBar": False, "responsive": True}

    # IV smile: moneyness 0.80–1.20, three DTE slices
    mon = np.linspace(0.80, 1.20, 31)
    lbl = [f"{int(m*100)}%" for m in mon]
    def _smile(base, skew, wing):
        return [(base + (-skew*(m-1.0)) + wing*(m-1.0)**2*15) * 100 for m in mon]
    iv7d  = _smile(0.35, 0.10, 0.12)
    iv30d = _smile(0.28, 0.07, 0.10)
    iv90d = _smile(0.22, 0.04, 0.08)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=lbl, y=iv7d,  mode="lines", name="7 DTE",
                             line=dict(color="#ef4444", width=2)))
    fig.add_trace(go.Scatter(x=lbl, y=iv30d, mode="lines", name="30 DTE",
                             line=dict(color="#fbbf24", width=2)))
    fig.add_trace(go.Scatter(x=lbl, y=iv90d, mode="lines", name="90 DTE",
                             line=dict(color="#3b82f6", width=2)))
    fig.add_shape(type="line", xref="x", yref="paper",
                  x0="100%", x1="100%", y0=0, y1=1,
                  line=dict(color="#69f0ae", width=1.5, dash="dot"))
    fig.add_annotation(x="100%", y=1, xref="x", yref="paper",
                       text="ATM (green in 3D)", showarrow=False,
                       font=dict(color="#69f0ae", size=10),
                       xanchor="left", yanchor="bottom")
    fig.update_layout(
        paper_bgcolor=_bg, plot_bgcolor=_bg, font=_fnt, height=280,
        title=dict(text="IV Smile — put skew + term structure (synthetic)",
                   font=dict(size=12, color="#d1d5db"), x=0),
        xaxis=dict(title="Strike (% of spot)", gridcolor=_grd, color="#9ca3af"),
        yaxis=dict(title="IV (%)", gridcolor=_grd, color="#9ca3af"),
        legend=dict(orientation="h", x=0, y=1.12, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=50, r=20, t=55, b=40),
    )

    def _rule(title, body, color=T.ACCENT):
        return html.Div([
            html.Span(title, style={"color": color, "fontWeight": "700", "fontSize": "12px"}),
            html.Span(f"  {body}", style={"color": "#9ca3af", "fontSize": "12px"}),
        ], style={"marginBottom": "6px"})

    return html.Div([
        html.Div([
            html.Div("Reading the Axes", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "10px"}),
            _rule("X (Strike $):", "Left = OTM puts (below spot). Right = OTM calls (above spot). Center = ATM."),
            _rule("Y (DTE):", "Days to expiration. Front = near-term. Back = longer-dated.", "#fbbf24"),
            _rule("Z (IV %):", "Implied volatility. Higher = options market pricing larger expected moves.", "#8b5cf6"),
            _rule("Green ATM column:", "The at-the-money strike. Skew and term structure are measured relative to ATM IV.", "#69f0ae"),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "12px 16px"}),

        html.Div([
            dcc.Graph(figure=fig, config=_cfg),
            html.Div([
                _rule("IV Smile:", "IV rises at both wings vs ATM — OTM options price tail risk. Universal pattern."),
                _rule("Put Skew (left wing higher):", "OTM puts more expensive than OTM calls — typical in equities. Reflects demand for downside hedges.", T.DANGER),
                _rule("Inverted term structure (near > far):", "Short-dated IV above long-dated IV. Common near earnings, macro events, or in elevated-vol regimes.", "#ef4444"),
                _rule("Normal term structure (far > near):", "Long-dated IV above short-dated IV. Default state in calm markets — time uncertainty priced at a premium.", "#3b82f6"),
            ], style={"padding": "8px 4px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "14px"}),

        html.Div([
            html.Div("Trade Applications", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("ATM IV = expected move:", "ATM IV × √(DTE/365) × Spot ≈ 1σ implied move. Read the green column.", "#69f0ae"),
            _rule("Elevated skew → put spreads:", "When OTM put IV is abnormally high vs HV, credit put spreads sell the expensive side. The skew shows you which side is overpriced.", T.SUCCESS),
            _rule("Steep term structure → calendars:", "Buy front-month/sell back-month (debit) when near-term IV is depressed. Reverse when inverted (near > far). Surface makes this visible at a glance.", "#fbbf24"),
            _rule("IV trough near ATM → butterflies:", "ATM IV cheapest relative to wings. Long butterfly buys wings, sells ATM — profits if surface flattens or price pins near current level.", T.ACCENT),
        ], style={**T.STYLE_CARD, "padding": "12px 16px"}),
    ], style={"marginTop": "16px"})


def _momentum_guide() -> html.Div:
    """Static illustrative guide for RSI and MACD."""
    _bg  = "#111827"
    _grd = "#1f2937"
    _fnt = dict(family="Inter, sans-serif", color="#9ca3af", size=10)
    _cfg = {"displayModeBar": False, "responsive": True}

    # Synthetic price: uptrend → overbought → pullback → oversold → recovery
    np.random.seed(7)
    n = 90
    segs = np.concatenate([
        np.linspace(100, 128, 35),  # uptrend
        np.linspace(128, 108, 25),  # pullback
        np.linspace(108, 122, 30),  # recovery
    ])
    price = pd.Series(segs + np.random.randn(n) * 1.2)

    delta  = price.diff()
    gain   = delta.clip(lower=0).rolling(14).mean()
    loss   = (-delta.clip(upper=0)).rolling(14).mean()
    rsi    = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    ema12  = price.ewm(span=12).mean()
    ema26  = price.ewm(span=26).mean()
    macd   = ema12 - ema26
    sig    = macd.ewm(span=9).mean()
    hist   = macd - sig

    from plotly.subplots import make_subplots
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.45, 0.28, 0.27], vertical_spacing=0.04,
                        subplot_titles=["Price", "RSI (14)", "MACD"])
    t = list(range(n))
    fig.add_trace(go.Scatter(x=t, y=price, mode="lines",
                             line=dict(color="#6366f1", width=2), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=rsi, mode="lines",
                             line=dict(color="#fbbf24", width=1.5), showlegend=False), row=2, col=1)
    fig.add_hrect(y0=70, y1=100, row=2, col=1, fillcolor="rgba(239,68,68,0.12)", line_width=0)
    fig.add_hrect(y0=0,  y1=30,  row=2, col=1, fillcolor="rgba(16,185,129,0.12)", line_width=0)
    fig.add_hline(y=70, row=2, col=1, line=dict(color="#ef4444", width=1, dash="dot"))
    fig.add_hline(y=30, row=2, col=1, line=dict(color="#10b981", width=1, dash="dot"))
    fig.add_hline(y=50, row=2, col=1, line=dict(color="#374151", width=0.8, dash="dot"))
    fig.add_trace(go.Scatter(x=t, y=macd, mode="lines",
                             line=dict(color="#6366f1", width=1.5), showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=t, y=sig, mode="lines",
                             line=dict(color="#fbbf24", width=1.5), showlegend=False), row=3, col=1)
    hist_colors = ["#10b981" if (v is not None and not np.isnan(v) and v >= 0) else "#ef4444"
                   for v in hist.fillna(0)]
    fig.add_trace(go.Bar(x=t, y=hist.fillna(0),
                         marker_color=hist_colors, opacity=0.6, showlegend=False), row=3, col=1)

    # Annotate first bullish MACD cross
    for i in range(1, len(t)):
        if (not pd.isna(macd.iloc[i-1]) and not pd.isna(sig.iloc[i-1])
                and macd.iloc[i-1] < sig.iloc[i-1] and macd.iloc[i] >= sig.iloc[i]):
            fig.add_annotation(x=i, y=float(macd.iloc[i]), xref="x3", yref="y3",
                               text="Bullish↑", showarrow=True, arrowhead=2,
                               arrowcolor="#10b981", font=dict(color="#10b981", size=9),
                               ax=0, ay=-28)
            break
    # Annotate first bearish MACD cross
    for i in range(1, len(t)):
        if (not pd.isna(macd.iloc[i-1]) and not pd.isna(sig.iloc[i-1])
                and macd.iloc[i-1] > sig.iloc[i-1] and macd.iloc[i] <= sig.iloc[i]):
            fig.add_annotation(x=i, y=float(macd.iloc[i]), xref="x3", yref="y3",
                               text="Bearish↓", showarrow=True, arrowhead=2,
                               arrowcolor="#ef4444", font=dict(color="#ef4444", size=9),
                               ax=0, ay=28)
            break

    for i in range(1, 4):
        fig.update_xaxes(gridcolor=_grd, showticklabels=(i == 3), row=i, col=1)
        fig.update_yaxes(gridcolor=_grd, row=i, col=1)
    fig.update_layout(paper_bgcolor=_bg, plot_bgcolor=_bg, font=_fnt,
                      height=400, margin=dict(l=50, r=20, t=35, b=20), showlegend=False)
    for ann in fig.layout.annotations:
        if ann.text in ("Price", "RSI (14)", "MACD"):
            ann.font = dict(size=11, color="#9ca3af")

    def _rule(title, body, color=T.ACCENT):
        return html.Div([
            html.Span(title, style={"color": color, "fontWeight": "700", "fontSize": "12px"}),
            html.Span(f"  {body}", style={"color": "#9ca3af", "fontSize": "12px"}),
        ], style={"marginBottom": "6px"})

    return html.Div([
        html.Div([dcc.Graph(figure=fig, config=_cfg)],
                 style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "14px"}),
        html.Div([
            html.Div("RSI — Relative Strength Index", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("RSI > 70 (red zone):", "Overbought. Momentum stretched upward — watch for RSI turning down as a warning, not an outright sell trigger.", T.DANGER),
            _rule("RSI < 30 (green zone):", "Oversold. Good time to tighten stops on shorts, watch for bounce setups. Not a standalone buy signal.", T.SUCCESS),
            _rule("RSI 50 centerline:", "Crossing 50 from below = bullish momentum shift. Below 50 = bearish regime. More reliable than overbought/oversold alone."),
            _rule("Divergence:", "Price new high + RSI lower high = bearish divergence (momentum fading). Price new low + RSI higher low = bullish divergence. Precedes reversals.", T.WARNING),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "12px 16px"}),
        html.Div([
            html.Div("MACD — Moving Average Convergence / Divergence", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("MACD line (blue):", "EMA(12) − EMA(26). Captures short-term vs intermediate momentum."),
            _rule("Signal line (yellow):", "EMA(9) of MACD. Cross above = bullish. Cross below = bearish. Confirmed by histogram direction.", "#fbbf24"),
            _rule("Histogram (green/red):", "MACD − Signal. Expanding = momentum building. Shrinking = momentum fading. Watch for bar shrinkage before price turns.", T.SUCCESS),
            _rule("Zero line cross:", "MACD crossing above zero = uptrend confirmed. Below zero = downtrend confirmed. Slower but more reliable than signal-line crosses."),
            _rule("Caveat:", "MACD generates many false signals in choppy, range-bound markets. Combine with RSI and price structure for confirmation.", T.WARNING),
        ], style={**T.STYLE_CARD, "padding": "12px 16px"}),
    ], style={"marginTop": "16px"})


def _yield_guide() -> html.Div:
    """Static illustrative guide for the Treasury yield curve."""
    _bg  = "#111827"
    _grd = "#1f2937"
    _fnt = dict(family="Inter, sans-serif", color="#9ca3af", size=10)
    _cfg = {"displayModeBar": False, "responsive": True}

    mat = ["3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y"]
    normal   = [4.8, 4.7, 4.5, 4.3, 4.2, 4.4, 4.6]
    inverted = [5.3, 5.4, 5.2, 5.0, 4.4, 4.1, 4.3]
    flat_h   = [4.9, 4.9, 4.8, 4.7, 4.6, 4.6, 4.7]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=mat, y=normal, mode="lines+markers",
                             name="Normal (healthy)", line=dict(color="#10b981", width=2),
                             marker=dict(size=7)))
    fig.add_trace(go.Scatter(x=mat, y=inverted, mode="lines+markers",
                             name="Inverted (recession signal)", line=dict(color="#ef4444", width=2),
                             marker=dict(size=7)))
    fig.add_trace(go.Scatter(x=mat, y=flat_h, mode="lines+markers",
                             name="Flat/Humped (transition)", line=dict(color="#fbbf24", width=2),
                             marker=dict(size=7)))
    fig.update_layout(
        paper_bgcolor=_bg, plot_bgcolor=_bg, font=_fnt, height=240,
        title=dict(text="Yield Curve Shapes (synthetic example)",
                   font=dict(size=12, color="#d1d5db"), x=0),
        xaxis=dict(title="Maturity", gridcolor=_grd, color="#9ca3af"),
        yaxis=dict(title="Yield (%)", gridcolor=_grd, color="#9ca3af", tickformat=".1f"),
        legend=dict(orientation="h", x=0, y=1.15, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=50, r=20, t=55, b=40),
    )

    def _rule(title, body, color=T.ACCENT):
        return html.Div([
            html.Span(title, style={"color": color, "fontWeight": "700", "fontSize": "12px"}),
            html.Span(f"  {body}", style={"color": "#9ca3af", "fontSize": "12px"}),
        ], style={"marginBottom": "6px"})

    return html.Div([
        html.Div([dcc.Graph(figure=fig, config=_cfg)],
                 style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "14px"}),
        html.Div([
            html.Div("Curve Shapes", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("Normal (green, upward):", "Long rates higher than short rates. Economy healthy, investors demand yield premium for time risk. Default state.", T.SUCCESS),
            _rule("Inverted (red):", "Short rates above long rates. Most reliable historical recession predictor. 2s10s negative = watch for credit stress 12–18 months out.", T.DANGER),
            _rule("Flat / Humped (yellow):", "Short and long rates converging. Transition state — watch the 2s10s trend to see which way it resolves.", "#fbbf24"),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "12px 16px"}),
        html.Div([
            html.Div("The Key Spreads", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "marginBottom": "8px"}),
            _rule("2s10s (shown in pills):", "10Y minus 2Y. Positive = normal. Goes negative months before recessions. Inversions can last 1–2 years before economic impact."),
            _rule("3m10y:", "Fed's preferred recession indicator. More sensitive to policy rate. First to invert, often first to re-steepen.", "#fbbf24"),
            _rule("Re-steepening from inversion:", "When 2s10s climbs rapidly from deeply negative, it often signals recession is starting — not ending. Counter-intuitive but historically consistent.", T.DANGER),
            _rule("3D Surface:", "Shows how the full curve evolved over 2 years. A 'front-end rise' = Fed tightening. A 'bull steepener' (long end dropping) = market pricing future cuts.", "#3b82f6"),
            _rule("For options traders:", "Steep inverted curve → recession risk elevated → reduce short vol, widen spread widths, avoid iron condors on cyclical sectors.", T.WARNING),
        ], style={**T.STYLE_CARD, "padding": "12px 16px"}),
    ], style={"marginTop": "16px"})
