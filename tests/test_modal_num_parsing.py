"""
Screener-grid cells are display strings, and a missing value is the em-dash "—".

The signal popup compared those cells against thresholds via
`float(str(v) or 0)`, which cannot work: `str("—")` is truthy so the `or 0`
never fires and float() raises ValueError. Any row with a missing VIX, Price or
Score took the entire popup down — and the Score parse sits in the shared tail
of `_build_signal_body`, so it affected every strategy.
"""

import pytest

from alan_trader.app.pages.strategies.format import _num


@pytest.mark.parametrize("missing", ["—", "-", "–", "", "   ", "N/A", "n/a",
                                     "None", "nan", None])
def test_missing_values_fall_back_to_the_default(missing):
    assert _num(missing) == 0.0
    assert _num(missing, 12.5) == 12.5


def test_the_em_dash_is_the_case_that_used_to_raise():
    """`float(str("—") or 0)` raises ValueError — this must not."""
    assert _num("—") == 0.0


@pytest.mark.parametrize("value,expected", [
    ("18.4", 18.4),
    ("$5.25", 5.25),
    ("62.5%", 62.5),
    ("+3.10", 3.10),
    ("$1,250.75", 1250.75),
    ("1.8x", 1.8),
    ("  24.0  ", 24.0),
    ("-7.25", -7.25),
    ("$-3.50", -3.50),
])
def test_display_formatting_is_stripped(value, expected):
    assert _num(value) == pytest.approx(expected)


@pytest.mark.parametrize("value,expected", [
    (42, 42.0),
    (3.5, 3.5),
    (0, 0.0),
])
def test_real_numbers_pass_through(value, expected):
    assert _num(value) == pytest.approx(expected)


def test_booleans_are_not_treated_as_numbers():
    """bool is an int subclass; treating True as 1.0 would be a silent lie."""
    assert _num(True) == 0.0
    assert _num(False) == 0.0


def test_garbage_falls_back_rather_than_raising():
    assert _num("not a number") == 0.0
    assert _num("$$$") == 0.0
    assert _num(object()) == 0.0


def test_threshold_comparison_is_safe_for_every_grid_value():
    """The exact shape of the code that was crashing."""
    for cell in ["—", "18.4", "$5.25", "62.5%", None, "", "N/A"]:
        assert isinstance(_num(cell) > 25, bool)
