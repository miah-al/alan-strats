"""
The signal popup must survive a missing grid value.

Grid cells are display strings, not numbers: a missing value is the em-dash
"—", which is truthy, so `float(row.get("Price") or 0)` raises and blanks the
whole modal. Every grid value must be parsed through `_num()`.
"""

import pytest

from alan_trader.app.pages.strategies.format import _num


@pytest.mark.parametrize("missing", ["—", "", "N/A", None, "-"])
def test_missing_values_fall_back_to_the_default(missing):
    assert _num(missing) == 0.0
    assert _num(missing, 12.5) == 12.5


def test_the_em_dash_is_the_case_that_used_to_raise():
    with pytest.raises(ValueError):
        float("—")
    assert _num("—") == 0.0


@pytest.mark.parametrize("value, expected", [
    ("$590.25", 590.25),
    ("42.5%", 42.5),
    ("+1.25", 1.25),
    ("1,234.5", 1234.5),
    ("2.3×", 2.3),
    (17, 17.0),
    (0.42, 0.42),
])
def test_display_formatting_is_stripped(value, expected):
    assert _num(value) == pytest.approx(expected)


@pytest.mark.parametrize("missing", ["—", "", "N/A", None, "-"])
def test_generic_signal_popup_survives_a_missing_price(missing):
    """`_build_signal_body` IS the callback: a raise blanks the modal with no
    message. The generic body (used by any strategy without a bespoke view)
    must render for a row whose Price cell is missing."""
    from alan_trader.app.pages.strategies.modals import _build_signal_body

    row = {
        "Ticker": "SPY", "Price": missing, "Score": 55, "Status": "Partial",
        "IVR": "0.42", "VIX": "16.0", "_slug": "__no_such_strategy__",
    }
    assert _build_signal_body(row) is not None


def test_no_unguarded_price_parses_remain():
    """Guards against the anti-pattern being reintroduced."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / "app" / "pages" / "strategies" / "modals.py").read_text(encoding="utf-8")
    assert 'float(row.get("Price")' not in src, (
        "a raw float() on a grid Price cell is back; route it through _num()"
    )
