"""
Chapter 2 figure builder for Binomial Option Pricing.

Run: python docs/binomial-option-pricing/_build_ch2_figs.py

Builds every figure referenced by Chapter-2-Multi-Period-Binomial.md.

Conventions:
    Toy lattice:        S0=4,   u=2,    d=1/2,  r=1/4,  ptilde=1/2
    Realistic lattice:  S0=100, u=1.10, d=0.90, r=2%,   ptilde=0.6

Style:
    matplotlib Agg backend, bright palette, 4-space indents.
    3-D plots use Poly3DCollection ridges (never 3-D bars).
"""
from __future__ import annotations

import math
import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm
from matplotlib.patches import FancyBboxPatch
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.special import comb
from scipy.stats import norm

FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG_DIR, exist_ok=True)
DPI = 200

# Palette
NAVY = "#0b1d3a"
BLUE = "#1f77b4"
ORANGE = "#ff7f0e"
GREEN = "#2ca02c"
RED = "#d62728"
PURPLE = "#9467bd"
GOLD = "#fbbf24"
TEAL = "#17becf"
GREY = "#666666"

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


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def crr_tree(S0, u, d, n):
    """Return matrix S where S[m, k] = S0 * u^k * d^(m-k), m=0..n, k=0..m."""
    S = np.zeros((n + 1, n + 1))
    for m in range(n + 1):
        for k in range(m + 1):
            S[m, k] = S0 * (u ** k) * (d ** (m - k))
    return S


def rollback(S, payoff_fn, r, p_tilde, n):
    """Backward induction; returns V matrix shape (n+1, n+1)."""
    V = np.zeros_like(S)
    for k in range(n + 1):
        V[n, k] = payoff_fn(S[n, k])
    disc = 1.0 / (1.0 + r)
    for m in range(n - 1, -1, -1):
        for k in range(m + 1):
            V[m, k] = disc * (p_tilde * V[m + 1, k + 1]
                              + (1 - p_tilde) * V[m + 1, k])
    return V


def crr_sum(S0, u, d, r, p, n, payoff_fn):
    """Closed-form CRR sum over leaves under RN measure."""
    total = 0.0
    for k in range(n + 1):
        ST = S0 * (u ** k) * (d ** (n - k))
        w = comb(n, k) * (p ** k) * ((1 - p) ** (n - k))
        total += w * payoff_fn(ST)
    return total / ((1 + r) ** n)


# ----------------------------------------------------------------------------
# 2.1 -- Recombining trees
# ----------------------------------------------------------------------------

def fig_recombining_tree():
    """Toy recombining tree, n=4, labelled with prices and binomial counts."""
    S0, u, d = 4.0, 2.0, 0.5
    n = 4
    S = crr_tree(S0, u, d, n)
    fig, ax = plt.subplots(figsize=(12, 7.5))
    for m in range(n):
        for k in range(m + 1):
            x0, y0 = m, math.log(S[m, k]) / math.log(2)
            x1u, y1u = m + 1, math.log(S[m + 1, k + 1]) / math.log(2)
            x1d, y1d = m + 1, math.log(S[m + 1, k]) / math.log(2)
            ax.plot([x0, x1u], [y0, y1u], color=GREEN, lw=2, alpha=0.7)
            ax.plot([x0, x1d], [y0, y1d], color=RED, lw=2, alpha=0.7)
    for m in range(n + 1):
        for k in range(m + 1):
            x = m
            y = math.log(S[m, k]) / math.log(2)
            ax.scatter([x], [y], s=520, color=NAVY, zorder=5)
            ax.text(x, y, f"{S[m, k]:.2f}", color="white", ha="center",
                    va="center", fontsize=8.5, fontweight="bold", zorder=6)
            if m == n:
                cnt = int(comb(n, k))
                ax.text(x + 0.22, y, f"$\\binom{{{n}}}{{{k}}}={cnt}$",
                        color=PURPLE, fontsize=11, va="center")
    ax.set_xlabel("time step $m$")
    ax.set_ylabel("$\\log_2 S$ (uniform spacing)")
    ax.set_title("Toy recombining tree "
                 "($S_0=4,\\ u=2,\\ d=\\frac{1}{2}$, $n=4$): "
                 "5 leaves, $\\binom{n}{k}$ paths each")
    ax.set_xticks(range(n + 1))
    ax.set_xlim(-0.3, n + 0.85)
    ax.grid(alpha=0.2)
    plt.tight_layout()
    _save("ch02-recombining-tree.png")


def fig_bushy_vs_recombining():
    """Side-by-side: bushy 2^n tree vs recombining n+1 tree."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.5))
    n = 4

    # Left: bushy 2^n leaves
    ax = axes[0]
    for m in range(n):
        n_parents = 2 ** m
        n_children = 2 ** (m + 1)
        for pidx in range(n_parents):
            x0 = m
            y0 = (pidx + 0.5) / n_parents
            for c in (2 * pidx, 2 * pidx + 1):
                x1 = m + 1
                y1 = (c + 0.5) / n_children
                col = GREEN if c % 2 == 1 else RED
                ax.plot([x0, x1], [y0, y1], color=col, lw=1, alpha=0.6)
    for m in range(n + 1):
        n_nodes = 2 ** m
        for pidx in range(n_nodes):
            ax.scatter([m], [(pidx + 0.5) / n_nodes],
                       s=18, color=NAVY, zorder=5)
    ax.set_title(f"Bushy tree: $2^{{{n}}}={2 ** n}$ leaves\n"
                 "(every path distinct)")
    ax.set_xlabel("time step")
    ax.set_yticks([])
    ax.set_xticks(range(n + 1))

    # Right: recombining
    ax = axes[1]
    S0, u, d = 4.0, 2.0, 0.5
    S = crr_tree(S0, u, d, n)
    for m in range(n):
        for k in range(m + 1):
            x0, y0 = m, math.log(S[m, k]) / math.log(2)
            x1u, y1u = m + 1, math.log(S[m + 1, k + 1]) / math.log(2)
            x1d, y1d = m + 1, math.log(S[m + 1, k]) / math.log(2)
            ax.plot([x0, x1u], [y0, y1u], color=GREEN, lw=2, alpha=0.7)
            ax.plot([x0, x1d], [y0, y1d], color=RED, lw=2, alpha=0.7)
    for m in range(n + 1):
        for k in range(m + 1):
            ax.scatter([m], [math.log(S[m, k]) / math.log(2)],
                       s=180, color=NAVY, zorder=5)
    ax.set_title(f"Recombining tree: ${n}+1={n + 1}$ leaves\n"
                 "($ud=du$ collapses paths)")
    ax.set_xlabel("time step")
    ax.set_ylabel("$\\log_2 S$")
    ax.set_xticks(range(n + 1))
    plt.tight_layout()
    _save("ch02-bushy-vs-recombining.png")


# ----------------------------------------------------------------------------
# 2.2 -- Backward induction
# ----------------------------------------------------------------------------

def _tree_plot(ax, S, V, n, title, S_fmt="{:.2f}", V_fmt="{:.3f}",
               V_color=ORANGE):
    for m in range(n):
        for k in range(m + 1):
            x0, y0 = m, math.log(S[m, k])
            x1u, y1u = m + 1, math.log(S[m + 1, k + 1])
            x1d, y1d = m + 1, math.log(S[m + 1, k])
            ax.plot([x0, x1u], [y0, y1u], color=GREEN, lw=1.5, alpha=0.55)
            ax.plot([x0, x1d], [y0, y1d], color=RED, lw=1.5, alpha=0.55)
    for m in range(n + 1):
        for k in range(m + 1):
            x = m
            y = math.log(S[m, k])
            ax.scatter([x], [y], s=560, color=NAVY, zorder=5)
            ax.text(x, y + 0.22, "$S=$" + S_fmt.format(S[m, k]),
                    ha="center", va="bottom", fontsize=9, color=NAVY)
            ax.text(x, y - 0.22, "$V=$" + V_fmt.format(V[m, k]),
                    ha="center", va="top", fontsize=9, color=V_color,
                    fontweight="bold")
    ax.set_xlabel("time step $m$")
    ax.set_ylabel("$\\ln S$")
    ax.set_title(title)
    ax.set_xticks(range(n + 1))
    ax.margins(y=0.18)


def fig_call_tree_st():
    """Toy n=2 call, K=5, rollback labelled at every node."""
    S0, u, d, r, p = 4.0, 2.0, 0.5, 0.25, 0.5
    n = 2
    K = 5.0
    S = crr_tree(S0, u, d, n)
    V = rollback(S, lambda x: max(x - K, 0.0), r, p, n)
    fig, ax = plt.subplots(figsize=(10, 6.5))
    _tree_plot(ax, S, V, n,
               f"Toy $n=2$ call $K={K:.0f}$: rollback gives "
               f"$V_0={V[0, 0]:.4f}$",
               V_color=ORANGE)
    plt.tight_layout()
    _save("ch02-call-tree-st.png")


def fig_put_tree_st():
    """Toy n=2 put, K=5, rollback labelled at every node."""
    S0, u, d, r, p = 4.0, 2.0, 0.5, 0.25, 0.5
    n = 2
    K = 5.0
    S = crr_tree(S0, u, d, n)
    V = rollback(S, lambda x: max(K - x, 0.0), r, p, n)
    Vcall = rollback(S, lambda x: max(x - K, 0.0), r, p, n)
    parity = Vcall[0, 0] - V[0, 0]
    fig, ax = plt.subplots(figsize=(10, 6.5))
    _tree_plot(ax, S, V, n,
               f"Toy $n=2$ put $K={K:.0f}$: $V_0={V[0, 0]:.4f}$ "
               f"(parity $C-P={parity:+.3f}$)",
               V_color=PURPLE)
    plt.tight_layout()
    _save("ch02-put-tree-st.png")


# ----------------------------------------------------------------------------
# 2.3 -- Self-financing replication
# ----------------------------------------------------------------------------

def fig_delta_tree():
    """Toy n=2 call with (Delta, B) at every non-terminal node."""
    S0, u, d, r, p = 4.0, 2.0, 0.5, 0.25, 0.5
    n = 2
    K = 5.0
    S = crr_tree(S0, u, d, n)
    V = rollback(S, lambda x: max(x - K, 0.0), r, p, n)
    fig, ax = plt.subplots(figsize=(12, 8))
    for m in range(n):
        for k in range(m + 1):
            x0, y0 = m, math.log(S[m, k])
            x1u, y1u = m + 1, math.log(S[m + 1, k + 1])
            x1d, y1d = m + 1, math.log(S[m + 1, k])
            ax.plot([x0, x1u], [y0, y1u], color=GREEN, lw=1.5, alpha=0.55)
            ax.plot([x0, x1d], [y0, y1d], color=RED, lw=1.5, alpha=0.55)
    for m in range(n + 1):
        for k in range(m + 1):
            x = m
            y = math.log(S[m, k])
            ax.scatter([x], [y], s=680, color=NAVY, zorder=5)
            ax.text(x, y + 0.25,
                    f"$S={S[m, k]:.2f}$, $V={V[m, k]:.3f}$",
                    ha="center", va="bottom", fontsize=9.5, color=NAVY)
            if m < n:
                Vu, Vd = V[m + 1, k + 1], V[m + 1, k]
                Su, Sd = S[m + 1, k + 1], S[m + 1, k]
                Delta = (Vu - Vd) / (Su - Sd)
                B = V[m, k] - Delta * S[m, k]
                ax.text(x, y - 0.28,
                        f"$\\Delta={Delta:+.3f}$\n$B={B:+.3f}$",
                        ha="center", va="top", fontsize=9.5, color=ORANGE,
                        fontweight="bold")
    ax.set_xlabel("time step $m$")
    ax.set_ylabel("$\\ln S$")
    ax.set_title("Toy $n=2$ call $K=5$: hedge $(\\Delta, B)$ "
                 "at every non-terminal node")
    ax.set_xticks(range(n + 1))
    ax.margins(y=0.18)
    plt.tight_layout()
    _save("ch02-delta-tree.png")


def fig_cashflow_arrows():
    """Cashflow audit for one path on Toy n=2 call."""
    S0, u, d, r, p = 4.0, 2.0, 0.5, 0.25, 0.5
    n = 2
    K = 5.0
    S = crr_tree(S0, u, d, n)
    V = rollback(S, lambda x: max(x - K, 0.0), r, p, n)
    D0 = (V[1, 1] - V[1, 0]) / (S[1, 1] - S[1, 0])
    B0 = V[0, 0] - D0 * S[0, 0]
    D1u = (V[2, 2] - V[2, 1]) / (S[2, 2] - S[2, 1])
    B1u = V[1, 1] - D1u * S[1, 1]
    D1d = (V[2, 1] - V[2, 0]) / (S[2, 1] - S[2, 0])
    B1d = V[1, 0] - D1d * S[1, 0]
    roll_up = D0 * S[1, 1] + (1 + r) * B0
    roll_dn = D0 * S[1, 0] + (1 + r) * B0

    fig, ax = plt.subplots(figsize=(14, 6.5))
    ax.set_xlim(-0.3, 5.1)
    ax.set_ylim(-0.6, 3.3)
    boxes = [
        (0.0, 1.5,
         f"Set up $t=0$\n$\\Delta_0={D0:.3f}$\n$B_0={B0:+.3f}$\n"
         f"Cost $=V_0={V[0, 0]:.3f}$"),
        (1.7, 2.7,
         f"UP: $S_1={S[1, 1]:.1f}$\nOld port "
         f"$={D0:.3f}\\cdot{S[1, 1]:.1f}+{1 + r:.2f}\\cdot{B0:+.3f}$\n"
         f"$={roll_up:.3f}=V_{{1,1}}$"),
        (3.5, 2.7,
         f"Re-hedge to\n$(\\Delta_{{1,1}}, B_{{1,1}})$\n"
         f"$=({D1u:.3f}, {B1u:+.3f})$"),
        (1.7, 0.3,
         f"DOWN: $S_1={S[1, 0]:.1f}$\nOld port "
         f"$={D0:.3f}\\cdot{S[1, 0]:.1f}+{1 + r:.2f}\\cdot{B0:+.3f}$\n"
         f"$={roll_dn:.3f}=V_{{1,0}}$"),
        (3.5, 0.3,
         f"Re-hedge to\n$(\\Delta_{{1,0}}, B_{{1,0}})$\n"
         f"$=({D1d:.3f}, {B1d:+.3f})$"),
    ]
    for (x, y, txt) in boxes:
        ax.add_patch(FancyBboxPatch((x, y - 0.45), 1.4, 0.9,
                                    boxstyle="round,pad=0.05",
                                    facecolor=GOLD, edgecolor=NAVY,
                                    alpha=0.4))
        ax.text(x + 0.70, y, txt, ha="center", va="center", fontsize=9)
    arrows = [
        (1.4, 1.5, 1.72, 2.7, GREEN),
        (1.4, 1.5, 1.72, 0.4, RED),
        (3.15, 2.7, 3.52, 2.7, NAVY),
        (3.15, 0.3, 3.52, 0.3, NAVY),
    ]
    for (x0, y0, x1, y1, c) in arrows:
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="->", color=c, lw=2))
    ax.text(2.4, -0.35,
            "Self-financing: every rebalance is paid for by the rolled-up "
            "old portfolio. No outside cash injected.",
            ha="center", fontsize=9.5, color=NAVY,
            bbox=dict(boxstyle="round", facecolor="white", edgecolor=NAVY))
    ax.set_axis_off()
    ax.set_title("Self-financing cashflow audit -- Toy $n=2$ call $K=5$")
    plt.tight_layout()
    _save("ch02-cashflow-arrows.png")


def fig_delta_3d():
    """Delta surface across (m, k) on RL n=5 call -- Poly3DCollection ridges."""
    S0, u, d, r, p = 100.0, 1.10, 0.90, 0.02, 0.6
    n = 5
    K = 100.0
    S = crr_tree(S0, u, d, n)
    V = rollback(S, lambda x: max(x - K, 0.0), r, p, n)
    Delta = np.full((n, n), np.nan)
    for m in range(n):
        for k in range(m + 1):
            Vu, Vd = V[m + 1, k + 1], V[m + 1, k]
            Su, Sd = S[m + 1, k + 1], S[m + 1, k]
            Delta[m, k] = (Vu - Vd) / (Su - Sd)

    fig = plt.figure(figsize=(12, 8.5))
    ax = fig.add_subplot(111, projection="3d")
    polys = []
    colors = []
    cmap = cm.get_cmap("coolwarm")

    # Build ridge polygons: for each (m, k) with all neighbours present.
    for m in range(n - 1):
        for k in range(m + 1):
            if k + 1 > m + 1:
                continue
            verts = [
                (m, k, Delta[m, k]),
                (m + 1, k, Delta[m + 1, k]),
                (m + 1, k + 1, Delta[m + 1, k + 1]),
            ]
            polys.append(verts)
            mid = (Delta[m, k] + Delta[m + 1, k]
                   + Delta[m + 1, k + 1]) / 3
            colors.append(cmap(mid))

    coll = Poly3DCollection(polys, alpha=0.85, edgecolor=NAVY,
                            linewidths=0.4)
    coll.set_facecolors(colors)
    ax.add_collection3d(coll)

    # Overlay node markers along the ridges
    for m in range(n):
        for k in range(m + 1):
            ax.scatter([m], [k], [Delta[m, k]],
                       color=NAVY, s=22, depthshade=False)

    ax.set_xlim(-0.5, n)
    ax.set_ylim(-0.5, n)
    ax.set_zlim(0, 1.05)
    ax.set_xlabel("step $m$", labelpad=10)
    ax.set_ylabel("up-count $k$", labelpad=10)
    ax.set_zlabel("$\\Delta_{m,k}$", labelpad=10)
    ax.set_title("Hedge ratio $\\Delta$ across the lattice -- "
                 "RL $n=5$, $K=100$ call")
    ax.view_init(elev=26, azim=-55)
    fig.subplots_adjust(left=0.05, right=0.92, top=0.94, bottom=0.06)
    _save("ch02-delta-3d.png")


# ----------------------------------------------------------------------------
# 2.4 -- CRR closed form
# ----------------------------------------------------------------------------

def fig_crr_stacked():
    """Stacked bars: payoff x RN weight x discount, leaf by leaf."""
    S0, u, d, r, p = 100.0, 1.10, 0.90, 0.02, 0.6
    n = 4
    K = 100.0
    leaves = [S0 * (u ** k) * (d ** (n - k)) for k in range(n + 1)]
    payoffs = [max(s - K, 0.0) for s in leaves]
    probs = [comb(n, k) * (p ** k) * ((1 - p) ** (n - k))
             for k in range(n + 1)]
    contribs = [pf * pr / ((1 + r) ** n)
                for pf, pr in zip(payoffs, probs)]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    x = np.arange(n + 1)
    labels = [f"$S_T={s:.1f}$\n$k={k}$"
              for k, s in enumerate(leaves)]

    axes[0].bar(x, payoffs, color=ORANGE, edgecolor=NAVY)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, fontsize=8)
    axes[0].set_title("Payoff $(S_T-K)^+$")
    axes[0].set_ylabel("value")

    axes[1].bar(x, probs, color=BLUE, edgecolor=NAVY)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, fontsize=8)
    axes[1].set_title("RN weight "
                      "$\\binom{n}{k}\\tilde p^k(1-\\tilde p)^{n-k}$")

    axes[2].bar(x, contribs, color=GREEN, edgecolor=NAVY)
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(labels, fontsize=8)
    axes[2].set_title(f"Discounted contribution "
                      f"(sum $={sum(contribs):.3f}$)")

    fig.suptitle("CRR sum: $V_0 = \\sum_k\\binom{n}{k}"
                 "\\tilde p^k(1-\\tilde p)^{n-k}"
                 "(S_0u^kd^{n-k}-K)^+ / (1+r)^n$",
                 fontsize=12)
    plt.tight_layout()
    _save("ch02-crr-stacked.png")


def fig_convergence_preview():
    """CRR RL call prices approach the Black-Scholes limit as n grows."""
    S0, K, r_ann, sigma, T = 100.0, 100.0, 0.02, 0.20, 1.0
    d1 = (math.log(S0 / K) + (r_ann + 0.5 * sigma ** 2) * T) \
        / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    BS = S0 * norm.cdf(d1) - K * math.exp(-r_ann * T) * norm.cdf(d2)

    ns = np.unique(np.round(np.logspace(0, 3.0, 28)).astype(int))
    vals = []
    for nn in ns:
        dt = T / nn
        u = math.exp(sigma * math.sqrt(dt))
        d = 1.0 / u
        rn = math.exp(r_ann * dt) - 1.0
        pq = (math.exp(r_ann * dt) - d) / (u - d)
        vals.append(crr_sum(S0, u, d, rn, pq, int(nn),
                            lambda x: max(x - K, 0.0)))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.semilogx(ns, vals, "o-", color=BLUE, label="CRR price")
    ax.axhline(BS, color=RED, ls="--", lw=2,
               label=f"Black-Scholes $={BS:.4f}$")
    ax.set_xlabel("steps $n$ (log scale)")
    ax.set_ylabel("call price $V_0$")
    ax.set_title("CRR convergence to Black-Scholes -- "
                 "RL ($\\sigma=20\\%$, $T=1$)")
    ax.legend()
    plt.tight_layout()
    _save("ch02-convergence.png")


# ----------------------------------------------------------------------------
# 2.5 -- Discounted martingale
# ----------------------------------------------------------------------------

def fig_discounted_tree():
    """Toy n=3 tree showing S_{m,k}/(1+r)^m collapsing to S_0."""
    S0, u, d, r, p = 4.0, 2.0, 0.5, 0.25, 0.5
    n = 3
    S = crr_tree(S0, u, d, n)

    fig, ax = plt.subplots(figsize=(12, 7.5))
    for m in range(n):
        for k in range(m + 1):
            x0, y0 = m, math.log(S[m, k] / (1 + r) ** m)
            x1 = m + 1
            y1u = math.log(S[m + 1, k + 1] / (1 + r) ** (m + 1))
            y1d = math.log(S[m + 1, k] / (1 + r) ** (m + 1))
            ax.plot([x0, x1], [y0, y1u], color=GREEN, lw=1.4, alpha=0.55)
            ax.plot([x0, x1], [y0, y1d], color=RED, lw=1.4, alpha=0.55)
    for m in range(n + 1):
        for k in range(m + 1):
            disc = S[m, k] / (1 + r) ** m
            ax.scatter([m], [math.log(disc)], s=620, color=NAVY, zorder=5)
            ax.text(m, math.log(disc), f"{disc:.2f}", color="white",
                    ha="center", va="center", fontsize=8.5,
                    fontweight="bold", zorder=6)
    ax.axhline(math.log(S0), color=GOLD, ls="--", lw=2,
               label=f"$\\ln S_0={math.log(S0):.3f}$ (RN mean of every column)")
    for m in range(n + 1):
        mean_disc = sum(comb(m, k) * (p ** k) * ((1 - p) ** (m - k))
                        * S[m, k] for k in range(m + 1)) / (1 + r) ** m
        ax.scatter([m + 0.15], [math.log(mean_disc)], marker="x", s=180,
                   color=ORANGE, zorder=7, linewidth=3)
    ax.set_xlabel("time step $m$")
    ax.set_ylabel("$\\ln(S_{m,k}/(1+r)^m)$")
    ax.set_title("Toy $n=3$ discounted tree: "
                 "RN-mean (orange x) stays at $S_0$")
    ax.legend(loc="lower left")
    ax.set_xticks(range(n + 1))
    plt.tight_layout()
    _save("ch02-discounted-tree.png")


# ----------------------------------------------------------------------------
# 2.6 -- Pricing many instruments
# ----------------------------------------------------------------------------

def fig_payoffs_5():
    """Payoff diagrams for six European structures."""
    K = 100.0
    S = np.linspace(60, 140, 400)
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.5))
    axes = axes.flatten()
    items = [
        ("Call $K=100$", np.maximum(S - K, 0), ORANGE),
        ("Put $K=100$", np.maximum(K - S, 0), PURPLE),
        ("Cash digital ($K=100$)", (S > K).astype(float), GREEN),
        ("Asset digital ($K=100$)", S * (S > K), BLUE),
        ("Forward $K=100$", S - K, RED),
        ("Bull spread $K_1=95, K_2=105$",
         np.maximum(S - 95, 0) - np.maximum(S - 105, 0), GOLD),
    ]
    for ax, (ttl, y, c) in zip(axes, items):
        ax.plot(S, y, color=c, lw=2.5)
        ax.axvline(K, color=NAVY, ls=":", lw=1, alpha=0.7)
        ax.set_title(ttl)
        ax.set_xlabel("$S_T$")
        ax.set_ylabel("payoff")
    plt.tight_layout()
    _save("ch02-payoffs-5.png")


def fig_bull_spread():
    """Bull spread = long call(K1) minus call(K2). Two rollbacks plus sum."""
    S0, u, d, r, p = 100.0, 1.10, 0.90, 0.02, 0.6
    n = 4
    S = crr_tree(S0, u, d, n)
    K1, K2 = 95.0, 105.0
    V1 = rollback(S, lambda x: max(x - K1, 0.0), r, p, n)
    V2 = rollback(S, lambda x: max(x - K2, 0.0), r, p, n)
    Vsp = V1 - V2

    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    panels = [
        (V1, f"Long call $K={K1:.0f}$", ORANGE),
        (V2, f"Short call $K={K2:.0f}$", RED),
        (Vsp, "Bull spread (difference)", GREEN),
    ]
    for ax, (V, ttl, c) in zip(axes, panels):
        for m in range(n):
            for k in range(m + 1):
                ax.plot([m, m + 1],
                        [math.log(S[m, k]), math.log(S[m + 1, k + 1])],
                        color=GREEN, alpha=0.3, lw=1)
                ax.plot([m, m + 1],
                        [math.log(S[m, k]), math.log(S[m + 1, k])],
                        color=RED, alpha=0.3, lw=1)
        for m in range(n + 1):
            for k in range(m + 1):
                ax.scatter([m], [math.log(S[m, k])], s=130, color=NAVY)
                ax.text(m, math.log(S[m, k]) - 0.05,
                        f"{V[m, k]:.2f}", ha="center", va="top",
                        fontsize=8, color=c, fontweight="bold")
        ax.set_title(ttl + f"\n$V_0={V[0, 0]:.3f}$")
        ax.set_xlabel("step")
        ax.set_ylabel("$\\ln S$")
        ax.set_xlim(-0.4, n + 0.4)
        ax.margins(y=0.08)
    plt.tight_layout()
    _save("ch02-bull-spread.png")


# ----------------------------------------------------------------------------
# 2.7 -- Greeks on a tree
# ----------------------------------------------------------------------------

def fig_greeks_tree():
    """Toy n=3 call: every node carries (V, Delta, Gamma)."""
    S0, u, d, r, p = 4.0, 2.0, 0.5, 0.25, 0.5
    n = 3
    K = 5.0
    S = crr_tree(S0, u, d, n)
    V = rollback(S, lambda x: max(x - K, 0.0), r, p, n)

    fig, ax = plt.subplots(figsize=(14, 8.5))
    for m in range(n):
        for k in range(m + 1):
            ax.plot([m, m + 1],
                    [math.log(S[m, k]), math.log(S[m + 1, k + 1])],
                    color=GREEN, lw=1.4, alpha=0.5)
            ax.plot([m, m + 1],
                    [math.log(S[m, k]), math.log(S[m + 1, k])],
                    color=RED, lw=1.4, alpha=0.5)
    for m in range(n + 1):
        for k in range(m + 1):
            x, y = m, math.log(S[m, k])
            ax.scatter([x], [y], s=220, color=NAVY, zorder=5)
            txt = f"$S={S[m, k]:.2f}$\n$V={V[m, k]:.3f}$"
            if m <= n - 1:
                Vu, Vd = V[m + 1, k + 1], V[m + 1, k]
                Su, Sd = S[m + 1, k + 1], S[m + 1, k]
                D = (Vu - Vd) / (Su - Sd)
                txt += f"\n$\\Delta={D:.3f}$"
            if m <= n - 2:
                Vuu = V[m + 2, k + 2]
                Vum = V[m + 2, k + 1]
                Vdd = V[m + 2, k]
                Suu = S[m + 2, k + 2]
                Sum_ = S[m + 2, k + 1]
                Sdd = S[m + 2, k]
                Du = (Vuu - Vum) / (Suu - Sum_)
                Dd = (Vum - Vdd) / (Sum_ - Sdd)
                G = (Du - Dd) / (0.5 * (Suu - Sdd))
                txt += f"\n$\\Gamma={G:.3f}$"
            # Anchor text to the right of the node so it never overlaps
            ax.text(x + 0.08, y, txt, ha="left", va="center",
                    fontsize=9, color=ORANGE, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.25",
                              facecolor="white", edgecolor=ORANGE,
                              alpha=0.85, linewidth=0.6))
    ax.set_xlabel("step $m$")
    ax.set_ylabel("$\\ln S$")
    ax.set_title("Toy $n=3$ call $K=5$: Greeks on the tree")
    ax.set_xticks(range(n + 1))
    ax.set_xlim(-0.3, n + 0.85)
    ax.margins(y=0.10)
    plt.tight_layout()
    _save("ch02-greeks-tree.png")


def fig_gamma_surface():
    """Gamma surface on RL n=8 call lattice -- Poly3DCollection ridges."""
    S0, u, d, r, p = 100.0, 1.10, 0.90, 0.02, 0.6
    n = 8
    K = 100.0
    S = crr_tree(S0, u, d, n)
    V = rollback(S, lambda x: max(x - K, 0.0), r, p, n)

    # Gamma at (m, k) for m <= n-2; index by (m, k).
    G = np.full((n - 1, n - 1), np.nan)
    lnS = np.full((n - 1, n - 1), np.nan)
    for m in range(n - 1):
        for k in range(m + 1):
            Vuu = V[m + 2, k + 2]
            Vum = V[m + 2, k + 1]
            Vdd = V[m + 2, k]
            Suu = S[m + 2, k + 2]
            Sum_ = S[m + 2, k + 1]
            Sdd = S[m + 2, k]
            Du = (Vuu - Vum) / (Suu - Sum_)
            Dd = (Vum - Vdd) / (Sum_ - Sdd)
            G[m, k] = (Du - Dd) / (0.5 * (Suu - Sdd))
            lnS[m, k] = math.log(S[m, k])

    fig = plt.figure(figsize=(12, 8.5))
    ax = fig.add_subplot(111, projection="3d")
    polys = []
    colors = []
    cmap = cm.get_cmap("magma")
    gmax = np.nanmax(G)

    for m in range(n - 2):
        for k in range(m + 1):
            if k + 1 > m + 1:
                continue
            verts = [
                (m, lnS[m, k], G[m, k]),
                (m + 1, lnS[m + 1, k], G[m + 1, k]),
                (m + 1, lnS[m + 1, k + 1], G[m + 1, k + 1]),
            ]
            polys.append(verts)
            mid = (G[m, k] + G[m + 1, k] + G[m + 1, k + 1]) / 3
            colors.append(cmap(mid / max(gmax, 1e-9)))

    coll = Poly3DCollection(polys, alpha=0.88, edgecolor=NAVY,
                            linewidths=0.3)
    coll.set_facecolors(colors)
    ax.add_collection3d(coll)

    # Mark each ridge node
    for m in range(n - 1):
        for k in range(m + 1):
            ax.scatter([m], [lnS[m, k]], [G[m, k]],
                       color=NAVY, s=18, depthshade=False)

    ax.set_xlim(0, n - 1)
    ax.set_ylim(np.nanmin(lnS), np.nanmax(lnS))
    ax.set_zlim(0, gmax * 1.1)
    ax.set_xlabel("step $m$", labelpad=12)
    ax.set_ylabel("$\\ln S$", labelpad=12)
    ax.set_zlabel("$\\Gamma$", labelpad=12)
    ax.set_title(f"Gamma surface -- RL $n={n}$, $K=100$ call "
                 "(ridge peaks near $S=K$)")
    ax.view_init(elev=26, azim=-55)
    fig.subplots_adjust(left=0.05, right=0.92, top=0.94, bottom=0.06)
    _save("ch02-gamma-surface.png")


def fig_gamma_vs_S():
    """Root-level lattice Gamma as a function of strike K, RL n=8 call.

    Mirrors the BS Gamma bell at $S_0=K$. Computed purely as a finite
    difference on the tree -- no calculus.
    """
    S0, u, d, r, p = 100.0, 1.10, 0.90, 0.02, 0.6
    n = 8
    Ks = np.linspace(70, 140, 36)
    gammas = []
    S = crr_tree(S0, u, d, n)
    for KK in Ks:
        V = rollback(S, lambda x: max(x - KK, 0.0), r, p, n)
        # Root Gamma uses level-1 deltas evaluated from level-2 children.
        Du = (V[2, 2] - V[2, 1]) / (S[2, 2] - S[2, 1])
        Dd = (V[2, 1] - V[2, 0]) / (S[2, 1] - S[2, 0])
        G0 = (Du - Dd) / (0.5 * (S[2, 2] - S[2, 0]))
        gammas.append(G0)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(Ks, gammas, "o-", color=PURPLE, lw=2.4,
            label="lattice $\\Gamma_0$")
    ax.axvline(S0, color=NAVY, ls=":", lw=1.4, alpha=0.7,
               label=f"$S_0={S0:.0f}$ (ATM)")
    ax.set_xlabel("strike $K$")
    ax.set_ylabel("$\\Gamma_0$")
    ax.set_title(f"Root Gamma vs strike -- RL $n={n}$ call "
                 "(peak at $K \\approx S_0$)")
    ax.legend()
    plt.tight_layout()
    _save("ch02-gamma-vs-S.png")


def fig_theta_lines():
    """Theta vs strike on RL call tree for several n."""
    S0, r, p, u, d = 100.0, 0.02, 0.6, 1.10, 0.90
    fig, ax = plt.subplots(figsize=(10, 6))
    for nn, c in zip([4, 6, 8, 10], [BLUE, GREEN, ORANGE, RED]):
        Ks = np.linspace(70, 140, 30)
        thetas = []
        for KK in Ks:
            S = crr_tree(S0, u, d, nn)
            V = rollback(S, lambda x: max(x - KK, 0.0), r, p, nn)
            theta0 = (V[2, 1] - V[0, 0]) / 2.0
            thetas.append(theta0)
        ax.plot(Ks, thetas, "o-", color=c, label=f"$n={nn}$", lw=2)
    ax.axvline(S0, color=NAVY, ls=":", lw=1, alpha=0.7, label="ATM")
    ax.set_xlabel("strike $K$")
    ax.set_ylabel("$\\Theta_0$ (per step)")
    ax.set_title("Theta vs strike -- RL call, several $n$")
    ax.legend()
    plt.tight_layout()
    _save("ch02-theta-lines.png")


# ----------------------------------------------------------------------------
# 2.8 -- Convergence
# ----------------------------------------------------------------------------

def fig_error_loglog():
    """Log-log absolute CRR -- BS error vs n, with slope -1 reference."""
    S0, K, r, sigma, T = 100.0, 100.0, 0.02, 0.20, 1.0
    d1 = (math.log(S0 / K) + (r + 0.5 * sigma ** 2) * T) \
        / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    BS = S0 * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)

    ns = np.unique(np.round(np.logspace(0.5, 3.0, 25)).astype(int))
    errs = []
    for nn in ns:
        dt = T / nn
        u = math.exp(sigma * math.sqrt(dt))
        d = 1.0 / u
        rn = math.exp(r * dt) - 1.0
        pq = (math.exp(r * dt) - d) / (u - d)
        v = crr_sum(S0, u, d, rn, pq, int(nn),
                    lambda x: max(x - K, 0.0))
        errs.append(abs(v - BS))

    fig, ax = plt.subplots(figsize=(10, 6.5))
    ax.loglog(ns, errs, "o-", color=BLUE, lw=2.2, markersize=6,
              label="$|V_n^{CRR}-V^{BS}|$")
    ref = errs[0] * (ns[0] / ns)
    ax.loglog(ns, ref, "--", color=RED, lw=2,
              label="slope $-1$ reference")
    ax.set_xlabel("steps $n$ (log scale)", fontsize=12)
    ax.set_ylabel("absolute error (log scale)", fontsize=12)
    ax.set_title(f"CRR convergence rate to BS (BS $={BS:.4f}$)",
                 fontsize=12)
    # Major + minor log grid for readability
    ax.grid(True, which="major", alpha=0.45, linestyle="-", linewidth=0.7)
    ax.grid(True, which="minor", alpha=0.18, linestyle=":", linewidth=0.5)
    ax.tick_params(axis="both", which="major", labelsize=10)
    # Move legend to lower-left so it does not sit on the descending data
    ax.legend(loc="lower left", fontsize=11, framealpha=0.95)
    plt.tight_layout()
    _save("ch02-error-loglog.png")


# ----------------------------------------------------------------------------
# 2.9 -- Path dependence
# ----------------------------------------------------------------------------

def fig_logS_overlay():
    """3 panels: histogram of ln(S_n/S_0) under RN measure, with normal limit.

    For each n in {10, 50, 200}:
      * Build CRR with sigma-matched u, d, p_tilde over T=1.
      * Compute the exact RN distribution of ln(S_n/S_0) on the lattice.
      * Plot as a bar histogram (bar width = grid spacing * 0.85, so bars do
        not overlap), overlay the CLT-implied normal density times bin width
        (so the curve and the discrete masses are on the same scale).
    """
    S0, r, sigma, T = 100.0, 0.02, 0.20, 1.0
    ns = [10, 50, 200]
    colors = [BLUE, ORANGE, GREEN]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5.2), sharey=False)
    for ax, nn, col in zip(axes, ns, colors):
        dt = T / nn
        u = math.exp(sigma * math.sqrt(dt))
        d = 1.0 / u
        p = (math.exp(r * dt) - d) / (u - d)
        ks = np.arange(nn + 1)
        logS = ks * math.log(u) + (nn - ks) * math.log(d)
        # Binomial PMF over k under risk-neutral measure
        log_pmf = (np.array([math.lgamma(nn + 1)
                             - math.lgamma(k + 1)
                             - math.lgamma(nn - k + 1) for k in ks])
                   + ks * math.log(p) + (nn - ks) * math.log(1 - p))
        pmf = np.exp(log_pmf)

        # Bar width = spacing between adjacent lattice points * 0.85
        spacing = (logS[-1] - logS[0]) / nn if nn > 0 else 1.0
        width = spacing * 0.85

        ax.bar(logS, pmf, width=width, color=col, alpha=0.55,
               edgecolor=NAVY, linewidth=0.4,
               label=f"lattice PMF, $n={nn}$")

        # CLT-implied normal density * bin width
        mu = nn * (p * math.log(u) + (1 - p) * math.log(d))
        var = nn * p * (1 - p) * (math.log(u) - math.log(d)) ** 2
        sd = math.sqrt(var)
        xs = np.linspace(logS[0] - 3 * sd / math.sqrt(max(nn, 1)),
                         logS[-1] + 3 * sd / math.sqrt(max(nn, 1)),
                         400)
        density = norm.pdf(xs, loc=mu, scale=sd) * spacing
        ax.plot(xs, density, color=RED, lw=2.2,
                label="CLT normal limit")

        ax.set_title(f"$n={nn}$")
        ax.set_xlabel("$\\ln(S_n/S_0)$")
        if ax is axes[0]:
            ax.set_ylabel("probability mass (bar) / scaled density (line)")
        ax.set_xlim(mu - 4 * sd, mu + 4 * sd)
        ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
        ax.grid(alpha=0.3)

    fig.suptitle("Histograms of $\\ln(S_n/S_0)$ under the risk-neutral "
                 "measure $\\tilde P$, with CLT normal overlay -- "
                 "CLT in action as $n$ grows",
                 fontsize=12)
    plt.tight_layout(rect=(0, 0, 1, 0.94))
    _save("ch02-logS-overlay.png")


def fig_bushy_asian():
    """All 8 paths of Toy n=3, highlighting two extreme Asian averages.

    Reduces visual clutter by:
      * lightening non-highlighted paths to alpha 0.28,
      * highlighting the min-average (DDD) and max-average (UUU) paths in
        BLUE / ORANGE with full opacity,
      * placing path labels at the right edge instead of a side-legend,
      * dropping numerical offsets that crowded the leaves.
    """
    S0, u, d = 4.0, 2.0, 0.5
    n = 3
    paths = []
    for omega in range(2 ** n):
        bits = [(omega >> (n - 1 - i)) & 1 for i in range(n)]
        prices = [S0]
        for b in bits:
            prices.append(prices[-1] * (u if b else d))
        avg = sum(prices) / (n + 1)
        paths.append((bits, prices, avg))

    # Pick highlight paths by extreme Asian average
    sorted_idx = sorted(range(len(paths)), key=lambda i: paths[i][2])
    lo_idx, hi_idx = sorted_idx[0], sorted_idx[-1]

    fig, ax = plt.subplots(figsize=(15, 8.5))
    xs = list(range(n + 1))

    # First pass: background paths
    for idx, (bits, prices, avg) in enumerate(paths):
        if idx in (lo_idx, hi_idx):
            continue
        ys = [math.log(p) for p in prices]
        ax.plot(xs, ys, "-", color=GREY, lw=1.3, alpha=0.28, zorder=2)

    # Second pass: highlighted extreme paths
    for idx, color in [(lo_idx, BLUE), (hi_idx, ORANGE)]:
        bits, prices, avg = paths[idx]
        ys = [math.log(p) for p in prices]
        word = "".join("U" if b else "D" for b in bits)
        ax.plot(xs, ys, "-o", color=color, lw=2.6, alpha=0.95,
                markersize=7, zorder=5,
                label=f"$\\omega={word}$, $\\bar S={avg:.2f}$")

    # Endpoint annotations for ALL paths at the rightmost step, stacked.
    leaf_groups = {}
    for idx, (bits, prices, avg) in enumerate(paths):
        leaf = round(prices[-1], 6)
        leaf_groups.setdefault(leaf, []).append((idx, bits, avg))
    for leaf, members in leaf_groups.items():
        y = math.log(leaf)
        # Show: leaf price and how many paths share it (Asian averages differ).
        ax.text(n + 0.10, y, f"$S_T={leaf:.2f}$  ({len(members)} path"
                f"{'s' if len(members) > 1 else ''})",
                ha="left", va="center", fontsize=9.5, color=NAVY)

    ax.set_xlabel("step $m$")
    ax.set_ylabel("$\\ln S$")
    ax.set_title("All 8 paths of Toy $n=3$ -- "
                 "Asian payoff depends on the path, not just the leaf "
                 "(extreme paths highlighted)")
    ax.legend(loc="upper left", fontsize=10, framealpha=0.92)
    ax.set_xticks(range(n + 1))
    ax.set_xlim(-0.3, n + 1.4)
    plt.tight_layout()
    _save("ch02-bushy-asian.png")


def fig_knockout_tree():
    """Up-and-out tree L=16 on Toy n=4: nodes that touch L are killed."""
    S0, u, d = 4.0, 2.0, 0.5
    n = 4
    L = 16.0
    S = crr_tree(S0, u, d, n)
    alive = S < L

    fig, ax = plt.subplots(figsize=(11, 7))
    for m in range(n):
        for k in range(m + 1):
            x0, y0 = m, math.log(S[m, k])
            x1u, y1u = m + 1, math.log(S[m + 1, k + 1])
            x1d, y1d = m + 1, math.log(S[m + 1, k])
            colu = GREEN if (alive[m + 1, k + 1] and alive[m, k]) else GREY
            cold = RED if (alive[m + 1, k] and alive[m, k]) else GREY
            au = 0.75 if (alive[m, k] and alive[m + 1, k + 1]) else 0.25
            ad = 0.75 if (alive[m, k] and alive[m + 1, k]) else 0.25
            ax.plot([x0, x1u], [y0, y1u], color=colu,
                    lw=2 if au > 0.4 else 1, alpha=au)
            ax.plot([x0, x1d], [y0, y1d], color=cold,
                    lw=2 if ad > 0.4 else 1, alpha=ad)
    for m in range(n + 1):
        for k in range(m + 1):
            col = NAVY if alive[m, k] else GREY
            a = 0.95 if alive[m, k] else 0.4
            ax.scatter([m], [math.log(S[m, k])], s=460,
                       color=col, zorder=5, alpha=a)
            ax.text(m, math.log(S[m, k]), f"{S[m, k]:.2f}",
                    color="white", ha="center", va="center",
                    fontsize=7.5, fontweight="bold", zorder=6, alpha=a)
    ax.axhline(math.log(L), color=GOLD, ls="--", lw=2,
               label=f"barrier $L={L:.0f}$")
    ax.set_xlabel("step $m$")
    ax.set_ylabel("$\\ln S$")
    ax.set_title(f"Toy $n={n}$ up-and-out call $L={L:.0f}$: "
                 "nodes $S \\geq L$ are killed (grey)")
    ax.set_xticks(range(n + 1))
    ax.legend(loc="lower right")
    plt.tight_layout()
    _save("ch02-knockout-tree.png")


# ----------------------------------------------------------------------------
if __name__ == "__main__":
    print("Building Chapter 2 figures...")
    fig_recombining_tree()
    fig_bushy_vs_recombining()
    fig_call_tree_st()
    fig_put_tree_st()
    fig_delta_tree()
    fig_cashflow_arrows()
    fig_delta_3d()
    fig_crr_stacked()
    fig_convergence_preview()
    fig_discounted_tree()
    fig_payoffs_5()
    fig_bull_spread()
    fig_greeks_tree()
    fig_gamma_surface()
    fig_gamma_vs_S()
    fig_theta_lines()
    fig_error_loglog()
    fig_logS_overlay()
    fig_bushy_asian()
    fig_knockout_tree()
    print("done.")
