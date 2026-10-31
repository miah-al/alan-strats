"""
Strategy registry — plugin discovery + the merged metadata table + factories.

Discovery order (all sources are merged, duplicates by plugin name dropped):

  1. entry points in the ``alan_trader.strategies`` group — each resolves to a
     ``StrategyPlugin``, a module with a ``PLUGIN`` attribute, or a zero-arg
     callable returning one;
  2. packages listed in ``ALAN_TRADER_STRATEGY_PACKAGES`` (comma-separated
     importable names, each exposing ``PLUGIN``);
  3. the default package ``alan_trader_strategies`` when it is importable.

Set ``ALAN_TRADER_STRATEGY_PACKAGES=none`` to disable every source — that is
the "strategy-free" configuration the platform must run under.

A plugin that fails to import is logged and skipped; the platform keeps
running with whatever else loaded. Two plugins providing the same slug is an
error, because the slug is the key everything else hangs off.
"""
from __future__ import annotations

import importlib
import logging
import os
from importlib import metadata as _im
from pathlib import Path
from typing import Callable, Optional

from alan_trader.strategy_api.base import BaseStrategy, StubStrategy
from alan_trader.strategy_api.plugin import StrategyPlugin
from alan_trader.strategy_api.ui import StrategyUI

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "alan_trader.strategies"
ENV_PACKAGES = "ALAN_TRADER_STRATEGY_PACKAGES"
DEFAULT_PACKAGES: tuple[str, ...] = ("alan_trader_strategies",)

#: slug -> metadata, merged across every loaded plugin. Populated by load();
#: mutated in place on reload() so existing references stay valid.
STRATEGY_METADATA: dict[str, dict] = {}

_PLUGINS: list[StrategyPlugin] = []
_SLUG_PLUGIN: dict[str, StrategyPlugin] = {}
_UI_CACHE: dict[str, StrategyUI] = {}
_LOADED = False


# ── Discovery ─────────────────────────────────────────────────────────────────

def _coerce(obj, origin: str) -> Optional[StrategyPlugin]:
    if isinstance(obj, StrategyPlugin):
        return obj
    if hasattr(obj, "PLUGIN"):
        return _coerce(getattr(obj, "PLUGIN"), origin)
    if callable(obj):
        return _coerce(obj(), origin)
    logger.warning("strategy plugin source %s did not yield a StrategyPlugin (%r)", origin, type(obj))
    return None


def _from_package(name: str) -> Optional[StrategyPlugin]:
    try:
        mod = importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name and (exc.name == name or name.startswith(exc.name + ".")):
            return None            # not installed — silently skip
        logger.warning("strategy package %s failed to import: %s", name, exc)
        return None
    except Exception as exc:       # pragma: no cover - defensive
        logger.warning("strategy package %s failed to import: %s", name, exc)
        return None
    return _coerce(mod, name)


def _sources() -> list[tuple[str, Callable[[], Optional[StrategyPlugin]]]]:
    env = os.environ.get(ENV_PACKAGES)
    if env is not None and env.strip().lower() == "none":
        return []

    out: list[tuple[str, Callable[[], Optional[StrategyPlugin]]]] = []

    try:
        eps = _im.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:              # pragma: no cover - very old importlib.metadata
        eps = _im.entry_points().get(ENTRY_POINT_GROUP, [])
    for ep in eps:
        out.append((f"entry-point:{ep.name}", lambda ep=ep: _coerce(ep.load(), ep.name)))

    names: list[str] = []
    if env:
        names.extend(n.strip() for n in env.split(",") if n.strip())
    else:
        names.extend(DEFAULT_PACKAGES)
    for n in names:
        out.append((f"package:{n}", lambda n=n: _from_package(n)))
    return out


def load(force: bool = False) -> None:
    """Discover plugins and (re)build the merged registry."""
    global _LOADED
    if _LOADED and not force:
        return
    plugins: list[StrategyPlugin] = []
    seen: set[str] = set()
    for origin, fn in _sources():
        try:
            plugin = fn()
        except Exception as exc:
            logger.warning("strategy plugin %s failed to load: %s", origin, exc)
            continue
        if plugin is None or plugin.name in seen:
            continue
        seen.add(plugin.name)
        plugins.append(plugin)
    _install(plugins)
    _LOADED = True


def _install(plugins: list[StrategyPlugin]) -> None:
    merged: dict[str, dict] = {}
    owner: dict[str, StrategyPlugin] = {}
    for p in plugins:
        for slug, meta in p.metadata.items():
            if slug in merged:
                raise ValueError(
                    f"strategy slug {slug!r} is provided by both "
                    f"{owner[slug].name!r} and {p.name!r}")
            merged[slug] = meta
            owner[slug] = p
    _PLUGINS[:] = plugins
    _SLUG_PLUGIN.clear(); _SLUG_PLUGIN.update(owner)
    STRATEGY_METADATA.clear(); STRATEGY_METADATA.update(merged)
    _UI_CACHE.clear()


def reload() -> None:
    load(force=True)


def register_plugin(plugin: StrategyPlugin) -> None:
    """Programmatic registration (tests, notebooks). Replaces a plugin with the
    same name."""
    load()
    others = [p for p in _PLUGINS if p.name != plugin.name]
    _install(others + [plugin])


def plugins() -> list[StrategyPlugin]:
    load()
    return list(_PLUGINS)


def plugin_for(slug: str) -> Optional[StrategyPlugin]:
    load()
    return _SLUG_PLUGIN.get(slug)


# ── Factories ─────────────────────────────────────────────────────────────────

def get_strategy(slug: str) -> BaseStrategy:
    """
    Lazy-load and return an instantiated strategy by slug.
    Returns StubStrategy if not implemented or class_path is empty.
    """
    load()
    meta = STRATEGY_METADATA.get(slug)
    if meta is None:
        raise KeyError(f"Unknown strategy slug: {slug!r}")

    class_path = meta.get("class_path", "")
    if not class_path or meta.get("status") == "stub":
        return StubStrategy(slug, meta)

    module_path, class_name = class_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls()
    except (ImportError, AttributeError) as e:
        logger.warning(f"Could not load {class_path}: {e} — using stub")
        return StubStrategy(slug, meta)


def get_all_strategies() -> dict[str, BaseStrategy]:
    """Return dict of slug → strategy instance for all registered strategies."""
    load()
    return {slug: get_strategy(slug) for slug in STRATEGY_METADATA}


def get_active_strategies() -> dict[str, BaseStrategy]:
    """Return only strategies with status=active."""
    load()
    return {
        slug: get_strategy(slug)
        for slug, meta in STRATEGY_METADATA.items()
        if meta.get("status") == "active"
    }


def registry_dataframe() -> "pd.DataFrame":
    """Return a DataFrame of all strategy metadata (for dashboard table)."""
    import pandas as pd
    load()
    rows = []
    for slug, meta in STRATEGY_METADATA.items():
        rows.append({
            "slug": slug,
            "Name": meta["display_name"],
            "Type": meta["type"].upper(),
            "Status": meta["status"].capitalize(),
            "Asset Class": meta.get("asset_class", ""),
            "Typical Hold (days)": meta.get("typical_holding_days", ""),
            "Target Sharpe": meta.get("target_sharpe", ""),
            "Description": meta.get("description", ""),
        })
    if not rows:
        return pd.DataFrame(columns=["Name", "Type", "Status", "Asset Class",
                                     "Typical Hold (days)", "Target Sharpe", "Description"])
    return pd.DataFrame(rows).set_index("slug")


# ── UI lookups ────────────────────────────────────────────────────────────────

def ui_slugs() -> list[str]:
    """Slugs the Strategies page lists, in plugin order."""
    load()
    return [s for s, m in STRATEGY_METADATA.items() if m.get("ui_visible")]


def ui_entries() -> list[dict]:
    """[{label, value, type}] for the selector, ordered by ``ui_order`` then
    plugin order."""
    load()
    items = [(m.get("ui_order", 10**9), i, s, m)
             for i, (s, m) in enumerate(STRATEGY_METADATA.items()) if m.get("ui_visible")]
    items.sort(key=lambda t: (t[0], t[1]))
    return [{"label": (m.get("ui_label") or m.get("display_name") or s),
             "value": s, "type": m.get("type", "rule")}
            for _, _, s, m in items]


def get_ui(slug: str) -> StrategyUI:
    """The strategy's UI hooks (cached). Falls back to the generic StrategyUI
    when the plugin declares none or the declared module fails to import."""
    load()
    if slug in _UI_CACHE:
        return _UI_CACHE[slug]
    meta = STRATEGY_METADATA.get(slug, {})
    ui: StrategyUI
    path = meta.get("ui")
    if path:
        try:
            mod = importlib.import_module(path)
            cls = getattr(mod, "UI", None)
            if cls is None or not issubclass(cls, StrategyUI):
                raise AttributeError(f"{path} does not define class UI(StrategyUI)")
            ui = cls(slug, meta)
        except Exception as exc:
            logger.warning("UI module for %s failed (%s) — using generic UI", slug, exc)
            ui = StrategyUI(slug, meta)
    else:
        ui = StrategyUI(slug, meta)
    _UI_CACHE[slug] = ui
    return ui


def review_status(slug: str) -> str:
    load()
    return STRATEGY_METADATA.get(slug, {}).get("review_status", "reviewing")


def score(slug: str):
    load()
    return STRATEGY_METADATA.get(slug, {}).get("score")


# ── Plugin resources ──────────────────────────────────────────────────────────

def guide_dirs() -> list[Path]:
    load()
    return [p.guide_dir for p in _PLUGINS if p.guide_dir]


def docs_dirs() -> list[Path]:
    load()
    return [p.docs_dir for p in _PLUGINS if p.docs_dir]


def find_guide(slug: str) -> Optional[Path]:
    """A strategy may carry its own article (metadata ``guide_path``);
    otherwise look through every plugin's guide directory."""
    load()
    own = STRATEGY_METADATA.get(slug, {}).get("guide_path")
    if own and Path(own).is_file():
        return Path(own)
    for d in guide_dirs():
        p = d / f"{slug}.md"
        if p.is_file():
            return p
    return None


def guide_slugs_from_metadata() -> list[str]:
    """Slugs whose metadata carries a ``guide_path`` that exists."""
    load()
    return [s for s, m in STRATEGY_METADATA.items()
            if m.get("guide_path") and Path(m["guide_path"]).is_file()]


def guide_chart_module(article_slug: str) -> Optional[str]:
    load()
    own = STRATEGY_METADATA.get(article_slug, {}).get("guide_chart")
    if own:
        return own
    for p in _PLUGINS:
        if article_slug in p.guide_charts:
            return p.guide_charts[article_slug]
    return None


def tests_dir_for(slug: str) -> Optional[Path]:
    load()
    own = STRATEGY_METADATA.get(slug, {}).get("tests_dir")
    if own:
        return Path(own)
    p = plugin_for(slug)
    return p.tests_dir if p else None


def root_for(slug: str) -> Optional[Path]:
    p = plugin_for(slug)
    return (p.root or (p.tests_dir.parent if p.tests_dir else None)) if p else None


def model_dir_for(slug: str) -> Optional[Path]:
    p = plugin_for(slug)
    return p.model_dir if p else None


# Populate at import so `from ...registry import STRATEGY_METADATA` is usable.
load()
