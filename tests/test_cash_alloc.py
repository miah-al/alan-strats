"""The cash sleeve (api/services/cash_alloc.py): cash above the reserve buys whole BOXX shares, a shortfall sells whole
lots newest first (never a lot opened today), small differences hold, a day is decided once, and a missing price or
cash figure trades nothing. Offline: stub inputs, a stub order book and the event desk's memory store."""
from __future__ import annotations

import datetime as _dt

import pandas as pd
import pytest

from api.services import cash_alloc as CA
from api.services.event_desk import MemoryEventStore


class Inputs:
    def __init__(self, price=118.5):
        self.px, self.held = price, []

    def prices_now(self, symbols):
        return {CA.SYMBOL: self.px}

    def lots(self):
        return list(self.held)


class Orders:
    def __init__(self, inputs, day_fn):
        self.inputs, self.day_fn, self.placed, self.closed, self.n = inputs, day_fn, [], [], 0

    def place(self, body):
        self.n += 1
        q = body["legs"][0]["quantity"]
        self.placed.append((body["underlying"], q, body["strategy"], body["client_order_id"]))
        tg = f"TG{self.n}"
        self.inputs.held.append({"trade_group_id": tg, "symbol": body["underlying"], "shares": q, "opened": self.day_fn()})
        return {"status": "filled", "fill_price": self.inputs.px, "trade_group_id": tg}

    def close_position(self, tgid, body):
        self.closed.append(tgid)
        self.inputs.held = [l for l in self.inputs.held if l["trade_group_id"] != tgid]
        return {"status": "filled"}


@pytest.fixture(autouse=True)
def _weekdays(monkeypatch):
    monkeypatch.setattr(CA.RA, "trading_day", lambda d: d.weekday() < 5)


def _setup(cash):
    inp = Inputs()
    day = {"d": _dt.date(2026, 10, 12)}
    orders = Orders(inp, lambda: day["d"])
    box = {"cash": cash}
    alloc = CA.CashSleeveAllocator(MemoryEventStore(), orders, inputs=inp, cash_fn=lambda: box["cash"])
    return alloc, inp, orders, day, box


def _at(d: str) -> pd.Timestamp:
    return pd.Timestamp(f"{d} 15:55", tz=CA.NY)


def test_the_plan():
    d = _dt.date(2026, 10, 14)
    lots = [{"trade_group_id": "A", "shares": 20, "opened": _dt.date(2026, 10, 12)},
            {"trade_group_id": "B", "shares": 10, "opened": _dt.date(2026, 10, 13)},
            {"trade_group_id": "C", "shares": 5, "opened": d}]
    assert CA.plan(11422.0, [], 118.5, d)["buy"] == 33                   # (11,422 - 7,500) / 118.5
    assert CA.plan(8000.0, lots, 118.5, d) == {"buy": 0, "close": [], "notes": []}      # inside the band: hold
    p = CA.plan(5000.0, lots, 118.5, d)                                  # short 2,500: newest held lot first (B), then A
    assert [l["trade_group_id"] for l in p["close"]] == ["B", "A"] and "1 lot(s)" in p["notes"][0]


def test_surplus_cash_buys_boxx_once_a_day():
    alloc, inp, orders, day, box = _setup(11422.0)
    r = alloc.run(now=_at("2026-10-12"))
    assert r["status"] == "swept" and r["verdict"] == "buy"
    assert orders.placed == [("BOXX", 33, "cash_sleeve", "cash-2026-10-12-buy-BOXX")]
    assert alloc.run(now=_at("2026-10-12"))["status"] == "already_decided"


def test_a_shortfall_sells_lots_and_small_gaps_hold():
    alloc, inp, orders, day, box = _setup(7900.0)
    inp.held = [{"trade_group_id": "TG7", "symbol": "BOXX", "shares": 33, "opened": _dt.date(2026, 10, 5)}]
    assert alloc.run(now=_at("2026-10-12"))["status"] == "held" and not orders.placed and not orders.closed
    box["cash"] = 3500.0
    day["d"] = _dt.date(2026, 10, 13)
    r = alloc.run(now=_at("2026-10-13"))
    assert r["status"] == "swept" and r["verdict"] == "sell" and orders.closed == ["TG7"]


def test_no_price_no_cash_and_weekends_trade_nothing():
    alloc, inp, orders, day, box = _setup(11422.0)
    inp.px = None
    assert alloc.run(now=_at("2026-10-12"))["status"] == "no_quote"
    alloc, inp, orders, day, box = _setup(None)
    assert alloc.run(now=_at("2026-10-12"))["status"] == "no_quote"
    alloc, inp, orders, day, box = _setup(11422.0)
    assert alloc.run(now=_at("2026-10-10"))["status"] == "no_session" and not orders.placed
