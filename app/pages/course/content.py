"""
app/pages/course/content.py — chapter discovery + markdown processing.

Pure logic, no Dash/Flask imports. Everything here is about *finding* the
guide's chapters under docs/guide/ and *transforming* their markdown (figure
paths, math fences) for the live view. The print-view variants live in
print_view.py.
"""
from __future__ import annotations

import re
from pathlib import Path

# docs/guide/ lives at the repo root: this file is app/pages/course/content.py
_GUIDE_DIR = Path(__file__).parent.parent.parent.parent / "docs" / "guide"
_FIG_DIR   = _GUIDE_DIR / "figures"


# ── Part grouping (chapter number ranges) ─────────────────────────────────────
_PARTS: list[tuple[str, range]] = [
    ("Prerequisites",                                  range(0, 1)),    # Chapter 0
    ("Part I — Discrete-Time Models",                  range(1, 3)),    # Chapter 1–2
    ("Part II — Continuous-Time Models",               range(3, 6)),    # Chapter 3–5
    ("Part III — Equity Derivatives",                  range(6, 10)),   # Chapter 6–9
    ("Part IV — Stochastic Volatility",                range(10, 11)),  # Chapter 10
    ("Part V — Calibration & Interest-Rate Models",    range(11, 15)),  # Chapter 11–14
    ("Part VI — Capstone",                             range(15, 16)),  # Chapter 15
    ("Bibliography",                                   range(16, 17)),  # Chapter 16
]

_CHAPTER_STEM_RE = re.compile(r"^Chapter-(\d+)-(.+)$")


def parse_chapter_stem(stem: str) -> tuple[int, str] | None:
    """`Chapter-13-Rate-Derivative-Applications` → (13, 'Rate Derivative Applications')."""
    m = _CHAPTER_STEM_RE.match(stem)
    if not m:
        return None
    return int(m.group(1)), m.group(2).replace("-", " ")


def chapter_options() -> list[dict]:
    """Flat list of chapter options (value = filename stem)."""
    raw: list[tuple[int, str, str]] = []
    for p in _GUIDE_DIR.glob("Chapter-*.md"):
        parsed = parse_chapter_stem(p.stem)
        if parsed is None:
            continue
        num, title = parsed
        raw.append((num, title, p.stem))
    raw.sort(key=lambda t: t[0])
    return [{"label": f"Chapter {num} — {title}", "value": stem, "num": num}
            for num, title, stem in raw]


def grouped_chapter_options() -> list[tuple[str, list[dict]]]:
    """Return [(part_name, [options])] grouped per Part I–VI."""
    all_opts = chapter_options()
    groups: list[tuple[str, list[dict]]] = []
    for part_name, nums in _PARTS:
        part_opts = [{"label": o["label"], "value": o["value"]}
                     for o in all_opts if o["num"] in nums]
        if part_opts:
            groups.append((part_name, part_opts))
    return groups


def figure_count() -> int:
    return len(list(_FIG_DIR.glob("*.png"))) if _FIG_DIR.is_dir() else 0


def rewrite_figure_paths(markdown: str) -> str:
    """Rewrite `figures/chNN-foo.png` → `/guide-figure/...` Flask route so the
    browser fetches+caches each PNG once instead of re-encoding base64 per nav."""
    return re.sub(
        r"\]\(figures/([^)\s]+\.(?:png|jpe?g|svg))\)",
        lambda m: f"](/guide-figure/{m.group(1)})",
        markdown,
    )


def convert_math_fences(markdown: str) -> str:
    """Rewrite ```math ... ``` fences to $$ ... $$ so dcc.Markdown's MathJax
    renders them (it handles $/$$ but not fenced math blocks)."""
    return re.sub(
        r"```math\s*\n(.+?)\n```",
        lambda m: f"\n\n$$\n{m.group(1)}\n$$\n\n",
        markdown,
        flags=re.DOTALL,
    )
