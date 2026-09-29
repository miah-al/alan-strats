"""The Backtest tab starts from what the live runner runs (engine/strategy_backtest.py): the strategy's own parameters,
then its LIVE_PARAMS, written in each slider's terms; and the "Read with care" panel says how the fills were priced."""
from __future__ import annotations

from types import SimpleNamespace

from engine import strategy_backtest as B


def test_slider_codes_read_from_the_label():
    assert B.slider_codes("Fill model (0 maker, 1 mid, 2 taker)") == {"maker": 0, "mid": 1, "taker": 2}
    assert B.slider_codes("Price source (0 model, 1 market prints)") == {"model": 0, "market": 1}
    assert B.slider_codes("Take-profit (pts)") == {}


def test_live_values_are_the_params_then_the_live_pricing():
    st = SimpleNamespace(get_params=lambda: {"fill_model": "taker", "width": 100.0}, LIVE_PARAMS={"fill_model": "mid"})
    assert B.live_values(st) == {"fill_model": "mid", "width": 100.0}


def test_specs_take_the_live_runners_values_in_their_own_terms():
    live = {"width": 100.0, "counter_trend": True, "stop_pts": 0.0, "fill_model": "mid", "pricing": "market", "target_pts": 10.0}
    width = B.synced_spec({"key": "width", "label": "Width", "min": 25, "max": 50, "default": 50.0}, live)
    assert width["default"] == 100.0 and width["max"] == 100.0                  # the range widens to hold it
    assert B.synced_spec({"key": "counter_trend", "label": "Counter-trend", "default": 0}, live)["default"] == 1
    assert B.synced_spec({"key": "stop_pts", "label": "Stop", "default": 60.0}, live)["default"] == 0.0
    fm = B.synced_spec({"key": "fill_model", "label": "Fill model (0 maker, 1 mid, 2 taker)", "default": 2}, live)
    assert fm["default"] == 1 and "live runner" in fm["help"]
    assert B.synced_spec({"key": "pricing", "label": "Price source (0 model, 1 market prints)", "default": 1}, live)["default"] == 1
    same = {"key": "target_pts", "label": "Target", "default": 10.0}
    assert B.synced_spec(same, live) is same                                     # nothing to change
    odd = {"key": "fill_model", "label": "Fill model", "default": 2}             # a name the slider cannot say
    assert B.synced_spec(odd, live) is odd


def test_the_panel_says_how_the_fills_were_priced():
    base = {"metrics": {"num_trades": 40}, "coverage": 1.0, "window_days": 100, "span_days": 100, "live_params": {"fill_model": 1, "cross_cost_model": "moneyness"},
            "live_params_named": {"fill_model": "mid", "cross_cost_model": "moneyness"}}
    like = B.performance_warnings({**base, "params": {"fill_model": 1, "cross_cost_model": "moneyness"}})
    assert any(n.startswith("Priced like the live runner") for n in like)
    off = B.performance_warnings({**base, "params": {"fill_model": 2, "cross_cost_model": "moneyness"}})
    assert any(n.startswith("Not priced like the live runner") and "fill_model is 2 here" in n for n in off)


def test_a_run_that_is_not_the_live_strategy_says_so():
    live_defaults = {"width": 100.0, "counter_trend": 1, "stop_pts": 0.0, "fill_model": 1}
    perf = {"metrics": {"num_trades": 40}, "coverage": 1.0, "window_days": 100, "span_days": 100,
            "live_params": {"fill_model": 1}, "live_params_named": {"fill_model": "mid"}, "live_defaults": live_defaults,
            "params": {"width": 50.0, "counter_trend": 0, "stop_pts": 60.0, "fill_model": 2}}
    notes = B.performance_warnings(perf)
    rules = next(n for n in notes if n.startswith("Not the strategy the live runner trades"))
    assert "width 50.0 (live 100.0)" in rules and "counter_trend 0 (live 1)" in rules and "stop_pts 60.0 (live 0.0)" in rules
    assert "fill_model" not in rules                                            # pricing has its own line
    assert any(n.startswith("Not priced like the live runner") for n in notes)
    same = B.performance_warnings({**perf, "params": {"width": 100, "counter_trend": 1, "stop_pts": 0, "fill_model": 1}})
    assert any(n.startswith("Priced like the live runner") for n in same)
    assert not any(n.startswith("Not the strategy") for n in same)
