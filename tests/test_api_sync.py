"""
Data sync (db/sync_jobs.py behind /api/data/sync): the dispatcher's normalised results and progress
adapter, request validation, and a job end to end with the sync itself faked — no vendor is called
and nothing is written.
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()


def test_dispatch_normalises_results_and_progress(monkeypatch):
    import db.sync as S
    from db import sync_jobs as J
    seen = []

    def fake_price(symbol, api_key, from_date=None, to_date=None, progress_cb=None):
        progress_cb("fetching")
        return {"status": "ok", "rows": 12}

    def fake_options(symbol, api_key, from_date=None, to_date=None, progress_cb=None):
        progress_cb("day 3", 3, 4, 100)                              # (message, done, total, rows)
        return {"status": "up_to_date", "rows": 0}

    def boom(**kw):
        raise RuntimeError("vendor down")

    monkeypatch.setattr(S, "sync_price_bars", fake_price)
    monkeypatch.setattr(S, "sync_option_snapshots", fake_options)
    monkeypatch.setattr(S, "sync_vix_bars", boom)
    r = J.run_sync("price", "SPY", date(2026, 9, 1), progress=lambda m, f: seen.append((m, f)))
    assert r["status"] == "ok" and r["rows"] == 12 and seen == [("fetching", None)]
    r = J.run_sync("options", "SPY", progress=lambda m, f: seen.append((m, f)))
    assert r["status"] == "up_to_date" and seen[-1] == ("day 3", 0.75)
    r = J.run_sync("vix")
    assert r["status"] == "error" and "vendor down" in r["detail"] and J.describe(r).startswith("Error")
    assert J.run_sync("price")["status"] == "error"                   # needs a ticker
    assert J.run_sync("nope")["status"] == "error"
    types = {t["data_type"]: t for t in J.sync_types()}
    assert types["price"]["needs_ticker"] and not types["treasury"]["needs_ticker"]


def test_dash_data_manager_uses_the_same_dispatcher(monkeypatch):
    from db import sync_jobs as J
    calls = []
    monkeypatch.setattr(J, "run_sync", lambda *a, **k: calls.append((a, k)) or {"status": "ok", "rows": 5})
    from app.pages.tools.data import _run_sync
    assert _run_sync("price", "SPY", "2026-01-02", []) == ("Done — 5 rows", "")
    assert calls[0][0][:3] == ("price", "SPY", date(2026, 1, 2))
    assert _run_sync("price", "", "2026-01-02", []) == ("Enter a ticker first", "")


def test_sync_request_validation():
    from api.services.sync import SyncRequestError, validate
    ok = validate({"data_type": "price", "tickers": ["spy", "SPY", "^vix"], "from": "2026-09-01"})
    assert ok["tickers"] == ["SPY", "VIX"] and ok["from"] == date(2026, 9, 1)
    assert validate({"data_type": "treasury", "tickers": ["SPY"]})["tickers"] == []   # global dataset
    for bad in ({"data_type": "bogus"}, {"data_type": "price"}, {"data_type": "price", "tickers": ["x y!"]},
                {"data_type": "price", "tickers": ["SPY261030C00770000"]},
                {"data_type": "price", "tickers": ["SPY"], "from": "2026-09-10", "to": "2026-09-01"},
                {"data_type": "price", "tickers": ["SPY"], "from": "soon"}):
        with pytest.raises(SyncRequestError):
            validate(bad)


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


def test_sync_job_end_to_end_with_progress_events(client, monkeypatch):
    from db import sync_jobs as J

    def fake_run(dt, ticker, fd, td, progress=None, **kw):
        progress(f"{ticker} half", 0.5)
        return {"status": "ok" if ticker != "BAD" else "error", "rows": 3 if ticker != "BAD" else 0,
                "detail": "" if ticker != "BAD" else "no such ticker", "raw": {}}

    monkeypatch.setattr(J, "run_sync", fake_run)
    types = client.get("/api/data/sync/types").json()
    assert {"data_type", "label", "needs_ticker"} <= set(types[0])
    assert client.post("/api/data/sync", json={"data_type": "price"}).status_code == 422
    with client.websocket_connect("/api/events") as ws:
        assert ws.receive_json()["type"] == "hello"
        r = client.post("/api/data/sync", json={"data_type": "price", "tickers": ["AAA", "BAD"], "from": "2026-09-01"})
        assert r.status_code == 202
        jid = r.json()["job_id"]
        msgs = []
        deadline = time.time() + 20
        while time.time() < deadline:
            m = ws.receive_json()
            if m["type"] == "job" and m["job"]["id"] == jid:
                msgs.append(m["job"])
                if m["job"]["status"] in ("succeeded", "failed", "cancelled"):
                    break
    assert msgs[-1]["status"] == "succeeded" and msgs[0]["kind"] == "sync"
    assert any("AAA half" in (m["message"] or "") for m in msgs)
    res = client.get(f"/api/jobs/{jid}").json()["result"]
    assert res["rows"] == 3 and res["ok"] == 1 and res["failed"] == 1
    assert [x["ticker"] for x in res["results"]] == ["AAA", "BAD"]
