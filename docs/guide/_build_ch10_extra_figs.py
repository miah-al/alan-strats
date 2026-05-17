"""
Standalone figure builder for Chapter 10 (Heston Model).

Run:  python docs/guide/_build_ch10_extra_figs.py

Outputs (under docs/guide/figures/):
    ch10-variance-paths-kappa.png
    ch10-charfunc-realimag.png
    ch10-smile-vs-rho.png
    ch10-smile-vs-volvol.png
    ch10-atm-term-structure.png
    ch10-feller-phase.png
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


def _simulate_cir(v0, kappa, theta, alpha, T, N, n_paths, seed=0):
    """Full-truncation Euler for CIR variance."""
    np.random.seed(seed)
    dt = T / N
    v = np.zeros((n_paths, N + 1))
    v[:, 0] = v0
    for i in range(N):
        v_pos = np.maximum(v[:, i], 0.0)
        dW = np.random.standard_normal(n_paths) * np.sqrt(dt)
        v[:, i + 1] = v[:, i] + kappa * (theta - v_pos) * dt + alpha * np.sqrt(v_pos) * dW
    t = np.linspace(0, T, N + 1)
    return t, v


# ---------------------------------------------------------------------
def fig_variance_paths_kappa():
    """CIR variance paths under three kappa values."""
    np.random.seed(0)
    v0 = 0.04
    theta = 0.04
    alpha = 0.5
    T = 2.0
    N = 1000
    n_paths = 4

    fig, axes = plt.subplots(1, 3, figsize=(12, 6.2), sharey=True)
    kappas = [0.5, 2.0, 6.0]
    for ax, kappa in zip(axes, kappas):
        t, v = _simulate_cir(v0, kappa, theta, alpha, T, N, n_paths, seed=int(kappa * 10))
        for p in range(n_paths):
            ax.plot(t, np.sqrt(np.maximum(v[p], 0)), lw=1.2, alpha=0.85)
        ax.axhline(float(np.sqrt(theta)), color="black", ls="--", lw=1.2,
                   label=fr"$\sqrt{{\theta}}={np.sqrt(theta):.2f}$")
        half_life = np.log(2) / kappa
        ax.set_title(fr"$\kappa = {kappa}$  (half-life $={half_life:.2f}$y)", fontsize=11)
        ax.set_xlabel("$t$")
        if kappa == 0.5:
            ax.set_ylabel(r"$\sqrt{v_t}$ (instantaneous vol)")
        ax.legend(loc="upper right", frameon=False, fontsize=9)

    fig.suptitle(
        r"Heston variance paths: small $\kappa$ wanders, large $\kappa$ pins to $\theta$" + "\n"
        r"Empirical $\kappa^\mathbb{Q}$ on SPX sits near 2-4 per year (vol half-life of a few months)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    _save("ch10-variance-paths-kappa.png")


# ---------------------------------------------------------------------
def fig_charfunc_realimag():
    """Heston log-price char function Re/Im versus frequency."""
    # Use a stable parameterisation. We'll re-derive the Heston characteristic function inline.
    np.random.seed(0)
    kappa, theta, alpha, rho, v0 = 2.0, 0.04, 0.5, -0.7, 0.04
    r, q = 0.03, 0.0
    T = 1.0
    S0 = 100.0

    phi = np.linspace(-30, 30, 800)

    def heston_cf(phi):
        ii = 1j
        # Standard "trap" formulation
        a = kappa * theta
        b = kappa  # for P2 form
        u = -0.5
        d = np.sqrt((rho * alpha * ii * phi - b) ** 2 - alpha ** 2 * (2 * u * ii * phi - phi ** 2))
        g = (b - rho * alpha * ii * phi - d) / (b - rho * alpha * ii * phi + d)
        C = (r - q) * ii * phi * T + (a / alpha ** 2) * (
            (b - rho * alpha * ii * phi - d) * T - 2 * np.log((1 - g * np.exp(-d * T)) / (1 - g))
        )
        D = ((b - rho * alpha * ii * phi - d) / alpha ** 2) * (
            (1 - np.exp(-d * T)) / (1 - g * np.exp(-d * T))
        )
        return np.exp(C + D * v0 + ii * phi * np.log(S0))

    cf = heston_cf(phi)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.0), sharex=True)
    ax = axes[0]
    ax.plot(phi, cf.real, color="#1e3a8a", lw=1.8, label=r"Re $\varphi(\phi)$")
    ax.plot(phi, cf.imag, color="#c2410c", lw=1.8, label=r"Im $\varphi(\phi)$")
    ax.axhline(0, color="black", lw=0.5)
    ax.set_xlabel(r"$\phi$ (Fourier variable)")
    ax.set_ylabel("value")
    ax.set_title(r"Heston characteristic function $\varphi_{X_T}(\phi)$")
    ax.legend(loc="upper right", frameon=False, fontsize=9)

    ax = axes[1]
    ax.plot(phi, np.abs(cf), color="#16a34a", lw=1.8)
    ax.set_xlabel(r"$\phi$")
    ax.set_ylabel(r"$|\varphi(\phi)|$")
    ax.set_title(r"Modulus — controls Fourier-inversion integrability")
    ax.set_yscale("log")

    fig.suptitle(
        "Heston: density is intractable, but the characteristic function is closed-form\n"
        "Carr-Madan Fourier inversion turns this into vanilla prices in milliseconds",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    _save("ch10-charfunc-realimag.png")


# ---------------------------------------------------------------------
def _heston_call_price(S0, K, T, r, q, kappa, theta, alpha, rho, v0):
    """Heston (1993) European call price via direct Fourier integration of the
    two probabilities P1 and P2. Stable across all parameters this script
    uses; the old Carr-Madan FFT path was producing prices the BS-inverter
    could not handle for K<=S0 (all curves collapsed)."""
    from scipy.integrate import quad
    ii = 1j

    def _cf_factor(phi, b_param, u_param):
        d = np.sqrt((rho * alpha * ii * phi - b_param) ** 2
                    - alpha ** 2 * (2 * u_param * ii * phi - phi ** 2))
        g = (b_param - rho * alpha * ii * phi - d) / (b_param - rho * alpha * ii * phi + d)
        C = (r - q) * ii * phi * T + (kappa * theta / alpha ** 2) * (
            (b_param - rho * alpha * ii * phi - d) * T
            - 2 * np.log((1 - g * np.exp(-d * T)) / (1 - g))
        )
        D = ((b_param - rho * alpha * ii * phi - d) / alpha ** 2) * (
            (1 - np.exp(-d * T)) / (1 - g * np.exp(-d * T))
        )
        return np.exp(C + D * v0 + ii * phi * np.log(S0))

    def integrand(phi, j):
        if phi == 0.0:
            return 0.0
        if j == 1:
            cf_val = _cf_factor(phi, kappa - rho * alpha, 0.5)
        else:
            cf_val = _cf_factor(phi, kappa, -0.5)
        return np.real(np.exp(-ii * phi * np.log(K)) * cf_val / (ii * phi))

    P1, _ = quad(integrand, 1e-8, 200.0, args=(1,), limit=200)
    P2, _ = quad(integrand, 1e-8, 200.0, args=(2,), limit=200)
    P1 = 0.5 + P1 / np.pi
    P2 = 0.5 + P2 / np.pi
    return S0 * np.exp(-q * T) * P1 - K * np.exp(-r * T) * P2


def _bs_implied_vol(price, S0, K, T, r, q):
    """Brent root-find for implied vol from a call price."""
    from math import erf, sqrt
    from scipy.optimize import brentq

    def bs_call(sigma):
        d1 = (np.log(S0 / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        def Phi(x): return 0.5 * (1 + erf(x / sqrt(2)))
        return S0 * np.exp(-q * T) * Phi(d1) - K * np.exp(-r * T) * Phi(d2)

    # Tight intrinsic-value floor / no-arb cap. Price must lie in
    # [max(0, S e^{-qT} - K e^{-rT}), S e^{-qT}] for a finite implied vol.
    lower = max(0.0, S0 * np.exp(-q * T) - K * np.exp(-r * T))
    upper = S0 * np.exp(-q * T)
    if not (lower < price < upper):
        return np.nan
    try:
        return brentq(lambda sigma: bs_call(sigma) - price, 1e-5, 5.0, maxiter=200)
    except (ValueError, RuntimeError):
        return np.nan


def fig_smile_vs_rho():
    """Heston implied-vol smile across rho."""
    S0 = 100.0
    T = 0.5
    r, q = 0.03, 0.0
    kappa = 2.0
    theta = 0.04
    alpha = 0.5
    v0 = 0.04

    fig, ax = plt.subplots(figsize=FIGSIZE)
    rhos = [-0.8, -0.4, 0.0, 0.4]
    colors = ["#1e3a8a", "#0891b2", "#16a34a", "#c2410c"]
    log_moneyness = np.linspace(-0.25, 0.25, 25)
    K_target = S0 * np.exp(log_moneyness)
    for rho, c in zip(rhos, colors):
        ivs = []
        for K in K_target:
            price = _heston_call_price(S0, K, T, r, q, kappa, theta, alpha, rho, v0)
            ivs.append(_bs_implied_vol(price, S0, K, T, r, q))
        ax.plot(log_moneyness, ivs, color=c, lw=2,
                label=fr"$\rho = {rho}$")
    ax.set_xlabel(r"log-moneyness $\log(K/S_0)$")
    ax.set_ylabel("Black-Scholes implied vol")
    ax.set_title(rf"Heston implied-vol smile vs $\rho$ at $T={T:.1f}$y" +
                 "\nMore negative $\\rho$ steepens the left wing — SPX historically prints $\\rho \\approx -0.7$, the source of the equity-index 'skew'")
    ax.legend(loc="upper right", frameon=False, fontsize=10)
    _save("ch10-smile-vs-rho.png")


def fig_smile_vs_volvol():
    """Heston implied-vol smile across vol-of-vol alpha."""
    S0 = 100.0
    T = 0.5
    r, q = 0.03, 0.0
    kappa = 2.0
    theta = 0.04
    rho = -0.6
    v0 = 0.04

    fig, ax = plt.subplots(figsize=FIGSIZE)
    alphas = [0.2, 0.5, 1.0]
    colors = ["#1e3a8a", "#16a34a", "#c2410c"]
    log_moneyness = np.linspace(-0.25, 0.25, 25)
    K_target = S0 * np.exp(log_moneyness)
    for alpha, c in zip(alphas, colors):
        ivs = []
        for K in K_target:
            price = _heston_call_price(S0, K, T, r, q, kappa, theta, alpha, rho, v0)
            ivs.append(_bs_implied_vol(price, S0, K, T, r, q))
        ax.plot(log_moneyness, ivs, color=c, lw=2,
                label=fr"vol-of-vol $\alpha = {alpha}$")
    ax.set_xlabel(r"log-moneyness $\log(K/S_0)$")
    ax.set_ylabel("Black-Scholes implied vol")
    ax.set_title(rf"Heston implied-vol smile vs vol-of-vol $\alpha$ ($\rho={rho}$, $T={T:.1f}$y)" +
                 "\nVol-of-vol thickens the wings (curvature); $\\rho$ tilts them — the two parameters carry orthogonal smile information")
    ax.legend(loc="upper right", frameon=False, fontsize=10)
    _save("ch10-smile-vs-volvol.png")


# ---------------------------------------------------------------------
def fig_atm_term_structure():
    """Heston ATM implied vol vs maturity."""
    S0 = 100.0
    r, q = 0.03, 0.0
    kappa = 2.0
    theta = 0.04
    alpha = 0.5
    rho = -0.6
    v0_cases = [(0.02, "low spot vol"), (0.04, "at long-run mean"), (0.08, "high spot vol")]

    fig, ax = plt.subplots(figsize=FIGSIZE)
    Ts = np.linspace(0.1, 3.0, 30)
    colors = ["#1e3a8a", "#16a34a", "#c2410c"]
    for (v0, label), c in zip(v0_cases, colors):
        ivs = []
        for T in Ts:
            p = _heston_call_price(S0, S0, T, r, q, kappa, theta, alpha, rho, v0)
            ivs.append(_bs_implied_vol(p, S0, S0, T, r, q))
        ax.plot(Ts, ivs, color=c, lw=2.0,
                label=fr"$v_0={v0}$  ({label})")
    ax.axhline(float(np.sqrt(theta)), color="black", ls="--", lw=1.2,
               label=fr"$\sqrt{{\theta}}={np.sqrt(theta):.2f}$ (long-run vol)")
    ax.set_xlabel("maturity $T$")
    ax.set_ylabel("ATM implied vol")
    ax.set_title(r"Heston ATM implied-vol term structure: relaxation from $\sqrt{v_0}$ to $\sqrt{\theta}$ at rate $\kappa$" +
                 "\nThe same mean-reversion shape that VIX futures term structure prints in calm vs stressed regimes")
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    _save("ch10-atm-term-structure.png")


# ---------------------------------------------------------------------
def fig_feller_phase():
    """Feller phase diagram in (kappa, alpha) plane for several theta levels."""
    kappas = np.linspace(0.1, 6, 200)
    fig, ax = plt.subplots(figsize=FIGSIZE)
    thetas = [0.02, 0.04, 0.08]
    colors = ["#1e3a8a", "#16a34a", "#c2410c"]
    for theta, c in zip(thetas, colors):
        alpha_crit = np.sqrt(2 * kappas * theta)
        ax.plot(kappas, alpha_crit, color=c, lw=2.5,
                label=fr"$\theta = {theta}$ boundary $\alpha = \sqrt{{2\kappa\theta}}$")
        ax.fill_between(kappas, 0, alpha_crit, color=c, alpha=0.10)
    # Mark SPX-ish calibration point
    ax.scatter([2.0], [0.5], color="black", s=80, zorder=5)
    ax.annotate("typical SPX\ncalibration\n($\\kappa\\approx 2,\\,\\alpha\\approx 0.5$)",
                xy=(2.0, 0.5), xytext=(3.2, 0.85),
                fontsize=9, arrowprops=dict(arrowstyle="->", color="black"))
    ax.set_xlabel(r"$\kappa$ (mean-reversion speed)")
    ax.set_ylabel(r"$\alpha$ (vol of vol)")
    ax.set_title(r"Feller condition $2\kappa\theta \geq \alpha^2$: below the curves $v_t > 0$ a.s." +
                 "\nReal-world SPX calibrations typically violate Feller mildly — wings need more vol-of-vol than Feller allows")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 1.2)
    _save("ch10-feller-phase.png")


# ---------------------------------------------------------------------
if __name__ == "__main__":
    fig_variance_paths_kappa()
    fig_charfunc_realimag()
    fig_smile_vs_rho()
    fig_smile_vs_volvol()
    fig_atm_term_structure()
    fig_feller_phase()
    print("Chapter 10 extras: done")
