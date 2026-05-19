"""
Chapter 7 figure builder for Binomial Option Pricing.

Run: python docs/binomial-option-pricing/_build_ch7_figs.py

Outputs under figures/:
 ch07-roadmap.png
 ch07-C0-surface-3d.png
 ch07-tree-skeletons.png
 ch07-tildep-vs-n.png
 ch07-tildep-approx.png
 ch07-logS-histograms.png
 ch07-density-ridge-3d.png
 ch07-binom-vs-normal-4panel.png
 ch07-qq-plot.png
 ch07-Phi-d2-bars.png
 ch07-Phi-d2-convergence.png
 ch07-pmf-shift.png
 ch07-Phi-d1-d2-surface.png
 ch07-convergence-final.png
 ch07-BS-surface-3d.png
 ch07-error-loglog.png
 ch07-error-linear.png
 ch07-greeks-vs-S.png
 ch07-vega-surface-3d.png
 ch07-parity-payoff.png
 ch07-call-put-vs-K.png
 ch07-IV-smile.png
 ch07-IV-newton.png
 ch07-barrier-paths.png
 ch07-CDO-vs-H.png
 ch07-smile-shapes.png
 ch07-paths-models.png
 ch07-arc-timeline.png

Style: bright palette, 3-D via filled Poly3DCollection where it clarifies.
"""
from __future__ import annotations

import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 register 3-D projection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.stats import binom, norm

FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG_DIR, exist_ok=True)
DPI = 200

# Bright palette
NAVY = "#0b1d3a"
BLUE = "#1f77b4"
ORANGE = "#ff7f0e"
GREEN = "#2ca02c"
RED = "#d62728"
PURPLE = "#9467bd"
GOLD = "#fbbf24"
TEAL = "#17becf"
GREY = "#666666"
PINK = "#e377c2"
MAGENTA = "#c2185b"

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 11,
    "font.family": "DejaVu Sans",
})


def _save(name: str) -> None:
    path = os.path.join(FIG_DIR, name)
    plt.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {name}")


# Running numerical example: S0=100, K=100, r=5%, sigma=20%, T=1, BS price approx 10.45
S0_RUN, K_RUN, R_RUN, SIG_RUN, T_RUN = 100.0, 100.0, 0.05, 0.20, 1.0


def bs_call(S0, K, r, sigma, T):
    d1 = (math.log(S0 / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S0 * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2), d1, d2


def bs_put(S0, K, r, sigma, T):
    d1 = (math.log(S0 / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S0 * norm.cdf(-d1)


def crr_params(sigma, T, n, r):
    dt = T / n
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    a = math.exp(r * dt)
    p = (a - d) / (u - d)
    return dt, u, d, a - 1.0, p


def crr_call_price(S0, K, r, sigma, T, n):
    dt, u, d, _rn, p = crr_params(sigma, T, n, r)
    a = math.exp(r * dt)
    j = np.arange(n + 1)
    ST = S0 * (u ** j) * (d ** (n - j))
    V = np.maximum(ST - K, 0.0)
    disc = 1.0 / a
    for step in range(n, 0, -1):
        V = disc * (p * V[1:step + 1] + (1 - p) * V[:step])
    return float(V[0])


# 7.1 Roadmap diagram
def fig_roadmap():
    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 6)
    ax.axis("off")

    boxes = [
        (0.4, 2.2, 2.4, 1.6, "CRR tree\n$u,d,\\tilde p, n$", BLUE),
        (3.3, 2.2, 2.4, 1.6, "Per-step\n$X_i \\in \\{\\pm \\sigma\\sqrt{\\Delta t}\\}$", ORANGE),
        (6.2, 2.2, 2.4, 1.6, "CLT applies\nto $\\sum X_i$", GREEN),
        (9.1, 2.2, 2.4, 1.6, "Normal limit\n$\\log S_T \\sim N(\\mu_* T,\\sigma^2 T)$", PURPLE),
        (12.0, 2.2, 1.8, 1.6, "$\\Phi(d_1),\\Phi(d_2)$", RED),
    ]
    for (x, y, w, h, txt, c) in boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08", linewidth=2,
                                    facecolor=c, edgecolor="black", alpha=0.85))
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center",
                fontsize=11, color="white", fontweight="bold")
    for i in range(4):
        x_start = boxes[i][0] + boxes[i][2]
        x_end = boxes[i + 1][0]
        ax.add_patch(FancyArrowPatch((x_start + 0.05, 3.0), (x_end - 0.05, 3.0),
                                     arrowstyle="-|>", mutation_scale=22,
                                     linewidth=2.2, color=NAVY))

    ax.add_patch(FancyBboxPatch((3.4, 0.2), 7.5, 1.2, boxstyle="round,pad=0.1",
                                linewidth=2, facecolor=GOLD, edgecolor=NAVY, alpha=0.8))
    ax.text(7.15, 0.8,
            "Destination: $C_0 = S_0\\,\\Phi(d_1) - Ke^{-rT}\\,\\Phi(d_2)$",
            ha="center", va="center", fontsize=15, fontweight="bold", color=NAVY)

    ax.text(7.0, 5.4, "Chapter 7 roadmap: CRR $\\to$ Black-Scholes via the CLT alone",
            ha="center", fontsize=14, fontweight="bold", color=NAVY)
    _save("ch07-roadmap.png")


# 7.1 BS price surface C0(S0, T)
def fig_C0_surface_3d():
    S_vals = np.linspace(60, 140, 30)
    T_vals = np.linspace(0.05, 2.0, 30)
    SS, TT = np.meshgrid(S_vals, T_vals)
    Z = np.zeros_like(SS)
    for i in range(SS.shape[0]):
        for j in range(SS.shape[1]):
            Z[i, j] = bs_call(SS[i, j], K_RUN, R_RUN, SIG_RUN, TT[i, j])[0]

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")
    surf = ax.plot_surface(SS, TT, Z, cmap=cm.plasma, edgecolor=NAVY,
                           linewidth=0.15, alpha=0.92)
    ax.set_xlabel("$S_0$", labelpad=12)
    ax.set_ylabel("$T$ (yrs)", labelpad=12)
    ax.set_zlabel("$C_0$", labelpad=10)
    ax.set_title("BS call price $C_0(S_0, T)$, $K=100$, $r=5\\%$, $\\sigma=20\\%$")
    fig.colorbar(surf, shrink=0.6, pad=0.12, label="$C_0$")
    _save("ch07-C0-surface-3d.png")


# 7.2 Tree skeletons n=4, 16, 64
def fig_tree_skeletons():
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5))
    ymax = 3 * SIG_RUN * math.sqrt(T_RUN)
    for ax, n, col in zip(axes, [4, 16, 64], [BLUE, ORANGE, GREEN]):
        dt = T_RUN / n
        ssd = SIG_RUN * math.sqrt(dt)
        for i in range(n):
            for k in range(-i, i + 1, 2):
                x0, y0 = i * dt, k * ssd
                ax.plot([x0, x0 + dt], [y0, y0 + ssd], color=col, linewidth=0.5, alpha=0.7)
                ax.plot([x0, x0 + dt], [y0, y0 - ssd], color=col, linewidth=0.5, alpha=0.7)
        ax.set_xlim(0, T_RUN)
        ax.set_ylim(-ymax, ymax)
        ax.set_title(f"$n={n}$, $\\Delta t=1/{n}$, $u-1={math.exp(ssd)-1:.4f}$")
        ax.set_xlabel("time")
        ax.set_ylabel("$\\log(S/S_0)$")
        ax.axhline(0, color=GREY, linewidth=0.6)
    fig.suptitle("CRR tree skeletons: same vertical extent, denser as $n$ grows",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    _save("ch07-tree-skeletons.png")


# 7.2 tilde p_n vs n
def fig_tildep_vs_n():
    ns = np.array([2, 4, 8, 16, 32, 64, 128, 256, 512, 1024])
    ps = []
    for n in ns:
        _, _, _, _, p = crr_params(SIG_RUN, T_RUN, int(n), R_RUN)
        ps.append(p)
    ps = np.array(ps)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.semilogx(ns, ps, "o-", color=BLUE, linewidth=2, markersize=8, label="$\\tilde p_n$")
    ax.axhline(0.5, color=RED, linewidth=1.5, linestyle="--", label="limit $1/2$")
    ax.set_xlabel("$n$")
    ax.set_ylabel("$\\tilde p_n$")
    ax.set_title("Risk-neutral probability $\\tilde p_n \\to 1/2$ as $n \\to \\infty$")
    ax.legend(loc="upper right")
    ymax = float(ps.max()) + 0.005
    ax.set_ylim(0.498, ymax)
    for x, y in zip(ns, ps):
        ax.annotate(f"{y:.4f}", (x, y), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8, color=NAVY)
    _save("ch07-tildep-vs-n.png")


# 7.3 exact vs Taylor approx for tilde p
def fig_tildep_approx():
    ns = np.array([2, 4, 8, 16, 32, 64, 128, 256, 512, 1024])
    exact = []
    approx = []
    mu_star = R_RUN - 0.5 * SIG_RUN ** 2
    for n in ns:
        dt = T_RUN / n
        _, _, _, _, p = crr_params(SIG_RUN, T_RUN, int(n), R_RUN)
        exact.append(p)
        approx.append(0.5 + (mu_star * math.sqrt(dt)) / (2 * SIG_RUN))
    exact = np.array(exact)
    approx = np.array(approx)

    fig, ax = plt.subplots(figsize=(9, 5))
    sqrtdt = np.sqrt(T_RUN / ns)
    ax.plot(sqrtdt, exact, "o-", color=BLUE, linewidth=2, markersize=8, label="exact $\\tilde p_n$")
    ax.plot(sqrtdt, approx, "s--", color=ORANGE, linewidth=2, markersize=7,
            label="$1/2 + \\mu_*\\sqrt{\\Delta t}/(2\\sigma)$")
    ax.set_xlabel("$\\sqrt{\\Delta t}$")
    ax.set_ylabel("$\\tilde p_n$")
    ax.set_title("Risk-neutral $\\tilde p_n$: exact vs Taylor approximation in $\\sqrt{\\Delta t}$")
    ax.legend()
    _save("ch07-tildep-approx.png")


# 7.4 log S histograms n=10 vs n=200
def fig_logS_histograms():
    mu_T = (R_RUN - 0.5 * SIG_RUN ** 2) * T_RUN
    var_T = SIG_RUN ** 2 * T_RUN
    sd = math.sqrt(var_T)
    xs = np.linspace(mu_T - 4 * sd, mu_T + 4 * sd, 400)
    pdf = norm.pdf(xs, mu_T, sd)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    for ax, n in zip(axes, [10, 200]):
        dt = T_RUN / n
        sx = SIG_RUN * math.sqrt(dt)
        _, _, _, _, p = crr_params(SIG_RUN, T_RUN, n, R_RUN)
        ks = np.arange(n + 1)
        log_ratios = ks * sx + (n - ks) * (-sx)
        probs = binom.pmf(ks, n, p)
        width = 2 * sx
        ax.bar(log_ratios, probs / width, width=width * 0.9, color=BLUE, alpha=0.6,
               edgecolor=NAVY, linewidth=0.5, label=f"CRR $n={n}$")
        ax.plot(xs, pdf, color=RED, linewidth=2.2,
                label="$N(\\mu_* T, \\sigma^2 T)$")
        ax.set_xlabel("$\\log(S_T/S_0)$")
        ax.set_ylabel("density")
        ax.set_title(f"$n={n}$ steps")
        ax.legend()
        ax.set_xlim(xs.min(), xs.max())
    fig.suptitle("Discrete CRR distribution of $\\log(S_T/S_0)$ overlaying the normal limit",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    _save("ch07-logS-histograms.png")


# 7.4 3-D ridge density at increasing n (Poly3DCollection)
def fig_density_ridge_3d():
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")
    ns = [4, 8, 16, 32, 64, 128]
    cmap = cm.plasma
    mu_T = (R_RUN - 0.5 * SIG_RUN ** 2) * T_RUN
    var_T = SIG_RUN ** 2 * T_RUN
    sd = math.sqrt(var_T)
    for idx, n in enumerate(ns):
        dt = T_RUN / n
        sx = SIG_RUN * math.sqrt(dt)
        _, _, _, _, p = crr_params(SIG_RUN, T_RUN, n, R_RUN)
        ks = np.arange(n + 1)
        log_ratios = ks * sx + (n - ks) * (-sx)
        probs = binom.pmf(ks, n, p)
        width = 2 * sx
        dens = probs / width
        col = cmap(idx / max(1, len(ns) - 1))
        verts = [(log_ratios[0], 0)]
        for x, y in zip(log_ratios, dens):
            verts.append((x, y))
        verts.append((log_ratios[-1], 0))
        poly = Poly3DCollection([[(v[0], idx, v[1]) for v in verts]],
                                facecolor=col, edgecolor=NAVY, linewidth=0.4, alpha=0.75)
        ax.add_collection3d(poly)
    xs = np.linspace(mu_T - 4 * sd, mu_T + 4 * sd, 200)
    pdf = norm.pdf(xs, mu_T, sd)
    ax.plot(xs, [len(ns)] * len(xs), pdf, color=RED, linewidth=2.5,
            label="$N(\\mu_* T,\\sigma^2 T)$")
    ax.set_xlabel("$\\log(S_T/S_0)$", labelpad=12)
    ax.set_ylabel("index of $n$", labelpad=14)
    ax.set_zlabel("density", labelpad=10)
    ax.set_yticks(range(len(ns) + 1))
    ax.set_yticklabels([str(n) for n in ns] + ["limit"])
    ax.set_title("CRR density ridges of $\\log(S_T/S_0)$ converge to the normal limit")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 0.95))
    _save("ch07-density-ridge-3d.png")


# 7.5 4-panel: binomial pmf vs normal at n=4,16,64,256
def fig_binom_vs_normal_4panel():
    mu_T = (R_RUN - 0.5 * SIG_RUN ** 2) * T_RUN
    var_T = SIG_RUN ** 2 * T_RUN
    sd = math.sqrt(var_T)
    xs = np.linspace(mu_T - 4 * sd, mu_T + 4 * sd, 400)
    pdf = norm.pdf(xs, mu_T, sd)

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for ax, n, c in zip(axes.flat, [4, 16, 64, 256], [BLUE, ORANGE, GREEN, PURPLE]):
        dt = T_RUN / n
        sx = SIG_RUN * math.sqrt(dt)
        _, _, _, _, p = crr_params(SIG_RUN, T_RUN, n, R_RUN)
        ks = np.arange(n + 1)
        log_ratios = ks * sx + (n - ks) * (-sx)
        probs = binom.pmf(ks, n, p)
        width = 2 * sx
        ax.bar(log_ratios, probs / width, width=width * 0.9, color=c, alpha=0.7,
               edgecolor=NAVY, linewidth=0.4)
        ax.plot(xs, pdf, color=RED, linewidth=2.5)
        ax.set_title(f"$n = {n}$")
        ax.set_xlim(xs.min(), xs.max())
        ax.set_xlabel("$\\log(S_T/S_0)$")
        ax.set_ylabel("density")
    fig.suptitle("CRR $\\to$ normal: same panel at four resolutions", fontsize=13, fontweight="bold")
    fig.tight_layout()
    _save("ch07-binom-vs-normal-4panel.png")


# 7.5 Q-Q plot of CRR log-returns vs normal
def fig_qq_plot():
    n = 512
    dt = T_RUN / n
    sx = SIG_RUN * math.sqrt(dt)
    _, _, _, _, p = crr_params(SIG_RUN, T_RUN, n, R_RUN)
    ks = np.arange(n + 1)
    log_ratios = ks * sx + (n - ks) * (-sx)
    probs = binom.pmf(ks, n, p)
    F = np.cumsum(probs)
    F_mid = F - 0.5 * probs
    mu_T = (R_RUN - 0.5 * SIG_RUN ** 2) * T_RUN
    sd = math.sqrt(SIG_RUN ** 2 * T_RUN)
    nq = norm.ppf(F_mid, loc=mu_T, scale=sd)

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot(nq, log_ratios, "o", color=BLUE, alpha=0.6, markersize=4)
    lo = min(nq.min(), log_ratios.min())
    hi = max(nq.max(), log_ratios.max())
    ax.plot([lo, hi], [lo, hi], color=RED, linewidth=2, label="$y = x$")
    ax.set_xlabel("normal quantile")
    ax.set_ylabel("CRR quantile $(n=512)$")
    ax.set_title("Q-Q plot: CRR log-returns vs $N(\\mu_* T,\\sigma^2 T)$")
    ax.legend()
    _save("ch07-qq-plot.png")


# 7.6 Phi(d2) bars: CRR pmf with right tail shaded
def fig_Phi_d2_bars():
    n = 64
    dt = T_RUN / n
    sx = SIG_RUN * math.sqrt(dt)
    _, _, _, _, p = crr_params(SIG_RUN, T_RUN, n, R_RUN)
    u = math.exp(sx)
    d = 1 / u
    ks = np.arange(n + 1)
    ST = S0_RUN * (u ** ks) * (d ** (n - ks))
    probs = binom.pmf(ks, n, p)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    colors = [BLUE if s < K_RUN else GREEN for s in ST]
    ax.bar(ST, probs, width=(ST[1] - ST[0]) * 0.9, color=colors, alpha=0.75,
           edgecolor=NAVY, linewidth=0.4)
    ax.axvline(K_RUN, color=RED, linewidth=2.2, label=f"$K={K_RUN:g}$")
    ax.set_xlabel("$S_T$")
    ax.set_ylabel("$\\tilde{\\mathbb{P}}(S_T = \\cdot)$")
    p_right = probs[ST >= K_RUN].sum()
    d2 = (math.log(S0_RUN / K_RUN) + (R_RUN - 0.5 * SIG_RUN ** 2) * T_RUN) / (SIG_RUN * math.sqrt(T_RUN))
    ax.set_title(
        f"CRR $n=64$ PMF: right tail $\\tilde P(S_T\\geq K)={p_right:.4f}$ "
        f"$\\to \\Phi(d_2)={norm.cdf(d2):.4f}$"
    )
    ax.set_xlim(40, 250)
    ax.legend(loc="upper right")
    _save("ch07-Phi-d2-bars.png")


# 7.6 Convergence of P(S_T >= K) to Phi(d2)
def fig_Phi_d2_convergence():
    ns = np.array([2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048])
    probs_crr = []
    for n in ns:
        dt = T_RUN / n
        sx = SIG_RUN * math.sqrt(dt)
        _, _, _, _, p = crr_params(SIG_RUN, T_RUN, int(n), R_RUN)
        u = math.exp(sx)
        d = 1 / u
        ks = np.arange(n + 1)
        ST = S0_RUN * (u ** ks) * (d ** (n - ks))
        pp = binom.pmf(ks, int(n), p)
        probs_crr.append(pp[ST >= K_RUN].sum())
    probs_crr = np.array(probs_crr)
    d2 = (math.log(S0_RUN / K_RUN) + (R_RUN - 0.5 * SIG_RUN ** 2) * T_RUN) / (SIG_RUN * math.sqrt(T_RUN))
    limit = norm.cdf(d2)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.semilogx(ns, probs_crr, "o-", color=BLUE, linewidth=2, markersize=7,
                label="CRR $\\tilde P(S_T\\geq K)$")
    ax.axhline(limit, color=RED, linewidth=2, linestyle="--",
               label=f"$\\Phi(d_2) = {limit:.4f}$")
    ax.set_xlabel("$n$")
    ax.set_ylabel("probability")
    ax.set_title("Convergence of risk-neutral exercise probability to $\\Phi(d_2)$")
    ax.legend(loc="center right", bbox_to_anchor=(1.0, 0.65))
    _save("ch07-Phi-d2-convergence.png")


# 7.7 pmf shift between P-tilde and stock-numeraire P-tilde-1
def fig_pmf_shift():
    n = 64
    dt = T_RUN / n
    sx = SIG_RUN * math.sqrt(dt)
    a = math.exp(R_RUN * dt)
    _, _, _, _, p = crr_params(SIG_RUN, T_RUN, n, R_RUN)
    u = math.exp(sx)
    d = 1 / u
    p1 = p * u / a
    ks = np.arange(n + 1)
    ST = S0_RUN * (u ** ks) * (d ** (n - ks))
    P0 = binom.pmf(ks, n, p)
    P1 = binom.pmf(ks, n, p1)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    for ax, prob, col, lab in zip(
        axes,
        [P0, P1],
        [GREY, BLUE],
        [
            "$\\tilde{\\mathbb{P}}$ (money-market numeraire)",
            "$\\tilde{\\mathbb{P}}^{(1)}$ (stock numeraire)",
        ],
    ):
        ax.bar(ST, prob, width=(ST[1] - ST[0]) * 0.9,
               color=[col if s < K_RUN else GREEN for s in ST],
               alpha=0.75, edgecolor=NAVY, linewidth=0.3)
        ax.axvline(K_RUN, color=RED, linewidth=2, label=f"$K={K_RUN:g}$")
        ax.set_xlabel("$S_T$")
        ax.set_ylabel("probability")
        right = prob[ST >= K_RUN].sum()
        ax.set_title(f"{lab}\n$P(S_T\\geq K) = {right:.4f}$")
        ax.set_xlim(40, 260)
        ax.legend()
    fig.suptitle("Two measures, two probabilities: $\\Phi(d_2)$ vs $\\Phi(d_1)$",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    _save("ch07-pmf-shift.png")


# 7.7 3-D surface of Phi(d1), Phi(d2) over (K, sigma)
def fig_Phi_d1_d2_surface():
    K_vals = np.linspace(60, 140, 30)
    sig_vals = np.linspace(0.05, 0.6, 30)
    KK, SS = np.meshgrid(K_vals, sig_vals)
    Phi1 = np.zeros_like(KK)
    Phi2 = np.zeros_like(KK)
    for i in range(KK.shape[0]):
        for j in range(KK.shape[1]):
            sig = SS[i, j]
            K = KK[i, j]
            d1 = (math.log(S0_RUN / K) + (R_RUN + 0.5 * sig ** 2) * T_RUN) / (sig * math.sqrt(T_RUN))
            d2 = d1 - sig * math.sqrt(T_RUN)
            Phi1[i, j] = norm.cdf(d1)
            Phi2[i, j] = norm.cdf(d2)

    fig = plt.figure(figsize=(15, 7))
    ax1 = fig.add_subplot(121, projection="3d")
    ax1.plot_surface(KK, SS, Phi1, cmap=cm.viridis, edgecolor=NAVY, linewidth=0.15, alpha=0.9)
    ax1.set_xlabel("$K$", labelpad=10)
    ax1.set_ylabel("$\\sigma$", labelpad=10)
    ax1.set_zlabel("$\\Phi(d_1)$", labelpad=10)
    ax1.set_title("$\\Phi(d_1)$ stock-numeraire prob")

    ax2 = fig.add_subplot(122, projection="3d")
    ax2.plot_surface(KK, SS, Phi2, cmap=cm.plasma, edgecolor=NAVY, linewidth=0.15, alpha=0.9)
    ax2.set_xlabel("$K$", labelpad=10)
    ax2.set_ylabel("$\\sigma$", labelpad=10)
    ax2.set_zlabel("$\\Phi(d_2)$", labelpad=10)
    ax2.set_title("$\\Phi(d_2)$ risk-neutral exercise prob")
    fig.subplots_adjust(wspace=0.15)
    _save("ch07-Phi-d1-d2-surface.png")


# 7.8 Final convergence of CRR to BS
def fig_convergence_final():
    ns = np.array([2, 4, 8, 16, 32, 64, 128, 256, 512, 1024])
    Cs = np.array([crr_call_price(S0_RUN, K_RUN, R_RUN, SIG_RUN, T_RUN, int(n)) for n in ns])
    C_bs, _, _ = bs_call(S0_RUN, K_RUN, R_RUN, SIG_RUN, T_RUN)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.semilogx(ns, Cs, "o-", color=BLUE, linewidth=2, markersize=8, label="CRR $C_0^{(n)}$")
    ax.axhline(C_bs, color=RED, linewidth=2, linestyle="--",
               label=f"Black-Scholes $= {C_bs:.4f}$")
    ax.set_xlabel("$n$")
    ax.set_ylabel("$C_0$")
    ax.set_title("CRR call price converges to Black-Scholes (running example)")
    for x, y in zip(ns, Cs):
        ax.annotate(f"{y:.3f}", (x, y), textcoords="offset points",
                    xytext=(0, -14),
                    ha="center", fontsize=8, color=NAVY)
    ax.legend(loc="lower right")
    _save("ch07-convergence-final.png")


# 7.8 3-D BS call surface over (S0/K, sigma*sqrt(T))
def fig_BS_surface_3d():
    m_vals = np.linspace(0.6, 1.5, 35)
    v_vals = np.linspace(0.05, 0.7, 35)
    MM, VV = np.meshgrid(m_vals, v_vals)
    Z = np.zeros_like(MM)
    K = 100.0
    for i in range(MM.shape[0]):
        for j in range(MM.shape[1]):
            S0 = MM[i, j] * K
            v = VV[i, j]
            C, _, _ = bs_call(S0, K, R_RUN, v, 1.0)
            Z[i, j] = C / K

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")
    surf = ax.plot_surface(MM, VV, Z, cmap=cm.viridis, edgecolor=NAVY,
                           linewidth=0.15, alpha=0.92)
    ax.set_xlabel("$S_0 / K$", labelpad=12)
    ax.set_ylabel("$\\sigma \\sqrt{T}$", labelpad=12)
    ax.set_zlabel("$C_0 / K$", labelpad=10)
    ax.set_title("BS call surface in moneyness and total vol")
    fig.colorbar(surf, shrink=0.6, pad=0.12, label="$C_0/K$")
    _save("ch07-BS-surface-3d.png")


# 7.9 Error log-log
def fig_error_loglog():
    ns = np.array([2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048])
    Cs = np.array([crr_call_price(S0_RUN, K_RUN, R_RUN, SIG_RUN, T_RUN, int(n)) for n in ns])
    C_bs, _, _ = bs_call(S0_RUN, K_RUN, R_RUN, SIG_RUN, T_RUN)
    err = np.abs(Cs - C_bs)
    rich = 0.5 * (Cs[:-1] + Cs[1:])
    rich_err = np.abs(rich - C_bs)
    rich_n = 0.5 * (ns[:-1] + ns[1:])

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.loglog(ns, err, "o-", color=BLUE, linewidth=2, markersize=7,
              label="CRR $|C^{(n)} - C^{BS}|$")
    ax.loglog(rich_n, rich_err, "s-", color=GREEN, linewidth=2, markersize=7,
              label="Richardson avg of consecutive $n$")
    ref1 = 0.6 * ns.astype(float) ** -1.0
    ref2 = 0.6 * ns.astype(float) ** -2.0
    ax.loglog(ns, ref1, color=GREY, linewidth=1.2, linestyle=":", label="slope $-1$")
    ax.loglog(ns, ref2, color=GREY, linewidth=1.2, linestyle="--", label="slope $-2$")
    ax.set_xlabel("$n$")
    ax.set_ylabel("absolute error")
    ax.set_title("CRR error $\\sim 1/n$ (oscillatory); Richardson averaging $\\sim 1/n^2$")
    ax.legend()
    _save("ch07-error-loglog.png")


# 7.9 Error linear (oscillation)
def fig_error_linear():
    ns = np.arange(20, 261, 2)
    Cs = np.array([crr_call_price(S0_RUN, K_RUN, R_RUN, SIG_RUN, T_RUN, int(n)) for n in ns])
    C_bs, _, _ = bs_call(S0_RUN, K_RUN, R_RUN, SIG_RUN, T_RUN)
    err = Cs - C_bs

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(ns, err, "-", color=BLUE, linewidth=1.6)
    ax.scatter(ns, err, s=14, color=ORANGE, zorder=3)
    ax.axhline(0, color=RED, linewidth=1.5, linestyle="--")
    ax.set_xlabel("$n$")
    ax.set_ylabel("$C^{(n)} - C^{BS}$")
    ax.set_title("Oscillation around BS price as $K$ falls between successive tree nodes")
    _save("ch07-error-linear.png")


# 7.10 Greeks vs S0
def fig_greeks_vs_S():
    S_vals = np.linspace(50, 160, 200)
    deltas, gammas, thetas, vegas = [], [], [], []
    for S0 in S_vals:
        d1 = (math.log(S0 / K_RUN) + (R_RUN + 0.5 * SIG_RUN ** 2) * T_RUN) / (SIG_RUN * math.sqrt(T_RUN))
        d2 = d1 - SIG_RUN * math.sqrt(T_RUN)
        deltas.append(norm.cdf(d1))
        gammas.append(norm.pdf(d1) / (S0 * SIG_RUN * math.sqrt(T_RUN)))
        thetas.append(-S0 * norm.pdf(d1) * SIG_RUN / (2 * math.sqrt(T_RUN))
                      - R_RUN * K_RUN * math.exp(-R_RUN * T_RUN) * norm.cdf(d2))
        vegas.append(S0 * math.sqrt(T_RUN) * norm.pdf(d1))

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    axes_flat = axes.flat
    titles = [
        "$\\Delta = \\Phi(d_1)$",
        "$\\Gamma = \\phi(d_1)/(S_0\\sigma\\sqrt{T})$",
        "$\\Theta$",
        "$\\nu$ (vega)",
    ]
    ylabels = ["$\\Delta$", "$\\Gamma$", "$\\Theta$", "$\\nu$"]
    legend_locs = ["lower right", "upper right", "lower right", "upper right"]
    colors = [BLUE, ORANGE, RED, GREEN]
    series = [deltas, gammas, thetas, vegas]
    for ax, vals, ttl, yl, col, lloc in zip(
        axes_flat, series, titles, ylabels, colors, legend_locs
    ):
        ax.plot(S_vals, vals, color=col, linewidth=2.5)
        ax.axvline(K_RUN, color=GREY, linewidth=1, linestyle="--", label=f"$K={K_RUN:g}$")
        ax.set_xlabel("$S_0$")
        ax.set_ylabel(yl)
        ax.set_title(ttl)
        ax.legend(loc=lloc)
    fig.suptitle("Black-Scholes call Greeks vs spot (running example)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    _save("ch07-greeks-vs-S.png")


# 7.10 Vega 3-D surface
def fig_vega_surface_3d():
    S_vals = np.linspace(60, 140, 30)
    T_vals = np.linspace(0.05, 2.0, 30)
    SS, TT = np.meshgrid(S_vals, T_vals)
    V = np.zeros_like(SS)
    for i in range(SS.shape[0]):
        for j in range(SS.shape[1]):
            S0 = SS[i, j]
            T = TT[i, j]
            d1 = (math.log(S0 / K_RUN) + (R_RUN + 0.5 * SIG_RUN ** 2) * T) / (SIG_RUN * math.sqrt(T))
            V[i, j] = S0 * math.sqrt(T) * norm.pdf(d1)

    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")
    surf = ax.plot_surface(SS, TT, V, cmap=cm.inferno, edgecolor=NAVY,
                           linewidth=0.15, alpha=0.92)
    ax.set_xlabel("$S_0$", labelpad=12)
    ax.set_ylabel("$T$", labelpad=12)
    ax.set_zlabel("$\\nu$", labelpad=10)
    ax.set_title("Vega surface $\\nu(S_0, T)$: peaks at ATM, rises with $\\sqrt{T}$")
    fig.colorbar(surf, shrink=0.6, pad=0.12, label="$\\nu$")
    _save("ch07-vega-surface-3d.png")


# 7.11 Parity payoff
def fig_parity_payoff():
    S_vals = np.linspace(30, 170, 400)
    call = np.maximum(S_vals - K_RUN, 0)
    put = np.maximum(K_RUN - S_vals, 0)
    diff = call - put
    long_S = S_vals - K_RUN

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(S_vals, call, color=BLUE, linewidth=2.5, label="Call payoff $(S_T-K)^+$")
    ax.plot(S_vals, put, color=ORANGE, linewidth=2.5, label="Put payoff $(K-S_T)^+$")
    ax.plot(S_vals, diff, color=GREEN, linewidth=2.5, linestyle="--",
            label="Call $-$ Put")
    ax.plot(S_vals, long_S, color=RED, linewidth=1.5, linestyle=":",
            label="$S_T - K$")
    ax.axhline(0, color=GREY, linewidth=0.6)
    ax.axvline(K_RUN, color=GREY, linewidth=0.6, linestyle="--")
    ax.set_xlabel("$S_T$")
    ax.set_ylabel("payoff")
    ax.set_title("Put-call parity at maturity: $C - P = S_T - K$")
    ax.legend()
    _save("ch07-parity-payoff.png")


# 7.11 Call/Put vs K
def fig_call_put_vs_K():
    K_vals = np.linspace(60, 140, 200)
    C_vals = [bs_call(S0_RUN, K, R_RUN, SIG_RUN, T_RUN)[0] for K in K_vals]
    P_vals = [bs_put(S0_RUN, K, R_RUN, SIG_RUN, T_RUN) for K in K_vals]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(K_vals, C_vals, color=BLUE, linewidth=2.5, label="Call $C_0(K)$")
    ax.plot(K_vals, P_vals, color=ORANGE, linewidth=2.5, label="Put $P_0(K)$")
    ax.axvline(S0_RUN, color=GREY, linewidth=1, linestyle="--", label=f"$S_0={S0_RUN:g}$")
    fwd = S0_RUN * math.exp(R_RUN * T_RUN)
    ax.axvline(fwd, color=RED, linewidth=1, linestyle=":", label=f"forward $={fwd:.2f}$")
    ax.set_xlabel("strike $K$")
    ax.set_ylabel("price")
    ax.set_title("BS call and put as functions of $K$ (running params)")
    ax.legend()
    _save("ch07-call-put-vs-K.png")


# 7.12 IV smile
def fig_IV_smile():
    Ks = np.array([85, 90, 95, 100, 105, 110, 115])
    IVs = np.array([0.250, 0.232, 0.218, 0.205, 0.215, 0.232, 0.255])
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(Ks, IVs, "o-", color=BLUE, linewidth=2.2, markersize=9)
    ax.axhline(SIG_RUN, color=RED, linewidth=1.5, linestyle="--",
               label=f"$\\sigma={SIG_RUN}$ (BS flat)")
    ax.set_xlabel("strike $K$")
    ax.set_ylabel("implied $\\sigma$")
    ax.set_title("Implied-vol smile recovered from market call prices")
    ax.legend()
    _save("ch07-IV-smile.png")


# 7.12 Newton iteration for implied vol
def fig_IV_newton():
    sig_vals = np.linspace(0.05, 0.6, 200)
    C_vals = [bs_call(S0_RUN, K_RUN, R_RUN, s, T_RUN)[0] for s in sig_vals]
    C_mkt = 12.0

    sigs = [0.20]
    for _ in range(4):
        s = sigs[-1]
        C, d1, _ = bs_call(S0_RUN, K_RUN, R_RUN, s, T_RUN)
        vega = S0_RUN * math.sqrt(T_RUN) * norm.pdf(d1)
        sigs.append(s - (C - C_mkt) / vega)
    sigs = sigs[:4]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(sig_vals, C_vals, color=BLUE, linewidth=2.2, label="$C_0(\\sigma)$")
    ax.axhline(C_mkt, color=RED, linewidth=1.5, linestyle="--",
               label=f"$C^{{mkt}}={C_mkt:.1f}$")
    label_offsets = [(-18, -18), (12, -18), (-22, 12), (14, 12)]
    for k, s in enumerate(sigs):
        C, _, _ = bs_call(S0_RUN, K_RUN, R_RUN, s, T_RUN)
        ax.scatter([s], [C], color=ORANGE, s=70, zorder=4)
        dx, dy = label_offsets[k % len(label_offsets)]
        ax.annotate(f"$\\sigma_{k}$", (s, C), textcoords="offset points",
                    xytext=(dx, dy), color=NAVY, fontsize=11, fontweight="bold")
    ax.set_xlabel("$\\sigma$")
    ax.set_ylabel("$C_0$")
    ax.set_title("Newton iteration to implied volatility")
    ax.legend(loc="upper left")
    _save("ch07-IV-newton.png")


# 7.13 Barrier paths (killed vs reflected)
def fig_barrier_paths():
    rng = np.random.default_rng(7)
    n = 200
    dt = T_RUN / n
    H = 80.0
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    for ax, ttl, killed in zip(
        axes,
        [
            "Paths killed at barrier $H=80$",
            "Reflection trick: each killed path mirrored",
        ],
        [True, False],
    ):
        for _i in range(20):
            Z = rng.standard_normal(n)
            logS = np.cumsum((R_RUN - 0.5 * SIG_RUN ** 2) * dt + SIG_RUN * math.sqrt(dt) * Z)
            S = S0_RUN * np.exp(logS)
            hit_idx = int(np.argmax(S <= H)) if (S <= H).any() else -1
            crossed = hit_idx >= 0 and S[hit_idx] <= H
            if crossed:
                if killed:
                    ax.plot(np.arange(hit_idx + 1) * dt, S[:hit_idx + 1],
                            color=RED, linewidth=1.0, alpha=0.7)
                else:
                    S_ref = np.copy(S)
                    S_ref[hit_idx:] = 2 * H - S[hit_idx:]
                    ax.plot(np.arange(n) * dt, S, color=RED, linewidth=0.8, alpha=0.5)
                    ax.plot(np.arange(n) * dt, S_ref, color=PURPLE,
                            linewidth=0.8, alpha=0.6, linestyle="--")
            else:
                ax.plot(np.arange(n) * dt, S, color=BLUE, linewidth=0.8, alpha=0.7)
        ax.axhline(H, color=NAVY, linewidth=2, linestyle="--", label=f"$H={H:g}$")
        ax.axhline(K_RUN, color=GREEN, linewidth=1, linestyle=":", label=f"$K={K_RUN:g}$")
        ax.set_xlabel("$t$")
        ax.set_ylabel("$S_t$")
        ax.set_title(ttl)
        ax.legend(loc="upper left")
    fig.tight_layout()
    _save("ch07-barrier-paths.png")


# 7.13 Down-and-out call vs H
def fig_CDO_vs_H():
    Hs = np.linspace(40, 99, 50)
    C_bs, _, _ = bs_call(S0_RUN, K_RUN, R_RUN, SIG_RUN, T_RUN)
    lam = (R_RUN + 0.5 * SIG_RUN ** 2) / (SIG_RUN ** 2)
    CDOs = []
    for H in Hs:
        S_mirror = H * H / S0_RUN
        C_mirror, _, _ = bs_call(S_mirror, K_RUN, R_RUN, SIG_RUN, T_RUN)
        c_do = C_bs - (H / S0_RUN) ** (2 * lam) * C_mirror
        CDOs.append(max(c_do, 0.0))
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    ax.plot(Hs, CDOs, "-", color=BLUE, linewidth=2.5, label="$C^{DO}(H)$")
    ax.axhline(C_bs, color=RED, linewidth=1.5, linestyle="--",
               label=f"vanilla $C_0={C_bs:.2f}$")
    ax.set_xlabel("barrier $H$")
    ax.set_ylabel("price")
    ax.set_title("Down-and-out call: closed-form BS price vs barrier level")
    ax.legend()
    _save("ch07-CDO-vs-H.png")


# 7.14 Smile shapes under different models
def fig_smile_shapes():
    Ks = np.linspace(80, 120, 50)
    bs = np.full_like(Ks, SIG_RUN, dtype=float)
    lv = 0.20 + 0.0015 * (100 - Ks)
    hes = 0.18 + 0.0001 * (Ks - 100) ** 2
    jd = 0.21 + 0.001 * (100 - Ks) + 0.00005 * (Ks - 100) ** 2

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(Ks, bs, color=BLUE, linewidth=2.2, label="Black-Scholes (flat)")
    ax.plot(Ks, lv, color=ORANGE, linewidth=2.2, label="local vol (skew)")
    ax.plot(Ks, hes, color=GREEN, linewidth=2.2, label="Heston (convex smile)")
    ax.plot(Ks, jd, color=PURPLE, linewidth=2.2, label="Merton jump (smirk)")
    ax.set_xlabel("strike $K$")
    ax.set_ylabel("implied $\\sigma$")
    ax.set_title("Where the binomial limit goes next: model-implied smile shapes")
    ax.legend()
    _save("ch07-smile-shapes.png")


# 7.14 Sample paths under various models
def fig_paths_models():
    rng = np.random.default_rng(11)
    n = 252
    dt = T_RUN / n
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    ax = axes[0]
    for _ in range(8):
        Z = rng.standard_normal(n)
        logS = np.cumsum((R_RUN - 0.5 * SIG_RUN ** 2) * dt + SIG_RUN * math.sqrt(dt) * Z)
        ax.plot(np.arange(n) * dt, S0_RUN * np.exp(logS), color=BLUE, alpha=0.6, linewidth=1)
    ax.set_title("GBM (Black-Scholes)")
    ax.set_xlabel("$t$")
    ax.set_ylabel("$S_t$")

    ax = axes[1]
    for _ in range(8):
        v = 0.04 * np.ones(n)
        for i in range(1, n):
            v[i] = max(
                v[i - 1] + 2.0 * (0.04 - v[i - 1]) * dt
                + 0.3 * math.sqrt(max(v[i - 1], 0)) * math.sqrt(dt) * rng.standard_normal(),
                0,
            )
        Z = rng.standard_normal(n)
        logS = np.cumsum((R_RUN - 0.5 * v) * dt + np.sqrt(v) * math.sqrt(dt) * Z)
        ax.plot(np.arange(n) * dt, S0_RUN * np.exp(logS), color=GREEN, alpha=0.6, linewidth=1)
    ax.set_title("Heston (stochastic vol)")
    ax.set_xlabel("$t$")
    ax.set_ylabel("$S_t$")

    ax = axes[2]
    lam_j = 5
    for _ in range(8):
        Z = rng.standard_normal(n)
        N_j = rng.poisson(lam_j * dt, n)
        J = rng.normal(0, 0.10, n) * N_j
        logS = np.cumsum(
            (R_RUN - 0.5 * SIG_RUN ** 2 - lam_j * 0.005) * dt
            + SIG_RUN * math.sqrt(dt) * Z + J
        )
        ax.plot(np.arange(n) * dt, S0_RUN * np.exp(logS), color=PURPLE, alpha=0.6, linewidth=1)
    ax.set_title("Merton jump-diffusion")
    ax.set_xlabel("$t$")
    ax.set_ylabel("$S_t$")

    fig.suptitle("Where the binomial limit goes next: alternative price-process models",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    _save("ch07-paths-models.png")


# 7.15 Book arc timeline
def fig_arc_timeline():
    fig, ax = plt.subplots(figsize=(15, 5))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 6)
    ax.axis("off")
    chapters = [
        (0.3, "Ch 0", "Math\nprimer", BLUE),
        (2.4, "Ch 1", "1-period\nreplication", ORANGE),
        (4.5, "Ch 2", "Multi-period\nCRR tree", GREEN),
        (6.6, "Ch 3", "Coin-toss\nspace", PURPLE),
        (8.7, "Ch 4", "American\noptions", RED),
        (10.8, "Ch 5", "Reflection\n& path-dep", TEAL),
        (12.9, "Ch 6", "Rates &\ninterest", GOLD),
        (14.9, "Ch 7", "CRR $\\to$\nBlack-Scholes", MAGENTA),
    ]
    for x, lab, txt, c in chapters:
        ax.add_patch(FancyBboxPatch((x - 0.7, 1.6), 1.5, 2.0,
                                    boxstyle="round,pad=0.08",
                                    linewidth=1.8, facecolor=c, edgecolor=NAVY, alpha=0.85))
        ax.text(x + 0.05, 2.6, txt, ha="center", va="center", color="white",
                fontsize=10, fontweight="bold")
        ax.text(x + 0.05, 4.0, lab, ha="center", va="center", color=NAVY,
                fontsize=11, fontweight="bold")
    for i in range(len(chapters) - 1):
        x0 = chapters[i][0] + 0.8
        x1 = chapters[i + 1][0] - 0.7
        ax.add_patch(FancyArrowPatch((x0, 2.6), (x1, 2.6),
                                     arrowstyle="-|>", mutation_scale=18,
                                     linewidth=1.6, color=NAVY))
    ax.text(7.5, 5.3,
            "One coin flip $\\to$ Tree $\\to$ CRR$\\,(n\\to\\infty)$ + CLT $\\to$ Black-Scholes",
            ha="center", fontsize=14, fontweight="bold", color=NAVY)
    ax.text(7.5, 0.7,
            "Counting (Ch 0) + Replication (Ch 1) + Backward induction (Ch 2) + CLT (Ch 0) $=$ BS",
            ha="center", fontsize=11, color=GREY, style="italic")
    _save("ch07-arc-timeline.png")


if __name__ == "__main__":
    print(f"Writing Chapter 7 figures to: {FIG_DIR}")
    fig_roadmap()
    fig_C0_surface_3d()
    fig_tree_skeletons()
    fig_tildep_vs_n()
    fig_tildep_approx()
    fig_logS_histograms()
    fig_density_ridge_3d()
    fig_binom_vs_normal_4panel()
    fig_qq_plot()
    fig_Phi_d2_bars()
    fig_Phi_d2_convergence()
    fig_pmf_shift()
    fig_Phi_d1_d2_surface()
    fig_convergence_final()
    fig_BS_surface_3d()
    fig_error_loglog()
    fig_error_linear()
    fig_greeks_vs_S()
    fig_vega_surface_3d()
    fig_parity_payoff()
    fig_call_put_vs_K()
    fig_IV_smile()
    fig_IV_newton()
    fig_barrier_paths()
    fig_CDO_vs_H()
    fig_smile_shapes()
    fig_paths_models()
    fig_arc_timeline()
    print("Done.")
