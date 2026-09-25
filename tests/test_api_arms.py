"""
Arming scheduled paper runs (api/services/arms.py): the schedule, late starts, missed days, the "already
running" rule, the claim that stops a double start, adoption after a restart and the kill switch — on a fake
clock, an in-memory arm store and a stand-in process (a sleeping python the test starts and stops itself) in
place of the scheduled task's script. No paper run is launched, nothing is written to the database.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.services import arms as A  # noqa: E402
from api.services import runner as RN  # noqa: E402

NY = "America/New_York"


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz=NY)


def iso(s: str) -> str:
    return ts(s).isoformat()


class Clock:
    def __init__(self, t: str):
        self.t = ts(t)

    def __call__(self):
        return self.t


@pytest.fixture
def rig(tmp_path, monkeypatch):
    import psutil
    monkeypatch.setattr(RN, "scan_processes", lambda: [])
    monkeypatch.setattr(RN, "fresh_heartbeats", lambda: {})
    procs, events = [], []

    def launcher(strategy):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        procs.append(p)
        log = tmp_path / f"{strategy}_{len(procs)}.log"
        return {"pid": p.pid, "created": psutil.Process(p.pid).create_time(), "log": str(log),
                "exit_file": f"{log}.exit", "cmdline": "stand-in", "task_command": A.task_command(strategy, tmp_path)}

    runners = RN.RunnerManager(publish=events.append, log_dir=tmp_path / "logs")
    clock = Clock("2026-09-25 09:00")                      # a Friday
    store = A.MemoryArmStore()
    sched = A.ArmScheduler(store, runners, publish=events.append, clock=clock, launcher=launcher)
    yield sched, runners, store, clock, events, procs
    for p in procs:                                        # only the stand-ins this test started
        if p.poll() is None:
            p.kill()
            p.wait(5)


def _wait_state(runners, strategy, state, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        runners._poll()
        rows = [c for c in runners._children.values() if c.strategy == strategy]
        if rows and rows[-1].state == state:
            return rows[-1]
        time.sleep(0.2)
    raise AssertionError(f"{strategy} never reached {state}")


def test_the_task_command_is_the_scheduled_tasks(tmp_path):
    cmd = A.task_command("ndx_0dte_tasty", Path(r"D:\Work\Project Dream\alan_trader"))
    assert cmd == ('powershell -NoProfile -ExecutionPolicy Bypass -File '
                   '"D:\\Work\\Project Dream\\alan_trader\\scripts\\start_paper_runner.ps1" -Strategy ndx_0dte_tasty')
    w = A.wrapped_command("ndx_0dte_tasty", Path(r"C:\logs\x.log"), Path(r"D:\Work\Project Dream\alan_trader"))
    assert w.startswith('cmd.exe /d /v:on /s /c "powershell -NoProfile') and w.endswith('> "C:\\logs\\x.log.exit""')
    assert '> "C:\\logs\\x.log" 2>&1 & echo !ERRORLEVEL!' in w
    # the script is a runner of its strategy from the moment it starts (and of ndx_0dte_tasty by default)
    p = RN.parse_runner_cmdline
    assert p(["powershell", "-File", r"D:\x\scripts\start_paper_runner.ps1", "-Strategy", "abc"])["strategy"] == "abc"
    assert p(["powershell", "-File", r"D:\x\scripts\start_paper_runner.ps1"])["strategy"] == "ndx_0dte_tasty"
    assert p(["cmd.exe", "/c", w])["kind"] == "task_script"
    # a shell or an editor that merely mentions the script (or a runner) is not a runner
    assert p(["bash", "-c", "grep start_paper_runner.ps1 -Strategy x; python -m scripts.paper_runner --strategy x"]) is None
    assert p(["powershell", "-Command", "Get-Content start_paper_runner.ps1"]) is None
    assert p([r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-File",
              r"D:\x\scripts\start_paper_runner.ps1"])["kind"] == "task_script"


def test_arm_run_stop_and_the_next_day(rig):
    sched, runners, store, clock, events, procs = rig
    [row] = sched.arm("ndx_0dte_tasty", "weekdays")
    assert row["next_run"] == iso("2026-09-25 10:30") and row["mode"] == "paper" and row["variant"] is None
    assert events[-1]["type"] == "arm" and events[-1]["event"] == "armed"
    assert sched.tick(ts("2026-09-25 10:29:50")) == [] and not procs
    [ev] = sched.tick(ts("2026-09-25 10:30:05"))
    assert ev["event"] == "started" and ev["late"] is False and "late" not in ev["detail"] and len(procs) == 1
    assert ev["command"].endswith("start_paper_runner.ps1\" -Strategy ndx_0dte_tasty")
    assert sched.tick(ts("2026-09-25 10:30:20")) == [] and len(procs) == 1         # the day is claimed
    [a] = sched.arms()
    assert a["running"] is True and a["pid"] == procs[0].pid and a["last_result"].startswith("started (pid")
    s = next(x for x in runners.sessions() if x["pid"] == procs[0].pid)
    assert s["managed_by"] == "service" and s["kind"] == "task_script" and s["launched_by"] == "arm"
    stopped = runners.stop_all()                                                    # the kill switch
    assert [x["state"] for x in stopped] == ["stopped"] and procs[0].wait(10) is not None
    assert store.active()[0]["last_result"].startswith("stopped at")
    assert any(e.get("event") == "stopped" for e in events)
    clock.t = ts("2026-09-25 17:00")
    assert sched.arms()[0]["next_run"] == iso("2026-09-28 10:30")                  # Monday
    assert sched.tick(ts("2026-09-26 10:31")) == []                               # Saturday: nothing
    [ev] = sched.tick(ts("2026-09-28 11:12"))                                     # the service came up late
    assert ev["event"] == "started" and "late at 11:12 ET" in ev["detail"] and ev["late"] is True
    runners.stop("ndx_0dte_tasty")


def test_missed_skipped_and_never_twice(rig, monkeypatch):
    sched, runners, store, clock, events, procs = rig
    sched.arm("ndx_0dte_tasty", "weekdays")
    [ev] = sched.tick(ts("2026-09-25 16:05"))                                     # up after the window
    assert ev["event"] == "missed" and store.active()[0]["last_result"].startswith("missed") and not procs
    # a runner already running anywhere: the day is skipped
    ext = [{"strategy": "ndx_0dte_tasty", "mode": "live", "date": "2026-09-28", "ledger": True, "pid": 4242,
            "ppid": 1, "started": "x", "cmdline": "powershell -File start_paper_runner.ps1"}]
    monkeypatch.setattr(RN, "scan_processes", lambda: ext)
    [ev] = sched.tick(ts("2026-09-28 10:30:01"))
    assert ev["event"] == "skipped" and "already running (external, pid 4242)" in ev["detail"] and not procs
    monkeypatch.setattr(RN, "scan_processes", lambda: [])
    # a second service process on the same arms: only one of them starts the day
    other = A.ArmScheduler(store, RN.RunnerManager(log_dir=runners.log_dir), clock=sched.clock,
                           launcher=sched.launcher)
    got = sched.tick(ts("2026-09-29 10:30:02")) + other.tick(ts("2026-09-29 10:30:03"))
    assert [e["event"] for e in got] == ["started"] and len(procs) == 1
    runners.stop("ndx_0dte_tasty")
    # armed after today's window: today is not "missed"
    sched.disarm("ndx_0dte_tasty")
    sched.arm("ndx_0dte_tasty", "weekdays")
    store._rows[max(store._rows)]["armed_at"] = ts("2026-09-30 20:30").tz_convert("UTC").tz_localize(None)
    assert sched.tick(ts("2026-09-30 20:31")) == []


def test_once_arms_and_validation(rig):
    sched, runners, store, clock, events, procs = rig
    with pytest.raises(A.ArmError):
        sched.arm("no_such", "weekdays")
    with pytest.raises(A.ArmError):
        sched.arm("ndx_0dte_tasty", "weekdays", variant="vix")                    # no variants
    with pytest.raises(A.ArmError):
        sched.arm("ndx_0dte_tasty", "once", "2026-11-26")                         # Thanksgiving
    with pytest.raises(A.ArmError):
        sched.arm("ndx_0dte_tasty", "once", "2026-09-24")                         # the past
    with pytest.raises(A.ArmError):
        sched.arm("ndx_0dte_tasty", "daily")
    with pytest.raises(A.ArmError):
        sched.arm("gex_positioning", "weekdays", variant="vix")                    # no allocator in this rig
    [row] = sched.arm("ndx_0dte_tasty", "once")                                    # the next session: today
    assert row["date"] == "2026-09-25" and row["next_run"] == iso("2026-09-25 10:30")
    [row] = sched.arm("ndx_0dte_tasty", "once", "2026-09-29")                      # re-arming replaces it
    assert len(store.active()) == 1 and row["next_run"] == iso("2026-09-29 10:30")
    assert sched.tick(ts("2026-09-28 10:31")) == []                               # not its day
    [ev] = sched.tick(ts("2026-09-30 09:00"))                                     # its day passed unseen
    assert ev["event"] == "missed" and sched.arms()[0]["next_run"] is None
    assert sched.disarm("ndx_0dte_tasty")[0]["active"] is False and sched.arms() == []
    assert events[-1]["event"] == "disarmed"


def test_a_restarted_service_adopts_its_running_session(rig):
    sched, runners, store, clock, events, procs = rig
    sched.arm("ndx_0dte_tasty", "weekdays")
    sched.tick(ts("2026-09-25 10:30:05"))
    pid = procs[0].pid
    # a new service process (the old one's session keeps running)
    runners2 = RN.RunnerManager(log_dir=runners.log_dir)
    sched2 = A.ArmScheduler(store, runners2, clock=sched.clock, launcher=sched.launcher)
    assert sched2.adopt_running() == 1
    assert runners2.mine_running("ndx_0dte_tasty").proc.pid == pid
    assert runners2.running_elsewhere("ndx_0dte_tasty") is None                   # its own, not external
    runners2.stop("ndx_0dte_tasty")
    assert procs[0].wait(10) is not None and store.active()[0]["last_result"].startswith("stopped at")


def test_the_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.bootstrap import db_guard_installed, uninstall_db_read_only_guard
    monkeypatch.setattr(RN, "scan_processes", lambda: [])
    monkeypatch.setattr(RN, "fresh_heartbeats", lambda: {})
    had = db_guard_installed()
    try:
        app = create_app()
        assert isinstance(app.state.arms.store, A.MemoryArmStore)                 # the suite never persists arms
        app.state.arms.launcher = lambda s: (_ for _ in ()).throw(AssertionError("nothing is launched here"))
        with TestClient(app) as c:
            r = c.post("/api/runner/ndx_0dte_tasty/arm", json={"schedule": "weekdays"})
            assert r.status_code == 200 and r.json()[0]["schedule"] == "weekdays" and r.json()[0]["mode"] == "paper"
            rows = c.get("/api/runner/arms").json()
            assert [(x["strategy"], x["schedule"]) for x in rows] == [("ndx_0dte_tasty", "weekdays")]
            assert set(rows[0]) >= {"strategy", "variant", "schedule", "date", "mode", "armed_at", "next_run",
                                    "last_run", "last_result"}
            assert c.post("/api/runner/ndx_0dte_tasty/arm", json={"schedule": "sometimes"}).status_code == 422
            assert c.post("/api/runner/nope/arm", json={}).status_code == 422
            assert c.delete("/api/runner/ndx_0dte_tasty/arm").status_code == 200
            assert c.delete("/api/runner/ndx_0dte_tasty/arm").status_code == 404
            assert c.post("/api/runner/stop-all").json() == {"stopped": []}
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
    """app.RunnerArm with a throwaway strategy name no scheduler knows (so nothing could ever start it);
    the rows are deleted afterwards."""
    import datetime as _dt
    import uuid
    from sqlalchemy import text
    from api.bootstrap import db_guard_installed, install_db_read_only_guard, uninstall_db_read_only_guard
    from api.services.db import require_db
    had = db_guard_installed()
    install_db_read_only_guard()
    name = f"zz_arm_test_{uuid.uuid4().hex[:8]}"
    st = A.DbArmStore()
    try:
        r = st.arm(name, "vix", "weekdays", None)
        assert r["strategy"] == name and r["variant"] == "vix" and r["schedule"] == "weekdays" and r["date"] is None
        r2 = st.arm(name, "vix", "once", _dt.date(2026, 9, 25))                # re-arm: the same active row
        assert r2["id"] == r["id"] and r2["schedule"] == "once" and r2["date"] == _dt.date(2026, 9, 25)
        st.arm(name, "gex", "weekdays", None)
        assert st.claim(r["id"], _dt.date(2026, 9, 25), "starting") is True
        assert st.claim(r["id"], _dt.date(2026, 9, 25), "starting") is False   # the day is taken
        st.record(r["id"], "started (pid 1)", pid=1, created=123.5, log="x.log")
        mine = {a["variant"]: a for a in st.active() if a["strategy"] == name}
        assert mine["vix"]["last_result"] == "started (pid 1)" and mine["vix"]["run_created"] == 123.5
        assert mine["vix"]["last_run_date"] == _dt.date(2026, 9, 25)
        st.record(r["id"], "stopped at 11:00 ET", keep_run=True)
        assert {a["variant"]: a for a in st.active() if a["strategy"] == name}["vix"]["run_pid"] == 1
        assert [x["variant"] for x in st.disarm(name, "gex")] == ["gex"]
        assert [x["variant"] for x in st.disarm(name)] == ["vix"]
        assert not [a for a in st.active() if a["strategy"] == name]
    finally:
        with require_db().begin() as c:
            c.execute(text("DELETE FROM app.RunnerArm WHERE Strategy = :s"), {"s": name})
        if not had:
            uninstall_db_read_only_guard()
