"""
Chapter 3 figure builder for Binomial Option Pricing.

Run: python docs/binomial-option-pricing/_build_ch3_figs.py

Outputs under figures/:
    ch03-omega-tree.png
    ch03-pathbundle-3d.png
    ch03-event-venn.png
    ch03-leaf-masses.png
    ch03-nested-rectangles.png
    ch03-Fk-blocks.png
    ch03-telescope-partitions-3d.png
    ch03-Fk-colour-tree.png
    ch03-Sk-heatmap.png
    ch03-adapted-vs-not.png
    ch03-block-average-tree.png
    ch03-block-avg-3d.png
    ch03-tower-cartoon.png
    ch03-martingale-paths.png
    ch03-Mtilde-3d.png
    ch03-Mtilde-P-3d.png
    ch03-stopping-tree.png
    ch03-stopped-3d.png
    ch03-ost-bars.png
    ch03-change-of-measure-bars.png
    ch03-Z-3d-bar.png
    ch03-Zk-heatmap.png
    ch03-Zk-mesh.png

Style: bright colourful palette. Coin-toss space made visible.
Toy parameters: S0=4, u=2, d=1/2, r=1/4, p_tilde=1/2.
Realistic: S0=100, u=1.10, d=0.90, r=2%, p_tilde=0.6.
"""
from __future__ import annotations

import itertools
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG_DIR, exist_ok=True)
DPI = 200

# Bright, distinguishable palette (consistent with Chapter 0)
NAVY = "#0b1d3a"
BLUE = "#1f77b4"
ORANGE = "#ff7f0e"
GREEN = "#2ca02c"
RED = "#d62728"
PURPLE = "#9467bd"
GOLD = "#fbbf24"
TEAL = "#17becf"
GREY = "#888888"

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


# Toy model
TOY_S0 = 4.0
TOY_U = 2.0
TOY_D = 0.5
TOY_R = 0.25
TOY_PT = 0.5

# Realistic
REAL_S0 = 100.0
REAL_U = 1.10
REAL_D = 0.90
REAL_R = 0.02
REAL_PT = 0.6


def _save(name: str) -> None:
    path = os.path.join(FIG_DIR, name)
    plt.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close()
    print(f"  wrote {name}")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def omegas(n):
    """Return list of length-n words over {H,T} in lexicographic order (H<T)."""
    return ["".join(w) for w in itertools.product("HT", repeat=n)]


def price_path(word, S0=TOY_S0, u=TOY_U, d=TOY_D):
    """Return list S_0,...,S_n along a coin-toss word."""
    S = [S0]
    for c in word:
        S.append(S[-1] * (u if c == "H" else d))
    return S


def heads(word):
    return word.count("H")


def fk_block_id(word, k):
    """Block of F_k containing word: prefix of length k (k=0 -> empty)."""
    return word[:k]


# ─────────────────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────────────────

def fig_omega_tree():
    """Non-recombining tree on Omega_3 with H green, T red, leaves labelled."""
    n = 3
    words = omegas(n)
    fig, ax = plt.subplots(figsize=(11, 7))

    # Build node positions. Non-recombining: each prefix is a node.
    # x = depth k; y based on path index in DFS order.
    leaf_ys = np.linspace(0, 1, len(words))
    leaf_pos = dict(zip(words, leaf_ys))

    def prefix_y(prefix):
        # average y of all leaves with that prefix
        ys = [leaf_pos[w] for w in words if w.startswith(prefix)]
        return float(np.mean(ys))

    prefixes = [""]
    for k in range(1, n + 1):
        for w in words:
            prefixes.append(w[:k])
    prefixes = sorted(set(prefixes), key=lambda s: (len(s), s))

    # Draw edges
    for p in prefixes:
        if len(p) == n:
            continue
        x0 = len(p)
        y0 = prefix_y(p)
        for c, col in (("H", GREEN), ("T", RED)):
            child = p + c
            x1 = len(child)
            y1 = prefix_y(child)
            ax.plot([x0, x1], [y0, y1], color=col, lw=2.2, alpha=0.85)
            # label edge
            ax.text((x0 + x1) / 2, (y0 + y1) / 2 + 0.012, c,
                    color=col, fontsize=9, ha="center", fontweight="bold")

    # Draw nodes
    for p in prefixes:
        x = len(p)
        y = prefix_y(p)
        ax.scatter([x], [y], s=160, color=NAVY, zorder=5)

    # Leaf labels with omega and S_3
    for w in words:
        x = n
        y = leaf_pos[w]
        S3 = price_path(w)[-1]
        ax.text(x + 0.08, y, f"{w}  $S_3={S3:g}$",
                va="center", ha="left", fontsize=10, color=NAVY)

    ax.set_xlim(-0.3, n + 1.6)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xticks(range(n + 1))
    ax.set_xticklabels([f"$k={k}$" for k in range(n + 1)])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_title(r"Coin-toss space $\Omega_3$: non-recombining tree (Toy: $S_0=4, u=2, d=1/2$)")
    _save("ch03-omega-tree.png")


def fig_pathbundle_3d():
    """All 16 paths of Omega_4 as 3-D ribbons: x=k, y=path index, z=S_k."""
    n = 4
    words = omegas(n)
    paths = [price_path(w, S0=REAL_S0, u=REAL_U, d=REAL_D) for w in words]
    paths = np.array(paths)  # (16, n+1)

    fig = plt.figure(figsize=(14, 9))
    ax = fig.add_subplot(111, projection="3d")

    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(words)))

    for j, w in enumerate(words):
        xs = np.arange(n + 1)
        ys = np.full(n + 1, j)
        zs = paths[j]
        ax.plot(xs, ys, zs, color=colors[j], lw=1.6, alpha=0.9)
        ax.scatter(xs, ys, zs, color=colors[j], s=14, depthshade=True)

    # mean line
    mean_curve = paths.mean(axis=0)
    ax.plot(np.arange(n + 1), np.full(n + 1, len(words) / 2), mean_curve,
            color=GOLD, lw=3.2, label=r"path-mean $\bar S_k$")
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.92))

    ax.set_xlabel(r"time $k$", labelpad=10)
    ax.set_ylabel("path index", labelpad=10)
    ax.set_zlabel(r"$S_k$", labelpad=10)
    ax.set_title(r"Path bundle on $\Omega_4$ (Realistic: $u=1.10, d=0.90$)", pad=18)
    _save("ch03-pathbundle-3d.png")


def fig_event_venn():
    """Venn-style: 8 leaves with three coloured event blobs."""
    n = 3
    words = omegas(n)
    fig, ax = plt.subplots(figsize=(10, 6.5))

    # Place leaves on a 2x4 grid
    grid = {w: (i % 4, 1 - i // 4) for i, w in enumerate(words)}

    A = {w for w in words if w[0] == "H"}
    B = {w for w in words if heads(w) >= 2}
    C = {w for w in words if price_path(w)[-1] == 4}  # possibly empty for Toy

    def blob(members, color, label, dx, dy, label_dy=0.12, alpha=0.22):
        pts = np.array([grid[w] for w in members])
        if len(pts) == 0:
            ax.text(2.0, -1.3, f"{label} is empty",
                    color=color, fontsize=10, ha="center")
            return
        cx = pts[:, 0].mean() + dx
        cy = pts[:, 1].mean() + dy
        rx = 1.9
        ry = 0.85
        from matplotlib.patches import Ellipse
        e = Ellipse((cx, cy), 2 * rx, 2 * ry, color=color,
                    alpha=alpha, lw=2.2, ec=color, fill=True)
        ax.add_patch(e)
        ax.text(cx, cy + ry + label_dy, label, color=color,
                fontsize=11, ha="center", fontweight="bold")

    blob(A, BLUE, r"$A=\{\omega_1=H\}$", dx=0.0, dy=0.0, label_dy=0.55)
    blob(B, ORANGE, r"$B=\{H_3\geq 2\}$", dx=0.1, dy=-0.05, label_dy=0.18)
    blob(C, GREEN, r"$C=\{S_3=4\}$", dx=-0.1, dy=0.05)

    for w, (x, y) in grid.items():
        ax.scatter([x], [y], s=240, color=NAVY, zorder=5)
        ax.text(x, y - 0.22, w, ha="center", va="top",
                fontsize=10, color=NAVY)

    ax.set_xlim(-1.8, 4.8)
    ax.set_ylim(-1.8, 2.6)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_title(r"Events on $\Omega_3$ (Toy: $S_3=4$ unattainable, $C=\emptyset$)",
                 pad=14)
    _save("ch03-event-venn.png")


def fig_leaf_masses():
    """Omega_2 leaf masses: P (p=0.6) vs Ptilde (p_tilde=0.5)."""
    n = 2
    words = omegas(n)
    p = 0.6
    pt = TOY_PT

    Pmass = np.array([p ** heads(w) * (1 - p) ** (n - heads(w)) for w in words])
    PTmass = np.array([pt ** heads(w) * (1 - pt) ** (n - heads(w)) for w in words])

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(words))
    w = 0.38
    ax.bar(x - w / 2, Pmass, width=w, color=BLUE, label=r"$\mathbb{P}$ ($p=0.6$)")
    ax.bar(x + w / 2, PTmass, width=w, color=ORANGE,
           label=r"$\tilde{\mathbb{P}}$ ($\tilde p=0.5$)")

    for i, (a, b) in enumerate(zip(Pmass, PTmass)):
        ax.text(i - w / 2, a + 0.005, f"{a:.2f}", ha="center", fontsize=9, color=BLUE)
        ax.text(i + w / 2, b + 0.005, f"{b:.2f}", ha="center", fontsize=9, color=ORANGE)

    ax.set_xticks(x)
    ax.set_xticklabels(words)
    ax.set_xlabel(r"$\omega \in \Omega_2$")
    ax.set_ylabel("leaf mass")
    ax.set_title(r"Leaf masses on $\Omega_2$: real-world vs risk-neutral")
    ax.legend()
    _save("ch03-leaf-masses.png")


def fig_nested_rectangles():
    """Nested rectangles for F_0, F_1, F_2, F_3 on Omega_3."""
    n = 3
    words = omegas(n)
    fig, ax = plt.subplots(figsize=(12, 6.5))

    total_w = 8.0
    leaf_w = total_w / len(words)
    levels = [
        (0, 1.0, NAVY, r"$\mathcal{F}_0$"),
        (1, 1.0, BLUE, r"$\mathcal{F}_1$"),
        (2, 1.0, ORANGE, r"$\mathcal{F}_2$"),
        (3, 1.0, GREEN, r"$\mathcal{F}_3$"),
    ]
    base_y = 0
    row_h = 0.9
    pad = 0.18

    def blocks_at(k):
        if k == 0:
            return [""]
        return sorted({w[:k] for w in words})

    for k, _, col, lab in levels:
        y0 = base_y - k * (row_h + pad)
        blocks = blocks_at(k)
        for b in blocks:
            members = [w for w in words if w.startswith(b)]
            i0 = words.index(members[0])
            x = i0 * leaf_w
            width = len(members) * leaf_w
            rect = Rectangle((x, y0), width, row_h,
                             facecolor=col, alpha=0.32, edgecolor=col, lw=2.0)
            ax.add_patch(rect)
            ax.text(x + width / 2, y0 + row_h / 2,
                    b if b else r"$\Omega$",
                    ha="center", va="center", fontsize=11,
                    color=NAVY, fontweight="bold")
        ax.text(-0.5, y0 + row_h / 2, lab, ha="right", va="center",
                fontsize=12, color=col, fontweight="bold")

    # Leaves at bottom
    yL = base_y - (n + 1) * (row_h + pad)
    for i, w in enumerate(words):
        ax.scatter([i * leaf_w + leaf_w / 2], [yL + row_h / 2],
                   s=160, color=NAVY, zorder=5)
        ax.text(i * leaf_w + leaf_w / 2, yL + row_h / 2 - 0.25,
                w, ha="center", fontsize=9, color=NAVY)

    ax.set_xlim(-1.0, total_w + 0.5)
    ax.set_ylim(yL - 0.6, base_y + row_h + 0.4)
    ax.set_aspect("auto")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_title(r"Nested rectangles: $\mathcal{F}_0 \subset \mathcal{F}_1 \subset \mathcal{F}_2 \subset \mathcal{F}_3$ on $\Omega_3$")
    _save("ch03-nested-rectangles.png")


def fig_Fk_blocks():
    """Paired bar chart on Omega_4: blocks count and block size."""
    n = 4
    ks = np.arange(n + 1)
    n_blocks = 2 ** ks
    block_size = 2 ** (n - ks)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    w = 0.38
    ax.bar(ks - w / 2, n_blocks, width=w, color=BLUE,
           label=r"# blocks of $\mathcal{F}_k = 2^k$")
    ax.bar(ks + w / 2, block_size, width=w, color=ORANGE,
           label=r"size of each block $= 2^{n-k}$")

    for k, (a, b) in enumerate(zip(n_blocks, block_size)):
        ax.text(k - w / 2, a + 0.3, str(a), ha="center", fontsize=9, color=BLUE)
        ax.text(k + w / 2, b + 0.3, str(b), ha="center", fontsize=9, color=ORANGE)

    ax.set_xticks(ks)
    ax.set_xticklabels([f"$k={k}$" for k in ks])
    ax.set_ylabel("count")
    ax.set_ylim(0, max(n_blocks.max(), block_size.max()) * 1.25)
    ax.set_title(r"Filtration on $\Omega_4$: blocks double, sizes halve (meet at $k=2$)")
    ax.legend(loc="upper right", framealpha=0.95)
    _save("ch03-Fk-blocks.png")


def fig_telescope_partitions_3d():
    """3-D stack of partition discs, each split into 2^k wedges."""
    n = 3
    fig = plt.figure(figsize=(13, 10))
    ax = fig.add_subplot(111, projection="3d")

    colors = [BLUE, ORANGE, GREEN, PURPLE]

    for k in range(n + 1):
        nW = 2 ** k
        theta = np.linspace(0, 2 * np.pi, 60)
        z = k * 1.0
        for j in range(nW):
            a0 = 2 * np.pi * j / nW
            a1 = 2 * np.pi * (j + 1) / nW
            ang = np.linspace(a0, a1, 24)
            r = 1.0
            xs = np.concatenate(([0], r * np.cos(ang), [0]))
            ys = np.concatenate(([0], r * np.sin(ang), [0]))
            zs = np.full_like(xs, z)
            verts = [list(zip(xs, ys, zs))]
            col = colors[k % len(colors)]
            # alternating shade
            shade = 0.55 + 0.4 * ((j % 2))
            poly = Poly3DCollection(verts, alpha=0.78,
                                    facecolor=col, edgecolor=NAVY, lw=0.6)
            poly.set_facecolor(plt.matplotlib.colors.to_rgba(col, alpha=shade * 0.55 + 0.2))
            ax.add_collection3d(poly)
        ax.text(1.15, 0, z, fr"$\mathcal{{F}}_{{{k}}}$: $2^{k}$ blocks",
                color=NAVY, fontsize=10)

    ax.set_xlim(-1.4, 2.0)
    ax.set_ylim(-1.4, 1.4)
    ax.set_zlim(-0.3, n + 0.5)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_zlabel(r"refinement level $k$", labelpad=12)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(r"Telescope of partitions $\mathcal{F}_0 \subset \cdots \subset \mathcal{F}_3$",
                 pad=18)
    _save("ch03-telescope-partitions-3d.png")


def fig_Fk_colour_tree():
    """4 panels: each leaf coloured by which F_k-block it sits in."""
    n = 3
    words = omegas(n)
    fig, axes = plt.subplots(1, n + 1, figsize=(14, 5.5))
    cmap_pool = [BLUE, ORANGE, GREEN, RED, PURPLE, GOLD, TEAL, GREY]

    for k, ax in enumerate(axes):
        blocks = sorted({w[:k] for w in words})
        block_color = {b: cmap_pool[i % len(cmap_pool)]
                       for i, b in enumerate(blocks)}
        for i, w in enumerate(words):
            y = len(words) - 1 - i
            b = w[:k]
            col = block_color[b]
            ax.add_patch(Rectangle((0, y - 0.4), 1.0, 0.8,
                                   facecolor=col, alpha=0.75, edgecolor=NAVY))
            ax.text(1.1, y, w, fontsize=10, va="center", color=NAVY)
            ax.text(0.5, y, b if b else r"$\Omega$",
                    ha="center", va="center", fontsize=9,
                    color="white", fontweight="bold")
        ax.set_xlim(-0.1, 2.2)
        ax.set_ylim(-0.7, len(words) - 0.3)
        ax.set_title(fr"$\mathcal{{F}}_{{{k}}}$ ({2**k} blocks)")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)

    fig.suptitle(r"Each $\omega \in \Omega_3$ coloured by its $\mathcal{F}_k$-block",
                 fontsize=12, color=NAVY)
    plt.tight_layout()
    _save("ch03-Fk-colour-tree.png")


def fig_Sk_heatmap():
    """Heatmap: rows omega, cols k, cells coloured by S_k(omega)."""
    n = 3
    words = omegas(n)
    M = np.zeros((len(words), n + 1))
    for i, w in enumerate(words):
        M[i, :] = price_path(w)

    fig, ax = plt.subplots(figsize=(11, 7.5))
    im = ax.imshow(M, aspect="auto", cmap="viridis", origin="upper")
    # luminance threshold: choose black text on light-yellow viridis cells
    vmin, vmax = M.min(), M.max()
    for i in range(len(words)):
        for k in range(n + 1):
            frac = (M[i, k] - vmin) / (vmax - vmin) if vmax > vmin else 0.0
            txt_col = "black" if frac > 0.7 else "white"
            ax.text(k, i, f"{M[i, k]:g}", ha="center", va="center",
                    fontsize=12, color=txt_col, fontweight="bold")

    ax.set_xticks(range(n + 1))
    ax.set_xticklabels([f"$k={k}$" for k in range(n + 1)], fontsize=11)
    ax.set_yticks(range(len(words)))
    ax.set_yticklabels(words, fontsize=11)
    ax.set_xlabel("time $k$", fontsize=12)
    ax.set_ylabel(r"$\omega \in \Omega_3$", fontsize=12)
    ax.set_title(r"$S_k(\omega)$ heatmap — leftward columns are block-constant",
                 fontsize=13, pad=12)
    cb = plt.colorbar(im, ax=ax, label=r"$S_k$", shrink=0.7, pad=0.04)
    cb.set_label(r"$S_k$", fontsize=11)
    ax.grid(False)
    _save("ch03-Sk-heatmap.png")


def fig_adapted_vs_not():
    """Two trees: S_2 (adapted, F_2-constant) vs Y_k=S_{k+1} (not adapted)."""
    n = 3
    words = omegas(n)
    fig, axes = plt.subplots(1, 2, figsize=(16, 9))

    def draw_tree(ax, value_fn, title):
        leaf_ys = np.linspace(0, 1, len(words))
        leaf_pos = dict(zip(words, leaf_ys))
        vals = np.array([value_fn(w) for w in words])
        vmin, vmax = vals.min(), vals.max()
        norm = plt.matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)
        cmap = plt.cm.plasma

        # edges
        prefixes = set()
        for w in words:
            for k in range(n + 1):
                prefixes.add(w[:k])
        for p in sorted(prefixes, key=lambda s: (len(s), s)):
            if len(p) == n:
                continue
            x0 = len(p)
            y0 = np.mean([leaf_pos[w] for w in words if w.startswith(p)])
            for c, col in (("H", GREEN), ("T", RED)):
                child = p + c
                x1 = len(child)
                y1 = np.mean([leaf_pos[w] for w in words if w.startswith(child)])
                ax.plot([x0, x1], [y0, y1], color=col, lw=1.5, alpha=0.55)

        for w in words:
            v = value_fn(w)
            ax.scatter([n], [leaf_pos[w]], s=320,
                       color=cmap(norm(v)), edgecolor=NAVY, lw=1.0, zorder=5)
            ax.text(n + 0.08, leaf_pos[w], f"{w}: {v:g}",
                    va="center", fontsize=9, color=NAVY)

        ax.set_xlim(-0.3, n + 1.4)
        ax.set_ylim(-0.05, 1.05)
        ax.set_xticks(range(n + 1))
        ax.set_xticklabels([f"$k={k}$" for k in range(n + 1)])
        ax.set_yticks([])
        ax.grid(False)
        ax.set_title(title)

    def S2(w):
        return price_path(w)[2]

    def Y2(w):
        return price_path(w)[3]  # S_{k+1} at k=2 -> S_3

    draw_tree(axes[0], S2,
              r"$S_2$: $\mathcal{F}_2$-measurable (siblings agree)")
    draw_tree(axes[1], Y2,
              r"$Y_2=S_3$: NOT $\mathcal{F}_2$-measurable (siblings differ)")
    plt.tight_layout()
    _save("ch03-adapted-vs-not.png")


def fig_block_average_tree():
    """Each F_2-block replaced by its p_tilde-average of S_3."""
    n = 3
    words = omegas(n)
    pt = TOY_PT
    S3 = {w: price_path(w)[-1] for w in words}

    blocks = sorted({w[:2] for w in words})
    block_avg = {}
    for b in blocks:
        ws = [w for w in words if w.startswith(b)]
        # H is index 0 in (H,T)
        wH = b + "H"
        wT = b + "T"
        block_avg[b] = pt * S3[wH] + (1 - pt) * S3[wT]

    fig, ax = plt.subplots(figsize=(11, 6.5))
    leaf_ys = np.linspace(0, 1, len(words))
    leaf_pos = dict(zip(words, leaf_ys))

    # Edges from F_2 block to its two children (leaves)
    for b in blocks:
        ws = [w for w in words if w.startswith(b)]
        yB = np.mean([leaf_pos[w] for w in ws])
        xB = 2.0
        ax.scatter([xB], [yB], s=420, color=GOLD, edgecolor=NAVY,
                   lw=1.2, zorder=5)
        ax.text(xB - 0.1, yB, f"{block_avg[b]:.2f}", fontsize=10,
                ha="right", va="center", color=NAVY, fontweight="bold")
        # also annotate the block label
        ax.text(xB, yB + 0.05, b, ha="center", va="bottom",
                fontsize=9, color=PURPLE)
        for w in ws:
            ax.plot([xB, n], [yB, leaf_pos[w]],
                    color=GREEN if w[-1] == "H" else RED, lw=1.6, alpha=0.8)
            ax.scatter([n], [leaf_pos[w]], s=180, color=NAVY, zorder=5)
            ax.text(n + 0.08, leaf_pos[w], f"{w}: $S_3={S3[w]:g}$",
                    va="center", fontsize=9, color=NAVY)

    # root and F_1 nodes (optional)
    ax.set_xlim(1.4, n + 1.6)
    ax.set_ylim(-0.05, 1.1)
    ax.set_xticks([2, 3])
    ax.set_xticklabels([r"$\mathcal{F}_2$ block average", r"$k=3$ leaves"])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_title(r"$\tilde{\mathbb{E}}[S_3\,|\,\mathcal{F}_2]$ per block " +
                 r"$=\,1.25\cdot S_2$ (Toy)")
    _save("ch03-block-average-tree.png")


def fig_block_avg_3d():
    """3-D bars: x=block, two bars per block at z=S_3 plus block-average line."""
    n = 3
    words = omegas(n)
    pt = TOY_PT
    S3 = {w: price_path(w)[-1] for w in words}
    blocks = sorted({w[:2] for w in words})
    block_avg = {b: pt * S3[b + "H"] + (1 - pt) * S3[b + "T"] for b in blocks}

    fig = plt.figure(figsize=(14, 9))
    ax = fig.add_subplot(111, projection="3d")

    width = 0.35
    depth = 0.6

    for i, b in enumerate(blocks):
        for j, c in enumerate(("H", "T")):
            w = b + c
            x = i + (j - 0.5) * 0.5
            y = 0
            dx = width
            dy = depth
            dz = S3[w]
            col = GREEN if c == "H" else RED
            # Build a Poly3DCollection rectangular prism (since rule forbids bars,
            # we use filled rectangle "fins" for each leaf S_3).
            verts = [
                [(x, y, 0), (x + dx, y, 0), (x + dx, y, dz), (x, y, dz)],
                [(x, y + dy, 0), (x + dx, y + dy, 0),
                 (x + dx, y + dy, dz), (x, y + dy, dz)],
                [(x, y, 0), (x, y + dy, 0), (x, y + dy, dz), (x, y, dz)],
                [(x + dx, y, 0), (x + dx, y + dy, 0),
                 (x + dx, y + dy, dz), (x + dx, y, dz)],
                [(x, y, dz), (x + dx, y, dz),
                 (x + dx, y + dy, dz), (x, y + dy, dz)],
            ]
            poly = Poly3DCollection(verts, facecolor=col, alpha=0.75,
                                    edgecolor=NAVY, lw=0.6)
            ax.add_collection3d(poly)
            ax.text(x + dx / 2, y + dy / 2, dz + 0.6,
                    f"{w}\n$S_3={S3[w]:g}$",
                    ha="center", fontsize=8, color=NAVY)

        # block-average horizontal "plate"
        avg = block_avg[b]
        xa = i - 0.5
        xb = i + 0.5
        ya = 0
        yb = depth
        plate = [[(xa, ya, avg), (xb, ya, avg), (xb, yb, avg), (xa, yb, avg)]]
        ax.add_collection3d(Poly3DCollection(plate, facecolor=GOLD,
                                             alpha=0.6, edgecolor=NAVY, lw=1.2))
        ax.text(i, yb + 0.05, avg + 1.0, f"avg = {avg:.2f}",
                ha="center", fontsize=9, color=NAVY, fontweight="bold")

    ax.set_xticks(range(len(blocks)))
    ax.set_xticklabels(blocks)
    ax.set_yticks([])
    ax.set_zlabel(r"$S_3$ value", labelpad=12)
    ax.set_title(r"Per-$\mathcal{F}_2$-block $S_3$ values vs block average (gold)",
                 pad=18)
    _save("ch03-block-avg-3d.png")


def fig_tower_cartoon():
    """Nested squares: 8 leaves -> 4 (F_2) -> 2 (F_1)."""
    fig, ax = plt.subplots(figsize=(13, 6.5))

    # 8 leaves on bottom right
    x_leaves = np.linspace(7, 13, 8)
    y_leaves = 0.5
    for i, x in enumerate(x_leaves):
        ax.add_patch(Rectangle((x - 0.3, y_leaves - 0.3),
                               0.6, 0.6,
                               facecolor=BLUE, edgecolor=NAVY, lw=1.2, alpha=0.85))
    ax.text(10, 1.85, "8 leaves of $\\Omega_3$", ha="center", color=BLUE, fontsize=11)

    # 4 orange (F_2)
    x_o = np.linspace(3.8, 6.2, 4)
    for x in x_o:
        ax.add_patch(Rectangle((x - 0.5, 0.0),
                               1.0, 1.0,
                               facecolor=ORANGE, edgecolor=NAVY, lw=1.4, alpha=0.85))
    ax.text(5, 1.6, "$\\mathcal{F}_2$: 4 blocks", ha="center", color=ORANGE, fontsize=11)

    # 2 green (F_1)
    x_g = np.linspace(0.7, 2.3, 2)
    for x in x_g:
        ax.add_patch(Rectangle((x - 0.8, -0.2),
                               1.6, 1.4,
                               facecolor=GREEN, edgecolor=NAVY, lw=1.6, alpha=0.85))
    ax.text(1.5, 1.7, "$\\mathcal{F}_1$: 2 blocks", ha="center", color=GREEN, fontsize=11)

    # Arrows
    ax.annotate("", xy=(7, 0.5), xytext=(6.7, 0.5),
                arrowprops=dict(arrowstyle="<-", lw=2, color=NAVY))
    ax.annotate("", xy=(3.3, 0.5), xytext=(2.6, 0.5),
                arrowprops=dict(arrowstyle="<-", lw=2, color=NAVY))
    ax.text(6.8, 0.05, r"average $|\mathcal{F}_2$", color=NAVY, fontsize=10,
            ha="center")
    ax.text(2.95, 0.05, r"average $|\mathcal{F}_1$", color=NAVY, fontsize=10,
            ha="center")

    # Curved arrow skip-straight
    arr = FancyArrowPatch((10, 2.2), (1.5, 2.7),
                          arrowstyle="->", mutation_scale=22,
                          connectionstyle="arc3,rad=-0.35",
                          color=PURPLE, lw=2.2)
    ax.add_patch(arr)
    ax.text(5.5, 3.5, r"tower: average twice $=$ average once",
            ha="center", color=PURPLE, fontsize=11, fontweight="bold")

    ax.set_xlim(-0.5, 14)
    ax.set_ylim(-0.5, 4.0)
    ax.set_aspect("auto")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_title("Tower property as nested averaging")
    _save("ch03-tower-cartoon.png")


def _Mtilde_path(word, S0=TOY_S0, u=TOY_U, d=TOY_D, r=TOY_R):
    """Discounted price path Mtilde_k = S_k / (1+r)^k."""
    S = price_path(word, S0=S0, u=u, d=d)
    return np.array([S[k] / (1 + r) ** k for k in range(len(S))])


def fig_martingale_paths():
    """8 paths of Mtilde on n=3, with constant cross-sectional mean."""
    n = 3
    words = omegas(n)
    pt = TOY_PT
    Ms = np.array([_Mtilde_path(w) for w in words])
    probs = np.array([pt ** heads(w) * (1 - pt) ** (n - heads(w)) for w in words])

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(words)))
    for j, w in enumerate(words):
        ax.plot(range(n + 1), Ms[j], color=colors[j], lw=1.8, alpha=0.85,
                marker="o", markersize=5, label=w)

    # cross-sectional mean under Ptilde
    mean = (probs[:, None] * Ms).sum(axis=0)
    ax.plot(range(n + 1), mean, color=GOLD, lw=3.5,
            label=r"$\tilde{\mathbb{E}}[\widetilde M_k]$")
    ax.axhline(TOY_S0, color=NAVY, lw=1.2, ls="--", alpha=0.6,
               label=r"$\widetilde M_0=4$")
    ax.set_xticks(range(n + 1))
    ax.set_xlabel("$k$")
    ax.set_ylabel(r"$\widetilde M_k$")
    ax.set_title(r"Discounted price $\widetilde M$ under $\tilde{\mathbb{P}}$ — constant mean")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    _save("ch03-martingale-paths.png")


def fig_Mtilde_3d():
    """3-D 'surface' over (k, path) of Mtilde under Ptilde with flat mean plane."""
    n = 3
    words = omegas(n)
    pt = TOY_PT
    Ms = np.array([_Mtilde_path(w) for w in words])
    probs = np.array([pt ** heads(w) * (1 - pt) ** (n - heads(w)) for w in words])

    fig = plt.figure(figsize=(14, 9))
    ax = fig.add_subplot(111, projection="3d")

    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(words)))
    for j in range(len(words)):
        xs = np.arange(n + 1)
        ys = np.full(n + 1, j)
        zs = Ms[j]
        ax.plot(xs, ys, zs, color=colors[j], lw=1.7, alpha=0.9)
        ax.scatter(xs, ys, zs, color=colors[j], s=16)

    # Flat mean plane (Poly3DCollection)
    mean = (probs[:, None] * Ms).sum(axis=0)  # constant = S0
    mean_val = mean.mean()
    xs = np.array([0, n, n, 0])
    ys = np.array([0, 0, len(words) - 1, len(words) - 1])
    zs = np.array([mean_val] * 4)
    verts = [list(zip(xs, ys, zs))]
    ax.add_collection3d(Poly3DCollection(verts, facecolor=GOLD,
                                         alpha=0.45, edgecolor=NAVY, lw=1.0))
    ax.text(0.0, len(words) - 1, mean_val + 0.8,
            fr"mean plane $z={mean_val:.2f}$", color=NAVY, fontsize=11,
            fontweight="bold")

    ax.set_xlabel("$k$", labelpad=10)
    ax.set_ylabel("path index", labelpad=10)
    ax.set_zlabel(r"$\widetilde M_k$", labelpad=10)
    ax.set_title(r"$\widetilde M$ under $\tilde{\mathbb{P}}$ — flat mean plane $=$ martingale",
                 pad=18)
    _save("ch03-Mtilde-3d.png")


def fig_Mtilde_P_3d():
    """Same but under real-world P (p=0.6): tilted expected line."""
    n = 3
    words = omegas(n)
    p = REAL_PT  # 0.6
    Ms = np.array([_Mtilde_path(w) for w in words])
    probs = np.array([p ** heads(w) * (1 - p) ** (n - heads(w)) for w in words])

    # Add some sampled noise paths (24 paths)
    rng = np.random.default_rng(7)
    sample_words = rng.choice(words, size=24,
                              p=probs / probs.sum())
    sample_paths = np.array([_Mtilde_path(w) for w in sample_words])

    fig = plt.figure(figsize=(14, 9))
    ax = fig.add_subplot(111, projection="3d")

    colors = plt.cm.plasma(np.linspace(0.05, 0.95, len(sample_words)))
    for j in range(len(sample_words)):
        xs = np.arange(n + 1)
        ys = np.full(n + 1, j)
        zs = sample_paths[j]
        ax.plot(xs, ys, zs, color=colors[j], lw=1.3, alpha=0.85)

    # Expected path under P
    EM = (probs[:, None] * Ms).sum(axis=0)
    xs = np.arange(n + 1)
    ys = np.full(n + 1, len(sample_words) / 2)
    ax.plot(xs, ys, EM, color=NAVY, lw=4.0, label=r"$\mathbb{E}[\widetilde M_k]$ tilts up")
    ax.scatter(xs, ys, EM, color=NAVY, s=40)

    ax.set_xlabel("$k$", labelpad=10)
    ax.set_ylabel("path index", labelpad=10)
    ax.set_zlabel(r"$\widetilde M_k$", labelpad=10)
    ax.set_title(r"$\widetilde M$ under real-world $\mathbb{P}$ ($p=0.6$) — sub-martingale drift",
                 pad=18)
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.92))
    _save("ch03-Mtilde-P-3d.png")


def _stop_time(word, threshold=8.0):
    """First k with S_k >= threshold; if never, return n."""
    S = price_path(word)
    for k, s in enumerate(S):
        if s >= threshold:
            return k
    return len(S) - 1


def fig_stopping_tree():
    """Tree on Omega_3, stopping nodes circled in gold."""
    n = 3
    words = omegas(n)
    fig, ax = plt.subplots(figsize=(13, 8))

    leaf_ys = np.linspace(0, 1, len(words))
    leaf_pos = dict(zip(words, leaf_ys))

    def prefix_y(prefix):
        return float(np.mean([leaf_pos[w] for w in words if w.startswith(prefix)]))

    prefixes = sorted({w[:k] for w in words for k in range(n + 1)},
                      key=lambda s: (len(s), s))

    # path colours by stop time
    stop_colors = {0: GOLD, 1: ORANGE, 2: PURPLE, 3: BLUE}

    # Draw edges with colour by stop time of leaf with that prefix
    for p in prefixes:
        if len(p) == n:
            continue
        x0 = len(p)
        y0 = prefix_y(p)
        for c, ecol in (("H", GREEN), ("T", RED)):
            child = p + c
            x1 = len(child)
            y1 = prefix_y(child)
            ax.plot([x0, x1], [y0, y1], color=ecol, lw=1.6, alpha=0.55)

    # Nodes: highlight stopping nodes
    for p in prefixes:
        k = len(p)
        x = k
        y = prefix_y(p)
        # is p a stopping node? S_k(prefix) reaches threshold
        S = price_path(p) if p else [TOY_S0]
        S_at_k = S[-1]
        if S_at_k >= 8.0:
            ax.scatter([x], [y], s=380, facecolor=GOLD, edgecolor=NAVY,
                       lw=2.0, zorder=6)
            # Only annotate the FIRST-stop (interior) nodes; leaf labels carry tau too
            if k < n:
                ax.text(x - 0.07, y + 0.04, fr"$\tau={k}$",
                        ha="right", va="bottom", fontsize=10,
                        color=NAVY, fontweight="bold")
        else:
            ax.scatter([x], [y], s=160, color=NAVY, zorder=5)

    for w in words:
        tau = _stop_time(w)
        ax.text(n + 0.12, leaf_pos[w],
                f"{w}: $\\tau$={tau}, $S_3$={price_path(w)[-1]:g}",
                va="center", fontsize=10, color=NAVY)

    ax.set_xlim(-0.3, n + 1.9)
    ax.set_ylim(-0.05, 1.07)
    ax.set_xticks(range(n + 1))
    ax.set_xticklabels([f"$k={k}$" for k in range(n + 1)])
    ax.set_yticks([])
    ax.grid(False)
    ax.set_title(r"Stopping rule $\tau = \min\{k : S_k\geq 8\}$ (Toy) — gold = stop")
    _save("ch03-stopping-tree.png")


def fig_stopped_3d():
    """Stopped process S_{tau ^ k} over (k, path, S) — flat tail."""
    n = 3
    words = omegas(n)
    fig = plt.figure(figsize=(14, 9))
    ax = fig.add_subplot(111, projection="3d")

    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(words)))
    for j, w in enumerate(words):
        S = price_path(w)
        tau = _stop_time(w)
        stopped = [S[min(k, tau)] for k in range(n + 1)]
        xs = np.arange(n + 1)
        ys = np.full(n + 1, j)
        ax.plot(xs, ys, stopped, color=colors[j], lw=2.2, alpha=0.9)
        ax.scatter(xs, ys, stopped, color=colors[j], s=22)
        # Mark stop point
        ax.scatter([tau], [j], [S[tau]], color=GOLD, s=80,
                   edgecolor=NAVY, lw=1.2)

    ax.set_xlabel("$k$", labelpad=10)
    ax.set_ylabel("path index", labelpad=10)
    ax.set_zlabel(r"$S_{\tau\wedge k}$", labelpad=10)
    ax.set_title(r"Stopped process $S_{\tau \wedge k}$ — flat tails after stop (gold)",
                 pad=18)
    _save("ch03-stopped-3d.png")


def fig_ost_bars():
    """Bar chart of Etilde[Mtilde_tau] under five stopping rules — all = 4."""
    n = 3
    words = omegas(n)
    pt = TOY_PT
    probs = np.array([pt ** heads(w) * (1 - pt) ** (n - heads(w)) for w in words])
    Mt = {w: _Mtilde_path(w) for w in words}

    def rule_tau(w, kind):
        S = price_path(w)
        if kind == "first H":
            for k, c in enumerate(w, start=1):
                if c == "H":
                    return k
            return n
        if kind == "first T":
            for k, c in enumerate(w, start=1):
                if c == "T":
                    return k
            return n
        if kind == "S>=8":
            for k, s in enumerate(S):
                if s >= 8:
                    return k
            return n
        if kind == "k=2":
            return 2
        if kind == "k=n":
            return n
        return n

    rules_keys = ["k=n", "k=2", "first H", "first T", "S>=8"]
    rules_lbl = [r"$\tau=n$", r"$\tau=2$", r"first $H$",
                 r"first $T$", r"$S_k\geq 8$"]
    means = []
    for r in rules_keys:
        taus = [rule_tau(w, r) for w in words]
        vals = np.array([Mt[w][t] for w, t in zip(words, taus)])
        means.append(float((probs * vals).sum()))

    fig, ax = plt.subplots(figsize=(11, 6.5))
    colors = [BLUE, ORANGE, GREEN, PURPLE, TEAL]
    bars = ax.bar(rules_lbl, means, color=colors,
                  edgecolor=NAVY, lw=1.2, width=0.6)
    ax.axhline(TOY_S0, color=GOLD, lw=2.5, ls="--",
               label=r"$\widetilde M_0=4$", zorder=1)
    for b, v in zip(bars, means):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.18, f"{v:.3f}",
                ha="center", fontsize=11, color=NAVY, fontweight="bold")
    ax.set_ylim(0, max(means) * 1.35 + 0.5)
    ax.set_ylabel(r"$\tilde{\mathbb{E}}[\widetilde M_\tau]$", fontsize=12)
    ax.set_xlabel(r"stopping rule $\tau$", fontsize=12)
    ax.tick_params(axis="x", labelsize=11)
    ax.set_title(r"Optional Stopping: $\tilde{\mathbb{E}}[\widetilde M_\tau]=4$ for every bounded $\tau$",
                 fontsize=13, pad=12)
    ax.legend(loc="upper right", framealpha=0.95)
    _save("ch03-ost-bars.png")


def fig_change_of_measure_bars():
    """Three bar charts: P, Ptilde, and ratio Z on Omega_2."""
    n = 2
    words = omegas(n)
    p = 0.6
    pt = TOY_PT
    Pmass = np.array([p ** heads(w) * (1 - p) ** (n - heads(w)) for w in words])
    PTmass = np.array([pt ** heads(w) * (1 - pt) ** (n - heads(w)) for w in words])
    Z = PTmass / Pmass

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    x = np.arange(len(words))

    axes[0].bar(x, Pmass, color=BLUE, edgecolor=NAVY)
    axes[0].set_title(r"$\mathbb{P}$ leaf masses ($p=0.6$)")
    axes[0].set_ylabel("mass")

    axes[1].bar(x, PTmass, color=ORANGE, edgecolor=NAVY)
    axes[1].set_title(r"$\tilde{\mathbb{P}}$ leaf masses ($\tilde p=0.5$)")

    axes[2].bar(x, Z, color=PURPLE, edgecolor=NAVY)
    axes[2].set_title(r"$Z(\omega) = \tilde{\mathbb{P}}/\mathbb{P}$")
    axes[2].axhline(1.0, color=GOLD, lw=1.5, ls="--")

    for ax, vals in zip(axes, (Pmass, PTmass, Z)):
        ax.set_xticks(x)
        ax.set_xticklabels(words)
        for i, v in enumerate(vals):
            ax.text(i, v + 0.01, f"{v:.2f}", ha="center", fontsize=9, color=NAVY)

    plt.tight_layout()
    _save("ch03-change-of-measure-bars.png")


def fig_Z_3d_bar():
    """Filled Poly3DCollection ridges of Z(omega) over Omega_3.

    One filled polygon per omega; the polygon is swept along the k-axis
    (depth) so each ridge is a clean wall from the base plane up to z=Z(omega).
    This avoids the clipping / narrow-bar issues of stacked prisms.
    """
    n = 3
    words = omegas(n)
    p = 0.6
    pt = TOY_PT
    Pmass = np.array([p ** heads(w) * (1 - p) ** (n - heads(w)) for w in words])
    PTmass = np.array([pt ** heads(w) * (1 - pt) ** (n - heads(w)) for w in words])
    Z = PTmass / Pmass

    fig = plt.figure(figsize=(13, 8.5))
    ax = fig.add_subplot(111, projection="3d")
    try:
        ax.set_box_aspect((2.6, 1.4, 1.6))
    except Exception:
        pass

    depth_max = float(n)  # y axis spans k = 0 .. n

    for i, (w, z) in enumerate(zip(words, Z)):
        # one filled ridge per omega: a vertical wall at x=i extending in y
        # from k=0 to k=n, rising from base plane to z.
        color = GREEN if z > 1 else (RED if z < 1 else GOLD)
        verts = [[
            (i, 0.0, 0.0),
            (i, depth_max, 0.0),
            (i, depth_max, z),
            (i, 0.0, z),
        ]]
        poly = Poly3DCollection(verts, facecolor=color, alpha=0.78,
                                edgecolor=NAVY, lw=1.0)
        ax.add_collection3d(poly)
        # value label above the ridge top-front corner
        ax.text(i, 0.0, z + 0.05, f"{z:.2f}", ha="center",
                fontsize=11, color=NAVY, fontweight="bold")

    # Reference plane Z=1 (gold translucent)
    xs = np.array([-0.5, len(words) - 0.5, len(words) - 0.5, -0.5])
    ys = np.array([0.0, 0.0, depth_max, depth_max])
    zs = np.array([1.0, 1.0, 1.0, 1.0])
    plane = [list(zip(xs, ys, zs))]
    ax.add_collection3d(Poly3DCollection(plane, facecolor=GOLD,
                                         alpha=0.30, edgecolor=NAVY, lw=0.8))
    ax.text(len(words) - 0.5, depth_max, 1.0 + 0.06,
            r"$Z=1$", color=NAVY, fontsize=11, ha="right",
            fontweight="bold")

    ax.set_xticks(range(len(words)))
    ax.set_xticklabels(words, fontsize=11)
    ax.set_yticks([0, depth_max])
    ax.set_yticklabels([r"$k=0$", fr"$k={n}$"], fontsize=11)
    ax.set_xlim(-0.5, len(words) - 0.5)
    ax.set_ylim(0.0, depth_max)
    ax.set_zlim(0.0, max(Z.max() * 1.15, 1.2))
    ax.set_xlabel(r"$\omega \in \Omega_3$", labelpad=18, fontsize=12)
    ax.set_ylabel(r"depth $k$", labelpad=14, fontsize=12)
    ax.set_zlabel(r"$Z(\omega)$", labelpad=18, fontsize=12)
    ax.set_title(r"Radon-Nikodym $Z = d\tilde{\mathbb{P}}/d\mathbb{P}$ on $\Omega_3$" +
                 "  (green: $Z>1$, red: $Z<1$, gold plane: $Z=1$)",
                 fontsize=13, pad=14)
    ax.view_init(elev=22, azim=-58)
    _save("ch03-Z-3d-bar.png")


def fig_Zk_heatmap():
    """Heatmap rows omega in Omega_3, cols k -> Z_k stabilises leftward."""
    n = 3
    words = omegas(n)
    p = 0.6
    pt = TOY_PT

    # Z_k(omega) = E[Z | F_k](omega).
    # For each omega and k, Z_k = Ptilde(F_k(omega)) / P(F_k(omega))
    def mass(prefix, prob):
        h = prefix.count("H")
        t = prefix.count("T")
        return prob ** h * (1 - prob) ** t

    M = np.zeros((len(words), n + 1))
    for i, w in enumerate(words):
        for k in range(n + 1):
            prefix = w[:k]
            num = mass(prefix, pt)
            den = mass(prefix, p)
            M[i, k] = num / den

    fig, ax = plt.subplots(figsize=(11, 7.5))
    im = ax.imshow(M, aspect="auto", cmap="plasma", origin="upper")
    vmin, vmax = M.min(), M.max()
    for i in range(len(words)):
        for k in range(n + 1):
            frac = (M[i, k] - vmin) / (vmax - vmin) if vmax > vmin else 0.0
            # plasma is dark at low end, bright yellow at high end
            txt_col = "black" if frac > 0.7 else "white"
            ax.text(k, i, f"{M[i, k]:.2f}", ha="center", va="center",
                    fontsize=11, color=txt_col, fontweight="bold")
    ax.set_xticks(range(n + 1))
    ax.set_xticklabels([f"$Z_{k}$" for k in range(n + 1)], fontsize=11)
    ax.set_yticks(range(len(words)))
    ax.set_yticklabels(words, fontsize=11)
    ax.set_xlabel("$k$", fontsize=12)
    ax.set_ylabel(r"$\omega \in \Omega_3$", fontsize=12)
    ax.set_title(r"$Z_k$ heatmap: leftward stabilisation $=$ $\mathbb{P}$-martingale (Toy)",
                 fontsize=13, pad=12)
    cb = plt.colorbar(im, ax=ax, label=r"$Z_k$", shrink=0.7, pad=0.04)
    cb.set_label(r"$Z_k$", fontsize=11)
    ax.grid(False)
    _save("ch03-Zk-heatmap.png")


def fig_Zk_mesh():
    """3-D wire mesh of Z_k over recombining (k, heads-so-far) lattice."""
    n = 3
    p = 0.6
    pt = TOY_PT

    # Z_k depends only on (k, h) = (time, heads-so-far)
    # because P, Ptilde are iid Bernoulli.
    # Z_k(h) = (pt/p)^h * ((1-pt)/(1-p))^(k-h)
    pts = []
    edges = []
    node_z = {}
    for k in range(n + 1):
        for h in range(k + 1):
            z = (pt / p) ** h * ((1 - pt) / (1 - p)) ** (k - h)
            x = k
            y = h - k / 2  # centre vertically
            node_z[(k, h)] = (x, y, z)
            pts.append((x, y, z))

    for k in range(n):
        for h in range(k + 1):
            # H child -> (k+1, h+1)
            edges.append(((k, h), (k + 1, h + 1)))
            # T child -> (k+1, h)
            edges.append(((k, h), (k + 1, h)))

    fig = plt.figure(figsize=(14, 9))
    ax = fig.add_subplot(111, projection="3d")

    # Edges
    for a, b in edges:
        xa, ya, za = node_z[a]
        xb, yb, zb = node_z[b]
        col = GREEN if b[1] - a[1] == 1 else RED
        ax.plot([xa, xb], [ya, yb], [za, zb], color=col, lw=1.4, alpha=0.7)

    # Nodes coloured by Z value
    xs = [v[0] for v in pts]
    ys = [v[1] for v in pts]
    zs = [v[2] for v in pts]
    sc = ax.scatter(xs, ys, zs, c=zs, cmap="plasma", s=140,
                    edgecolor=NAVY, lw=0.8)
    for (k, h), (x, y, z) in node_z.items():
        ax.text(x, y, z + 0.06, f"{z:.2f}", fontsize=8, color=NAVY,
                ha="center")

    plt.colorbar(sc, ax=ax, label=r"$Z_k$ value", shrink=0.7, pad=0.12)
    ax.set_xlabel("$k$", labelpad=10)
    ax.set_ylabel("heads-so-far", labelpad=12)
    ax.set_zlabel(r"$Z_k$", labelpad=10)
    ax.set_title(r"$Z_k$ on the recombining lattice — $\mathbb{P}$-martingale", pad=18)
    _save("ch03-Zk-mesh.png")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Building Chapter 3 figures...")
    fig_omega_tree()
    fig_pathbundle_3d()
    fig_event_venn()
    fig_leaf_masses()
    fig_nested_rectangles()
    fig_Fk_blocks()
    fig_telescope_partitions_3d()
    fig_Fk_colour_tree()
    fig_Sk_heatmap()
    fig_adapted_vs_not()
    fig_block_average_tree()
    fig_block_avg_3d()
    fig_tower_cartoon()
    fig_martingale_paths()
    fig_Mtilde_3d()
    fig_Mtilde_P_3d()
    fig_stopping_tree()
    fig_stopped_3d()
    fig_ost_bars()
    fig_change_of_measure_bars()
    fig_Z_3d_bar()
    fig_Zk_heatmap()
    fig_Zk_mesh()
    print("Done.")
