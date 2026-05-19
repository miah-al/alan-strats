"""
Chapter 6 figure builder for Binomial Option Pricing.

Run: python docs/binomial-option-pricing/_build_ch6_figs.py

Outputs under figures/:
    ch06-rate-lattice-A.png
    ch06-stock-vs-rate-tree.png
    ch06-M3-bar-3d.png
    ch06-bond-tree-A.png
    ch06-bond-surface-3d.png
    ch06-D3-hist.png
    ch06-yield-bars.png
    ch06-yield-shapes.png
    ch06-D3-bar-3d.png
    ch06-forward-vs-expected.png
    ch06-pie-P-vs-PT.png
    ch06-Z3-bar-3d.png
    ch06-caplet-payoff.png
    ch06-caplet-tree.png
    ch06-cap-surface-3d.png
    ch06-cap-floor-vs-K.png
    ch06-bond-call-tree.png
    ch06-swap-pv-bars.png
    ch06-pos-vs-neg-convexity.png
    ch06-callable-tree.png
    ch06-yield-overlay.png
    ch06-calibrated-tree.png

Two running examples used throughout (no third-party labels):
    Toy-A:        r0 = 0.25, u = 2.0,  d = 0.5,  p~ = 1/2
    Realistic-B:  r0 = 0.05, u = 1.25, d = 0.80, p~ = 1/2

3-D bars are drawn as filled Poly3DCollections (NOT ax.bar3d), which renders
cleanly in matplotlib's mpl_toolkits.
"""
from __future__ import annotations

import math
import os
from itertools import product
from math import comb

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cm
from matplotlib.colors import Normalize
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  register 3-D projection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

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


# ---------------------------------------------------------------------------
# Tree helpers
# ---------------------------------------------------------------------------

def rate_tree(r0: float, u: float, d: float, N: int) -> dict:
    """Recombining short-rate tree: (n, k) -> r0 * u^k * d^(n-k)."""
    t = {}
    for n in range(N + 1):
        for k in range(n + 1):
            t[(n, k)] = r0 * (u ** k) * (d ** (n - k))
    return t


def all_paths(N: int) -> list:
    """All 2^N paths as tuples of 0/1 (1 = H)."""
    return list(product([0, 1], repeat=N))


def path_discount(path: tuple, rt: dict) -> float:
    """D_n along path, n = len(path)."""
    n = len(path)
    k = 0
    D = 1.0
    for step in range(n):
        D /= (1.0 + rt[(step, k)])
        if path[step] == 1:
            k += 1
    return D


def bond_tree(rt: dict, T: int) -> dict:
    """Backward-recursion B(n, T) at every (n, k) with n <= T."""
    B = {}
    for k in range(T + 1):
        B[(T, k)] = 1.0
    for n in range(T - 1, -1, -1):
        for k in range(n + 1):
            B[(n, k)] = (0.5 * B[(n + 1, k + 1)]
                         + 0.5 * B[(n + 1, k)]) / (1.0 + rt[(n, k)])
    return B


# Running examples (the only two used in the chapter)
TOY_A = dict(r0=0.25, u=2.0, d=0.5)
REAL_B = dict(r0=0.05, u=1.25, d=0.80)


# ---------------------------------------------------------------------------
# 3-D bar via Poly3DCollection (cuboid faces)
# ---------------------------------------------------------------------------

def _cuboid_faces(x, y, z, dx, dy, dz):
    """6 face-polygons of the cuboid [x, x+dx] x [y, y+dy] x [z, z+dz]."""
    return [
        [(x, y, z), (x + dx, y, z), (x + dx, y + dy, z), (x, y + dy, z)],
        [(x, y, z + dz), (x + dx, y, z + dz),
         (x + dx, y + dy, z + dz), (x, y + dy, z + dz)],
        [(x, y, z), (x + dx, y, z), (x + dx, y, z + dz), (x, y, z + dz)],
        [(x, y + dy, z), (x + dx, y + dy, z),
         (x + dx, y + dy, z + dz), (x, y + dy, z + dz)],
        [(x, y, z), (x, y + dy, z), (x, y + dy, z + dz), (x, y, z + dz)],
        [(x + dx, y, z), (x + dx, y + dy, z),
         (x + dx, y + dy, z + dz), (x + dx, y, z + dz)],
    ]


def _bars3d(ax, xs, ys, zs_top, dx, dy, colors,
            edgecolor=NAVY, alpha=0.95):
    """Draw 3-D bars as filled Poly3DCollections."""
    for x, y, z, c in zip(xs, ys, zs_top, colors):
        faces = _cuboid_faces(x, y, 0.0, dx, dy, z)
        poly = Poly3DCollection(faces, facecolors=c,
                                edgecolors=edgecolor,
                                linewidths=0.4, alpha=alpha)
        ax.add_collection3d(poly)


# ---------------------------------------------------------------------------
# Section 6.1 figures
# ---------------------------------------------------------------------------

def fig_rate_lattice_A():
    N = 3
    rt = rate_tree(**TOY_A, N=N)
    fig, ax = plt.subplots(figsize=(10, 6))
    vals = np.array(list(rt.values()))
    norm = Normalize(vmin=vals.min(), vmax=vals.max())
    cmap = cm.get_cmap("plasma")
    for (n, k), r in rt.items():
        x, y = n, k - n / 2
        ax.scatter([x], [y], s=2000, color=cmap(norm(r)),
                   edgecolor=NAVY, alpha=0.95, zorder=3)
        ax.text(x, y, f"{r:g}", ha="center", va="center",
                fontsize=9,
                color="white" if norm(r) > 0.5 else "black",
                fontweight="bold", zorder=4)
    for n in range(N):
        for k in range(n + 1):
            xa, ya = n, k - n / 2
            for dk in (0, 1):
                ax.plot([xa, n + 1], [ya, (k + dk) - (n + 1) / 2],
                        color=GREY, lw=1.0, alpha=0.6, zorder=1)
    ax.set_xlim(-0.5, N + 0.5)
    ax.set_ylim(-N / 2 - 0.7, N / 2 + 0.7)
    ax.set_xlabel("step $n$")
    ax.set_yticks([])
    ax.set_title(r"Toy-A short-rate lattice: $r_0 = 0.25,\ u = 2,\ d = 0.5$")
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label=r"$r_n$", shrink=0.7)
    ax.grid(False)
    fig.tight_layout()
    _save("ch06-rate-lattice-A.png")


def fig_stock_vs_rate_tree():
    N = 3
    S0, u_s, d_s = 4.0, 2.0, 0.5
    rt = rate_tree(**TOY_A, N=N)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))

    # Stock tree (left)
    ax = axes[0]
    ax.set_title(r"Chapter 5 — stock tree ($S_0=4,\ u=2,\ d=0.5$)")
    for n in range(N + 1):
        for k in range(n + 1):
            x = n
            y = k - n / 2
            price = S0 * (u_s ** k) * (d_s ** (n - k))
            ax.scatter([x], [y], s=1500, color=ORANGE,
                       edgecolor="#b85a00", alpha=0.95, zorder=3)
            ax.text(x, y, f"{price:g}", ha="center", va="center",
                    color="white", fontsize=9,
                    fontweight="bold", zorder=4)
    for n in range(N):
        for k in range(n + 1):
            xa, ya = n, k - n / 2
            for dk in (0, 1):
                ax.plot([xa, n + 1], [ya, (k + dk) - (n + 1) / 2],
                        color=GREY, lw=0.8, alpha=0.5, zorder=1)
    ax.set_xlim(-0.5, N + 0.5)
    ax.set_ylim(-N / 2 - 0.7, N / 2 + 0.7)
    ax.set_yticks([])
    ax.set_xlabel("step $n$")

    # Rate tree (right)
    ax = axes[1]
    ax.set_title(r"Chapter 6 — short-rate tree ($r_0=0.25,\ u=2,\ d=0.5$)")
    for (n, k), r in rt.items():
        x = n
        y = k - n / 2
        ax.scatter([x], [y], s=1500, color=BLUE,
                   edgecolor=NAVY, alpha=0.95, zorder=3)
        ax.text(x, y, f"{r:g}", ha="center", va="center",
                color="white", fontsize=8,
                fontweight="bold", zorder=4)
    for n in range(N):
        for k in range(n + 1):
            xa, ya = n, k - n / 2
            for dk in (0, 1):
                ax.plot([xa, n + 1], [ya, (k + dk) - (n + 1) / 2],
                        color=GREY, lw=0.8, alpha=0.5, zorder=1)
    ax.set_xlim(-0.5, N + 0.5)
    ax.set_ylim(-N / 2 - 0.7, N / 2 + 0.7)
    ax.set_yticks([])
    ax.set_xlabel("step $n$")

    fig.suptitle("Same lattice shape, different underlying object.",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    _save("ch06-stock-vs-rate-tree.png")


def fig_M3_bar_3d():
    rt = rate_tree(**TOY_A, N=3)
    paths = all_paths(3)
    M3 = []
    labels = []
    for p in paths:
        k0 = 0
        k1 = k0 + p[0]
        k2 = k1 + p[1]
        m = ((1 + rt[(0, k0)])
             * (1 + rt[(1, k1)])
             * (1 + rt[(2, k2)]))
        M3.append(m)
        labels.append("".join("H" if x else "T" for x in p))

    fig = plt.figure(figsize=(11, 6.5))
    ax = fig.add_subplot(111, projection="3d")
    xs = np.arange(len(paths), dtype=float)
    ys = np.zeros_like(xs)
    cmap = cm.get_cmap("plasma")
    norm = Normalize(vmin=min(M3), vmax=max(M3))
    colors = [cmap(norm(m)) for m in M3]
    _bars3d(ax, xs - 0.4, ys - 0.4, M3, 0.8, 0.8, colors)

    mean_M3 = float(np.mean(M3))
    det_M3 = (1 + TOY_A["r0"]) ** 3
    X, Y = np.meshgrid(
        np.array([-0.5, len(paths) - 0.5]),
        np.array([-0.5, 0.5]),
    )
    ax.plot_surface(X, Y, np.full_like(X, mean_M3),
                    color=BLUE, alpha=0.18,
                    edgecolor=BLUE, linewidth=0.5)
    ax.plot_surface(X, Y, np.full_like(X, det_M3),
                    color=RED, alpha=0.15,
                    edgecolor=RED, linewidth=0.5)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_yticks([])
    ax.set_zlabel(r"$M_3(\omega)$")
    ax.set_title(
        "Toy-A money-market $M_3$ across 8 paths\n"
        r"Blue plane: $\tilde E[M_3]$ = "
        + f"{mean_M3:.3f}; "
        + r"red plane: $(1+r_0)^3$ = "
        + f"{det_M3:.3f}"
    )
    ax.view_init(elev=25, azim=-65)
    fig.tight_layout()
    _save("ch06-M3-bar-3d.png")


# ---------------------------------------------------------------------------
# Section 6.2 figures
# ---------------------------------------------------------------------------

def fig_bond_tree_A():
    rt = rate_tree(**TOY_A, N=3)
    B = bond_tree(rt, T=3)
    fig, ax = plt.subplots(figsize=(10, 6))
    cmap = cm.get_cmap("viridis")
    norm = Normalize(vmin=0.0, vmax=1.0)
    for (n, k), b in B.items():
        x = n
        y = k - n / 2
        ax.scatter([x], [y], s=1800, color=cmap(norm(b)),
                   edgecolor=NAVY, alpha=0.95, zorder=3)
        ax.text(x, y, f"{b:.4f}", ha="center", va="center",
                color="white" if norm(b) < 0.6 else "black",
                fontsize=8, fontweight="bold", zorder=4)
    for n in range(3):
        for k in range(n + 1):
            xa, ya = n, k - n / 2
            for dk in (0, 1):
                ax.plot([xa, n + 1], [ya, (k + dk) - (n + 1) / 2],
                        color=GREY, lw=0.8, alpha=0.6, zorder=1)
    ax.set_xlim(-0.5, 3.5)
    ax.set_ylim(-1.7, 1.7)
    ax.set_yticks([])
    ax.set_xlabel("step $n$")
    ax.set_title(r"Toy-A bond-price tree $B(n, 3)$ — colour = bond price")
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label=r"$B(n, 3)$", shrink=0.7)
    ax.grid(False)
    fig.tight_layout()
    _save("ch06-bond-tree-A.png")


def fig_bond_surface_3d():
    rt = rate_tree(**REAL_B, N=8)
    N_max = 8
    T_max = 8
    Z = np.full((N_max + 1, T_max + 1), np.nan)
    for T in range(1, T_max + 1):
        B = bond_tree(rt, T=T)
        for n in range(T + 1):
            k = n // 2  # centre path
            Z[n, T] = B[(n, k)]

    fig = plt.figure(figsize=(11, 7))
    ax = fig.add_subplot(111, projection="3d")
    nn, TT = np.meshgrid(
        np.arange(N_max + 1),
        np.arange(T_max + 1),
        indexing="ij",
    )
    valid = ~np.isnan(Z)
    xs = nn[valid].astype(float).ravel()
    ys = TT[valid].astype(float).ravel()
    zs = Z[valid].ravel()
    cmap = cm.get_cmap("viridis")
    norm = Normalize(0.0, 1.0)
    colors = [cmap(norm(z)) for z in zs]
    _bars3d(ax, xs - 0.4, ys - 0.4, zs, 0.8, 0.8,
            colors, alpha=0.92)

    ax.set_xlabel(r"$n$ (time)")
    ax.set_ylabel(r"$T$ (maturity)")
    ax.set_zlabel(r"$B(n, T)$")
    ax.set_title(
        "Realistic-B bond-price surface $B(n, T)$\n"
        "(centre-path node at each $n$)"
    )
    ax.view_init(elev=27, azim=-60)
    fig.tight_layout()
    _save("ch06-bond-surface-3d.png")


def fig_D3_hist():
    rt = rate_tree(**TOY_A, N=3)
    paths = all_paths(3)
    D3 = [path_discount(p, rt) for p in paths]
    labels = ["".join("H" if x else "T" for x in p) for p in paths]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    cmap = cm.get_cmap("plasma")
    norm = Normalize(min(D3), max(D3))
    colors = [cmap(norm(d)) for d in D3]
    bars = ax.bar(labels, D3, color=colors,
                  edgecolor=NAVY, linewidth=0.6)
    mean_D3 = float(np.mean(D3))
    ax.axhline(
        mean_D3, color=RED, lw=2.0, linestyle="--",
        label=r"$\tilde E[D_3] = B(0,3) = " + f"{mean_D3:.4f}$",
    )
    for b, d in zip(bars, D3):
        ax.text(b.get_x() + b.get_width() / 2,
                b.get_height() + 0.01,
                f"{d:.3f}", ha="center", fontsize=8)
    ax.set_ylabel(r"$D_3(\omega)$")
    ax.set_xlabel(r"path $\omega$")
    ax.set_title(
        "Toy-A discount factor $D_3$ across 8 paths\n"
        r"Pairs of equal bars: $D_3$ depends only on $r_0, r_1, r_2$"
    )
    # Headroom + legend below title to avoid covering tallest bar labels.
    ax.set_ylim(0, max(D3) * 1.18)
    ax.legend(loc="upper right", framealpha=0.95)
    fig.tight_layout()
    _save("ch06-D3-hist.png")


# ---------------------------------------------------------------------------
# Section 6.3 figures
# ---------------------------------------------------------------------------

def fig_yield_bars():
    rt = rate_tree(**TOY_A, N=8)
    Ts = list(range(1, 8))
    B0T = [bond_tree(rt, T)[(0, 0)] for T in Ts]
    y = [-math.log(b) / T for b, T in zip(B0T, Ts)]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    cmap = cm.get_cmap("viridis")
    norm = Normalize(min(Ts), max(Ts))
    colors = [cmap(norm(T)) for T in Ts]
    bars = ax.bar(Ts, y, color=colors,
                  edgecolor=NAVY, linewidth=0.6)
    for b, yi in zip(bars, y):
        ax.text(b.get_x() + b.get_width() / 2,
                b.get_height() + 0.003,
                f"{yi:.3f}", ha="center", fontsize=9)
    ax.set_xlabel(r"maturity $T$")
    ax.set_ylabel(r"continuous yield $y(0, T)$")
    ax.set_title(r"Toy-A yield curve: $y(0,T) = -\ln B(0,T)/T$")
    fig.tight_layout()
    _save("ch06-yield-bars.png")


def fig_yield_shapes():
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    Ts = np.arange(1, 11)

    # 1. Flat
    rt = rate_tree(r0=0.05, u=1.0, d=1.0, N=12)
    y = [-math.log(bond_tree(rt, T)[(0, 0)]) / T for T in Ts]
    axes[0, 0].plot(Ts, y, "o-", color=BLUE, lw=2.5, ms=8)
    axes[0, 0].set_title(r"Flat: $u = d = 1$")

    # 2. Upward (Realistic-B)
    rt = rate_tree(**REAL_B, N=12)
    y = [-math.log(bond_tree(rt, T)[(0, 0)]) / T for T in Ts]
    axes[0, 1].plot(Ts, y, "o-", color=ORANGE, lw=2.5, ms=8)
    axes[0, 1].set_title(r"Gentle upward: $u=1.25,\ d=0.8$ (Realistic-B)")

    # 3. Inverted
    rt = rate_tree(r0=0.08, u=0.85, d=1.05, N=12)
    y = [-math.log(bond_tree(rt, T)[(0, 0)]) / T for T in Ts]
    axes[1, 0].plot(Ts, y, "o-", color=RED, lw=2.5, ms=8)
    axes[1, 0].set_title(r"Inverted: $u < 1 < d$")

    # 4. Humped: regime-switch
    N = 12
    rt_h = {(0, 0): 0.04}
    for n in range(N):
        u_n = 1.18 if n < 3 else 0.92
        d_n = 1.0 / u_n
        for k in range(n + 1):
            rt_h[(n + 1, k + 1)] = rt_h[(n, k)] * u_n
            rt_h[(n + 1, k)] = rt_h[(n, k)] * d_n
    y = []
    for T in Ts:
        Bl = {(T, k): 1.0 for k in range(T + 1)}
        for n in range(T - 1, -1, -1):
            for k in range(n + 1):
                Bl[(n, k)] = (
                    (0.5 * Bl[(n + 1, k + 1)]
                     + 0.5 * Bl[(n + 1, k)])
                    / (1.0 + rt_h[(n, k)])
                )
        y.append(-math.log(Bl[(0, 0)]) / T)
    axes[1, 1].plot(Ts, y, "o-", color=PURPLE, lw=2.5, ms=8)
    axes[1, 1].set_title(r"Humped: regime switch in $u, d$ at $n=3$")

    for ax in axes.flat:
        ax.set_xlabel(r"maturity $T$")
        ax.set_ylabel(r"yield $y(0, T)$")
    fig.suptitle(
        "Four canonical yield-curve shapes from binomial short-rate trees",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    _save("ch06-yield-shapes.png")


# ---------------------------------------------------------------------------
# Section 6.4 figure
# ---------------------------------------------------------------------------

def fig_D3_bar_3d():
    rt = rate_tree(**TOY_A, N=3)
    paths = all_paths(3)
    D3 = [path_discount(p, rt) for p in paths]
    labels = ["".join("H" if x else "T" for x in p) for p in paths]

    fig = plt.figure(figsize=(11, 6.5))
    ax = fig.add_subplot(111, projection="3d")
    xs = np.arange(len(paths), dtype=float)
    ys = np.zeros_like(xs)
    cmap = cm.get_cmap("plasma")
    norm = Normalize(min(D3), max(D3))
    colors = [cmap(norm(d)) for d in D3]
    _bars3d(ax, xs - 0.4, ys - 0.4, D3, 0.8, 0.8, colors)

    mean_D3 = float(np.mean(D3))
    X, Y = np.meshgrid([-0.5, len(paths) - 0.5], [-0.5, 0.5])
    ax.plot_surface(X, Y, np.full_like(X, mean_D3),
                    color=RED, alpha=0.20,
                    edgecolor=RED, linewidth=0.8)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_yticks([])
    ax.set_zlabel(r"$D_3(\omega)$")
    ax.set_title(
        "Toy-A discount factor $D_3$ across 8 paths\n"
        r"Red plane: $B(0,3) = \tilde E[D_3] = "
        + f"{mean_D3:.4f}$"
    )
    ax.view_init(elev=25, azim=-65)
    fig.tight_layout()
    _save("ch06-D3-bar-3d.png")


# ---------------------------------------------------------------------------
# Section 6.5 figure
# ---------------------------------------------------------------------------

def fig_forward_vs_expected():
    rt = rate_tree(**TOY_A, N=6)
    Ts = list(range(7))
    B0T = [bond_tree(rt, T)[(0, 0)] if T > 0 else 1.0 for T in Ts]
    fwd = [(B0T[t] / B0T[t + 1]) - 1 for t in range(len(Ts) - 1)]
    Er = []
    for t in range(len(Ts) - 1):
        s = 0.0
        for k in range(t + 1):
            s += comb(t, k) / (2 ** t) * rt[(t, k)]
        Er.append(s)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ts = np.arange(len(fwd))
    ax.plot(ts, Er, "o-", color=RED, lw=2.5, ms=10,
            label=r"$\tilde E[r_t]$ (expected short)")
    ax.plot(ts, fwd, "s-", color=BLUE, lw=2.5, ms=10,
            label=r"$f(0, t, t+1)$ (forward rate)")
    ax.fill_between(ts, Er, fwd, color=GOLD, alpha=0.3,
                    label="Jensen gap")
    for t, e, f in zip(ts, Er, fwd):
        ax.annotate(
            f"gap={e - f:+.3f}",
            xy=(t, (e + f) / 2),
            fontsize=8, ha="center",
            bbox=dict(boxstyle="round,pad=0.2",
                      fc="white", ec=GREY, alpha=0.85),
        )
    ax.set_xlabel(r"$t$")
    ax.set_ylabel("rate")
    ax.set_title(
        r"Toy-A: forward rates $f(0, t, t+1)$ vs $\tilde E[r_t]$"
        + "\nForwards sit below expected shorts (Jensen gap)."
    )
    ax.legend()
    fig.tight_layout()
    _save("ch06-forward-vs-expected.png")


# ---------------------------------------------------------------------------
# Section 6.6 figures
# ---------------------------------------------------------------------------

def fig_pie_P_vs_PT():
    rt = rate_tree(**TOY_A, N=3)
    paths = all_paths(3)
    D3 = [path_discount(p, rt) for p in paths]
    B03 = float(np.mean(D3))
    PT = [d / B03 / 8 for d in D3]
    labels = ["".join("H" if x else "T" for x in p) for p in paths]
    cmap = cm.get_cmap("plasma")
    colors = [cmap(i / len(paths)) for i in range(len(paths))]

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    axes[0].pie([1 / 8] * 8, labels=labels, colors=colors,
                autopct="%.3f", startangle=90,
                wedgeprops=dict(edgecolor="white", linewidth=1))
    axes[0].set_title(r"$\tilde P$: uniform $1/8$ across 8 paths")

    axes[1].pie(PT, labels=labels, colors=colors,
                autopct="%.3f", startangle=90,
                wedgeprops=dict(edgecolor="white", linewidth=1))
    axes[1].set_title(
        r"$P^3 = (D_3/B(0,3))\cdot\tilde P$: tilted to low-rate paths"
    )
    fig.suptitle(
        r"Same paths, two measures. $P^3$ rebalances away from high rates.",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    _save("ch06-pie-P-vs-PT.png")


def fig_Z3_bar_3d():
    rt = rate_tree(**TOY_A, N=3)
    paths = all_paths(3)
    D3 = [path_discount(p, rt) for p in paths]
    B03 = float(np.mean(D3))
    Z3 = [d / B03 for d in D3]
    labels = ["".join("H" if x else "T" for x in p) for p in paths]

    fig = plt.figure(figsize=(11, 6.5))
    ax = fig.add_subplot(111, projection="3d")
    xs = np.arange(len(paths), dtype=float)
    ys = np.zeros_like(xs)
    cmap = cm.get_cmap("plasma")
    norm = Normalize(min(Z3), max(Z3))
    colors = [cmap(norm(z)) for z in Z3]
    _bars3d(ax, xs - 0.4, ys - 0.4, Z3, 0.8, 0.8, colors)

    X, Y = np.meshgrid([-0.5, len(paths) - 0.5], [-0.5, 0.5])
    ax.plot_surface(X, Y, np.ones_like(X),
                    color=RED, alpha=0.15,
                    edgecolor=RED, linewidth=0.5)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_yticks([])
    ax.set_zlabel(r"$Z_3(\omega) = D_3/B(0,3)$")
    ax.set_title(
        "Toy-A Radon-Nikodym density $Z_3$\n"
        r"Red plane: $\tilde E[Z_3] = 1$"
    )
    ax.view_init(elev=25, azim=-65)
    fig.tight_layout()
    _save("ch06-Z3-bar-3d.png")


# ---------------------------------------------------------------------------
# Section 6.7 figures
# ---------------------------------------------------------------------------

def fig_caplet_payoff():
    K = 0.30
    r = np.linspace(0.0, 1.0, 200)
    payoff = np.maximum(r - K, 0.0)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.fill_between(r, payoff, color=GOLD, alpha=0.5,
                    label=r"payoff $(r - K)^+$")
    ax.plot(r, payoff, color=ORANGE, lw=3.0)
    ax.axvline(K, color=RED, lw=1.5, linestyle="--",
               label=f"$K = {K}$")
    ax.scatter([0.5], [0.20], color=BLUE, s=120, zorder=5,
               label=r"Toy-A $r_1(H) = 0.5$ — ITM, payoff 0.20")
    ax.scatter([0.125], [0.0], color=GREEN, s=120, zorder=5,
               label=r"Toy-A $r_1(T) = 0.125$ — OTM, payoff 0")
    ax.set_xlabel(r"realised short rate $r$")
    ax.set_ylabel(r"caplet payoff at $n+1$")
    ax.set_title(
        f"Caplet payoff $(r - K)^+$ at strike $K = {K}$. "
        "Two Toy-A nodes overlaid."
    )
    ax.legend()
    fig.tight_layout()
    _save("ch06-caplet-payoff.png")


def fig_caplet_tree():
    K = 0.30
    n_caplet = 2  # caplet on r_2, pays at n=3
    rt = rate_tree(**TOY_A, N=3)
    V = {}
    for k in range(n_caplet + 1):
        payoff = max(rt[(n_caplet, k)] - K, 0.0)
        V[(n_caplet, k)] = payoff / (1.0 + rt[(n_caplet, k)])
    for n in range(n_caplet - 1, -1, -1):
        for k in range(n + 1):
            V[(n, k)] = (
                (0.5 * V[(n + 1, k + 1)]
                 + 0.5 * V[(n + 1, k)])
                / (1.0 + rt[(n, k)])
            )

    fig, ax = plt.subplots(figsize=(13, 8))
    vals = list(V.values())
    cmap = cm.get_cmap("plasma")
    vmax = max(vals) if max(vals) > 0 else 1.0
    norm = Normalize(0.0, vmax)
    # Vertical spread between sibling nodes so labels never collide.
    Y_SCALE = 1.25
    for (n, k), v in V.items():
        x = n
        y = (k - n / 2) * Y_SCALE
        r = rt[(n, k)]
        edge = RED if r > K else NAVY
        lw = 2.2 if r > K else 0.8
        ax.scatter([x], [y], s=900, color=cmap(norm(v)),
                   edgecolor=edge, linewidth=lw,
                   alpha=0.95, zorder=3)
        # V-label placed clearly ABOVE the disc.
        ax.text(x, y + 0.34, f"V={v:.4f}", ha="center",
                va="bottom", fontsize=10, color=NAVY,
                fontweight="bold", zorder=4)
        # r-label placed clearly BELOW the disc.
        ax.text(x, y - 0.34, f"r={r:.3f}", ha="center",
                va="top", fontsize=10, color=NAVY, zorder=4)
    for n in range(n_caplet):
        for k in range(n + 1):
            xa, ya = n, (k - n / 2) * Y_SCALE
            for dk in (0, 1):
                ax.plot([xa, n + 1],
                        [ya, ((k + dk) - (n + 1) / 2) * Y_SCALE],
                        color=GREY, lw=0.8, alpha=0.5, zorder=1)
    ax.set_xlim(-0.9, 2.9)
    ax.set_ylim(-n_caplet / 2 * Y_SCALE - 0.9,
                n_caplet / 2 * Y_SCALE + 0.9)
    ax.set_yticks([])
    ax.set_xlabel("step $n$")
    ax.set_title(
        f"Toy-A caplet on $r_2$ at $K = {K}$ — backward-induction value\n"
        r"Red-bordered nodes: $r \geq K$ (ITM at that node)"
    )
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label=r"$V_n$", shrink=0.7)
    ax.grid(False)
    fig.tight_layout()
    _save("ch06-caplet-tree.png")


def _cap_price(rt: dict, K: float, N_cap: int) -> float:
    """Total cap price = sum of caplets on r_1,...,r_N_cap."""
    total = 0.0
    for n in range(1, N_cap + 1):
        vp = 0.0
        for path in all_paths(n):
            D = path_discount(path, rt)
            k_end = sum(path)
            r_n = rt[(n, k_end)]
            payoff = max(r_n - K, 0.0)
            vp += D * payoff / (1.0 + r_n) / (2 ** n)
        total += vp
    return total


def _floor_price(rt: dict, K: float, N_cap: int) -> float:
    total = 0.0
    for n in range(1, N_cap + 1):
        vp = 0.0
        for path in all_paths(n):
            D = path_discount(path, rt)
            k_end = sum(path)
            r_n = rt[(n, k_end)]
            payoff = max(K - r_n, 0.0)
            vp += D * payoff / (1.0 + r_n) / (2 ** n)
        total += vp
    return total


def fig_cap_surface_3d():
    rt = rate_tree(**TOY_A, N=6)
    Ks = np.linspace(0.05, 0.80, 16)
    Ns = list(range(1, 6))
    Z = np.zeros((len(Ks), len(Ns)))
    for i, K in enumerate(Ks):
        for j, N_cap in enumerate(Ns):
            Z[i, j] = _cap_price(rt, K, N_cap)

    fig = plt.figure(figsize=(11, 7))
    ax = fig.add_subplot(111, projection="3d")
    K_grid, N_grid = np.meshgrid(Ks, Ns, indexing="ij")
    cmap = cm.get_cmap("plasma")
    surf = ax.plot_surface(K_grid, N_grid, Z, cmap=cmap,
                           edgecolor=NAVY, linewidth=0.3,
                           alpha=0.92)
    ax.set_xlabel(r"strike $K$")
    ax.set_ylabel(r"cap tenor $N$")
    ax.set_zlabel("cap price")
    ax.set_title(
        "Toy-A cap price surface: decreasing in $K$, increasing in $N$"
    )
    ax.view_init(elev=25, azim=-55)
    fig.colorbar(surf, ax=ax, shrink=0.6, label="cap price")
    fig.tight_layout()
    _save("ch06-cap-surface-3d.png")


# ---------------------------------------------------------------------------
# Section 6.8 figure
# ---------------------------------------------------------------------------

def fig_cap_floor_vs_K():
    rt = rate_tree(**TOY_A, N=4)
    Ks = np.linspace(0.05, 0.75, 30)
    N_cap = 3
    cap = [_cap_price(rt, K, N_cap) for K in Ks]
    floor = [_floor_price(rt, K, N_cap) for K in Ks]

    B0T = [bond_tree(rt, T)[(0, 0)] for T in range(1, N_cap + 1)]
    S_par = (1 - B0T[-1]) / sum(B0T)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(Ks, cap, color=BLUE, lw=2.5,
            label=r"Cap$(K,\, N=3)$")
    ax.plot(Ks, floor, color=ORANGE, lw=2.5,
            label=r"Floor$(K,\, N=3)$")
    ax.axvline(S_par, color=RED, lw=1.5, linestyle="--",
               label=f"par swap rate $S = {S_par:.4f}$")
    ax.set_xlabel(r"strike $K$")
    ax.set_ylabel("price")
    ax.set_title(
        "Toy-A: cap and floor prices vs strike\n"
        "They cross at the par swap rate"
    )
    ax.legend()
    fig.tight_layout()
    _save("ch06-cap-floor-vs-K.png")


# ---------------------------------------------------------------------------
# Section 6.9 figure
# ---------------------------------------------------------------------------

def fig_bond_call_tree():
    K = 0.70
    rt = rate_tree(**TOY_A, N=3)
    B23 = {(2, k): 1.0 / (1.0 + rt[(2, k)]) for k in range(3)}
    V = {(2, k): max(B23[(2, k)] - K, 0.0) for k in range(3)}
    for n in range(1, -1, -1):
        for k in range(n + 1):
            V[(n, k)] = (
                (0.5 * V[(n + 1, k + 1)]
                 + 0.5 * V[(n + 1, k)])
                / (1.0 + rt[(n, k)])
            )

    fig, ax = plt.subplots(figsize=(12, 7))
    cmap = cm.get_cmap("plasma")
    vals = list(V.values())
    vmax = max(vals) if max(vals) > 0 else 1.0
    norm = Normalize(min(vals), vmax)
    for (n, k), v in V.items():
        x = n
        y = k - n / 2
        r = rt[(n, k)]
        b = B23.get((n, k)) if n == 2 else None
        itm = (n == 2 and b is not None and b > K)
        edge = RED if itm else NAVY
        lw = 2.5 if itm else 0.7
        ax.scatter([x], [y], s=1500, color=cmap(norm(v)),
                   edgecolor=edge, linewidth=lw,
                   alpha=0.95, zorder=3)
        # Labels offset clearly outside the disc.
        ax.text(x, y + 0.22, f"V={v:.4f}", ha="center", va="bottom",
                fontsize=9, color=NAVY, fontweight="bold", zorder=4)
        ax.text(x, y - 0.22, f"r={r:.3f}", ha="center", va="top",
                fontsize=8.5, color=NAVY, zorder=4)
        if n == 2:
            ax.text(x, y - 0.40, f"B={b:.3f}",
                    ha="center", va="top",
                    fontsize=8.5, color=ORANGE,
                    fontweight="bold", zorder=4)
    for n in range(2):
        for k in range(n + 1):
            xa, ya = n, k - n / 2
            for dk in (0, 1):
                ax.plot([xa, n + 1], [ya, (k + dk) - (n + 1) / 2],
                        color=GREY, lw=0.8, alpha=0.5, zorder=1)
    ax.set_xlim(-0.7, 2.7)
    ax.set_ylim(-2.0, 2.0)
    ax.set_yticks([])
    ax.set_xlabel("step $n$")
    ax.set_title(
        f"Toy-A: European call on $B(2, 3)$ at strike $K = {K}$\n"
        r"Red-bordered $n=2$ nodes are ITM ($B \geq K$)"
    )
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label=r"call value $V_n$", shrink=0.7)
    ax.grid(False)
    fig.tight_layout()
    _save("ch06-bond-call-tree.png")


# ---------------------------------------------------------------------------
# Section 6.10 figure
# ---------------------------------------------------------------------------

def fig_swap_pv_bars():
    rt = rate_tree(**REAL_B, N=4)
    N = 3
    B0T = [bond_tree(rt, T)[(0, 0)] for T in range(1, N + 1)]
    sum_B = sum(B0T)
    floating_pv = 1 - B0T[-1]
    Ks = np.linspace(0.02, 0.08, 13)
    fixed_pvs = Ks * sum_B
    swap_pvs = floating_pv - fixed_pvs
    S_par = floating_pv / sum_B

    fig, ax = plt.subplots(figsize=(11, 6))
    width = (Ks[1] - Ks[0]) * 0.4
    ax.bar(Ks - width / 2, [floating_pv] * len(Ks), width,
           color=BLUE, alpha=0.85,
           label=r"Floating PV $= 1 - B(0, N) = "
                 + f"{floating_pv:.4f}$")
    ax.bar(Ks + width / 2, fixed_pvs, width,
           color=ORANGE, alpha=0.85,
           label=r"Fixed PV $= K \cdot \sum B$")
    ax.plot(Ks, swap_pvs, "o-", color=GREEN, lw=2.5, ms=8,
            label=r"Payer Swap PV (Floating $-$ Fixed)")
    ax.axvline(S_par, color=RED, lw=1.5, linestyle="--",
               label=f"par swap rate $S = {S_par:.4f}$")
    ax.axhline(0, color="black", lw=0.6, alpha=0.5)
    ax.set_xlabel(r"fixed-leg strike $K$")
    ax.set_ylabel("PV")
    ax.set_title(
        "Realistic-B, $N = 3$: floating vs fixed PV across strikes\n"
        "Crossing at $K = S$"
    )
    ax.legend()
    fig.tight_layout()
    _save("ch06-swap-pv-bars.png")


# ---------------------------------------------------------------------------
# Section 6.11 — Negative-convexity figures (callable bond on Toy-A)
# ---------------------------------------------------------------------------

def _toyA_rates_shifted(delta: float) -> dict:
    """Toy-A short rates with an additive parallel shift delta at every node."""
    rt = rate_tree(**TOY_A, N=2)
    return {key: r + delta for key, r in rt.items()}


def _straight_coupon_bond(rt: dict, c: float, N: int = 3) -> dict:
    """Backward-recursion straight coupon bond.

    Coupons c paid at n=1..N, face 1 at n=N.
    Convention: V_n is the cum-future-coupon ex-current-coupon value at the
    end of period n; V_N = 1, and the parent receives V_{n+1}+c discounted
    by (1+r_n)^{-1}.
    """
    V = {(N, k): 1.0 for k in range(N + 1)}
    for n in range(N - 1, -1, -1):
        for k in range(n + 1):
            r = rt[(n, k)]
            V[(n, k)] = (0.5 * (V[(n + 1, k + 1)] + c)
                         + 0.5 * (V[(n + 1, k)] + c)) / (1.0 + r)
    return V


def _callable_coupon_bond(rt: dict, c: float, K_call: float,
                          N: int = 3) -> tuple:
    """Issuer-callable coupon bond: continuation min'd against K_call at
    every non-terminal node except n=0 (issuance date). Returns (V_dict,
    called_dict) where called_dict[(n,k)] is True iff the issuer optimally
    calls at that node.
    """
    V = {(N, k): 1.0 for k in range(N + 1)}
    called = {}
    for n in range(N - 1, -1, -1):
        for k in range(n + 1):
            r = rt[(n, k)]
            cont = (0.5 * (V[(n + 1, k + 1)] + c)
                    + 0.5 * (V[(n + 1, k)] + c)) / (1.0 + r)
            if n == 0:
                V[(n, k)] = cont
                called[(n, k)] = False
            else:
                if cont > K_call:
                    V[(n, k)] = K_call
                    called[(n, k)] = True
                else:
                    V[(n, k)] = cont
                    called[(n, k)] = False
    return V, called


def fig_pos_vs_neg_convexity():
    """Side-by-side price-vs-rate-shift curves: straight bond (positively
    convex) vs callable bond (negative convexity zone visible)."""
    c = 0.25
    K_call = 1.0
    deltas = np.linspace(-0.22, 0.22, 89)
    V_str, V_call, embedded = [], [], []
    for d in deltas:
        rt = _toyA_rates_shifted(d)
        Vs = _straight_coupon_bond(rt, c)
        Vc, _ = _callable_coupon_bond(rt, c, K_call)
        V_str.append(Vs[(0, 0)])
        V_call.append(Vc[(0, 0)])
        embedded.append(Vs[(0, 0)] - Vc[(0, 0)])

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 6),
                                  gridspec_kw={"width_ratios": [1.4, 1]})

    # Left: P vs Delta
    ax.plot(deltas, V_str, "-", color=BLUE, lw=2.6,
            label=r"Straight bond $P^{\mathrm{str}}(\Delta)$")
    ax.plot(deltas, V_call, "-", color=RED, lw=2.6,
            label=r"Callable bond $P^{\mathrm{call}}(\Delta)$")
    ax.fill_between(deltas, V_call, V_str,
                    color=GOLD, alpha=0.35,
                    label=r"Embedded call $C^{\mathrm{call}}(\Delta)$")
    ax.axhline(K_call, color=PURPLE, lw=1.2, linestyle="--",
               label=fr"Call price $K_{{\mathrm{{call}}}} = {K_call}$")
    ax.axvline(0.0, color=GREY, lw=0.8, alpha=0.7)
    # Mark sample points from worked examples
    sample_deltas = [-0.20, -0.10, 0.0, 0.10, 0.20]
    for d in sample_deltas:
        rt = _toyA_rates_shifted(d)
        Vs = _straight_coupon_bond(rt, c)[(0, 0)]
        Vc, _ = _callable_coupon_bond(rt, c, K_call)
        Vc = Vc[(0, 0)]
        ax.plot([d], [Vs], "o", color=BLUE, ms=8, mec=NAVY)
        ax.plot([d], [Vc], "o", color=RED, ms=8, mec=NAVY)
    ax.set_xlabel(r"parallel short-rate shift $\Delta$")
    ax.set_ylabel("bond price at $n = 0$")
    ax.set_title(
        "Toy-A 3-period 25%-coupon bond:\n"
        "positively-convex straight vs negatively-convex callable"
    )
    ax.legend(loc="upper right", framealpha=0.95)

    # Right: discrete second-difference (convexity) vs Delta
    deltas_h = np.linspace(-0.18, 0.18, 73)
    h = 0.04
    conv_str, conv_call = [], []
    for d in deltas_h:
        Vs_m = _straight_coupon_bond(_toyA_rates_shifted(d - h), c)[(0, 0)]
        Vs_0 = _straight_coupon_bond(_toyA_rates_shifted(d), c)[(0, 0)]
        Vs_p = _straight_coupon_bond(_toyA_rates_shifted(d + h), c)[(0, 0)]
        Vc_m = _callable_coupon_bond(
            _toyA_rates_shifted(d - h), c, K_call)[0][(0, 0)]
        Vc_0 = _callable_coupon_bond(
            _toyA_rates_shifted(d), c, K_call)[0][(0, 0)]
        Vc_p = _callable_coupon_bond(
            _toyA_rates_shifted(d + h), c, K_call)[0][(0, 0)]
        conv_str.append((Vs_m - 2 * Vs_0 + Vs_p) / (h * h))
        conv_call.append((Vc_m - 2 * Vc_0 + Vc_p) / (h * h))
    ax2.plot(deltas_h, conv_str, "-", color=BLUE, lw=2.4,
             label="Straight (always > 0)")
    ax2.plot(deltas_h, conv_call, "-", color=RED, lw=2.4,
             label="Callable (dips negative)")
    ax2.axhline(0.0, color="black", lw=0.8)
    ax2.fill_between(deltas_h, conv_call, 0,
                     where=(np.array(conv_call) < 0),
                     color=RED, alpha=0.25,
                     label="negative-convexity zone")
    ax2.axvline(0.0, color=GREY, lw=0.8, alpha=0.7)
    ax2.set_xlabel(r"$\Delta$")
    ax2.set_ylabel(r"discrete convexity $[V(\Delta-h)-2V(\Delta)+V(\Delta+h)]/h^{2}$")
    ax2.set_title(
        "Discrete second difference, $h = 0.04$\n"
        "(callable's curvature flips sign near the kink)"
    )
    ax2.legend(loc="upper right", framealpha=0.95)

    fig.tight_layout()
    _save("ch06-pos-vs-neg-convexity.png")


def fig_callable_tree():
    """Toy-A short-rate tree with straight and callable bond values at every
    node, called nodes highlighted."""
    c = 0.25
    K_call = 1.0
    rt = rate_tree(**TOY_A, N=3)
    V_str = _straight_coupon_bond(rt, c)
    V_call, called = _callable_coupon_bond(rt, c, K_call)

    # Wider y-spacing so two-line value cards never collide with next node.
    Y_SCALE = 1.0  # vertical scale; y_node = (k - n/2) * Y_SCALE
    fig, ax = plt.subplots(figsize=(14, 9.5))
    N = 3
    # Colour nodes by short rate (cool = low, warm = high)
    rt_vals = [rt[(n, k)] for n in range(N + 1) for k in range(n + 1)]
    norm = Normalize(min(rt_vals), max(rt_vals))
    cmap = cm.get_cmap("plasma")

    for n in range(N + 1):
        for k in range(n + 1):
            x = n
            y = (k - n / 2) * Y_SCALE
            r = rt[(n, k)]
            vs = V_str[(n, k)]
            vc = V_call[(n, k)]
            is_called = called.get((n, k), False)
            edge = RED if is_called else NAVY
            lw = 3.0 if is_called else 0.8
            # Compact disc holds only the short rate.
            ax.scatter([x], [y], s=1500, color=cmap(norm(r)),
                       edgecolor=edge, linewidth=lw,
                       alpha=0.95, zorder=3)
            ax.text(x, y, f"r={r:.4g}",
                    ha="center", va="center", fontsize=8.5,
                    color="white" if norm(r) > 0.5 else NAVY,
                    fontweight="bold", zorder=4)
            # V_str ABOVE the node, V_call BELOW — never collide with siblings.
            ax.text(x, y + 0.22, fr"$V^{{\mathrm{{str}}}}={vs:.4f}$",
                    ha="center", va="bottom", fontsize=8.5,
                    color=BLUE, fontweight="bold", zorder=4)
            label = (
                fr"$V^{{\mathrm{{call}}}}={vc:.4f}$"
                + (r"  $\bigstar$" if is_called else "")
            )
            ax.text(x, y - 0.22, label,
                    ha="center", va="top", fontsize=8.5,
                    color=RED if is_called else GREY,
                    fontweight="bold" if is_called else "normal",
                    zorder=4)

    # Connect with grey lines
    for n in range(N):
        for k in range(n + 1):
            xa, ya = n, (k - n / 2) * Y_SCALE
            for dk in (0, 1):
                ax.plot([xa, n + 1],
                        [ya, ((k + dk) - (n + 1) / 2) * Y_SCALE],
                        color=GREY, lw=0.8, alpha=0.5, zorder=1)
    ax.set_xlim(-0.8, N + 0.9)
    ax.set_ylim(-N / 2 * Y_SCALE - 0.7, N / 2 * Y_SCALE + 0.7)
    ax.set_yticks([])
    ax.set_xlabel("step $n$")
    ax.set_title(
        "Toy-A short-rate tree with straight and callable bond values\n"
        r"(coupon $c = 0.25$, call price $K_{\mathrm{call}} = 1$; "
        r"red-outline + $\bigstar$ = issuer optimally calls)"
    )
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label=r"$r_n$", shrink=0.7)
    ax.grid(False)
    fig.tight_layout()
    _save("ch06-callable-tree.png")


# ---------------------------------------------------------------------------
# Section 6.12 — Ho-Lee calibration figures
# ---------------------------------------------------------------------------

def hl_bond_price(r0, thetas, sigma, T):
    """Ho-Lee discretisation: r_{n+1} = r_n + theta_n +/- sigma.

    Returns (B(0, T), rate_tree dict)."""
    rt = {(0, 0): r0}
    for n in range(T):
        theta = thetas[n] if n < len(thetas) else 0.0
        for k in range(n + 1):
            rt[(n + 1, k + 1)] = rt[(n, k)] + theta + sigma
            rt[(n + 1, k)] = rt[(n, k)] + theta - sigma
    B = {(T, k): 1.0 for k in range(T + 1)}
    for n in range(T - 1, -1, -1):
        for k in range(n + 1):
            B[(n, k)] = (
                (0.5 * B[(n + 1, k + 1)]
                 + 0.5 * B[(n + 1, k)])
                / (1.0 + rt[(n, k)])
            )
    return B[(0, 0)], rt


def calibrate_hl(B_mkt: dict, sigma: float = 0.01):
    """Bootstrap thetas to match quoted market bond prices B_mkt[T]."""
    Ts = sorted(B_mkt.keys())
    r0 = 1.0 / B_mkt[1] - 1.0
    thetas = []
    for T in Ts:
        if T == 1:
            continue
        target = B_mkt[T]
        lo, hi = -0.5, 0.5
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            trial = thetas + [mid]
            b, _rt = hl_bond_price(r0, trial, sigma, T)
            if b > target:
                lo = mid
            else:
                hi = mid
        thetas.append(0.5 * (lo + hi))
    return r0, thetas


def fig_yield_overlay():
    B_mkt = {1: 0.95, 2: 0.89, 3: 0.82, 4: 0.75}
    sigma = 0.005
    r0, thetas = calibrate_hl(B_mkt, sigma=sigma)
    Ts = sorted(B_mkt.keys())
    y_mkt = [-math.log(B_mkt[T]) / T for T in Ts]
    y_model = []
    for T in Ts:
        b, _rt = hl_bond_price(r0, thetas[:max(T - 1, 0)], sigma, T)
        y_model.append(-math.log(b) / T)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(Ts, y_mkt, "o", color=RED, ms=12,
            label="market yield")
    ax.plot(Ts, y_model, "-", color=BLUE, lw=2.5,
            label="calibrated Ho-Lee model yield")
    # Place err labels just below the markers (boxed) — avoids clipping.
    for T, ym, yo in zip(Ts, y_mkt, y_model):
        ax.annotate(
            f"err={ym - yo:+.0e}",
            xy=(T, ym), xytext=(T, ym - 0.0045),
            fontsize=8, ha="center", va="top",
            bbox=dict(boxstyle="round,pad=0.18",
                      fc="white", ec=GREY, alpha=0.85),
        )
    ax.set_xlabel(r"maturity $T$")
    ax.set_ylabel(r"yield $y(0, T)$")
    ax.set_title(
        "After bootstrap calibration, "
        "model and market yield curves agree at every node"
    )
    # Headroom + bottom-room so boxed labels and legend never clip.
    lo, hi = min(y_mkt + y_model), max(y_mkt + y_model)
    span = hi - lo
    ax.set_ylim(lo - 0.20 * span, hi + 0.15 * span)
    ax.legend(loc="upper left")
    fig.tight_layout()
    _save("ch06-yield-overlay.png")


def fig_calibrated_tree():
    B_mkt = {1: 0.95, 2: 0.89, 3: 0.82, 4: 0.75}
    sigma = 0.01
    r0, thetas = calibrate_hl(B_mkt, sigma=sigma)
    N = 4
    rt = {(0, 0): r0}
    for n in range(N):
        if n < len(thetas):
            theta = thetas[n]
        elif thetas:
            theta = thetas[-1]
        else:
            theta = 0.0
        for k in range(n + 1):
            rt[(n + 1, k + 1)] = rt[(n, k)] + theta + sigma
            rt[(n + 1, k)] = rt[(n, k)] + theta - sigma

    fig, ax = plt.subplots(figsize=(11, 6.5))
    vals = np.array(list(rt.values()))
    norm = Normalize(vals.min(), vals.max())
    cmap = cm.get_cmap("plasma")
    for (n, k), r in rt.items():
        x = n
        y = k - n / 2
        ax.scatter([x], [y], s=1800, color=cmap(norm(r)),
                   edgecolor=NAVY, alpha=0.95, zorder=3)
        ax.text(x, y, f"{r:.4f}", ha="center", va="center",
                color="white" if norm(r) > 0.5 else "black",
                fontsize=8, fontweight="bold", zorder=4)
    for n in range(N):
        for k in range(n + 1):
            xa, ya = n, k - n / 2
            for dk in (0, 1):
                ax.plot([xa, n + 1], [ya, (k + dk) - (n + 1) / 2],
                        color=GREY, lw=0.8, alpha=0.55, zorder=1)
    ax.set_xlim(-0.5, N + 0.5)
    ax.set_ylim(-N / 2 - 0.7, N / 2 + 0.7)
    ax.set_yticks([])
    ax.set_xlabel("step $n$")
    theta_str = ", ".join(f"{t:+.4f}" for t in thetas)
    ax.set_title(
        r"Calibrated Ho-Lee short-rate tree, $\sigma = "
        + f"{sigma}$\n"
        + r"Drifts: $\theta = ("
        + theta_str
        + r")$"
    )
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label=r"$r_n$", shrink=0.7)
    ax.grid(False)
    fig.tight_layout()
    _save("ch06-calibrated-tree.png")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Building Chapter 6 figures ...")
    fig_rate_lattice_A()
    fig_stock_vs_rate_tree()
    fig_M3_bar_3d()
    fig_bond_tree_A()
    fig_bond_surface_3d()
    fig_D3_hist()
    fig_yield_bars()
    fig_yield_shapes()
    fig_D3_bar_3d()
    fig_forward_vs_expected()
    fig_pie_P_vs_PT()
    fig_Z3_bar_3d()
    fig_caplet_payoff()
    fig_caplet_tree()
    fig_cap_surface_3d()
    fig_cap_floor_vs_K()
    fig_bond_call_tree()
    fig_swap_pv_bars()
    fig_pos_vs_neg_convexity()
    fig_callable_tree()
    fig_yield_overlay()
    fig_calibrated_tree()
    print("Done.")
