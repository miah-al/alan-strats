"""The sector rotation's paper allocator (api/services/rotation_alloc.py): the first run buys the last month-end's
picks, later days hold, the month's last trading day re-ranks and trades, young lots are never sold, and a day is
decided once. Offline: stub inputs, a stub order book, the event desk's memory store and a stub rule (this module's
scores / picks / target_shares) so the plugin isn't needed."""
from __future__ import annotations

import datetime as _dt
import math

import pandas as pd
import pytest

from api.services import rotation_alloc as RA
from api.services.event_desk import MemoryEventStore

UNI = ("AAA", "BBB", "CCC", "DDD", "EEE")


# ── the stub rule: the score is the last close, so the picks are the 3 priciest ──
def scores(closes, lookback=21, vol_window=60):
    return closes.iloc[-1].astype(float)


def picks(closes, top_k=3, lookback=21, vol_window=60):
    return list(scores(closes).dropna().sort_values(ascending=False).index[:top_k])


def target_shares(chosen, prices, sleeve):
    each = sleeve / len(chosen)
    return {s: int(math.floor(each / prices[s])) if prices.get(s) else 0 for s in chosen}


class Rule:
    universe, top_k, lookback, vol_window, sleeve, min_trade_frac = UNI, 3, 21, 60, 5000.0, 0.02


class Inputs:
    def __init__(self, closes: pd.DataFrame, prices: dict):
        self.df, self.px, self.held = closes, dict(prices), []

    def closes(self, symbols, until):
        return self.df[self.df.index <= pd.Timestamp(until)]

    def prices_now(self, symbols):
        return {s: self.px.get(s) for s in symbols}

    def lots(self):
        return list(self.held)


class Orders:
    def __init__(self, inputs: Inputs, day_fn):
        self.inputs, self.day_fn, self.placed, self.closed, self.n = inputs, day_fn, [], [], 0

    def place(self, body):
        self.n += 1
        sym, q = body["underlying"], body["legs"][0]["quantity"]
        self.placed.append((sym, q, body["client_order_id"]))
        tg = f"TG{self.n}"
        self.inputs.held.append({"trade_group_id": tg, "symbol": sym, "shares": q, "opened": self.day_fn()})
        return {"status": "filled", "order_id": self.n, "fill_price": self.inputs.px[sym], "trade_group_id": tg}

    def close_position(self, tgid, body):
        self.closed.append(tgid)
        self.inputs.held = [l for l in self.inputs.held if l["trade_group_id"] != tgid]
        return {"status": "filled", "order_id": f"c{tgid}"}


def _setup(closes_rows: dict, prices: dict):
    idx = pd.to_datetime(list(closes_rows))
    df = pd.DataFrame(list(closes_rows.values()), index=idx, columns=UNI)
    inp = Inputs(df, prices)
    day = {"d": None}
    orders = Orders(inp, lambda: day["d"])
    alloc = RA.RotationAllocator(MemoryEventStore(), orders, inputs=inp, strategy_factory=Rule)
    return alloc, inp, orders, day


def _at(d: str, hm: str = "15:50") -> pd.Timestamp:
    return pd.Timestamp(f"{d} {hm}", tz=RA.NY)


@pytest.fixture(autouse=True)
def _no_holidays(monkeypatch):
    monkeypatch.setattr(RA, "trading_day", lambda d: d.weekday() < 5)
    monkeypatch.setattr(RA, "previous_trading_day", lambda d: next(d - _dt.timedelta(days=k) for k in range(1, 8)
                                                                   if (d - _dt.timedelta(days=k)).weekday() < 5))


ROWS = {"2026-09-29": [50, 60, 70, 80, 90], "2026-09-30": [100, 90, 80, 70, 60],   # 09-30: AAA, BBB, CCC lead
        "2026-10-01": [60, 70, 80, 90, 100], "2026-10-05": [60, 70, 80, 90, 100]}
PRICES = {"AAA": 100.0, "BBB": 90.0, "CCC": 80.0, "DDD": 70.0, "EEE": 60.0}


def test_the_calendar():
    assert RA.is_month_end(_dt.date(2026, 9, 30)) and not RA.is_month_end(_dt.date(2026, 10, 6))
    assert RA.is_month_end(_dt.date(2026, 10, 30))                       # a Friday; the next session is in November
    assert RA.last_month_end_before(_dt.date(2026, 10, 6)) == _dt.date(2026, 9, 30)
    assert RA.last_month_end_before(_dt.date(2026, 11, 2)) == _dt.date(2026, 10, 30)


def test_the_first_run_buys_the_last_month_ends_picks_and_a_day_is_decided_once():
    alloc, inp, orders, day = _setup(ROWS, PRICES)
    day["d"] = _dt.date(2026, 10, 6)
    r = alloc.run(now=_at("2026-10-06"))
    # ranked on 09-30's closes (AAA, BBB, CCC), not on the later rows that favour EEE/DDD
    assert r["status"] == "rebalanced" and r["verdict"] == "catch_up"
    assert r["detail"]["picks"] == ["AAA", "BBB", "CCC"] and r["detail"]["basis"].startswith("the 2026-09-30")
    assert sorted((s, q) for s, q, _ in orders.placed) == [("AAA", 16), ("BBB", 18), ("CCC", 20)]   # $1,666 each
    assert all(cid.startswith("rotation-2026-10-06-buy-") for _, _, cid in orders.placed)
    again = alloc.run(now=_at("2026-10-06", "15:55"))
    assert again["status"] == "already_decided" and len(orders.placed) == 3


def test_later_days_hold_and_a_weekend_is_no_session():
    alloc, inp, orders, day = _setup(ROWS, PRICES)
    day["d"] = _dt.date(2026, 10, 6)
    alloc.run(now=_at("2026-10-06"))
    day["d"] = _dt.date(2026, 10, 7)
    r = alloc.run(now=_at("2026-10-07"))
    assert r["status"] == "held" and r["verdict"] == "hold" and len(orders.placed) == 3 and not orders.closed
    assert alloc.run(now=_at("2026-10-10"))["status"] == "no_session"    # a Saturday


def test_the_month_end_re_ranks_sells_the_dropped_and_buys_the_new():
    rows = dict(ROWS)
    rows["2026-10-29"] = [100, 90, 80, 70, 60]
    alloc, inp, orders, day = _setup(rows, PRICES)
    day["d"] = _dt.date(2026, 10, 6)
    alloc.run(now=_at("2026-10-06"))                                     # holds AAA 16, BBB 18, CCC 20
    inp.px = {"AAA": 100.0, "BBB": 90.0, "CCC": 50.0, "DDD": 95.0, "EEE": 60.0}   # 10-30 at 15:50: DDD up, CCC down
    day["d"] = _dt.date(2026, 10, 30)
    r = alloc.run(now=_at("2026-10-30"))
    assert r["verdict"] == "month_end" and r["status"] == "rebalanced"
    assert r["detail"]["picks"] == ["AAA", "DDD", "BBB"]
    sold = [l for l in orders.closed]
    assert len(sold) == 1                                                # CCC's lot
    assert ("DDD", 17, "rotation-2026-10-30-buy-DDD") in orders.placed  # floor(1666.67 / 95)
    # AAA and BBB stay: their targets (16, 18) equal what is held, so no resize orders
    assert sum(1 for s, _, cid in orders.placed if cid.startswith("rotation-2026-10-30") and s in ("AAA", "BBB")) == 0


def test_the_plan_never_sells_a_lot_bought_today_and_resizes_only_past_the_threshold():
    today = _dt.date(2026, 10, 30)
    lots = [{"trade_group_id": "T1", "symbol": "XXX", "shares": 10, "opened": today},
            {"trade_group_id": "T2", "symbol": "AAA", "shares": 10, "opened": _dt.date(2026, 10, 6)}]
    p = RA.plan({"AAA": 10, "BBB": 5}, lots, today, {"AAA": 100.0, "BBB": 50.0}, 5000.0, 0.02, resize=True)
    assert p["close"] == [] and p["buy"] == {"BBB": 5} and "XXX" in p["notes"][0]
    small = RA.plan({"AAA": 11}, lots[1:], today, {"AAA": 50.0}, 5000.0, 0.02, resize=True)
    assert small["buy"] == {} and small["close"] == []                   # +1 x $50 < 2% of $5,000
    big = RA.plan({"AAA": 14}, lots[1:], today, {"AAA": 50.0}, 5000.0, 0.02, resize=True)
    assert big["buy"] == {"AAA": 4}
    down = RA.plan({"AAA": 4}, lots[1:], today, {"AAA": 50.0}, 5000.0, 0.02, resize=True)
    assert [l["trade_group_id"] for l in down["close"]] == ["T2"] and down["buy"] == {"AAA": 4}
    assert RA.plan({"AAA": 14}, lots[1:], today, {"AAA": 50.0}, 5000.0, 0.02, resize=False)["buy"] == {}


def test_a_failed_input_is_logged_not_half_done():
    alloc, inp, orders, day = _setup({"2026-09-30": [100, 90, 80, 70, 60]}, PRICES)
    inp.df = inp.df.iloc[:0]
    r = alloc.run(now=_at("2026-10-06"))
    assert r["status"] == "failed" and not orders.placed
    assert alloc.store.decided(RA.PLAYBOOK, _dt.date(2026, 10, 6))["status"] == "failed"
