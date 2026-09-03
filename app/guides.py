"""
app/guides.py — guide-article lookup across the platform and strategy plugins.

The platform ships general education articles in ``app/guide_articles``.
Strategy plugins ship one article per strategy in their own guide directory.
Pages that render guides resolve a slug through here so neither side needs to
know about the other.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

PLATFORM_GUIDE_DIR = Path(__file__).resolve().parent / "guide_articles"

# Interactive charts for the platform's own (generic) articles. Plugins declare
# their own map on their StrategyPlugin; strategy_api.registry merges lookups.
PLATFORM_GUIDE_CHARTS: dict[str, str] = {
    "iron_condor":      "app.guide_charts.iron_condor_charts",
    "bear_call_spread": "app.guide_charts.bull_put_spread_charts",
    "momentum_factor":  "app.guide_charts.momentum_factor_charts",
}


def guide_dirs() -> list[Path]:
    """Platform directory first, then every plugin's."""
    from alan_trader.strategy_api import registry as R
    return [PLATFORM_GUIDE_DIR] + R.guide_dirs()


def find_guide(slug: str) -> Optional[Path]:
    """Platform article first; otherwise whatever the registry knows — a
    strategy's own ``guide_path`` or a plugin-level guide directory."""
    p = PLATFORM_GUIDE_DIR / f"{slug}.md"
    if p.is_file():
        return p
    from alan_trader.strategy_api import registry as R
    return R.find_guide(slug)


def load_guide(slug: str) -> str:
    p = find_guide(slug)
    if p is not None:
        return p.read_text(encoding="utf-8")
    return f"*No guide article found for `{slug}`.*"


def all_guide_slugs() -> list[str]:
    """Every article slug available, de-duplicated, sorted."""
    from alan_trader.strategy_api import registry as R
    seen: set[str] = set(R.guide_slugs_from_metadata())
    for d in guide_dirs():
        if d.is_dir():
            for p in d.glob("*.md"):
                if not p.name.startswith("_"):
                    seen.add(p.stem)
    return sorted(seen)


def chart_module(slug: str) -> Optional[str]:
    from alan_trader.strategy_api import registry as R
    return PLATFORM_GUIDE_CHARTS.get(slug) or R.guide_chart_module(slug)
