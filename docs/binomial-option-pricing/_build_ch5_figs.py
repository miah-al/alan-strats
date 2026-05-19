"""
Chapter 5 figure builder for Binomial Option Pricing.

Run: python docs/binomial-option-pricing/_build_ch5_figs.py

Outputs under figures/:
    ch05-8-paths.png
    ch05-paths-vs-stock.png
    ch05-running-max-staircase.png
    ch05-three-paths-same-end.png
    ch05-reflection-twin.png
    ch05-length5-pairs-4panel.png
    ch05-bijection-schematic.png
    ch05-joint-bar-n6.png
    ch05-tau-hist.png
    ch05-tau-sample-paths.png
    ch05-joint-heatmap.png
    ch05-joint-bar-3d.png
    ch05-knockin-tree-st.png
    ch05-knockin-tree-rl.png
    ch05-ki-price-vs-L.png
    ch05-lookback-paths.png
    ch05-am-frontier-paths.png
    ch05-Mn-asymptotic-2panel.png
    ch05-clt-reflection-curves.png

Style: bright palette, Poly3DCollection for 3-D, no LaTeX dependency at render time.
Toy model: S_0 = 4, u = 2, d = 1/2. Realistic: S_0 = 100, u = 1.10, d = 0.90.
"""
from __future__ import annotations

import itertools
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  -- register 3-D projection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from scipy.special import comb
from scipy.stats import norm

FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG_DIR, exist_ok=True)
DPI = 200

# Palette (matches Chapter 0)
NAVY = "#0b1d3a"
BLUE = "#1f77b4"
ORANGE = "#ff7f0e"
GREEN = "#2ca02c"
RED = "#d62728"
PURPLE = "#9467bd"
GOLD = "#fbbf24"
TEAL = "#17becf"
GREY = "#666666"
LIGHTGREY = "#bbbbbb"

PALETTE_8 = [BLUE, ORANGE, GREEN, RED, PURPLE, TEAL, GOLD, NAVY]

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


def _all_paths(n):
    """Return all 2^n step sequences (+1 / -1) as a (2^n, n) array."""
    return np.array(list(itertools.product([+1, -1], repeat=n)))


def _path_from_steps(steps):
    """Return positions X_0 = 0, X_1, ..., X_n given +/-1 steps."""
    return np.concatenate(([0], np.cumsum(steps)))


def _reflect_after_first_hit(X, m):
    """Reflect a path after its first hit of level m across y = m. Return (X_refl, tau)."""
    X = X.astype(float).copy()
    hits = np.where(X == m)[0]
    if len(hits) == 0:
        return None, None
    tau = int(hits[0])
    X[tau + 1:] = 2 * m - X[tau + 1:]
    return X, tau


# -----------------------------------------------------------------------------
# 5.1 -- All eight length-3 paths of the symmetric random walk
# -----------------------------------------------------------------------------

def fig_8_paths():
    steps = _all_paths(3)
    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    t = np.arange(0, 4)
    # Small vertical jitter so coincident segments are distinguishable.
    jitter = np.linspace(-0.08, 0.08, len(steps))
    for i, s in enumerate(steps):
        x = _path_from_steps(s).astype(float)
        ax.plot(t, x + jitter[i], color=PALETTE_8[i], lw=2.3, marker="o", ms=6,
                alpha=0.92, zorder=3 + i,
                label="".join("U" if k == 1 else "D" for k in s))
    ax.axhline(0, color=GREY, lw=0.7)
    ax.set_xlabel("step $n$")
    ax.set_ylabel("position $X_n$")
    ax.set_title("All $2^3 = 8$ length-3 symmetric random walks")
    ax.set_xticks(t)
    ax.set_ylim(-3.6, 3.6)
    leg = ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=10,
                    title="path", handlelength=2.6)
    for line in leg.get_lines():
        line.set_linewidth(3.2)
    plt.tight_layout()
    _save("ch05-8-paths.png")


# -----------------------------------------------------------------------------
# 5.1 -- Same eight paths, walk vs stock (log axis)
# -----------------------------------------------------------------------------

def fig_paths_vs_stock():
    steps = _all_paths(3)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    t = np.arange(0, 4)
    S0 = 4.0  # Toy model
    for i, s in enumerate(steps):
        x = _path_from_steps(s)
        S = S0 * (2.0 ** x)
        axes[0].plot(t, x, color=PALETTE_8[i], lw=2.0, marker="o", ms=5,
                     alpha=0.95)
        axes[1].plot(t, S, color=PALETTE_8[i], lw=2.0, marker="o", ms=5,
                     alpha=0.95)
    axes[0].axhline(0, color=GREY, lw=0.7)
    axes[0].set_xlabel("step $n$")
    axes[0].set_ylabel("$X_n$")
    axes[0].set_title("Symmetric random walk $X_n$")
    axes[0].set_xticks(t)
    axes[1].set_yscale("log")
    axes[1].set_xlabel("step $n$")
    axes[1].set_ylabel("$S_n$ (log scale)")
    axes[1].set_title("Toy stock $S_n = 4 \\cdot 2^{X_n}$")
    axes[1].set_xticks(t)
    axes[1].axhline(4, color=GREY, lw=0.7, ls="--", alpha=0.6)
    plt.suptitle("Same eight paths in two coordinates", y=0.995, fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    _save("ch05-paths-vs-stock.png")


# -----------------------------------------------------------------------------
# 5.2 -- Running-max staircase with drawdown shading
# -----------------------------------------------------------------------------

def fig_running_max_staircase():
    steps = np.array([+1, -1, +1, +1, -1, +1])  # UDUUDU
    X = _path_from_steps(steps)
    M = np.maximum.accumulate(X)
    t = np.arange(0, 7)
    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    ax.plot(t, X, color=BLUE, lw=2.6, marker="o", ms=7, label="path $X_n$",
            zorder=4)
    ax.step(t, M, where="post", color=RED, lw=2.6, label="running max $M_n$",
            zorder=3)
    ax.fill_between(t, X, M, step="post", color=GOLD, alpha=0.25,
                    label="$M_n - X_n$ (drawdown)")
    # Offset labels above-or-below vertex so they don't overlap segments.
    offsets = [(0, 12), (10, 8), (0, -18), (-10, 8), (12, 6), (-10, 8),
               (8, -16)]
    for k in range(len(t)):
        dx, dy = offsets[k]
        ax.annotate(f"$X_{{{k}}}={X[k]}$", (t[k], X[k]),
                    textcoords="offset points", xytext=(dx, dy),
                    fontsize=8.5, color=NAVY,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white",
                              ec="none", alpha=0.75))
    ax.axhline(0, color=GREY, lw=0.7)
    ax.set_xlabel("step $n$")
    ax.set_ylabel("position")
    ax.set_title("Path UDUUDU and its running maximum")
    ax.set_xticks(t)
    ax.set_ylim(-0.4, 2.6)
    leg = ax.legend(loc="lower right", fontsize=10)
    for line in leg.get_lines():
        line.set_linewidth(3.0)
    plt.tight_layout()
    _save("ch05-running-max-staircase.png")


# -----------------------------------------------------------------------------
# 5.2 -- Three length-4 paths with same endpoint, different running max
# -----------------------------------------------------------------------------

def fig_three_paths_same_end():
    paths = {
        "DDUU": np.array([-1, -1, +1, +1]),  # M_4 = 0
        "DUDU": np.array([-1, +1, -1, +1]),  # M_4 = 0
        "UUDD": np.array([+1, +1, -1, -1]),  # M_4 = 2
    }
    colors = [GREEN, BLUE, RED]
    t = np.arange(0, 5)
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.0), sharey=True)
    for ax, (name, s), c in zip(axes, paths.items(), colors):
        X = _path_from_steps(s)
        M = np.maximum.accumulate(X)
        ax.plot(t, X, color=c, lw=2.6, marker="o", ms=7)
        ax.step(t, M, where="post", color=GREY, lw=1.5, ls="--",
                label=f"$M_4 = {M[-1]}$")
        ax.axhline(0, color=GREY, lw=0.7)
        ax.set_title(f"Path {name}: $X_4 = 0$, $M_4 = {M[-1]}$", fontsize=11)
        ax.set_xlabel("step $n$")
        ax.set_xticks(t)
        leg = ax.legend(loc="lower right", fontsize=10)
        for line in leg.get_lines():
            line.set_linewidth(2.6)
    axes[0].set_ylabel("$X_n$")
    plt.suptitle("Same endpoint $X_4 = 0$, three different running maxima",
                 y=0.995, fontsize=12)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    _save("ch05-three-paths-same-end.png")


# -----------------------------------------------------------------------------
# 5.3 -- Reflection twin: 2-D figure showing original (blue) and reflected
#         twin (red dashed) on the SAME axes with barrier and first-hit star.
# -----------------------------------------------------------------------------

def fig_reflection_twin():
    # n = 4, barrier m = 2. Path UUDD touches +2 at tau = 2 and ends at 0.
    # Its reflected twin (post-tau flipped across y = 2) is UUUU, ending at 4.
    s_orig = np.array([+1, +1, -1, -1])
    X_orig = _path_from_steps(s_orig)  # 0,1,2,1,0
    m = 2
    X_refl, tau = _reflect_after_first_hit(X_orig, m)
    t = np.arange(0, 5)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(t, X_orig, color=BLUE, lw=2.8, marker="o", ms=9,
            label="original UUDD ($X_4 = 0$)")
    ax.plot(t, X_refl, color=RED, lw=2.6, marker="s", ms=8, ls="--",
            label=f"reflected twin UUUU ($X_4 = {int(X_refl[-1])}$)")
    ax.axhline(m, color=GOLD, lw=2.0, ls="--", label=f"barrier $y = m = {m}$")
    ax.axhline(0, color=GREY, lw=0.7)
    ax.scatter([tau], [m], color=GOLD, s=260, marker="*",
               edgecolor="black", zorder=6, label=f"first hit $\\tau = {tau}$")
    # Vertical pairing lines for steps after tau
    for k in range(tau + 1, len(t)):
        ax.plot([t[k], t[k]], [X_orig[k], X_refl[k]],
                color=PURPLE, lw=1.0, ls=":", alpha=0.7)
    ax.set_xlabel("step $n$")
    ax.set_ylabel("$X_n$")
    ax.set_xticks(t)
    ax.set_title("Reflection bijection at $n = 4$, $m = 2$: "
                 "post-$\\tau$ steps flip across $y = m$")
    leg = ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
                    fontsize=10)
    for line in leg.get_lines():
        line.set_linewidth(3.0)
    plt.tight_layout()
    _save("ch05-reflection-twin.png")


# -----------------------------------------------------------------------------
# 5.3 -- Four pairs (original / reflected) at n = 5, m = 2, terminal h = 1
# -----------------------------------------------------------------------------

def fig_length5_pairs_4panel():
    n = 5
    m = 2
    target_h = 1
    all_steps = _all_paths(n)
    pairs = []
    for s in all_steps:
        X = _path_from_steps(s)
        if X.max() >= m and X[-1] == target_h:
            refl, tau = _reflect_after_first_hit(X, m)
            pairs.append((s, X, refl, tau))
    pairs = pairs[:4]
    t = np.arange(0, n + 1)
    fig, axes = plt.subplots(2, 4, figsize=(16, 8.5), sharex=True, sharey=True)
    for j, (s, X, refl, tau) in enumerate(pairs):
        name = "".join("U" if k == 1 else "D" for k in s)
        ax = axes[0, j]
        ax.plot(t, X, color=BLUE, lw=2.6, marker="o", ms=7)
        ax.axhline(m, color=GOLD, lw=1.8, ls="--")
        ax.scatter([tau], [m], color=GOLD, s=180, marker="*",
                   edgecolor="black", zorder=6)
        ax.set_title(f"{name}: $X_5 = {target_h}$", fontsize=11)
        ax.axhline(0, color=GREY, lw=0.5)
        ax = axes[1, j]
        ax.plot(t[:tau + 1], X[:tau + 1], color=BLUE, lw=2.6, marker="o",
                ms=7, alpha=0.7)
        ax.plot(t[tau:], refl[tau:], color=RED, lw=2.6, marker="o", ms=7,
                ls="--")
        ax.axhline(m, color=GOLD, lw=1.8, ls="--")
        ax.scatter([tau], [m], color=GOLD, s=180, marker="*",
                   edgecolor="black", zorder=6)
        ax.set_title(f"reflected: $X_5 = {2 * m - target_h}$", fontsize=11)
        ax.axhline(0, color=GREY, lw=0.5)
        ax.set_xlabel("step $n$", fontsize=10)
    axes[0, 0].set_ylabel("original\n$X_n$", fontsize=11)
    axes[1, 0].set_ylabel("reflected\n$X_n$", fontsize=11)
    for ax in axes.flat:
        ax.set_xticks(t)
        ax.tick_params(labelsize=9)
    plt.suptitle(f"$n = 5$, $m = 2$: four paths with $M_5 \\geq 2$ and "
                 f"$X_5 = {target_h}$, reflected to twins ending at "
                 f"$X_5 = {2 * m - target_h}$",
                 y=0.995, fontsize=12)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    _save("ch05-length5-pairs-4panel.png")


# -----------------------------------------------------------------------------
# 5.3 -- Bijection schematic with arrows showing reflection
# -----------------------------------------------------------------------------

def fig_bijection_schematic():
    fig, ax = plt.subplots(figsize=(11, 6))
    n = 6
    m = 2
    h = 0
    s = np.array([+1, +1, -1, -1, +1, -1])  # 0,1,2,1,0,1,0; tau = 2
    X = _path_from_steps(s)
    refl, tau = _reflect_after_first_hit(X, m)
    t = np.arange(0, n + 1)
    ax.plot(t, X, color=BLUE, lw=2.6, marker="o", ms=7,
            label=f"original (touches $m = {m}$, ends at $h = {h}$)")
    ax.plot(t[tau:], refl[tau:], color=RED, lw=2.6, marker="o", ms=7,
            ls="--", label=f"reflected (ends at $2m - h = {2 * m - h}$)")
    ax.axhline(m, color=GOLD, lw=2.0, ls="--", label=f"barrier $y = m = {m}$")
    ax.axhline(0, color=GREY, lw=0.7)
    ax.scatter([tau], [m], color=GOLD, s=240, marker="*",
               edgecolor="black", zorder=6, label=f"first hit $\\tau = {tau}$")
    for k in range(tau + 1, n + 1):
        ax.annotate("", xy=(t[k], refl[k]), xytext=(t[k], X[k]),
                    arrowprops=dict(arrowstyle="->", color=PURPLE, lw=1.3,
                                    alpha=0.85))
    ax.set_xlabel("step $n$")
    ax.set_ylabel("$X_n$")
    ax.set_xticks(t)
    ax.set_title("Reflection bijection: post-$\\tau$ vertex at $X_n$ flips to "
                 "$2m - X_n$; endpoint $h \\to 2m - h$")
    leg = ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
                    fontsize=10)
    for line in leg.get_lines():
        line.set_linewidth(3.0)
    plt.tight_layout()
    _save("ch05-bijection-schematic.png")


# -----------------------------------------------------------------------------
# 5.3 -- Empirical vs theoretical joint pmf at n = 6, m = 2
# -----------------------------------------------------------------------------

def _Pxn(n, k):
    if (n + k) % 2 != 0 or abs(k) > n:
        return 0.0
    return comb(n, (n + k) // 2) / 2.0 ** n


def fig_joint_bar_n6():
    """Joint pmf P(M_6 = m, X_6 = h) as 3-D Poly3DCollection ridges.

    One filled ridge per terminal h (a slice of the joint pmf), showing
    the conditional shape over the running max m. Bars/3-D bars clip the
    axis labels, so we use filled prism ridges instead.
    """
    n = 6
    m_vals, h_vals, P = _joint_pmf(n)

    # Drop terminal h with zero total mass to remove empty ridges
    # (e.g. h = -6 has zero joint mass because all four leaves of the
    # joint diagram require parity, but every visible h is plotted).
    keep_h = [j for j in range(len(h_vals)) if P[:, j].sum() > 0]
    h_vals = h_vals[keep_h]
    P = P[:, keep_h]

    fig = plt.figure(figsize=(13, 8.2))
    ax = fig.add_subplot(111, projection="3d")

    # Palette: one colour per terminal h, cycling through brand colours.
    band = [BLUE, ORANGE, GREEN, RED, PURPLE, TEAL, GOLD]

    dy = 0.55  # ridge half-thickness in the h direction
    base_z = 0.0
    for j, h in enumerate(h_vals):
        color = band[j % len(band)]
        # Build a closed polygon (m, z) profile and lift it to 3-D at y = h.
        ms = m_vals.astype(float)
        zs = P[:, j].astype(float)
        # Front face (y = h - dy)
        front = [(m, h - dy, base_z) for m in ms] + \
                [(ms[-1], h - dy, base_z)] + \
                [(m, h - dy, z) for m, z in zip(ms[::-1], zs[::-1])]
        # Back face (y = h + dy)
        back = [(m, h + dy, base_z) for m in ms] + \
               [(ms[-1], h + dy, base_z)] + \
               [(m, h + dy, z) for m, z in zip(ms[::-1], zs[::-1])]
        # Top ribbon connecting front-top and back-top (one quad per step).
        top_quads = []
        for k in range(len(ms) - 1):
            top_quads.append([
                (ms[k],     h - dy, zs[k]),
                (ms[k + 1], h - dy, zs[k + 1]),
                (ms[k + 1], h + dy, zs[k + 1]),
                (ms[k],     h + dy, zs[k]),
            ])
        # Side caps at both ends.
        left_cap = [
            (ms[0], h - dy, base_z), (ms[0], h + dy, base_z),
            (ms[0], h + dy, zs[0]),  (ms[0], h - dy, zs[0]),
        ]
        right_cap = [
            (ms[-1], h - dy, base_z), (ms[-1], h + dy, base_z),
            (ms[-1], h + dy, zs[-1]), (ms[-1], h - dy, zs[-1]),
        ]
        # Front + back filled outlines.
        front_face = [(m, h - dy, base_z) for m in ms] + \
                     [(m, h - dy, z) for m, z in zip(ms[::-1], zs[::-1])]
        back_face = [(m, h + dy, base_z) for m in ms] + \
                    [(m, h + dy, z) for m, z in zip(ms[::-1], zs[::-1])]

        polys = [front_face, back_face, left_cap, right_cap] + top_quads
        poly = Poly3DCollection(polys, facecolors=color,
                                edgecolors=NAVY, linewidths=0.5,
                                alpha=0.88)
        ax.add_collection3d(poly)

    ax.set_xlim(m_vals[0] - 0.5, m_vals[-1] + 0.5)
    ax.set_ylim(h_vals[0] - 1, h_vals[-1] + 1)
    ax.set_zlim(0, P.max() * 1.10)
    ax.set_xlabel("running max $M_6 = m$", labelpad=12, fontsize=12)
    ax.set_ylabel("terminal $X_6 = h$", labelpad=12, fontsize=12)
    ax.set_zlabel("probability", labelpad=10, fontsize=12)
    ax.set_xticks(m_vals)
    ax.set_yticks(h_vals)
    ax.tick_params(axis="x", labelsize=10, pad=2)
    ax.tick_params(axis="y", labelsize=10, pad=2)
    ax.tick_params(axis="z", labelsize=10, pad=4)
    ax.set_title("Joint pmf $\\mathbb{P}(M_6 = m,\\ X_6 = h)$ as ridges "
                 "over terminal $h$",
                 fontsize=13, pad=18)
    ax.view_init(elev=24, azim=-58)
    plt.subplots_adjust(left=0.04, right=0.96, top=0.92, bottom=0.06)
    _save("ch05-joint-bar-n6.png")


# -----------------------------------------------------------------------------
# 5.4 -- First-passage time pmf and sample paths
# -----------------------------------------------------------------------------

def fig_tau_hist():
    # P(tau_m = n) = (m / n) * P(X_n = m) (hitting-time formula).
    ns = np.arange(2, 11)
    probs = []
    for n in ns:
        if (n + 2) % 2 != 0:
            probs.append(0.0)
            continue
        Pxn = comb(n, (n + 2) // 2) / 2.0 ** n
        probs.append(2.0 / n * Pxn)
    probs = np.array(probs)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(ns, probs, color=TEAL, edgecolor=NAVY)
    for n, p in zip(ns, probs):
        ax.annotate(f"{p:.4f}", (n, p), textcoords="offset points",
                    xytext=(0, 4), ha="center", fontsize=9, color=NAVY)
    ax.set_xticks(ns)
    ax.set_xlabel("$n$")
    ax.set_ylabel("$\\mathbb{P}(\\tau_2 = n)$")
    ax.set_title("First-passage time to $+2$: pmf for $n \\leq 10$")
    plt.tight_layout()
    _save("ch05-tau-hist.png")


def fig_tau_sample_paths():
    rng = np.random.default_rng(7)
    n = 12
    fig, ax = plt.subplots(figsize=(12, 6.2))
    t = np.arange(0, n + 1)
    for i in range(5):
        steps = rng.choice([+1, -1], size=n)
        X = _path_from_steps(steps)
        ax.plot(t, X, color=PALETTE_8[i], lw=2.2, marker="o", ms=6,
                alpha=0.92, label=f"path {i + 1}")
        hits = np.where(X == 2)[0]
        if len(hits) > 0:
            tau = hits[0]
            ax.scatter([tau], [2], color=PALETTE_8[i], s=260, marker="*",
                       edgecolor="black", zorder=6)
    ax.axhline(2, color=GOLD, lw=2.0, ls="--", label="level $m = 2$")
    ax.axhline(0, color=GREY, lw=0.7)
    ax.set_xlabel("step $n$")
    ax.set_ylabel("$X_n$")
    ax.set_xticks(t)
    ax.set_title("Five sample length-12 walks; star marks first hit of $+2$")
    leg = ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5),
                    fontsize=10)
    for line in leg.get_lines():
        line.set_linewidth(3.0)
    plt.tight_layout()
    _save("ch05-tau-sample-paths.png")


# -----------------------------------------------------------------------------
# 5.5 -- Joint pmf heatmap (n = 6) and 3-D Poly3DCollection bars (n = 8)
# -----------------------------------------------------------------------------

def _joint_pmf(n):
    """Return m_vals, h_vals, P[m, h_idx] = P(M_n = m, X_n = h)."""
    all_s = _all_paths(n)
    m_vals = np.arange(0, n + 1)
    h_vals = np.arange(-n, n + 1)
    P = np.zeros((len(m_vals), len(h_vals)))
    for s in all_s:
        X = _path_from_steps(s)
        M = int(X.max())
        h = int(X[-1])
        P[M, h - h_vals[0]] += 1
    P /= 2 ** n
    return m_vals, h_vals, P


def fig_joint_heatmap():
    m_vals, h_vals, P = _joint_pmf(6)
    fig, ax = plt.subplots(figsize=(10, 6))
    Pm = np.ma.masked_equal(P, 0)
    im = ax.imshow(Pm, origin="lower", aspect="auto",
                   extent=[h_vals[0] - 0.5, h_vals[-1] + 0.5,
                           m_vals[0] - 0.5, m_vals[-1] + 0.5],
                   cmap="plasma")
    for i, m in enumerate(m_vals):
        for j, h in enumerate(h_vals):
            v = P[i, j]
            if v > 0:
                ax.text(h, m, f"{v * 64:.0f}/64", ha="center", va="center",
                        color="white" if v < 0.06 else "black", fontsize=8)
    ax.set_xlabel("terminal $X_6 = h$")
    ax.set_ylabel("running max $M_6 = m$")
    ax.set_title("Joint pmf $\\mathbb{P}(M_6 = m,\\ X_6 = h)$ as counts over 64 paths")
    plt.colorbar(im, ax=ax, label="probability")
    plt.tight_layout()
    _save("ch05-joint-heatmap.png")


def fig_joint_bar_3d():
    """3-D joint pmf using filled Poly3DCollection prisms (NOT 3-D bars)."""
    m_vals, h_vals, P = _joint_pmf(8)
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")
    dx = dy = 0.85
    for i, m in enumerate(m_vals):
        for j, h in enumerate(h_vals):
            v = P[i, j]
            if v <= 0:
                continue
            x0, y0, z0 = h - dx / 2, m - dy / 2, 0.0
            x1, y1, z1 = h + dx / 2, m + dy / 2, v
            verts = [
                [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
                [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
                [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
                [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
                [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)],
                [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
            ]
            shade = m / m_vals.max()
            face = plt.cm.viridis(0.15 + 0.75 * shade)
            poly = Poly3DCollection(verts, facecolors=face,
                                    edgecolors=NAVY, linewidths=0.4,
                                    alpha=0.92)
            ax.add_collection3d(poly)
    ax.set_xlim(h_vals[0] - 1, h_vals[-1] + 1)
    ax.set_ylim(m_vals[0] - 1, m_vals[-1] + 1)
    ax.set_zlim(0, P.max() * 1.05)
    ax.set_xlabel("terminal $X_8 = h$", labelpad=10)
    ax.set_ylabel("max $M_8 = m$", labelpad=10)
    ax.set_zlabel("probability", labelpad=10)
    ax.tick_params(axis="x", pad=2)
    ax.tick_params(axis="y", pad=2)
    ax.tick_params(axis="z", pad=4)
    ax.set_title("Joint pmf $\\mathbb{P}(M_8 = m,\\ X_8 = h)$ -- reflection "
                 "identity in 3-D", pad=14)
    ax.view_init(elev=26, azim=-62)
    plt.subplots_adjust(left=0.04, right=0.94, top=0.94, bottom=0.06)
    _save("ch05-joint-bar-3d.png")


# -----------------------------------------------------------------------------
# 5.6 -- Knock-in barrier trees: Toy and Realistic
# -----------------------------------------------------------------------------

def fig_knockin_tree_st():
    # Toy model: S_0 = 4, u = 2, d = 1/2, n = 3, L = 16.
    S0 = 4.0
    u = 2.0
    d = 0.5
    n = 3
    L = 16.0
    fig, ax = plt.subplots(figsize=(11, 6.5))
    steps = _all_paths(n)
    for s in steps:
        S = np.empty(n + 1)
        S[0] = S0
        for k in range(n):
            S[k + 1] = S[k] * (u if s[k] == +1 else d)
        hit = S.max() >= L
        col = GOLD if hit else LIGHTGREY
        lw = 2.4 if hit else 1.4
        alpha = 1.0 if hit else 0.6
        ax.plot(np.arange(n + 1), S, color=col, lw=lw, marker="o", ms=7,
                alpha=alpha)
    ax.axhline(L, color=RED, lw=2.0, ls="--", label=f"barrier $L = {L:.0f}$")
    ax.axhline(S0, color=GREY, lw=0.7, ls=":")
    ax.set_yscale("log", base=2)
    ax.set_yticks([0.5, 1, 2, 4, 8, 16, 32])
    ax.set_yticklabels(["1/2", "1", "2", "4", "8", "16", "32"])
    ax.set_xlabel("step $n$")
    ax.set_ylabel("stock price $S_n$ (log$_2$ scale)")
    ax.set_xticks(range(n + 1))
    ax.set_title(f"Toy model, $n = 3$, $L = {L:.0f}$: gold paths trigger the up-and-in barrier")
    ax.legend(loc="upper left", fontsize=10)
    plt.tight_layout()
    _save("ch05-knockin-tree-st.png")


def fig_knockin_tree_rl():
    # Realistic: S_0 = 100, u = 1.10, d = 0.90, n = 4, L = 120.
    S0 = 100.0
    u = 1.10
    d = 0.90
    n = 4
    L = 120.0
    fig, ax = plt.subplots(figsize=(11, 6.5))
    steps = _all_paths(n)
    for s in steps:
        S = np.empty(n + 1)
        S[0] = S0
        for k in range(n):
            S[k + 1] = S[k] * (u if s[k] == +1 else d)
        hit = S.max() >= L
        col = GOLD if hit else LIGHTGREY
        lw = 2.0 if hit else 1.2
        alpha = 1.0 if hit else 0.55
        ax.plot(np.arange(n + 1), S, color=col, lw=lw, marker="o", ms=6,
                alpha=alpha)
    ax.axhline(L, color=RED, lw=2.0, ls="--", label=f"barrier $L = {L:.0f}$")
    ax.axhline(S0, color=GREY, lw=0.7, ls=":")
    ax.set_xlabel("step $n$")
    ax.set_ylabel("stock price $S_n$")
    ax.set_xticks(range(n + 1))
    ax.set_title(f"Realistic, $u = 1.10$, $d = 0.90$, $n = 4$, $L = {L:.0f}$: "
                 "gold paths trigger up-and-in")
    ax.legend(loc="upper left", fontsize=10)
    plt.tight_layout()
    _save("ch05-knockin-tree-rl.png")


# -----------------------------------------------------------------------------
# 5.6 -- Up-and-in call price vs barrier L (Toy n = 3)
# -----------------------------------------------------------------------------

def fig_ki_price_vs_L():
    S0 = 4.0
    u = 2.0
    d = 0.5
    r = 0.25
    n = 3
    K = 5.0
    p_tilde = ((1 + r) - d) / (u - d)  # = 0.5
    df = 1.0 / (1 + r) ** n
    Ls = [2.0, 4.0, 8.0, 16.0, 32.0]
    steps = _all_paths(n)
    vanilla = 0.0
    for s in steps:
        nU = int((s == +1).sum())
        S = np.empty(n + 1)
        S[0] = S0
        for k in range(n):
            S[k + 1] = S[k] * (u if s[k] == +1 else d)
        payoff = max(S[-1] - K, 0.0)
        prob = (p_tilde ** nU) * ((1 - p_tilde) ** (n - nU))
        vanilla += prob * payoff
    vanilla *= df
    prices = []
    for L in Ls:
        v_in = 0.0
        for s in steps:
            nU = int((s == +1).sum())
            S = np.empty(n + 1)
            S[0] = S0
            for k in range(n):
                S[k + 1] = S[k] * (u if s[k] == +1 else d)
            if S.max() >= L:
                payoff = max(S[-1] - K, 0.0)
                prob = (p_tilde ** nU) * ((1 - p_tilde) ** (n - nU))
                v_in += prob * payoff
        prices.append(v_in * df)
    fig, ax = plt.subplots(figsize=(11.0, 6.4))
    ax.bar(range(len(Ls)), prices, color=GOLD, edgecolor=NAVY, linewidth=1.4)
    ax.axhline(vanilla, color=RED, lw=2.2, ls="--",
               label=f"vanilla call = {vanilla:.4f}")
    for i, p in enumerate(prices):
        ax.annotate(f"{p:.4f}", (i, p), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=11, color=NAVY)
    ax.set_xticks(range(len(Ls)))
    ax.set_xticklabels([f"$L = {L:g}$" for L in Ls], fontsize=11)
    ax.tick_params(axis="y", labelsize=11)
    ax.set_ylabel("up-and-in call price (today)", fontsize=12)
    ax.set_xlabel("barrier level $L$", fontsize=12, labelpad=8)
    ax.set_title("Up-and-in call price vs barrier $L$ -- Toy $n = 3$, $K = 5$",
                 fontsize=13, pad=10)
    # Headroom so legend below the plot does not get clipped, and bar
    # value labels never touch the legend.
    ax.set_ylim(0, vanilla * 1.22)
    # Move the legend below the axes so it never overlaps the bars.
    leg = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14),
                    fontsize=11, framealpha=0.95, ncol=1)
    for line in leg.get_lines():
        line.set_linewidth(3.0)
    plt.tight_layout()
    _save("ch05-ki-price-vs-L.png")


# -----------------------------------------------------------------------------
# 5.7 -- Lookback paths with running peak marked
# -----------------------------------------------------------------------------

def fig_lookback_paths():
    S0 = 4.0
    chosen = [
        np.array([+1, +1, +1]),  # 4, 8, 16, 32
        np.array([+1, -1, +1]),  # 4, 8, 4, 8
        np.array([+1, +1, -1]),  # 4, 8, 16, 8
    ]
    colors = [BLUE, GREEN, ORANGE]
    names = ["UUU", "UDU", "UUD"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    t = np.arange(0, 4)
    for s, c, name in zip(chosen, colors, names):
        S = np.empty(4)
        S[0] = S0
        for k in range(3):
            S[k + 1] = S[k] * (2.0 if s[k] == +1 else 0.5)
        ax.plot(t, S, color=c, lw=2.6, marker="o", ms=8,
                label=f"{name}, $M^S_3 = {S.max():.0f}$")
        ax.scatter([np.argmax(S)], [S.max()], color=c, s=240, marker="*",
                   edgecolor="black", zorder=6)
    ax.axhline(S0, color=GREY, lw=0.7, ls=":")
    ax.set_yscale("log", base=2)
    ax.set_yticks([1, 2, 4, 8, 16, 32])
    ax.set_yticklabels(["1", "2", "4", "8", "16", "32"])
    ax.set_xlabel("step $n$")
    ax.set_ylabel("stock price $S_n$ (log$_2$)")
    ax.set_xticks(t)
    ax.set_title("Three Toy paths and their running maxima (stars); lookback pays $M^S_3 - K$")
    ax.legend(loc="upper left", fontsize=10)
    plt.tight_layout()
    _save("ch05-lookback-paths.png")


# -----------------------------------------------------------------------------
# 5.8 -- American put exercise frontier with sample paths (Toy, n = 4)
# -----------------------------------------------------------------------------

def fig_am_frontier_paths():
    S0 = 4.0
    u = 2.0
    d = 0.5
    r = 0.25
    n = 4
    K = 5.0
    p_tilde = ((1 + r) - d) / (u - d)  # 0.5
    disc = 1.0 / (1 + r)
    V = {}
    exer = {}
    for j in range(n + 1):
        S = S0 * (u ** j) * (d ** (n - j))
        V[(n, j)] = max(K - S, 0.0)
        exer[(n, j)] = (K - S) > 0
    for i in range(n - 1, -1, -1):
        for j in range(i + 1):
            S = S0 * (u ** j) * (d ** (i - j))
            cont = disc * (p_tilde * V[(i + 1, j + 1)]
                           + (1 - p_tilde) * V[(i + 1, j)])
            ex = max(K - S, 0.0)
            V[(i, j)] = max(cont, ex)
            exer[(i, j)] = ex > cont

    fig, ax = plt.subplots(figsize=(12, 7.2))
    for i in range(n + 1):
        for j in range(i + 1):
            S = S0 * (u ** j) * (d ** (i - j))
            col = RED if exer[(i, j)] else GREEN
            ax.scatter([i], [S], color=col, s=280, edgecolor="black",
                       zorder=5)
            # Shift label right for interior nodes, left for the top-rightmost
            # node so it stays inside the axes.
            dx = -34 if i == n and j == i else 10
            ha = "right" if dx < 0 else "left"
            ax.annotate(f"{S:.2f}", (i, S),
                        textcoords="offset points", xytext=(dx, 8),
                        fontsize=8.5, color=NAVY, ha=ha,
                        bbox=dict(boxstyle="round,pad=0.18", fc="white",
                                  ec="none", alpha=0.78), zorder=6)
    for i in range(n):
        for j in range(i + 1):
            S = S0 * (u ** j) * (d ** (i - j))
            ax.plot([i, i + 1], [S, S * u], color=LIGHTGREY, lw=1, zorder=1)
            ax.plot([i, i + 1], [S, S * d], color=LIGHTGREY, lw=1, zorder=1)
    sample_paths = [
        ("DDUU", np.array([-1, -1, +1, +1])),
        ("UDDD", np.array([+1, -1, -1, -1])),
    ]
    cols = [BLUE, PURPLE]
    for (name, s), c in zip(sample_paths, cols):
        S = np.empty(n + 1)
        S[0] = S0
        for k in range(n):
            S[k + 1] = S[k] * (u if s[k] == +1 else d)
        ax.plot(range(n + 1), S, color=c, lw=2.6, marker="o", ms=8,
                label=f"path {name}", alpha=0.95, zorder=4)
    ax.set_yscale("log", base=2)
    ax.set_yticks([0.25, 0.5, 1, 2, 4, 8, 16, 32, 64])
    ax.set_yticklabels(["1/4", "1/2", "1", "2", "4", "8", "16", "32", "64"])
    ax.set_xlabel("step $n$")
    ax.set_ylabel("stock price $S_n$ (log$_2$)")
    ax.set_title("American put $K = 5$, $n = 4$: red = exercise, green = hold; "
                 "sample paths overlaid")
    from matplotlib.lines import Line2D
    leg = [
        Line2D([0], [0], marker="o", color="white", markerfacecolor=RED,
               markeredgecolor="black", markersize=12, label="exercise"),
        Line2D([0], [0], marker="o", color="white", markerfacecolor=GREEN,
               markeredgecolor="black", markersize=12, label="hold"),
        Line2D([0], [0], color=BLUE, lw=2.5, label="path DDUU"),
        Line2D([0], [0], color=PURPLE, lw=2.5, label="path UDDD"),
    ]
    leg_artist = ax.legend(handles=leg, loc="center left",
                           bbox_to_anchor=(1.02, 0.5), fontsize=10)
    ax.set_xticks(range(n + 1))
    plt.tight_layout()
    _save("ch05-am-frontier-paths.png")


# -----------------------------------------------------------------------------
# 5.9 -- Asymptotic max law: discrete reflection -> 2(1 - Phi(a))
# -----------------------------------------------------------------------------

def _P_X_ge(n, m):
    if m > n:
        return 0.0
    if (m + n) % 2 != 0:
        m += 1
    if m > n:
        return 0.0
    ks = np.arange(m, n + 1, 2)
    return sum(comb(n, (n + k) // 2) for k in ks) / 2 ** n


def _P_M_ge(n, m):
    if m <= 0:
        return 1.0
    if (m + n) % 2 != 0:
        m += 1
    if m > n:
        return 0.0
    ks1 = np.arange(m, n + 1, 2)
    ks2 = np.arange(m + 1, n + 1, 2)
    return (sum(comb(n, (n + k) // 2) for k in ks1)
            + sum(comb(n, (n + k) // 2) for k in ks2)) / 2 ** n


def fig_Mn_asymptotic_2panel():
    ns = [20, 50, 100, 500]
    a_grid = np.linspace(0.0, 3.0, 60)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.8))
    for ax, log_y in zip(axes, [False, True]):
        for n, col in zip(ns, [BLUE, GREEN, ORANGE, RED]):
            vals = [_P_M_ge(n, int(np.ceil(a * np.sqrt(n)))) for a in a_grid]
            ax.plot(a_grid, vals, color=col, lw=2.4, label=f"$n = {n}$")
        ax.plot(a_grid, 2 * (1 - norm.cdf(a_grid)), color=NAVY, lw=2.8,
                ls="--", label="$2(1 - \\Phi(a))$")
        ax.set_xlabel("$a$", fontsize=11)
        ax.set_ylabel("$\\mathbb{P}(M_n \\geq a\\sqrt{n})$", fontsize=11)
        if log_y:
            ax.set_yscale("log")
            ax.set_title("log scale", fontsize=12)
        else:
            ax.set_title("linear scale", fontsize=12)
        leg = ax.legend(loc="upper right", fontsize=10, framealpha=0.92)
        for line in leg.get_lines():
            line.set_linewidth(3.0)
    plt.suptitle("Asymptotic max law: discrete reflection $\\to$ "
                 "continuous reflection $2(1 - \\Phi(a))$",
                 y=0.995, fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    _save("ch05-Mn-asymptotic-2panel.png")


def fig_clt_reflection_curves():
    n = 100
    a_grid = np.linspace(0, 3.5, 80)
    xn_vals = [_P_X_ge(n, int(np.ceil(a * np.sqrt(n)))) for a in a_grid]
    mn_vals = [_P_M_ge(n, int(np.ceil(a * np.sqrt(n)))) for a in a_grid]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(a_grid, xn_vals, color=BLUE, lw=2.4,
            label=f"$\\mathbb{{P}}(X_{{{n}}} \\geq a\\sqrt{{n}})$ (exact)")
    ax.plot(a_grid, 1 - norm.cdf(a_grid), color=BLUE, lw=1.8, ls="--",
            label="$1 - \\Phi(a)$ (CLT)")
    ax.plot(a_grid, mn_vals, color=RED, lw=2.4,
            label=f"$\\mathbb{{P}}(M_{{{n}}} \\geq a\\sqrt{{n}})$ (exact)")
    ax.plot(a_grid, 2 * (1 - norm.cdf(a_grid)), color=RED, lw=1.8, ls="--",
            label="$2(1 - \\Phi(a))$ (reflection limit)")
    ax.set_xlabel("$a$")
    ax.set_ylabel("probability")
    ax.set_title(f"At $n = {n}$: exact $X_n$ and $M_n$ tails overlay their "
                 "continuous limits -- reflection survives")
    ax.legend(loc="upper right", fontsize=10)
    plt.tight_layout()
    _save("ch05-clt-reflection-curves.png")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    fig_8_paths()
    fig_paths_vs_stock()
    fig_running_max_staircase()
    fig_three_paths_same_end()
    fig_reflection_twin()
    fig_length5_pairs_4panel()
    fig_bijection_schematic()
    fig_joint_bar_n6()
    fig_tau_hist()
    fig_tau_sample_paths()
    fig_joint_heatmap()
    fig_joint_bar_3d()
    fig_knockin_tree_st()
    fig_knockin_tree_rl()
    fig_ki_price_vs_L()
    fig_lookback_paths()
    fig_am_frontier_paths()
    fig_Mn_asymptotic_2panel()
    fig_clt_reflection_curves()
    print("Chapter 5 figures: done.")
