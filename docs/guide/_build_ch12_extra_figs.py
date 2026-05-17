"""
Standalone figure builder for Chapter 12 (Short-Rate Models).

Run:  python docs/guide/_build_ch12_extra_figs.py

Outputs (under docs/guide/figures/):
    ch12-vasicek-vs-cir.png
    ch12-mean-reversion-speeds.png
    ch12-cir-zero-boundary.png
    ch12-hw-theta-fit.png
    ch12-bond-vs-rate.png
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
def fig_vasicek_vs_cir():
    """Side-by-side Vasicek and CIR sample paths under identical (kappa, theta)."""
    np.random.seed(0)
    kappa = 0.5
    theta = 0.04
    sigma_v = 0.015          # Vasicek absolute vol
    sigma_c = 0.075          # CIR coefficient
    r0 = 0.02
    T = 10.0
    N = 2000
    dt = T / N
    t = np.linspace(0, T, N + 1)

    n_paths = 5
    vas = np.zeros((n_paths, N + 1))
    cir = np.zeros((n_paths, N + 1))
    vas[:, 0] = r0
    cir[:, 0] = r0
    for i in range(N):
        Z = np.random.standard_normal(n_paths)
        vas[:, i + 1] = vas[:, i] + kappa * (theta - vas[:, i]) * dt + sigma_v * np.sqrt(dt) * Z
        r_pos = np.maximum(cir[:, i], 0)
        cir[:, i + 1] = cir[:, i] + kappa * (theta - r_pos) * dt + sigma_c * np.sqrt(r_pos) * np.sqrt(dt) * Z

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.5), sharey=True)
    ax = axes[0]
    for p in range(n_paths):
        ax.plot(t, vas[p], lw=1.3, alpha=0.85)
    ax.axhline(theta, color="black", ls="--", lw=1.4,
               label=fr"$\theta={theta}$")
    ax.axhline(0, color="#dc2626", lw=0.7, alpha=0.6)
    ax.set_xlabel("$t$ (years)")
    ax.set_ylabel(r"$r_t$")
    ax.set_title(r"Vasicek: $\mathrm{d}r = \kappa(\theta - r)\mathrm{d}t + \sigma\,\mathrm{d}W$")
    ax.legend(loc="upper right", frameon=False, fontsize=9)

    ax = axes[1]
    for p in range(n_paths):
        ax.plot(t, cir[p], lw=1.3, alpha=0.85)
    ax.axhline(theta, color="black", ls="--", lw=1.4,
               label=fr"$\theta={theta}$")
    ax.axhline(0, color="#dc2626", lw=0.7, alpha=0.6,
               label="$r=0$ (CIR floor)")
    ax.set_xlabel("$t$ (years)")
    ax.set_title(r"CIR: $\mathrm{d}r = \kappa(\theta - r)\mathrm{d}t + \sigma\sqrt{r}\,\mathrm{d}W$")
    ax.legend(loc="upper right", frameon=False, fontsize=9)

    fig.suptitle(
        "Vasicek (Gaussian) admits negative rates; CIR (square-root) is non-negative\n"
        r"The 2022-24 Fed-funds hiking cycle traced a Vasicek-like reversion to a moving $\theta$",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    _save("ch12-vasicek-vs-cir.png")


# ---------------------------------------------------------------------
def fig_mean_reversion_speeds():
    """Deterministic relaxation under three kappa values."""
    np.random.seed(0)
    theta = 0.04
    r0 = 0.08
    t = np.linspace(0, 10, 400)

    fig, ax = plt.subplots(figsize=FIGSIZE)
    kappas = [0.1, 0.5, 2.0]
    colors = ["#1e3a8a", "#16a34a", "#c2410c"]
    for kappa, c in zip(kappas, colors):
        path = r0 * np.exp(-kappa * t) + theta * (1 - np.exp(-kappa * t))
        half_life = np.log(2) / kappa
        ax.plot(t, path, color=c, lw=2.2,
                label=fr"$\kappa={kappa}$  (half-life $={half_life:.2f}$y)")
    ax.axhline(theta, color="black", ls="--", lw=1.2,
               label=fr"$\theta = {theta}$")
    ax.scatter([0], [r0], color="black", s=70, zorder=5)
    ax.set_xlabel("$t$ (years)")
    ax.set_ylabel(r"$\mathbb{E}[r_t]$")
    ax.set_title(r"Deterministic mean-reversion under Vasicek: $r_0 e^{-\kappa t} + \theta(1 - e^{-\kappa t})$" +
                 "\nLarger $\\kappa \\Rightarrow$ faster pull to $\\theta$ — Fed-funds rates revert with $\\kappa \\sim 0.3$ (half-life 2.3y) in calm regimes")
    ax.legend(loc="upper right", frameon=False, fontsize=10)
    _save("ch12-mean-reversion-speeds.png")


# ---------------------------------------------------------------------
def fig_cir_zero_boundary():
    """Long-run CIR density (gamma) under Feller satisfied vs violated."""
    from scipy.stats import gamma as gamma_dist

    kappa = 0.5
    theta = 0.04
    # Stationary gamma: shape = 2 kappa theta / sigma^2, scale = sigma^2 / (2 kappa)
    sigmas = [0.05, 0.10, 0.30]
    labels = []
    for s in sigmas:
        feller = 2 * kappa * theta - s ** 2
        labels.append(("OK" if feller > 0 else "VIOLATED",
                       f"$\\sigma={s}$",
                       f"$2\\kappa\\theta - \\sigma^2 = {feller:+.3f}$"))

    fig, ax = plt.subplots(figsize=FIGSIZE)
    x = np.linspace(0.0001, 0.15, 800)
    colors = ["#1e3a8a", "#16a34a", "#c2410c"]
    for (status, label_s, feller_str), s, c in zip(labels, sigmas, colors):
        shape = 2 * kappa * theta / s ** 2
        scale = s ** 2 / (2 * kappa)
        pdf = gamma_dist.pdf(x, a=shape, scale=scale)
        ax.plot(x, pdf, color=c, lw=2.2,
                label=fr"{label_s}  (Feller {status})  {feller_str}")
    ax.set_xlabel("$r$ (rate level)")
    ax.set_ylabel("stationary density")
    ax.set_title(r"CIR stationary density: when $2\kappa\theta > \sigma^2$ (Feller), density is bounded at $0$" +
                 "\nWhen violated, density diverges integrably at $0$ — corporate-credit hazard-rate models often live at the boundary")
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    ax.set_xlim(0, 0.15)
    _save("ch12-cir-zero-boundary.png")


# ---------------------------------------------------------------------
def fig_hw_theta_fit():
    """Hull-White theta(t) reverse-engineered to fit a synthetic forward curve."""
    np.random.seed(0)
    kappa = 0.15
    sigma = 0.012
    T_grid = np.linspace(0, 30, 400)
    # Monotone synthetic forward curve so theta - f isolates the (always
    # positive) convexity correction rather than the oscillating f'/kappa.
    fwd = 0.025 + 0.025 * (1 - np.exp(-T_grid / 6))
    f_prime = np.gradient(fwd, T_grid)
    convex = (sigma ** 2 / (2 * kappa ** 2)) * (1 - np.exp(-2 * kappa * T_grid))
    theta_t = f_prime / kappa + fwd + convex

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(T_grid, fwd * 100, color="#1e3a8a", lw=2, label=r"market forward $f(0, t)$ (%)")
    ax.plot(T_grid, theta_t * 100, color="#c2410c", lw=2,
            label=r"calibrated $\theta(t)$ (%)")
    # Shade *only* the pure convexity correction sitting on top of f(0,t).
    ax.fill_between(T_grid, fwd * 100, (fwd + convex) * 100,
                    color="#fde68a", alpha=0.55,
                    label=r"convexity $\frac{\sigma^2}{2\kappa^2}(1 - e^{-2\kappa t})$")
    ax.set_xlabel("$t$ (years)")
    ax.set_ylabel("rate (%)")
    ax.set_title(r"Hull-White $\theta(t) = f(0,t) + f'(0,t)/\kappa + \frac{\sigma^2}{2\kappa^2}(1-e^{-2\kappa t})$" +
                 "\nThe shaded convexity term is the always-positive piece; every fixed-income desk's HW bootstrap implements it daily")
    # Legend at lower-right keeps it clear of both the converging-curves region
    # and the shaded convexity band that sits in the upper portion of the axes.
    ax.legend(loc="lower right", frameon=True, framealpha=0.92, fontsize=9)
    _save("ch12-hw-theta-fit.png")


# ---------------------------------------------------------------------
def fig_bond_vs_rate():
    """Vasicek zero-coupon bond price as a function of (r_t, T-t)."""
    kappa = 0.3
    theta = 0.04
    sigma = 0.012
    r_grid = np.linspace(0.0, 0.10, 200)

    fig, ax = plt.subplots(figsize=FIGSIZE)
    tenors = [1, 3, 5, 10, 20]
    colors = ["#1e3a8a", "#0891b2", "#16a34a", "#ca8a04", "#c2410c"]
    for tau, c in zip(tenors, colors):
        B = (1 - np.exp(-kappa * tau)) / kappa
        A = (theta - sigma ** 2 / (2 * kappa ** 2)) * (B - tau) - (sigma ** 2 / (4 * kappa)) * B ** 2
        prices = np.exp(A - B * r_grid)
        ax.plot(r_grid * 100, prices, color=c, lw=2.2,
                label=fr"$\tau = {tau}$y  (slope $= -B = -{B:.2f}$)")
    ax.set_xlabel("short rate $r$ (%)")
    ax.set_ylabel("zero-coupon bond price $P(r, \\tau)$")
    ax.set_title(r"Vasicek zero-coupon bond price $P = e^{A - B r}$ versus short-rate level $r$" +
                 "\nSlope at $r$ is exactly the bond's duration $B$ — every fixed-income desk's DV01 readout traces back to this curve")
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    _save("ch12-bond-vs-rate.png")


# ---------------------------------------------------------------------
if __name__ == "__main__":
    fig_vasicek_vs_cir()
    fig_mean_reversion_speeds()
    fig_cir_zero_boundary()
    fig_hw_theta_fit()
    fig_bond_vs_rate()
    print("Chapter 12 extras: done")
