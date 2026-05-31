# -*- coding: utf-8 -*-
"""
dash_app/pages/models - callbacks + slider-readout registration.

Importing this module registers every @callback via Dash's decorator
side-effect (and runs _register_readouts at import time, exactly as the
original module did). Pure numerical/figure helpers come from
dash_app.pages.models.pricing.
"""
from __future__ import annotations

import math

import dash_bootstrap_components as dbc
import numpy as np
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update, dash_table
from dash_app import theme as T
from models import (
    bs_price, bs_greeks, black76_price, black76_greeks,
    crr_american, crr_greeks_fd, american_exercise_boundary,
    digital_cash_price, digital_asset_price,
    asian_geometric_price, asian_arithmetic_mc,
    rr_barrier, barrier_mc, prob_hit_barrier,
    ZeroCurve, flat_curve, bootstrap_from_swaps,
    bond_price_ytm, bond_price_curve, ytm_solve, durations, effective_duration,
    key_rate_durations,
    swap_npv, par_swap_rate, swap_dv01, swap_cashflows,
    price_callable_bond,
    sabr_implied_vol, sabr_smile, heston_price, variance_swap_fair_variance,
    margrabe_exchange, kirk_spread,
    cap_price, european_swaption, forward_swap_rate,
)

from dash_app.pages.models.pricing import (
    _dark_fig, _wire_surface, _binomial_tree_fig,
)


def _register_readouts(pairs: list[tuple[str, str]]):
    """For each (slider_id, fmt) pair, wire a callback that updates
    #{slider_id}-readout with the current value formatted."""
    for sid, fmt in pairs:
        @callback(Output(f"{sid}-readout", "children"),
                  Input(sid, "value"),
                  prevent_initial_call=False)
        def _rd(v, _fmt=fmt):
            try:
                return f"{float(v):{_fmt}}"
            except Exception:
                return str(v)


_READOUT_FMTS = [
    # European
    ("eu-S", ".2f"), ("eu-K", ".2f"), ("eu-T", ".2f"),
    ("eu-r", ".3%"), ("eu-q", ".3%"), ("eu-sig", ".2%"),
    # American
    ("am-S", ".2f"), ("am-K", ".2f"), ("am-T", ".2f"),
    ("am-r", ".3%"), ("am-q", ".3%"), ("am-sig", ".2%"),
    ("am-N", ".0f"), ("am-Nviz", ".0f"),
    # Black-76
    ("b76-F", ".2f"), ("b76-K", ".2f"), ("b76-T", ".2f"),
    ("b76-r", ".3%"), ("b76-sig", ".2%"),
    # Barrier
    ("br-S", ".2f"), ("br-K", ".2f"), ("br-H", ".2f"), ("br-T", ".2f"),
    ("br-r", ".3%"), ("br-q", ".3%"), ("br-sig", ".2%"),
    # Digital
    ("dg-S", ".2f"), ("dg-K", ".2f"), ("dg-T", ".2f"),
    ("dg-r", ".3%"), ("dg-q", ".3%"), ("dg-sig", ".2%"), ("dg-cash", ".2f"),
    # Asian
    ("as-S", ".2f"), ("as-K", ".2f"), ("as-T", ".2f"),
    ("as-r", ".3%"), ("as-q", ".3%"), ("as-sig", ".2%"), ("as-n", ".0f"),
    # SABR
    ("sb-F", ".2f"), ("sb-T", ".2f"), ("sb-alpha", ".2%"),
    ("sb-beta", ".2f"), ("sb-rho", ".2f"), ("sb-nu", ".2f"),
    # Heston
    ("hs-S",".2f"), ("hs-K",".2f"), ("hs-T",".2f"), ("hs-r",".3%"), ("hs-q",".3%"),
    ("hs-v0",".3f"), ("hs-kappa",".2f"), ("hs-theta",".3f"),
    ("hs-sigv",".2f"), ("hs-rho",".2f"),
    # Variance swap
    ("vs-S",".2f"), ("vs-T",".2f"), ("vs-r",".3%"), ("vs-q",".3%"),
    ("vs-atm",".2%"), ("vs-skew",".4f"),
    # Spread
    ("sp-S1",".2f"), ("sp-S2",".2f"), ("sp-K",".2f"), ("sp-T",".2f"),
    ("sp-r",".3%"), ("sp-s1",".2%"), ("sp-s2",".2%"), ("sp-rho",".2f"),
    # Caps
    ("cp-strike",".3%"), ("cp-tenor",".2f"), ("cp-sigma",".2%"),
    ("cp-curve",".3%"),  ("cp-not",".0f"),
    # Swaption
    ("sp2-exp",".2f"),  ("sp2-ten",".2f"),  ("sp2-K",".3%"),
    ("sp2-sig",".2%"),  ("sp2-curve",".3%"),("sp2-not",".0f"),
    # Bond
    ("bd-face", ".0f"), ("bd-cpn", ".3%"), ("bd-mat", ".2f"), ("bd-ytm", ".3%"),
    # Swap
    ("sw-not", ".0f"), ("sw-rate", ".3%"), ("sw-tenor", ".2f"), ("sw-curve", ".3%"),
    # Callable
    ("cb-face", ".0f"), ("cb-cpn", ".3%"), ("cb-mat", ".2f"), ("cb-curve", ".3%"),
    ("cb-sig",  ".3f"), ("cb-a",   ".3f"), ("cb-ct", ".2f"),  ("cb-cp", ".2f"),
    ("cb-N",    ".0f"),
]
_register_readouts(_READOUT_FMTS)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — European
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("eu-price","children"), Output("eu-delta","children"),
    Output("eu-gamma","children"), Output("eu-vega","children"),
    Output("eu-theta","children"), Output("eu-rho","children"),
    Output("eu-vanna","children"), Output("eu-vomma","children"),
    Output("eu-chart-price","figure"), Output("eu-chart-greeks","figure"),
    Output("eu-chart-gamma-surf","figure"),
    Output("eu-chart-term","figure"), Output("eu-chart-vol","figure"),
    Input("eu-S","value"), Input("eu-K","value"), Input("eu-T","value"),
    Input("eu-r","value"), Input("eu-q","value"), Input("eu-sig","value"),
    Input("eu-cp","value"),
)
def _eu_update(S, K, Tau, r, q, sig, cp):
    S, K, Tau, r, q, sig = float(S), float(K), float(Tau), float(r), float(q), float(sig)
    price = bs_price(S, K, Tau, r, q, sig, cp)
    g = bs_greeks(S, K, Tau, r, q, sig, cp)

    # Price vs spot
    spots = np.linspace(max(5, S*0.5), S*1.5, 80)
    prices = [bs_price(s, K, Tau, r, q, sig, cp) for s in spots]
    fig_p = go.Figure(go.Scatter(x=spots, y=prices, mode="lines",
                                  line=dict(color=T.ACCENT, width=2), name="Price"))
    fig_p.add_vline(x=S, line=dict(color=T.WARNING, width=1, dash="dash"),
                    annotation_text=f"S={S:.2f}", annotation_position="top")
    fig_p.update_layout(**_dark_fig(), title="Price vs Spot", height=620,
                         xaxis_title="Spot", yaxis_title="Price")

    # Greeks vs spot
    delta_l = [bs_greeks(s, K, Tau, r, q, sig, cp)["delta"] for s in spots]
    gamma_l = [bs_greeks(s, K, Tau, r, q, sig, cp)["gamma"] for s in spots]
    vega_l  = [bs_greeks(s, K, Tau, r, q, sig, cp)["vega"]  for s in spots]
    fig_g = go.Figure()
    fig_g.add_trace(go.Scatter(x=spots, y=delta_l, name="Delta", line=dict(color="#10b981")))
    fig_g.add_trace(go.Scatter(x=spots, y=np.array(gamma_l)*100, name="Gamma (×100)", line=dict(color="#f59e0b")))
    fig_g.add_trace(go.Scatter(x=spots, y=np.array(vega_l)/10,  name="Vega (÷10)",  line=dict(color="#60a5fa")))
    fig_g.update_layout(**_dark_fig(), title="Greeks vs Spot", height=620)

    # Gamma surface over (S, T) — wireframe style (matches Market Data tab)
    S_grid = np.linspace(max(5, S*0.7), S*1.3, 24)
    T_grid = np.linspace(max(0.05, Tau*0.1), Tau*2.0 if Tau else 2.0, 20)
    Gm = np.zeros((len(T_grid), len(S_grid)))
    for i, tt in enumerate(T_grid):
        for j, ss in enumerate(S_grid):
            Gm[i, j] = bs_greeks(ss, K, tt, r, q, sig, cp)["gamma"]
    fig_s = _wire_surface(S_grid, T_grid, Gm,
                          x_title="Spot", y_title="T (yrs)", z_title="Gamma",
                          title="Gamma Surface (Spot × Time)",
                          x_fmt=".1f", z_fmt=".4f", highlight_x=S)

    # Term structure
    T_l = np.linspace(0.01, max(Tau*3, 3.0), 60)
    p_T = [bs_price(S, K, tt, r, q, sig, cp) for tt in T_l]
    fig_t = go.Figure(go.Scatter(x=T_l, y=p_T, mode="lines", line=dict(color=T.ACCENT)))
    fig_t.add_vline(x=Tau, line=dict(color=T.WARNING, dash="dash"))
    fig_t.update_layout(**_dark_fig(), title="Price vs Time to Expiry", height=620,
                         xaxis_title="T (years)", yaxis_title="Price")

    # Vol sweep
    sig_l = np.linspace(0.01, 1.0, 60)
    p_sig = [bs_price(S, K, Tau, r, q, s, cp) for s in sig_l]
    fig_v = go.Figure(go.Scatter(x=sig_l, y=p_sig, mode="lines", line=dict(color=T.ACCENT)))
    fig_v.add_vline(x=sig, line=dict(color=T.WARNING, dash="dash"))
    fig_v.update_layout(**_dark_fig(), title="Price vs Volatility", height=620,
                         xaxis_title="σ", yaxis_title="Price")

    def _f(v, fmt=".4f"): return f"{v:{fmt}}"
    return (
        _f(price, ".4f"),  _f(g["delta"], ".4f"), _f(g["gamma"], ".5f"),
        _f(g["vega"]/100,  ".4f"),
        _f(g["theta"], ".4f"), _f(g["rho"],   ".4f"),
        _f(g["vanna"], ".4f"), _f(g["vomma"], ".4f"),
        fig_p, fig_g, fig_s, fig_t, fig_v,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — American (CRR)
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("am-price","children"), Output("am-eep","children"),
    Output("am-delta","children"), Output("am-gamma","children"),
    Output("am-vega","children"),  Output("am-theta","children"),
    Output("am-euro","children"),  Output("am-conv","children"),
    Output("am-chart-stock-tree","figure"),
    Output("am-chart-option-tree","figure"),
    Output("am-chart-boundary","figure"),
    Output("am-chart-price","figure"),
    Output("am-chart-conv","figure"),
    Input("am-S","value"),   Input("am-K","value"),   Input("am-T","value"),
    Input("am-r","value"),   Input("am-q","value"),   Input("am-sig","value"),
    Input("am-N","value"),   Input("am-Nviz","value"),
    Input("am-cp","value"),
)
def _am_update(S, K, Tau, r, q, sig, N, N_viz, cp):
    S, K, Tau, r, q, sig = float(S), float(K), float(Tau), float(r), float(q), float(sig)
    N = int(N)
    am = crr_american(S, K, Tau, r, q, sig, cp, N=N)
    eu = bs_price(S, K, Tau, r, q, sig, cp)
    eep = am - eu
    fd  = crr_greeks_fd(S, K, Tau, r, q, sig, cp, N=max(100, min(N, 400)))

    # Boundary
    tt, bd = american_exercise_boundary(S, K, Tau, r, q, sig, cp, N=min(200, max(50, N//2)))
    fig_b = go.Figure()
    if len(tt) > 0:
        fig_b.add_trace(go.Scatter(x=tt, y=bd, mode="lines+markers",
                                    line=dict(color=T.DANGER, width=2),
                                    marker=dict(size=4),
                                    name="Critical S*(t)"))
    fig_b.add_hline(y=K, line=dict(color=T.WARNING, dash="dash"),
                     annotation_text="K")
    fig_b.update_layout(**_dark_fig(),
                         title=f"Early-Exercise Boundary — {cp.title()}",
                         xaxis_title="Time to expiry (years)", yaxis_title="Critical S*",
                         height=620)

    # Price vs Spot (American vs European)
    sp = np.linspace(max(5, S*0.5), S*1.5, 40)
    a_l = [crr_american(s, K, Tau, r, q, sig, cp, N=min(N, 200)) for s in sp]
    e_l = [bs_price(s, K, Tau, r, q, sig, cp) for s in sp]
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=sp, y=a_l, name="American", line=dict(color=T.ACCENT)))
    fig_p.add_trace(go.Scatter(x=sp, y=e_l, name="European", line=dict(color=T.SUCCESS, dash="dot")))
    fig_p.add_vline(x=S, line=dict(color=T.WARNING, dash="dash"))
    fig_p.update_layout(**_dark_fig(), title="American vs European", height=620,
                         xaxis_title="Spot", yaxis_title="Price")

    # CRR convergence plot
    N_list = [20, 40, 60, 100, 150, 200, 300, 500, 800, 1200]
    c_list = [crr_american(S, K, Tau, r, q, sig, cp, N=n_) for n_ in N_list]
    fig_c = go.Figure()
    fig_c.add_trace(go.Scatter(x=N_list, y=c_list, mode="lines+markers",
                                line=dict(color=T.ACCENT), name="CRR price"))
    fig_c.add_hline(y=eu, line=dict(color=T.SUCCESS, dash="dot"),
                     annotation_text=f"European = {eu:.4f}")
    fig_c.update_layout(**_dark_fig(), title="CRR Price Convergence in N",
                         xaxis_title="Binomial steps N", yaxis_title="Price", height=620)

    # Suggested N for convergence within 1e-3
    conv_N = next((n for n, p_ in zip(N_list, c_list)
                    if abs(p_ - c_list[-1]) < 1e-3), N_list[-1])

    # Stock & Option trees — controlled by independent N_viz slider
    nviz = int(max(4, min(30, int(N_viz))))
    fig_st = _binomial_tree_fig(S, K, Tau, r, q, sig, cp, N_viz=nviz, tree_kind="stock")
    fig_op = _binomial_tree_fig(S, K, Tau, r, q, sig, cp, N_viz=nviz, tree_kind="option")

    return (
        f"{am:.4f}", f"{eep:+.4f}",
        f"{fd['delta']:.4f}", f"{fd['gamma']:.5f}",
        f"{fd['vega']:.4f}",  f"{fd['theta']:.4f}",
        f"{eu:.4f}", f"{conv_N}",
        fig_st, fig_op, fig_b, fig_p, fig_c,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Black-76
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("b76-price","children"), Output("b76-delta","children"),
    Output("b76-gamma","children"), Output("b76-vega","children"),
    Output("b76-theta","children"), Output("b76-rho","children"),
    Output("b76-chart-price","figure"), Output("b76-chart-greeks","figure"),
    Input("b76-F","value"), Input("b76-K","value"), Input("b76-T","value"),
    Input("b76-r","value"), Input("b76-sig","value"), Input("b76-cp","value"),
)
def _b76_update(F, K, Tau, r, sig, cp):
    F, K, Tau, r, sig = float(F), float(K), float(Tau), float(r), float(sig)
    p = black76_price(F, K, Tau, r, sig, cp)
    g = black76_greeks(F, K, Tau, r, sig, cp)

    Fg = np.linspace(max(5, F*0.5), F*1.5, 80)
    prices = [black76_price(f, K, Tau, r, sig, cp) for f in Fg]
    deltas = [black76_greeks(f, K, Tau, r, sig, cp)["delta"] for f in Fg]
    gammas = [black76_greeks(f, K, Tau, r, sig, cp)["gamma"] for f in Fg]

    fig_p = go.Figure(go.Scatter(x=Fg, y=prices, line=dict(color=T.ACCENT)))
    fig_p.add_vline(x=F, line=dict(color=T.WARNING, dash="dash"))
    fig_p.update_layout(**_dark_fig(), title="Price vs Forward",
                         xaxis_title="Forward F", yaxis_title="Price", height=620)

    fig_g = go.Figure()
    fig_g.add_trace(go.Scatter(x=Fg, y=deltas, name="Delta (dF)", line=dict(color=T.SUCCESS)))
    fig_g.add_trace(go.Scatter(x=Fg, y=np.array(gammas)*100, name="Gamma ×100", line=dict(color=T.WARNING)))
    fig_g.update_layout(**_dark_fig(), title="Greeks vs Forward", height=620)

    return (f"{p:.4f}", f"{g['delta']:.4f}", f"{g['gamma']:.5f}",
            f"{g['vega']/100:.4f}", f"{g['theta']:.4f}", f"{g['rho']:.4f}",
            fig_p, fig_g)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Barrier
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("br-price","children"), Output("br-mc","children"),
    Output("br-mc-se","children"), Output("br-phit","children"),
    Output("br-vanilla","children"), Output("br-check","children"),
    Output("br-chart-price","figure"), Output("br-chart-phit-term","figure"),
    Input("br-S","value"), Input("br-K","value"), Input("br-H","value"),
    Input("br-T","value"), Input("br-r","value"), Input("br-q","value"),
    Input("br-sig","value"), Input("br-cp","value"),
    Input("br-io","value"), Input("br-ud","value"),
)
def _br_update(S, K, H, Tau, r, q, sig, cp, io, ud):
    S, K, H, Tau, r, q, sig = map(float, (S, K, H, Tau, r, q, sig))
    try:
        rr = rr_barrier(S, K, H, Tau, r, q, sig, cp, io, ud)
    except Exception as e:
        rr = float("nan")
    try:
        mc, se = barrier_mc(S, K, H, Tau, r, q, sig, cp, io, ud,
                             paths=6000, steps=120, seed=42)
    except Exception:
        mc, se = float("nan"), 0.0
    phit = prob_hit_barrier(S, H, Tau, r, q, sig, up=(ud == "up"))
    vanilla = bs_price(S, K, Tau, r, q, sig, cp)

    other_io = "out" if io == "in" else "in"
    try:
        other = rr_barrier(S, K, H, Tau, r, q, sig, cp, other_io, ud)
    except Exception:
        other = float("nan")
    check = f"{rr:.4f} + {other:.4f} = {rr+other:.4f}  (vanilla = {vanilla:.4f})"

    # Price vs spot
    sp = np.linspace(max(5, S*0.5), max(S, H)*1.3, 80)
    prices = []
    for s in sp:
        try:
            prices.append(rr_barrier(s, K, H, Tau, r, q, sig, cp, io, ud))
        except Exception:
            prices.append(float("nan"))
    fig_p = go.Figure(go.Scatter(x=sp, y=prices, line=dict(color=T.ACCENT)))
    fig_p.add_vline(x=S, line=dict(color=T.WARNING, dash="dash"),
                     annotation_text=f"S={S:.0f}")
    fig_p.add_vline(x=H, line=dict(color=T.DANGER, dash="dot"),
                     annotation_text=f"H={H:.0f}")
    fig_p.update_layout(**_dark_fig(), title=f"{cp.title()} {ud}-{io} Barrier — Price",
                         xaxis_title="Spot", yaxis_title="Price", height=620)

    # Hit probability vs T
    Tg = np.linspace(0.01, max(Tau*3, 2.0), 50)
    p_hit = [prob_hit_barrier(S, H, tt, r, q, sig, up=(ud == "up")) for tt in Tg]
    fig_h = go.Figure(go.Scatter(x=Tg, y=p_hit, line=dict(color=T.DANGER),
                                   fill="tozeroy"))
    fig_h.add_vline(x=Tau, line=dict(color=T.WARNING, dash="dash"))
    fig_h.update_layout(**_dark_fig(), title="P(Hit Barrier) vs T",
                         xaxis_title="T (years)", yaxis_title="Probability",
                         yaxis=dict(range=[0, 1]), height=620)

    return (f"{rr:.4f}", f"{mc:.4f}", f"±{2*se:.4f}", f"{phit:.3%}",
            f"{vanilla:.4f}", check, fig_p, fig_h)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Digital
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("dg-cash-price","children"), Output("dg-asset-price","children"),
    Output("dg-parity","children"),
    Output("dg-chart-price","figure"),
    Input("dg-S","value"), Input("dg-K","value"), Input("dg-T","value"),
    Input("dg-r","value"), Input("dg-q","value"), Input("dg-sig","value"),
    Input("dg-cash","value"), Input("dg-cp","value"),
)
def _dg_update(S, K, Tau, r, q, sig, cash, cp):
    S, K, Tau, r, q, sig, cash = map(float, (S, K, Tau, r, q, sig, cash))
    cash_p  = digital_cash_price(S, K, Tau, r, q, sig, cp, cash=cash)
    asset_p = digital_asset_price(S, K, Tau, r, q, sig, cp)
    opp = "put" if cp == "call" else "call"
    cash_o = digital_cash_price(S, K, Tau, r, q, sig, opp, cash=cash)
    parity = f"{cash_p:.4f} + {cash_o:.4f} = {cash_p + cash_o:.4f}  (target {cash*math.exp(-r*Tau):.4f})"

    sp = np.linspace(max(5, S*0.5), S*1.5, 80)
    prices = [digital_cash_price(s, K, Tau, r, q, sig, cp, cash=cash) for s in sp]
    fig = go.Figure(go.Scatter(x=sp, y=prices, line=dict(color=T.ACCENT)))
    fig.add_vline(x=S, line=dict(color=T.WARNING, dash="dash"))
    fig.add_vline(x=K, line=dict(color=T.DANGER, dash="dot"),
                   annotation_text=f"K={K:.0f}")
    fig.update_layout(**_dark_fig(), title=f"Cash-or-Nothing {cp.title()} vs Spot",
                       xaxis_title="Spot", yaxis_title="Price", height=620)
    return (f"{cash_p:.4f}", f"{asset_p:.4f}", parity, fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Asian
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("as-geo","children"), Output("as-arith","children"),
    Output("as-euro","children"),
    Output("as-chart-vs-spot","figure"), Output("as-chart-vs-n","figure"),
    Input("as-S","value"), Input("as-K","value"), Input("as-T","value"),
    Input("as-r","value"), Input("as-q","value"), Input("as-sig","value"),
    Input("as-n","value"), Input("as-cp","value"),
)
def _as_update(S, K, Tau, r, q, sig, n, cp):
    S, K, Tau, r, q, sig = map(float, (S, K, Tau, r, q, sig))
    n = int(n)
    geo  = asian_geometric_price(S, K, Tau, r, q, sig, cp, n_fix=n)
    arith, se = asian_arithmetic_mc(S, K, Tau, r, q, sig, cp, n_fix=n,
                                     paths=4000, seed=42)
    eu = bs_price(S, K, Tau, r, q, sig, cp)

    sp = np.linspace(max(5, S*0.5), S*1.5, 40)
    g_l = [asian_geometric_price(s, K, Tau, r, q, sig, cp, n_fix=n) for s in sp]
    e_l = [bs_price(s, K, Tau, r, q, sig, cp) for s in sp]
    fig_p = go.Figure()
    fig_p.add_trace(go.Scatter(x=sp, y=g_l, name="Geometric Asian", line=dict(color=T.ACCENT)))
    fig_p.add_trace(go.Scatter(x=sp, y=e_l, name="European",       line=dict(color=T.SUCCESS, dash="dot")))
    fig_p.add_vline(x=S, line=dict(color=T.WARNING, dash="dash"))
    fig_p.update_layout(**_dark_fig(), title="Asian vs European", height=620,
                         xaxis_title="Spot", yaxis_title="Price")

    ns = [2, 4, 6, 12, 24, 52, 100, 252]
    p_n = [asian_geometric_price(S, K, Tau, r, q, sig, cp, n_fix=m) for m in ns]
    fig_n = go.Figure(go.Scatter(x=ns, y=p_n, mode="lines+markers",
                                  line=dict(color=T.ACCENT)))
    fig_n.add_hline(y=eu, line=dict(color=T.SUCCESS, dash="dot"),
                     annotation_text=f"European = {eu:.4f}")
    fig_n.update_layout(**_dark_fig(), title="Price vs # Fixings (Geometric)",
                         xaxis_title="Fixings", yaxis_title="Price",
                         xaxis_type="log", height=620)
    return (f"{geo:.4f}", f"{arith:.4f} ±{2*se:.3f}", f"{eu:.4f}", fig_p, fig_n)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Curve
# ═══════════════════════════════════════════════════════════════════════════

@callback(Output("rc-curve-table","data", allow_duplicate=True),
          Input("rc-add-row","n_clicks"),
          State("rc-curve-table","data"),
          prevent_initial_call=True)
def _rc_add_row(n, data):
    if not n:
        return no_update
    data = list(data or [])
    last_t = data[-1]["tenor"] if data else 1
    last_r = data[-1]["rate"]  if data else 4.0
    data.append({"tenor": float(last_t) + 1.0, "rate": float(last_r)})
    return data


@callback(
    Output("rc-short","children"), Output("rc-mid","children"),
    Output("rc-long","children"),
    Output("rc-chart-zero-fwd","figure"), Output("rc-chart-df","figure"),
    Output("rc-chart-fwd-surf","figure"),
    Input("rc-curve-table","data"), Input("rc-interp","value"),
)
def _rc_update(data, interp):
    if not data:
        empty = go.Figure().update_layout(**_dark_fig(), title="No data")
        return "—","—","—", empty, empty, empty
    try:
        tenors = [float(r["tenor"]) for r in data if r.get("tenor") is not None]
        rates  = [float(r["rate"])/100 for r in data if r.get("rate") is not None]
        curve  = ZeroCurve(tenors, rates, interp=interp)
    except Exception as e:
        empty = go.Figure().update_layout(**_dark_fig(), title=f"Error: {e}")
        return "—","—","—", empty, empty, empty

    tg = np.linspace(0.25, max(30, max(tenors)), 80)
    zeros = np.array([float(curve.zero(t)) for t in tg])
    fwds  = np.zeros(len(tg)-1)
    for i in range(len(tg)-1):
        fwds[i] = curve.forward(tg[i], tg[i+1])

    fig_zf = go.Figure()
    fig_zf.add_trace(go.Scatter(x=tg, y=zeros*100, name="Zero rate", line=dict(color=T.ACCENT)))
    fig_zf.add_trace(go.Scatter(x=tg[:-1], y=fwds*100, name="Inst. forward",
                                  line=dict(color=T.SUCCESS, dash="dot")))
    fig_zf.update_layout(**_dark_fig(), title="Zero + Forward Curve",
                          xaxis_title="Tenor (y)", yaxis_title="Rate (%)", height=620)

    dfs = np.array([float(curve.df(t)) for t in tg])
    fig_df = go.Figure(go.Scatter(x=tg, y=dfs, line=dict(color=T.ACCENT)))
    fig_df.update_layout(**_dark_fig(), title="Discount Factor",
                          xaxis_title="Tenor", yaxis_title="DF", height=620)

    # Forward surface — wireframe style
    starts = np.linspace(0.25, min(10, max(tenors)*0.7), 16)
    taus   = np.linspace(0.25, min(10, max(tenors)*0.7), 16)
    Z = np.zeros((len(starts), len(taus)))
    for i, s in enumerate(starts):
        for j, tau in enumerate(taus):
            try:
                Z[i, j] = curve.forward(s, s + tau) * 100
            except Exception:
                Z[i, j] = np.nan
    fig_s = _wire_surface(taus, starts, Z,
                          x_title="τ (years)", y_title="Start (y)",
                          z_title="Forward (%)",
                          title="Forward Rate Surface",
                          x_fmt=".1f", z_fmt=".2f")

    def _f(t_): return f"{float(curve.zero(t_))*100:.3f}%"
    return (_f(0.25), _f(5.0), _f(min(30, max(tenors))),
            fig_zf, fig_df, fig_s)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Bond
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("bd-pv","children"),  Output("bd-mac","children"),
    Output("bd-mod","children"), Output("bd-conv","children"),
    Output("bd-dv01","children"),Output("bd-par","children"),
    Output("bd-acc","children"), Output("bd-clean","children"),
    Output("bd-chart-cf","figure"),  Output("bd-chart-pvy","figure"),
    Output("bd-chart-dvmat","figure"),
    Input("bd-face","value"), Input("bd-cpn","value"),
    Input("bd-mat","value"),  Input("bd-ytm","value"),
    Input("bd-freq","value"),
)
def _bd_update(face, cpn, mat, ytm, freq):
    face, cpn, mat, ytm = map(float, (face, cpn, mat, ytm))
    freq = int(freq)
    r  = bond_price_ytm(face, cpn, freq, mat, ytm)
    d  = durations(face, cpn, freq, mat, ytm)

    # Cash-flow chart
    times, amounts = r["times"], r["amounts"]
    fig_cf = go.Figure(go.Bar(x=times, y=amounts, marker_color=T.ACCENT))
    fig_cf.update_layout(**_dark_fig(), title="Bond Cash Flows",
                          xaxis_title="Year", yaxis_title="Cashflow", height=620)

    # PV vs YTM with linear approx
    ys = np.linspace(max(-0.02, ytm - 0.05), ytm + 0.05, 60)
    pvs = [bond_price_ytm(face, cpn, freq, mat, y)["pv"] for y in ys]
    lin = [r["pv"] - d["modified"] * r["pv"] * (y - ytm) for y in ys]
    fig_py = go.Figure()
    fig_py.add_trace(go.Scatter(x=ys*100, y=pvs, name="Actual PV",  line=dict(color=T.ACCENT)))
    fig_py.add_trace(go.Scatter(x=ys*100, y=lin, name="Linear (mod dur)",
                                  line=dict(color=T.DANGER, dash="dot")))
    fig_py.add_vline(x=ytm*100, line=dict(color=T.WARNING, dash="dash"))
    fig_py.update_layout(**_dark_fig(), title="PV vs YTM — Convexity Visible",
                          xaxis_title="YTM (%)", yaxis_title="PV", height=620)

    # Duration vs maturity
    mats = np.linspace(0.5, 30, 60)
    durs = [durations(face, cpn, freq, m, ytm)["modified"] for m in mats]
    fig_dm = go.Figure(go.Scatter(x=mats, y=durs, line=dict(color=T.ACCENT)))
    fig_dm.add_vline(x=mat, line=dict(color=T.WARNING, dash="dash"))
    fig_dm.update_layout(**_dark_fig(), title="Modified Duration vs Maturity",
                          xaxis_title="Maturity (y)", yaxis_title="Mod. duration (y)", height=620)

    # Par yield: coupon where price=face
    try:
        par_yield = ytm_solve(face, face, cpn, freq, mat)
    except Exception:
        par_yield = ytm
    return (
        f"{r['pv']:.4f}", f"{d['macaulay']:.3f}",
        f"{d['modified']:.3f}", f"{d['convexity']:.2f}",
        f"{d['dv01']:.4f}", f"{par_yield:.3%}",
        f"{r['accrued']:.4f}", f"{r['clean']:.4f}",
        fig_cf, fig_py, fig_dm,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Swap
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("sw-npv","children"), Output("sw-par","children"),
    Output("sw-dv01","children"),Output("sw-fxleg","children"),
    Output("sw-chart-cf","figure"), Output("sw-chart-npv","figure"),
    Input("sw-not","value"),   Input("sw-rate","value"),
    Input("sw-tenor","value"), Input("sw-curve","value"),
    Input("sw-ff","value"),    Input("sw-side","value"),
)
def _sw_update(notM, rate, tenor, base, ff, pay_fixed):
    notional = float(notM) * 1_000_000
    rate, tenor, base = float(rate), float(tenor), float(base)
    ff = int(ff)
    curve = flat_curve(base)
    npv = swap_npv(curve, notional, rate, tenor, ff, 4, bool(pay_fixed))
    par = par_swap_rate(curve, tenor, ff)
    dv01 = swap_dv01(curve, notional, rate, tenor, ff, 4, bool(pay_fixed))
    cf = swap_cashflows(curve, notional, rate, tenor, ff, 4, bool(pay_fixed))

    # Fixed leg PV
    fix_pv = float(sum(cf["fixed_amounts"][i] * curve.df(cf["fixed_times"][i])
                        for i in range(len(cf["fixed_amounts"]))))

    # Cashflow ladder
    fig_cf = go.Figure()
    fig_cf.add_trace(go.Bar(x=cf["fixed_times"], y=cf["fixed_amounts"]/1_000_000,
                              name="Fixed (pay)", marker_color=T.DANGER, opacity=0.7))
    fig_cf.add_trace(go.Bar(x=cf["float_times"], y=cf["float_amounts"]/1_000_000,
                              name="Float (receive)", marker_color=T.SUCCESS, opacity=0.7))
    fig_cf.update_layout(**_dark_fig(), title="Swap Cashflows ($ millions)",
                          xaxis_title="Year", yaxis_title="CF ($M)",
                          barmode="group", height=620)

    # NPV vs parallel shift
    shifts = np.linspace(-100, 100, 41)
    npvs = [swap_npv(curve.shift(b), notional, rate, tenor, ff, 4, bool(pay_fixed))
            for b in shifts]
    fig_npv = go.Figure(go.Scatter(x=shifts, y=np.array(npvs)/1_000, line=dict(color=T.ACCENT)))
    fig_npv.add_hline(y=0, line=dict(color=T.TEXT_MUTED, dash="dot"))
    fig_npv.update_layout(**_dark_fig(), title="NPV vs Curve Shift (bp)",
                           xaxis_title="Parallel shift (bp)",
                           yaxis_title="NPV ($k)", height=620)

    return (f"{npv:,.0f}", f"{par:.3%}", f"{dv01:,.0f}", f"{fix_pv:,.0f}",
            fig_cf, fig_npv)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Callable bond (Hull-White)
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("cb-straight","children"), Output("cb-cbl","children"),
    Output("cb-opt","children"),      Output("cb-dur","children"),
    Output("cb-chart-shift","figure"),
    Input("cb-face","value"),  Input("cb-cpn","value"),
    Input("cb-mat","value"),   Input("cb-curve","value"),
    Input("cb-sig","value"),   Input("cb-a","value"),
    Input("cb-ct","value"),    Input("cb-cp","value"),
    Input("cb-N","value"),
)
def _cb_update(face, cpn, mat, base, sig, a, ct, cp, N):
    face, cpn, mat, base = map(float, (face, cpn, mat, base))
    sig, a, ct, cp = map(float, (sig, a, ct, cp))
    N = int(N)
    curve = flat_curve(base)
    try:
        res = price_callable_bond(
            curve, face=face, coupon_rate=cpn, freq=2, maturity=mat,
            call_schedule=[(ct, cp)],
            sigma=sig, a=a, steps=max(20, min(N, 80)),
        )
        callable_p = res["callable_price"]
        straight_p = res["straight_price"]
        opt_val    = res["call_option_value"]
        dur        = res["effective_duration"]
    except Exception as e:
        return "—","—","—", f"error: {e}", go.Figure().update_layout(**_dark_fig())

    # Shift chart
    shifts = np.linspace(-200, 200, 17)
    cb_prices = []
    st_prices = []
    for b in shifts:
        try:
            r2 = price_callable_bond(
                curve.shift(b), face=face, coupon_rate=cpn, freq=2, maturity=mat,
                call_schedule=[(ct, cp)],
                sigma=sig, a=a, steps=max(20, min(N, 50)),
            )
            cb_prices.append(r2["callable_price"])
            st_prices.append(r2["straight_price"])
        except Exception:
            cb_prices.append(float("nan"))
            st_prices.append(float("nan"))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=shifts, y=st_prices, name="Straight",
                               line=dict(color=T.SUCCESS, dash="dot")))
    fig.add_trace(go.Scatter(x=shifts, y=cb_prices, name="Callable",
                               line=dict(color=T.ACCENT)))
    fig.update_layout(**_dark_fig(), title="Price vs Parallel Curve Shift",
                       xaxis_title="Shift (bp)", yaxis_title="Price", height=620)

    return (f"{straight_p:.4f}", f"{callable_p:.4f}",
            f"{opt_val:.4f}", f"{dur:.3f}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — SABR
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("sb-atm","children"), Output("sb-skew","children"),
    Output("sb-wing","children"),
    Output("sb-chart-smile","figure"),
    Input("sb-F","value"),     Input("sb-T","value"),
    Input("sb-alpha","value"), Input("sb-beta","value"),
    Input("sb-rho","value"),   Input("sb-nu","value"),
)
def _sb_update(F, Tau, alpha, beta, rho, nu):
    F, Tau, alpha, beta, rho, nu = map(float, (F, Tau, alpha, beta, rho, nu))
    Ks = np.linspace(F*0.7, F*1.3, 61)
    smile = sabr_smile(F, Tau, Ks, alpha, beta, rho, nu)
    atm = sabr_implied_vol(F, F, Tau, alpha, beta, rho, nu)
    put_25d = sabr_implied_vol(F, F*0.90, Tau, alpha, beta, rho, nu)
    call_25d = sabr_implied_vol(F, F*1.10, Tau, alpha, beta, rho, nu)
    skew = put_25d - call_25d
    wing_diff = sabr_implied_vol(F, F*0.90, Tau, alpha, beta, rho, nu) - sabr_implied_vol(F, F*1.10, Tau, alpha, beta, rho, nu)

    fig = go.Figure(go.Scatter(x=Ks, y=smile*100, line=dict(color=T.ACCENT, width=2)))
    fig.add_vline(x=F, line=dict(color=T.WARNING, dash="dash"),
                   annotation_text=f"F={F:.0f}")
    fig.update_layout(**_dark_fig(),
                       title="SABR Implied-Vol Smile",
                       xaxis_title="Strike K", yaxis_title="σ_B (%)", height=620)
    return (f"{atm:.2%}", f"{skew:+.2%}", f"{wing_diff:+.2%}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Heston
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("hs-price","children"), Output("hs-bs","children"),
    Output("hs-diff","children"),
    Output("hs-chart-smile","figure"),
    Input("hs-S","value"),  Input("hs-K","value"),  Input("hs-T","value"),
    Input("hs-r","value"),  Input("hs-q","value"),  Input("hs-v0","value"),
    Input("hs-kappa","value"), Input("hs-theta","value"),
    Input("hs-sigv","value"),  Input("hs-rho","value"),
    Input("hs-cp","value"),
)
def _hs_update(S, K, Tau, r, q, v0, kappa, theta, sigv, rho, cp):
    S, K, Tau, r, q, v0, kappa, theta, sigv, rho = map(
        float, (S, K, Tau, r, q, v0, kappa, theta, sigv, rho))
    try:
        hp = heston_price(S, K, Tau, r, q, v0, kappa, theta, sigv, rho, cp)
    except Exception as e:
        hp = float("nan")
    bs = bs_price(S, K, Tau, r, q, math.sqrt(max(v0, 1e-8)), cp)
    diff = hp - bs

    # Implied smile: reprice across strikes, invert to BS vol
    from models import implied_vol_bs
    Ks = np.linspace(S*0.75, S*1.25, 25)
    ivs = []
    for K_ in Ks:
        try:
            p = heston_price(S, K_, Tau, r, q, v0, kappa, theta, sigv, rho, "call")
            iv = implied_vol_bs(p, S, K_, Tau, r, q, "call")
        except Exception:
            iv = float("nan")
        ivs.append(iv)
    ivs = np.array(ivs)
    mask = ~np.isnan(ivs)
    fig = go.Figure()
    if mask.any():
        fig.add_trace(go.Scatter(x=Ks[mask], y=ivs[mask]*100, line=dict(color=T.ACCENT, width=2),
                                  name="Heston-implied σ"))
    fig.add_hline(y=math.sqrt(max(v0, 1e-8))*100,
                   line=dict(color=T.SUCCESS, dash="dot"),
                   annotation_text=f"√v₀ = {math.sqrt(max(v0, 1e-8))*100:.1f}%")
    fig.update_layout(**_dark_fig(), title="Heston → BS Implied Smile",
                       xaxis_title="Strike", yaxis_title="σ (%)", height=620)
    return (f"{hp:.4f}", f"{bs:.4f}", f"{diff:+.4f}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Variance swap
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("vs-kvar","children"), Output("vs-fvol","children"),
    Output("vs-avol","children"), Output("vs-premium","children"),
    Output("vs-chart-weights","figure"),
    Input("vs-S","value"), Input("vs-T","value"), Input("vs-r","value"),
    Input("vs-q","value"), Input("vs-atm","value"), Input("vs-skew","value"),
)
def _vs_update(S, Tau, r, q, atm, skew):
    S, Tau, r, q, atm, skew = map(float, (S, Tau, r, q, atm, skew))
    Ks = np.linspace(S*0.5, S*1.5, 81)
    ivs = atm + skew * (Ks - S)
    ivs = np.clip(ivs, 0.02, 2.0)
    kvar = variance_swap_fair_variance(S, Tau, r, q, Ks, ivs)
    fvol = math.sqrt(max(kvar, 0))
    premium = fvol - atm

    # Show replication weights 1/K²
    weights = 1.0 / (Ks * Ks)
    weights = weights / weights.max()   # normalised
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=Ks, y=weights, line=dict(color=T.ACCENT, width=2),
                              name="1/K² weight (norm)", yaxis="y1"))
    fig.add_trace(go.Scatter(x=Ks, y=ivs*100, line=dict(color=T.SUCCESS, dash="dot", width=2),
                              name="Input σ (%)", yaxis="y2"))
    fig.update_layout(
        **_dark_fig(),
        title="Var-Swap Replication Weights (1/K²) + Input Smile",
        xaxis_title="Strike",
        yaxis=dict(title="Norm weight", side="left"),
        yaxis2=dict(title="σ (%)", overlaying="y", side="right"),
        height=620,
    )
    return (f"{kvar:.4f}", f"{fvol:.2%}", f"{atm:.2%}", f"{premium:+.3%}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Spread (Margrabe + Kirk)
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("sp-marg","children"), Output("sp-kirk","children"),
    Output("sp-corrd","children"),
    Output("sp-chart-rho","figure"),
    Input("sp-S1","value"), Input("sp-S2","value"), Input("sp-K","value"),
    Input("sp-T","value"),  Input("sp-r","value"),
    Input("sp-s1","value"), Input("sp-s2","value"), Input("sp-rho","value"),
)
def _sp_update(S1, S2, K, Tau, r, s1, s2, rho):
    S1, S2, K, Tau, r, s1, s2, rho = map(float, (S1, S2, K, Tau, r, s1, s2, rho))
    marg = margrabe_exchange(S1, S2, Tau, s1, s2, rho)
    kirk = kirk_spread(S1, S2, K if abs(K) > 1e-6 else 1e-6, Tau, r, s1, s2, rho)
    # Correlation sensitivity dPrice/dρ (central FD)
    d_rho = 0.05
    k_up = kirk_spread(S1, S2, K if abs(K) > 1e-6 else 1e-6, Tau, r, s1, s2, min(rho + d_rho, 0.99))
    k_dn = kirk_spread(S1, S2, K if abs(K) > 1e-6 else 1e-6, Tau, r, s1, s2, max(rho - d_rho, -0.99))
    corr_d = (k_up - k_dn) / (2 * d_rho)

    rhos = np.linspace(-0.95, 0.95, 40)
    marg_l = [margrabe_exchange(S1, S2, Tau, s1, s2, rr) for rr in rhos]
    kirk_l = [kirk_spread(S1, S2, K if abs(K) > 1e-6 else 1e-6, Tau, r, s1, s2, rr) for rr in rhos]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rhos, y=marg_l, line=dict(color=T.SUCCESS), name="Margrabe (K=0)"))
    fig.add_trace(go.Scatter(x=rhos, y=kirk_l, line=dict(color=T.ACCENT),  name="Kirk"))
    fig.add_vline(x=rho, line=dict(color=T.WARNING, dash="dash"))
    fig.update_layout(**_dark_fig(), title="Spread Price vs Correlation ρ",
                       xaxis_title="ρ", yaxis_title="Price", height=620)
    return (f"{marg:.4f}", f"{kirk:.4f}", f"{corr_d:+.4f}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — Caps/Floors
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("cp-cap","children"),  Output("cp-floor","children"),
    Output("cp-diff","children"), Output("cp-n","children"),
    Output("cp-chart-ladder","figure"),
    Input("cp-strike","value"), Input("cp-tenor","value"),
    Input("cp-sigma","value"),  Input("cp-curve","value"),
    Input("cp-not","value"),    Input("cp-freq","value"),
)
def _cp_update(strike, tenor, sigma, base, notM, freq):
    strike, tenor, sigma, base = map(float, (strike, tenor, sigma, base))
    notional = float(notM) * 1_000_000
    freq = int(freq)
    curve = flat_curve(base)
    cap = cap_price(curve, strike, tenor, freq, sigma, notional)
    from models.caps import floor_price as _floor
    fl  = _floor(curve, strike, tenor, freq, sigma, notional)
    n_caplets = len(cap["caplet_prices"])

    fig = go.Figure()
    fig.add_trace(go.Bar(x=cap["caplet_times"], y=cap["caplet_prices"],
                          name="Caplet price", marker_color=T.ACCENT, opacity=0.7))
    fig.add_trace(go.Bar(x=fl["floorlet_times"], y=fl["floorlet_prices"],
                          name="Floorlet price", marker_color=T.SUCCESS, opacity=0.7))
    fig.update_layout(**_dark_fig(), title="Caplet / Floorlet Price Ladder",
                       xaxis_title="Expiry (y)", yaxis_title="Price",
                       barmode="group", height=620)
    return (f"{cap['total_price']:,.0f}", f"{fl['total_price']:,.0f}",
            f"{cap['total_price'] - fl['total_price']:+,.0f}", f"{n_caplets}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — European Swaption
# ═══════════════════════════════════════════════════════════════════════════

@callback(
    Output("sp2-price","children"), Output("sp2-fsr","children"),
    Output("sp2-ann","children"),   Output("sp2-vega","children"),
    Output("sp2-chart","figure"),
    Input("sp2-exp","value"),   Input("sp2-ten","value"),
    Input("sp2-K","value"),     Input("sp2-sig","value"),
    Input("sp2-curve","value"), Input("sp2-not","value"),
    Input("sp2-side","value"),
)
def _sp2_update(expiry, tenor, K, sig, base, notM, payer):
    expiry, tenor, K, sig, base = map(float, (expiry, tenor, K, sig, base))
    notional = float(notM) * 1_000_000
    curve = flat_curve(base)
    r = european_swaption(curve, expiry, tenor, K, sig, notional, freq=2, payer=bool(payer))
    # Vega via ±1% vol bump
    r_up = european_swaption(curve, expiry, tenor, K, sig + 0.01, notional, freq=2, payer=bool(payer))
    vega = r_up["price"] - r["price"]

    # Price vs strike
    Ks = np.linspace(max(base - 0.02, 0.001), base + 0.05, 40)
    prices = [european_swaption(curve, expiry, tenor, k_, sig, notional,
                                 freq=2, payer=bool(payer))["price"] for k_ in Ks]
    fig = go.Figure(go.Scatter(x=Ks*100, y=prices, line=dict(color=T.ACCENT)))
    fig.add_vline(x=K*100, line=dict(color=T.WARNING, dash="dash"),
                   annotation_text=f"K={K:.2%}")
    fig.add_vline(x=r["forward_swap_rate"]*100, line=dict(color=T.SUCCESS, dash="dot"),
                   annotation_text=f"F={r['forward_swap_rate']:.2%}")
    fig.update_layout(**_dark_fig(), title="Swaption Price vs Strike",
                       xaxis_title="Strike rate (%)", yaxis_title="Price ($)",
                       height=620)
    return (f"{r['price']:,.0f}", f"{r['forward_swap_rate']:.3%}",
            f"{r['annuity']:.4f}", f"{vega:,.0f}", fig)


# ═══════════════════════════════════════════════════════════════════════════
# Callbacks — DV01 Ladder (SOFR Futures + Treasury Bonds)
# ═══════════════════════════════════════════════════════════════════════════

@callback(Output("dv-table","data", allow_duplicate=True),
          Input("dv-add","n_clicks"),
          State("dv-table","data"),
          prevent_initial_call=True)
def _dv_add_row(n, data):
    if not n: return no_update
    data = list(data or [])
    data.append({"instrument":"New", "type":"treasury", "notional_M":10.0,
                 "tenor":5.0, "coupon":4.0, "position":1})
    return data


@callback(
    Output("dv-total","children"), Output("dv-sofr","children"),
    Output("dv-ust","children"),
    Output("dv-chart-ladder","figure"), Output("dv-chart-bucket","figure"),
    Input("dv-table","data"), Input("dv-curve","value"),
)
def _dv_update(data, base):
    if not data:
        empty = go.Figure().update_layout(**_dark_fig(), title="No data")
        return "—","—","—", empty, empty
    curve = flat_curve(float(base or 0.04))
    rows = []
    sofr_total = 0.0
    ust_total  = 0.0
    for row in data:
        try:
            name   = str(row.get("instrument", ""))
            typ    = str(row.get("type", "treasury"))
            notM   = float(row.get("notional_M") or 0)
            tenor  = float(row.get("tenor") or 0)
            coupon = float(row.get("coupon") or 0) / 100.0
            pos    = float(row.get("position") or 0)
        except Exception:
            continue
        if typ == "sofr_fut":
            # SOFR futures DV01 = $25 × notional_M × position per 1bp
            dv = 25.0 * notM * pos
            sofr_total += dv
        else:
            # Treasury: bond price on curve, parallel ±1bp
            try:
                p0 = bond_price_curve(curve,           notM * 1_000_000, coupon, 2, tenor)["pv"]
                p_up = bond_price_curve(curve.shift(+1), notM * 1_000_000, coupon, 2, tenor)["pv"]
                p_dn = bond_price_curve(curve.shift(-1), notM * 1_000_000, coupon, 2, tenor)["pv"]
                dv = (p_dn - p_up) / 2 * pos
            except Exception:
                dv = 0.0
            ust_total += dv
        rows.append({"name": name, "type": typ, "tenor": tenor, "dv01": dv})

    total = sofr_total + ust_total

    # Ladder chart: per-instrument DV01
    labels = [r["name"] for r in rows]
    dvs    = [r["dv01"] for r in rows]
    colors = [T.WARNING if r["type"] == "sofr_fut" else T.ACCENT for r in rows]
    fig_l = go.Figure(go.Bar(x=labels, y=dvs, marker_color=colors))
    fig_l.update_layout(**_dark_fig(), title="DV01 by Instrument ($ per 1bp)",
                         xaxis_title="", yaxis_title="DV01 ($)", height=620)

    # Bucket chart: DV01 grouped by tenor bucket
    buckets = [(0, 1, "0-1y"), (1, 3, "1-3y"), (3, 7, "3-7y"),
                (7, 15, "7-15y"), (15, 50, "15y+")]
    bucket_dvs = []
    bucket_labels = [b[2] for b in buckets]
    for lo, hi, _ in buckets:
        bdv = sum(r["dv01"] for r in rows if lo <= r["tenor"] < hi)
        bucket_dvs.append(bdv)
    fig_b = go.Figure(go.Bar(x=bucket_labels, y=bucket_dvs, marker_color=T.ACCENT))
    fig_b.update_layout(**_dark_fig(), title="DV01 by Tenor Bucket",
                         xaxis_title="Tenor bucket", yaxis_title="DV01 ($)", height=620)

    return (f"${total:,.0f}", f"${sofr_total:,.0f}", f"${ust_total:,.0f}",
            fig_l, fig_b)
