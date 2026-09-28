"""
app/guides.py — the Dash side of guide lookup.

The lookup itself (platform articles in ``docs/guides`` plus every plugin's) is headless and
lives in ``engine/guides.py``; this module re-exports it for the pages and keeps the one
Dash-specific piece, the interactive-chart modules for the platform's own articles.
"""
from __future__ import annotations

from typing import Optional

from engine.guides import (  # noqa: F401  (re-exported for the pages)
    PLATFORM_GUIDE_DIR, all_guide_slugs, find_guide, guide_dirs, load_guide,
)

# Interactive charts for the platform's own (generic) articles. Plugins declare
# their own map on their StrategyPlugin; strategy_api.registry merges lookups.
PLATFORM_GUIDE_CHARTS: dict[str, str] = {
    "iron_condor":      "app.guide_charts.iron_condor_charts",
    "bear_call_spread": "app.guide_charts.bull_put_spread_charts",
    "momentum_factor":  "app.guide_charts.momentum_factor_charts",
}


def chart_module(slug: str) -> Optional[str]:
    from alan_trader.strategy_api import registry as R
    return PLATFORM_GUIDE_CHARTS.get(slug) or R.guide_chart_module(slug)
