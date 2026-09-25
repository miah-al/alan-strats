"""
Runner control (/api/runner): reading runner command lines, what the service refuses, and its own
sessions' lifecycle — with a stand-in child process instead of the paper runner, so no session runs,
no broker is called and nothing is written. The process table is only read, and the tests stop only
the stand-ins they started.
"""
from __future__ import annotations

import datetime as _dt
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from alan_trader.strategy_api import registry as R  # noqa: E402
from api.services import runner as RN  # noqa: E402


def test_runner_command_lines_are_read():
    p = RN.parse_runner_cmdline
    assert p(["python", "-m", "scripts.paper_runner", "--strategy", "abc", "--replay", "2026-08-26"]) == \
        {"strategy": "abc", "mode": "replay", "date": "2026-08-26", "ledger": False}
    live = p(["python", "scripts/paper_runner.py", "--strategy=abc", "--no-ledger"])
    assert live["mode"] == "live" and live["ledger"] is False and live["date"] == _dt.date.today().isoformat()
    assert p(["python", "-m", "api.runner_launch", "--strategy", "abc", "--check"])["mode"] == "check"
    assert p(["python", "-m", "api"]) is None and p(["python", "scripts/paper_runner.py"]) is None


def _live_slug():
    for slug in R.STRATEGY_METADATA:
        try:
            if R.get_strategy(slug).live_instrument():
                return slug
        except Exception:
            continue
    return None


SLUG = _live_slug()
needs_live_strategy = pytest.mark.skipif(SLUG is None, reason="no installed strategy has a live session")

_STAND_IN = "import sys, time; print('stand-in runner', sys.argv[1:], flush=True); time.sleep(float(sys.argv[1]))"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    had = db_guard_installed()
    app = create_app()
    mgr = app.state.runner
    mgr.log_dir = tmp_path / "runner_logs"
    delays = {"replay": "0.2", "live": "60"}
    # the runner's argv would go to scripts/paper_runner.py; the stand-in just sleeps (60 s: "live")
    mgr.command = lambda args: [sys.executable, "-c", _STAND_IN,
                                delays["replay" if "--replay" in args else "live"], *args]
    monkeypatch.setattr(RN, "fresh_heartbeats", lambda: {})
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        for ch in list(mgr._children.values()):              # only the stand-ins this test started
            if ch.proc.poll() is None:
                mgr._kill_tree(ch.proc)
        if not had:
            uninstall_db_read_only_guard()


@needs_live_strategy
def test_start_validation(client):
    assert client.post("/api/runner/no_such_strategy/start", json={}).status_code == 404
    for body in ({"mode": "paper"}, {"mode": "replay"}, {"mode": "replay", "date": _dt.date.today().isoformat()},
                 {"mode": "live", "date": "2026-01-02"}):
        r = client.post(f"/api/runner/{SLUG}/start", json=body)
        assert r.status_code == 422, (body, r.text)
    hidden = [s for s in R.STRATEGY_METADATA if s != SLUG]
    no_live = next((s for s in hidden if not R.get_strategy(s).live_instrument()), None)
    if no_live:
        assert client.post(f"/api/runner/{no_live}/start", json={"mode": "replay", "date": "2026-09-01"}).status_code == 422


@needs_live_strategy
def test_the_service_never_starts_a_duplicate_nor_stops_what_it_did_not_start(client, monkeypatch):
    external = [{"strategy": SLUG, "mode": "live", "date": _dt.date.today().isoformat(), "ledger": True, "pid": 424242,
                 "ppid": 1, "started": "2026-09-24T09:25:00-04:00", "cmdline": f"python -m scripts.paper_runner --strategy {SLUG}"}]
    monkeypatch.setattr(RN, "scan_processes", lambda: external)
    r = client.post(f"/api/runner/{SLUG}/start", json={"mode": "replay", "date": "2026-09-23"})
    assert r.status_code == 409 and "424242" in r.json()["detail"]
    r = client.post(f"/api/runner/{SLUG}/stop")
    assert r.status_code == 409 and "never stops" in r.json()["detail"]
    rows = client.get("/api/runner/sessions").json()
    assert rows[0]["managed_by"] == "external" and rows[0]["pid"] == 424242
    monkeypatch.setattr(RN, "fresh_heartbeats", lambda: {SLUG: {"at": "x", "day": "2026-09-24", "state_dir": "elsewhere"}})
    monkeypatch.setattr(RN, "scan_processes", lambda: [])
    r = client.post(f"/api/runner/{SLUG}/start", json={"mode": "replay", "date": "2026-09-23"})
    assert r.status_code == 409 and "heartbeat" in r.json()["detail"]


@needs_live_strategy
def test_the_services_own_sessions_start_run_and_stop(client):
    r = client.post(f"/api/runner/{SLUG}/start", json={"mode": "replay", "date": "2026-09-23"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["managed_by"] == "service" and s["mode"] == "replay" and s["ledger"] is False and s["pid"]
    deadline = time.time() + 20
    while time.time() < deadline:
        row = next(x for x in client.get("/api/runner/sessions").json() if x["pid"] == s["pid"])
        if row["state"] != "running":
            break
        time.sleep(0.2)
    assert row["state"] == "finished" and row["returncode"] == 0
    log = Path(s["log"]).read_text(encoding="utf-8")
    assert "--replay" in log and "2026-09-23" in log and "--log-dir" in log and "--ledger" not in log

    live = client.post(f"/api/runner/{SLUG}/start", json={"mode": "live", "ledger": False}).json()
    assert live["state"] == "running" and live["ledger"] is False
    assert client.post(f"/api/runner/{SLUG}/start", json={"mode": "replay", "date": "2026-09-23"}).status_code == 409
    stopped = client.post(f"/api/runner/{SLUG}/stop").json()
    assert stopped["state"] == "stopped" and stopped["pid"] == live["pid"]
    assert client.post(f"/api/runner/{SLUG}/stop").status_code == 404
    kinds = [x["managed_by"] for x in client.get("/api/runner/sessions").json() if x["strategy"] == SLUG]
    assert kinds.count("service") == 2
