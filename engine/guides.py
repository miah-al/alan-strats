"""
engine/guides.py — guide-article lookup across the platform and strategy plugins, headless.

The platform ships general education articles in ``docs/guides``. Strategy plugins ship one
article per strategy in their own guide directory (or a strategy's own ``guide_path``).
Anything that renders a guide — the service, the Dash pages while they exist — resolves a slug
through here, so neither side needs to know about the other.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

PLATFORM_GUIDE_DIR = Path(__file__).resolve().parent.parent / "docs" / "guides"


def _registry():
    from alan_trader.strategy_api import registry as R
    return R


def guide_dirs() -> list[Path]:
    """Platform directory first, then every plugin's."""
    return [PLATFORM_GUIDE_DIR] + _registry().guide_dirs()


def find_guide(slug: str) -> Optional[Path]:
    """Platform article first; otherwise whatever the registry knows — a
    strategy's own ``guide_path`` or a plugin-level guide directory."""
    p = PLATFORM_GUIDE_DIR / f"{slug}.md"
    if p.is_file():
        return p
    return _registry().find_guide(slug)


def load_guide(slug: str) -> str:
    p = find_guide(slug)
    if p is not None:
        return p.read_text(encoding="utf-8")
    return f"*No guide article found for `{slug}`.*"


def all_guide_slugs() -> list[str]:
    """Every article slug available, de-duplicated, sorted."""
    R = _registry()
    seen: set[str] = set(R.guide_slugs_from_metadata())
    for d in guide_dirs():
        if d.is_dir():
            for p in d.glob("*.md"):
                if not p.name.startswith("_"):
                    seen.add(p.stem)
    return sorted(seen)
