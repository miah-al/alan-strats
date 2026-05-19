"""
Lulu HARDCOVER WITH DUST JACKET cover for Binomial Option Pricing.

Adapted from docs/guide/_build_lulu_cover.py with the geometry Lulu publishes
for our exact page count.

Single-page PDF, total 20.875" x 9.75", with 5 panels:

    bleed | back flap | fold | back cover | spine | front cover | fold | front flap | bleed
    0.125 |   3.25    | 0.25 |    6.25    | 1.125|    6.25     | 0.25 |    3.25   | 0.125
    ------------------------------------------------------------------------------- = 20.875"

Vertical: 0.375 top bleed + 9.0 content + 0.375 bottom bleed = 9.75"

The spine width (1.125") is Lulu's published value for the page count this
script is invoked with (388 pages). If you change paper / page count, ask
Lulu's template generator for the correct spine and update SPINE below.

Run:
    python docs/binomial-option-pricing/_build_lulu_cover.py --pages 388
"""
from __future__ import annotations

import argparse
import os
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.image import imread

BOOK = os.path.dirname(os.path.abspath(__file__))
COVER_FRONT = os.path.join(BOOK, "figures", "cover.png")
OUT_DIR = os.path.join(BOOK, "pdf")
os.makedirs(OUT_DIR, exist_ok=True)

# Lulu Hardcover-with-Dust-Jacket fixed geometry for 6x9 trim
TOTAL_W       = 20.875
TOTAL_H       = 9.75
OUTER_BLEED_X = 0.125
OUTER_BLEED_Y = 0.375
FLAP_W        = 3.25
FLAP_FOLD     = 0.25
COVER_W       = 6.25
SPINE         = 1.125          # Lulu published for 388 pages (hardcover/DJ)

# Palette
NAVY      = "#0b1d3a"
NAVY_DARK = "#06122a"
GOLD      = "#fbbf24"
GOLD_DIM  = "#b88a1a"
TEXT      = "#e8ecf3"
TEXT_DIM  = "#8b94a8"
RULE      = "#2a3b5e"

AUTHOR       = "Alan"
TITLE_LINE_1 = "Binomial"
TITLE_LINE_2 = "Option Pricing"
SUBTITLE     = "From a Coin Flip to Black–Scholes"
NAMEPLATE    = "BINOMIAL OPTION PRICING"
TAGLINE      = "A quant-curious tour. No calculus required."

FRONT_FLAP_BLURB = (
    "Eight chapters take the reader from a single coin toss to the Black–"
    "Scholes formula, using only finite sums, the Central Limit Theorem "
    "stated as a fact, and a standard-normal CDF table. No derivatives, "
    "no integrals, no measure theory beyond what is genuinely needed.\n\n"
    "Chapter 0 is a math primer with a Stirling-based proof sketch of "
    "de Moivre–Laplace. Chapters 1–6 build the binomial machine: single-"
    "period replication, multi-period trees, optimal stopping for American "
    "options, the reflection principle for path-dependents, and a short-rate "
    "tree for bonds and callable bonds. Chapter 7 — the capstone — derives "
    "Black–Scholes as the Cox–Ross–Rubinstein limit via the CLT alone.\n\n"
    "Every concept is anchored by a worked numerical example with named "
    "numbers a reader can verify by hand."
)

BACK_FLAP_BIO = (
    "Alan is a derivatives practitioner. This book is the route he wishes "
    "had existed when he first wanted to understand binomial option "
    "pricing without first absorbing measure theory and stochastic "
    "calculus.\n\n"
    "He lives in the United States."
)

INSIDE_LINES = [
    ("Ch 0",  "Math primer (no calculus)"),
    ("Ch 1",  "Single-period binomial"),
    ("Ch 2",  "Multi-period tree + Greeks"),
    ("Ch 3",  "Coin-toss probability space"),
    ("Ch 4",  "American options & optimal stopping"),
    ("Ch 5",  "Random walks, reflection principle"),
    ("Ch 6",  "Bonds, caplets, callable bonds"),
    ("Ch 7",  "Binomial → Black–Scholes (CLT)"),
]

HERO_EQUATION = (
    r"$C_0 \;=\; S_0\,\Phi(d_1) \;-\; K e^{-rT}\,\Phi(d_2)$"
)


def panel_x() -> dict:
    x = OUTER_BLEED_X
    bflap_l, bflap_r = x, x + FLAP_W;       x = bflap_r + FLAP_FOLD
    back_l,  back_r  = x, x + COVER_W;      x = back_r
    spine_l, spine_r = x, x + SPINE;        x = spine_r
    front_l, front_r = x, x + COVER_W;      x = front_r + FLAP_FOLD
    fflap_l, fflap_r = x, x + FLAP_W
    return dict(
        bflap=(bflap_l, bflap_r),
        back=(back_l, back_r),
        spine=(spine_l, spine_r),
        front=(front_l, front_r),
        fflap=(fflap_l, fflap_r),
    )


def fill_panel(ax, x_l, x_r, y_b, y_t, color):
    ax.add_patch(Rectangle((x_l, y_b), x_r - x_l, y_t - y_b,
                           facecolor=color, edgecolor="none", zorder=1))


def draw_front(ax, x_l, x_r, y_b, y_t):
    if os.path.exists(COVER_FRONT):
        ax.imshow(imread(COVER_FRONT),
                  extent=(x_l, x_r, y_b, y_t),
                  aspect="auto", zorder=1)
    else:
        fill_panel(ax, x_l, x_r, y_b, y_t, NAVY)


def draw_spine(ax, x_l, x_r, y_b, y_t):
    spine_w = x_r - x_l
    cx = 0.5 * (x_l + x_r)
    fill_panel(ax, x_l, x_r, y_b, y_t, NAVY_DARK)

    cap_h = 0.04
    inset = 0.5
    for yy in (y_t - inset, y_b + inset - cap_h):
        ax.add_patch(Rectangle((x_l + spine_w * 0.2, yy),
                               spine_w * 0.6, cap_h,
                               facecolor=GOLD, edgecolor="none", zorder=3))

    title_font = max(13, min(22, int(spine_w * 14)))
    sub_font   = max(9,  min(12, int(spine_w * 8)))
    auth_font  = max(10, min(14, int(spine_w * 10)))

    ax.text(cx, y_b + (y_t - y_b) * 0.66,
            "Binomial Option Pricing",
            color=TEXT, fontsize=title_font, fontweight="bold",
            ha="center", va="center", rotation=90, zorder=4, family="serif")
    ax.text(cx, y_b + (y_t - y_b) * 0.42,
            "FROM A COIN FLIP TO BLACK–SCHOLES",
            color=GOLD_DIM, fontsize=sub_font,
            ha="center", va="center", rotation=90, zorder=4, family="serif")
    ax.text(cx, y_b + (y_t - y_b) * 0.18,
            AUTHOR.upper(),
            color=GOLD, fontsize=auth_font, fontweight="bold",
            ha="center", va="center", rotation=90, zorder=4, family="serif")


def draw_back_cover(ax, x_l, x_r, y_b, y_t):
    w = x_r - x_l
    h = y_t - y_b
    cx = 0.5 * (x_l + x_r)
    fill_panel(ax, x_l, x_r, y_b, y_t, NAVY)

    margin = 0.55

    # Header gold rule + nameplate
    rule_y = y_t - 0.85
    ax.add_patch(Rectangle((x_l + margin, rule_y),
                           0.55, 0.025, facecolor=GOLD,
                           edgecolor="none", zorder=4))
    ax.text(x_l + margin, rule_y - 0.20, NAMEPLATE,
            color=GOLD, fontsize=10, fontweight="bold",
            ha="left", va="top", zorder=4, family="serif")

    # Title block
    ax.text(x_l + margin, y_t - 1.55, TITLE_LINE_1,
            color=TEXT, fontsize=20, fontweight="bold",
            ha="left", va="top", zorder=4, family="serif")
    ax.text(x_l + margin, y_t - 2.00, TITLE_LINE_2,
            color=TEXT, fontsize=20, fontweight="bold",
            ha="left", va="top", zorder=4, family="serif")
    ax.text(x_l + margin, y_t - 2.40, SUBTITLE,
            color=TEXT_DIM, fontsize=10, fontstyle="italic",
            ha="left", va="top", zorder=4, family="serif")

    # Hero equation
    hero_y = y_t - 3.30
    ax.text(cx, hero_y, HERO_EQUATION,
            color=TEXT, fontsize=14, ha="center", va="center", zorder=4)
    ax.text(cx, hero_y - 0.45,
            "the Black–Scholes call price, derived in Chapter 7",
            color=GOLD_DIM, fontsize=8.5, fontstyle="italic",
            ha="center", va="center", zorder=4, family="serif")

    # Separator
    ax.add_patch(Rectangle((x_l + margin + 0.3, hero_y - 0.95),
                           w - 2 * (margin + 0.3), 0.012,
                           facecolor=RULE, edgecolor="none", zorder=4))

    # INSIDE list (2 columns)
    toc_top = hero_y - 1.30
    ax.text(x_l + margin, toc_top, "INSIDE",
            color=GOLD, fontsize=10, fontweight="bold",
            ha="left", va="top", zorder=4, family="serif")
    col_w = (w - 2 * margin) * 0.55
    for k, (label, desc) in enumerate(INSIDE_LINES):
        col = k % 2
        row = k // 2
        x = x_l + margin + col * col_w
        y = toc_top - 0.30 - row * 0.26
        ax.text(x, y, label,
                color=GOLD, fontsize=8.5, fontweight="bold",
                ha="left", va="top", zorder=4, family="serif")
        ax.text(x + 0.60, y, desc,
                color=TEXT, fontsize=8.5,
                ha="left", va="top", zorder=4, family="serif")

    # Tagline + author byline (bottom)
    by_y = y_b + 0.80
    ax.text(x_l + margin, by_y, AUTHOR.upper(),
            color=TEXT, fontsize=11, fontweight="bold",
            ha="left", va="bottom", zorder=4, family="serif")
    ax.text(x_l + margin, by_y - 0.22, TAGLINE,
            color=TEXT_DIM, fontsize=7.5, fontstyle="italic",
            ha="left", va="bottom", zorder=4, family="serif")
    ax.add_patch(Rectangle((x_l + margin, by_y - 0.32),
                           0.55, 0.018,
                           facecolor=GOLD, edgecolor="none", zorder=4))


def draw_flap(ax, x_l, x_r, y_b, y_t, heading, body):
    fill_panel(ax, x_l, x_r, y_b, y_t, NAVY)
    w = x_r - x_l
    margin = 0.35
    ax.add_patch(Rectangle((x_l + margin, y_t - 0.60),
                           0.40, 0.025, facecolor=GOLD,
                           edgecolor="none", zorder=4))
    ax.text(x_l + margin, y_t - 0.80, heading,
            color=GOLD, fontsize=9, fontweight="bold",
            ha="left", va="top", zorder=4, family="serif")
    wrapped = textwrap.fill(body, width=34, break_long_words=False,
                            replace_whitespace=False)
    ax.text(x_l + margin, y_t - 1.20, wrapped,
            color=TEXT, fontsize=8.5,
            ha="left", va="top", zorder=4, family="serif",
            linespacing=1.5)


def build_cover(pages: int, out_path: str) -> None:
    px = panel_x()
    fig = plt.figure(figsize=(TOTAL_W, TOTAL_H), dpi=300, facecolor=NAVY)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, TOTAL_W)
    ax.set_ylim(0, TOTAL_H)
    ax.set_axis_off()

    y_b = OUTER_BLEED_Y
    y_t = TOTAL_H - OUTER_BLEED_Y

    # Background fill so outer bleed is solid navy
    fill_panel(ax, 0, TOTAL_W, 0, TOTAL_H, NAVY)

    # Panels
    draw_flap(ax, *px["bflap"], y_b, y_t,
              heading="ABOUT THE AUTHOR", body=BACK_FLAP_BIO)
    draw_back_cover(ax, *px["back"], y_b, y_t)
    draw_spine(ax, *px["spine"], y_b, y_t)
    draw_front(ax, *px["front"], y_b, y_t)
    draw_flap(ax, *px["fflap"], y_b, y_t,
              heading="ABOUT THIS BOOK", body=FRONT_FLAP_BLURB)

    fig.savefig(out_path, dpi=300, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"wrote {out_path}")
    print(f"  total dims   : {TOTAL_W:.3f}\" x {TOTAL_H:.3f}\"  (Lulu HC w/ DJ for {pages} pp)")
    print(f"  spine width  : {SPINE:.3f}\"")
    print(f"  panel layout : bleed | flap {FLAP_W} | fold {FLAP_FOLD} | back {COVER_W} | spine {SPINE} | front {COVER_W} | fold {FLAP_FOLD} | flap {FLAP_W} | bleed")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pages", type=int, default=388)
    p.add_argument("--out", default=os.path.join(OUT_DIR, "Binomial-Cover.pdf"))
    args = p.parse_args()
    build_cover(args.pages, args.out)


if __name__ == "__main__":
    main()
