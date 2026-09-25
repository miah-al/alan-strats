"""
Paper orders (api/services/orders.py) and the DB write allow-list.

Unit tests need no database. The end-to-end test trades a THROWAWAY paper account it creates
(``alan_trader service tests …``), on a made-up underlying (ZZQA) quoted by a fake provider, and
deletes every row it wrote at the end — its transactions, its orders, the ZZQA securities nobody else
references, the account. The real paper account (AccountId 1, the runner's) is protected by the
service's own guard for the whole suite (ALAN_TRADER_PROTECTED_ACCOUNTS, tests/conftest.py): a write
for it would be refused before reaching the server.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import ReadOnlyViolation, bootstrap, check_statement  # noqa: E402

bootstrap()

from api.marketdata import symbols as SYM  # noqa: E402
from api.marketdata.limits import ProviderLimits, ProviderPolicy  # noqa: E402
from api.marketdata.providers.base import Provider  # noqa: E402
from api.services import orders as O  # noqa: E402

REAL_PAPER_ACCOUNT = 1
UND = "ZZQA"


# ── the write allow-list ──────────────────────────────────────────────────────

@pytest.mark.parametrize("sql", [
    "INSERT INTO portfolio.[Transaction] (AccountId) VALUES (:aid)",
    "IF NOT EXISTS (SELECT 1 FROM mkt.PriceBar WHERE TickerId=:t) INSERT INTO mkt.PriceBar (TickerId) VALUES (:t)",
    "UPDATE portfolio.Position SET Status = :st WHERE PositionId = :p",
    "DELETE FROM mkt.VixBar WHERE BarDate = :d",
    "INSERT INTO portfolio.Security (Symbol) OUTPUT INSERTED.SecurityId VALUES (:s)",
    "CREATE SCHEMA app", "CREATE TABLE app.PaperOrder (OrderId INT)", "UPDATE app.Alert SET Active = 0",
    "CREATE UNIQUE INDEX UX ON app.PaperOrder (OrderId) WHERE OrderId IS NOT NULL",
    "SELECT UpdatedAt, CreatedAt, 'drop table x' FROM app.PaperOrder",
])
def test_allow_list_admits_the_ledger_market_data_and_app(sql):
    check_statement(sql)


@pytest.mark.parametrize("sql", [
    "CREATE TABLE t (x int)", "DROP TABLE app.PaperOrder", "TRUNCATE TABLE mkt.PriceBar", "EXEC sp_who",
    "SELECT * INTO dbo.copy FROM mkt.PriceBar", "INSERT INTO portfolio.Holding (x) VALUES (1)",
    "DELETE portfolio.Holding", "CREATE SCHEMA other", "CREATE TABLE mkt.NewTable (x int)",
    "ALTER TABLE portfolio.Account ADD x INT", "INSERT INTO OtherDb.portfolio.Account (x) VALUES (1)",
    "UPDATE STATISTICS mkt.PriceBar", "SELECT 1; DELETE FROM dbo.users",
])
def test_allow_list_refuses_everything_else(sql):
    with pytest.raises(ReadOnlyViolation):
        check_statement(sql)


def test_protected_account_writes_are_refused_before_the_server(monkeypatch):
    from sqlalchemy import create_engine, text
    from api.bootstrap import install_db_read_only_guard, db_guard_installed, uninstall_db_read_only_guard
    monkeypatch.setenv("ALAN_TRADER_PROTECTED_ACCOUNTS", "1")
    was = db_guard_installed()
    install_db_read_only_guard()
    try:
        eng = create_engine("sqlite://")                 # never the shared database
        with eng.connect() as c:
            with pytest.raises(ReadOnlyViolation, match="protected account"):
                c.execute(text("INSERT INTO portfolio.[Transaction] (AccountId) VALUES (:aid)"), {"aid": 1})
            with pytest.raises(Exception) as e:          # allowed by the guard: sqlite then has no such table
                c.execute(text("INSERT INTO portfolio.[Transaction] (AccountId) VALUES (:aid)"), {"aid": 7})
            assert not isinstance(e.value, ReadOnlyViolation)
    finally:
        if not was:
            uninstall_db_read_only_guard()


# ── orders without a database ─────────────────────────────────────────────────

def _exp(days=30):
    return (_dt.date.today() + _dt.timedelta(days=days)).isoformat()


def _vertical(**kw):
    body = {"account": "paper", "underlying": UND, "order_type": "limit", "limit_price": 2.0,
            "legs": [{"type": "call", "strike": 100, "expiry": _exp(), "side": "buy", "quantity": 2},
                     {"type": "call", "strike": 105, "expiry": _exp(), "side": "sell", "quantity": 2}]}
    body.update(kw)
    return body


def test_order_validation():
    with pytest.raises(O.LiveNotArmed, match="not armed"):
        O.parse_order(_vertical(account="live"))
    for bad in ({"legs": []}, {"order_type": "stop"}, {"limit_price": None},
                {"legs": [{"type": "call", "strike": 100, "expiry": "2001-01-19", "side": "buy", "quantity": 1}]},
                {"legs": [{"type": "call", "strike": -5, "expiry": _exp(), "side": "buy", "quantity": 1}]},
                {"legs": [{"type": "fut", "strike": 5, "expiry": _exp(), "side": "buy", "quantity": 1}]},
                {"legs": [{"type": "put", "strike": 5, "expiry": _exp(), "side": "hold", "quantity": 1}]},
                {"legs": [{"type": "put", "strike": 5, "expiry": _exp(), "side": "buy", "quantity": 1.5}]},
                {"underlying": "SPY261030C00770000"}, {"account": "margin"}):
        with pytest.raises(O.OrderError):
            O.parse_order(_vertical(**bad))
    o = O.parse_order(_vertical(client_order_id="abc"))
    assert o.units == 2 and o.ratios == [1, 1]
    assert o.legs[0].symbol == SYM.make_option(UND, _dt.date.fromisoformat(_exp()), "C", 100).occ
    assert O.parse_order(_vertical(order_type="market", limit_price=None)).limit_price is None


def test_vertical_economics_net_and_breakeven():
    o = O.parse_order(_vertical())
    q = [{"symbol": o.legs[0].symbol, "mid": 3.0}, {"symbol": o.legs[1].symbol, "mid": 1.0}]
    assert O.net_price(o, q) == 2.0                                  # debit 2.00 per unit
    econ = O.economics(o, q, 102.0)
    assert econ["max_loss"] == pytest.approx(-400.0)                 # 2 units x 2.00 x 100
    assert econ["max_profit"] == pytest.approx(600.0)                # (5 - 2) x 2 x 100
    assert econ["breakevens"] == [pytest.approx(102.0)]
    bp, notes = O.buying_power(o, q, 102.0, econ)
    assert bp == pytest.approx(400.0) and not notes


def test_naked_short_call_is_undefined_risk_with_a_reg_t_estimate():
    o = O.parse_order(_vertical(legs=[{"type": "call", "strike": 110, "expiry": _exp(), "side": "sell", "quantity": 1}],
                                limit_price=-1.0))
    q = [{"symbol": o.legs[0].symbol, "mid": 1.5}]
    assert O.net_price(o, q) == -1.5
    econ = O.economics(o, q, 100.0)
    assert econ["max_loss"] is None and econ["max_profit"] == pytest.approx(150.0)
    bp, notes = O.buying_power(o, q, 100.0, econ)
    assert bp == pytest.approx((max(20 - 10, 10) + 1.5) * 100) and notes


# ── end to end, against a throwaway account ───────────────────────────────────

def _db_ok() -> bool:
    try:
        from api.services.db import ping
        return ping()[0]
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _db_ok(), reason="AlanStrats database unreachable")


class Quotes(Provider):
    """A streaming provider whose prices the test sets."""
    name = "fakebroker"
    streaming = True
    capabilities = frozenset({"quotes", "options", "greeks", "chain"})

    def __init__(self):
        super().__init__(ProviderLimits(ProviderPolicy(self.name, per_min=6000, per_day=100000, burst=1000)))
        self.px: dict[str, tuple[float, float]] = {}
        self.subscribed: set[str] = set()

    def supports(self, s):
        return s.startswith(UND)

    def set(self, sym, bid, ask):
        self.px[sym] = (bid, ask)
        if sym in self.subscribed:
            self.emit(sym, self.name, time.time(), bid=bid, ask=ask, last=(bid + ask) / 2)

    def subscribe(self, syms):
        for s in syms:
            self.subscribed.add(s)
            if s in self.px:
                b, a = self.px[s]
                self.emit(s, self.name, time.time(), bid=b, ask=a, last=(b + a) / 2)

    def unsubscribe(self, syms):
        self.subscribed.difference_update(syms)


def _sql(sql, params=None, write=False):
    from sqlalchemy import text
    from api.services.db import require_db
    eng = require_db()
    if write:
        with eng.begin() as c:
            return c.execute(text(sql), params or {})
    with eng.connect() as c:
        return c.execute(text(sql), params or {}).fetchall()


def _cleanup(aid: int) -> None:
    assert aid != REAL_PAPER_ACCOUNT
    name = _sql("SELECT Name FROM portfolio.Account WHERE AccountId = :a", {"a": aid})
    assert name and name[0][0].startswith("alan_trader service tests"), name
    _sql("DELETE FROM portfolio.[Transaction] WHERE AccountId = :aid", {"aid": aid}, write=True)
    if _sql("SELECT OBJECT_ID('app.PaperOrder', 'U')")[0][0] is not None:
        _sql("DELETE FROM app.PaperOrder WHERE AccountId = :aid", {"aid": aid}, write=True)
    _sql("DELETE FROM portfolio.Balance WHERE AccountId = :aid", {"aid": aid}, write=True)
    _sql("DELETE FROM portfolio.Security WHERE Underlying = :u AND NOT EXISTS "
         "(SELECT 1 FROM portfolio.[Transaction] t WHERE t.SecurityId = portfolio.Security.SecurityId)",
         {"u": UND}, write=True)
    _sql("DELETE FROM portfolio.Account WHERE AccountId = :aid", {"aid": aid}, write=True)


@pytest.fixture
def test_account(monkeypatch):
    from api.bootstrap import db_guard_installed, install_db_read_only_guard, uninstall_db_read_only_guard
    had_guard = db_guard_installed()
    install_db_read_only_guard()                         # every write below passes the allow-list
    for (old,) in _sql("SELECT AccountId FROM portfolio.Account WHERE Name LIKE 'alan_trader service tests%'"):
        _cleanup(int(old))                               # a run that died before its cleanup
    name = f"alan_trader service tests {uuid.uuid4().hex[:8]}"
    _sql("INSERT INTO portfolio.Account (Name, BrokerName, AccountType, Notes) VALUES (:n, 'Paper', 'paper', "
         "'throwaway: tests/test_api_orders.py')", {"n": name}, write=True)
    aid = int(_sql("SELECT AccountId FROM portfolio.Account WHERE Name = :n", {"n": name})[0][0])
    assert aid != REAL_PAPER_ACCOUNT
    monkeypatch.setenv("ALAN_TRADER_PAPER_ACCOUNT_ID", str(aid))
    try:
        yield aid
    finally:
        _cleanup(aid)
        left = _sql("SELECT COUNT(*) FROM portfolio.[Transaction] WHERE AccountId = :a", {"a": aid})[0][0]
        if not had_guard:
            uninstall_db_read_only_guard()
        assert left == 0


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from api.app import create_app
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@needs_db
def test_orders_end_to_end_on_a_throwaway_account(client, test_account):
    real_before = _sql("SELECT COUNT(*), COALESCE(MAX(TransactionId), 0) FROM portfolio.[Transaction] "
                       "WHERE AccountId = :a", {"a": REAL_PAPER_ACCOUNT})[0]
    hub = client.app.state.market
    fb = Quotes()
    hub.add_provider(fb, first=True)
    exp = _dt.date.today() + _dt.timedelta(days=30)
    c100 = SYM.make_option(UND, exp, "C", 100).occ
    c105 = SYM.make_option(UND, exp, "C", 105).occ
    c110 = SYM.make_option(UND, exp, "C", 110).occ
    fb.set(UND, 101.9, 102.1)
    fb.set(c100, 2.9, 3.1)
    fb.set(c105, 0.9, 1.1)
    fb.set(c110, 0.25, 0.35)
    body = _vertical(order_type="market", limit_price=None, client_order_id=f"t-{uuid.uuid4().hex}",
                     legs=[{"type": "call", "strike": 100, "expiry": exp.isoformat(), "side": "buy", "quantity": 2},
                           {"type": "call", "strike": 105, "expiry": exp.isoformat(), "side": "sell", "quantity": 2}])

    # preview
    pv = client.post("/api/orders/preview", json=body).json()
    assert pv["ok"] and pv["net_mid"] == pytest.approx(2.0) and pv["debit_credit"] == "debit"
    assert pv["max_loss"] == pytest.approx(-400.0) and pv["max_profit"] == pytest.approx(600.0)
    assert [l["symbol"] for l in pv["legs"]] == [c100, c105] and pv["buying_power_effect"] == pytest.approx(400.0)
    assert client.post("/api/orders/preview", json={**body, "account": "live"}).status_code == 403
    assert client.post("/api/orders", json={**body, "account": "live"}).status_code == 403

    # a market order fills at the mids, once however often it is sent
    r = client.post("/api/orders", json=body).json()
    assert r["status"] == "filled" and r["trade_group_id"], r
    assert [f["price"] for f in r["fills"]] == [pytest.approx(3.0), pytest.approx(1.0)]
    again = client.post("/api/orders", json=body).json()
    assert again["order_id"] == r["order_id"] and again["trade_group_id"] == r["trade_group_id"]
    tg = r["trade_group_id"]
    rows = _sql("SELECT s.Symbol, t.Direction, t.Quantity, t.TransactionPrice, t.Amount, t.Source FROM portfolio.[Transaction] t "
                "JOIN portfolio.Security s ON s.SecurityId = t.SecurityId WHERE t.TradeGroupId = :g AND t.AccountId = :a "
                "ORDER BY t.TransactionId", {"g": tg, "a": test_account})
    assert [(x[0], x[1]) for x in rows] == [(c100, "Buy"), (c105, "Sell")]
    assert [float(x[4]) for x in rows] == [pytest.approx(-601.0), pytest.approx(199.0)]    # cash, commission off

    # the Paper views see it, marked at the hub's mids
    pos = client.get("/api/paper/positions?status=open").json()
    mine = [p for p in pos["rows"] if p["trade_group_id"] == tg]
    assert mine and mine[0]["underlying"] == UND and mine[0]["contracts"] == 2
    assert mine[0]["priced_by"].startswith("market data") and mine[0]["market_value"] == pytest.approx(400.0)
    assert mine[0]["pnl"] == pytest.approx(-2.0)                                            # the two commissions
    m = mine[0]
    assert m["structure"] == "call debit spread 100/105" and m["managed_by"] == "manual" and m["runner_feed"] is None
    assert m["spot"] == pytest.approx(102.0) and m["units"] == 2 and m["entry_type"] == "debit"
    assert m["entry_credit_debit"] == pytest.approx(-2.01)                                 # per unit, commission in
    assert m["max_profit"] == pytest.approx(598.0) and m["max_loss"] == pytest.approx(-402.0)
    assert m["breakevens"] == [pytest.approx(102.01)] and m["short_strikes"] == [105.0]
    assert m["pnl_pct_of_max"] == pytest.approx(-2.0 / 598.0 * 100)
    # the fake feed quotes no greeks: Black-Scholes on each leg's implied vol; a debit call spread is long delta
    assert m["delta"] > 0 and m["gamma"] is not None and m["short_delta"] > 0 and m["sigma_to_short"] > 0
    assert "implied vol" in m["greeks_source"]
    lg = client.get(f"/api/paper/positions/{tg}/legs").json()
    assert {"iv", "delta", "gamma", "theta", "vega", "mark", "greeks_source"} <= set(lg["rows"][0])
    assert all(r["delta"] is not None and r["mark"] is not None for r in lg["rows"])
    summ = client.get("/api/paper/summary").json()
    assert summ["open_positions"] >= 1

    # a limit order that is not marketable works, then fills when the market comes to it
    lim = client.post("/api/orders", json={**body, "order_type": "limit", "limit_price": 1.5,
                                           "client_order_id": f"t-{uuid.uuid4().hex}"}).json()
    assert lim["status"] == "working", lim
    working = client.get("/api/orders?status=working").json()
    assert [row["order_id"] for row in working["rows"]] == [lim["order_id"]]
    fb.set(c100, 2.35, 2.45)                                          # net mid 1.40 <= 1.50
    deadline = time.time() + 20
    while time.time() < deadline:
        o = client.get("/api/orders?status=all").json()
        st = {row["order_id"]: row["status"] for row in o["rows"]}
        if st.get(lim["order_id"]) == "filled":
            break
        time.sleep(0.3)
    assert st.get(lim["order_id"]) == "filled"

    # a working order can be cancelled; a filled one cannot
    w2 = client.post("/api/orders", json={**body, "order_type": "limit", "limit_price": 0.5,
                                          "client_order_id": f"t-{uuid.uuid4().hex}"}).json()
    assert w2["status"] == "working"
    cx = client.delete(f"/api/orders/{w2['order_id']}")
    assert cx.status_code == 200 and cx.json()["status"] == "cancelled"
    assert client.delete(f"/api/orders/{w2['order_id']}").status_code == 409
    assert client.delete("/api/orders/999999999").status_code == 404

    # closing the first position sells the vertical at the mids and books a closed trade
    fb.set(c100, 3.9, 4.1)
    cl = client.post(f"/api/paper/positions/{tg}/close", json={"order_type": "market"}).json()
    assert cl["status"] == "filled" and cl["closes_trade_group_id"] == tg, cl
    closed = client.get("/api/paper/positions?status=closed").json()
    row = next(p for p in closed["rows"] if p["trade_group_id"] == tg)
    # opened for -400 cash - 2 commission, closed for (4.00 - 1.00) x 2 x 100 = +600 - 2 commission
    assert row["pnl"] == pytest.approx(196.0)
    assert client.post(f"/api/paper/positions/{tg}/close", json={}).status_code == 409
    assert client.post("/api/paper/positions/NO-SUCH/close", json={}).status_code == 404

    # nothing reached the real paper account
    real_after = _sql("SELECT COUNT(*), COALESCE(MAX(TransactionId), 0) FROM portfolio.[Transaction] "
                      "WHERE AccountId = :a", {"a": REAL_PAPER_ACCOUNT})[0]
    assert tuple(real_after) == tuple(real_before)
    hub.providers.remove(fb)
    hub.by_name.pop(fb.name, None)
