"""
app/pages/strategies/data_fetch.py — shared data + option-chain helpers.

Leaf module (no callbacks). Holds the fetch / payoff / trade-preview helpers used
by more than one of scan.py, backtest_view.py and modals.py. Keeping them here —
imported by those modules but importing none of them — avoids an import cycle.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from scipy.stats import norm as _scipy_norm

import plotly.graph_objects as go
from dash import html, dcc

from app import theme as T
from app.grid_helpers import mrt_grid as _mrt_grid_shared
from app.pages.strategies.registry import _UNIVERSE_TICKERS


def _get_vix_series(api_key: str | None = None):
    """Load VIX close series — DB first, Polygon fallback."""
    # Try DB first
    try:
        from db.client import get_engine, get_vix_bars
        engine = get_engine()
        vix_df = get_vix_bars(engine, date.today() - timedelta(days=400), date.today())
        if not vix_df.empty:
            return vix_df["close"].astype(float)
    except Exception:
        pass

    # Polygon fallback — fetch VIX as a ticker (^VIX / VIXW)
    if api_key:
        try:
            from engine.screener import _fetch_ohlcv
            for sym in ["I:VIX", "VIX"]:
                df = _fetch_ohlcv(sym, api_key, bars=400)
                if not df.empty and "close" in df.columns:
                    return df["close"].astype(float)
        except Exception:
            pass

    return None


def _resolve_tickers(universe: str, custom: str | None) -> list[str]:
    # If user typed anything in the custom field, always use it (overrides dropdown)
    if custom and custom.strip():
        return [t.strip().upper() for t in custom.split(",") if t.strip()]
    return _UNIVERSE_TICKERS.get(universe, [])


def _fetch_ic_strikes(ticker: str, api_key: str, spot: float, adx_ok: bool) -> tuple[dict | None, str | None]:
    """Fetch real options chain for ticker and return (chain_dict, err_str). chain is None on failure."""
    from engine.screener import _get_options_chain, _find_strike, _get_chain_mid
    target_delta = 0.16 if adx_ok else 0.10
    wing_pct     = 0.05

    exp_chain, best_exp, dte_used, err = _get_options_chain(ticker, api_key, spot)
    if err:
        return None, err
    if exp_chain is None or exp_chain.empty:
        return None, "Polygon returned no contracts in the 30–60 DTE window"

    calls = exp_chain[exp_chain["type"].str.lower() == "call"].sort_values("strike")
    puts  = exp_chain[exp_chain["type"].str.lower() == "put"].sort_values("strike", ascending=False)

    short_call_k, short_call_mid = _find_strike(calls, "call", spot, target_delta)
    short_put_k,  short_put_mid  = _find_strike(puts,  "put",  spot, target_delta)
    if short_call_k is None or short_put_k is None:
        n_calls = len(calls); n_puts = len(puts)
        return None, f"Could not find {target_delta:.0%}-delta strikes (chain had {n_calls} calls, {n_puts} puts in window)"

    wing_w = round(spot * wing_pct, 0)

    # Long call wing must be ABOVE short call (further OTM).
    calls_above = calls[calls["strike"] > short_call_k]
    if calls_above.empty:
        return None, f"No call strikes above short call ${short_call_k:.0f} — chain too narrow"
    long_call_mid, long_call_k = _get_chain_mid(calls_above, short_call_k + wing_w,
                                                 exclude_strike=short_call_k)
    if long_call_k <= short_call_k:
        return None, f"Call wing ${long_call_k:.0f} ≤ short call ${short_call_k:.0f} — invalid spread"

    # Long put wing must be BELOW short put (further OTM).
    puts_below = puts[puts["strike"] < short_put_k]
    if puts_below.empty:
        return None, f"No put strikes below short put ${short_put_k:.0f} — chain too narrow"
    long_put_mid, long_put_k = _get_chain_mid(puts_below, short_put_k - wing_w,
                                               exclude_strike=short_put_k)
    if long_put_k >= short_put_k:
        return None, f"Put wing ${long_put_k:.0f} ≥ short put ${short_put_k:.0f} — invalid spread"

    def _m(v): return v if v is not None else 0.0

    net_credit    = _m(short_call_mid) + _m(short_put_mid) - _m(long_call_mid) - _m(long_put_mid)
    call_width    = long_call_k  - short_call_k
    put_width     = short_put_k  - long_put_k
    max_loss      = min(call_width, put_width) - net_credit

    # An iron condor MUST collect a credit. A non-positive net credit means the
    # wings priced richer than the shorts — only happens on illiquid/garbage
    # quotes — so reject rather than surface an un-tradeable (debit) "condor".
    if net_credit <= 0.05:
        return None, (f"Illiquid chain — net credit ${net_credit:.2f}/share is not positive "
                      f"(wings priced richer than shorts). Try a more liquid underlying.")

    return {
        "short_call_k":   short_call_k,
        "long_call_k":    long_call_k,
        "short_put_k":    short_put_k,
        "long_put_k":     long_put_k,
        "short_call_mid": _m(short_call_mid),
        "long_call_mid":  _m(long_call_mid),
        "short_put_mid":  _m(short_put_mid),
        "long_put_mid":   _m(long_put_mid),
        "net_credit":     net_credit,
        "max_loss":       max_loss,
        "best_exp":       best_exp,
        "dte_used":       dte_used,
        "target_delta":   target_delta,
    }, None


def _fetch_ps_strikes(ticker: str, api_key: str, spot: float,
                      itm_pct: float = 0.05, wing_pct: float = 0.04) -> tuple[dict | None, str | None]:
    """
    Fetch real Polygon options chain for Put Steal and find ITM put strikes.
    short_put target: spot × (1 - itm_pct)  — slightly ITM
    long_put  target: short_put × (1 - wing_pct) — wing below
    Returns (chain_dict, err_str).
    """
    from engine.screener import _get_options_chain, _get_chain_mid

    exp_chain, best_exp, dte_used, err = _get_options_chain(ticker, api_key, spot)
    if err:
        return None, err
    if exp_chain is None or exp_chain.empty:
        return None, "No contracts in 15–45 DTE window"

    puts = exp_chain[exp_chain["type"].str.lower() == "put"].sort_values("strike", ascending=False)
    if puts.empty:
        return None, "No put contracts found"

    target_short = spot * (1.0 - itm_pct)
    target_long  = target_short * (1.0 - wing_pct)

    # Find closest real strike to target_short
    puts_sorted_short = puts.copy()
    puts_sorted_short["_dist"] = (puts_sorted_short["strike"] - target_short).abs()
    best_short = puts_sorted_short.nsmallest(1, "_dist")
    if best_short.empty:
        return None, "Could not find short put strike"
    short_put_k   = float(best_short["strike"].iloc[0])
    short_put_mid = float(best_short["mid"].iloc[0]) if not best_short["mid"].isna().iloc[0] else None

    # Find closest real strike to target_long (must be below short)
    puts_below = puts[puts["strike"] < short_put_k].copy()
    if puts_below.empty:
        return None, f"No put strikes below short put ${short_put_k:.0f}"
    long_put_mid, long_put_k = _get_chain_mid(puts_below, target_long, exclude_strike=short_put_k)

    if long_put_k >= short_put_k:
        return None, f"Long put ${long_put_k:.0f} ≥ short put ${short_put_k:.0f}"

    def _m(v): return v if v is not None else 0.0

    net_credit = _m(short_put_mid) - _m(long_put_mid)
    put_width  = short_put_k - long_put_k
    max_loss   = put_width - net_credit

    return {
        "short_put_k":   short_put_k,
        "long_put_k":    long_put_k,
        "short_put_mid": _m(short_put_mid),
        "long_put_mid":  _m(long_put_mid),
        "net_credit":    net_credit,
        "put_width":     put_width,
        "max_loss":      max_loss,
        "best_exp":      best_exp,
        "dte_used":      dte_used,
    }, None


def _build_ic_payoff_fig(spot, short_call_k, long_call_k, short_put_k, long_put_k,
                          net_credit, dte_used, atm_iv, ticker, best_exp):
    """Build IC payoff chart matching the Streamlit version."""
    r = 0.045
    prices = np.linspace(spot * 0.75, spot * 1.25, 400)

    def pnl_expiry(S):
        call_spread = np.minimum(0, short_call_k - S) + np.maximum(0, S - long_call_k)
        put_spread  = np.minimum(0, S - short_put_k)  + np.maximum(0, long_put_k - S)
        return (net_credit + call_spread + put_spread) * 100

    def pnl_today(S_arr):
        T      = max(dte_used / 252, 0.001)
        iv     = max(atm_iv or 0.25, 0.01)
        sqT    = math.sqrt(T)
        exp_rT = math.exp(-r * T)

        def _call(K):
            d1 = (np.log(S_arr / K) + (r + 0.5 * iv ** 2) * T) / (iv * sqT)
            return S_arr * _scipy_norm.cdf(d1) - K * exp_rT * _scipy_norm.cdf(d1 - sqT * iv)

        def _put(K):
            d1 = (np.log(S_arr / K) + (r + 0.5 * iv ** 2) * T) / (iv * sqT)
            return K * exp_rT * _scipy_norm.cdf(sqT * iv - d1) - S_arr * _scipy_norm.cdf(-d1)

        sc = _call(short_call_k)
        lc = _call(long_call_k)
        sp = _put(short_put_k)
        lp = _put(long_put_k)
        return (net_credit + (-sc + lc - sp + lp)) * 100

    pe = pnl_expiry(prices)
    pt = pnl_today(prices)
    profit_close  = net_credit * 0.50 * 100
    stop_loss_val = -net_credit * 2.0  * 100
    be_upper      = short_call_k + net_credit
    be_lower      = short_put_k  - net_credit

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prices, y=np.where(pe >= 0, pe, 0),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prices, y=np.where(pe < 0, pe, 0),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prices, y=pe,
        line=dict(color="#6366f1", width=2), name="P&L at expiry",
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>At expiry</extra>"))
    fig.add_trace(go.Scatter(x=prices, y=pt,
        line=dict(color="#10b981", width=1.5, dash="dot"), name="P&L today (BS)",
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Today</extra>"))

    fig.add_hline(y=profit_close, line=dict(color="#10b981", width=1.5, dash="dash"),
        annotation_text=f"✅ 50% target: +${profit_close:.0f}",
        annotation_position="top left", annotation_font_color="#10b981")
    fig.add_hline(y=stop_loss_val, line=dict(color="#ef4444", width=1.5, dash="dash"),
        annotation_text=f"🛑 2× stop: -${abs(stop_loss_val):.0f}",
        annotation_position="bottom left", annotation_font_color="#ef4444")
    fig.add_hline(y=0, line=dict(color="#374151", width=1))
    fig.add_vline(x=spot,     line=dict(color="#f59e0b", width=1.5, dash="dash"),
        annotation_text=f"Spot ${spot:.0f}", annotation_font_color="#f59e0b")
    fig.add_vline(x=be_upper, line=dict(color="#9ca3af", width=1, dash="dot"),
        annotation_text=f"BE ${be_upper:.0f}", annotation_font_color="#9ca3af")
    fig.add_vline(x=be_lower, line=dict(color="#9ca3af", width=1, dash="dot"),
        annotation_text=f"BE ${be_lower:.0f}", annotation_font_color="#9ca3af")

    fig.update_layout(
        title=dict(text=f"{ticker} Iron Condor  |  {best_exp} ({dte_used} DTE)  |  "
                        "Exit: 50% profit · 2× stop · 21 DTE", font=dict(size=13)),
        xaxis_title="Underlying Price", yaxis_title="P&L per Contract ($)",
        height=380, margin=dict(l=0, r=0, t=50, b=0),
        paper_bgcolor=T.BG_BASE, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=12),
        xaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f"),
        yaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
        template="plotly_dark",
    )
    return fig


def _hmm_trade_preview(state: int, spot: float, vix: float, ticker: str = "SPY") -> dict | None:
    """Build a state-specific trade preview for the HMM Regime modal.

    Mirrors the strategy's actual structures (see strategies/hmm_regime.py):
      state 0  → bull put credit spread (short 0.20Δ put, long 5% wider)        30 DTE
      state 1  → iron condor (0.16Δ both sides, 5% wings)                       35 DTE
      state 2  → long put debit spread (long 0.30Δ put, short 5% lower)         45 DTE

    Strikes are computed via BS delta inversion at IV proxy = VIX / 100 (same
    approximation the strategy uses internally). Returns a dict with:
        metrics     : html.Div  — metric cards row
        legs_table  : dash component — leg-by-leg breakdown (MRT)
        chart       : dcc.Graph — payoff diagram (P&L at expiry)
    Or None if inputs are degenerate.
    """
    if spot <= 0 or vix <= 0 or state not in (0, 1, 2):
        return None

    iv = max(vix / 100.0, 0.05)
    r  = 0.045

    sqT_per_yr = math.sqrt
    cdf = _scipy_norm.cdf

    def bs_call(S, K, T, sig):
        if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
            return max(0.0, S - K)
        d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqT_per_yr(T))
        d2 = d1 - sig * sqT_per_yr(T)
        return float(S * cdf(d1) - K * math.exp(-r * T) * cdf(d2))

    def bs_put(S, K, T, sig):
        if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
            return max(0.0, K - S)
        d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqT_per_yr(T))
        d2 = d1 - sig * sqT_per_yr(T)
        return float(K * math.exp(-r * T) * cdf(-d2) - S * cdf(-d1))

    def bs_delta(S, K, T, sig, option_type):
        if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
            return (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
        d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqT_per_yr(T))
        return float(cdf(d1)) if option_type == "call" else float(cdf(d1) - 1.0)

    def strike_for_delta(target_abs_delta, T, option_type):
        from scipy.optimize import brentq
        def obj(K):
            return abs(bs_delta(spot, K, T, iv, option_type)) - target_abs_delta
        try:
            return float(brentq(obj, spot * 0.40, spot * 1.60, xtol=0.01, maxiter=60))
        except (ValueError, RuntimeError):
            sign = 1.0 if option_type == "call" else -1.0
            return spot * math.exp(sign * iv * sqT_per_yr(T))

    # ── Build per-state structure ──────────────────────────────────────────
    if state == 0:
        # Bull put credit spread — 30 DTE
        dte = 30
        tau = dte / 365.0
        short_put_K = strike_for_delta(0.20, tau, "put")
        long_put_K  = short_put_K * 0.95
        sp = bs_put(spot, short_put_K, tau, iv)
        lp = bs_put(spot, long_put_K,  tau, iv)
        net_credit = max(0.01, sp - lp)
        wing       = short_put_K - long_put_K
        max_loss   = max(0.01, wing - net_credit)
        profit_target = net_credit * 0.50
        stop_loss     = -net_credit * 2.0
        be_lower      = short_put_K - net_credit
        be_upper      = None  # bull put has no upper BE (unbounded profit cap)

        trade_label = "Bull put credit spread"
        delta_target = 0.20
        is_credit = True

        # Payoff at expiry
        prices = np.linspace(spot * 0.85, spot * 1.10, 400)
        pnl_exp = np.where(
            prices >= short_put_K, net_credit * 100,
            np.where(prices >= long_put_K,
                     (net_credit - (short_put_K - prices)) * 100,
                     -max_loss * 100)
        )
        leg_rows = [
            {"Leg": "Short put",        "Strike": f"${short_put_K:.0f}",
             "Mid": f"${sp:.2f}", "Action": "SELL",
             "$/Contract": f"+${sp*100:.2f}"},
            {"Leg": "Long put (wing)",  "Strike": f"${long_put_K:.0f}",
             "Mid": f"${lp:.2f}", "Action": "BUY",
             "$/Contract": f"-${lp*100:.2f}"},
            {"Leg": "NET CREDIT",       "Strike": "", "Mid": "", "Action": "",
             "$/Contract": f"+${net_credit*100:.2f}"},
        ]
        be_marks = [("BE", be_lower)]

    elif state == 1:
        # Iron condor — 35 DTE
        dte = 35
        tau = dte / 365.0
        short_call_K = strike_for_delta(0.16, tau, "call")
        short_put_K  = strike_for_delta(0.16, tau, "put")
        long_call_K  = short_call_K * 1.05
        long_put_K   = short_put_K  * 0.95
        cs = bs_call(spot, short_call_K, tau, iv)
        cl = bs_call(spot, long_call_K,  tau, iv)
        sp = bs_put (spot, short_put_K,  tau, iv)
        lp = bs_put (spot, long_put_K,   tau, iv)
        net_credit = max(0.01, (cs - cl) + (sp - lp))
        wing       = max(short_call_K - long_call_K, short_put_K - long_put_K) * -1 + (long_call_K - short_call_K)
        # wing width is symmetric; use call-side
        wing       = long_call_K - short_call_K
        max_loss   = max(0.01, wing - net_credit)
        profit_target = net_credit * 0.50
        stop_loss     = -net_credit * 2.0
        be_lower      = short_put_K  - net_credit
        be_upper      = short_call_K + net_credit

        trade_label  = "Iron condor"
        delta_target = 0.16
        is_credit    = True

        prices = np.linspace(spot * 0.85, spot * 1.15, 400)
        call_spread = np.minimum(0, short_call_K - prices) + np.maximum(0, prices - long_call_K)
        put_spread  = np.minimum(0, prices - short_put_K)  + np.maximum(0, long_put_K  - prices)
        pnl_exp     = (net_credit + call_spread + put_spread) * 100

        leg_rows = [
            {"Leg": "Long call (wing)", "Strike": f"${long_call_K:.0f}",
             "Mid": f"${cl:.2f}", "Action": "BUY",
             "$/Contract": f"-${cl*100:.2f}"},
            {"Leg": "Short call",       "Strike": f"${short_call_K:.0f}",
             "Mid": f"${cs:.2f}", "Action": "SELL",
             "$/Contract": f"+${cs*100:.2f}"},
            {"Leg": "Short put",        "Strike": f"${short_put_K:.0f}",
             "Mid": f"${sp:.2f}", "Action": "SELL",
             "$/Contract": f"+${sp*100:.2f}"},
            {"Leg": "Long put (wing)",  "Strike": f"${long_put_K:.0f}",
             "Mid": f"${lp:.2f}", "Action": "BUY",
             "$/Contract": f"-${lp*100:.2f}"},
            {"Leg": "NET CREDIT",       "Strike": "", "Mid": "", "Action": "",
             "$/Contract": f"+${net_credit*100:.2f}"},
        ]
        be_marks = [("BE", be_lower), ("BE", be_upper)]

    else:  # state == 2
        # Long put debit spread — 45 DTE
        dte = 45
        tau = dte / 365.0
        long_put_K  = strike_for_delta(0.30, tau, "put")
        short_put_K = long_put_K * 0.95
        lp = bs_put(spot, long_put_K,  tau, iv)
        sp = bs_put(spot, short_put_K, tau, iv)
        net_debit  = max(0.01, lp - sp)
        max_profit = (long_put_K - short_put_K) - net_debit
        max_loss   = net_debit  # debit paid IS the max loss
        profit_target = net_debit * 1.00   # +100% of debit
        stop_loss     = -net_debit * 0.50  # -50% of debit
        be_upper = long_put_K - net_debit  # breakeven where the spread ITM portion covers debit
        be_lower = None

        trade_label  = "Long put debit spread"
        delta_target = 0.30
        is_credit    = False

        prices = np.linspace(spot * 0.80, spot * 1.10, 400)
        pnl_exp = np.where(
            prices >= long_put_K, -net_debit * 100,
            np.where(prices >= short_put_K,
                     ((long_put_K - prices) - net_debit) * 100,
                     ((long_put_K - short_put_K) - net_debit) * 100)
        )

        leg_rows = [
            {"Leg": "Long put",          "Strike": f"${long_put_K:.0f}",
             "Mid": f"${lp:.2f}", "Action": "BUY",
             "$/Contract": f"-${lp*100:.2f}"},
            {"Leg": "Short put (wing)",  "Strike": f"${short_put_K:.0f}",
             "Mid": f"${sp:.2f}", "Action": "SELL",
             "$/Contract": f"+${sp*100:.2f}"},
            {"Leg": "NET DEBIT",         "Strike": "", "Mid": "", "Action": "",
             "$/Contract": f"-${net_debit*100:.2f}"},
        ]
        be_marks = [("BE", be_upper)]

    # ── Metric cards ───────────────────────────────────────────────────────
    def _mc(label: str, val: str, color: str = T.TEXT_PRIMARY) -> html.Div:
        return html.Div([
            html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                    "fontWeight": "600", "textTransform": "uppercase",
                                    "marginBottom": "4px"}),
            html.Div(val,   style={"color": color, "fontSize": "1.05rem",
                                    "fontWeight": "700"}),
        ], style={**T.STYLE_CARD, "flex": "1", "minWidth": "110px", "padding": "10px 12px"})

    nc100 = (net_credit if is_credit else net_debit) * 100
    ml100 = max_loss * 100
    pt100 = profit_target * 100
    metric_cards = [
        _mc("Net Credit" if is_credit else "Net Debit",
            f"+${nc100:.2f}" if is_credit else f"-${nc100:.2f}",
            T.SUCCESS if is_credit else T.WARNING),
        _mc("Max Loss",     f"-${ml100:.2f}", T.DANGER),
        _mc("50% Target" if is_credit else "100% Target",
            f"+${pt100:.2f}", T.SUCCESS),
    ]
    if be_upper is not None:
        metric_cards.append(_mc("Upper BE", f"${be_upper:.2f}"))
    if be_lower is not None:
        metric_cards.append(_mc("Lower BE", f"${be_lower:.2f}"))
    metric_cards.append(_mc("DTE", f"{dte}d"))
    metric_cards.append(_mc("Δ target", f"~{delta_target:.0%}"))
    metric_cards.append(_mc("IV proxy", f"{iv*100:.1f}%"))

    metrics = html.Div(metric_cards,
        style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "14px"})

    # ── Legs table ─────────────────────────────────────────────────────────
    legs_table = _mrt_grid_shared(
        data=leg_rows,
        col_defs=[
            {"field": "Leg"},
            {"field": "Strike"},
            {"field": "Mid"},
            {"field": "Action"},
            {"field": "$/Contract"},
        ],
        height=240,
        enable_pagination=False,
    )

    # ── Payoff figure ──────────────────────────────────────────────────────
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prices, y=np.where(pnl_exp >= 0, pnl_exp, 0),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prices, y=np.where(pnl_exp < 0, pnl_exp, 0),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prices, y=pnl_exp,
        line=dict(color="#6366f1", width=2), name="P&L at expiry",
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>At expiry</extra>"))

    fig.add_hline(y=profit_target * 100, line=dict(color="#10b981", width=1.5, dash="dash"),
        annotation_text=f"✅ target: +${profit_target*100:.0f}",
        annotation_position="top left", annotation_font_color="#10b981")
    fig.add_hline(y=stop_loss * 100, line=dict(color="#ef4444", width=1.5, dash="dash"),
        annotation_text=f"🛑 stop: ${stop_loss*100:.0f}",
        annotation_position="bottom left", annotation_font_color="#ef4444")
    fig.add_hline(y=0, line=dict(color="#374151", width=1))
    fig.add_vline(x=spot, line=dict(color="#f59e0b", width=1.5, dash="dash"),
        annotation_text=f"Spot ${spot:.0f}", annotation_font_color="#f59e0b")
    for label, x in be_marks:
        if x is not None:
            fig.add_vline(x=x, line=dict(color="#9ca3af", width=1, dash="dot"),
                annotation_text=f"{label} ${x:.0f}",
                annotation_font_color="#9ca3af")

    fig.update_layout(
        title=dict(text=f"{ticker} {trade_label}  |  {dte} DTE  |  IV proxy {iv*100:.1f}%",
                   font=dict(size=13)),
        xaxis_title="Underlying Price",
        yaxis_title="P&L per Contract ($)",
        height=360, margin=dict(l=0, r=0, t=50, b=0),
        paper_bgcolor=T.BG_BASE, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=12),
        xaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f"),
        yaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
        template="plotly_dark",
    )
    chart = dcc.Graph(figure=fig, config={"displayModeBar": False})

    return {"metrics": metrics, "legs_table": legs_table, "chart": chart}


def _fetch_data(tickers: list[str], api_key: str):
    """Returns (vix_series, price_dfs, iv_all). Raises on fatal error."""
    from engine.screener import _fetch_ohlcv
    from engine.iv_metrics import get_iv_metrics_batch

    vix_series = _get_vix_series(api_key)
    if vix_series is None:
        raise RuntimeError("No VIX data available (DB offline and Polygon VIX fetch failed).")

    price_dfs: dict = {}
    for ticker in tickers:
        df = _fetch_ohlcv(ticker, api_key)
        if not df.empty:
            price_dfs[ticker] = df

    if not price_dfs:
        raise RuntimeError("No price data returned from Polygon for any ticker. Check API key.")

    iv_all = get_iv_metrics_batch(
        tickers=list(price_dfs.keys()),
        api_key=api_key,
        price_dfs=price_dfs,
    )
    return vix_series, price_dfs, iv_all
