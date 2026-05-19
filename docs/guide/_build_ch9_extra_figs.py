"""
Standalone figure builder for Chapter 9 (Monte Carlo and Path-Dependent).

Run:  python docs/guide/_build_ch9_extra_figs.py

Outputs (under docs/guide/figures/):
    ch09-sqrt-n-error.png
    ch09-antithetic.png
    ch09-control-variate.png
    ch09-sobol-vs-pseudo.png
    ch09-bb-barrier.png            (Brownian Bridge barrier correction)
    ch09-bb-survival.png           (survival probability surface)
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
def fig_sqrt_n_error():
    """Empirical 1/sqrt(N) error of an MC estimator."""
    np.random.seed(0)
    # Estimate E[Z^2] = 1 for standard normal
    Ns = np.logspace(2, 6, 12).astype(int)
    n_repeats = 200
    sds = []
    for N in Ns:
        ests = []
        for _ in range(n_repeats):
            Z = np.random.standard_normal(N)
            ests.append(np.mean(Z ** 2))
        sds.append(np.std(ests))
    sds = np.array(sds)

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.loglog(Ns, sds, "o-", color="#1e3a8a", lw=2, ms=7,
              label="empirical SD across runs")
    # Theoretical: SE = sqrt(Var(Z^2))/sqrt(N) = sqrt(2)/sqrt(N)
    ax.loglog(Ns, np.sqrt(2) / np.sqrt(Ns), color="#c2410c", lw=2, ls="--",
              label=r"theory $\sqrt{2}/\sqrt{N}$")
    ax.set_xlabel("$N$ sample size")
    ax.set_ylabel("std. dev. of estimator")
    ax.set_title(r"Monte-Carlo error scales as $1/\sqrt{N}$ — dimension-free, the basic justification for MC pricing of high-D baskets")
    ax.legend(loc="upper right", frameon=False, fontsize=10)
    _save("ch09-sqrt-n-error.png")


# ---------------------------------------------------------------------
def fig_antithetic():
    """Compare plain MC vs antithetic MC for an ATM call."""
    np.random.seed(0)
    S0 = 100.0
    K = 100.0
    r = 0.05
    sigma = 0.2
    T = 1.0
    # BS price
    d1 = (np.log(S0 / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    from math import erf, sqrt
    def Phi(x): return 0.5 * (1 + erf(x / sqrt(2)))
    bs_price = S0 * Phi(d1) - K * np.exp(-r * T) * Phi(d2)

    Ns = np.logspace(2.0, 4.5, 12).astype(int)
    n_repeats = 80
    plain_sds = []
    anti_sds = []
    for N in Ns:
        plain_ests = []
        anti_ests = []
        for _ in range(n_repeats):
            Z = np.random.standard_normal(N)
            ST = S0 * np.exp((r - 0.5 * sigma ** 2) * T + sigma * np.sqrt(T) * Z)
            plain_ests.append(np.exp(-r * T) * np.mean(np.maximum(ST - K, 0)))
            ST_neg = S0 * np.exp((r - 0.5 * sigma ** 2) * T + sigma * np.sqrt(T) * (-Z))
            payoff_pair = 0.5 * (np.maximum(ST - K, 0) + np.maximum(ST_neg - K, 0))
            anti_ests.append(np.exp(-r * T) * np.mean(payoff_pair))
        plain_sds.append(np.std(plain_ests))
        anti_sds.append(np.std(anti_ests))
    plain_sds = np.array(plain_sds)
    anti_sds = np.array(anti_sds)

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.loglog(Ns, plain_sds, "o-", color="#1e3a8a", lw=2, ms=7,
              label="plain MC")
    ax.loglog(Ns, anti_sds, "s-", color="#c2410c", lw=2, ms=7,
              label="antithetic MC")
    ax.set_xlabel("$N$ paths (equal compute basis)")
    ax.set_ylabel("std. dev. of price estimate")
    ax.set_title(f"Antithetic variates on an ATM call (BS = {bs_price:.3f}): SE roughly halves at equal cost\n"
                 f"Same trick every Heston/local-vol MC pricer uses to cut overnight risk-run time by 2-3x")
    ax.legend(loc="upper right", frameon=False, fontsize=10)
    _save("ch09-antithetic.png")


# ---------------------------------------------------------------------
def fig_control_variate():
    """Control-variate reduction for Asian call using geometric Asian as control."""
    np.random.seed(0)
    S0 = 100.0
    K = 100.0
    r = 0.05
    sigma = 0.3
    T = 1.0
    n_obs = 50

    Ns = np.array([200, 500, 1000, 2000, 5000, 10000])
    n_repeats = 40
    plain_sds = []
    cv_sds = []

    for N in Ns:
        plain_ests = []
        cv_ests = []
        for _ in range(n_repeats):
            dt = T / n_obs
            Z = np.random.standard_normal((N, n_obs))
            log_steps = (r - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * Z
            log_paths = np.cumsum(log_steps, axis=1)
            log_S = np.log(S0) + log_paths
            S = np.exp(log_S)
            arith_avg = np.mean(S, axis=1)
            geom_avg = np.exp(np.mean(log_S, axis=1))
            arith_payoff = np.exp(-r * T) * np.maximum(arith_avg - K, 0)
            geom_payoff = np.exp(-r * T) * np.maximum(geom_avg - K, 0)

            plain_ests.append(np.mean(arith_payoff))

            # Compute geometric-Asian closed form (Kemna-Vorst):
            # sigma_g = sigma * sqrt((2n+1)/(6(n+1)))
            # mu_g = (r - sigma^2/6)*(T/2)*(1 - 1/n) approx; use standard formula
            n = n_obs
            sigma_g = sigma * np.sqrt((2 * n + 1) / (6 * (n + 1)))
            mu_g = (r - 0.5 * sigma ** 2) * (n + 1) / (2 * n) + 0.5 * sigma_g ** 2
            d1g = (np.log(S0 / K) + (mu_g + 0.5 * sigma_g ** 2) * T) / (sigma_g * np.sqrt(T))
            d2g = d1g - sigma_g * np.sqrt(T)
            from math import erf, sqrt
            def Phi(x): return 0.5 * (1 + erf(x / sqrt(2)))
            geom_closed = np.exp(-r * T) * (S0 * np.exp(mu_g * T) * Phi(d1g) - K * Phi(d2g))

            # Control variate: arith - beta * (geom - geom_closed)
            cov_ag = np.cov(arith_payoff, geom_payoff)[0, 1]
            var_g = np.var(geom_payoff)
            beta = cov_ag / max(var_g, 1e-12)
            cv_ests.append(np.mean(arith_payoff) - beta * (np.mean(geom_payoff) - geom_closed))
        plain_sds.append(np.std(plain_ests))
        cv_sds.append(np.std(cv_ests))

    plain_sds = np.array(plain_sds)
    cv_sds = np.array(cv_sds)

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.loglog(Ns, plain_sds, "o-", color="#1e3a8a", lw=2, ms=7,
              label="plain MC")
    ax.loglog(Ns, cv_sds, "s-", color="#16a34a", lw=2, ms=7,
              label="geometric-Asian control variate")
    ax.set_xlabel("$N$ paths")
    ax.set_ylabel("std. dev. of price estimate")
    ax.set_title("Control-variate variance reduction for arithmetic-Asian call\n"
                 "Same Vorst-1992 trick airlines use to price quarterly jet-fuel Asian options under bid-ask spread tolerance")
    ax.legend(loc="upper right", frameon=False, fontsize=10)
    _save("ch09-control-variate.png")


# ---------------------------------------------------------------------
def fig_sobol_vs_pseudo():
    """Sobol low-discrepancy vs pseudo-random uniform-in-unit-square."""
    np.random.seed(0)
    N = 256

    # Pseudo-random
    pseudo = np.random.uniform(0, 1, (N, 2))

    # Sobol (try scipy, otherwise fallback simple sequence)
    try:
        from scipy.stats import qmc
        sampler = qmc.Sobol(d=2, scramble=False, seed=0)
        sobol = sampler.random(N)
    except Exception:
        # Van der Corput / Halton fallback for 2D
        def vdc(n, b):
            q = 0.0
            denom = 1.0
            while n > 0:
                denom *= b
                q += (n % b) / denom
                n //= b
            return q
        sobol = np.array([(vdc(i + 1, 2), vdc(i + 1, 3)) for i in range(N)])

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    ax = axes[0]
    ax.scatter(pseudo[:, 0], pseudo[:, 1], s=10, color="#1e3a8a", alpha=0.75)
    ax.set_title(f"Pseudo-random ({N} draws)")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    ax = axes[1]
    ax.scatter(sobol[:, 0], sobol[:, 1], s=10, color="#c2410c", alpha=0.75)
    ax.set_title(f"Sobol low-discrepancy ({N} draws)")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    fig.suptitle("Sobol fills the unit square more uniformly than pseudo-random for the same $N$ — visible as fewer gaps and clusters.\nProduction MC pricers use Sobol for moderate-D integration; gains erode above $d \\approx 20$",
                 fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    _save("ch09-sobol-vs-pseudo.png")


# ---------------------------------------------------------------------
def fig_bb_barrier():
    """Brownian-Bridge barrier-option continuity correction: daily-close path
    that 'survives' the daily check but continuous path that breached."""
    np.random.seed(2)
    S0 = 100.0
    H = 110.0  # up-and-out barrier
    sigma = 0.25
    r = 0.05
    T = 0.5

    # Generate one fine GBM path (intra-day), sub-sample daily
    n_fine = 1000
    dt_fine = T / n_fine
    Z = np.random.standard_normal(n_fine)
    logS = np.log(S0) + np.cumsum((r - 0.5 * sigma ** 2) * dt_fine + sigma * np.sqrt(dt_fine) * Z)
    S_fine = np.concatenate(([S0], np.exp(logS)))
    t_fine = np.linspace(0, T, n_fine + 1)

    # Daily sample (about 1 obs every 8 fine steps so 125 daily) — choose smaller
    n_daily = 25
    daily_idx = np.linspace(0, n_fine, n_daily + 1).astype(int)
    t_daily = t_fine[daily_idx]
    S_daily = S_fine[daily_idx]

    # Check: does daily path "see" H?
    daily_max = S_daily.max()
    fine_max = S_fine.max()

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(t_fine, S_fine, color="#94a3b8", lw=0.8, alpha=0.7,
            label="continuous-time path")
    ax.plot(t_daily, S_daily, "o-", color="#1e3a8a", lw=1.8, ms=6,
            label=f"daily-close path ($N={n_daily}$ obs)")
    ax.axhline(H, color="#dc2626", ls="--", lw=2,
               label=f"barrier $H={H:.0f}$")
    # Annotate violation
    if fine_max >= H and daily_max < H:
        idx = int(np.argmax(S_fine))
        ax.scatter([t_fine[idx]], [S_fine[idx]], color="#dc2626", s=120, zorder=5,
                   label=f"continuous max = {fine_max:.2f} (breached)")
        ax.annotate(
            "barrier breached\nbetween daily closes —\nBrownian Bridge survival\nprobability $< 1$",
            xy=(t_fine[idx], S_fine[idx]),
            xytext=(t_fine[idx] + 0.05, S_fine[idx] + 1.5),
            fontsize=9, color="#7f1d1d",
            arrowprops=dict(arrowstyle="->", color="#7f1d1d"))
    ax.set_xlabel("$t$ (years)")
    ax.set_ylabel("$S_t$")
    ax.set_title("Brownian-Bridge barrier correction: daily-close monitoring misses an intraday breach.\n"
                 "Real-world use: SPX knock-out options where intraday touches of 4500 do *not* show in EOD closes — bridge correction is the standard fix")
    ax.legend(loc="lower left", frameon=False, fontsize=9)
    _save("ch09-bb-barrier.png")


# ---------------------------------------------------------------------
def fig_bb_survival():
    """Bridge survival probability as function of (S_i, S_{i+1}) given barrier H."""
    np.random.seed(0)
    H = 110.0
    sigma = 0.25
    dt = 1 / 252  # one trading day

    # Grid of (S_i, S_{i+1})
    grid = np.linspace(90, 109, 80)
    Si, Sj = np.meshgrid(grid, grid)

    with np.errstate(divide="ignore", invalid="ignore"):
        log_ratio_i = np.log(H / Si)
        log_ratio_j = np.log(H / Sj)
        # Bridge crossing-probability formula (9.32) from the chapter
        prob_cross = np.exp(-2 * log_ratio_i * log_ratio_j / (sigma ** 2 * dt))
        prob_cross = np.where((Si >= H) | (Sj >= H), 1.0, prob_cross)
    survival = 1 - prob_cross

    fig, ax = plt.subplots(figsize=FIGSIZE)
    cs = ax.contourf(Si, Sj, survival, levels=np.linspace(0.5, 1.0, 11),
                     cmap="viridis")
    ax.contour(Si, Sj, survival, levels=[0.95, 0.99, 0.999],
               colors="white", linewidths=1.2)
    ax.set_xlabel("$S_i$ (start of interval)")
    ax.set_ylabel(r"$S_{i+1}$ (end of interval)")
    ax.set_title(r"Conditional bridge survival probability $\mathbb{P}(\max_{[t_i, t_{i+1}]} S < H \mid S_i, S_{i+1})$" +
                 f"\nbarrier $H={H:.0f}$, $\\sigma$={sigma*100:.0f}%, $\\Delta t = 1/252$. Used to correct daily-grid MC barrier prices in production")
    cbar = plt.colorbar(cs, ax=ax)
    cbar.set_label("survival probability")
    _save("ch09-bb-survival.png")


# ---------------------------------------------------------------------
def fig_reflection_principle():
    """A Brownian path that touches level u at time tau, plus its reflection
    after tau across y=u. Visualises §9.7.2 — the one-to-one correspondence
    between "touched u, ended below u" and "ended above u".
    """
    np.random.seed(7)
    T = 1.0
    N = 1000
    dt = T / N
    times = np.linspace(0.0, T, N + 1)
    u = 1.0   # barrier level

    # Sample a Brownian path that DOES cross u and ENDS below u — we draw paths
    # until we find one with that signature, so the figure is unambiguous.
    while True:
        z = np.random.standard_normal(N)
        W = np.concatenate([[0.0], np.cumsum(z) * np.sqrt(dt)])
        crosses = (W >= u).any()
        ends_below = W[-1] < u
        if crosses and ends_below and W[-1] > -1.5 and W[-1] < u - 0.05:
            break

    # First-hit time index tau_idx (first index where W >= u)
    tau_idx = int(np.argmax(W >= u))

    # Reflected path: same on [0, tau], mirror across u on (tau, T]
    W_refl = W.copy()
    W_refl[tau_idx:] = 2 * u - W[tau_idx:]

    fig, ax = plt.subplots(figsize=(9.5, 5.5))

    # Pre-hit segment shared by both paths
    ax.plot(times[: tau_idx + 1], W[: tau_idx + 1],
            color="#1e3a8a", lw=1.7, label="Original path $W_t$")
    # Original continues below
    ax.plot(times[tau_idx:], W[tau_idx:], color="#1e3a8a", lw=1.7)
    # Reflected continues above
    ax.plot(times[tau_idx:], W_refl[tau_idx:],
            color="#7f7f7f", lw=1.7, linestyle="--",
            label=r"Reflected path (mirror of $W_t$ across $y=u$ for $t>\tau$)")

    # Barrier and first-hit markers
    ax.axhline(u, color="#c2410c", lw=1.4, linestyle=":")
    ax.text(0.02, u + 0.04, "$u$", color="#c2410c", fontsize=12, fontweight="bold")
    ax.axvline(times[tau_idx], color="#999999", lw=0.8, linestyle="--", alpha=0.6)
    ax.text(times[tau_idx] + 0.01, ax.get_ylim()[0] + 0.15, r"$\tau$", fontsize=11)
    ax.scatter([times[tau_idx]], [u], color="#c2410c", s=55, zorder=5,
               label=r"First-hit $\tau$ of level $u$")

    # End-point markers
    ax.scatter([T], [W[-1]],      color="#1e3a8a", s=55, zorder=5)
    ax.scatter([T], [W_refl[-1]], color="#7f7f7f", s=55, zorder=5,
               facecolors="none", edgecolors="#7f7f7f", linewidths=1.7)

    ax.set_xlabel("$t$")
    ax.set_ylabel(r"$W_t$")
    ax.set_xlim(0, T)
    ax.set_title(
        "Reflection principle: every path that touches $u$ and ends below $u$ pairs one-to-one\n"
        r"with a reflected path that ends above $u$. Both are equally likely.  $\Rightarrow\;\mathbb{P}(M_T\geq u)=2\,\mathbb{P}(W_T\geq u)$",
        fontsize=11,
    )
    ax.legend(loc="lower left", fontsize=9.5, framealpha=0.95)
    fig.tight_layout()
    _save("ch09-reflection-principle.png")


# ---------------------------------------------------------------------
if __name__ == "__main__":
    fig_sqrt_n_error()
    fig_antithetic()
    fig_control_variate()
    fig_sobol_vs_pseudo()
    fig_bb_barrier()
    fig_bb_survival()
    fig_reflection_principle()
    print("Chapter 9 extras: done")
