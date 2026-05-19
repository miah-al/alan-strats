"""
Chapter 1 figure builder for Binomial Option Pricing.

Run: python docs/binomial-option-pricing/_build_ch1_figs.py

Outputs under figures/:
 ch01-tree-skeleton-st.png
 ch01-tree-side-by-side.png
 ch01-noarb-zones.png
 ch01-arb-cashflow.png
 ch01-replication-wheel.png
 ch01-delta-plane-3d.png
 ch01-cost-decomposition.png
 ch01-tildep-vs-r.png
 ch01-call-surface-3d.png
 ch01-commutative-diagram.png
 ch01-real-vs-rn-trees.png
 ch01-returns-bars.png
 ch01-payoff-strip.png
 ch01-menagerie-3d.png
 ch01-parity-payoff.png
 ch01-dealer-pl.png

Toy market:       S0=4,   u=2,    d=1/2,  r=1/4, ptilde=1/2
Realistic market: S0=100, u=1.10, d=0.90, r=2%,  ptilde=0.6

Style: bright palette. 3-D figures use filled Poly3DCollection (not 3-D bars).
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — register 3-D projection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

FIG_DIR = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG_DIR, exist_ok=True)
DPI = 200

# Bright, distinguishable palette
NAVY = "#0b1d3a"
BLUE = "#1f77b4"
ORANGE = "#ff7f0e"
GREEN = "#2ca02c"
RED = "#d62728"
PURPLE = "#9467bd"
GOLD = "#fbbf24"
TEAL = "#17becf"
GREY = "#666666"

# Toy market
TOY_S0 = 4.0
TOY_U = 2.0
TOY_D = 0.5
TOY_R = 0.25
TOY_PTILDE = 0.5

# Realistic market
RL_S0 = 100.0
RL_U = 1.10
RL_D = 0.90
RL_R = 0.02
RL_PTILDE = 0.6


def _save(name: str, *, tight: bool = True, pad: float = 0.2) -> None:
    """Save current figure. For 3-D figures, pass tight=False so the
    bbox_inches='tight' crop does not collapse the empty axes margins
    and produce a thumbnail-size render."""
    path = os.path.join(FIG_DIR, name)
    if tight:
        plt.savefig(path, dpi=DPI, bbox_inches="tight")
    else:
        plt.savefig(path, dpi=DPI, pad_inches=pad)
    plt.close()
    print(f"  wrote {name}")


def _draw_tree(ax, S0, Su, Sd, *, title=None, p_up=None, p_dn=None,
               up_label=None, dn_label=None):
    """Draw a one-step binomial tree on ax (2-D matplotlib axes).

    Node markers are kept small dots; the numeric label is placed
    BESIDE each node (with a coloured bbox) so text never overflows.
    """
    x0, y0 = 0.05, 0.5
    xu, yu = 0.85, 0.92
    xd, yd = 0.85, 0.08
    ax.plot([x0, xu], [y0, yu], color=GREEN, lw=2.4, zorder=1)
    ax.plot([x0, xd], [y0, yd], color=RED, lw=2.4, zorder=1)

    def _node(x, y, txt, col, ha, dx):
        ax.scatter([x], [y], s=80, color=col, edgecolor=NAVY,
                   linewidth=1.4, zorder=3)
        ax.text(x + dx, y, txt, ha=ha, va="center", color=col,
                fontsize=11, fontweight="bold", zorder=4,
                bbox=dict(boxstyle="round,pad=0.25", fc="white",
                          ec=col, lw=1.2))

    _node(x0, y0, f"$S_0={S0:g}$", NAVY, "right", -0.03)
    _node(xu, yu, up_label or f"$S_1(H)={Su:g}$", GREEN, "left", 0.04)
    _node(xd, yd, dn_label or f"$S_1(T)={Sd:g}$", RED, "left", 0.04)

    if p_up is not None:
        ax.text(0.42, 0.78, f"$p={p_up:g}$", color=GREEN, fontsize=10,
                ha="center", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.18", fc="white",
                          ec="none", alpha=0.85))
    if p_dn is not None:
        ax.text(0.42, 0.22, f"$1-p={p_dn:g}$", color=RED, fontsize=10,
                ha="center", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.18", fc="white",
                          ec="none", alpha=0.85))
    ax.set_xlim(-0.25, 1.30)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    if title:
        ax.set_title(title, color=NAVY, fontweight="bold", fontsize=11)


def fig_tree_skeleton_st():
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    Su = TOY_S0 * TOY_U
    Sd = TOY_S0 * TOY_D
    _draw_tree(ax, TOY_S0, Su, Sd,
               title=f"Toy one-step tree: $S_0={TOY_S0:g}$, $u={TOY_U:g}$, $d={TOY_D:g}$")
    ax.text(0.5, -0.02, "green = up ($H$)   |   red = down ($T$)",
            ha="center", color=GREY, fontsize=9, transform=ax.transAxes)
    _save("ch01-tree-skeleton-st.png")


def fig_tree_side_by_side():
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.2))
    _draw_tree(axes[0], TOY_S0, TOY_S0 * TOY_U, TOY_S0 * TOY_D,
               title=f"Toy: $u={TOY_U:g}$, $d={TOY_D:g}$  ($u\\cdot d=1$)")
    _draw_tree(axes[1], RL_S0, RL_S0 * RL_U, RL_S0 * RL_D,
               title=f"Realistic: $u={RL_U:.2f}$, $d={RL_D:.2f}$  ($u\\cdot d=0.99$)")
    fig.suptitle("Same geometry, different numbers", color=NAVY,
                 fontweight="bold", fontsize=12)
    _save("ch01-tree-side-by-side.png")


def fig_noarb_zones():
    # Wider canvas + dedicated label gutter on the left.
    fig, ax = plt.subplots(figsize=(11.0, 3.8))
    markets = [
        ("Toy",     TOY_D, 1 + TOY_R, TOY_U,  GREEN),
        ("RL",      RL_D,  1 + RL_R,  RL_U,   BLUE),
        ("Broken",  0.95,  1.02,      1.00,   RED),
    ]
    ymax = len(markets)
    # Strip starts at x=0.40 — accommodates Toy's d=0.5 endpoint and
    # leaves room for the row name in the left gutter (x < 0.40).
    strip_left = 0.40
    for i, (name, d, gross, u, col) in enumerate(markets):
        y = ymax - 1 - i
        ax.axhline(y, color="lightgrey", lw=0.6, zorder=0)
        ax.plot([strip_left, d], [y, y], color=RED, lw=7,
                solid_capstyle="butt", alpha=0.55)
        ax.plot([d, u], [y, y], color=GREEN, lw=7,
                solid_capstyle="butt", alpha=0.55)
        ax.plot([u, 2.2], [y, y], color=RED, lw=7,
                solid_capstyle="butt", alpha=0.55)
        ax.scatter([d], [y], s=120, color=RED, edgecolor=NAVY,
                   zorder=4, marker="o")
        ax.scatter([u], [y], s=120, color=RED, edgecolor=NAVY,
                   zorder=4, marker="o")
        ax.scatter([gross], [y], s=160, color=GOLD, edgecolor=NAVY,
                   linewidth=1.6, zorder=5, marker="D")

        # Stagger d/u labels: if d and u are too close, push u below
        # and 1+r further down so they do not collide.
        gap = u - d
        if gap < 0.10:
            ax.text(d, y + 0.22, f"$d={d:g}$", ha="right", fontsize=9,
                    color=NAVY)
            ax.text(u, y + 0.22, f"$u={u:g}$", ha="left", fontsize=9,
                    color=NAVY)
            ax.text(gross, y - 0.32, f"$1+r={gross:g}$", ha="center",
                    fontsize=9, color=NAVY, fontweight="bold")
        else:
            ax.text(d, y + 0.22, f"$d={d:g}$", ha="center", fontsize=9,
                    color=NAVY)
            ax.text(u, y + 0.22, f"$u={u:g}$", ha="center", fontsize=9,
                    color=NAVY)
            ax.text(gross, y - 0.30, f"$1+r={gross:g}$", ha="center",
                    fontsize=9, color=NAVY, fontweight="bold")

        # Row name in dedicated left gutter (x < strip_left).
        ax.text(0.32, y, name, ha="right", va="center", fontsize=11,
                color=col, fontweight="bold")
    ax.set_xlim(0.10, 2.30)
    ax.set_ylim(-0.7, ymax - 0.3)
    ax.set_yticks([])
    ax.set_xlabel("gross rate")
    ax.set_title("No-arbitrage zones: $d < 1+r < u$ (green) vs arbitrage (red)",
                 color=NAVY, fontweight="bold")
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    _save("ch01-noarb-zones.png")


def fig_arb_cashflow():
    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    # Broken-up arbitrage: u=1.01, d=0.97, 1+r=1.02
    S0 = 1.0
    u_b, d_b, gross = 1.01, 0.97, 1.02

    # t=0 position
    ax.add_patch(FancyBboxPatch((0.05, 0.78), 0.9, 0.14,
                                boxstyle="round,pad=0.02",
                                facecolor="#eaf2ff", edgecolor=NAVY))
    ax.text(0.5, 0.85,
            f"t=0: short 1 share (+\\${S0:g}) and lend \\${S0:g} (-\\${S0:g})  "
            f"$\\Rightarrow$ net cash 0",
            ha="center", va="center", fontsize=10, color=NAVY, fontweight="bold")

    # t=1 H
    ax.add_patch(FancyBboxPatch((0.05, 0.40), 0.42, 0.22,
                                boxstyle="round,pad=0.02",
                                facecolor="#e6f7ec", edgecolor=GREEN))
    ax.text(0.26, 0.56, "State $H$  ($S_1 = uS_0 = 1.01$)", ha="center",
            fontsize=10, color=GREEN, fontweight="bold")
    ax.text(0.26, 0.50, f"repurchase share: $-{u_b:g}\\,S_0$", ha="center",
            fontsize=9, color=NAVY)
    ax.text(0.26, 0.46, f"bond pays back: $+{gross:g}\\,S_0$", ha="center",
            fontsize=9, color=NAVY)
    ax.text(0.26, 0.42, f"net: $+{gross - u_b:.2f}\\,S_0$", ha="center",
            fontsize=10, color=GREEN, fontweight="bold")

    # t=1 T
    ax.add_patch(FancyBboxPatch((0.53, 0.40), 0.42, 0.22,
                                boxstyle="round,pad=0.02",
                                facecolor="#fdecec", edgecolor=RED))
    ax.text(0.74, 0.56, "State $T$  ($S_1 = dS_0 = 0.97$)", ha="center",
            fontsize=10, color=RED, fontweight="bold")
    ax.text(0.74, 0.50, f"repurchase share: $-{d_b:g}\\,S_0$", ha="center",
            fontsize=9, color=NAVY)
    ax.text(0.74, 0.46, f"bond pays back: $+{gross:g}\\,S_0$", ha="center",
            fontsize=9, color=NAVY)
    ax.text(0.74, 0.42, f"net: $+{gross - d_b:.2f}\\,S_0$", ha="center",
            fontsize=10, color=RED, fontweight="bold")

    # Arrows
    ax.annotate("", xy=(0.26, 0.62), xytext=(0.4, 0.78),
                arrowprops=dict(arrowstyle="->", color=GREEN, lw=2))
    ax.annotate("", xy=(0.74, 0.62), xytext=(0.6, 0.78),
                arrowprops=dict(arrowstyle="->", color=RED, lw=2))

    ax.text(0.5, 0.22,
            "Both outcomes pay strictly positive cash $\\Rightarrow$ arbitrage.",
            ha="center", fontsize=11, color=PURPLE, fontweight="bold")
    ax.text(0.5, 0.10,
            "(condition $1+r \\geq u$ violated: $1.02 > 1.01$)",
            ha="center", fontsize=10, color=NAVY)

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("Arbitrage cashflow when $1+r$ exceeds $u$",
                 color=NAVY, fontweight="bold", fontsize=12)
    _save("ch01-arb-cashflow.png")


def fig_replication_wheel():
    # Wider canvas so we can place labels well outside the arrow body.
    fig, ax = plt.subplots(figsize=(10.0, 6.2))
    # Toy: V_u=3, V_d=0 (call payoff with K=5). Delta = 0.5, B = -0.8.
    # stock vec = (uS0, dS0) = (8, 2); delta*stock = (4, 1)
    # bond vec = (1+r, 1+r) = (1.25, 1.25); B*bond = (-1, -1)
    # sum = (3, 0).
    O = np.array([0.0, 0.0])
    stock = np.array([8.0, 2.0])
    delta = 0.5
    delta_stock = delta * stock
    bond = np.array([1.25, 1.25])
    B = -0.8
    B_bond = B * bond
    payoff = delta_stock + B_bond

    def draw_arrow(start, end, color, ls="-"):
        ax.annotate("", xy=end, xytext=start,
                    arrowprops=dict(arrowstyle="-|>", color=color,
                                    lw=2.4, linestyle=ls,
                                    mutation_scale=18))

    # Draw the four arrows first; labels are placed manually below.
    draw_arrow(O, stock,                  BLUE,   ls="--")
    draw_arrow(O, delta_stock,            BLUE)
    draw_arrow(delta_stock,
               delta_stock + B_bond,      ORANGE)
    draw_arrow(O, payoff,                 GREEN)

    # Place each label with a unique offset and a white bbox so they
    # never bump into the dashed stock-vector or each other.
    # ax.annotate with xytext + arrow pulls a leader line to the
    # label so the connection stays clear.
    label_specs = [
        # (anchor point, text, xytext offset (data coords), colour)
        (stock,                       "stock $(uS_0,dS_0)=(8,2)$",
            (8.4, 2.6),  BLUE),
        (delta_stock,                 "$\\Delta\\cdot$stock $=(4,1)$",
            (4.6, 1.9),  BLUE),
        (delta_stock + 0.5 * B_bond,  "$B\\cdot$bond $=(-1,-1)$",
            (4.2, 0.05), ORANGE),
        (0.5 * payoff,                "payoff $(V_u,V_d)=(3,0)$",
            (1.5, -0.9), GREEN),
    ]
    for anchor, txt, xy_txt, col in label_specs:
        ax.annotate(txt, xy=anchor, xytext=xy_txt,
                    color=col, fontsize=10, fontweight="bold",
                    ha="left", va="center",
                    bbox=dict(boxstyle="round,pad=0.25", fc="white",
                              ec=col, lw=1.0, alpha=0.95),
                    arrowprops=dict(arrowstyle="-", color=col,
                                    lw=0.8, alpha=0.6))

    ax.scatter([payoff[0]], [payoff[1]], s=160, color=GREEN,
               edgecolor=NAVY, zorder=5)
    ax.text(5.5, -1.5,
            "tip-to-tail: $(4,1)+(-1,-1)=(3,0)$  $\\checkmark$",
            fontsize=10, color=NAVY, ha="left",
            bbox=dict(boxstyle="round,pad=0.3", fc="#fffbe6", ec=GOLD))

    ax.axhline(0, color="lightgrey", lw=0.6)
    ax.axvline(0, color="lightgrey", lw=0.6)
    ax.set_xlim(-2, 10)
    ax.set_ylim(-2, 3.2)
    ax.set_xlabel("value in state $H$ ($V_u$)", color=NAVY)
    ax.set_ylabel("value in state $T$ ($V_d$)", color=NAVY)
    ax.set_title("Replication as 2-D vector decomposition (Toy call)",
                 color=NAVY, fontweight="bold")
    ax.set_aspect("equal", adjustable="box")
    _save("ch01-replication-wheel.png")


def fig_delta_plane_3d():
    fig = plt.figure(figsize=(10.0, 7.0))
    ax = fig.add_subplot(111, projection="3d")
    # Delta = (V_u - V_d) / ((u-d)S0); for Toy: (u-d)S0 = 1.5 * 4 = 6
    denom = (TOY_U - TOY_D) * TOY_S0
    Vu = np.linspace(0, 6, 25)
    Vd = np.linspace(0, 6, 25)
    Vu_g, Vd_g = np.meshgrid(Vu, Vd)
    Delta = (Vu_g - Vd_g) / denom

    verts = []
    colors = []
    cmap = plt.get_cmap("viridis")
    Dmin, Dmax = Delta.min(), Delta.max()
    for i in range(Vu_g.shape[0] - 1):
        for j in range(Vu_g.shape[1] - 1):
            poly = [
                (Vu_g[i, j],     Vd_g[i, j],     Delta[i, j]),
                (Vu_g[i + 1, j], Vd_g[i + 1, j], Delta[i + 1, j]),
                (Vu_g[i + 1, j + 1], Vd_g[i + 1, j + 1], Delta[i + 1, j + 1]),
                (Vu_g[i, j + 1], Vd_g[i, j + 1], Delta[i, j + 1]),
            ]
            verts.append(poly)
            mean_d = 0.25 * (Delta[i, j] + Delta[i + 1, j] +
                             Delta[i + 1, j + 1] + Delta[i, j + 1])
            colors.append(cmap((mean_d - Dmin) / (Dmax - Dmin + 1e-9)))
    coll = Poly3DCollection(verts, facecolors=colors, edgecolors="none",
                            alpha=0.85)
    ax.add_collection3d(coll)

    # Three derivatives on surface. Dots are drawn in 3-D at the
    # true (vu,vd,z); labels are placed in 2-D axes-fraction space
    # (text2D) so they never overlap due to the 3-D projection.
    pts = [
        ("call $(3,0) \\to \\Delta=+0.50$",     3.0, 0.0, GREEN,
            (0.55, 0.94)),
        ("put $(0,3) \\to \\Delta=-0.50$",      0.0, 3.0, RED,
            (0.05, 0.14)),
        ("straddle $(4,2) \\to \\Delta=+0.33$", 4.0, 2.0, PURPLE,
            (0.70, 0.06)),
    ]
    for label, vu, vd, col, (fx, fy) in pts:
        z = (vu - vd) / denom
        ax.scatter([vu], [vd], [z], s=120, color=col, edgecolor=NAVY,
                   linewidth=1.6, zorder=10)
        ax.text2D(fx, fy, label, transform=ax.transAxes,
                  color=col, fontsize=10, fontweight="bold",
                  ha="left", va="center",
                  bbox=dict(boxstyle="round,pad=0.25", fc="white",
                            ec=col, lw=1.0, alpha=0.95))

    ax.set_xlim(0, 6)
    ax.set_ylim(0, 6)
    ax.set_zlim(Dmin - 0.6, Dmax + 0.8)
    ax.set_xlabel("$V_u$", color=NAVY)
    ax.set_ylabel("$V_d$", color=NAVY)
    ax.set_zlabel("$\\Delta$", color=NAVY)
    ax.set_title("$\\Delta$ as linear function of payoff (Toy, $(u-d)S_0=6$)",
                 color=NAVY, fontweight="bold")
    ax.view_init(elev=22, azim=-58)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.94, bottom=0.04)
    _save("ch01-delta-plane-3d.png", tight=False)


def fig_cost_decomposition():
    # Five Toy derivatives on a comparable scale (power excluded — its
    # stock leg of +$40 and bond leg of -$13 dwarfed everything else).
    # Toy: S0=4, u=2, d=0.5, r=0.25, ptilde=0.5
    derivs = []

    def add(name, Vu, Vd):
        denom = (TOY_U - TOY_D) * TOY_S0
        D = (Vu - Vd) / denom
        # B = (uVd - dVu) / ((u-d)(1+r))
        B = (TOY_U * Vd - TOY_D * Vu) / ((TOY_U - TOY_D) * (1 + TOY_R))
        derivs.append((name, D * TOY_S0, B, D * TOY_S0 + B))

    add("call $K=5$",     3.0, 0.0)
    add("put $K=5$",      0.0, 3.0)
    add("cash digital",   1.0, 0.0)
    add("forward $K=5$",  3.0, -3.0)
    add("straddle $K=5$", 3.0, 3.0)

    names = [d[0] for d in derivs]
    stock_leg = np.array([d[1] for d in derivs])
    bond_leg = np.array([d[2] for d in derivs])
    total = np.array([d[3] for d in derivs])

    fig, ax = plt.subplots(figsize=(11.0, 5.6))
    x = np.arange(len(names))
    w2 = 0.32
    ax.bar(x - w2 / 2, stock_leg, w2, color=BLUE, edgecolor=NAVY,
           label="stock leg $\\Delta\\,S_0$")
    ax.bar(x + w2 / 2, bond_leg, w2, color=ORANGE, edgecolor=NAVY,
           label="bond leg $B$")
    # Net price marker — place each diamond DIRECTLY ABOVE its bar
    # group at a fixed height in the top margin, then draw a thin
    # leader line from the diamond down to the true net value on
    # the y-axis. This keeps every diamond clear of every bar.
    y_top = max(stock_leg.max(), bond_leg.max(), total.max()) + 1.6
    ax.scatter(x, [y_top] * len(x), s=170, color=GREEN, edgecolor=NAVY,
               linewidth=1.4, zorder=5, marker="D", label="net $V_0$")
    for xi, v in zip(x, total):
        # Dashed leader from y_top diamond down to the actual value.
        ax.plot([xi, xi], [y_top, v], color=GREEN, lw=0.8,
                ls=":", alpha=0.7, zorder=4)
        ax.annotate(f"{v:+.2f}",
                    xy=(xi, y_top),
                    xytext=(0, 12), textcoords="offset points",
                    ha="center", va="bottom",
                    color=GREEN, fontsize=10, fontweight="bold")

    ax.axhline(0, color=GREY, lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=12, ha="right", color=NAVY)
    ax.set_xlim(-0.6, len(names) - 0.4)
    ax.set_ylim(min(stock_leg.min(), bond_leg.min()) - 0.6, y_top + 1.0)
    ax.set_ylabel("dollars", color=NAVY)
    ax.set_title("Cost decomposition $V_0 = \\Delta\\,S_0 + B$ (Toy)",
                 color=NAVY, fontweight="bold")
    ax.legend(loc="lower left", fontsize=9,
              bbox_to_anchor=(0.01, 0.01), framealpha=0.95)
    ax.grid(True, axis="y", alpha=0.3)
    _save("ch01-cost-decomposition.png")


def fig_tildep_vs_r():
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    u, d = 1.10, 0.90
    r = np.linspace(-0.20, 0.20, 200)
    ptilde = (1 + r - d) / (u - d)
    inside = (ptilde >= 0) & (ptilde <= 1)
    ax.plot(r, ptilde, color=GREY, lw=1.2, ls="--", alpha=0.7)
    ax.plot(r[inside], ptilde[inside], color=BLUE, lw=2.6,
            label="$\\tilde p = (1+r-d)/(u-d)$")
    ax.axhline(0, color="lightgrey", lw=0.6)
    ax.axhline(1, color="lightgrey", lw=0.6)

    # r=d-1 endpoint: label INSIDE the plot to the upper-right of the dot.
    ax.scatter([d - 1], [0], s=100, color=RED, edgecolor=NAVY, zorder=5)
    ax.annotate("$r=d-1=-0.10$", xy=(d - 1, 0),
                xytext=(-0.085, 0.13), color=RED, fontsize=9,
                fontweight="bold", ha="left",
                arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))

    # r=u-1 endpoint: label INSIDE the plot to the lower-left of the dot.
    ax.scatter([u - 1], [1], s=100, color=RED, edgecolor=NAVY, zorder=5)
    ax.annotate("$r=u-1=+0.10$", xy=(u - 1, 1),
                xytext=(0.005, 0.87), color=RED, fontsize=9,
                fontweight="bold", ha="left",
                arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))

    ax.axvspan(d - 1, u - 1, color=GREEN, alpha=0.10,
               label="no-arb region")

    # Real-world p reference
    ax.axhline(0.55, color=GREY, lw=1.2, alpha=0.6)
    ax.text(-0.19, 0.575, "real $p=0.55$ (not on curve)",
            ha="left", color=GREY, fontsize=9)

    ax.set_xlim(-0.20, 0.20)
    ax.set_ylim(-0.10, 1.15)
    ax.set_xlabel("$r$", color=NAVY)
    ax.set_ylabel("$\\tilde p$", color=NAVY)
    ax.set_title("Risk-neutral probability vs $r$  ($u=1.10,\\,d=0.90$)",
                 color=NAVY, fontweight="bold")
    ax.legend(loc="upper left", fontsize=9,
              bbox_to_anchor=(0.02, 0.98), framealpha=0.95)
    ax.grid(True, alpha=0.3)
    _save("ch01-tildep-vs-r.png")


def fig_call_surface_3d():
    # Toy call: K=5, d=0.5, S0=4. Vary u in (1+r, 4], r in (-0.5, u-1).
    # V0 = (ptilde * max(uS0-K,0) + (1-ptilde)*max(dS0-K,0)) / (1+r)
    fig = plt.figure(figsize=(10.5, 7.2))
    ax = fig.add_subplot(111, projection="3d")
    S0 = TOY_S0
    K = 5.0
    d = TOY_D
    u_arr = np.linspace(1.30, 3.5, 30)
    r_arr = np.linspace(-0.30, 0.60, 30)
    U, R = np.meshgrid(u_arr, r_arr)
    # Mask: require d < 1+r < u
    valid = (1 + R > d) & (1 + R < U)
    ptilde = (1 + R - d) / (U - d)
    payoff_u = np.maximum(U * S0 - K, 0)
    payoff_d = np.maximum(d * S0 - K, 0)  # 0
    V0 = (ptilde * payoff_u + (1 - ptilde) * payoff_d) / (1 + R)
    V0_masked = np.where(valid, V0, np.nan)

    verts = []
    colors = []
    cmap = plt.get_cmap("plasma")
    Vmin = np.nanmin(V0_masked)
    Vmax = np.nanmax(V0_masked)
    for i in range(U.shape[0] - 1):
        for j in range(U.shape[1] - 1):
            zs = [V0_masked[i, j], V0_masked[i + 1, j],
                  V0_masked[i + 1, j + 1], V0_masked[i, j + 1]]
            if any(np.isnan(z) for z in zs):
                continue
            poly = [
                (U[i, j],     R[i, j],     zs[0]),
                (U[i + 1, j], R[i + 1, j], zs[1]),
                (U[i + 1, j + 1], R[i + 1, j + 1], zs[2]),
                (U[i, j + 1], R[i, j + 1], zs[3]),
            ]
            verts.append(poly)
            colors.append(cmap((np.mean(zs) - Vmin) / (Vmax - Vmin + 1e-9)))
    coll = Poly3DCollection(verts, facecolors=colors, edgecolors="none",
                            alpha=0.9)
    ax.add_collection3d(coll)

    # Mark base contour where 1+r = u (right edge of no-arb)
    u_edge = u_arr
    r_edge = u_arr - 1
    ax.plot(u_edge, r_edge, np.zeros_like(u_edge), color=RED, lw=2,
            label="$1+r=u$ boundary")

    ax.set_xlim(u_arr.min(), u_arr.max())
    ax.set_ylim(r_arr.min(), r_arr.max())
    ax.set_zlim(0, np.nanmax(V0_masked) * 1.1)
    ax.set_xlabel("$u$", color=NAVY)
    ax.set_ylabel("$r$", color=NAVY)
    ax.set_zlabel("$V_0$", color=NAVY)
    ax.set_title("Toy call $V_0$ surface over $(u,r)$  ($d=0.5,\\,K=5$)",
                 color=NAVY, fontweight="bold")
    ax.legend(fontsize=9, loc="upper left", bbox_to_anchor=(0.0, 0.95))
    ax.view_init(elev=24, azim=-62)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.94, bottom=0.04)
    _save("ch01-call-surface-3d.png", tight=False)


def fig_commutative_diagram():
    fig, ax = plt.subplots(figsize=(9.0, 6.0))

    nodes = {
        "TL": (0.18, 0.78, "Payoff\n$(V_u, V_d)$", BLUE),
        "BL": (0.18, 0.22, "Replicating\n$(\\Delta, B)$", ORANGE),
        "TR": (0.78, 0.78, "RN expectation\n$\\frac{\\tilde p V_u + \\tilde q V_d}{1+r}$",
               PURPLE),
        "BR": (0.78, 0.22, "Price $V_0$", GREEN),
    }
    for key, (x, y, txt, col) in nodes.items():
        ax.add_patch(FancyBboxPatch((x - 0.14, y - 0.08), 0.28, 0.16,
                                    boxstyle="round,pad=0.02",
                                    facecolor="white", edgecolor=col,
                                    linewidth=2))
        ax.text(x, y, txt, ha="center", va="center", color=col,
                fontsize=10, fontweight="bold")

    def arrow(a, b, label, color, dy=0.0, dx=0.0):
        xa, ya, *_ = nodes[a]
        xb, yb, *_ = nodes[b]
        ax.annotate("", xy=(xb, yb), xytext=(xa, ya),
                    arrowprops=dict(arrowstyle="->", color=color, lw=2.0,
                                    shrinkA=42, shrinkB=42))
        ax.text((xa + xb) / 2 + dx, (ya + yb) / 2 + dy, label,
                ha="center", va="center", fontsize=9, color=color,
                bbox=dict(boxstyle="round,pad=0.2", fc="white",
                          ec="none", alpha=0.9))

    arrow("TL", "BL", "$\\S 1.3$:\n$\\Delta=\\frac{V_u-V_d}{(u-d)S_0}$",
          ORANGE, dx=-0.04)
    arrow("BL", "BR", "$V_0 = \\Delta\\,S_0 + B$",
          ORANGE, dy=-0.04)
    arrow("TL", "TR", "$\\S 1.5$: take $\\tilde E$",
          PURPLE, dy=0.04)
    arrow("TR", "BR", "discount by $1+r$",
          PURPLE, dx=0.06)

    ax.text(0.5, 0.05,
            "Both routes yield the same $V_0$ — the diagram commutes.",
            ha="center", fontsize=11, color=NAVY, fontweight="bold")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("Two routes to the same price",
                 color=NAVY, fontweight="bold", fontsize=12)
    _save("ch01-commutative-diagram.png")


def fig_real_vs_rn_trees():
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.6))
    Su = RL_S0 * RL_U
    Sd = RL_S0 * RL_D
    _draw_tree(axes[0], RL_S0, Su, Sd,
               title="Real-world (RL): $p=0.55$  drift $=1.01$",
               p_up=0.55, p_dn=0.45)
    _draw_tree(axes[1], RL_S0, Su, Sd,
               title="Risk-neutral: $\\tilde p=0.60$  drift $=1.02$",
               p_up=0.60, p_dn=0.40)
    fig.suptitle("Same states, different probabilities",
                 color=NAVY, fontweight="bold", fontsize=12)
    _save("ch01-real-vs-rn-trees.png")


def fig_returns_bars():
    fig, ax = plt.subplots(figsize=(10.0, 5.0))
    # Labels and pairs of (real, RN) returns
    items = [
        ("Toy stock\n($p=0.7$)",    TOY_PTILDE_real_st := 0.7,
            (TOY_PTILDE_real_st * TOY_U + (1 - TOY_PTILDE_real_st) * TOY_D),
            1 + TOY_R),
        ("RL stock\n($p=0.55$)",    0.55,
            (0.55 * RL_U + 0.45 * RL_D),
            1 + RL_R),
        ("Bond Toy", None, 1 + TOY_R, 1 + TOY_R),
        ("Bond RL",  None, 1 + RL_R,  1 + RL_R),
        ("Toy call\n$K=5$",          None,
            (TOY_PTILDE_real_st * 3.0 + (1 - TOY_PTILDE_real_st) * 0.0) / 1.20,
            1 + TOY_R),  # RN price is 1.20, return = expected/price under RN = 1+r
    ]
    labels = [it[0] for it in items]
    real_returns = [it[2] for it in items]
    rn_returns = [it[3] for it in items]

    x = np.arange(len(labels))
    w = 0.35
    ax.bar(x - w / 2, real_returns, w, color=BLUE, edgecolor=NAVY,
           label="under real $p$")
    ax.bar(x + w / 2, rn_returns, w, color=ORANGE, edgecolor=NAVY,
           label="under RN $\\tilde p$")
    for xi, (rr, nr) in enumerate(zip(real_returns, rn_returns)):
        ax.text(xi - w / 2, rr + 0.02, f"{rr:.2f}", ha="center",
                fontsize=9, color=BLUE)
        ax.text(xi + w / 2, nr + 0.02, f"{nr:.2f}", ha="center",
                fontsize=9, color=ORANGE)

    ax.axhline(1.0, color=GREY, lw=0.8, ls="--")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=NAVY, fontsize=9)
    ax.set_ylabel("expected one-period gross return", color=NAVY)
    ax.set_title("Real vs risk-neutral expected returns",
                 color=NAVY, fontweight="bold")
    # Anchor legend in the gap above the second/third bar groups so
    # it never sits behind the tallest "Toy stock" bar value label.
    ax.legend(loc="upper center", fontsize=10,
              bbox_to_anchor=(0.38, 0.99), framealpha=0.95)
    ax.set_ylim(0, max(max(real_returns), max(rn_returns)) * 1.18)
    ax.grid(True, axis="y", alpha=0.3)
    _save("ch01-returns-bars.png")


def fig_payoff_strip():
    fig, axes = plt.subplots(2, 4, figsize=(13.0, 6.4))
    axes = axes.flatten()
    S = np.linspace(60, 140, 400)  # use RL scale around K=100
    K = 100.0

    panels = [
        ("Call $\\max(S-K,0)$", np.maximum(S - K, 0), BLUE),
        ("Put $\\max(K-S,0)$",  np.maximum(K - S, 0), ORANGE),
        ("Cash digital $1_{S \\geq K}$", (S >= K).astype(float), GREEN),
        ("Asset digital $S\\cdot 1_{S \\geq K}$", S * (S >= K).astype(float), PURPLE),
        ("Forward $S-K$", S - K, TEAL),
        ("Straddle $|S-K|$", np.abs(S - K), RED),
        ("Risk reversal $\\max(S-110,0)-\\max(90-S,0)$",
            np.maximum(S - 110, 0) - np.maximum(90 - S, 0), GOLD),
        ("Power $(S-K)^2/100$", (S - K) ** 2 / 100.0, NAVY),
    ]

    # Realistic binomial outcomes: S1 = 90 or 110
    Sup_RL = RL_S0 * RL_U
    Sdn_RL = RL_S0 * RL_D

    for ax, (title, V, col) in zip(axes, panels):
        ax.plot(S, V, color=col, lw=2.0)
        # Mark binomial points
        ax.axvline(Sup_RL, color=GREY, lw=0.6, ls=":")
        ax.axvline(Sdn_RL, color=GREY, lw=0.6, ls=":")
        # Evaluate V at the two points
        v_up = np.interp(Sup_RL, S, V)
        v_dn = np.interp(Sdn_RL, S, V)
        ax.scatter([Sup_RL, Sdn_RL], [v_up, v_dn], s=80,
                   color=[GREEN, RED], edgecolor=NAVY, zorder=5)
        ax.set_title(title, fontsize=9, color=NAVY)
        ax.set_xlabel("$S_1$", fontsize=8)
        ax.set_ylabel("$V_1$", fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

    fig.suptitle("Eight payoff diagrams — only two $S_1$ values are reached in the binomial model",
                 color=NAVY, fontweight="bold", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    _save("ch01-payoff-strip.png")


def fig_menagerie_3d():
    """Clean 2-D grouped bar chart (replaces the chunky 3-D version)."""
    derivs = [
        ("call",     BLUE),
        ("put",      ORANGE),
        ("digital",  GREEN),
        ("forward",  RED),
        ("straddle", PURPLE),
        ("power",    GOLD),
    ]

    def price(world, kind):
        if world == "Toy":
            S0, u, d, r, pt = TOY_S0, TOY_U, TOY_D, TOY_R, TOY_PTILDE
            K = 5.0
        else:
            S0, u, d, r, pt = RL_S0, RL_U, RL_D, RL_R, RL_PTILDE
            K = 100.0
        Su, Sd = u * S0, d * S0
        if kind == "call":
            Vu, Vd = max(Su - K, 0), max(Sd - K, 0)
        elif kind == "put":
            Vu, Vd = max(K - Su, 0), max(K - Sd, 0)
        elif kind == "digital":
            Vu, Vd = float(Su >= K), float(Sd >= K)
        elif kind == "forward":
            Vu, Vd = Su - K, Sd - K
        elif kind == "straddle":
            Vu, Vd = abs(Su - K), abs(Sd - K)
        else:  # power
            Vu, Vd = (Su - K) ** 2, (Sd - K) ** 2
        return (pt * Vu + (1 - pt) * Vd) / (1 + r)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), sharey=False)
    for ax, world, title in zip(
        axes, ("Toy", "RL"),
        ("Toy: $S_0{=}4, u{=}2, d{=}1/2, r{=}1/4, K{=}5$",
         "RL: $S_0{=}100, u{=}1.10, d{=}0.90, r{=}2\\%, K{=}100$")
    ):
        names = [d[0] for d in derivs]
        colors = [d[1] for d in derivs]
        vals = [price(world, k) for k, _ in derivs]
        bars = ax.bar(names, vals, color=colors, edgecolor=NAVY, linewidth=1.2)
        for bar, v in zip(bars, vals):
            label_y = bar.get_height()
            va = "bottom" if v >= 0 else "top"
            offset = max(abs(v) * 0.03, 0.4 if max(vals) > 10 else 0.04)
            ax.text(bar.get_x() + bar.get_width() / 2,
                    label_y + (offset if v >= 0 else -offset),
                    f"{v:.2f}", ha="center", va=va, fontsize=10,
                    color=NAVY, fontweight="bold")
        ax.axhline(0, color=GREY, lw=0.8)
        ax.set_title(title, fontsize=10.5, color=NAVY)
        ax.set_ylabel("price $V_0$")
        ax.tick_params(axis="x", labelrotation=18)
        ymin = min(0, min(vals))
        ymax = max(vals)
        pad = (ymax - ymin) * 0.18
        ax.set_ylim(ymin - pad, ymax + pad)

    fig.suptitle("Menagerie of one-period derivatives — six payoffs, two worlds",
                 fontsize=12, color=NAVY, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    _save("ch01-menagerie-3d.png")


def fig_parity_payoff():
    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    K = 100.0
    S = np.linspace(60, 140, 400)
    call = np.maximum(S - K, 0)
    put = np.maximum(K - S, 0)
    fwd = S - K

    ax.plot(S, call, color=BLUE, lw=2.2, label="long call $\\max(S-K,0)$")
    ax.plot(S, -put, color=ORANGE, lw=2.2,
            label="short put $-\\max(K-S,0)$")
    ax.plot(S, fwd, color=GREEN, lw=2.4, ls="--",
            label="forward $S-K$  (= sum)")

    # Two RL binomial outcomes
    for Sx, lbl, col in [(RL_S0 * RL_D, "$S_1=90$", RED),
                         (RL_S0 * RL_U, "$S_1=110$", GREEN)]:
        ax.axvline(Sx, color=GREY, lw=0.6, ls=":")
        c = max(Sx - K, 0)
        p = -max(K - Sx, 0)
        f = Sx - K
        ax.scatter([Sx, Sx, Sx], [c, p, f], s=80,
                   color=[BLUE, ORANGE, GREEN], edgecolor=NAVY, zorder=5)
        ax.text(Sx, 38, lbl, ha="center", color=col,
                fontsize=10, fontweight="bold")

    ax.axhline(0, color="lightgrey", lw=0.6)
    ax.set_xlabel("$S_1$", color=NAVY)
    ax.set_ylabel("payoff", color=NAVY)
    ax.set_title("Put-call parity in payoffs: call $-$ put $= S - K$",
                 color=NAVY, fontweight="bold")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)
    _save("ch01-parity-payoff.png")


def fig_dealer_pl():
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.6))
    # Toy call example: V0 = 1.20, Delta = 0.5, sold at 1.20.
    # If unhedged: dealer P/L in H = -V_u + V0*(1+r) = -3 + 1.5 = -1.5;
    #              in T = -0 + 1.5 = +1.5
    # Hedged: zero in both states.
    states = ["$H$", "$T$"]
    hedged = [0.0, 0.0]
    unhedged = [-1.5, 1.5]

    for ax, vals, title in [(axes[0], hedged, "Hedged dealer"),
                             (axes[1], unhedged, "Unhedged dealer")]:
        colors = [GREEN if v >= 0 else RED for v in vals]
        bars = ax.bar(states, vals, color=colors, edgecolor=NAVY, width=0.5)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2,
                    v + (0.1 if v >= 0 else -0.15),
                    f"{v:+.2f}", ha="center",
                    color=NAVY, fontsize=11, fontweight="bold")
        ax.axhline(0, color=GREY, lw=0.8)
        ax.set_title(title, color=NAVY, fontweight="bold")
        ax.set_ylim(-2.2, 2.2)
        ax.set_ylabel("P/L (dollars)", color=NAVY)
        ax.grid(True, axis="y", alpha=0.3)

    fig.suptitle("Dealer P/L: hedging eliminates randomness (Toy call)",
                 color=NAVY, fontweight="bold", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    _save("ch01-dealer-pl.png")


if __name__ == "__main__":
    fig_tree_skeleton_st()
    fig_tree_side_by_side()
    fig_noarb_zones()
    fig_arb_cashflow()
    fig_replication_wheel()
    fig_delta_plane_3d()
    fig_cost_decomposition()
    fig_tildep_vs_r()
    fig_call_surface_3d()
    fig_commutative_diagram()
    fig_real_vs_rn_trees()
    fig_returns_bars()
    fig_payoff_strip()
    fig_menagerie_3d()
    fig_parity_payoff()
    fig_dealer_pl()
    print("All Chapter 1 figures written.")
