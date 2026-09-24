"""
Watchlists and alerts (app.Watchlist, app.Alert): the firing rules on their own, and against the
database with a fake quote provider — the alert fires on /api/events. Every watchlist / alert a test
creates is named or noted ``zz-test`` and deleted at the end.
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for _p in (str(REPO), str(REPO.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.marketdata.limits import ProviderLimits, ProviderPolicy  # noqa: E402
from api.marketdata.providers.base import Provider  # noqa: E402
from api.services.alerts import AlertEngine, AlertError, validate  # noqa: E402

SYM_T = "ZZQB"


def test_alert_rules():
    chk = AlertEngine.check
    assert chk(">", 100, None, 101, None) == (True, True)
    assert chk(">", 100, 101, 102, True) == (False, True)            # stays true: no repeat
    assert chk(">", 100, 102, 99, True) == (False, False)
    assert chk(">", 100, 99, 100.5, False) == (True, True)            # true again: fires again
    assert chk("<", 100, None, 99, None) == (True, True)
    assert chk("crosses_above", 100, None, 101, None) == (False, None)  # first value: baseline only
    assert chk("crosses_above", 100, 99, 101, None) == (True, None)
    assert chk("crosses_above", 100, 101, 102, None) == (False, None)
    assert chk("crosses_below", 100, 101, 99, None) == (True, None)
    assert chk("crosses_below", 100, 100, 99.9, None) == (True, None)


def test_alert_validation():
    assert validate({"symbol": "^vix", "field": "last", "op": ">", "value": 20})["symbol"] == "VIX"
    for bad in ({"symbol": "", "op": ">", "value": 1}, {"symbol": "SPY", "op": "==", "value": 1},
                {"symbol": "SPY", "field": "volume", "op": ">", "value": 1}, {"symbol": "SPY", "op": ">", "value": "x"}):
        with pytest.raises(AlertError):
            validate(bad)


def _db_ok() -> bool:
    try:
        from api.services.db import ping
        return ping()[0]
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _db_ok(), reason="AlanStrats database unreachable")


class Feed(Provider):
    name = "fakefeed"
    streaming = True
    capabilities = frozenset({"quotes"})

    def __init__(self):
        super().__init__(ProviderLimits(ProviderPolicy(self.name, per_min=6000, per_day=100000, burst=1000)))

    def supports(self, s):
        return s.startswith("ZZQ")

    def subscribe(self, syms):
        pass

    def unsubscribe(self, syms):
        pass


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    had = db_guard_installed()
    app = create_app()
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        if not had:
            uninstall_db_read_only_guard()


@needs_db
def test_watchlist_crud(client):
    name = f"zz-test {uuid.uuid4().hex[:6]}"
    try:
        r = client.put(f"/api/watchlists/{name}", json={"symbols": ["spy", "^VIX", "SPY", "O:SPY261030C00770000"]})
        assert r.status_code == 200, r.text
        assert r.json()["symbols"] == ["SPY", "VIX", "SPY261030C00770000"]
        assert name in [w["name"] for w in client.get("/api/watchlists").json()]
        r = client.put(f"/api/watchlists/{name}", json={"symbols": ["QQQ"]})
        assert r.json()["symbols"] == ["QQQ"]
        assert client.put(f"/api/watchlists/{name}", json={"symbols": ["not a symbol!"]}).status_code == 422
        assert client.get(f"/api/watchlists/{name}").json()["symbols"] == ["QQQ"]
    finally:
        client.delete(f"/api/watchlists/{name}")
    assert client.delete(f"/api/watchlists/{name}").status_code == 404
    assert name not in [w["name"] for w in client.get("/api/watchlists").json()]


@needs_db
def test_alert_fires_on_the_event_stream(client):
    hub = client.app.state.market
    feed = Feed()
    hub.add_provider(feed, first=True)
    created = []
    try:
        hub.emit(SYM_T, feed.name, time.time(), last=99.0, prev_close=98.0)
        a = client.post("/api/alerts", json={"symbol": SYM_T, "field": "last", "op": "crosses_above", "value": 100,
                                             "note": "zz-test cross", "once": True}).json()
        created.append(a["id"])
        b = client.post("/api/alerts", json={"symbol": SYM_T, "field": "change_pct", "op": ">", "value": 5,
                                             "note": "zz-test pct", "once": False}).json()
        created.append(b["id"])
        assert {a["field"], b["field"]} == {"last", "change_pct"} and a["active"] and not b["once"]
        assert client.post("/api/alerts", json={"symbol": SYM_T, "op": "=", "value": 1}).status_code == 422
        with client.websocket_connect("/api/events") as ws:
            assert ws.receive_json()["type"] == "hello"
            hub.emit(SYM_T, feed.name, time.time(), last=99.5)          # baseline for the cross
            time.sleep(0.4)
            hub.emit(SYM_T, feed.name, time.time(), last=101.0)         # crosses 100; change +3.06%: no pct alert
            got = []
            deadline = time.time() + 15
            while time.time() < deadline and not got:
                m = ws.receive_json()
                if m["type"] == "alert":
                    got.append(m)
            assert got and got[0]["alert"]["id"] == a["id"] and got[0]["value"] == pytest.approx(101.0)
            assert set(got[0]) >= {"type", "alert", "value", "time"}
            time.sleep(0.4)
            hub.emit(SYM_T, feed.name, time.time(), last=104.0)          # +6.1%: the level alert fires
            deadline = time.time() + 15
            pct = None
            while time.time() < deadline and pct is None:
                m = ws.receive_json()
                if m["type"] == "alert" and m["alert"]["id"] == b["id"]:
                    pct = m
            assert pct is not None and pct["value"] == pytest.approx((104 - 98) / 98 * 100)
        listed = {x["id"]: x for x in client.get("/api/alerts").json()}
        assert listed[a["id"]]["active"] is False and listed[a["id"]]["triggered"]            # once: done
        assert listed[b["id"]]["active"] is True and listed[b["id"]]["trigger_count"] == 1
    finally:
        for i in created:
            client.delete(f"/api/alerts/{i}")
        hub.providers.remove(feed)
        hub.by_name.pop(feed.name, None)
    assert client.delete(f"/api/alerts/{created[0]}").status_code == 404
