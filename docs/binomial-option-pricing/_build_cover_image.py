"""
Front-cover image generator for Binomial Option Pricing.

Run: python docs/binomial-option-pricing/_build_cover_image.py

Outputs figures/cover.png — the FRONT panel only.
The full Lulu wrap (back + spine + front + flaps + bleed) is built by
_build_lulu_cover.py which consumes this PNG.

The cover features a binomial tree growing into a smooth bell curve — the
book's whole arc in one image.
"""
from __future__ import annotations

import math
import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Rectangle
from scipy.stats import norm

OUT = os.path.join(os.path.dirname(__file__), "figures", "cover.png")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# Palette (matches the guide's NAVY/GOLD but slightly warmer)
NAVY      = "#0b1d3a"
NAVY_DARK = "#06122a"
GOLD      = "#fbbf24"
GOLD_DIM  = "#b88a1a"
TEXT      = "#e8ecf3"
TEXT_DIM  = "#8b94a8"
EDGE      = "#1a2a4a"


def main() -> None:
    # Front cover panel: 6.25 in wide x 9.0 in tall (matches Lulu wrap geometry)
    fig = plt.figure(figsize=(6.25, 9.0), dpi=300, facecolor=NAVY)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 6.25)
    ax.set_ylim(0, 9.0)
    ax.set_axis_off()

    # Background — radial-ish gradient via stacked rectangles
    for i, frac in enumerate(np.linspace(0, 1, 60)):
        col = (
            0.043 + (0.025 - 0.043) * frac,
            0.114 + (0.071 - 0.114) * frac,
            0.227 + (0.165 - 0.227) * frac,
        )
        ax.add_patch(Rectangle((0, 9 * frac), 6.25, 9 / 60,
                               facecolor=col, edgecolor="none", zorder=0))

    # Top gold rule
    ax.add_patch(Rectangle((0.55, 8.05), 0.85, 0.04,
                           facecolor=GOLD, edgecolor="none", zorder=3))
    ax.text(0.55, 8.27, "A QUANT-CURIOUS BOOK",
            color=GOLD_DIM, fontsize=8.5, fontweight="bold",
            ha="left", va="bottom", family="serif", zorder=3)

    # Title
    ax.text(0.55, 7.40, "Binomial",
            color=TEXT, fontsize=44, fontweight="bold",
            ha="left", va="top", family="serif", zorder=3)
    ax.text(0.55, 6.60, "Option Pricing",
            color=TEXT, fontsize=44, fontweight="bold",
            ha="left", va="top", family="serif", zorder=3)

    # Subtitle
    ax.text(0.55, 5.80, "From a Coin Flip to",
            color=GOLD, fontsize=18, fontstyle="italic",
            ha="left", va="top", family="serif", zorder=3)
    ax.text(0.55, 5.40, "Black–Scholes",
            color=GOLD, fontsize=18, fontstyle="italic",
            ha="left", va="top", family="serif", zorder=3)

    # Tagline / no-calculus badge
    ax.text(0.55, 4.85, "No calculus required.",
            color=TEXT_DIM, fontsize=11.5, fontstyle="italic",
            ha="left", va="top", family="serif", zorder=3)

    # ── Centerpiece: binomial tree dissolving into a bell curve ────────────
    # Draw a 6-level binomial lattice on the left, then a Φ-like bell to the
    # right of it, with a thin gold arrow joining them.
    tree_left   = 0.85
    tree_right  = 3.20
    tree_top    = 4.35
    tree_bottom = 1.55
    n_levels    = 6
    dx = (tree_right - tree_left) / n_levels
    dy = (tree_top - tree_bottom) / n_levels
    # Centred lattice
    for n in range(n_levels + 1):
        for k in range(n + 1):
            cx = tree_left + n * dx
            cy = (tree_top + tree_bottom) / 2 + (k - n / 2) * dy
            # Edges to children
            if n < n_levels:
                for dk in (0, 1):
                    cx2 = tree_left + (n + 1) * dx
                    cy2 = (tree_top + tree_bottom) / 2 + (k + dk - (n + 1) / 2) * dy
                    ax.plot([cx, cx2], [cy, cy2],
                            color=GOLD_DIM, lw=0.6, alpha=0.65, zorder=2)
            ax.add_patch(Circle((cx, cy), 0.08,
                                facecolor=GOLD, edgecolor=GOLD_DIM,
                                lw=0.5, zorder=4))

    # Bell curve on the right
    bell_x_left  = 3.55
    bell_x_right = 5.95
    bell_y_base  = (tree_top + tree_bottom) / 2 - (tree_top - tree_bottom) / 2
    bell_height  = (tree_top - tree_bottom) * 0.65
    xs = np.linspace(-3.2, 3.2, 200)
    ys = norm.pdf(xs)
    ys_norm = ys / ys.max()
    bx = bell_x_left + (xs - xs.min()) / (xs.max() - xs.min()) * (bell_x_right - bell_x_left)
    by = bell_y_base + ys_norm * bell_height
    # Filled bell
    ax.fill_between(bx, bell_y_base, by, color=GOLD, alpha=0.25, zorder=2)
    ax.plot(bx, by, color=GOLD, lw=2.0, zorder=3)
    # Vertical centre line at z=0
    midx = bell_x_left + (0 - xs.min()) / (xs.max() - xs.min()) * (bell_x_right - bell_x_left)
    ax.plot([midx, midx], [bell_y_base, bell_y_base + bell_height * 1.05],
            color=GOLD_DIM, lw=0.8, linestyle=":", zorder=3)

    # Arrow from tree to bell
    ax.annotate(
        "", xy=(bell_x_left - 0.10, (tree_top + tree_bottom) / 2),
        xytext=(tree_right + 0.10, (tree_top + tree_bottom) / 2),
        arrowprops=dict(arrowstyle="-|>", color=TEXT_DIM, lw=1.4,
                        mutation_scale=18),
        zorder=3,
    )
    ax.text((tree_right + bell_x_left) / 2,
            (tree_top + tree_bottom) / 2 - 0.30,
            r"$n \to \infty$",
            color=TEXT_DIM, fontsize=10, ha="center", va="top",
            family="serif", zorder=4)

    # Hero formula at the bottom
    ax.text(3.125, 1.10,
            r"$C_0 \;=\; S_0\,\Phi(d_1) \;-\; K e^{-rT}\,\Phi(d_2)$",
            color=TEXT, fontsize=14, ha="center", va="center",
            family="serif", zorder=4)
    ax.text(3.125, 0.78,
            "the Black–Scholes call price, derived in Chapter 7",
            color=GOLD_DIM, fontsize=8.5, fontstyle="italic",
            ha="center", va="center", family="serif", zorder=4)

    # Author byline
    ax.add_patch(Rectangle((0.55, 0.35), 0.55, 0.018,
                           facecolor=GOLD, edgecolor="none", zorder=4))
    ax.text(0.55, 0.20, "ALAN",
            color=TEXT, fontsize=14, fontweight="bold",
            ha="left", va="bottom", family="serif", zorder=4)

    fig.savefig(OUT, dpi=300, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
