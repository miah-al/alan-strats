"""
Standalone figure builder for Chapter 13 (Rate-Derivative Applications).

Run:  python docs/guide/_build_ch13_extra_figs.py

Outputs (under docs/guide/figures/):
    ch13-swap-leg-decomposition.png
    ch13-callable-negative-convexity.png
    ch13-cds-leg-balance.png
    ch13-convexity-adjustment.png
"""
from __future__ import annotations
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIG = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG, exist_ok=True)
DPI = 200
FIGSIZE = (8, 5)

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 11,
})


def _save(name):
    path = os.path.join(FIG, name)
    plt.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {name}")


# ---------------------------------------------------------------------
def fig_swap_leg_decomposition():
    """Fixed leg vs floating leg cashflows for a 5-year semi swap."""
    np.random.seed(0)
    n_years = 5
    freq = 2  # semi-annual
    n_pay = n_years * freq
    dt_arr = np.array([1.0 / freq] * n_pay)
    t_pay = np.cumsum(dt_arr)

    # Synthetic upward-sloping forward curve
    fwd = 0.025 + 0.005 * t_pay
    par_swap_rate = 0.0335
    # Fixed coupon
    fixed = par_swap_rate * dt_arr
    floating = fwd * dt_arr  # Expected (forward) floating leg

    fig, ax = plt.subplots(figsize=(10, 5))
    width = 0.18
    ax.bar(t_pay - width / 2, fixed * 100, width=width,
           color="#1e3a8a", label=f"fixed coupon ({par_swap_rate:.2%})")
    ax.bar(t_pay + width / 2, floating * 100, width=width,
           color="#c2410c", label="floating coupon (forward-implied)")
    ax.axhline(par_swap_rate * 0.5 * 100, color="#1e3a8a", ls="--", lw=1, alpha=0.5)
    ax.set_xlabel("payment date (years)")
    ax.set_ylabel("coupon (% of notional, half-year)")
    ax.set_title(r"5-year semi-annual IRS leg decomposition under an upward-sloping curve" +
                 "\nAt inception the par swap rate balances the two PV streams — same arithmetic SOFR-IRS desks run every morning")
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    _save("ch13-swap-leg-decomposition.png")


# ---------------------------------------------------------------------
def fig_callable_negative_convexity():
    """Callable bond vs straight bond price vs rate level."""
    np.random.seed(0)
    r_grid = np.linspace(0.005, 0.10, 200)
    # Straight bond: 5-yr 5% coupon
    coupon = 0.05
    T = 5
    cashflows = np.array([coupon] * (T - 1) + [1.0 + coupon])
    times = np.arange(1, T + 1)
    straight = np.array([np.sum(cashflows * np.exp(-r * times)) for r in r_grid])
    # Embedded call: dealer can call at par after year 3 if rates drop
    # Approximate call value as a smooth max-style cap
    call_strike = 1.02  # call price at 102
    # Call option crude proxy: scaled positive (B_straight - call_strike)
    call_value = np.maximum(straight - call_strike, 0) * 0.8
    callable_bond = straight - call_value

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(r_grid * 100, straight, color="#1e3a8a", lw=2.2,
            label="straight bond")
    ax.plot(r_grid * 100, callable_bond, color="#c2410c", lw=2.2,
            label="callable bond")
    ax.fill_between(r_grid * 100, callable_bond, straight,
                    color="#fde68a", alpha=0.5, label="embedded call (issuer's option)")
    ax.axvline(coupon * 100, color="gray", lw=0.7, ls="--", alpha=0.7)
    ax.text(coupon * 100 + 0.1, 0.92, "coupon level", fontsize=9, color="gray")
    ax.set_xlabel("rate level $r$ (%)")
    ax.set_ylabel("bond price (per unit face)")
    ax.set_title(r"Callable bond's *negative convexity*: price flattens in low-rate regime as the embedded call bites" +
                 "\nSame curve every MBS portfolio manager sees — extension risk in rising rates, prepayment in falling")
    ax.legend(loc="upper right", frameon=False, fontsize=10)
    _save("ch13-callable-negative-convexity.png")


# ---------------------------------------------------------------------
def fig_cds_leg_balance():
    """CDS premium leg (fixed running coupon) vs default leg as functions of
    market-implied intensity. Mimics the post-2009 ISDA Standard Model: the
    running coupon is contractual (100 or 500 bp), the market quotes the
    upfront. The two legs cross at the par intensity lambda* = S_run/(1-R),
    where upfront = 0. Above that, default-leg PV exceeds premium-leg PV and
    the *buyer* pays an upfront; below, the *seller* pays."""
    np.random.seed(0)
    T = 5.0
    R = 0.4
    r = 0.03
    S_run = 0.01  # 100 bp fixed running coupon (standard ISDA contract)
    lambdas = np.linspace(0.0005, 0.05, 400)  # implied intensity 5bp - 500bp

    # Annuity factor under (r + lambda) discount
    annuity = (1 - np.exp(-(r + lambdas) * T)) / (r + lambdas)
    prem = S_run * annuity                       # fixed-coupon premium leg
    deflt = (1 - R) * lambdas * annuity          # default leg
    # Par intensity (legs cross)
    lambda_par = S_run / (1 - R)
    par_spread_bps = S_run * 10000               # equivalent par spread

    fig, ax = plt.subplots(figsize=FIGSIZE)
    spreads_bps = lambdas * (1 - R) * 10000      # x-axis: equivalent par spread
    ax.plot(spreads_bps, prem * 100, color="#1e3a8a", lw=2.2,
            label=f"premium leg PV ({S_run*10000:.0f}bp fixed running)")
    ax.plot(spreads_bps, deflt * 100, color="#c2410c", lw=2.2,
            label="default leg PV")
    ax.fill_between(spreads_bps, prem * 100, deflt * 100,
                    where=(deflt > prem), color="#fee2e2", alpha=0.5,
                    label="upfront (buyer pays)")
    ax.fill_between(spreads_bps, prem * 100, deflt * 100,
                    where=(deflt <= prem), color="#dbeafe", alpha=0.5,
                    label="upfront (seller pays)")
    ax.axvline(par_spread_bps, color="black", ls="--", lw=1, alpha=0.6)
    ax.annotate(f"par crossover\n$S_{{par}} = (1-R)\\lambda^* = {par_spread_bps:.0f}$bp",
                xy=(par_spread_bps, np.interp(par_spread_bps, spreads_bps, prem * 100)),
                xytext=(par_spread_bps + 60, 2.5),
                fontsize=9, ha="left",
                arrowprops=dict(arrowstyle="->", color="black", lw=0.8))
    ax.set_xlabel("equivalent par spread $S_{par}=(1-R)\\lambda$ (bps)")
    ax.set_ylabel("PV (% of notional)")
    ax.set_title(f"CDS legs under a fixed {S_run*10000:.0f}bp running coupon ($T={T:.0f}$y, $R$={R*100:.0f}%)\n"
                 f"Post-2009 ISDA contracts fix the coupon; the *upfront* makes the trade fair when market $\\lambda \\neq \\lambda^*$")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    _save("ch13-cds-leg-balance.png")


# ---------------------------------------------------------------------
def fig_convexity_adjustment():
    """Convexity adjustment between forward rate and expected future spot rate."""
    np.random.seed(0)
    kappa = 0.15
    sigma = 0.008   # calibrated to put the asymptote in the empirical 5-15bp ED-vs-swap band
    Ts = np.linspace(0.25, 30, 120)

    # Vasicek convexity gap between Q-measure E[r_T] and T-forward E[r_T]:
    #   gap(T) = (sigma^2 / (2 kappa^2)) (1 - exp(-2 kappa T))
    # The Eurodollar-futures-vs-forward-swap convexity has the same functional
    # form modulated by an extra B(T_f, T_2)^2 factor, hence the empirical band.
    convex = (sigma ** 2 / (2 * kappa ** 2)) * (1 - np.exp(-2 * kappa * Ts))

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(Ts, convex * 10000, color="#1e3a8a", lw=2.2,
            label=r"Vasicek gap $\frac{\sigma^2}{2\kappa^2}(1-e^{-2\kappa T})$ ($\sigma$=0.008, $\kappa$=0.15)")
    ax.axhspan(5, 15, color="#fef3c7", alpha=0.55, zorder=0,
               label="empirical ED-vs-swap band (5-15 bp)")
    ax.set_xlabel("maturity $T$ (years)")
    ax.set_ylabel("convexity adjustment (bp)")
    ax.set_title(r"Vasicek convexity gap: $\mathbb{E}^Q[r_T] - \mathbb{E}^{T\text{-fwd}}[r_T]$ grows with $T$" +
                 "\nSame functional form as the Eurodollar-futures-vs-forward-swap convexity adjustment (5-15 bp empirically)")
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    ax.set_xlim(0, 30)
    ax.set_ylim(0, max(max(convex * 10000) * 1.15, 18))
    _save("ch13-convexity-adjustment.png")


# ---------------------------------------------------------------------
if __name__ == "__main__":
    fig_swap_leg_decomposition()
    fig_callable_negative_convexity()
    fig_cds_leg_balance()
    fig_convexity_adjustment()
    print("Chapter 13 extras: done")
