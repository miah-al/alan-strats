"""
The real-order path (api/services/real_orders.py, scripts/real_order.py): the only way to the owner's REAL account.

No tastytrade calls: a fake session and a fake Account. The scans prove that nothing else imports the module, reads
the order login or places an order, and that the paper order book still refuses live orders.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.services import real_orders as R  # noqa: E402

AT_1301 = dt.datetime(2026, 11, 10, 13, 1, 30)
STRAT = "strat_a"          # a made-up name: platform code and its tests name no real strategy

PERM = {"mode": "live", "key": "trade", "account": "6973", "since": "2026-11-09", "loss_pause": -1500,
        "allow": [{"strategy": STRAT, "underlying": "SPX", "root": "SPXW", "right": "C", "width": 10,
                   "max_lots": 1, "min_credit": 0.20, "min_room": 10, "window": ["13:00:00", "13:03:59"],
                   "cancel_at": "13:04:00", "max_live_per_day": 1}]}
TICKET = {"strategy": STRAT, "day": "2026-11-10", "underlying": "SPX", "root": "SPXW", "right": "C",
          "short": 7565, "long": 7575, "lots": 1, "limit": 1.30, "spot": 7549.20}


def write_perm(state_dir: Path, **over) -> Path:
    d = R.orders_dir(state_dir)
    (d / "permission.json").write_text(json.dumps(dict(PERM, **over)), encoding="utf-8")
    return state_dir


@pytest.fixture
def sd(tmp_path):
    return write_perm(tmp_path)


class Clock:
    def __init__(self, t: dt.datetime):
        self.t = t

    def now(self) -> dt.datetime:
        return self.t

    async def sleep(self, s: float) -> None:
        self.t += dt.timedelta(seconds=s)


class FakeSession:
    def __init__(self, *creds):
        self.creds = creds

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


class FakeAcct:
    def __init__(self, number="5WX16973", statuses=("Live", "Filled"), dry_errors=(), send_exc=None,
                 fills=(3.20, 1.90), positions=(), working=()):
        self.account_number = number
        self.is_closed = False
        self.statuses = list(statuses)
        self.dry_errors = list(dry_errors)
        self.send_exc = send_exc
        self.fills = fills                      # per leg of the last order placed, in its leg order
        self.positions = list(positions)
        self.working = list(working)
        self.calls: list[str] = []
        self.cancelled = False
        self.orders: list = []

    def _resp(self, errors=()):
        return NS(buying_power_effect=NS(change_in_buying_power=Decimal("-870.00")),
                  fee_calculation=NS(total_fees=Decimal("-3.44")), warnings=[], errors=list(errors),
                  order=NS(id=4242, status="Received"))

    async def place_order(self, session, order, dry_run=True):
        self.calls.append("dry" if dry_run else "live")
        self.orders.append(order)
        if dry_run:
            return self._resp(self.dry_errors)
        if self.send_exc is not None:
            raise self.send_exc
        return self._resp()

    async def get_order(self, session, oid):
        self.calls.append("get")
        st = "Cancelled" if self.cancelled else (self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0])
        acts = ([getattr(leg.action, "value", leg.action) for leg in self.orders[-1].legs] if self.orders
                else ["Sell to Open", "Buy to Open"])
        legs = [NS(action=a, fills=[]) for a in acts]
        if st == "Filled":
            legs = [NS(action=a, fills=[NS(quantity=Decimal(1), fill_price=Decimal(str(f)))])
                    for a, f in zip(acts, self.fills)]
        return NS(id=oid, status=st, legs=legs)

    async def delete_order(self, session, oid):
        self.calls.append("cancel")
        self.cancelled = True

    async def get_live_orders(self, session):
        self.calls.append("orders")
        return list(self.working)

    async def get_positions(self, session):
        self.calls.append("positions")
        return list(self.positions)


def account_api(*accts):
    class API:
        @staticmethod
        async def get(session):
            return list(accts)
    return API


def run_place(sd, acct, *, live=True, clock=None, ticket=None, budget=None):
    clock = clock or Clock(AT_1301)
    t = R.parse_ticket(ticket or TICKET)
    perm = R.load_permission(sd)
    rule = R.check(t, perm, clock.now(), live, sd)

    async def go():
        async with R.Broker(("secret", "refresh"), budget=budget, session_factory=FakeSession,
                            account_api=account_api(acct)) as b:
            return await R.place(t, perm, rule, b, sd, live=live, now=clock.now, sleep=clock.sleep, say=lambda s: None)
    return asyncio.run(go()), clock


# ── the order ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_order_is_the_call_credit_spread_as_one_limit_day_order():
    o = R.build_order(R.parse_ticket(TICKET))
    assert [leg.symbol for leg in o.legs] == ["SPXW  261110C07565000", "SPXW  261110C07575000"]
    assert [leg.action.value for leg in o.legs] == ["Sell to Open", "Buy to Open"]
    assert [leg.quantity for leg in o.legs] == [1, 1]
    js = json.loads(o.model_dump_json(exclude_none=True, by_alias=True))
    assert js["order-type"] == "Limit" and js["time-in-force"] == "Day"
    assert js["price-effect"] == "Credit" and Decimal(str(js["price"])) == Decimal("1.30")
    assert {leg["instrument-type"] for leg in js["legs"]} == {"Equity Option"}


# ── the guard ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_allowed_ticket_passes_as_a_test_order_and_live_inside_the_window(sd):
    t = R.parse_ticket(TICKET)
    perm = R.load_permission(sd)
    assert R.check(t, perm, AT_1301, False, sd).strategy == STRAT
    assert R.check(t, perm, AT_1301, True, sd).strategy == STRAT
    assert R.check(t, perm, dt.datetime(2026, 11, 10, 9, 0), False, sd)          # a test order: any time today


REFUSALS = [
    ("mode off", {}, {"mode": "off"}, AT_1301, False, "off"),
    ("a test-only permission refuses live", {}, {"mode": "dry_run"}, AT_1301, True, "not allowed"),
    ("another strategy", {"strategy": "strat_b"}, {}, AT_1301, False, "may not trade"),
    ("NDX", {"underlying": "NDX", "root": "NDXP"}, {}, AT_1301, False, "underlying"),
    ("the AM-settled root", {"root": "SPX"}, {}, AT_1301, False, "root"),
    ("puts", {"right": "P"}, {}, AT_1301, False, "only C"),
    ("5 wide", {"long": 7570}, {}, AT_1301, False, "10 wide"),
    ("inverted: a debit call spread", {"short": 7575, "long": 7565}, {}, AT_1301, False, "10 wide"),
    ("2 lots", {"lots": 2}, {}, AT_1301, False, "lots"),
    ("0 lots", {"lots": 0}, {}, AT_1301, False, "lots"),
    ("a fractional lot", {"lots": 1.5}, {}, AT_1301, False, "whole number"),
    ("under the minimum credit", {"limit": 0.15}, {}, AT_1301, False, "minimum"),
    ("off the 0.05 tick", {"limit": 1.33}, {}, AT_1301, False, "steps"),
    ("a credit as wide as the spread", {"limit": 10.0}, {}, AT_1301, False, "width"),
    ("the short strike too close", {"spot": 7560}, {}, AT_1301, False, "pts above"),
    ("another expiry", {"day": "2026-11-11"}, {}, AT_1301, False, "not today"),
    ("live before 13:00", {}, {}, dt.datetime(2026, 11, 10, 12, 59, 59), True, "window"),
    ("live at 13:04", {}, {}, dt.datetime(2026, 11, 10, 13, 4, 0), True, "window"),
]


@pytest.mark.parametrize("what,t_over,p_over,now,live,why", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_everything_else_is_refused(tmp_path, what, t_over, p_over, now, live, why):
    sd = write_perm(tmp_path, **p_over)
    with pytest.raises(R.Refused, match=why):
        t = R.parse_ticket(dict(TICKET, **t_over))
        R.check(t, R.load_permission(sd), now, live, sd)


def test_the_hard_lot_cap_beats_a_bigger_permission(tmp_path):
    rule = dict(PERM["allow"][0], max_lots=5)
    sd = write_perm(tmp_path, allow=[rule])
    with pytest.raises(R.Refused, match="the limit is 1"):
        R.check(R.parse_ticket(dict(TICKET, lots=2)), R.load_permission(sd), AT_1301, False, sd)


@pytest.mark.parametrize("perm", [None, {"mode": "yolo"}, {"allow": []}, {"key": "someone_else"},
                                  {"loss_pause": 1500}, {"account": "12"}])
def test_no_or_a_bad_permission_file_turns_real_orders_off(tmp_path, perm):
    if perm is not None:
        write_perm(tmp_path, **perm)
    with pytest.raises(R.Refused, match="no permission file|not valid"):
        R.load_permission(tmp_path)


# ── place and watch ───────────────────────────────────────────────────────────────────────────────────────────────

def test_a_test_order_is_never_sent(sd):
    acct = FakeAcct()
    out, _ = run_place(sd, acct, live=False)
    assert acct.calls == ["dry"]
    assert out["account"] == "****6973" and "live" not in out
    assert R.live_slots_used(sd, dt.date(2026, 11, 10)) == 0


def test_live_sends_after_a_clean_test_order_and_books_the_fill(sd):
    acct = FakeAcct(statuses=("Live", "Filled"), fills=(3.20, 1.90))
    out, _ = run_place(sd, acct)
    assert acct.calls == ["dry", "live", "get", "get"]
    assert out["live"]["status"] == "Filled" and out["live"]["fill_credit"] == pytest.approx(1.30)
    assert R.live_slots_used(sd, dt.date(2026, 11, 10)) == 1
    events = [r["event"] for r in R.read_ledger(sd, dt.date(2026, 11, 10))]
    assert events == ["dry_run", "live_sending", "live_sent", "live_final"]
    assert "5WX16973" not in R.ledger_path(sd, dt.date(2026, 11, 10)).read_text(encoding="utf-8")


def test_an_unfilled_order_is_cancelled_at_the_cut_off(sd):
    acct = FakeAcct(statuses=("Live",))
    out, clock = run_place(sd, acct, clock=Clock(dt.datetime(2026, 11, 10, 13, 3, 30)))
    assert acct.calls.count("cancel") == 1 and acct.calls[:2] == ["dry", "live"]
    assert out["live"]["status"] == "Cancelled"
    rows = R.read_ledger(sd, dt.date(2026, 11, 10))
    sent = next(r for r in rows if r["event"] == "live_cancel_sent")
    assert sent["at"] >= "2026-11-10T13:04:00"


def test_test_order_errors_stop_the_live_send(sd):
    acct = FakeAcct(dry_errors=["invalid_symbol: no such option"])
    with pytest.raises(R.Refused, match="errors"):
        run_place(sd, acct)
    assert acct.calls == ["dry"]
    assert R.live_slots_used(sd, dt.date(2026, 11, 10)) == 0


def test_one_live_order_a_day_even_after_a_failed_send(sd):
    with pytest.raises(RuntimeError, match="slot stays used"):
        run_place(sd, FakeAcct(send_exc=TimeoutError("read timed out")))
    acct = FakeAcct()
    with pytest.raises(R.Refused, match="already sent"):
        run_place(sd, acct)
    assert acct.calls == []


def test_the_account_must_be_the_permitted_one(sd):
    acct = FakeAcct(number="5WX11234")
    with pytest.raises(R.Refused, match="no open account ending 6973"):
        run_place(sd, acct)
    assert acct.calls == []


def test_an_empty_sdk_error_says_what_tastytrade_said():
    import logging

    import tastytrade  # noqa: F401 - the SDK sets its logger to DEBUG on import
    R.capture_sdk_errors()
    logging.getLogger("tastytrade").debug("Unknown error type: {'message': 'Token has insufficient scopes for this request'}")
    text = R.describe_error(RuntimeError(""))
    assert "insufficient scopes" in text and "'trade' scope" in text
    assert R.describe_error(RuntimeError("")) == "RuntimeError: (tastytrade gave no message)"   # used once
    assert R.describe_error(ValueError("price_too_far: x")) == "ValueError: price_too_far: x"


def test_the_cancel_goes_out_even_when_the_budget_is_spent(sd):
    class Spent:
        def take(self):
            raise RuntimeError("tastytrade request budget spent")
    acct = FakeAcct(statuses=("Live",))
    out, _ = run_place(sd, acct, clock=Clock(dt.datetime(2026, 11, 10, 13, 3, 50)), budget=Spent())
    assert "cancel" in acct.calls and out["live"]["status"] == "Cancelled"


# ── settle and the loss pause ─────────────────────────────────────────────────────────────────────────────────────

def test_settle_books_the_result_and_the_loss_pause_stops_the_next_order(sd):
    run_place(sd, FakeAcct(statuses=("Filled",), fills=(3.20, 1.90)))
    row = R.settle(sd, dt.date(2026, 11, 10), 7580.0)                  # above the long strike: the full loss
    # both legs settle in the money: tastytrade's $5 a leg on top of the order's fees (as it posted on 11/10)
    assert row["settle_value"] == 10 and row["pnl"] == pytest.approx((1.30 - 10) * 100 - 3.44 - 10.0)
    with pytest.raises(R.Refused, match="already in the results"):
        R.settle(sd, dt.date(2026, 11, 10), 7580.0)
    R.add_result(sd, {"day": "2026-11-11", "strategy": STRAT, "pnl": -700})
    assert R.realized_since(sd, dt.date(2026, 11, 9)) <= -1500
    nxt = R.parse_ticket(dict(TICKET, day="2026-11-12"))
    with pytest.raises(R.Refused, match="paused"):
        R.check(nxt, R.load_permission(sd), dt.datetime(2026, 11, 12, 13, 1), True, sd)


def test_settle_needs_a_filled_order(sd):
    with pytest.raises(R.Refused, match="no filled real order"):
        R.settle(sd, dt.date(2026, 11, 10), 7500.0)


def test_an_expired_worthless_spread_keeps_the_credit(sd):
    run_place(sd, FakeAcct(statuses=("Filled",), fills=(3.20, 1.90)))
    row = R.settle(sd, dt.date(2026, 11, 10), 7549.83)
    assert row["settle_value"] == 0 and row["pnl"] == pytest.approx(130 - 3.44)


def test_settle_adds_tastytrades_fee_for_each_leg_settled_in_the_money(sd):
    # 2026-11-13: 7560/7570 sold at 1.35, SPX closed 7,561.67: the short settled 1.67 in the money, the long worthless
    t = dict(TICKET, day="2026-11-13", short=7560, long=7570, limit=1.35, spot=7533.37)
    run_place(sd, FakeAcct(statuses=("Filled",), fills=(2.95, 1.60)), ticket=t,
              clock=Clock(dt.datetime(2026, 11, 13, 13, 1, 30)))
    row = R.settle(sd, dt.date(2026, 11, 13), 7561.67)
    assert row["settle_value"] == pytest.approx(1.67) and row["fees"] == pytest.approx(3.44 + 5.0)
    assert row["pnl"] == pytest.approx(-40.44) and row["how"] == "settled"           # what tastytrade posted


def test_settle_needs_the_index_close_unless_the_spread_was_closed(sd):
    run_place(sd, FakeAcct(statuses=("Filled",), fills=(3.20, 1.90)))
    with pytest.raises(R.Refused, match="official close"):
        R.settle(sd, dt.date(2026, 11, 10), None)


# ── closing the day's own spread ─────────────────────────────────────────────────────────────────────────────────────

CLOSE_AT = dt.datetime(2026, 11, 10, 15, 46, 0)
HELD = [NS(symbol="SPXW  261110C07565000", quantity=Decimal("1"), quantity_direction="Short"),
        NS(symbol="SPXW  261110C07575000", quantity=Decimal("1"), quantity_direction="Long")]


def opened(sd):
    """The day's spread, filled at 1.30 at 13:01."""
    run_place(sd, FakeAcct(statuses=("Filled",), fills=(3.20, 1.90)))
    return sd


def run_close(sd, acct, debit=0.80, *, live=True, clock=None, wait_s=45.0):
    clock = clock or Clock(CLOSE_AT)
    perm = R.load_permission(sd)
    t, rule = R.check_close(R.day_order(sd, dt.date(2026, 11, 10)), perm, debit, clock.now(), live, sd)

    async def go():
        async with R.Broker(("secret", "refresh"), session_factory=FakeSession, account_api=account_api(acct)) as b:
            return await R.close_spread(t, perm, rule, debit, b, sd, live=live, now=clock.now, sleep=clock.sleep,
                                        wait_s=wait_s, say=lambda s: None)
    return asyncio.run(go()), clock


def test_the_closing_order_buys_back_the_short_and_sells_the_long_for_a_debit():
    o = R.build_close_order(R.parse_ticket(TICKET), 0.80)
    assert [leg.symbol for leg in o.legs] == ["SPXW  261110C07565000", "SPXW  261110C07575000"]
    assert [leg.action.value for leg in o.legs] == ["Buy to Close", "Sell to Close"]
    assert [leg.quantity for leg in o.legs] == [1, 1]
    js = json.loads(o.model_dump_json(exclude_none=True, by_alias=True))
    assert js["order-type"] == "Limit" and js["time-in-force"] == "Day"
    assert js["price-effect"] == "Debit" and Decimal(str(js["price"])) == Decimal("0.80")


def test_a_test_close_is_never_sent(sd):
    opened(sd)
    acct = FakeAcct(positions=HELD)
    out, _ = run_close(sd, acct, live=False)
    assert acct.calls == ["positions", "orders", "dry"] and "live" not in out
    assert R.close_slots_used(sd, dt.date(2026, 11, 10)) == 0
    assert R.live_slots_used(sd, dt.date(2026, 11, 10)) == 1                        # the opening order's, untouched


def test_a_live_close_fills_and_settle_books_it(sd):
    opened(sd)
    acct = FakeAcct(positions=HELD, statuses=("Live", "Filled"), fills=(2.00, 1.20))  # buy back 2.00, sell 1.20
    out, _ = run_close(sd, acct)
    assert acct.calls == ["positions", "orders", "dry", "live", "get", "get"]
    assert out["live"]["status"] == "Filled" and out["live"]["fill_debit"] == pytest.approx(0.80)
    o = R.day_order(sd, dt.date(2026, 11, 10))
    assert o["status"] == "Filled" and o["fill_credit"] == pytest.approx(1.30)        # the opening order, unchanged
    assert o["close"]["status"] == "Filled" and o["close"]["fill_debit"] == pytest.approx(0.80)
    row = R.settle(sd, dt.date(2026, 11, 10), None)                                     # no index close needed
    assert row["how"] == "closed" and row["settle_value"] == pytest.approx(0.80)
    assert row["pnl"] == pytest.approx((1.30 - 0.80) * 100 - 3.44 - 3.44)              # both orders' fees, no settlement fee
    with pytest.raises(R.Refused, match="already closed"):
        R.check_close(R.day_order(sd, dt.date(2026, 11, 10)), R.load_permission(sd), 0.80, CLOSE_AT, True, sd)


def test_a_close_needs_the_spread_held_exactly_as_opened(sd):
    opened(sd)
    short2 = NS(symbol=HELD[0].symbol, quantity=Decimal("2"), quantity_direction="Short")
    for positions in ([], HELD[:1], [short2, HELD[1]]):
        acct = FakeAcct(positions=positions)
        with pytest.raises(R.Refused, match="does not hold"):
            run_close(sd, acct)
        assert acct.calls == ["positions"]
    assert R.close_slots_used(sd, dt.date(2026, 11, 10)) == 0


def test_a_close_waits_for_any_order_working_on_the_spread(sd):
    opened(sd)
    working = NS(id=77, status="Live", legs=[NS(symbol="SPXW  261110C07565000")])
    acct = FakeAcct(positions=HELD, working=[working])
    with pytest.raises(R.Refused, match="77 is still working"):
        run_close(sd, acct)
    assert "dry" not in acct.calls
    done = NS(id=78, status="Cancelled", legs=[NS(symbol="SPXW  261110C07565000")])
    other = NS(id=79, status="Live", legs=[NS(symbol="IBIT  261120P00043000")])
    acct = FakeAcct(positions=HELD, working=[done, other])
    run_close(sd, acct, live=False)                       # a final order, or one on another symbol: no obstacle
    assert acct.calls[-1] == "dry"


def test_an_unfilled_close_is_cancelled_after_the_wait_and_the_next_attempt_may_go(sd):
    opened(sd)
    acct = FakeAcct(positions=HELD, statuses=("Live",))
    out, _ = run_close(sd, acct, wait_s=30)
    assert acct.calls.count("cancel") == 1 and out["live"]["status"] == "Cancelled"
    sent = next(r for r in R.read_ledger(sd, dt.date(2026, 11, 10)) if r["event"] == "close_cancel_sent")
    assert sent["at"] >= "2026-11-10T15:46:30"
    assert R.day_order(sd, dt.date(2026, 11, 10))["close"]["status"] == "Cancelled"
    acct2 = FakeAcct(positions=HELD, statuses=("Filled",), fills=(2.10, 1.20))
    out2, _ = run_close(sd, acct2, debit=0.90)
    assert out2["live"]["status"] == "Filled" and R.close_slots_used(sd, dt.date(2026, 11, 10)) == 2
    assert R.day_order(sd, dt.date(2026, 11, 10))["close"]["fill_debit"] == pytest.approx(0.90)


CLOSE_REFUSALS = [
    ("off the 0.05 tick", {}, 0.83, CLOSE_AT, True, "steps"),
    ("nothing to pay", {}, 0.0, CLOSE_AT, True, "between"),
    ("more than the width", {}, 10.05, CLOSE_AT, True, "between"),
    ("mode off", {"mode": "off"}, 0.80, CLOSE_AT, False, "off"),
    ("a test-only permission refuses a live close", {"mode": "dry_run"}, 0.80, CLOSE_AT, True, "not allowed"),
    ("before the open", {}, 0.80, dt.datetime(2026, 11, 10, 9, 29, 59), True, "outside"),
    ("in the last half minute", {}, 0.80, dt.datetime(2026, 11, 10, 15, 59, 30), True, "outside"),
    ("the next day", {}, 0.80, dt.datetime(2026, 11, 11, 10, 0), True, "only today"),
]


@pytest.mark.parametrize("what,p_over,debit,now,live,why", CLOSE_REFUSALS, ids=[r[0] for r in CLOSE_REFUSALS])
def test_closing_refusals(tmp_path, what, p_over, debit, now, live, why):
    sd = opened(write_perm(tmp_path))
    if p_over:
        write_perm(sd, **p_over)
    with pytest.raises(R.Refused, match=why):
        R.check_close(R.day_order(sd, dt.date(2026, 11, 10)), R.load_permission(sd), debit, now, live, sd)


def test_a_close_needs_a_filled_opening_order(sd):
    with pytest.raises(R.Refused, match="no filled real order"):
        R.check_close(R.day_order(sd, dt.date(2026, 11, 10)), R.load_permission(sd), 0.80, CLOSE_AT, True, sd)
    run_place(sd, FakeAcct(statuses=("Live",)), clock=Clock(dt.datetime(2026, 11, 10, 13, 3, 30)))   # cancelled unfilled
    with pytest.raises(R.Refused, match="no filled real order"):
        R.check_close(R.day_order(sd, dt.date(2026, 11, 10)), R.load_permission(sd), 0.80, CLOSE_AT, True, sd)


def test_the_closing_attempts_are_capped(sd):
    opened(sd)
    for i in range(1, R.HARD_MAX_CLOSES_PER_DAY + 1):
        (R.orders_dir(sd) / f"2026-11-10.close.{i}.lock").write_text("x", encoding="utf-8")
    with pytest.raises(R.Refused, match="closing attempts"):
        R.check_close(R.day_order(sd, dt.date(2026, 11, 10)), R.load_permission(sd), 0.80, CLOSE_AT, True, sd)
    assert R.check_close(R.day_order(sd, dt.date(2026, 11, 10)), R.load_permission(sd), 0.80, CLOSE_AT, False, sd)


# ── segregation: nothing else reaches the real account ─────────────────────────────────────────────────────────────

_SKIP = {".git", ".pycache", "__pycache__", "node_modules", "paper_state", "logs", "tests"}
_ALLOWED = {"api/services/real_orders.py", "scripts/real_order.py"}


def _py_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP and not d.startswith(".venv")]
        for f in filenames:
            if f.endswith(".py"):
                p = Path(dirpath) / f
                yield p, p.relative_to(root).as_posix()


def _grep(root: Path, pat: re.Pattern, allowed: set[str]) -> list[str]:
    return [rel for p, rel in _py_files(root) if rel not in allowed
            and pat.search(p.read_text(encoding="utf-8", errors="replace"))]


_IMPORT = re.compile(r"^\s*(from\s+[\w.]*real_orders\b|import\s+[\w.]*real_orders\b|from\s+[\w.]+\s+import\s+[^\n]*\b"
                     r"real_orders\b)|import_module\([^)]*real_orders|__import__\([^)]*real_orders", re.M)


def test_only_the_cli_imports_the_real_order_module():
    assert _grep(REPO, _IMPORT, _ALLOWED) == []


def test_the_order_login_is_read_only_in_the_real_order_module():
    assert _grep(REPO, re.compile(r"TT_TRADE_"), {"api/services/real_orders.py"}) == []


def test_nothing_else_places_or_cancels_a_broker_order():
    pat = re.compile(r"\.(place_order|place_complex_order|delete_order|delete_complex_order|replace_order)\(|"
                     r"/orders/dry-run")
    assert _grep(REPO, pat, {"api/services/real_orders.py"}) == []


def test_the_strategies_never_touch_the_real_order_path():
    """The strategy folders, which the service and the runners load. The operator's scripts in ops/ are checked below."""
    strategies = REPO.parent / "alan_trader_strategies"
    if not strategies.is_dir():
        pytest.skip("no strategies checkout beside this one")
    pat = re.compile(r"services[./]real_orders|scripts[./]real_order|real_order\.py|TT_TRADE_|\.place_order\(|"
                     r"\.delete_order\(")
    assert [rel for rel in _grep(strategies, pat, set()) if not rel.startswith("ops/")] == []


def test_the_ops_scripts_reach_the_real_account_only_through_the_cli():
    """The strategies repo's ops/ (the operator's scripts) may write a ticket and run scripts/real_order.py, but never
    import its module, read the order login or call the broker's order endpoints themselves; and only the no-ask 1 PM
    job, run for a day the owner names, sends a live order."""
    ops = REPO.parent / "alan_trader_strategies" / "ops"
    if not ops.is_dir():
        pytest.skip("no strategies checkout with ops/ beside this one")
    direct = re.compile(r"services[./]real_orders|TT_TRADE_|\.place_order\(|\.delete_order\(|/orders/dry-run")
    live = re.compile(r"real_order\.py\b[^\n]*--live")
    hits = []
    for p in sorted(ops.rglob("*")):
        if not p.is_file() or p.suffix not in (".py", ".sh", ".ps1") or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(ops).as_posix()
        code = "\n".join(line for line in p.read_text(encoding="utf-8", errors="replace").splitlines()
                         if not line.lstrip().startswith("#"))
        if direct.search(code):
            hits.append(f"{rel}: reaches the broker directly")
        if live.search(code) and rel != "ticket/run_1pm_noask.sh":
            hits.append(f"{rel}: sends a live order")
    assert hits == []


def test_the_paper_order_book_still_refuses_live_orders():
    from api.services import orders as O
    with pytest.raises(O.LiveNotArmed):
        O.parse_order({"account": "live", "underlying": "SPX", "legs": []})
