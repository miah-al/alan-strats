"""
Registry wiring invariants.

Every strategy the UI offers must actually resolve to its real implementation.
`earnings_straddle` and `wheel_strategy` were both shipped with
`status: "stub"` and an empty `class_path` despite having complete, working
implementations — so `get_strategy()` handed back a `StubStrategy` whose
`backtest()` raises NotImplementedError, and `is_ready()` reported False.
"""

import importlib

import pytest

from alan_trader.strategies.base import BaseStrategy, StubStrategy
from alan_trader.strategies.registry import STRATEGY_METADATA, get_strategy
from alan_trader.app.pages.strategies.registry import (
    _STRATEGIES_RULES, _STRATEGIES_AI,
)


UI_SLUGS = [e["value"] for e in _STRATEGIES_RULES + _STRATEGIES_AI]


def test_ui_exposes_strategies():
    assert len(UI_SLUGS) >= 33
    assert len(UI_SLUGS) == len(set(UI_SLUGS)), "duplicate slug in the UI lists"


@pytest.mark.parametrize("slug", UI_SLUGS)
def test_ui_wired_slug_is_registered(slug):
    assert slug in STRATEGY_METADATA, f"{slug} is offered by the UI but not registered"


@pytest.mark.parametrize("slug", UI_SLUGS)
def test_ui_wired_slug_does_not_resolve_to_a_stub(slug):
    """A user-selectable strategy that resolves to StubStrategy cannot backtest."""
    strategy = get_strategy(slug)
    assert not isinstance(strategy, StubStrategy), (
        f"{slug} resolves to StubStrategy — check its 'status' and 'class_path' "
        f"in STRATEGY_METADATA"
    )
    assert isinstance(strategy, BaseStrategy)


@pytest.mark.parametrize("slug", UI_SLUGS)
def test_ui_wired_slug_is_ready(slug):
    assert get_strategy(slug).is_ready(), f"{slug} is not ACTIVE"


@pytest.mark.parametrize("slug", UI_SLUGS)
def test_class_path_matches_a_real_class(slug):
    """A class_path that no longer resolves silently degrades to a stub."""
    class_path = STRATEGY_METADATA[slug].get("class_path", "")
    assert class_path, f"{slug} has an empty class_path"
    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    assert hasattr(module, class_name), f"{class_path} does not exist"


@pytest.mark.parametrize("slug", UI_SLUGS)
def test_registry_status_agrees_with_the_class(slug):
    """
    The class declares its own status. If the registry says one thing and the
    implementation another, one of them is a lie — this is exactly how
    earnings_straddle and wheel_strategy drifted.
    """
    strategy = get_strategy(slug)
    assert STRATEGY_METADATA[slug]["status"] == strategy.status.value, (
        f"{slug}: registry says {STRATEGY_METADATA[slug]['status']!r} but the "
        f"class declares {strategy.status.value!r}"
    )


@pytest.mark.parametrize("slug", UI_SLUGS)
def test_registry_type_agrees_with_the_class(slug):
    """The AI/rules split drives how the UI groups and ranks strategies."""
    strategy = get_strategy(slug)
    assert STRATEGY_METADATA[slug]["type"] == strategy.strategy_type.value, (
        f"{slug}: registry says type={STRATEGY_METADATA[slug]['type']!r} but the "
        f"class declares {strategy.strategy_type.value!r}"
    )


@pytest.mark.parametrize("slug", UI_SLUGS)
def test_backtest_is_not_the_stub_implementation(slug):
    """Guards against a real class that still inherits StubStrategy.backtest."""
    strategy = get_strategy(slug)
    assert strategy.backtest.__qualname__.split(".")[0] != "StubStrategy"
