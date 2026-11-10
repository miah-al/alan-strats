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
                 fills=(3.20, 1.90)):
        self.account_number = number
        self.is_closed = False
        self.statuses = list(statuses)
        self.dry_errors = list(dry_errors)
        self.send_exc = send_exc
        self.fills = fills
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
        legs = [NS(action="Sell to Open", fills=[]), NS(action="Buy to Open", fills=[])]
        if st == "Filled":
            legs = [NS(action="Sell to Open", fills=[NS(quantity=Decimal(1), fill_price=Decimal(str(self.fills[0])))]),
                    NS(action="Buy to Open", fills=[NS(quantity=Decimal(1), fill_price=Decimal(str(self.fills[1])))])]
        return NS(id=oid, status=st, legs=legs)

    async def delete_order(self, session, oid):
        self.calls.append("cancel")
        self.cancelled = True

    async def get_live_orders(self, session):
        return []


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
    assert row["settle_value"] == 10 and row["pnl"] == pytest.approx((1.30 - 10) * 100 - 3.44)
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
    strategies = REPO.parent / "alan_trader_strategies"
    if not strategies.is_dir():
        pytest.skip("no strategies checkout beside this one")
    pat = re.compile(r"services[./]real_orders|scripts[./]real_order|real_order\.py|TT_TRADE_|\.place_order\(|"
                     r"\.delete_order\(")
    assert _grep(strategies, pat, set()) == []


def test_the_paper_order_book_still_refuses_live_orders():
    from api.services import orders as O
    with pytest.raises(O.LiveNotArmed):
        O.parse_order({"account": "live", "underlying": "SPX", "legs": []})
