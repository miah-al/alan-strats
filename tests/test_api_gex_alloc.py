"""
The GEX paper allocator (api/services/gex_alloc.py): the VIX variant's state machine against the strategy's own
backtest, the rebalance plan (1% band, whole lots, the one-night ETF rule), and whole days on a synthetic ledger,
fake quotes and a fake order book — nothing is written to the database or the paper account.
"""
from __future__ import annotations

import datetime as _dt
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
for _p in (str(REPO), str(REPO.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.services import gex_alloc as G  # noqa: E402

NY = "America/New_York"
D = _dt.date


def _vix_path(n=320, seed=7):
    """A VIX path that crosses every regime boundary, with some one- and two-day blips."""
    rng = np.random.default_rng(seed)
    base = np.concatenate([np.linspace(13, 35, n // 3), np.linspace(35, 16, n // 3), np.linspace(16, 24, n - 2 * (n // 3))])
    v = base + rng.normal(0, 1.8, n)
    v[50] = 40.0
    v[120:122] = 12.0
    return np.clip(v, 9, 60)


def test_the_vix_state_machine_is_the_backtest():
    s = G.strategy()
    days = pd.bdate_range("2025-01-02", periods=320)
    vix = pd.Series(_vix_path(), index=days)
    price = pd.DataFrame({"close": 500 * np.cumprod(1 + np.random.default_rng(1).normal(0, 0.01, len(days)))},
                         index=days)
    bt = s.backtest(price, {"vix": pd.DataFrame({"close": vix})}, starting_capital=100_000)
    state, path = G.replay(s, G.aligned_vix(list(days), vix))
    assert [p["weight"] for p in path] == pytest.approx(list(bt.extra["spy_weights"].values))
    assert [p["confirmed"] for p in path] == list(bt.extra["regime_series"].values)
    assert len({p["held"] for p in path}) >= 4                              # the path really moves
    # one day at a time from a stored state = the whole replay
    st, _ = G.replay(s, G.aligned_vix(list(days[:200]), vix))
    for d, v in vix.iloc[200:].items():
        st, _ = G.step(st, s, G.vix_regime(s, v), d.date())
    assert st == state


def test_the_plan():
    today = D(2026, 9, 29)
    lots = [{"trade_group_id": "A", "shares": 5, "opened": D(2026, 9, 25)},
            {"trade_group_id": "B", "shares": 28, "opened": D(2026, 9, 28)}]
    assert G.target_shares(0.9, 28883.0, 767.2) == 33 and G.target_shares(0.15, 28883.0, 767.2) == 5
    p = G.plan(33, lots, today, 767.2, 28883.0)
    assert p["action"] == "hold" and p["current"] == 33
    p = G.plan(33, [], today, 767.2, 28883.0)
    assert p["action"] == "rebalance" and p["buy"] == 33 and p["close"] == []
    p = G.plan(33, lots[:1], today, 767.2, 28883.0)
    assert p["buy"] == 28
    p = G.plan(5, lots, today, 767.2, 28883.0)                               # oldest first, then buy back
    assert [l["trade_group_id"] for l in p["close"]] == ["A", "B"] and p["buy"] == 5
    p = G.plan(28, lots, today, 767.2, 28883.0)                              # the 1% band: 5 shares = $3.8k > $289
    assert [l["trade_group_id"] for l in p["close"]] == ["A"] and p["buy"] == 0
    p = G.plan(32, lots, today, 767.2, 28883.0)                              # 1 share = $767 > 1%: close A, buy 4
    assert [l["trade_group_id"] for l in p["close"]] == ["A"] and p["buy"] == 4
    p = G.plan(33, lots, today, 767.2, 2_000_000.0)                           # under 1% of a big account: hold
    assert p["action"] == "hold"
    fresh = [{"trade_group_id": "C", "shares": 30, "opened": today}]
    p = G.plan(5, fresh, today, 767.2, 28883.0)                              # never a lot opened today
    assert p["action"] == "hold" and "holding rule" in p["reason"]


class FakeInputs:
    def __init__(self):
        self.vix = 14.2
        self.net_gex = -5.95e9
        self.price = 767.2
        self.eq = 28883.0
        self.book: dict[str, list[dict]] = {v: [] for v in G.LEDGER.values()}
        days = pd.bdate_range("2024-09-02", "2026-09-24")
        self.hist = pd.Series(np.full(len(days), 14.0), index=days)
        self.hist_calls = 0

    def vix_now(self):
        return self.vix, "fake"

    def spy_price(self):
        return self.price

    def spy_net_gex(self):
        return self.net_gex, "hub:fake"

    def vix_history(self, until, days=G.SEED_DAYS):
        self.hist_calls += 1
        return self.hist[self.hist.index.date <= until]

    def equity(self):
        return self.eq

    def lots(self, name):
        return [dict(l) for l in self.book[name]]


class FakeOrders:
    def __init__(self, inputs: FakeInputs, today):
        self.inputs, self.today, self.calls, self.n = inputs, today, [], 0

    def place(self, body):
        self.calls.append(("place", body))
        self.n += 1
        tg = f"TG{self.n}"
        self.inputs.book[body["strategy"]].append({"trade_group_id": tg, "shares": body["legs"][0]["quantity"],
                                                   "opened": self.today()})
        return {"order_id": self.n, "status": "filled", "fill_price": self.inputs.price, "trade_group_id": tg,
                "message": "filled"}

    def close_position(self, tgid, body):
        self.calls.append(("close", tgid, body))
        for name, lots in self.inputs.book.items():
            self.inputs.book[name] = [l for l in lots if l["trade_group_id"] != tgid]
        self.n += 1
        return {"order_id": self.n, "status": "filled", "fill_price": self.inputs.price, "closes_trade_group_id": tgid}


@pytest.fixture
def alloc():
    inputs = FakeInputs()
    clock = {"t": pd.Timestamp("2026-09-25 15:50", tz=NY)}
    orders = FakeOrders(inputs, lambda: clock["t"].date())
    events = []
    a = G.GexAllocator(None, orders, publish=events.append, store=G.MemoryAllocStore(), inputs=inputs,
                       clock=lambda: clock["t"])
    return a, inputs, orders, clock, events


def test_day_one_opens_both_variants_and_decides_once(alloc):
    a, inputs, orders, clock, events = alloc
    r = a.run("vix")
    assert r["status"] == "rebalanced" and r["regime"] == "HighPositive" and r["weight"] == 0.9
    assert (r["current"], r["target"]) == (0, 33) and r["detail"]["seeded"]["days"] > 400
    assert r["detail"]["raw_regime"] == "HighPositive" and r["detail"]["vix"] == 14.2
    kind, body = orders.calls[-1]
    assert kind == "place" and body["strategy"] == "gex_positioning:vix" and body["order_type"] == "market"
    assert body["legs"] == [{"type": "stock", "side": "buy", "quantity": 33}] and body["account"] == "paper"
    assert body["client_order_id"] == "gexalloc-vix-2026-09-25-buy"
    g = a.run("gex")
    assert g["regime"] == "DeepNegative" and g["weight"] == 0.15 and g["target"] == 5 and g["status"] == "rebalanced"
    assert g["detail"]["net_gex_billions"] == pytest.approx(-5.95)          # $B, as _classify_gex expects
    assert g["detail"]["combined_exposure_x"] == pytest.approx((33 + 5) * 767.2 / 28883.0, abs=1e-3)
    n = len(orders.calls)
    again = a.run("vix")
    assert again["status"] == "already_decided" and len(orders.calls) == n   # one decision a day
    assert [e["type"] for e in events] == ["gex_alloc", "gex_alloc"] and events[0]["orders"][0]["side"] == "buy"
    log = a.log(5)
    assert [(d["variant"], d["status"]) for d in log["decisions"]] == [("gex", "rebalanced"), ("vix", "rebalanced")]
    st = a.status("vix")
    assert st["shares"] == 33 and st["state"]["held"] == "HighPositive" and st["last_decision"]["target"] == 33


def test_the_following_days(alloc):
    a, inputs, orders, clock, events = alloc
    a.run("vix"), a.run("gex")
    # Monday: VIX jumps to 25 (raw Negative) — the 3-day confirmation holds the regime: no trade
    clock["t"] = pd.Timestamp("2026-09-28 15:50", tz=NY)
    inputs.hist.loc[pd.Timestamp("2026-09-25")] = 14.2                     # Friday's stored close
    inputs.vix = 25.0
    r = a.run("vix")
    assert r["status"] == "held" and r["regime"] == "HighPositive" and r["detail"]["raw_regime"] == "Negative"
    assert r["detail"]["streak"] == 1 and "caught_up" not in r["detail"]     # the state was already at Friday
    # the GEX variant follows GEX at once: +4 $B -> HighPositive 90%: buys 28 more
    inputs.net_gex = 4e9
    g = a.run("gex")
    assert g["regime"] == "HighPositive" and g["target"] == 33 and orders.calls[-1][1]["legs"][0]["quantity"] == 28
    # Tuesday: GEX deeply negative again -> 5 shares: the oldest lots go first, then 5 are bought back
    clock["t"] = pd.Timestamp("2026-09-29 15:50", tz=NY)
    inputs.net_gex = -5e9
    g = a.run("gex")
    closes = [c for c in orders.calls if c[0] == "close"]
    assert g["status"] == "rebalanced" and len(closes) == 2 and orders.calls[-1][1]["legs"][0]["quantity"] == 5
    assert sum(l["shares"] for l in inputs.book["gex_positioning:gex"]) == 5
    # the VIX variant after 3 days of VIX 25 (with the cooldown long passed) switches to Negative 35%
    inputs.vix = 25.0
    r = a.run("vix")
    assert r["regime"] == "HighPositive" and r["detail"]["streak"] == 2
    clock["t"] = pd.Timestamp("2026-09-30 15:50", tz=NY)
    r = a.run("vix")
    assert r["regime"] == "Negative" and r["weight"] == 0.35 and r["detail"]["regime_changed"] is True
    assert r["target"] == math.floor(0.35 * 28883.0 / 767.2) and r["status"] == "rebalanced"


def test_a_failed_input_is_logged_not_traded(alloc):
    a, inputs, orders, clock, events = alloc
    inputs.vix = None
    r = a.run("vix")
    assert r["status"] == "failed" and "VIX" in r["summary"] and orders.calls == []
    assert events[-1]["status"] == "failed"


def test_armed_through_the_scheduler(alloc, tmp_path):
    from api.services import arms as A
    from api.services import runner as RN
    a, inputs, orders, clock, events = alloc
    sched = A.ArmScheduler(A.MemoryArmStore(), RN.RunnerManager(log_dir=tmp_path), publish=events.append,
                           clock=lambda: clock["t"], launcher=lambda s: (_ for _ in ()).throw(AssertionError("no script")),
                           allocator=a)
    clock["t"] = pd.Timestamp("2026-09-25 09:00", tz=NY)
    rows = sched.arm("gex_positioning", "once", "2026-09-25", "both")
    assert [(r["variant"], r["next_run"]) for r in rows] == [("vix", "2026-09-25T15:50:00-04:00"),
                                                             ("gex", "2026-09-25T15:50:00-04:00")]
    assert sched.tick(pd.Timestamp("2026-09-25 15:49", tz=NY)) == []
    evs = sched.tick(pd.Timestamp("2026-09-25 15:50:10", tz=NY))
    assert [e["event"] for e in evs] == ["ran", "ran"] and {e["variant"] for e in evs} == {"vix", "gex"}
    arms = {r["variant"]: r for r in sched.arms()}
    assert arms["vix"]["last_result"].startswith("ran: vix: HighPositive 90%") and arms["vix"]["next_run"] is None
    assert arms["gex"]["status"]["shares"] == 5 and arms["gex"]["kind"] == "allocator"
    assert sched.tick(pd.Timestamp("2026-09-25 15:51", tz=NY)) == []           # once a day


def test_the_log_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    had = db_guard_installed()
    try:
        app = create_app()
        inputs = FakeInputs()
        al = app.state.gex_allocator
        assert isinstance(al.store, G.MemoryAllocStore)
        al.inputs = inputs
        al.orders = FakeOrders(inputs, lambda: D(2026, 9, 25))
        al.clock = lambda: pd.Timestamp("2026-09-25 15:50", tz=NY)
        al.run("gex")
        with TestClient(app) as c:
            j = c.get("/api/runner/gex_positioning/log?days=3").json()
            assert j["decisions"][0]["variant"] == "gex" and j["table"]["rows"][0]["target"] == 5
            assert c.get("/api/runner/ndx_0dte_tasty/log").status_code == 404
            r = c.post("/api/runner/gex_positioning/arm", json={"schedule": "once", "date": "2026-10-01",
                                                                 "variant": "both"})
            assert r.status_code == 200 and [x["variant"] for x in r.json()] == ["vix", "gex"]
            assert c.post("/api/runner/gex_positioning/arm", json={"variant": "spx"}).status_code == 422
    finally:
        if not had:
            uninstall_db_read_only_guard()


def _db_ok() -> bool:
    try:
        from api.services.db import ping
        return ping()[0]
    except Exception:
        return False


@pytest.mark.skipif(not _db_ok(), reason="AlanStrats database unreachable")
def test_the_db_store_round_trip():
    """app.GexAllocState / app.GexAllocLog under a throwaway variant name (deleted afterwards)."""
    import uuid
    from sqlalchemy import text
    from api.bootstrap import db_guard_installed, install_db_read_only_guard, uninstall_db_read_only_guard
    from api.services.db import require_db
    had = db_guard_installed()
    install_db_read_only_guard()
    v = f"zz{uuid.uuid4().hex[:6]}"
    st = G.DbAllocStore()
    try:
        assert st.get_state(v) is None
        st.put_state(v, {"held": "Neutral", "asof": "2026-09-24"})
        st.put_state(v, {"held": "HighPositive", "asof": "2026-09-25"})
        assert st.get_state(v) == {"held": "HighPositive", "asof": "2026-09-25"}
        row = {"variant": v, "date": D(2026, 9, 25), "status": "held", "regime": "HighPositive", "weight": 0.9,
               "equity": 28883.0, "price": 767.2, "current": 33, "target": 33, "detail": {"plan": "x"}}
        assert st.add_log(row) is True and st.add_log(row) is False            # one decision a day
        got = st.decided(v, D(2026, 9, 25))
        assert got["status"] == "held" and got["detail"] == {"plan": "x"} and got["target"] == 33
        assert any(r["variant"] == v for r in st.recent(D(2026, 9, 20)))
    finally:
        with require_db().begin() as c:
            c.execute(text("DELETE FROM app.GexAllocLog WHERE Variant = :v"), {"v": v})
            c.execute(text("DELETE FROM app.GexAllocState WHERE Variant = :v"), {"v": v})
        if not had:
            uninstall_db_read_only_guard()
