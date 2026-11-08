"""
The REAL account reads (api/services/real_account.py, api/routers/real.py): read-only, in /api/paper's shapes.

No tastytrade calls: every test runs on a fake session and a fake Account. One test scans the module and the router
for anything that could place, change or cancel an order.
"""
from __future__ import annotations

import datetime as _dt
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

from api.services import real_account as R  # noqa: E402

TODAY = _dt.date(2026, 11, 9)


class FakeSession:
    session_expiration = 4_102_444_800.0          # far future: no refresh counted

    def __init__(self, *creds):
        self.creds = creds

    async def __aenter__(self):
        return self


def make_account(positions=(), history=(), nlv=(), balances=None):
    class FakeAccount:
        account_number = "5WT00006973"
        nickname = "Individual"
        account_type_name = "Individual"
        margin_or_cash = "Margin"
        is_closed = False
        seen: list = []

        @classmethod
        async def get(cls, session):
            cls.seen.append("Account.get")
            return [cls()]

        async def get_balances(self, session):
            self.seen.append("get_balances")
            return balances or NS(net_liquidating_value=Decimal("3100"), cash_balance=Decimal("3100"),
                                  derivative_buying_power=Decimal("3100"), equity_buying_power=Decimal("6200"),
                                  pending_cash=Decimal("0"))

        async def get_positions(self, session, include_marks=None):
            self.seen.append("get_positions")
            return list(positions)

        async def get_history(self, session, **kw):
            self.seen.append("get_history")
            return list(history)

        async def get_net_liquidating_value_history(self, session, time_back=None, start_time=None):
            self.seen.append("get_net_liquidating_value_history")
            return list(nlv)
    return FakeAccount


class CountingBudget:
    def __init__(self):
        self.n = 0

    def take(self):
        self.n += 1


@pytest.fixture
def install(monkeypatch):
    monkeypatch.setattr(R, "_today", lambda: TODAY)
    monkeypatch.setattr(R, "_market_hours", lambda now=None: True)
    monkeypatch.delenv("REAL_ACCOUNT", raising=False)

    def go(**kw):
        acct = make_account(**kw)
        budget = CountingBudget()
        R.set_client(R.RealAccountClient(creds=("s", "r"), budget=budget, session_factory=FakeSession, account_api=acct))
        return acct, budget
    yield go
    R.set_client(None)


def pos(symbol, qty, direction, avg, mark, und="SPX"):
    return NS(symbol=symbol, underlying_symbol=und, instrument_type="Equity Option", quantity=Decimal(qty),
              quantity_direction=direction, average_open_price=Decimal(str(avg)), mark_price=Decimal(str(mark)),
              close_price=Decimal(str(mark)), multiplier=Decimal("100"), expires_at=None,
              created_at=_dt.datetime(2026, 11, 9, 13, 1, tzinfo=_dt.timezone.utc))


def txn(i, ttype, sub, action, symbol, qty, price, net_value, day="2026-11-06", und="SPX", fees=Decimal("1.725")):
    return NS(id=i, transaction_type=ttype, transaction_sub_type=sub, action=action, symbol=symbol, underlying_symbol=und,
              quantity=Decimal(str(qty)) if qty is not None else None, price=Decimal(str(price)) if price is not None else None,
              value=Decimal(str(net_value)), net_value=Decimal(str(net_value)), commission=fees, clearing_fees=None,
              regulatory_fees=None, proprietary_index_option_fees=None, other_charge=None,
              transaction_date=_dt.date.fromisoformat(day), executed_at=_dt.datetime.fromisoformat(day + "T18:01:16+00:00"),
              order_id=77, description=sub)


# ── read-only by construction ─────────────────────────────────────────────────

def test_module_and_router_cannot_touch_orders():
    for f in (REPO / "api/services/real_account.py", REPO / "api/routers/real.py"):
        src = f.read_text(encoding="utf-8")
        code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
        body = code.split('"""', 2)[-1]                              # past the module docstring
        for bad in ("place_order", "replace_order", "delete_order", "place_complex_order", "delete_complex_order",
                    "get_order_buying_power_effect", "NewOrder", "dry_run"):
            assert bad not in body, f"{f.name} mentions {bad}"
    from api.routers import real
    assert all(r.methods <= {"GET", "HEAD"} for r in real.router.routes), "the real router must be GET-only"


def test_only_read_calls_are_made_and_counted(install):
    acct, budget = install(positions=[pos("SPXW  261109C07425000", 1, "Short", 1.80, 0.90),
                                      pos("SPXW  261109C07435000", 1, "Long", 0.0, 0.10)])
    R.summary()
    assert set(acct.seen) <= {"Account.get", "get_balances", "get_positions", "get_history",
                              "get_net_liquidating_value_history"}
    assert budget.n == len(acct.seen)                                # every REST call charged once
    n = budget.n
    R.summary()                                                      # served from the cache
    assert budget.n == n


# ── shapes and arithmetic ─────────────────────────────────────────────────────

def test_open_call_credit_spread_row(install):
    install(positions=[pos("SPXW  261109C07425000", 1, "Short", 1.80, 0.90),
                       pos("SPXW  261109C07435000", 1, "Long", 0.0, 0.10)])
    t = R.positions("open")
    assert [c["field"] for c in t["columns"]][:3] == ["trade_group_id", "strategy", "strategy_label"]
    (row,) = t["rows"]
    assert row["trade_group_id"] == "real:SPX:2026-11-09"
    assert row["structure"] == "Call credit spread 7425/7435"
    assert row["entry_net"] == pytest.approx(180.0)                  # sold 1.80 x 100, bought 0.00
    assert row["market_value"] == pytest.approx(-80.0)               # -0.90 x 100 + 0.10 x 100
    assert row["pnl"] == pytest.approx(100.0)
    assert row["max_profit"] == pytest.approx(180.0) and row["max_loss"] == pytest.approx(820.0)
    assert row["short_strikes"] == [7425.0] and row["dte"] == 0 and row["managed_by"] == "you"


def test_closed_round_trip_and_summary(install):
    hist = [txn(1, "Money Movement", "Deposit", None, "", None, None, "3100", day="2026-11-02", fees=None),
            txn(2, "Trade", "Sell to Open", "Sell to Open", "SPXW  261106C07425000", 1, 1.80, "178.27"),
            txn(3, "Trade", "Buy to Open", "Buy to Open", "SPXW  261106C07435000", 1, 0.00, "-1.72"),
            txn(4, "Receive Deliver", "Expiration", None, "SPXW  261106C07425000", 1, None, "0", fees=None),
            txn(5, "Receive Deliver", "Expiration", None, "SPXW  261106C07435000", 1, None, "0", fees=None)]
    nlv = [NS(time="2026-11-05T21:00:00Z", close=Decimal("3100")), NS(time="2026-11-06T21:00:00Z", close=Decimal("3276.55"))]
    install(history=hist, nlv=nlv, balances=NS(net_liquidating_value=Decimal("3276.55"), cash_balance=Decimal("3276.55"),
                                               derivative_buying_power=Decimal("3276.55"),
                                               equity_buying_power=Decimal("6553.10"), pending_cash=Decimal("0")))
    s = R.summary()
    assert s["equity"] == pytest.approx(3276.55) and s["deposits"] == pytest.approx(3100)
    assert s["realized_pnl"] == pytest.approx(176.55) and s["closed_positions"] == 1 and s["wins"] == 1
    assert s["total_pnl"] == pytest.approx(176.55) and s["account"] == "****6973"
    assert s["previous_close"] == pytest.approx(3276.55)            # the last close before TODAY (11/09)
    assert s["day_pnl"] == pytest.approx(0.0) and s["buying_power"] == pytest.approx(3276.55)
    closed = R.positions("closed")["rows"]
    assert len(closed) == 1 and closed[0]["structure"] == "Call credit spread 7425/7435"
    assert closed[0]["pnl"] == pytest.approx(176.55) and closed[0]["closed"] == "2026-11-06"
    tx = R.transactions()["rows"]
    assert tx[0]["date"] >= tx[-1]["date"] and {r["sub_type"] for r in tx} >= {"Sell to Open", "Expiration"}


def test_unsettled_expiry_is_not_counted_as_realized(install):
    hist = [txn(2, "Trade", "Sell to Open", "Sell to Open", "SPXW  261109C07425000", 1, 1.80, "178.27", day="2026-11-09"),
            txn(3, "Trade", "Buy to Open", "Buy to Open", "SPXW  261109C07435000", 1, 0.00, "-1.72", day="2026-11-09")]
    install(history=hist)
    rts = R.round_trips([R._txn_row(t) for t in hist])
    assert rts[0]["status"] == "settling"                            # expiry today, nothing posted yet
    assert R.summary()["realized_pnl"] == 0


def test_equity_series_from_net_liq(install):
    nlv = [NS(time=f"2026-11-0{d}T21:00:00Z", close=Decimal(str(3100 + d))) for d in (2, 3, 4, 5, 6)]
    install(nlv=nlv)
    e = R.equity("2026-11-03", "2026-11-06")
    eq = e["series"][0]
    assert eq["name"] == "equity" and len(eq["t"]) == 4 and eq["v"] == [3103.0, 3104.0, 3105.0, 3106.0]
    assert eq["t"][0].startswith("2026-11-03")


def test_a_deposit_is_never_pnl(install):
    """The owner's account: $1,100 by 10/30, then $2,000 deposited on 11/02, no trades. The raw net liq jumps +$2,000;
    the equity line the app reads must stay flat (P&L 0), and the day's P&L must be 0."""
    hist = [txn(1, "Money Movement", "Deposit", None, "", None, None, "1100", day="2026-10-05", fees=None),
            txn(2, "Money Movement", "Deposit", None, "", None, None, "2000", day="2026-11-02", fees=None)]
    nlv = [NS(time="2026-10-30T21:00:00Z", close=Decimal("1100")), NS(time="2026-11-02T21:00:00Z", close=Decimal("3100")),
           NS(time="2026-11-06T21:00:00Z", close=Decimal("3100"))]
    install(history=hist, nlv=nlv)
    eq = R.equity("2026-10-29", "2026-11-08")["series"][0]
    assert eq["v"] == [3100.0, 3100.0, 3100.0]                     # 10/30 1,100 + the 2,000 deposited after it
    s = R.summary()
    assert s["day_pnl"] == pytest.approx(0.0) and s["total_pnl"] == pytest.approx(0.0) and s["deposits"] == pytest.approx(3100)


def test_router_answers_503_without_a_login(monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import create_app
    R.set_client(R.RealAccountClient(creds=None, budget=CountingBudget(), session_factory=FakeSession,
                                     account_api=make_account()))
    monkeypatch.setattr("engine.env.tastytrade_credentials", lambda: None)
    try:
        r = TestClient(create_app()).get("/api/real/summary")
        assert r.status_code == 503 and "no tastytrade login" in r.json().get("detail", r.text)
    finally:
        R.set_client(None)


def test_parse_occ_and_describe():
    o = R.parse_occ("SPXW  261106P07425000")
    assert o == {"root": "SPXW", "expiry": _dt.date(2026, 11, 6), "right": "put", "strike": 7425.0}
    assert R.parse_occ("QQQ") is None
    assert R.describe([{"strike": 43.0, "type": "put", "qty": 6.0}]) == "Long put 43"
    assert R.describe([{"strike": 650.0, "type": "call", "qty": 1.0}, {"strike": 665.0, "type": "call", "qty": -1.0}]) \
        == "Call debit spread 650/665"
    assert R.mask("5WT00006973") == "****6973"
