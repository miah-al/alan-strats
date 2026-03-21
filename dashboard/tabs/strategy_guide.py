"""
Strategy Guide — detailed reference articles for every strategy in the registry.
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# File-based article loader
# ─────────────────────────────────────────────────────────────────────────────

_ARTICLES_DIR = os.path.join(os.path.dirname(__file__), "guide_articles")

@st.cache_data
def _load_article(slug: str) -> str | None:
    path = os.path.join(_ARTICLES_DIR, f"{slug}.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None

# ─────────────────────────────────────────────────────────────────────────────
# Article content  (legacy inline dict — kept as fallback, file-based takes priority)
# ─────────────────────────────────────────────────────────────────────────────

ARTICLES: dict[str, str] = {}  # content now served from guide_articles/ directory


# ─────────────────────────────────────────────────────────────────────────────
# Category groupings for navigation
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIES: dict[str, list[str]] = {
    "🤖 Implemented": ["options_spread", "dividend_arb", "vol_arbitrage"],
    "📉 Systematic Vol Selling": ["wheel_strategy", "0dte_condor", "iv_rank_credit", "vix_futures_roll", "tail_risk_collar"],
    "🌊 VIX Strategies": ["vix_mean_reversion", "vix_term_structure", "vix_spike_fade"],
    "🔗 Pairs Trading": ["pairs_spy_qqq", "pairs_spy_iwm", "pairs_spy_dia"],
    "📈 Momentum": ["momentum_cross_sector", "momentum_12_1", "momentum_risk_on_off"],
    "🏗️ Options Structures": ["iron_condor_weekly", "calendar_spread_vix", "butterfly_atm"],
    "📣 Earnings": ["earnings_vol_crush", "earnings_straddle", "earnings_pin_risk", "earnings_drift"],
    "🌍 Macro": ["macro_yield_curve", "macro_fed_cycle", "macro_inflation_regime"],
    "⚙️ Statistical Arb": ["stat_arb_etf_basket", "stat_arb_sector_rotation", "stat_arb_index_recon"],
    "🔬 ML Variants": ["ml_gradient_boost", "ml_transformer_seq", "ml_ensemble_stacking"],
    "🛡️ Tail Risk / Hedges": ["tail_risk_long_put", "tail_risk_put_spread"],
    "🌐 Cross-Asset": ["crypto_corr_spy", "commodities_oil_spy"],
    "⚡ Intraday": ["opening_range_breakout", "vwap_reversion", "gap_fade"],
    "📅 Event-Driven": ["fomc_event_straddle", "expiry_max_pain", "turn_of_month"],
    "🌊 Alt Data / Flow": ["options_flow_scanner", "news_sentiment_nlp", "gex_positioning", "short_squeeze_detector"],
    "📐 Technical": ["trend_ma_crossover", "bollinger_squeeze", "rsi_mean_reversion"],
    "🔮 Regime ML": ["regime_hmm", "reinforcement_agent", "neural_regime_transformer", "online_adaptive_model"],
    "⚖️ Portfolio Construction": ["risk_parity_alloc", "min_variance_hedge"],
    "🏦 Fixed Income Signals": ["rates_spy_rotation", "rates_spy_rotation_options", "credit_spread_signal"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Payoff / concept charts
# ─────────────────────────────────────────────────────────────────────────────

def _dark_layout(title: str = "", height: int = 280) -> dict:
    return dict(
        title=dict(text=title, font=dict(color="#e0e0e0", size=13)),
        paper_bgcolor="#0e1117", plot_bgcolor="#161b27",
        font=dict(color="#b0b8c8", size=11),
        margin=dict(l=44, r=16, t=36, b=44),
        height=height,
        xaxis=dict(gridcolor="#2a2f3f", showgrid=True),
        yaxis=dict(gridcolor="#2a2f3f", showgrid=True,
                   zeroline=True, zerolinecolor="#5c6bc0", zerolinewidth=1),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        showlegend=True,
    )


@st.cache_data(show_spinner=False)
def _payoff_chart(slug: str):
    """Return a plotly Figure for the given strategy, or None if not applicable."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None

    S = np.linspace(80, 120, 500)   # normalised underlying, ATM = 100

    # ── helper ────────────────────────────────────────────────────────────────
    def fig1(y, name, color="#26a69a", title="Payoff at Expiry",
             be_x=None, annotations=None):
        f = go.Figure()
        f.add_trace(go.Scatter(
            x=S, y=y, mode="lines", name=name,
            line=dict(color=color, width=2.5),
            fill="tozeroy",
            fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08)",
        ))
        if be_x is not None:
            for bx in (be_x if hasattr(be_x, "__iter__") else [be_x]):
                f.add_vline(x=bx, line_dash="dash", line_color="#ffb300", line_width=1,
                            annotation_text=f"BE {bx:.1f}", annotation_font_size=9,
                            annotation_font_color="#ffb300")
        f.add_hline(y=0, line_color="#444", line_width=1)
        f.update_layout(
            xaxis_title="Underlying price at expiry",
            yaxis_title="P&L per contract ($)",
            **_dark_layout(title),
        )
        return f

    # ── per-slug dispatch ──────────────────────────────────────────────────────

    # ── Bull call spread ───────────────────────────────────────────────────────
    if slug in ("options_spread", "bull_call_spread"):
        K1, K2, debit = 95, 105, 3.5
        y = np.where(S <= K1, -debit,
            np.where(S <= K2, S - K1 - debit, K2 - K1 - debit))
        return fig1(y, "Bull Call Spread", "#26a69a",
                    "Bull Call Spread — payoff at expiry", be_x=K1+debit)

    # ── Bear put spread ────────────────────────────────────────────────────────
    if slug == "bear_put_spread":
        K1, K2, debit = 95, 105, 3.5
        y = np.where(S >= K2, -debit,
            np.where(S >= K1, K2 - S - debit, K2 - K1 - debit))
        return fig1(y, "Bear Put Spread", "#ef5350",
                    "Bear Put Spread — payoff at expiry", be_x=K2-debit)

    # ── Bull put spread (credit) ───────────────────────────────────────────────
    if slug == "bull_put_spread":
        K1, K2, credit = 93, 100, 2.5
        y = np.where(S >= K2, credit,
            np.where(S >= K1, S - K2 + credit, K1 - K2 + credit))
        return fig1(y, "Bull Put Spread (credit)", "#66bb6a",
                    "Bull Put Spread — payoff at expiry", be_x=K2-credit)

    # ── Bear call spread (credit) ──────────────────────────────────────────────
    if slug == "bear_call_spread":
        K1, K2, credit = 100, 107, 2.5
        y = np.where(S <= K1, credit,
            np.where(S <= K2, K1 - S + credit, K1 - K2 + credit))
        return fig1(y, "Bear Call Spread (credit)", "#ab47bc",
                    "Bear Call Spread — payoff at expiry", be_x=K1+credit)

    # ── Iron condor ────────────────────────────────────────────────────────────
    if slug in ("iron_condor", "0dte_condor", "iv_rank_credit"):
        # short 95/90 put spread + short 105/110 call spread; net credit 4
        Kpp, Kps, Kcs, Kcp, credit = 90, 95, 105, 110, 4.0
        put_leg  = np.where(S >= Kps, 0,
                   np.where(S >= Kpp, S - Kps, Kpp - Kps))
        call_leg = np.where(S <= Kcs, 0,
                   np.where(S <= Kcp, S - Kcs, Kcp - Kcs))
        y = credit + put_leg + call_leg  # put/call legs are negative when breached
        return fig1(y, "Iron Condor", "#ffb300",
                    "Iron Condor — payoff at expiry",
                    be_x=[Kps-credit/2, Kcs+credit/2])

    # ── Long straddle ──────────────────────────────────────────────────────────
    if slug == "long_straddle":
        K, debit = 100, 8.0
        y = np.abs(S - K) - debit
        return fig1(y, "Long Straddle", "#29b6f6",
                    "Long Straddle — payoff at expiry",
                    be_x=[K-debit, K+debit])

    # ── Short strangle ─────────────────────────────────────────────────────────
    if slug in ("short_strangle", "wheel_strategy"):
        Kp, Kc, credit = 93, 107, 5.0
        y = np.where(S <= Kp, S - Kp + credit,
            np.where(S >= Kc, Kc - S + credit, credit))
        return fig1(y, "Short Strangle", "#ff7043",
                    "Short Strangle — payoff at expiry",
                    be_x=[Kp-credit, Kc+credit])

    # ── Butterfly ─────────────────────────────────────────────────────────────
    if slug in ("butterfly_spread", "broken_wing_butterfly"):
        K1, K2, K3, debit = 90, 100, 110, 2.5
        y = (np.maximum(S-K1,0) - 2*np.maximum(S-K2,0) + np.maximum(S-K3,0)) - debit
        return fig1(y, "Long Call Butterfly", "#ce93d8",
                    "Butterfly Spread — payoff at expiry",
                    be_x=[K1+debit, K3-debit])

    # ── Calendar spread ────────────────────────────────────────────────────────
    if slug == "calendar_spread":
        import plotly.graph_objects as go
        days = np.linspace(0, 45, 200)
        # theta: short leg decays faster near expiry
        def theta(days_left, vega=2.0):
            return vega * np.sqrt(days_left / 45) * np.exp(-0.5*((days_left-5)/10)**2)
        short_decay = np.array([theta(d, 2.5) for d in days])
        long_decay  = np.array([theta(d, 1.8) for d in days])
        net = np.cumsum(short_decay - long_decay) * 0.1  # illustrative net theta

        f = go.Figure()
        f.add_trace(go.Scatter(x=days, y=short_decay, name="Short-term theta", line=dict(color="#ef5350", width=2)))
        f.add_trace(go.Scatter(x=days, y=long_decay,  name="Long-term theta",  line=dict(color="#26a69a", width=2)))
        f.update_layout(
            xaxis_title="Days to near-term expiry",
            yaxis_title="Daily theta decay (illustrative)",
            **_dark_layout("Calendar Spread — theta advantage"),
        )
        return f

    # ── VIX mean reversion ─────────────────────────────────────────────────────
    if slug in ("vix_mean_reversion", "vix_futures_roll", "tail_risk_collar"):
        import plotly.graph_objects as go
        np.random.seed(42)
        t = np.arange(252)
        # Simulate VIX-like series: mean-reverting around 18
        vix = [18.0]
        for _ in t[1:]:
            vix.append(max(9, vix[-1] + 1.2*(18-vix[-1])*0.05 + np.random.normal(0, 1.1)))
        vix = np.array(vix)
        signal = np.where(vix > 28, "SELL VOL", np.where(vix < 14, "BUY VOL", ""))

        f = go.Figure()
        f.add_trace(go.Scatter(x=t, y=vix, mode="lines", name="VIX (simulated)",
                               line=dict(color="#b0b8c8", width=1.5)))
        f.add_hline(y=28, line_dash="dot", line_color="#ef5350",
                    annotation_text="Sell volatility", annotation_font_color="#ef5350", annotation_font_size=10)
        f.add_hline(y=14, line_dash="dot", line_color="#26a69a",
                    annotation_text="Buy volatility", annotation_font_color="#26a69a", annotation_font_size=10)
        f.add_hline(y=18, line_dash="dash", line_color="#ffb300", line_width=1,
                    annotation_text="Long-run mean", annotation_font_color="#ffb300", annotation_font_size=10)
        f.update_layout(
            xaxis_title="Trading days (simulated)", yaxis_title="VIX",
            **_dark_layout("VIX Mean Reversion — signal bands"),
        )
        return f

    # ── VWAP reversion ─────────────────────────────────────────────────────────
    if slug in ("vwap_reversion", "opening_range_breakout", "gap_fade"):
        import plotly.graph_objects as go
        np.random.seed(7)
        minutes = np.arange(390)
        price = 100 + np.cumsum(np.random.normal(0, 0.04, 390))
        vwap = pd.Series(price).expanding().mean().values

        f = go.Figure()
        f.add_trace(go.Scatter(x=minutes, y=price, mode="lines", name="Price",
                               line=dict(color="#29b6f6", width=1.5)))
        f.add_trace(go.Scatter(x=minutes, y=vwap, mode="lines", name="VWAP",
                               line=dict(color="#ffb300", width=2, dash="dot")))
        # shade ±0.3% band
        f.add_trace(go.Scatter(x=np.concatenate([minutes, minutes[::-1]]),
                               y=np.concatenate([vwap*1.003, (vwap*0.997)[::-1]]),
                               fill="toself", fillcolor="rgba(255,179,0,0.07)",
                               line=dict(width=0), name="±0.3% band", showlegend=True))
        f.update_layout(
            xaxis_title="Minutes from open", yaxis_title="Price",
            **_dark_layout("VWAP Reversion — intraday signal"),
        )
        return f

    # ── RSI mean reversion / Bollinger ────────────────────────────────────────
    if slug in ("rsi_mean_reversion", "bollinger_squeeze", "trend_ma_crossover"):
        import plotly.graph_objects as go
        np.random.seed(3)
        t = np.arange(120)
        price = 100 + np.cumsum(np.random.normal(0.02, 0.8, 120))
        roll_mean = pd.Series(price).rolling(20).mean().values
        roll_std  = pd.Series(price).rolling(20).std().values
        upper = roll_mean + 2*roll_std
        lower = roll_mean - 2*roll_std

        f = go.Figure()
        f.add_trace(go.Scatter(
            x=np.concatenate([t, t[::-1]]), y=np.concatenate([upper, lower[::-1]]),
            fill="toself", fillcolor="rgba(92,107,192,0.12)", line=dict(width=0), name="Bollinger Bands"))
        f.add_trace(go.Scatter(x=t, y=price, mode="lines", name="Price",
                               line=dict(color="#b0b8c8", width=1.5)))
        f.add_trace(go.Scatter(x=t, y=roll_mean, mode="lines", name="20-day SMA",
                               line=dict(color="#ffb300", width=1.5, dash="dot")))
        f.update_layout(
            xaxis_title="Days", yaxis_title="Price",
            **_dark_layout("Bollinger Bands — squeeze & breakout"),
        )
        return f

    # ── Regime HMM ────────────────────────────────────────────────────────────
    if slug in ("regime_hmm", "reinforcement_agent", "neural_regime_transformer"):
        import plotly.graph_objects as go
        np.random.seed(99)
        t = np.arange(252)
        regimes = np.zeros(252, dtype=int)
        # Create block regime labels: 0=bull, 1=neutral, 2=bear
        regimes[60:100]  = 2   # bear
        regimes[100:130] = 1   # neutral
        regimes[160:195] = 1   # neutral
        regimes[195:230] = 2   # bear
        # Build price consistent with regimes
        drifts = {0: 0.06, 1: 0.02, 2: -0.08}
        vols   = {0: 0.01, 1: 0.012, 2: 0.018}
        price = [100.0]
        for i in t[1:]:
            r = regimes[i]
            price.append(price[-1] * np.exp(np.random.normal(drifts[r]/252, vols[r])))
        price = np.array(price)

        regime_info = {0: ("#26a69a", "Bull"), 1: ("#ffb300", "Neutral"), 2: ("#ef5350", "Bear")}
        price_min, price_max = price.min() * 0.98, price.max() * 1.02
        f = go.Figure()
        # Shade regimes as filled band traces (one per regime, avoids 251 vrect calls)
        for r, (color, label) in regime_info.items():
            mask = (regimes == r)
            x_fill = np.concatenate([t[mask], t[mask][::-1]])
            y_fill = np.concatenate([np.full(mask.sum(), price_max),
                                     np.full(mask.sum(), price_min)])
            f.add_trace(go.Scatter(
                x=x_fill, y=y_fill, fill="toself",
                fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.12)",
                line=dict(width=0), name=label, showlegend=True,
            ))
        f.add_trace(go.Scatter(x=t, y=price, mode="lines", name="Price",
                               line=dict(color="#b0b8c8", width=1.5)))
        f.update_layout(
            xaxis_title="Trading days (simulated)", yaxis_title="Price",
            **_dark_layout("HMM Regime Classification — bull / neutral / bear"),
        )
        return f

    # ── Earnings drift ────────────────────────────────────────────────────────
    if slug in ("earnings_drift", "fomc_event_straddle", "turn_of_month"):
        import plotly.graph_objects as go
        np.random.seed(21)
        # Average cumulative return around earnings: −5d to +10d
        days = np.arange(-5, 11)
        # Illustrative: strong post-earnings drift upward on beat
        beat = np.array([-0.2,-0.1, 0.0, 0.1, 0.3, 1.8, 2.5, 3.0, 3.3, 3.5, 3.6, 3.7, 3.8, 4.0, 4.1, 4.2])
        miss = np.array([ 0.1, 0.0, 0.1, 0.0,-0.2,-2.5,-3.2,-3.8,-4.0,-4.1,-4.0,-3.9,-3.7,-3.5,-3.4,-3.2])

        f = go.Figure()
        f.add_trace(go.Scatter(x=days, y=beat, mode="lines+markers", name="Earnings beat",
                               line=dict(color="#26a69a", width=2)))
        f.add_trace(go.Scatter(x=days, y=miss, mode="lines+markers", name="Earnings miss",
                               line=dict(color="#ef5350", width=2)))
        f.add_vline(x=0, line_dash="dash", line_color="#ffb300",
                    annotation_text="Earnings", annotation_font_color="#ffb300", annotation_font_size=10)
        f.update_layout(
            xaxis_title="Days relative to earnings", yaxis_title="Avg cumulative return (%)",
            **_dark_layout("Post-Earnings Drift — beat vs miss"),
        )
        return f

    # ── Risk parity ────────────────────────────────────────────────────────────
    if slug in ("risk_parity_alloc", "min_variance_hedge"):
        import plotly.graph_objects as go
        assets = ["SPY", "TLT", "GLD", "VNQ", "HYG"]
        # Illustrative: equal risk contribution weights
        risk_parity  = [0.22, 0.38, 0.18, 0.12, 0.10]
        mkt_cap      = [0.50, 0.20, 0.10, 0.10, 0.10]
        colors_rp    = ["#26a69a","#29b6f6","#ffb300","#ce93d8","#ff7043"]

        f = go.Figure()
        f.add_trace(go.Bar(name="Risk Parity", x=assets, y=risk_parity,
                           marker_color=colors_rp, opacity=0.9))
        f.add_trace(go.Bar(name="Market Cap Weight", x=assets, y=mkt_cap,
                           marker_color="#78909c", opacity=0.5))
        f.update_layout(
            barmode="group", xaxis_title="Asset", yaxis_title="Weight",
            **_dark_layout("Risk Parity vs Market-Cap Weights"),
        )
        return f

    # ── Options flow scanner ───────────────────────────────────────────────────
    if slug in ("options_flow_scanner", "gex_positioning", "short_squeeze_detector"):
        import plotly.graph_objects as go
        np.random.seed(5)
        strikes = np.arange(480, 521, 5)
        call_oi = np.random.randint(5000, 40000, len(strikes))
        put_oi  = np.random.randint(5000, 30000, len(strikes))
        # Spike at key strikes
        call_oi[4] = 85000
        put_oi[2]  = 60000

        f = go.Figure()
        f.add_trace(go.Bar(x=strikes, y=call_oi, name="Call OI", marker_color="#26a69a", opacity=0.8))
        f.add_trace(go.Bar(x=strikes, y=-put_oi, name="Put OI",  marker_color="#ef5350", opacity=0.8))
        f.add_hline(y=0, line_color="#444", line_width=1)
        f.update_layout(
            barmode="overlay", xaxis_title="Strike", yaxis_title="Open Interest",
            **_dark_layout("Options Open Interest by Strike (illustrative)"),
        )
        return f

    # ── Rates / fixed income ───────────────────────────────────────────────────
    if slug in ("rates_spy_rotation", "rates_spy_rotation_options", "credit_spread_signal"):
        import plotly.graph_objects as go
        np.random.seed(8)
        t = np.arange(252)
        rate10y = 3.5 + np.cumsum(np.random.normal(0, 0.02, 252))
        spy_ret = -0.4 * (rate10y - rate10y[0]) + np.cumsum(np.random.normal(0.03/252, 0.01, 252))

        f = go.Figure()
        ax2_color = "#ef5350"
        f.add_trace(go.Scatter(x=t, y=spy_ret*100, mode="lines", name="SPY cumulative return (%)",
                               line=dict(color="#26a69a", width=1.5)))
        f.add_trace(go.Scatter(x=t, y=rate10y, mode="lines", name="10Y yield",
                               line=dict(color="#ef5350", width=1.5, dash="dot"),
                               yaxis="y2"))
        base = _dark_layout("Rates-SPY Rotation — yield vs equity return")
        base.pop("yaxis", None)
        f.update_layout(
            xaxis_title="Trading days",
            yaxis=dict(title="SPY cum. return (%)", gridcolor="#2a2f3f", color="#26a69a",
                       zeroline=True, zerolinecolor="#5c6bc0", zerolinewidth=1),
            yaxis2=dict(title="10Y Yield (%)", overlaying="y", side="right",
                        color="#ef5350", gridcolor="#2a2f3f"),
            **base,
        )
        return f

    # ── Momentum ───────────────────────────────────────────────────────────────
    if slug in ("momentum_factor", "trend_ma_crossover"):
        import plotly.graph_objects as go
        np.random.seed(11)
        t = np.arange(200)
        price = 100 * np.cumprod(1 + np.random.normal(0.0003, 0.01, 200))
        ma50  = pd.Series(price).rolling(50).mean().values
        ma20  = pd.Series(price).rolling(20).mean().values

        # Crossover signals
        cross_up   = np.where((ma20[1:] > ma50[1:]) & (ma20[:-1] <= ma50[:-1]))[0] + 1
        cross_down = np.where((ma20[1:] < ma50[1:]) & (ma20[:-1] >= ma50[:-1]))[0] + 1

        f = go.Figure()
        f.add_trace(go.Scatter(x=t, y=price, mode="lines", name="Price",
                               line=dict(color="#b0b8c8", width=1.5)))
        f.add_trace(go.Scatter(x=t, y=ma20, mode="lines", name="MA-20",
                               line=dict(color="#29b6f6", width=1.5, dash="dot")))
        f.add_trace(go.Scatter(x=t, y=ma50, mode="lines", name="MA-50",
                               line=dict(color="#ffb300", width=1.5, dash="dash")))
        f.add_trace(go.Scatter(x=t[cross_up], y=price[cross_up], mode="markers",
                               name="Buy signal", marker=dict(symbol="triangle-up", size=10, color="#26a69a")))
        f.add_trace(go.Scatter(x=t[cross_down], y=price[cross_down], mode="markers",
                               name="Sell signal", marker=dict(symbol="triangle-down", size=10, color="#ef5350")))
        f.update_layout(
            xaxis_title="Days", yaxis_title="Price",
            **_dark_layout("MA Crossover — buy/sell signals"),
        )
        return f

    return None


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

_GUIDE_CSS = """
<style>
/* ── Strategy card grid ─────────────────────────────────────────────── */
.sg-card {
  background: #161b27;
  border: 1px solid #2a2f3f;
  border-radius: 10px;
  padding: 16px 18px 14px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  min-height: 140px;
  position: relative;
}
.sg-card:hover { border-color: #5c6bc0; background: #1a2035; }
.sg-card-name  { font-size: 14px; font-weight: 700; color: #e0e0e0; margin-bottom: 6px; }
.sg-card-desc  { font-size: 12px; color: #78909c; margin-bottom: 10px; line-height: 1.4;
                 display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.sg-badges     { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 8px; }
.sg-badge      { font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 20px; }
.sg-badge-ai   { background: rgba(124,106,247,0.18); color: #9c89ff; }
.sg-badge-rule { background: rgba(79,195,247,0.15); color: #4fc3f7; }
.sg-badge-hybrid { background: rgba(255,179,0,0.15); color: #ffb300; }
.sg-badge-live { background: rgba(38,166,154,0.18); color: #26a69a; }
.sg-badge-stub { background: rgba(92,107,192,0.18); color: #7986cb; }
.sg-stats      { font-size: 11px; color: #546e7a; margin-top: 4px; }

/* ── Category pill nav ──────────────────────────────────────────────── */
.sg-cat-pill {
  display: inline-block; padding: 4px 12px; border-radius: 20px;
  background: #1e2130; color: #b0b8c8; font-size: 12px;
  border: 1px solid #2a2f3f; cursor: pointer; margin: 2px;
}
.sg-cat-pill.active { background: #5c6bc0; color: white; border-color: #5c6bc0; }

/* ── Detail view ────────────────────────────────────────────────────── */
.sg-detail-header {
  background: linear-gradient(90deg, #161b27 0%, #1a2035 100%);
  border: 1px solid #2a2f3f; border-radius: 10px;
  padding: 20px 24px; margin-bottom: 20px;
}
.sg-detail-title { font-size: 22px; font-weight: 700; color: #e0e0e0; }
.sg-detail-meta  { font-size: 13px; color: #78909c; margin-top: 6px; }
.sg-status-live  { background:#0d1f1a; border-left:3px solid #26a69a;
                   padding:10px 16px; border-radius:6px; margin-top:16px; }
.sg-status-stub  { background:#161b27; border-left:3px solid #5c6bc0;
                   padding:10px 16px; border-radius:6px; margin-top:16px; }

/* ── Search bar ─────────────────────────────────────────────────────── */
div[data-testid="stTextInput"] > div > input {
  background: #1e2130 !important;
  border: 1px solid #2a2f3f !important;
  border-radius: 8px !important;
  color: #e0e0e0 !important;
}
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Main render
# ─────────────────────────────────────────────────────────────────────────────

@st.fragment
def render():
    from alan_trader.strategies.registry import STRATEGY_METADATA

    st.markdown(_GUIDE_CSS, unsafe_allow_html=True)

    # Session state
    if "guide_selected" not in st.session_state:
        st.session_state.guide_selected = None

    selected = st.session_state.guide_selected

    # ── Detail view ───────────────────────────────────────────────────────────
    if selected and selected in STRATEGY_METADATA:
        _render_detail(selected, STRATEGY_METADATA[selected])
        return

    # ── Grid view ─────────────────────────────────────────────────────────────
    # Header
    st.markdown("## 📚 Strategy Guide")
    st.caption("58 strategies · 19 categories · Click any card to read the full article")

    # Search + category filter
    hc1, hc2 = st.columns([3, 2])
    search     = hc1.text_input("Search", placeholder="🔍  Search — e.g. iron condor, VIX, momentum…",
                                 key="guide_search", label_visibility="collapsed").lower().strip()
    all_cats   = ["All"] + list(CATEGORIES.keys())
    cat_filter = hc2.selectbox("Category", all_cats, key="guide_cat", label_visibility="collapsed")

    st.markdown("")

    # Build matched set
    _all_categorised = {s for slugs in CATEGORIES.values() for s in slugs}

    def _matches(slug, meta):
        if cat_filter != "All" and slug not in CATEGORIES.get(cat_filter, []):
            return False
        if search:
            hay = " ".join([slug, meta.get("display_name",""), meta.get("description",""),
                            meta.get("asset_class",""), meta.get("type","")]).lower()
            return search in hay
        return True

    matched = {s: m for s, m in STRATEGY_METADATA.items() if _matches(s, m)}

    if not matched:
        st.info("No strategies match your search.")
        return

    total = len(STRATEGY_METADATA)
    st.caption(f"Showing **{len(matched)}** of **{total}** strategies")
    st.markdown("")

    # Collect all visible slugs in order, tagging the first slug of each category
    cats_to_show = [cat_filter] if cat_filter != "All" else list(CATEGORIES.keys())
    other        = [s for s in matched if s not in _all_categorised]

    all_slugs: list[str] = []
    cat_of_first: dict[str, str] = {}   # slug -> category label (only first slug per cat)

    for cat in cats_to_show:
        slugs_in_cat = [s for s in CATEGORIES.get(cat, []) if s in matched]
        if slugs_in_cat:
            cat_of_first[slugs_in_cat[0]] = cat
            all_slugs.extend(slugs_in_cat)

    if other and cat_filter == "All":
        cat_of_first[other[0]] = "📦 Other"
        all_slugs.extend(other)

    # One single _render_card_row call → 1 st.columns, 3 st.markdown, N buttons
    _render_card_row(all_slugs, STRATEGY_METADATA, cat_of_first)


def _render_card_row(slugs: list, meta_map: dict, cat_of_first: dict | None = None):
    """Render all cards in ONE st.columns(3) call.

    One st.columns call instead of 19 (one per category). Each card gets
    its own markdown + button interleaved so buttons stay below their card.
    Category headers are injected as HTML above the first card of each category.
    """
    cols = st.columns(3)
    col_contexts = [cols[0], cols[1], cols[2]]

    for i, slug in enumerate(slugs):
        ci   = i % 3
        meta = meta_map[slug]
        status = meta.get("status", "stub")
        stype  = meta.get("type", "rule")
        icon   = meta.get("icon", "📌")
        sharpe = meta.get("target_sharpe", "—")
        hold   = meta.get("typical_holding_days", "—")
        desc   = meta.get("description", "")

        with col_contexts[ci]:
            # Category header inline above first card of each category
            header_html = ""
            if cat_of_first and slug in cat_of_first:
                header_html = (
                    f'<div style="font-size:12px;font-weight:700;color:#b0b8c8;'
                    f'padding:10px 2px 4px;margin-top:6px">{cat_of_first[slug]}</div>'
                )

            st.markdown(
                header_html +
                f'<div class="sg-card">'
                f'<div class="sg-card-name">{icon} {meta["display_name"]}</div>'
                f'<div class="sg-badges">'
                f'<span class="sg-badge sg-badge-{stype}">{stype.upper()}</span>'
                f'<span class="sg-badge sg-badge-{status}">{status.upper()}</span>'
                f'</div>'
                f'<div class="sg-card-desc">{desc}</div>'
                f'<div class="sg-stats">Hold {hold}d &nbsp;·&nbsp; Sharpe {sharpe}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("Open →", key=f"guide_open_{slug}", width="stretch"):
                st.session_state.guide_selected = slug
                st.rerun()


def _render_detail(slug: str, meta: dict):
    """Full detail view for one strategy — article + chart."""
    status = meta.get("status", "stub")
    stype  = meta.get("type", "rule")
    icon   = meta.get("icon", "📌")
    sharpe = meta.get("target_sharpe", "—")
    hold   = meta.get("typical_holding_days", "—")
    asset  = meta.get("asset_class", "")

    type_color   = {"ai": "#9c89ff", "rule": "#4fc3f7", "hybrid": "#ffb300"}.get(stype, "#78909c")
    status_color = {"active": "#26a69a", "stub": "#7986cb"}.get(status, "#78909c")

    # Back button
    if st.button("← Back to all strategies", key="guide_back"):
        st.session_state.guide_selected = None
        st.rerun()

    # Header card
    st.markdown(
        f"""<div class="sg-detail-header">
  <div class="sg-detail-title">{icon} {meta['display_name']}</div>
  <div class="sg-detail-meta">
    <span style="color:{type_color};font-weight:600">{stype.upper()}</span>
    &nbsp;·&nbsp;
    <span style="color:{status_color}">{status.upper()}</span>
    &nbsp;·&nbsp; Hold <strong>{hold}d</strong>
    &nbsp;·&nbsp; Target Sharpe <strong>{sharpe}</strong>
    &nbsp;·&nbsp; {asset}
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # Stats row
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Type", stype.upper())
    s2.metric("Status", status.upper())
    s3.metric("Target Sharpe", str(sharpe))
    s4.metric("Hold (days)", str(hold))

    st.markdown("")

    # Chart + article in two columns (if chart exists)
    chart = _payoff_chart(slug)
    if chart is not None:
        art_col, chart_col = st.columns([1, 1])
    else:
        art_col = st.container()
        chart_col = None

    with art_col:
        article = _load_article(slug) or ARTICLES.get(slug)
        if article:
            st.markdown(article)
        else:
            st.markdown(f"**Overview:** {meta.get('description', 'No description.')}")
            st.info("Detailed article coming soon.")

    if chart_col is not None:
        with chart_col:
            st.plotly_chart(chart, width="stretch",
                            config={"displayModeBar": False},
                            key=f"guide_chart_{slug}")

    # Status banner
    if status == "active":
        st.markdown(
            "<div class='sg-status-live'>"
            "<span style='color:#26a69a;font-weight:600'>✅ Live — </span>"
            "<span style='color:#b0b8c8'>Fully implemented. Select from the sidebar to train and backtest.</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    elif status == "stub":
        st.markdown(
            "<div class='sg-status-stub'>"
            "<span style='color:#7986cb;font-weight:600'>📐 Stub — </span>"
            "<span style='color:#b0b8c8'>Registered but not yet built. The article above describes planned mechanics.</span>"
            "</div>",
            unsafe_allow_html=True,
        )
