"""The fill rule for NDX / SPX option orders (paper/fill_rule.py) and the order book's use of it. No database."""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from paper import fill_rule as FR  # noqa: E402

DAY = _dt.date(2026, 10, 22)


def leg(cp, side, k, bid, ask, ratio=1, expiry=DAY):
    return FR.RuleLeg(type=cp, side=side, ratio=ratio, strike=k, expiry=expiry, bid=bid, ask=ask)


def test_index_and_fees():
    assert [FR.index_of(u) for u in ("NDX", "ndxp", "SPX", "SPXW", "QQQ", "", None)] == \
        ["NDX", "NDX", "SPX", "SPX", None, None, None]
    assert FR.fee_per_contract("SPX", True) * 2 == pytest.approx(3.45)       # a spread opened
    assert FR.fee_per_contract("NDX", True) * 2 == pytest.approx(2.77)
    assert FR.fee_per_contract("SPX", False) == pytest.approx(0.725) and FR.fee_per_contract(None, True) is None


def test_ndx_vertical_gives_up_half_a_point_or_a_quarter_of_its_half_width():
    # 10/22 11:09:30, the desk sold the 29100/29125 calls: 80.5 x 87.0 and 70.2 x 75.1 -> mid credit 11.10, hw 5.7
    prices, net, mid = FR.leg_prices("NDX", [leg("call", "sell", 29100, 80.5, 87.0), leg("call", "buy", 29125, 70.2, 75.1)])
    assert mid == pytest.approx(-11.10) and net == pytest.approx(-11.10 + 5.7 / 4)
    assert prices[0] < 83.75 and prices[1] > 72.65 and prices[1] - prices[0] == pytest.approx(net)
    # a tight quote: the 0.5 floor
    _, net, mid = FR.leg_prices("NDX", [leg("call", "sell", 29500, 3.0, 3.6), leg("call", "buy", 29525, 1.9, 2.3)])
    assert net == pytest.approx(mid + 0.5)


def test_never_through_the_bid_and_spx_gives_up_a_nickel():
    _, net, mid = FR.leg_prices("SPX", [leg("call", "sell", 7730, 2.00, 2.10), leg("call", "buy", 7740, 0.85, 0.95)])
    assert net == pytest.approx(mid + 0.05)
    # a locked quote (the backfill's prints): nothing to give up
    _, net, mid = FR.leg_prices("SPX", [leg("call", "sell", 7735, 3.0, 3.0), leg("call", "buy", 7745, 1.75, 1.75)])
    assert net == pytest.approx(mid) == pytest.approx(-1.25)
    # NDX 0.5 on a quote only 0.3 wide: capped at the vertical's bid
    _, net, _ = FR.leg_prices("NDX", [leg("call", "sell", 29900, 1.0, 1.1), leg("call", "buy", 29925, 0.5, 0.7)])
    assert net == pytest.approx(0.7 - 1.0)


def test_a_vertical_is_kept_inside_what_it_can_be_worth():
    # 10/22 15:55, buying back the 29150/29175 call spread: the legs' mids (0.625, 1.15) made it a 0.525 CREDIT
    prices, net, mid = FR.leg_prices("NDX", [leg("call", "buy", 29150, 0.20, 1.05), leg("call", "sell", 29175, 0.05, 2.25)])
    assert mid == pytest.approx(-0.525) and net == pytest.approx(0.5)           # worth >= 0, plus the 0.5
    assert 0.20 <= prices[0] <= 1.05 and 0.05 <= prices[1] <= 2.25


def test_condor_is_two_verticals_and_a_ratio_pairs_unit_by_unit():
    condor = [leg("call", "sell", 7775, 5.1, 5.2), leg("call", "buy", 7785, 3.1, 3.2),
              leg("put", "sell", 7700, 4.4, 4.5), leg("put", "buy", 7680, 2.1, 2.15)]
    _, net, mid = FR.leg_prices("SPX", condor)
    assert net == pytest.approx(mid + 0.10)
    # a 1x2 put ratio: one pair plus one unpaired short (it gives up the same, capped at its own half-width)
    ratio = [leg("put", "buy", 7700, 4.4, 4.6), leg("put", "sell", 7690, 2.9, 3.1, ratio=2)]
    _, net, mid = FR.leg_prices("SPX", ratio)
    assert net == pytest.approx(mid + 0.05 + 0.05)


def test_order_book_prices_index_orders_by_the_rule_and_others_at_the_mid():
    from api.services import orders as O
    body = {"account": "paper", "underlying": "NDX", "order_type": "market",
            "legs": [{"type": "call", "strike": 29100, "expiry": "2099-01-02", "side": "sell", "quantity": 2},
                     {"type": "call", "strike": 29125, "expiry": "2099-01-02", "side": "buy", "quantity": 2}]}
    order = O.parse_order(body)
    quotes = [{"bid": 80.5, "ask": 87.0, "mid": 83.75}, {"bid": 70.2, "ask": 75.1, "mid": 72.65}]
    prices, net = O.rule_prices(order, quotes)
    assert net == pytest.approx(-11.10 + 1.425) and order.ratios == [1, 1]
    assert O.rule_prices(order, [quotes[0], {"bid": None, "ask": 75.1, "mid": None}]) is None
    other = O.parse_order({**body, "underlying": "QQQ",
                           "legs": [{**l, "strike": 500 + i} for i, l in enumerate(body["legs"])]})
    assert O.rule_prices(other, quotes) is None
    assert O._fee(order, order.legs[0], True) == pytest.approx(1.385) and O._fee(other, other.legs[0], True) is None
