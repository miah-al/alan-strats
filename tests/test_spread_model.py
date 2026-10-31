"""The replay's spread model (paper/spread_model.py): calibrated on the live quotes, wider for legs deeper in the
money, built like the live derived quote (the two legs added), and never narrower than what the runners actually
saw at their fills. No database."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from paper.spread_model import (FlatSpread, LiveSpread, MEASURED_CROSSING_PTS, is_conservative, label_of,  # noqa: E402
                                leg_moneyness, make_spread)

# (spot, kind, k_low, k_high, spread value, half of the derived bid/ask the runner logged) at the ndx_0dte_tasty fills
# of 2026-09-23/24 (events.csv) and the ndx_gamma_walls entry of 2026-09-25 (call 30625/30675: 11.80 / 17.70)
LOGGED_FILLS = [
    (30480.76, "put", 30475, 30525, 27.05, 7.15), (30488.10, "put", 30475, 30525, 24.05, 6.75),
    (30438.93, "put", 30475, 30525, 38.70, 11.10), (30438.93, "put", 30450, 30500, 32.50, 8.60),
    (30424.58, "put", 30450, 30500, 37.65, 9.75), (30424.58, "put", 30425, 30475, 29.25, 6.75),
    (30395.32, "put", 30425, 30475, 38.90, 10.90), (30395.32, "put", 30400, 30450, 30.50, 6.70),
    (30371.58, "put", 30400, 30450, 36.05, 8.95), (30371.58, "put", 30375, 30425, 30.55, 7.65),
    (30406.05, "put", 30375, 30425, 19.90, 3.70), (30456.59, "put", 30375, 30425, 13.55, 2.95),
    (30251.36, "put", 30250, 30300, 25.85, 5.45), (30221.51, "put", 30250, 30300, 32.05, 8.85),
    (30221.51, "put", 30225, 30275, 26.00, 8.60), (30243.33, "put", 30225, 30275, 12.30, 6.30),
    (30573.0, "call", 30625, 30675, 14.75, 2.95),
]


def test_leg_curve_widens_into_the_money_and_the_vertical_adds_its_legs():
    m = LiveSpread()
    legs = [m.leg(x) for x in (-100, -25, 0, 10, 25, 40, 60, 80, 120)]
    assert all(b >= a for a, b in zip(legs, legs[1:])) and legs[0] == 1.75 and legs[-1] == 7.25
    assert m.leg(0) == 2.0 and m.leg(25) == 4.25 and m.leg(32.5) == pytest.approx(5.0)
    assert leg_moneyness("put", 30250, 30300, 30251.36) == pytest.approx((48.64, -1.36))
    assert leg_moneyness("call", 30625, 30675, 30573.0) == pytest.approx((-52.0, -102.0))
    # the 2026-09-24 11:00 entry: long put 48.6 in the money (6.18), short put at the money (1.99)
    assert m(25.85, 50.0, 30251.36, 30250, 30300, "put") == pytest.approx(6.18 + 1.986, abs=0.02)
    # a 100-wide on the same spot sits deeper: wider, but not twice as wide
    h50 = m(25.0, 50.0, 30250.0, 30225, 30275, "put"); h100 = m(50.0, 100.0, 30250.0, 30200, 30300, "put")
    assert h50 < h100 < 2 * h50
    # the bid never goes negative
    assert m(0.8, 50.0, 30500.0, 30250, 30300, "put") == pytest.approx(0.8)
    assert LiveSpread(scale=1.5).leg(25) == pytest.approx(6.375)


def test_model_is_never_narrower_than_the_logged_fills_and_at_most_half_again_as_wide():
    m = LiveSpread()
    ratios = [m(v, kh - kl, S, kl, kh, kind) / half for S, kind, kl, kh, v, half in LOGGED_FILLS]
    assert min(ratios) >= 0.99, ratios
    assert max(ratios) <= 1.55, ratios
    assert m(14.75, 50.0, 30573.0, 30625, 30675, "call") == pytest.approx(3.5)     # the walls quote: logged 2.95


def test_value_fallback_without_spot():
    m = LiveSpread()
    hs = [m.by_value(f * 50.0, 50.0) for f in (0.0, 0.1, 0.3, 0.5, 0.7, 1.0)]
    assert all(b >= a for a, b in zip(hs, hs[1:])) and hs[0] == 1.4 and hs[-1] == 11.0
    assert m(25.0, 50.0) == pytest.approx(6.0) and m(50.0, 100.0) == pytest.approx(6.0 * 2 ** 0.5)
    assert m(22.5, 50.0) == pytest.approx(5.125)


def test_flat_and_factory_and_labels():
    assert make_spread(None).name == "live" and make_spread("live").name == "live" and make_spread(0.5).h == 0.5
    assert make_spread("flat").h == 0.5 and make_spread("3").h == 3.0 and make_spread(FlatSpread(2.0)).h == 2.0
    assert FlatSpread(0.5)(30.0, 50.0, 30250.0, 30250, 30300, "put") == 0.5
    assert "live spread model" in label_of(LiveSpread()) and "0.5" in label_of(FlatSpread(0.5))
    assert is_conservative(LiveSpread()) and not is_conservative(LiveSpread(scale=0.5))
    assert not is_conservative(FlatSpread(0.5)) and is_conservative(FlatSpread(MEASURED_CROSSING_PTS))
