"""
Chapter 4 figure builder for Binomial Option Pricing — American Derivatives.

Run: python docs/binomial-option-pricing/_build_ch4_figs.py

Toy lattice:     S0 = 4,   u = 2,    d = 1/2, r = 1/4, ptilde = 1/2
Realistic (RL):  S0 = 100, u = 1.10, d = 0.90, r = 2%,  ptilde = 0.6
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, Rectangle
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# ------------------------------------------------------------------ paths
FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG_DIR, exist_ok=True)
DPI = 200

# ------------------------------------------------------------------ palette
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

# ------------------------------------------------------------------ models
TOY = dict(S0=4.0, u=2.0, d=0.5, r=0.25, p=0.5)
RL  = dict(S0=100.0, u=1.10, d=0.90, r=0.02, p=0.6)


def _save(name: str, tight: bool = True) -> None:
    path = os.path.join(FIG_DIR, name)
    if tight:
        plt.savefig(path, dpi=DPI, bbox_inches="tight")
    else:
        plt.savefig(path, dpi=DPI)
    plt.close()
    print(f"  wrote {name}")


def _tree_nodes(S0, u, d, n):
    """Return dict {(k,j): S} where j = number of up moves so far."""
    nodes = {}
    for k in range(n + 1):
        for j in range(k + 1):
            nodes[(k, j)] = S0 * (u ** j) * (d ** (k - j))
    return nodes


def _node_xy(k, j, n):
    """Layout: k on x, (2j-k) on y (centered binomial)."""
    return k, (2 * j - k)


def _draw_tree_edges(ax, n, color=GREY, lw=1.0, alpha=0.5):
    for k in range(n):
        for j in range(k + 1):
            x0, y0 = _node_xy(k, j, n)
            x1u, y1u = _node_xy(k + 1, j + 1, n)
            x1d, y1d = _node_xy(k + 1, j, n)
            ax.plot([x0, x1u], [y0, y1u], color=color, lw=lw, alpha=alpha, zorder=1)
            ax.plot([x0, x1d], [y0, y1d], color=color, lw=lw, alpha=alpha, zorder=1)


def _american_put(S0, u, d, r, p, K, n):
    """Return V[(k,j)], C[(k,j)] (continuation), exer set."""
    disc = 1.0 / (1.0 + r)
    V = {}
    C = {}
    exer = set()
    for j in range(n + 1):
        S = S0 * (u ** j) * (d ** (n - j))
        V[(n, j)] = max(K - S, 0.0)
    for k in range(n - 1, -1, -1):
        for j in range(k + 1):
            S = S0 * (u ** j) * (d ** (k - j))
            cont = disc * (p * V[(k + 1, j + 1)] + (1 - p) * V[(k + 1, j)])
            intr = max(K - S, 0.0)
            C[(k, j)] = cont
            if intr > cont + 1e-12:
                V[(k, j)] = intr
                exer.add((k, j))
            else:
                V[(k, j)] = cont
    return V, C, exer


def _american_call(S0, u, d, r, p, K, n, q=0.0):
    """American call with proportional per-period dividend yield q."""
    disc = 1.0 / (1.0 + r)
    V = {}
    C = {}
    exer = set()
    for j in range(n + 1):
        S = S0 * (u ** j) * (d ** (n - j)) * ((1.0 - q) ** n)
        V[(n, j)] = max(S - K, 0.0)
    for k in range(n - 1, -1, -1):
        for j in range(k + 1):
            S = S0 * (u ** j) * (d ** (k - j)) * ((1.0 - q) ** k)
            cont = disc * (p * V[(k + 1, j + 1)] + (1 - p) * V[(k + 1, j)])
            intr = max(S - K, 0.0)
            C[(k, j)] = cont
            if intr > cont + 1e-12:
                V[(k, j)] = intr
                exer.add((k, j))
            else:
                V[(k, j)] = cont
    return V, C, exer


def _european_put(S0, u, d, r, p, K, n):
    disc = 1.0 / (1.0 + r)
    V = {}
    for j in range(n + 1):
        S = S0 * (u ** j) * (d ** (n - j))
        V[(n, j)] = max(K - S, 0.0)
    for k in range(n - 1, -1, -1):
        for j in range(k + 1):
            V[(k, j)] = disc * (p * V[(k + 1, j + 1)] + (1 - p) * V[(k + 1, j)])
    return V


def _european_call(S0, u, d, r, p, K, n):
    disc = 1.0 / (1.0 + r)
    V = {}
    for j in range(n + 1):
        S = S0 * (u ** j) * (d ** (n - j))
        V[(n, j)] = max(S - K, 0.0)
    for k in range(n - 1, -1, -1):
        for j in range(k + 1):
            V[(k, j)] = disc * (p * V[(k + 1, j + 1)] + (1 - p) * V[(k + 1, j)])
    return V


# ------------------------------------------------------------------ figures

def fig_eu_vs_am_timeline():
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.set_xlim(-0.5, 6.5)
    ax.set_ylim(-1.4, 1.6)
    ax.axis("off")
    ax.plot([0, 6], [0.8, 0.8], color=NAVY, lw=2)
    for k in range(7):
        ax.plot(k, 0.8, "o", color=GREY, ms=7)
    ax.plot(6, 0.8, "s", color=RED, ms=14)
    ax.text(6, 1.15, "exercise (forced)", color=RED, ha="center", fontsize=10)
    ax.text(-0.3, 0.8, "European", ha="right", va="center", fontweight="bold", color=NAVY)
    ax.plot([0, 6], [-0.6, -0.6], color=NAVY, lw=2)
    for k in range(7):
        ax.plot(k, -0.6, "s", color=GREEN, ms=12)
    ax.text(3, -1.05, "exercise allowed at any node", color=GREEN, ha="center", fontsize=10)
    ax.text(-0.3, -0.6, "American", ha="right", va="center", fontweight="bold", color=NAVY)
    ax.set_title("European vs American: one date vs a menu of dates", color=NAVY, fontsize=12)
    _save("ch04-eu-vs-am-timeline.png")


def fig_eu_vs_am_bars():
    n = 3
    Ks = list(range(2, 8))
    eu_vals, am_vals = [], []
    for K in Ks:
        eu = _european_put(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
        V, _, _ = _american_put(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
        eu_vals.append(eu[(0, 0)])
        am_vals.append(V[(0, 0)])
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(Ks))
    w = 0.38
    ax.bar(x - w / 2, eu_vals, w, color=BLUE, label="European")
    ax.bar(x + w / 2, am_vals, w, color=ORANGE, label="American")
    for xi, e, a in zip(x, eu_vals, am_vals):
        if a - e > 1e-9:
            ax.annotate("", xy=(xi + w / 2, a), xytext=(xi + w / 2, e),
                        arrowprops=dict(arrowstyle="->", color=RED, lw=1.4))
    ax.set_xticks(x)
    ax.set_xticklabels([f"K={K}" for K in Ks])
    ax.set_ylabel(r"$V_0$ (Toy put)")
    ax.set_title("Toy puts: American weakly dominates European", color=NAVY)
    ax.legend()
    _save("ch04-eu-vs-am-bars.png")


def fig_tau_shaded():
    n = 3
    fig, ax = plt.subplots(figsize=(9, 6))
    nodes = _tree_nodes(TOY["S0"], TOY["u"], TOY["d"], n)
    _draw_tree_edges(ax, n)
    fired = set()
    later = set()
    cont = set()
    for path in range(2 ** n):
        j = 0
        stopped = False
        for k in range(n + 1):
            S = nodes[(k, j)]
            if not stopped and S <= 2.0:
                fired.add((k, j))
                stopped = True
            elif stopped:
                if S <= 2.0:
                    later.add((k, j))
                else:
                    cont.add((k, j))
            else:
                cont.add((k, j))
            if k < n:
                bit = (path >> (n - 1 - k)) & 1
                j += bit
    later -= fired
    cont -= fired
    cont -= later
    for (k, j), S in nodes.items():
        x, y = _node_xy(k, j, n)
        if (k, j) in fired:
            color = RED
        elif (k, j) in later:
            color = ORANGE
        else:
            color = BLUE
        ax.plot(x, y, "o", color=color, ms=22, zorder=3)
        ax.text(x, y, f"{S:g}", ha="center", va="center", color="white",
                fontsize=10, fontweight="bold", zorder=4)
    ax.set_xlim(-0.5, n + 0.7)
    ax.set_ylim(-n - 1, n + 1)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title(r"Toy tree: $\tau$ fires (red) at first $S \leq 2$", color=NAVY)
    from matplotlib.lines import Line2D
    ax.legend(handles=[
        Line2D([0], [0], marker="o", color="w", markerfacecolor=RED, markersize=10, label=r"$\tau$ fires"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=BLUE, markersize=10, label="continuation"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=ORANGE, markersize=10, label="already stopped"),
    ], loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0)
    _save("ch04-tau-shaded.png")


def fig_lookahead_violation():
    n = 3
    fig, ax = plt.subplots(figsize=(9, 5))
    nodes = _tree_nodes(TOY["S0"], TOY["u"], TOY["d"], n)
    _draw_tree_edges(ax, n, alpha=0.25)
    path_a = [(0, 0), (1, 1), (2, 2), (3, 2)]
    path_b = [(0, 0), (1, 1), (2, 1), (3, 1)]
    xa = [_node_xy(k, j, n) for (k, j) in path_a]
    xb = [_node_xy(k, j, n) for (k, j) in path_b]
    ax.plot([p[0] for p in xa], [p[1] for p in xa], color=BLUE, lw=2.5, label="path A")
    ax.plot([p[0] for p in xb], [p[1] for p in xb], color=ORANGE, lw=2.5, label="path B")
    for (k, j) in set(path_a + path_b):
        x, y = _node_xy(k, j, n)
        ax.plot(x, y, "o", color=NAVY, ms=14, zorder=3)
        ax.text(x, y, f"{nodes[(k, j)]:g}", ha="center", va="center",
                color="white", fontsize=9, fontweight="bold", zorder=4)
    x1, y1 = _node_xy(1, 1, n)
    ax.add_patch(plt.Circle((x1, y1), 0.45, fill=False, ec=RED, lw=2.5, zorder=5))
    ax.annotate("same info at k=1\nbut different future",
                xy=(x1, y1), xytext=(x1 + 0.6, y1 + 1.5),
                arrowprops=dict(arrowstyle="->", color=RED), color=RED, fontsize=10)
    ax.set_xlim(-0.5, n + 1.5)
    ax.set_ylim(-n - 1, n + 1)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title("Lookahead violation: stopping rule cannot peek at future", color=NAVY)
    ax.legend()
    _save("ch04-lookahead-violation.png")


def fig_snell_tree():
    n = 3
    K = 5.0
    V, C, exer = _american_put(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
    nodes = _tree_nodes(TOY["S0"], TOY["u"], TOY["d"], n)
    fig, ax = plt.subplots(figsize=(11, 7))
    _draw_tree_edges(ax, n)
    for (k, j), S in nodes.items():
        x, y = _node_xy(k, j, n)
        g = max(K - S, 0.0)
        v = V[(k, j)]
        is_ex = (k, j) in exer
        color = RED if is_ex else BLUE
        ax.add_patch(Rectangle((x - 0.32, y - 0.45), 0.64, 0.9,
                               facecolor=color, edgecolor=NAVY, alpha=0.85, zorder=3))
        ax.text(x, y + 0.28, f"S={S:g}", ha="center", va="center",
                color="white", fontsize=8, fontweight="bold", zorder=4)
        ax.text(x, y + 0.02, f"g={g:g}", ha="center", va="center",
                color="white", fontsize=8, zorder=4)
        ax.text(x, y - 0.26, f"V={v:.2f}", ha="center", va="center",
                color="white", fontsize=8, fontweight="bold", zorder=4)
    ax.set_xlim(-0.6, n + 0.8)
    ax.set_ylim(-n - 1.2, n + 1.2)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title(rf"Toy put $K={K:g}$: Snell envelope (red = exercise)", color=NAVY)
    _save("ch04-snell-tree.png")


def fig_V_vs_g():
    n = 3
    K = 5.0
    V, _, _ = _american_put(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
    path = [(k, 0) for k in range(n + 1)]
    Ss = [TOY["S0"] * TOY["u"] ** j * TOY["d"] ** (k - j) for (k, j) in path]
    gs = [max(K - S, 0.0) for S in Ss]
    Vs = [V[(k, j)] for (k, j) in path]
    fig, ax = plt.subplots(figsize=(9, 5))
    ks = list(range(n + 1))
    ax.plot(ks, Vs, "o-", color=BLUE, lw=2.5, ms=10, label=r"$V_k$ (envelope)")
    ax.plot(ks, gs, "s--", color=ORANGE, lw=2, ms=9, label=r"$g(S_k)$ (intrinsic)")
    for k, (v, g) in enumerate(zip(Vs, gs)):
        if abs(v - g) < 1e-9 and g > 0:
            ax.axvline(k, color=RED, ls=":", lw=1.5)
            ax.text(k + 0.05, max(Vs) * 0.85, rf"$\tau^* = {k}$", color=RED)
            break
    ax.fill_between(ks, gs, Vs, color=GOLD, alpha=0.4, label="continuation premium")
    ax.set_xlabel("k")
    ax.set_ylabel("value")
    ax.set_title("Path TT: envelope above intrinsic until touch", color=NAVY)
    ax.legend()
    _save("ch04-V-vs-g.png")


def fig_Vk_3d():
    """Snell-envelope ridges: one filled polygon per time level k.

    x-axis = (2j - k) (centered lattice position); y-axis = k (time, depth);
    z-axis = V_k(j). Each level becomes a closed Poly3DCollection ridge,
    with markers on top distinguishing continuation (green) vs exercise (red).
    """
    n = 3
    K = 100.0
    V, _, exer = _american_put(RL["S0"], RL["u"], RL["d"], RL["r"], RL["p"], K, n)
    fig = plt.figure(figsize=(13, 9))
    ax = fig.add_subplot(111, projection="3d")

    vmax = max(V.values())
    polys = []
    face_colors = []
    edge_colors = []
    for k in range(n + 1):
        xs = [2 * j - k for j in range(k + 1)]
        zs = [V[(k, j)] for j in range(k + 1)]
        # Build a closed ridge polygon at y=k: start at (xs[0], 0), trace top, back to (xs[-1], 0).
        verts = [(xs[0], k, 0.0)]
        for x, z in zip(xs, zs):
            verts.append((x, k, z))
        verts.append((xs[-1], k, 0.0))
        polys.append(verts)
        # Color the ridge: orange if this level contains any optimal-exercise node, else teal.
        has_exer = any((k, j) in exer for j in range(k + 1))
        face_colors.append(ORANGE if has_exer else TEAL)
        edge_colors.append(NAVY)

    coll = Poly3DCollection(polys, facecolors=face_colors, edgecolors=edge_colors,
                            alpha=0.55, linewidths=1.4)
    ax.add_collection3d(coll)

    # Overlay node markers on top of the ridges (continuation vs exercise).
    for (k, j), v in V.items():
        x = 2 * j - k
        is_exer = (k, j) in exer and v > 1e-9
        ax.scatter([x], [k], [v],
                   color=RED if is_exer else GREEN,
                   edgecolor=NAVY, s=70, depthshade=False, zorder=5)

    # Vertical stems from baseline to node value, for legibility.
    for (k, j), v in V.items():
        if v <= 1e-9:
            continue
        x = 2 * j - k
        ax.plot([x, x], [k, k], [0.0, v], color=NAVY, lw=0.8, alpha=0.6, zorder=4)

    ax.set_xlim(-n - 0.6, n + 0.6)
    ax.set_ylim(-0.3, n + 0.3)
    ax.set_zlim(0, vmax * 1.15 + 0.1)
    ax.set_xlabel(r"net ups $2j - k$", labelpad=12, fontsize=11)
    ax.set_ylabel(r"time level $k$", labelpad=12, fontsize=11)
    ax.set_zlabel(r"$V_k$", labelpad=10, fontsize=12)
    ax.set_yticks(list(range(n + 1)))
    ax.set_title(
        rf"Snell envelope $V_k$ for realistic put ($K={K:g}$, $n={n}$): "
        r"ridges per level, red dot $=$ exercise",
        color=NAVY, pad=18, fontsize=13,
    )
    ax.view_init(elev=22, azim=-58)

    # Legend (placed in upper-left of figure to avoid the data ridges).
    legend_handles = [
        plt.Line2D([0], [0], marker="o", linestyle="",
                   markerfacecolor=GREEN, markeredgecolor=NAVY, markersize=10,
                   label="continuation node"),
        plt.Line2D([0], [0], marker="o", linestyle="",
                   markerfacecolor=RED, markeredgecolor=NAVY, markersize=10,
                   label="optimal-exercise node"),
        plt.Line2D([0], [0], marker="s", linestyle="",
                   markerfacecolor=ORANGE, markeredgecolor=NAVY, alpha=0.55, markersize=12,
                   label=r"level contains exercise"),
        plt.Line2D([0], [0], marker="s", linestyle="",
                   markerfacecolor=TEAL, markeredgecolor=NAVY, alpha=0.55, markersize=12,
                   label=r"level is pure continuation"),
    ]
    ax.legend(handles=legend_handles, loc="upper left", bbox_to_anchor=(0.0, 0.95),
              fontsize=10, framealpha=0.92)

    fig.tight_layout()
    _save("ch04-Vk-3d.png")


def fig_tau_star_paths():
    n = 3
    K = 5.0
    V, _, exer = _american_put(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
    paths = [
        ("HHH", [(0, 0), (1, 1), (2, 2), (3, 3)]),
        ("HHT", [(0, 0), (1, 1), (2, 2), (3, 2)]),
        ("HTT", [(0, 0), (1, 1), (2, 1), (3, 1)]),
        ("TTT", [(0, 0), (1, 0), (2, 0), (3, 0)]),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for ax, (name, path) in zip(axes.flat, paths):
        Ss = [TOY["S0"] * TOY["u"] ** j * TOY["d"] ** (k - j) for (k, j) in path]
        gs = [max(K - S, 0.0) for S in Ss]
        Vs = [V[(k, j)] for (k, j) in path]
        ks = list(range(n + 1))
        ax.plot(ks, Vs, "o-", color=BLUE, lw=2.2, label=r"$V_k$")
        ax.plot(ks, gs, "s--", color=ORANGE, lw=1.8, label=r"$g(S_k)$")
        tstar = None
        for k in ks:
            if abs(Vs[k] - gs[k]) < 1e-9 and gs[k] > 0:
                tstar = k
                break
        if tstar is None and gs[-1] > 0 and abs(Vs[-1] - gs[-1]) < 1e-9:
            tstar = n
        if tstar is not None:
            ax.axvline(tstar, color=RED, ls="--", lw=1.5)
            ax.text(tstar + 0.05, max(Vs + gs) * 0.9 + 0.01, rf"$\tau^*={tstar}$", color=RED)
        ax.set_title(f"path {name}", color=NAVY)
        ax.set_xlabel("k")
        ax.legend(fontsize=9)
    fig.suptitle(r"Four paths: $V_k$ vs $g(S_k)$ — touch marks $\tau^*$", color=NAVY)
    fig.tight_layout()
    _save("ch04-tau-star-paths.png")


def fig_stopped_mart():
    n = 3
    K = 5.0
    V, _, exer = _american_put(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
    disc = 1.0 / (1.0 + TOY["r"])
    paths = [
        ("HHH", [(0, 0), (1, 1), (2, 2), (3, 3)]),
        ("HHT", [(0, 0), (1, 1), (2, 2), (3, 2)]),
        ("HTT", [(0, 0), (1, 1), (2, 1), (3, 1)]),
        ("TTT", [(0, 0), (1, 0), (2, 0), (3, 0)]),
    ]
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = [BLUE, ORANGE, GREEN, PURPLE]
    ks = list(range(n + 1))
    stopped_curves = []
    for (name, path), col in zip(paths, colors):
        Ss = [TOY["S0"] * TOY["u"] ** j * TOY["d"] ** (k - j) for (k, j) in path]
        gs = [max(K - S, 0.0) for S in Ss]
        Vs = [V[(k, j)] for (k, j) in path]
        tstar = n
        for k in ks:
            if abs(Vs[k] - gs[k]) < 1e-9 and gs[k] > 0:
                tstar = k
                break
        Y = []
        for k in ks:
            kk = min(k, tstar)
            Y.append((disc ** kk) * Vs[kk])
        stopped_curves.append(Y)
        ax.plot(ks, Y, "o-", color=col, lw=2, label=f"path {name}")
    avg = np.mean(stopped_curves, axis=0)
    ax.plot(ks, avg, "D--", color=RED, lw=2.5, label=r"average $= V_0$")
    ax.set_xlabel("k")
    ax.set_ylabel(r"$(1+r)^{-k} V_{k \wedge \tau^*}$")
    ax.set_title(r"Stopped discounted envelope: flat past $\tau^*$, average $= V_0$", color=NAVY)
    ax.legend(fontsize=9)
    _save("ch04-stopped-mart.png")


def _frontier_tree_plot(ax, S0, u, d, r, p, K, n, title):
    V, C, exer = _american_put(S0, u, d, r, p, K, n)
    nodes = _tree_nodes(S0, u, d, n)
    _draw_tree_edges(ax, n)
    for (k, j), S in nodes.items():
        x, y = _node_xy(k, j, n)
        if k == n:
            color = RED if max(K - S, 0.0) > 0 else GREEN
        else:
            color = RED if (k, j) in exer else GREEN
        ax.plot(x, y, "o", color=color, ms=20, zorder=3)
        ax.text(x, y, f"{S:.1f}" if S < 10 else f"{S:.0f}",
                ha="center", va="center", color="white",
                fontsize=8, fontweight="bold", zorder=4)
    ax.set_xlim(-0.5, n + 0.7)
    ax.set_ylim(-n - 1, n + 1)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title(title, color=NAVY)


def fig_frontier_st():
    n = 3
    fig, ax = plt.subplots(figsize=(9, 6))
    _frontier_tree_plot(ax, TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], 5.0, n,
                        "Toy put K=5: green=continue, red=exercise")
    _save("ch04-frontier-st.png")


def fig_frontier_rl():
    n = 3
    fig, ax = plt.subplots(figsize=(9, 6))
    _frontier_tree_plot(ax, RL["S0"], RL["u"], RL["d"], RL["r"], RL["p"], 100.0, n,
                        "Realistic put K=100, n=3: green=continue, red=exercise")
    _save("ch04-frontier-rl.png")


def fig_frontier_3d():
    n = 10
    K = 100.0
    V, _, exer = _american_put(RL["S0"], RL["u"], RL["d"], RL["r"], RL["p"], K, n)
    fig = plt.figure(figsize=(13, 9))
    ax = fig.add_subplot(111, projection="3d")
    polys = []
    for (k, j) in exer:
        S = RL["S0"] * RL["u"] ** j * RL["d"] ** (k - j)
        x0, x1 = k - 0.4, k + 0.4
        z0, z1 = 0.0, S
        y = 2 * j - k
        face = [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)]
        polys.append(face)
    coll = Poly3DCollection(polys, facecolors=RED, edgecolors=NAVY, alpha=0.7, linewidths=0.4)
    ax.add_collection3d(coll)
    cx, cy, cz = [], [], []
    for (k, j), v in V.items():
        if (k, j) in exer or k == n:
            continue
        S = RL["S0"] * RL["u"] ** j * RL["d"] ** (k - j)
        cx.append(k)
        cy.append(2 * j - k)
        cz.append(S)
    ax.scatter(cx, cy, cz, color=GREEN, s=22, depthshade=True)
    ax.set_xlim(0, n)
    ax.set_ylim(-n, n)
    ax.set_zlim(0, max(RL["S0"] * RL["u"] ** n, K) * 1.1)
    ax.set_xlabel("k", labelpad=10)
    ax.set_ylabel("2j - k", labelpad=10)
    ax.set_zlabel("S", labelpad=10)
    ax.set_title(rf"Realistic put frontier in 3-D (n={n}): red wall = exercise", color=NAVY, pad=20)
    fig.tight_layout()
    _save("ch04-frontier-3d.png", tight=False)


def fig_frontier_r_compare():
    n = 4
    K = 100.0
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    for ax, r, lbl in zip(axes, [0.0, 0.05], ["r = 0%", "r = 5%"]):
        _frontier_tree_plot(ax, RL["S0"], RL["u"], RL["d"], r, RL["p"], K, n,
                            f"Realistic put K=100, n=4, {lbl}")
    fig.suptitle("Higher r enlarges the exercise region", color=NAVY, fontsize=13)
    fig.tight_layout()
    _save("ch04-frontier-r-compare.png")


def fig_call_tree_all_green():
    n = 3
    K = 5.0
    V, C, exer = _american_call(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n, q=0.0)
    nodes = _tree_nodes(TOY["S0"], TOY["u"], TOY["d"], n)
    fig, ax = plt.subplots(figsize=(9, 6))
    _draw_tree_edges(ax, n)
    for (k, j), S in nodes.items():
        x, y = _node_xy(k, j, n)
        if k == n:
            color = RED if max(S - K, 0.0) > 0 else GREEN
        else:
            color = RED if (k, j) in exer else GREEN
        ax.plot(x, y, "o", color=color, ms=20, zorder=3)
        ax.text(x, y, f"{S:g}", ha="center", va="center", color="white",
                fontsize=9, fontweight="bold", zorder=4)
    ax.set_xlim(-0.5, n + 0.7)
    ax.set_ylim(-n - 1, n + 1)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title("Toy call K=5, no dividends: never exercise early", color=NAVY)
    _save("ch04-call-tree-all-green.png")


def fig_call_tree_with_div():
    n = 3
    K = 4.0
    q = 0.10
    V, C, exer = _american_call(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n, q=q)
    fig, ax = plt.subplots(figsize=(11, 7))
    _draw_tree_edges(ax, n)
    for k in range(n + 1):
        for j in range(k + 1):
            S = TOY["S0"] * TOY["u"] ** j * TOY["d"] ** (k - j) * (1 - q) ** k
            x, y = _node_xy(k, j, n)
            if k == n:
                color = RED if max(S - K, 0.0) > 0 else GREEN
            else:
                color = RED if (k, j) in exer else GREEN
            ax.plot(x, y, "o", color=color, ms=34, zorder=3)
            ax.text(x, y, f"{S:.2f}", ha="center", va="center",
                    color="white", fontsize=7, fontweight="bold", zorder=4)
    ax.set_xlim(-0.5, n + 0.7)
    ax.set_ylim(-n - 1, n + 1)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title("Toy call K=4 with 10% dividend: early exercise emerges", color=NAVY)
    _save("ch04-call-tree-with-div.png")


def fig_am_eu_diff_vs_div():
    n = 4
    K = 100.0
    qs = np.linspace(0.0, 0.10, 21)
    gaps = []
    for q in qs:
        amV, _, _ = _american_call(RL["S0"], RL["u"], RL["d"], RL["r"], RL["p"], K, n, q=q)
        disc = 1.0 / (1.0 + RL["r"])
        Veu = {}
        for j in range(n + 1):
            S = RL["S0"] * RL["u"] ** j * RL["d"] ** (n - j) * (1 - q) ** n
            Veu[(n, j)] = max(S - K, 0.0)
        for k in range(n - 1, -1, -1):
            for j in range(k + 1):
                Veu[(k, j)] = disc * (RL["p"] * Veu[(k + 1, j + 1)] + (1 - RL["p"]) * Veu[(k + 1, j)])
        gaps.append(amV[(0, 0)] - Veu[(0, 0)])
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(qs * 100, gaps, "o-", color=ORANGE, lw=2.5, ms=7)
    ax.axhline(0, color=GREY, lw=1)
    ax.fill_between(qs * 100, 0, gaps, color=GOLD, alpha=0.3)
    ax.set_xlabel("dividend yield q (% per period)")
    ax.set_ylabel(r"American $-$ European")
    ax.set_title("American call premium grows with dividend yield (RL, n=4)", color=NAVY)
    _save("ch04-am-eu-diff-vs-div.png")


def fig_put_frontier_close():
    n = 3
    K = 5.0
    V, C, exer = _american_put(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
    nodes = _tree_nodes(TOY["S0"], TOY["u"], TOY["d"], n)
    fig, ax = plt.subplots(figsize=(11, 7))
    _draw_tree_edges(ax, n)
    for (k, j), S in nodes.items():
        x, y = _node_xy(k, j, n)
        g = max(K - S, 0.0)
        v = V[(k, j)]
        if k < n:
            c = C[(k, j)]
            is_ex = (k, j) in exer
            color = RED if is_ex else GREEN
            ax.add_patch(Rectangle((x - 0.38, y - 0.55), 0.76, 1.1,
                                   facecolor=color, edgecolor=NAVY, alpha=0.85, zorder=3))
            ax.text(x, y + 0.36, f"S={S:g}", ha="center", color="white",
                    fontsize=8, fontweight="bold", zorder=4)
            ax.text(x, y + 0.10, f"g={g:g}", ha="center", color="white", fontsize=8, zorder=4)
            ax.text(x, y - 0.15, f"C={c:.2f}", ha="center", color="white", fontsize=8, zorder=4)
            ax.text(x, y - 0.40, f"V={v:.2f}", ha="center", color="white",
                    fontsize=8, fontweight="bold", zorder=4)
        else:
            color = RED if g > 0 else GREEN
            ax.plot(x, y, "o", color=color, ms=22, zorder=3)
            ax.text(x, y, f"{g:g}", ha="center", va="center", color="white",
                    fontsize=9, fontweight="bold", zorder=4)
    ax.set_xlim(-0.7, n + 1.0)
    ax.set_ylim(-n - 1.2, n + 1.2)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title(r"Toy put $K=5$: at each node $V = \max\{g, C\}$", color=NAVY)
    _save("ch04-put-frontier-close.png")


def fig_V0_vs_r():
    n = 4
    K = 100.0
    rs = np.linspace(0.0, 0.10, 21)
    eu, am = [], []
    for r in rs:
        Veu = _european_put(RL["S0"], RL["u"], RL["d"], r, RL["p"], K, n)
        V, _, _ = _american_put(RL["S0"], RL["u"], RL["d"], r, RL["p"], K, n)
        eu.append(Veu[(0, 0)])
        am.append(V[(0, 0)])
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(rs * 100, eu, "o-", color=BLUE, lw=2.5, label="European")
    ax.plot(rs * 100, am, "s-", color=ORANGE, lw=2.5, label="American")
    ax.fill_between(rs * 100, eu, am, color=GOLD, alpha=0.4, label="early-exercise premium")
    ax.set_xlabel("r (% per period)")
    ax.set_ylabel(r"$V_0$")
    ax.set_title("RL put K=100, n=4: American widens above European with r", color=NAVY)
    ax.legend()
    _save("ch04-V0-vs-r.png")


def fig_frontier_sigma_3d():
    n = 6
    K = 100.0
    us = [1.05, 1.10, 1.20, 1.50]
    colors_list = [BLUE, GREEN, ORANGE, RED]
    fig = plt.figure(figsize=(13, 9))
    ax = fig.add_subplot(111, projection="3d")
    for idx, (u, col) in enumerate(zip(us, colors_list)):
        d = 1.0 / u
        p = ((1 + RL["r"]) - d) / (u - d)
        if p <= 0 or p >= 1:
            p = 0.5
        V, _, exer = _american_put(RL["S0"], u, d, RL["r"], p, K, n)
        ks = []
        Sstars = []
        for k in range(n + 1):
            opts = []
            for j in range(k + 1):
                S = RL["S0"] * u ** j * d ** (k - j)
                if (k, j) in exer:
                    opts.append(S)
                elif k == n and max(K - S, 0.0) > 0:
                    opts.append(S)
            if opts:
                ks.append(k)
                Sstars.append(max(opts))
        ys = [idx] * len(ks)
        ax.plot(ks, ys, Sstars, "o-", color=col, lw=2.5, ms=7, label=f"u={u}")
    ax.set_xlabel("k", labelpad=10)
    ax.set_ylabel("vol index", labelpad=14)
    ax.set_zlabel(r"$S^*(k)$", labelpad=10)
    ax.set_yticks(range(len(us)))
    ax.set_yticklabels([f"u={u}" for u in us])
    ax.set_title(r"Exercise frontier vs volatility (higher u $\rightarrow$ lower frontier)", color=NAVY, pad=20)
    ax.legend(loc="upper left", bbox_to_anchor=(1.05, 1.0), fontsize=10, borderaxespad=0)
    fig.tight_layout()
    _save("ch04-frontier-sigma-3d.png", tight=False)


def fig_digital_am():
    n = 3
    H = 8.0
    nodes = _tree_nodes(TOY["S0"], TOY["u"], TOY["d"], n)
    fig, ax = plt.subplots(figsize=(9, 6))
    _draw_tree_edges(ax, n)
    for (k, j), S in nodes.items():
        x, y = _node_xy(k, j, n)
        color = RED if S >= H else GREEN
        ax.plot(x, y, "o", color=color, ms=22, zorder=3)
        ax.text(x, y, f"{S:g}", ha="center", va="center", color="white",
                fontsize=9, fontweight="bold", zorder=4)
    ax.set_xlim(-0.5, n + 0.7)
    ax.set_ylim(-n - 1, n + 1)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title(rf"Toy American digital ($H={H:g}$): exercise (red) when $S \geq H$", color=NAVY)
    _save("ch04-digital-am.png")


def fig_knockout_am():
    n = 3
    K = 5.0
    B = 8.0
    disc = 1.0 / (1.0 + TOY["r"])
    nodes = _tree_nodes(TOY["S0"], TOY["u"], TOY["d"], n)
    alive = {(k, j): nodes[(k, j)] < B for (k, j) in nodes}
    for k in range(1, n + 1):
        for j in range(k + 1):
            if not alive[(k, j)]:
                continue
            par_ok = False
            if j - 1 >= 0 and alive.get((k - 1, j - 1), False):
                par_ok = True
            if j <= k - 1 and alive.get((k - 1, j), False):
                par_ok = True
            if not par_ok:
                alive[(k, j)] = False
    V = {}
    exer = set()
    for j in range(n + 1):
        S = nodes[(n, j)]
        V[(n, j)] = 0.0 if not alive[(n, j)] else max(K - S, 0.0)
    for k in range(n - 1, -1, -1):
        for j in range(k + 1):
            if not alive[(k, j)]:
                V[(k, j)] = 0.0
                continue
            cont = disc * (TOY["p"] * V[(k + 1, j + 1)] + (1 - TOY["p"]) * V[(k + 1, j)])
            intr = max(K - nodes[(k, j)], 0.0)
            if intr > cont + 1e-12:
                V[(k, j)] = intr
                exer.add((k, j))
            else:
                V[(k, j)] = cont
    fig, ax = plt.subplots(figsize=(9, 6))
    _draw_tree_edges(ax, n)
    for (k, j), S in nodes.items():
        x, y = _node_xy(k, j, n)
        if not alive[(k, j)]:
            color = GREY
        elif (k, j) in exer or (k == n and max(K - S, 0) > 0 and alive[(k, j)]):
            color = RED
        else:
            color = GREEN
        ax.plot(x, y, "o", color=color, ms=22, zorder=3)
        label = f"{S:g}" if alive[(k, j)] else "KO"
        ax.text(x, y, label, ha="center", va="center", color="white",
                fontsize=9, fontweight="bold", zorder=4)
    ax.set_xlim(-0.5, n + 0.7)
    ax.set_ylim(-n - 1, n + 1)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title(rf"Toy up-and-out put $K={K:g}, B={B:g}$: grey = knocked out", color=NAVY)
    _save("ch04-knockout-am.png")


def fig_chooser():
    n = 3
    K = 5.0
    Vc = _european_call(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
    Vp = _european_put(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
    nodes = _tree_nodes(TOY["S0"], TOY["u"], TOY["d"], n)
    fig, axes = plt.subplots(1, 3, figsize=(15, 6))
    titles = ["European call", "European put", "Chooser = max at k=1"]
    for ax in axes:
        _draw_tree_edges(ax, n)
        ax.set_xlim(-0.5, n + 0.7)
        ax.set_ylim(-n - 1, n + 1)
        ax.set_xlabel("k")
    for (k, j), S in nodes.items():
        x, y = _node_xy(k, j, n)
        axes[0].plot(x, y, "o", color=BLUE, ms=22, zorder=3)
        axes[0].text(x, y, f"{Vc[(k, j)]:.2f}", ha="center", va="center",
                     color="white", fontsize=8, fontweight="bold", zorder=4)
        axes[1].plot(x, y, "o", color=ORANGE, ms=22, zorder=3)
        axes[1].text(x, y, f"{Vp[(k, j)]:.2f}", ha="center", va="center",
                     color="white", fontsize=8, fontweight="bold", zorder=4)
        if k <= 1:
            val = max(Vc[(k, j)], Vp[(k, j)])
            color = PURPLE
            axes[2].plot(x, y, "o", color=color, ms=22, zorder=3)
            axes[2].text(x, y, f"{val:.2f}", ha="center", va="center",
                         color="white", fontsize=8, fontweight="bold", zorder=4)
        else:
            axes[2].plot(x, y, "o", color=GREY, ms=22, zorder=3, alpha=0.25)
    for ax, t in zip(axes, titles):
        ax.set_title(t, color=NAVY)
    fig.suptitle("Chooser at k=1: pointwise max(call, put)", color=NAVY, fontsize=13)
    fig.tight_layout()
    _save("ch04-chooser.png")


def _delta_replication(S0, u, d, r, p, K, n):
    """Delta and consumption for American put dealer (super-replication)."""
    V, C, exer = _american_put(S0, u, d, r, p, K, n)
    disc = 1.0 / (1.0 + r)
    Delta = {}
    dC = {}
    for k in range(n):
        for j in range(k + 1):
            S = S0 * u ** j * d ** (k - j)
            Vu = V[(k + 1, j + 1)]
            Vd = V[(k + 1, j)]
            delta = (Vu - Vd) / (S * (u - d))
            Delta[(k, j)] = delta
            cont = disc * (p * Vu + (1 - p) * Vd)
            dC[(k, j)] = V[(k, j)] - cont
    return V, Delta, dC, exer


def fig_delta_X_tree():
    n = 3
    K = 5.0
    V, Delta, dC, exer = _delta_replication(
        TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
    nodes = _tree_nodes(TOY["S0"], TOY["u"], TOY["d"], n)
    fig, ax = plt.subplots(figsize=(11, 7))
    _draw_tree_edges(ax, n)
    for (k, j), S in nodes.items():
        x, y = _node_xy(k, j, n)
        if k < n:
            delta = Delta[(k, j)]
            dc = dC[(k, j)]
            color = RED if dc > 1e-9 else BLUE
            ax.add_patch(Rectangle((x - 0.38, y - 0.4), 0.76, 0.8,
                                   facecolor=color, edgecolor=NAVY, alpha=0.85, zorder=3))
            ax.text(x, y + 0.18, rf"$\Delta$={delta:.2f}", ha="center", color="white",
                    fontsize=8, fontweight="bold", zorder=4)
            ax.text(x, y - 0.15, f"dC={dc:.2f}", ha="center", color="white", fontsize=8, zorder=4)
        else:
            ax.plot(x, y, "o", color=GREEN, ms=18, zorder=3)
            ax.text(x, y, f"{S:g}", ha="center", va="center", color="white",
                    fontsize=8, fontweight="bold", zorder=4)
    ax.set_xlim(-0.7, n + 1.0)
    ax.set_ylim(-n - 1.2, n + 1.2)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title(r"Dealer super-replication: $\Delta_k$ and $dC_k$ on Toy put tree", color=NAVY)
    _save("ch04-delta-X-tree.png")


def fig_X_vs_g_path():
    n = 3
    K = 5.0
    V, Delta, dC, exer = _delta_replication(
        TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
    paths = [
        ("HHH", [(0, 0), (1, 1), (2, 2), (3, 3)]),
        ("HHT", [(0, 0), (1, 1), (2, 2), (3, 2)]),
        ("HTT", [(0, 0), (1, 1), (2, 1), (3, 1)]),
        ("TTT", [(0, 0), (1, 0), (2, 0), (3, 0)]),
    ]
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = [BLUE, ORANGE, GREEN, PURPLE]
    for (name, path), col in zip(paths, colors):
        Ss = [TOY["S0"] * TOY["u"] ** j * TOY["d"] ** (k - j) for (k, j) in path]
        gs = [max(K - S, 0.0) for S in Ss]
        Xs = [V[(0, 0)]]
        for k in range(n):
            (kk, jj) = path[k]
            dlt = Delta[(kk, jj)]
            dc = dC[(kk, jj)]
            Snow = Ss[k]
            Snext = Ss[k + 1]
            bond = (Xs[-1] - dlt * Snow - dc)
            Xnext = dlt * Snext + (1 + TOY["r"]) * bond
            Xs.append(Xnext)
        ks = list(range(n + 1))
        ax.plot(ks, Xs, "o-", color=col, lw=2.2, label=f"X path {name}")
        ax.plot(ks, gs, "s--", color=col, lw=1, ms=6, alpha=0.6)
    ax.set_xlabel("k")
    ax.set_ylabel("value")
    ax.set_title(r"Wealth $X_k$ (solid) dominates intrinsic $g(S_k)$ (dashed)", color=NAVY)
    ax.legend(fontsize=9, ncol=2)
    _save("ch04-X-vs-g-path.png")


def fig_consumption_bars():
    """Bars of dC_k at each pre-terminal node (k, j).

    Positive bars (red) flag optimal-exercise nodes where the dealer's
    super-replicating portfolio releases cash; zero bars (blue stub) confirm
    consumption stays at zero on the continuation set, as required for
    super-replication of an American put.
    """
    n = 3
    K = 5.0
    V, Delta, dC, exer = _delta_replication(
        TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)

    labels = []
    vals = []
    cols = []
    is_pos = []
    for k in range(n):
        for j in range(k + 1):
            labels.append(rf"$({k},{j})$")
            v = dC[(k, j)]
            vals.append(v)
            pos = v > 1e-9
            is_pos.append(pos)
            cols.append(RED if pos else BLUE)

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(labels))
    width = 0.6
    ymax = max(vals) if max(vals) > 0 else 1.0
    # Give zero-bars a tiny visible stub so the axis-position is not "empty".
    stub = ymax * 0.015
    plot_vals = [v if v > 1e-9 else stub for v in vals]
    bars = ax.bar(x, plot_vals, width=width, color=cols, edgecolor=NAVY, linewidth=1.0)

    # Value labels on top of each bar (true value, not the stub).
    for xi, v, pos in zip(x, vals, is_pos):
        if pos:
            ax.text(xi, v + ymax * 0.025, f"{v:.3f}",
                    ha="center", va="bottom", color=NAVY, fontsize=10, fontweight="bold")
        else:
            ax.text(xi, stub + ymax * 0.025, r"$0$",
                    ha="center", va="bottom", color=GREY, fontsize=10)

    # Group nodes by k with light shading + a k-label underneath the ticks.
    boundaries = []
    idx = 0
    for k in range(n):
        m = k + 1
        boundaries.append((idx - 0.5, idx + m - 0.5, k))
        idx += m
    for lo, hi, k in boundaries:
        if k % 2 == 0:
            ax.axvspan(lo, hi, color=GREY, alpha=0.06, zorder=0)
        ax.text((lo + hi) / 2, -ymax * 0.16, rf"$k={k}$",
                ha="center", va="top", color=NAVY, fontsize=11, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_xlabel(r"node $(k,\,j)$", fontsize=11, labelpad=22)
    ax.set_ylabel(r"$dC_k(\omega)$", fontsize=12)
    ax.set_ylim(0, ymax * 1.20)
    ax.set_xlim(-0.7, len(labels) - 0.3)
    ax.set_title(
        r"Consumption process: $dC_k > 0$ only on the optimal-exercise set",
        color=NAVY, fontsize=13, pad=12,
    )

    # Legend in the upper-right corner (where there is no data — leftmost bars are zero).
    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor=RED, edgecolor=NAVY,
                      label=r"$dC_k > 0$  (exercise node)"),
        plt.Rectangle((0, 0), 1, 1, facecolor=BLUE, edgecolor=NAVY,
                      label=r"$dC_k = 0$  (continuation)"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=10, framealpha=0.95)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)

    _save("ch04-consumption-bars.png")


def fig_arb_pnl():
    n = 3
    K = 5.0
    V, _, _ = _american_put(TOY["S0"], TOY["u"], TOY["d"], TOY["r"], TOY["p"], K, n)
    true_v = V[(0, 0)]
    quoted = 1.20
    edge = true_v - quoted
    ks = np.arange(0, n + 1)
    pnl = edge * (1 + TOY["r"]) ** ks
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(ks, pnl, "o-", color=GREEN, lw=2.5, ms=10)
    ax.fill_between(ks, 0, pnl, color=GREEN, alpha=0.25)
    ax.axhline(0, color=GREY, lw=1)
    ax.set_xlabel("k")
    ax.set_ylabel("locked P&L (grown at r)")
    ax.set_title(rf"Buyer-side arbitrage: quote ${quoted:.2f}$ vs true ${true_v:.2f}$", color=NAVY)
    for k, p in zip(ks, pnl):
        ax.text(k, p + 0.01, f"{p:.3f}", ha="center", fontsize=9, color=NAVY)
    _save("ch04-arb-pnl.png")


def fig_knockout_same_S():
    n = 3
    fig, ax = plt.subplots(figsize=(10, 6))
    nodes = _tree_nodes(TOY["S0"], TOY["u"], TOY["d"], n)
    _draw_tree_edges(ax, n, alpha=0.2)
    path_HT = [(0, 0), (1, 1), (2, 1)]
    path_TH = [(0, 0), (1, 0), (2, 1)]
    xa = [_node_xy(k, j, n) for (k, j) in path_HT]
    xb = [_node_xy(k, j, n) for (k, j) in path_TH]
    ax.plot([p[0] for p in xa], [p[1] for p in xa], color=RED, lw=2.8, label="HT: touches B=8")
    ax.plot([p[0] for p in xb], [p[1] for p in xb], color=GREEN, lw=2.8, label="TH: never touches")
    for (k, j) in set(path_HT + path_TH):
        x, y = _node_xy(k, j, n)
        ax.plot(x, y, "o", color=NAVY, ms=16, zorder=3)
        ax.text(x, y, f"{nodes[(k, j)]:g}", ha="center", va="center",
                color="white", fontsize=8, fontweight="bold", zorder=4)
    x2, y2 = _node_xy(2, 1, n)
    ax.add_patch(plt.Circle((x2, y2), 0.45, fill=False, ec=PURPLE, lw=2.5))
    ax.annotate("same (k,S) = (2, 4)\ndifferent value!",
                xy=(x2, y2), xytext=(x2 + 0.5, y2 - 1.5),
                arrowprops=dict(arrowstyle="->", color=PURPLE), color=PURPLE)
    x1, y1 = _node_xy(1, 1, n)
    ax.text(x1 + 0.1, y1 + 0.4, "B=8 touched", color=RED, fontsize=9)
    ax.set_xlim(-0.5, n + 1.0)
    ax.set_ylim(-n - 1, n + 1)
    ax.set_xlabel("k")
    ax.set_ylabel("net ups")
    ax.set_title("Knockout: path matters, not just (k, S)", color=NAVY)
    ax.legend(loc="upper right")
    _save("ch04-knockout-same-S.png")


def fig_augmented_tree():
    n = 3
    B = 8.0
    fig, ax = plt.subplots(figsize=(14, 9))
    paths = []
    for code in range(2 ** n):
        bits = [(code >> (n - 1 - i)) & 1 for i in range(n)]
        j_seq = [0]
        for b in bits:
            j_seq.append(j_seq[-1] + b)
        S_seq = [TOY["S0"] * TOY["u"] ** j_seq[k] * TOY["d"] ** (k - j_seq[k]) for k in range(n + 1)]
        touched = any(S >= B for S in S_seq)
        paths.append((bits, S_seq, touched))
    for idx, (bits, S_seq, touched) in enumerate(paths):
        y_off = (idx - 3.5) * 1.1
        xs = list(range(n + 1))
        ys = [(2 * sum(bits[:k]) - k) + y_off for k in range(n + 1)]
        col = GREY if touched else GREEN
        ax.plot(xs, ys, "o-", color=col, lw=2.2 if not touched else 1.6,
                alpha=1.0 if not touched else 0.55, ms=10)
        for k, (xk, yk) in enumerate(zip(xs, ys)):
            ax.text(xk, yk + 0.28, f"{S_seq[k]:g}", ha="center",
                    fontsize=9, color=NAVY)
        name = "".join("H" if b else "T" for b in bits)
        ax.text(n + 0.25, ys[-1], name, color=col, fontsize=11, va="center", fontweight="bold")
    ax.set_xlim(-0.5, n + 1.0)
    ax.set_xlabel("k")
    ax.set_ylabel("offset position (per path)")
    ax.set_title("Augmented (non-recombining) tree: 8 distinct path states", color=NAVY)
    ax.set_yticks([])
    _save("ch04-augmented-tree.png")


# ------------------------------------------------------------------ main

if __name__ == "__main__":
    fig_eu_vs_am_timeline()
    fig_eu_vs_am_bars()
    fig_tau_shaded()
    fig_lookahead_violation()
    fig_snell_tree()
    fig_V_vs_g()
    fig_Vk_3d()
    fig_tau_star_paths()
    fig_stopped_mart()
    fig_frontier_st()
    fig_frontier_rl()
    fig_frontier_3d()
    fig_frontier_r_compare()
    fig_call_tree_all_green()
    fig_call_tree_with_div()
    fig_am_eu_diff_vs_div()
    fig_put_frontier_close()
    fig_V0_vs_r()
    fig_frontier_sigma_3d()
    fig_digital_am()
    fig_knockout_am()
    fig_chooser()
    fig_delta_X_tree()
    fig_X_vs_g_path()
    fig_consumption_bars()
    fig_arb_pnl()
    fig_knockout_same_S()
    fig_augmented_tree()
    print("done.")
