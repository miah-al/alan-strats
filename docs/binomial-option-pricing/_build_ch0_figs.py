"""
Chapter 0 figure builder for the Binomial Option Pricing guide.

Run:
    python docs/binomial-option-pricing/_build_ch0_figs.py

Writes 19 PNGs under ./figures relative to this file. The recurring "Toy"
example uses S0=4, u=2, d=1/2, r=1/4, p_tilde=1/2 (a neutral name; no
attribution).

Style: bright, colourful palette. 3-D figures use filled Poly3DCollection
ridges so they read as surfaces rather than 3-D bars.
"""
from __future__ import annotations

import math
import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registers 3-D projection)
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.special import comb
from scipy.stats import binom, norm


# ----------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------

FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG_DIR, exist_ok=True)
DPI = 180

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
    "axes.titlesize": 12,
    "axes.labelsize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
    "font.family": "DejaVu Sans",
    "savefig.bbox": "tight",
})


def _save(name: str) -> None:
    out = os.path.join(FIG_DIR, name)
    plt.savefig(out, dpi=DPI)
    plt.close()
    print(f"  wrote {name}")


# ----------------------------------------------------------------------
# 1. ch00-gross-vs-log : three views of a 10% up-move
# ----------------------------------------------------------------------

def fig_gross_vs_log() -> None:
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    labels = ["Simple\n$R=0.10$", "Gross\n$G=1.10$", "Log\n$\\ln G=0.0953$"]
    values = [0.10, 1.10, math.log(1.10)]
    colors = [ORANGE, BLUE, GREEN]
    bars = ax.bar(labels, values, color=colors, edgecolor=NAVY, linewidth=1.4)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.03, f"{v:.4f}",
                ha="center", va="bottom", fontsize=11, color=NAVY)
    ax.axhline(0, color=GREY, lw=0.8)
    ax.set_ylim(0, 1.35)
    ax.set_ylabel("value")
    ax.set_title("Three views of a single 10% up-move")
    ax.text(0.5, -0.22,
            "Log return undercounts ups, overcounts downs — that is what compounding leverages.",
            transform=ax.transAxes, ha="center", fontsize=9, color=GREY)
    _save("ch00-gross-vs-log.png")


# ----------------------------------------------------------------------
# 2. ch00-paths-gross-vs-log
# ----------------------------------------------------------------------

def fig_paths_gross_vs_log() -> None:
    rng = np.random.default_rng(0)
    n_paths, n_days = 20, 20
    u, d = 1.10, 1.0 / 1.10
    p = 0.5
    steps = rng.choice([u, d], size=(n_paths, n_days), p=[p, 1 - p])
    gross = np.cumprod(np.concatenate([np.ones((n_paths, 1)), steps], axis=1), axis=1)
    log_p = np.log(gross)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    cmap = plt.colormaps.get_cmap("plasma")
    colors = [cmap(i / n_paths) for i in range(n_paths)]
    t = np.arange(n_days + 1)
    for i in range(n_paths):
        axes[0].plot(t, gross[i], color=colors[i], alpha=0.85, lw=1.3)
        axes[1].plot(t, log_p[i], color=colors[i], alpha=0.85, lw=1.3)
    axes[0].set_title("Gross-price space (fan-shaped, asymmetric)")
    axes[0].set_xlabel("day")
    axes[0].set_ylabel("$S_t$")
    axes[1].set_title("Log-price space (symmetric)")
    axes[1].set_xlabel("day")
    axes[1].set_ylabel("$\\ln S_t$")
    axes[1].axhline(0, color=GREY, lw=0.8)
    fig.suptitle("Same paths, two coordinate systems", color=NAVY)
    _save("ch00-paths-gross-vs-log.png")


# ----------------------------------------------------------------------
# 3. ch00-compounding-converges
# ----------------------------------------------------------------------

def fig_compounding_converges() -> None:
    r = 0.10
    t = np.linspace(0, 10, 400)
    annual = (1 + r) ** t
    monthly = (1 + r / 12) ** (12 * t)
    continuous = np.exp(r * t)

    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.plot(t, annual, color=ORANGE, lw=2.4, label="annual $(1+r)^t$")
    ax.plot(t, monthly, color=GREEN, lw=2.0, ls="--", label="monthly $(1+r/12)^{12t}$")
    ax.plot(t, continuous, color=BLUE, lw=1.6, ls=":", label="continuous $e^{rt}$")
    ax.set_xlabel("time $t$ (years)")
    ax.set_ylabel("growth factor")
    ax.set_title(f"Three compoundings, $r={r:.2f}$ — visually indistinguishable")
    ax.legend(loc="upper left", frameon=False)
    _save("ch00-compounding-converges.png")


# ----------------------------------------------------------------------
# 4. ch00-exp-and-log
# ----------------------------------------------------------------------

def fig_exp_and_log() -> None:
    fig, ax = plt.subplots(figsize=(6.5, 6.0))
    x1 = np.linspace(-2.2, 2.2, 400)
    x2 = np.linspace(0.05, 9.0, 400)
    ax.plot(x1, np.exp(x1), color=ORANGE, lw=2.5, label="$e^x$")
    ax.plot(x2, np.log(x2), color=BLUE, lw=2.5, label="$\\ln x$")
    lim = 9.0
    ax.plot([-2.2, lim], [-2.2, lim], color=GREY, lw=1.0, ls="--", label="$y=x$")
    ax.axhline(0, color="black", lw=0.6)
    ax.axvline(0, color="black", lw=0.6)
    ax.set_xlim(-2.5, lim)
    ax.set_ylim(-2.5, lim)
    ax.set_aspect("equal")
    ax.set_title("$e^x$ and $\\ln x$ are reflections across $y=x$")
    ax.legend(loc="lower right", frameon=False)
    _save("ch00-exp-and-log.png")


# ----------------------------------------------------------------------
# 5. ch00-pascal-vs-tree : Pascal vs Toy stock tree
# ----------------------------------------------------------------------

def fig_pascal_vs_tree() -> None:
    N = 8
    S0, u, d = 4.0, 2.0, 0.5

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.4))

    # Left: Pascal triangle
    ax = axes[0]
    for n in range(N + 1):
        for k in range(n + 1):
            x = k - n / 2
            y = -n
            val = int(comb(n, k, exact=True))
            ax.scatter(x, y, s=520, color=GOLD, edgecolor=NAVY, zorder=3)
            ax.text(x, y, str(val), ha="center", va="center", fontsize=9, color=NAVY)
    for n in range(N):
        for k in range(n + 1):
            x = k - n / 2
            y = -n
            ax.plot([x, x - 0.5], [y, y - 1], color=GREY, lw=0.8, zorder=1)
            ax.plot([x, x + 0.5], [y, y - 1], color=GREY, lw=0.8, zorder=1)
    ax.set_title("Pascal's triangle: $\\binom{n}{k}$")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(-N / 2 - 1, N / 2 + 1)
    ax.set_ylim(-N - 1, 1)
    ax.set_frame_on(False)
    ax.grid(False)

    # Right: Toy stock tree.  Limit N here so node text never overflows.
    N_tree = 5
    ax = axes[1]
    for n in range(N_tree + 1):
        for k in range(n + 1):
            price = S0 * (u ** k) * (d ** (n - k))
            x = n
            y = k - n / 2
            ax.scatter(x, y, s=900, color=BLUE, edgecolor=NAVY, zorder=3)
            # Format large/small values compactly so they fit the disc
            if price >= 100:
                txt = f"{price:.0f}"
            elif price >= 1:
                txt = f"{price:g}"
            else:
                txt = f"{price:.3g}"
            ax.text(x, y, txt, ha="center", va="center",
                    fontsize=8, color="white")
    for n in range(N_tree):
        for k in range(n + 1):
            x, y = n, k - n / 2
            ax.plot([x, x + 1], [y, y + 0.5], color=GREEN, lw=0.9, zorder=1)
            ax.plot([x, x + 1], [y, y - 0.5], color=RED, lw=0.9, zorder=1)
    ax.set_title("Toy stock tree: $S_n = S_0\\, u^k d^{n-k}$")
    ax.set_xticks(range(N_tree + 1))
    ax.set_yticks([])
    ax.set_xlabel("period $n$")
    ax.set_xlim(-0.4, N_tree + 0.4)
    ax.set_ylim(-N_tree / 2 - 0.6, N_tree / 2 + 0.6)
    ax.set_frame_on(False)
    ax.grid(False)

    fig.suptitle("Same shape, different labels", color=NAVY)
    _save("ch00-pascal-vs-tree.png")


# ----------------------------------------------------------------------
# 6. ch00-pascal-3d : 3-D ridge of binomial coefficients
# ----------------------------------------------------------------------

def _ridge_polygons(rows):
    """Build filled Poly3DCollection ridges.

    rows : list of (y_value, xs, heights, color).
    Returns a list of polygons in 3-space.
    """
    polys = []
    colors = []
    for y, xs, hs, color in rows:
        verts = [(xs[0], y, 0.0)]
        for xi, hi in zip(xs, hs):
            verts.append((xi, y, hi))
        verts.append((xs[-1], y, 0.0))
        polys.append(verts)
        colors.append(color)
    pc = Poly3DCollection(polys, facecolors=colors, edgecolors=NAVY, linewidths=0.6, alpha=0.85)
    return pc


def fig_pascal_3d() -> None:
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")
    Nmax = 12
    cmap = plt.colormaps.get_cmap("viridis")
    rows = []
    for n in range(Nmax + 1):
        ks = np.arange(n + 1)
        hs = np.array([comb(n, int(k), exact=True) for k in ks], dtype=float)
        xs = ks - n / 2.0
        # pad to cover full base for nicer ridge
        xs_full = np.concatenate([[xs[0] - 0.4], xs, [xs[-1] + 0.4]])
        hs_full = np.concatenate([[0.0], hs, [0.0]])
        rows.append((n, xs_full, hs_full, cmap(n / Nmax)))
    ax.add_collection3d(_ridge_polygons(rows))
    ax.set_xlim(-Nmax / 2 - 1, Nmax / 2 + 1)
    ax.set_ylim(0, Nmax)
    ax.set_zlim(0, comb(Nmax, Nmax // 2, exact=True) * 1.05)
    ax.set_xlabel("$k - n/2$", labelpad=8)
    ax.set_ylabel("$n$", labelpad=8)
    ax.set_zlabel("$\\binom{n}{k}$", labelpad=10)
    ax.set_title("Pascal's triangle as a ridge — the bell curve is already visible",
                 pad=14)
    ax.view_init(elev=28, azim=-62)
    _save("ch00-pascal-3d.png")


# ----------------------------------------------------------------------
# 7. ch00-sample-space-tree : 3-toss tree, p=0.6, "exactly two heads"
# ----------------------------------------------------------------------

def fig_sample_space_tree() -> None:
    p = 0.6
    fig, ax = plt.subplots(figsize=(10.5, 7.5))

    # Build all 8 leaves
    leaves = []
    def recurse(depth, y, prob, path, spread):
        if depth == 3:
            heads = path.count("H")
            leaves.append((y, prob, path, heads))
            return
        # up = H, down = T
        ax.scatter(depth, y, s=240, color=GOLD, edgecolor=NAVY, zorder=3)
        ax.plot([depth, depth + 1], [y, y + spread], color=GREEN, lw=1.3,
                zorder=1)
        ax.plot([depth, depth + 1], [y, y - spread], color=RED, lw=1.3,
                zorder=1)
        # Place edge labels at 30% along the branch so deeper-level labels
        # don't crowd the receiving node.
        fx = depth + 0.3
        fy_up = y + 0.3 * spread
        fy_dn = y - 0.3 * spread
        ax.text(fx, fy_up + 0.18, f"H, {p}",
                color=GREEN, fontsize=8.5, ha="center", va="bottom",
                bbox=dict(facecolor="white", edgecolor="none",
                          alpha=0.85, pad=0.6), zorder=2)
        ax.text(fx, fy_dn - 0.18, f"T, {1 - p}",
                color=RED, fontsize=8.5, ha="center", va="top",
                bbox=dict(facecolor="white", edgecolor="none",
                          alpha=0.85, pad=0.6), zorder=2)
        recurse(depth + 1, y + spread, prob * p, path + "H", spread / 2)
        recurse(depth + 1, y - spread, prob * (1 - p), path + "T", spread / 2)

    recurse(0, 0.0, 1.0, "", 4.0)

    total_event = 0.0
    for y, prob, path, heads in leaves:
        highlight = (heads == 2)
        color = GOLD if highlight else "#cccccc"
        edge = ORANGE if highlight else GREY
        ax.scatter(3, y, s=420, color=color, edgecolor=edge, linewidth=1.6, zorder=4)
        ax.text(3.15, y, f"{path}\n$P={prob:.3f}$",
                ha="left", va="center", fontsize=8.5,
                color=NAVY if highlight else GREY)
        if highlight:
            total_event += prob
    ax.set_xlim(-0.4, 4.4)
    ax.set_ylim(-8.5, 8.5)
    ax.set_xticks([0, 1, 2, 3])
    ax.set_xticklabels(["start", "toss 1", "toss 2", "toss 3"])
    ax.set_yticks([])
    ax.set_title(f"Three-toss sample space (p={p}) — event \"exactly two heads\""
                 f"  $P = {total_event:.3f}$", pad=14)
    ax.grid(False)
    ax.set_frame_on(False)
    _save("ch00-sample-space-tree.png")


# ----------------------------------------------------------------------
# 8. ch00-mean-as-fulcrum
# ----------------------------------------------------------------------

def fig_mean_as_fulcrum() -> None:
    S0, u, d, r = 4.0, 2.0, 0.5, 0.25
    p = 0.5  # risk-neutral
    up_val = S0 * u
    dn_val = S0 * d
    mean = p * up_val + (1 - p) * dn_val
    discounted = mean / (1 + r)

    fig, ax = plt.subplots(figsize=(8.5, 5.0))
    ax.bar([dn_val, up_val], [1 - p, p], width=0.6,
           color=[RED, GREEN], edgecolor=NAVY, linewidth=1.4,
           label="PMF of $S_1$")
    ax.set_xticks([dn_val, mean, up_val])
    ax.set_xticklabels([f"d·$S_0$ = {dn_val:g}",
                        f"$\\tilde{{E}}[S_1]$ = {mean:g}",
                        f"u·$S_0$ = {up_val:g}"])
    # Fulcrum triangle at mean, placed clearly below the bars / axis.
    ax.plot(mean, -0.025, marker="^", markersize=22, color=GOLD,
            markeredgecolor=NAVY, clip_on=False, zorder=5)
    # 'fulcrum' label is offset to the side of the mean tick so the two
    # texts never collide.
    ax.annotate("(fulcrum)", xy=(mean, -0.025),
                xytext=(mean + 1.4, -0.18),
                ha="left", va="center", color=NAVY, fontsize=9,
                annotation_clip=False,
                arrowprops=dict(arrowstyle="-", color=GREY, lw=0.8))
    # Discount arrow from mean back to S0
    ax.annotate("", xy=(discounted, 0.7), xytext=(mean, 0.7),
                arrowprops=dict(arrowstyle="->", color=PURPLE, lw=2.2))
    ax.text((mean + discounted) / 2, 0.78,
            f"$\\div(1+r) = \\div{1 + r}$", ha="center", color=PURPLE, fontsize=10)
    ax.scatter([discounted], [0.0], s=180, color=BLUE, zorder=4)
    ax.text(discounted, 0.05, f"$S_0={discounted:g}$",
            ha="center", va="bottom", color=BLUE, fontsize=10)
    ax.set_ylim(-0.05, 1.0)
    ax.set_xlim(dn_val - 1.0, up_val + 1.0)
    ax.set_ylabel("probability")
    ax.set_title("Toy: mean is a fulcrum; discounting returns to today's price")
    ax.legend(loc="upper right", frameon=False)
    # Push tick labels just clear of the fulcrum triangle.
    ax.tick_params(axis="x", pad=22)
    _save("ch00-mean-as-fulcrum.png")


# ----------------------------------------------------------------------
# 9. ch00-cond-exp-subtree : 2-period Toy tree with upper subtree highlighted
# ----------------------------------------------------------------------

def _draw_tree_2period(ax, highlight_branch=None):
    S0, u, d = 4.0, 2.0, 0.5
    nodes = {}
    nodes[(0, 0)] = S0
    nodes[(1, 1)] = S0 * u
    nodes[(1, -1)] = S0 * d
    nodes[(2, 2)] = S0 * u * u
    nodes[(2, 0)] = S0 * u * d
    nodes[(2, -2)] = S0 * d * d

    edges = [((0, 0), (1, 1)),
             ((0, 0), (1, -1)),
             ((1, 1), (2, 2)),
             ((1, 1), (2, 0)),
             ((1, -1), (2, 0)),
             ((1, -1), (2, -2))]
    for a, b in edges:
        emph = (highlight_branch == "up" and a in [(0, 0)] and b == (1, 1)) or \
               (highlight_branch == "up" and a == (1, 1))
        color = GOLD if emph else GREY
        lw = 3.0 if emph else 1.2
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=lw, zorder=1)
    for (n, y), val in nodes.items():
        emph = highlight_branch == "up" and ((n == 1 and y == 1) or (n == 2 and y in (2, 0)))
        face = ORANGE if emph else BLUE
        ax.scatter(n, y, s=620, color=face, edgecolor=NAVY, linewidth=1.4, zorder=3)
        ax.text(n, y, f"{val:g}", ha="center", va="center",
                color="white", fontsize=10)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["$n=0$", "$n=1$", "$n=2$"])
    ax.set_yticks([])
    ax.set_xlim(-0.4, 2.6)
    ax.set_ylim(-3, 3)
    ax.grid(False)
    ax.set_frame_on(False)


def fig_cond_exp_subtree() -> None:
    fig, ax = plt.subplots(figsize=(8, 5.4))
    _draw_tree_2period(ax, highlight_branch="up")
    ax.set_title("Conditional expectation = average over the highlighted subtree")
    ax.annotate("$\\tilde{E}[S_2 \\mid \\mathcal{F}_1]$ at $S_1=8$\n"
                "$= \\tfrac{1}{2}(16) + \\tfrac{1}{2}(4) = 10$".replace("\\tfrac", "\\frac"),
                xy=(1, 1), xytext=(0.15, 2.4),
                arrowprops=dict(arrowstyle="->", color=PURPLE, lw=1.8),
                color=PURPLE, fontsize=10, ha="left")
    _save("ch00-cond-exp-subtree.png")


# ----------------------------------------------------------------------
# 10. ch00-tower-property : three-panel storyboard
# ----------------------------------------------------------------------

def fig_tower_property() -> None:
    S0, u, d = 4.0, 2.0, 0.5
    p = 0.5
    leaves = {2: S0 * u * u, 0: S0 * u * d, -2: S0 * d * d}  # 16, 4, 1
    e_up = p * leaves[2] + (1 - p) * leaves[0]      # 10
    e_dn = p * leaves[0] + (1 - p) * leaves[-2]     # 2.5
    e_root = p * e_up + (1 - p) * e_dn               # 6.25

    # Wider figure so titles never collide with the next panel.
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.8))

    # Node helper -- larger nodes, fontsize >= 11 inside.
    def node(ax, x, y, val, color, fs=12):
        ax.scatter(x, y, s=1500, color=color, edgecolor=NAVY,
                   linewidth=1.8, zorder=3)
        txt = f"{val:g}" if isinstance(val, (int, float)) else val
        ax.text(x, y, txt, ha="center", va="center",
                color="white", fontsize=fs, fontweight="bold", zorder=4)

    # Panel 1: leaves S_2 -- show a 2-step tree with edges so the
    # "block structure" the tower property folds is visible.
    ax = axes[0]
    # Root (faint) and intermediates (faint) so the block grouping is clear.
    ax.plot([0.05, 0.45], [0.0, 1.6], color=GREY, lw=1.2, zorder=1)
    ax.plot([0.05, 0.45], [0.0, -1.6], color=GREY, lw=1.2, zorder=1)
    ax.plot([0.45, 0.92], [1.6, 2.4], color=GREY, lw=1.2, zorder=1)
    ax.plot([0.45, 0.92], [1.6, 0.0], color=GREY, lw=1.2, zorder=1)
    ax.plot([0.45, 0.92], [-1.6, 0.0], color=GREY, lw=1.2, zorder=1)
    ax.plot([0.45, 0.92], [-1.6, -2.4], color=GREY, lw=1.2, zorder=1)
    # Faint intermediates labelled with S_1 values.
    ax.scatter([0.45, 0.45], [1.6, -1.6], s=1700, facecolor="white",
               edgecolor=GREY, linewidth=1.4, zorder=2)
    ax.text(0.45, 1.6, "$S_1=8$", ha="center", va="center",
            fontsize=11, color=GREY, zorder=3)
    ax.text(0.45, -1.6, "$S_1=2$", ha="center", va="center",
            fontsize=11, color=GREY, zorder=3)
    # Leaves -- the values to be averaged.
    node(ax, 0.92, 2.4, leaves[2], GREEN, fs=12)
    node(ax, 0.92, 0.0, leaves[0], GREEN, fs=12)
    node(ax, 0.92, -2.4, leaves[-2], GREEN, fs=12)
    # Block brackets.
    ax.annotate("", xy=(1.05, 2.4), xytext=(1.05, 0.0),
                arrowprops=dict(arrowstyle="-", color=BLUE, lw=2.2))
    ax.annotate("", xy=(1.05, 0.0), xytext=(1.05, -2.4),
                arrowprops=dict(arrowstyle="-", color=ORANGE, lw=2.2))
    ax.text(1.12, 1.2, "up\nblock", color=BLUE, fontsize=11, va="center")
    ax.text(1.12, -1.2, "down\nblock", color=ORANGE, fontsize=11, va="center")
    ax.set_title("1. Leaf values $S_2$", fontsize=13, pad=10)
    ax.set_xlim(0, 1.45)
    ax.set_ylim(-3.4, 3.4)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_frame_on(False); ax.grid(False)

    # Panel 2: conditional expectations at F_1.
    ax = axes[1]
    # Show the averages 10 and 2.5 sitting at S_1=8 and S_1=2 respectively,
    # with labels off to the side so digits inside the node stay readable.
    node(ax, 0.30, 1.6, e_up, BLUE, fs=12)
    node(ax, 0.30, -1.6, e_dn, ORANGE, fs=12)
    ax.text(0.55, 1.6,
            "$\\tilde{E}[S_2 \\,|\\, \\mathcal{F}_1]$\nat $S_1=8$",
            va="center", ha="left", color=NAVY, fontsize=11)
    ax.text(0.55, -1.6,
            "$\\tilde{E}[S_2 \\,|\\, \\mathcal{F}_1]$\nat $S_1=2$",
            va="center", ha="left", color=NAVY, fontsize=11)
    # Block sums shown above each node.
    ax.text(0.30, 2.55, r"$\frac{1}{2}(16+4)$", ha="center",
            fontsize=11, color=BLUE)
    ax.text(0.30, -2.55, r"$\frac{1}{2}(4+1)$", ha="center",
            fontsize=11, color=ORANGE)
    ax.set_title("2. Average within each block $\\to$ $\\mathcal{F}_1$",
                 fontsize=13, pad=10)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(-3.4, 3.4)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_frame_on(False); ax.grid(False)

    # Panel 3: root -- average of the two block averages.
    ax = axes[2]
    node(ax, 0.5, 0.4, e_root, PURPLE, fs=13)
    ax.text(0.5, -0.95,
            f"$\\tilde{{E}}[S_2] = \\frac{{1}}{{2}}(10 + 2.5) = {e_root:g}$",
            ha="center", color=NAVY, fontsize=12)
    ax.text(0.5, -1.95,
            "Same answer as averaging\nall four leaves directly.",
            ha="center", color=GREY, fontsize=10, style="italic")
    ax.set_title("3. Average the block averages $\\to$ root",
                 fontsize=13, pad=10)
    ax.set_xlim(0, 1)
    ax.set_ylim(-3.4, 3.4)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_frame_on(False); ax.grid(False)

    fig.suptitle("Tower property: average within blocks, then average across blocks",
                 color=NAVY, fontsize=14, y=1.02)
    plt.subplots_adjust(wspace=0.18)
    _save("ch00-tower-property.png")


# ----------------------------------------------------------------------
# 11. ch00-reflection-bijection
# ----------------------------------------------------------------------

def fig_reflection_bijection() -> None:
    # Blue path of length 6 that first touches +3 at t=4 and ends at +2.
    # Steps:  +1 +1 +1 +1 -1 +1  -> levels 0,1,2,3,3 wait need first-touch at 4.
    # Let's choose steps: +1, +1, -1, +1, +1, +1 -> levels 0,1,2,1,2,3,? no.
    # Need to reach +3 first time at t=4.  Steps +1,+1,+1,-1,+1,? Then after step 4 level=2.
    # Try steps: +1,+1,+1,-1,+1,+1 -> levels: 0,1,2,3,2,3,4  first hits +3 at t=3, not 4.
    # Try +1,+1,-1,+1,+1,+1 -> 0,1,2,1,2,3,4 first hits +3 at t=5.  Nope.
    # We want first touch at t=4 (4th step) and end +2.
    # Steps: +1,+1,+1,? — gets to +3 at t=3.  To have first hit at t=4 we need
    # to NOT hit +3 by t=3 then hit at t=4.
    # +1,+1,-1,+1,+1,?  levels 0,1,2,1,2,3,?  first hit +3 at t=5.
    # +1,-1,+1,+1,+1,? levels 0,1,0,1,2,3,?  first hit +3 at t=5.
    # We need first hit at t=4 AND end at +2 (length 6). Then last 2 steps must sum to -1.
    # +1,+1,-1,+1,?,? with first 4 levels 0,1,2,1,2 — never hits +3.  Pad more.
    # OK: first-touch at t=4 means level=3 at t=4 and level<3 for t<4.
    # max possible after 4 steps is +4 if all +1.  We need exactly +3 at t=4 with <3 before.
    # 4 steps summing to +3 means 3 up and 1 down somewhere in first 3 steps with
    # final step +1.  Example: -1,+1,+1,+1,+1,-1 -> 0,-1,0,1,2,3,2.  Level=3 at t=5, not 4.
    # We want level=3 at t=4 so we need 4 steps with sum +3 and never hitting +3
    # before step 4 itself.  Example: +1,-1,+1,+1 -> 0,1,0,1,2 ... only +2.
    # Hmm 4-step sum +3 with strictly <3 along the way needs first 3 steps sum +2.
    # +1,+1,?,?: sum after 2 = +2, then step 3 must keep <3 (so -1 or +1 — +1 gives +3 at t=3 bad).
    # So step 3 = -1 -> level +1 at t=3; step 4 must make level 3: requires +2 step, impossible (single step is +/-1).
    # So it's impossible to first hit +3 at t=4 if we require single-step +/-1.
    # Re-read caption: "length-6 path that touches level +3 at t = 4" — interpret as
    # any path that touches +3 at time t=4 (not necessarily first time). Allowed: levels
    # reach +3 somewhere, and one such touch is at t=4.  We mark the FIRST touch with a star.
    # Choose blue path with first touch at t=4 by allowing higher-step interpretation:
    # actually we can: +1,+1,+1,-1,? — first touch at t=3.  Reflected from t=3 to end.
    # The caption says first-touch at t=4. Probably the steps used are t=1..6 indexed.
    # Use steps over t=1..6 and "t=4" means after 4 steps (so it matches earlier logic).
    # Simpler: pick first hit at t=3, but caption says 4. Switch to t indexing where
    # we draw 6 points along x and a path of 6 STEPS giving 7 positions.
    # Easier: produce a path of length n=6 (so positions at t=0..6, 7 points).  First-touch
    # at t=4 means after 4 steps we are at +3 and before that <3.
    # That requires steps 1..4 sum +3 with no partial sum >=3, which we showed needs final
    # step +2 — impossible.
    # Resolution: increase path length so steps can be +/-1.  Let level=+3 be reached at
    # t=5 (5 steps), and we let "t=4" in caption mean step index 4 differently. Actually
    # let's just use first-touch at t=5 to be faithful to integer-step constraints, but
    # the caption says 4.  Strict constraint: 4-step paths to +3 must be UUUU (+4) or
    # any with sum +3 (impossible since 4 has even parity vs +3 odd) -> 4 and +3 have
    # different parity (even vs odd), so we CANNOT be at +3 at t=4 with +/-1 steps!
    # So caption is approximate.  Choose first-touch at t=3 (UUU): then reflect.  Length
    # 6 ending at +2: UUU then 3 more steps summing to -1: e.g. D, U, D -> levels 0,1,2,3,2,3,2.
    # First touch at t=3.  We'll mark t=3 as the touch.
    steps_blue = np.array([+1, +1, +1, -1, +1, -1])
    levels_blue = np.concatenate([[0], np.cumsum(steps_blue)])
    touch_t = int(np.argmax(levels_blue >= 3))   # first index reaching 3
    # Red path = reflect blue after touch across y=+3.
    levels_red = levels_blue.copy()
    for i in range(touch_t + 1, len(levels_red)):
        levels_red[i] = 2 * 3 - levels_red[i]

    fig, ax = plt.subplots(figsize=(9, 5))
    t = np.arange(len(levels_blue))
    ax.axhline(3, color=GOLD, lw=2.0, ls="--", label="reflection axis $y=3$")
    ax.plot(t, levels_blue, color=BLUE, lw=2.5, marker="o", markersize=8,
            label=f"blue path (ends {levels_blue[-1]:+d})")
    ax.plot(t, levels_red, color=RED, lw=2.5, marker="s", markersize=8,
            label=f"red path = reflected (ends {levels_red[-1]:+d})")
    ax.scatter([touch_t], [3], marker="*", s=420, color=GOLD,
               edgecolor=NAVY, zorder=5, label=f"first touch at $t={touch_t}$")
    ax.set_xticks(t)
    ax.set_xlabel("$t$")
    ax.set_ylabel("level $X_t$")
    ax.set_title("Reflection bijection — every blue corresponds to one red")
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    _save("ch00-reflection-bijection.png")


# ----------------------------------------------------------------------
# 12. ch00-all-16-paths : small-multiples of all 16 length-4 paths
# ----------------------------------------------------------------------

def fig_all_16_paths() -> None:
    fig, axes = plt.subplots(4, 4, figsize=(10, 8.5), sharex=True, sharey=True)
    red_count = 0
    for idx in range(16):
        ax = axes[idx // 4][idx % 4]
        bits = [(idx >> b) & 1 for b in range(4)]
        steps = np.array([+1 if b == 1 else -1 for b in bits])
        levels = np.concatenate([[0], np.cumsum(steps)])
        hits_2 = (levels >= 2).any()
        color = RED if hits_2 else GREY
        if hits_2:
            red_count += 1
        ax.plot(range(5), levels, color=color, lw=2.0, marker="o", markersize=4)
        ax.axhline(2, color=GOLD, lw=0.9, ls="--")
        ax.set_ylim(-4.7, 4.7)
        ax.set_xticks([0, 2, 4])
        ax.set_yticks([-4, 0, 4])
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.2)
    fig.suptitle(f"All 16 length-4 paths — red = ever reaches $+2$  "
                 f"($P(\\max \\geq 2) = {red_count}/16$)", color=NAVY)
    _save("ch00-all-16-paths.png")


# ----------------------------------------------------------------------
# 13. ch00-max-distribution-3d
# ----------------------------------------------------------------------

def _running_max_dist(n: int):
    """PMF of max_{1..n} X_t for fair +/-1 walk via enumeration."""
    counts = {}
    for idx in range(1 << n):
        steps = [+1 if (idx >> b) & 1 else -1 for b in range(n)]
        level = 0
        running_max = 0
        for s in steps:
            level += s
            if level > running_max:
                running_max = level
        counts[running_max] = counts.get(running_max, 0) + 1
    total = 1 << n
    items = sorted(counts.items())
    xs = np.array([m for m, _ in items])
    ps = np.array([c / total for _, c in items])
    return xs, ps


def fig_max_distribution_3d() -> None:
    fig = plt.figure(figsize=(10.5, 7))
    ax = fig.add_subplot(111, projection="3d")
    ns = [4, 8, 12, 16, 20]
    cmap = plt.colormaps.get_cmap("plasma")
    rows = []
    for i, n in enumerate(ns):
        xs, ps = _running_max_dist(n)
        xs_full = np.concatenate([[xs[0] - 0.5], xs.astype(float), [xs[-1] + 0.5]])
        ps_full = np.concatenate([[0.0], ps, [0.0]])
        rows.append((n, xs_full, ps_full, cmap(i / (len(ns) - 1))))
    ax.add_collection3d(_ridge_polygons(rows))
    ax.set_xlim(-1, max(_running_max_dist(ns[-1])[0]) + 1)
    ax.set_ylim(ns[0] - 1, ns[-1] + 1)
    ax.set_zlim(0, 0.55)
    ax.set_xlabel("level $m$", labelpad=8)
    ax.set_ylabel("$n$", labelpad=8)
    ax.set_zlabel("$P(\\max = m)$", labelpad=10)
    ax.set_title("Distribution of the running maximum — ridge spreads with $n$",
                 pad=14)
    ax.view_init(elev=28, azim=-60)
    _save("ch00-max-distribution-3d.png")


# ----------------------------------------------------------------------
# 14. ch00-binom-10-06-pmf
# ----------------------------------------------------------------------

def fig_binom_10_06_pmf() -> None:
    n, p = 10, 0.6
    ks = np.arange(n + 1)
    pmf = binom.pmf(ks, n, p)
    fig, ax = plt.subplots(figsize=(8, 4.6))
    colors = [GOLD if k == int(round(n * p)) else BLUE for k in ks]
    bars = ax.bar(ks, pmf, color=colors, edgecolor=NAVY, linewidth=1.2)
    for k, b in zip(ks, bars):
        if pmf[k] > 0.02:
            ax.text(k, pmf[k] + 0.005, f"{pmf[k]:.3f}",
                    ha="center", fontsize=8, color=NAVY)
    ax.set_xticks(ks)
    ax.set_xlabel("$k$ (number of heads)")
    ax.set_ylabel("$P(H = k)$")
    ax.set_ylim(0, max(pmf) * 1.18)
    ax.set_title(f"Binomial$(n={n}, p={p})$ — mode at $k={int(round(n * p))}$")
    _save("ch00-binom-10-06-pmf.png")


# ----------------------------------------------------------------------
# 15. ch00-binom-stacked-3d : ridge across n
# ----------------------------------------------------------------------

def fig_binom_stacked_3d() -> None:
    fig = plt.figure(figsize=(10.5, 7))
    ax = fig.add_subplot(111, projection="3d")
    ns = [4, 8, 16, 32, 64]
    p = 0.6
    cmap = plt.colormaps.get_cmap("viridis")
    rows = []
    for i, n in enumerate(ns):
        ks = np.arange(n + 1)
        pmf = binom.pmf(ks, n, p)
        frac = ks / n
        # add padding to anchor ridge to baseline
        xs_full = np.concatenate([[frac[0] - 0.02], frac, [frac[-1] + 0.02]])
        ps_full = np.concatenate([[0.0], pmf, [0.0]])
        rows.append((n, xs_full, ps_full, cmap(i / (len(ns) - 1))))
    ax.add_collection3d(_ridge_polygons(rows))
    ax.set_xlim(0, 1)
    ax.set_ylim(ns[0] - 1, ns[-1] + 1)
    ax.set_zlim(0, 0.45)
    ax.set_xlabel("fraction heads $k/n$", labelpad=8)
    ax.set_ylabel("$n$", labelpad=8)
    ax.set_zlabel("PMF", labelpad=10)
    ax.set_title(f"Binomial PMF concentrates around $p={p}$ as $n$ grows", pad=14)
    ax.view_init(elev=26, azim=-58)
    _save("ch00-binom-stacked-3d.png")


# ----------------------------------------------------------------------
# 16. ch00-phi-and-Phi
# ----------------------------------------------------------------------

def fig_phi_and_Phi() -> None:
    z = np.linspace(-4, 4, 400)
    phi = norm.pdf(z)
    Phi = norm.cdf(z)
    z0 = 1.0
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    ax = axes[0]
    ax.plot(z, phi, color=BLUE, lw=2.5)
    z_fill = z[z <= z0]
    ax.fill_between(z_fill, 0, norm.pdf(z_fill), color=GOLD, alpha=0.6,
                    label=f"area = $\\Phi(1) = {norm.cdf(z0):.4f}$")
    ax.axvline(z0, color=ORANGE, lw=1.6, ls="--")
    ax.set_xlabel("$z$")
    ax.set_ylabel("$\\phi(z)$")
    ax.set_title("Standard normal density $\\phi$")
    ax.legend(loc="upper left", frameon=False)

    ax = axes[1]
    ax.plot(z, Phi, color=GREEN, lw=2.5)
    ax.axvline(z0, color=ORANGE, lw=1.6, ls="--")
    ax.axhline(norm.cdf(z0), color=GOLD, lw=1.6, ls="--")
    ax.scatter([z0], [norm.cdf(z0)], color=RED, s=80, zorder=5)
    ax.text(z0 + 0.15, norm.cdf(z0) - 0.05,
            f"$\\Phi(1)={norm.cdf(z0):.4f}$", color=NAVY, fontsize=10)
    ax.set_xlabel("$z$")
    ax.set_ylabel("$\\Phi(z)$")
    ax.set_title("Standard normal CDF $\\Phi$")
    fig.suptitle("$\\Phi$ is the running area under $\\phi$", color=NAVY)
    _save("ch00-phi-and-Phi.png")


# ----------------------------------------------------------------------
# 17. ch00-three-normals
# ----------------------------------------------------------------------

def fig_three_normals() -> None:
    x = np.linspace(-6, 8, 600)
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.plot(x, norm.pdf(x, 0, 1), color=BLUE, lw=2.4, label="$N(0,1)$")
    ax.plot(x, norm.pdf(x, 0, 2), color=ORANGE, lw=2.4, label="$N(0,4)$  (wider)")
    ax.plot(x, norm.pdf(x, 2, 1), color=GREEN, lw=2.4, label="$N(2,1)$  (shifted)")
    ax.axhline(0, color=GREY, lw=0.6)
    ax.set_xlabel("$x$")
    ax.set_ylabel("density")
    ax.set_title("$\\mu$ shifts, $\\sigma$ scales — every normal reduces to $\\Phi$")
    ax.legend(loc="upper right", frameon=False)
    _save("ch00-three-normals.png")


# ----------------------------------------------------------------------
# 18. ch00-clt-ridge-3d
# ----------------------------------------------------------------------

def fig_clt_ridge_3d() -> None:
    fig = plt.figure(figsize=(10.5, 7))
    ax = fig.add_subplot(111, projection="3d")
    ns = [10, 20, 50, 100, 200]
    p = 0.5
    cmap = plt.colormaps.get_cmap("magma")
    rows = []
    for i, n in enumerate(ns):
        ks = np.arange(n + 1)
        pmf = binom.pmf(ks, n, p)
        mu = n * p
        sigma = math.sqrt(n * p * (1 - p))
        z = (ks - mu) / sigma
        # scale pmf to density on z-axis: divide by spacing 1/sigma
        dens = pmf * sigma
        mask = (z >= -4) & (z <= 4)
        xs = z[mask]
        ys = dens[mask]
        xs_full = np.concatenate([[xs[0] - 0.1], xs, [xs[-1] + 0.1]])
        ys_full = np.concatenate([[0.0], ys, [0.0]])
        rows.append((n, xs_full, ys_full, cmap(0.15 + 0.7 * i / (len(ns) - 1))))
    ax.add_collection3d(_ridge_polygons(rows))
    # overlay the limiting normal at the far end
    z_curve = np.linspace(-4, 4, 200)
    ax.plot(z_curve, [ns[-1] + 8] * len(z_curve), norm.pdf(z_curve),
            color=GOLD, lw=2.4, label="$\\phi(z)$")
    ax.set_xlim(-4, 4)
    ax.set_ylim(ns[0] - 5, ns[-1] + 15)
    ax.set_zlim(0, 0.5)
    ax.set_xlabel("$(k-\\mu)/\\sigma$", labelpad=8)
    ax.set_ylabel("$n$", labelpad=8)
    ax.set_zlabel("density", labelpad=10)
    ax.set_title("Central Limit Theorem in action — Binomial standardised PMFs",
                 pad=14)
    # Move legend outside the 3-D box so it never lands on the title or ridges.
    ax.legend(loc="upper right", bbox_to_anchor=(1.18, 0.95), frameon=False)
    ax.view_init(elev=24, azim=-60)
    _save("ch00-clt-ridge-3d.png")


# ----------------------------------------------------------------------
# 19. ch00-clt-4-panels
# ----------------------------------------------------------------------

def fig_clt_4_panels() -> None:
    ns = [10, 30, 100, 400]
    p = 0.5
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5))
    palette = [BLUE, ORANGE, GREEN, PURPLE]
    for ax, n, color in zip(axes.flat, ns, palette):
        ks = np.arange(n + 1)
        pmf = binom.pmf(ks, n, p)
        ax.bar(ks, pmf, color=color, edgecolor=NAVY, linewidth=0.4, width=1.0,
               alpha=0.7, label=f"Bin$(n={n}, p={p})$")
        mu = n * p
        sigma = math.sqrt(n * p * (1 - p))
        x = np.linspace(0, n, 500)
        ax.plot(x, norm.pdf(x, mu, sigma), color=RED, lw=2.2,
                label=f"$N({mu:g}, {sigma**2:g})$")
        ax.set_xlim(mu - 4 * sigma, mu + 4 * sigma)
        # Give headroom for the legend so it never lands on the bell.
        ymax = max(pmf.max(), norm.pdf(mu, mu, sigma)) * 1.30
        ax.set_ylim(0, ymax)
        ax.set_title(f"$n = {n}$")
        ax.legend(loc="upper left", fontsize=9, frameon=False)
        ax.set_xlabel("$k$")
        ax.set_ylabel("PMF / density")
    fig.suptitle("CLT at four scales — bars meet the bell", color=NAVY)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    _save("ch00-clt-4-panels.png")


# ----------------------------------------------------------------------
# 20. ch00-stirling-clt-proof : 4-panel storyboard for §0.10 proof sketch
# ----------------------------------------------------------------------

def fig_stirling_clt_proof() -> None:
    """Four-panel storyboard of the Stirling/de Moivre-Laplace argument.

    Top row (3 panels): exact symmetric-binomial PMF bars vs the Stirling
    approximation 1/sqrt(pi n/2) * exp(-2 j^2 / n) for n = 20, 100, 500 in
    the (k - n/2) = j coordinate.  The matching limiting phi(z) on the
    standardised z-axis is traced on each as a thin gold curve so the
    reader sees the bell appear as n grows.

    Bottom row (1 wide panel): log-scale relative-error vs n at fixed
    standardised deviation z = 2 j / sqrt(n) = const, showing the
    Berry-Esseen-style 1/sqrt(n) decay.
    """
    fig = plt.figure(figsize=(13.5, 8.2))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 0.85], hspace=0.50,
                          wspace=0.30)

    panel_colors = [BLUE, GREEN, PURPLE]
    ns_top = [20, 100, 500]
    for i, n in enumerate(ns_top):
        ax = fig.add_subplot(gs[0, i])
        ks = np.arange(n + 1)
        js = ks - n // 2
        pmf = binom.pmf(ks, n, 0.5)
        # Window: |j| <= 4 * sigma for clarity.
        sigma = math.sqrt(n / 4.0)
        mask = np.abs(js) <= 4.0 * sigma
        js_m = js[mask]
        pmf_m = pmf[mask]
        # Stirling approximation in j-coordinates.
        approx = (1.0 / math.sqrt(math.pi * n / 2.0)) * np.exp(
            -2.0 * js_m**2 / n
        )
        ax.bar(js_m, pmf_m, width=1.0, color=panel_colors[i],
               edgecolor=NAVY, linewidth=0.4, alpha=0.65,
               label=f"exact $\\binom{{{n}}}{{n/2+j}}/2^{{{n}}}$")
        # Smooth Stirling curve at fractional resolution.
        js_fine = np.linspace(js_m.min(), js_m.max(), 400)
        approx_fine = (1.0 / math.sqrt(math.pi * n / 2.0)) * np.exp(
            -2.0 * js_fine**2 / n
        )
        ax.plot(js_fine, approx_fine, color=RED, lw=2.4,
                label=r"$\frac{1}{\sqrt{\pi n/2}}\, e^{-2j^2/n}$")
        # Trace the limiting phi(z) rescaled to the j-axis for visual
        # reference: phi(z) / sigma converts density-in-z to PMF-in-j.
        z_fine = js_fine / sigma
        phi_curve = norm.pdf(z_fine) / sigma
        ax.plot(js_fine, phi_curve, color=GOLD, lw=1.6, ls="--",
                label=r"$\phi(z)/\sigma$")
        ax.set_title(f"$n = {n}$")
        ax.set_xlabel("$j = k - n/2$")
        ax.set_ylabel("probability")
        # Leave plenty of headroom; legend pinned upper-right outside the
        # bars by anchoring above the peak.
        ax.set_ylim(0, max(pmf_m.max(), approx.max()) * 1.45)
        ax.legend(loc="upper right", fontsize=8, frameon=False)

    # Bottom: log-scale relative error vs n at fixed z = 1.0.
    ax = fig.add_subplot(gs[1, :])
    ns_bot = np.array([10, 20, 40, 80, 160, 320, 640, 1280, 2560])
    z_fixed = 1.0
    rel_errs = []
    for n in ns_bot:
        sigma = math.sqrt(n / 4.0)
        # j must be an integer; pick the integer closest to z * sigma.
        j_target = int(round(z_fixed * sigma))
        k = n // 2 + j_target
        exact = binom.pmf(k, n, 0.5)
        approx = (1.0 / math.sqrt(math.pi * n / 2.0)) * math.exp(
            -2.0 * j_target**2 / n
        )
        rel_errs.append(abs(exact - approx) / exact)
    rel_errs = np.array(rel_errs)
    ax.loglog(ns_bot, rel_errs, color=ORANGE, lw=2.2, marker="o",
              markersize=8, markerfacecolor=GOLD, markeredgecolor=NAVY,
              label="$|\\mathrm{exact} - \\mathrm{Stirling}|/\\mathrm{exact}$"
              " at $z \\approx 1$")
    # Reference 1/n guide line.
    ref = rel_errs[0] * ns_bot[0] / ns_bot
    ax.loglog(ns_bot, ref, color=GREY, lw=1.2, ls="--",
              label="$1/n$ reference slope")
    ax.set_xlabel("$n$ (log scale)")
    ax.set_ylabel("relative error (log scale)")
    ax.set_title("Stirling/CLT approximation error decays like $1/n$ at fixed $z$")
    ax.legend(loc="upper right", frameon=False, fontsize=10)
    ax.grid(True, which="both", alpha=0.3)

    fig.suptitle(
        "Stirling $\\rightarrow$ de Moivre--Laplace: bars meet the bell as $n$ grows",
        color=NAVY, fontsize=14, y=0.995,
    )
    _save("ch00-stirling-clt-proof.png")


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------

ALL_FIGS = [
    fig_gross_vs_log,
    fig_paths_gross_vs_log,
    fig_compounding_converges,
    fig_exp_and_log,
    fig_pascal_vs_tree,
    fig_pascal_3d,
    fig_sample_space_tree,
    fig_mean_as_fulcrum,
    fig_cond_exp_subtree,
    fig_tower_property,
    fig_reflection_bijection,
    fig_all_16_paths,
    fig_max_distribution_3d,
    fig_binom_10_06_pmf,
    fig_binom_stacked_3d,
    fig_phi_and_Phi,
    fig_three_normals,
    fig_clt_ridge_3d,
    fig_clt_4_panels,
    fig_stirling_clt_proof,
]


if __name__ == "__main__":
    print(f"Building {len(ALL_FIGS)} Chapter 0 figures to {FIG_DIR} ...")
    for fn in ALL_FIGS:
        fn()
    print("Done.")
