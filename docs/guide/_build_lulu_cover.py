"""
Lulu HARDCOVER WITH DUST JACKET cover for 6x9 trim.

Single-page PDF, total 21.25" x 9.75", with 5 panels left-to-right:

    bleed | back flap | fold | back cover | spine | front cover | fold | front flap | bleed
    0.125 |   3.25    | 0.25 |    6.25    | 1.5  |    6.25     | 0.25 |    3.25   | 0.125
    ------------------------------------------------------------------------------- = 21.25"

Vertical: 0.375 top bleed + 9.0 content + 0.375 bottom bleed = 9.75"

The spine width (1.5") is fixed by Lulu's published spec for the page count
this script is invoked with; if you change paper / page count, ask Lulu's
template generator for the correct spine and edit the SPINE constant below.

Run:
    python docs/guide/_build_lulu_cover.py --pages 552
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

GUIDE = os.path.dirname(os.path.abspath(__file__))
COVER_FRONT = os.path.join(GUIDE, "figures", "cover.png")
OUT_DIR = os.path.join(GUIDE, "pdf")
os.makedirs(OUT_DIR, exist_ok=True)

# Lulu Hardcover-with-Dust-Jacket fixed geometry for 6x9 trim
TOTAL_W = 21.25
TOTAL_H = 9.75
OUTER_BLEED_X = 0.125     # left/right outer bleed
OUTER_BLEED_Y = 0.375     # top/bottom (jacket folds over the book + bleed)
FLAP_W = 3.25
FLAP_FOLD = 0.25
COVER_W = 6.25            # back/front panels (slightly > 6" trim for fold-around)
SPINE = 1.5               # Lulu's published spine for 552 pages here

# Palette — sampled from the front cover.png
NAVY = "#0b1d3a"
NAVY_DARK = "#06122a"
GOLD = "#fbbf24"
GOLD_DIM = "#b88a1a"
TEXT = "#e8ecf3"
TEXT_DIM = "#8b94a8"
RULE = "#2a3b5e"

AUTHOR = "Alan"
TITLE_LINE_1 = "Arbitrage Pricing"
TITLE_LINE_2 = "& Derivatives"
NAMEPLATE = "QUANT COURSE"
TAGLINE = "A self-study companion for the graduate derivatives canon"

FRONT_FLAP_BLURB = (
    "Sixteen chapters take the reader from a probability refresher to the "
    "trading desk. No-arbitrage pricing is built from replication alone, "
    "then extended through stochastic calculus, the Black-Scholes PDE, "
    "the full Greek atlas, Monte Carlo, Heston stochastic volatility, "
    "calibration, short-rate models, caps and swaptions, and a capstone "
    "on VaR, expected shortfall, and coherent risk.\n\n"
    "Every concept lives next to the figure that visualises it. Real-world "
    "case studies thread through the chapters: Black Monday 1987, LTCM, "
    "Volmageddon 2018, negative WTI, SVB, the UK LDI mini-budget, and the "
    "LIBOR-to-SOFR transition.\n\n"
    "Written for a self-study reader comfortable with undergraduate "
    "probability and real analysis who wants a single coherent path from "
    "first principles to senior-quant practice."
)

BACK_FLAP_BIO = (
    "Alan is a derivatives practitioner and self-study writer. This guide "
    "distils the path he wishes had existed when he first sat for an "
    "interview at a derivatives desk — one coherent route from the "
    "probability axioms to the risk-system Greeks, with the same care "
    "given to the math and the institutional context that surrounds it.\n\n"
    "He lives in the United States."
)

BACK_COVER_QUOTE = (
    '"The math is built once, then applied everywhere — replication, '
    'measure change, Feynman-Kac, Heston, VaR. The same machine through '
    'every chapter."'
)

HERO_EQUATION = (
    r"$\frac{\partial g}{\partial t}"
    r"\,+\,\frac{1}{2}\sigma^{2} S^{2}\,\frac{\partial^{2} g}{\partial S^{2}}"
    r"\,+\,rS\,\frac{\partial g}{\partial S}"
    r"\,-\,r\,g \,=\, 0$"
)


def panel_x() -> dict:
    """Compute x-ranges of each panel."""
    x = OUTER_BLEED_X
    bflap_l, bflap_r = x, x + FLAP_W;          x = bflap_r + FLAP_FOLD
    back_l,  back_r  = x, x + COVER_W;         x = back_r
    spine_l, spine_r = x, x + SPINE;           x = spine_r
    front_l, front_r = x, x + COVER_W;         x = front_r + FLAP_FOLD
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

    # Gold accent caps top and bottom
    cap_h = 0.04
    inset = 0.5
    for yy in (y_t - inset, y_b + inset - cap_h):
        ax.add_patch(Rectangle((x_l + spine_w * 0.2, yy),
                               spine_w * 0.6, cap_h,
                               facecolor=GOLD, edgecolor="none", zorder=3))

    # Title reads bottom-to-top (English book convention)
    title_font = max(13, min(22, int(spine_w * 14)))
    sub_font = max(9, min(12, int(spine_w * 8)))
    auth_font = max(10, min(14, int(spine_w * 10)))

    ax.text(cx, y_b + (y_t - y_b) * 0.66,
            "Arbitrage Pricing & Derivatives",
            color=TEXT, fontsize=title_font, fontweight="bold",
            ha="center", va="center", rotation=90, zorder=4, family="serif")
    ax.text(cx, y_b + (y_t - y_b) * 0.42,
            "QUANT COURSE",
            color=GOLD_DIM, fontsize=sub_font,
            ha="center", va="center", rotation=90, zorder=4, family="serif")
    ax.text(cx, y_b + (y_t - y_b) * 0.18,
            AUTHOR.upper(),
            color=GOLD, fontsize=auth_font, fontweight="bold",
            ha="center", va="center", rotation=90, zorder=4, family="serif")


def draw_back_cover(ax, x_l, x_r, y_b, y_t):
    """Back cover: title, hero equation, INSIDE parts list, byline, barcode."""
    w = x_r - x_l
    h = y_t - y_b
    cx = 0.5 * (x_l + x_r)
    fill_panel(ax, x_l, x_r, y_b, y_t, NAVY)

    margin = 0.55

    # Header: thin gold rule + nameplate
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

    # Hero equation as visual centerpiece (between title and INSIDE list)
    hero_y = y_t - 3.25
    ax.text(cx, hero_y, HERO_EQUATION,
            color=TEXT, fontsize=14, ha="center", va="center", zorder=4)
    ax.text(cx, hero_y - 0.50, "the Black-Scholes PDE",
            color=GOLD_DIM, fontsize=8.5, fontstyle="italic",
            ha="center", va="center", zorder=4, family="serif")

    # Thin separator
    ax.add_patch(Rectangle((x_l + margin + 0.3, hero_y - 0.95),
                           w - 2 * (margin + 0.3), 0.012,
                           facecolor=RULE, edgecolor="none", zorder=4))

    # INSIDE parts list
    toc_top = hero_y - 1.30
    ax.text(x_l + margin, toc_top, "INSIDE",
            color=GOLD, fontsize=10, fontweight="bold",
            ha="left", va="top", zorder=4, family="serif")
    inside_lines = [
        ("Part I",   "Discrete-time models, FTAP"),
        ("Part II",  "Stochastic calculus, Feynman-Kac"),
        ("Part III", "Greeks, Monte Carlo, Black PDE"),
        ("Part IV",  "Heston stochastic volatility"),
        ("Part V",   "Short rates, swaptions, VaR/ES"),
    ]
    for k, (label, desc) in enumerate(inside_lines):
        y = toc_top - 0.28 - k * 0.22
        ax.text(x_l + margin, y, label,
                color=GOLD, fontsize=8.5, fontweight="bold",
                ha="left", va="top", zorder=4, family="serif")
        ax.text(x_l + margin + 0.80, y, desc,
                color=TEXT, fontsize=8.5,
                ha="left", va="top", zorder=4, family="serif")

    # Author byline
    by_y = y_b + 0.70
    ax.text(x_l + margin, by_y, AUTHOR.upper(),
            color=TEXT, fontsize=11, fontweight="bold",
            ha="left", va="bottom", zorder=4, family="serif")
    ax.text(x_l + margin, by_y - 0.22, TAGLINE,
            color=TEXT_DIM, fontsize=7.5, fontstyle="italic",
            ha="left", va="bottom", zorder=4, family="serif")
    ax.add_patch(Rectangle((x_l + margin, by_y - 0.32),
                           0.55, 0.018,
                           facecolor=GOLD, edgecolor="none", zorder=4))

    # ISBN barcode well (bottom-right)
    bar_w, bar_h = 1.7, 0.95
    bar_x = x_r - margin - bar_w
    bar_y = y_b + 0.50
    ax.add_patch(Rectangle((bar_x, bar_y), bar_w, bar_h,
                           facecolor="white", edgecolor="white", zorder=5))
    ax.text(bar_x + bar_w / 2, bar_y + bar_h / 2,
            "ISBN\nbarcode",
            color="#9aa3b2", fontsize=8,
            ha="center", va="center", zorder=6, family="serif")


def draw_flap(ax, x_l, x_r, y_b, y_t, heading, body):
    """Generic flap renderer: heading + wrapped body, small margins."""
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

    # Background fill across the entire jacket so outer bleed is solid colour
    fill_panel(ax, 0, TOTAL_W, 0, TOTAL_H, NAVY)

    # Back flap (leftmost interior panel)
    draw_flap(ax, *px["bflap"], y_b, y_t,
              heading="ABOUT THE AUTHOR", body=BACK_FLAP_BIO)
    # Back cover
    draw_back_cover(ax, *px["back"], y_b, y_t)
    # Spine
    draw_spine(ax, *px["spine"], y_b, y_t)
    # Front cover (uses cover.png)
    draw_front(ax, *px["front"], y_b, y_t)
    # Front flap (rightmost interior panel)
    draw_flap(ax, *px["fflap"], y_b, y_t,
              heading="ABOUT THIS BOOK", body=FRONT_FLAP_BLURB)

    fig.savefig(out_path, dpi=300, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"wrote {out_path}")
    print(f"  total dims  : {TOTAL_W:.3f}\" wide x {TOTAL_H:.3f}\" tall")
    print(f"  spine width : {SPINE:.3f}\"  (Lulu published for {pages} pages)")
    print(f"  panel layout: bleed | flap {FLAP_W} | fold {FLAP_FOLD} | back {COVER_W} | spine {SPINE} | front {COVER_W} | fold {FLAP_FOLD} | flap {FLAP_W} | bleed")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pages", type=int, default=552)
    p.add_argument("--out", default=os.path.join(OUT_DIR, "Quant-Guide-Cover.pdf"))
    args = p.parse_args()
    build_cover(args.pages, args.out)


if __name__ == "__main__":
    main()
