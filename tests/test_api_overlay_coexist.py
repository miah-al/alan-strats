"""Strategy overlays (api/bootstrap.py) and a second paper runner beside the NDX one: the arm for ndx_gamma_walls,
runner detection that keeps the two apart, one broker budget across checkouts, and the account's day balance
written last with every runner's P&L. No runner is started, no broker is called, nothing is written."""
from __future__ import annotations

import datetime as _dt
import json
import sys
import textwrap
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:      # only the checkout: its parent holds the live alan_trader (conftest binds ours by path)
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api import bootstrap as B  # noqa: E402
from api.services import arms as A  # noqa: E402
from api.services import runner as RN  # noqa: E402

NY = "America/New_York"


def _overlay(tmp_path: Path, slug: str) -> Path:
    folder = tmp_path / "strategies" / slug
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text("", encoding="utf-8")
    (folder / "meta.py").write_text(textwrap.dedent(f'''
        METADATA = {{"display_name": "Overlay test", "type": "rule", "status": "active", "ui_visible": True,
                     "class_path": "alan_trader_strategies.strategies.{slug}.strategy.S"}}
    '''), encoding="utf-8")
    (folder / "strategy.py").write_text(textwrap.dedent('''
        from alan_trader.strategy_api.base import BaseStrategy, SignalResult

        class S(BaseStrategy):
            name = "overlay"
            def generate_signal(self, snap): return SignalResult("overlay", "HOLD", 0.0, 0.0, {})
            def backtest(self, *a, **k): raise ValueError("no")
            def get_params(self): return {}
            def live_instrument(self): return {"underlying": "NDX", "root": "NDXP"}
    '''), encoding="utf-8")
    (folder / "guide.md").write_text("# overlay\n", encoding="utf-8")
    return folder


def test_an_overlay_strategy_is_registered_without_touching_the_plugin_checkout(tmp_path, monkeypatch):
    import alan_trader_strategies as P
    from strategy_api import registry as R
    if "ndx_0dte_tasty" not in P.STRATEGY_METADATA:
        pytest.skip("the plugin checkout has no ndx_0dte_tasty")
    slug = "zz_overlay_test"
    folder = _overlay(tmp_path, slug)
    pkg = sys.modules["alan_trader_strategies.strategies"]
    before = list(pkg.__path__)
    try:
        assert B.apply_overlays([folder]) == [slug]
        R.reload()
        s = R.get_strategy(slug)
        assert type(s).__name__ == "S" and s.live_instrument()["root"] == "NDXP"
        meta = R.STRATEGY_METADATA[slug]
        assert meta["overlay"] == str(folder) and meta["guide_path"].endswith("guide.md") and meta["status"] == "active"
        # the plugin's own strategies still come from its own checkout, and a slug it has is never replaced
        assert str(Path(P.__file__).parent) in str(sys.modules["alan_trader_strategies.strategies.ndx_0dte_tasty"].__file__) \
            if "alan_trader_strategies.strategies.ndx_0dte_tasty" in sys.modules else True
        clash = _overlay(tmp_path / "x", "ndx_0dte_tasty")
        assert B.apply_overlays([clash]) == []
        assert B.apply_overlays([tmp_path / "nothing_here"]) == []
        # the setting: the environment, else strategy_overlays.txt in the checkout
        monkeypatch.setenv(B.ENV_OVERLAYS, str(folder))
        assert B.overlay_folders() == [folder]
    finally:
        P.STRATEGY_METADATA.pop(slug, None)
        pkg.__path__[:] = before
        for m in [m for m in sys.modules if m.startswith(f"alan_trader_strategies.strategies.{slug}")]:
            sys.modules.pop(m, None)
        R.reload()


def test_the_walls_runner_is_not_the_ndx_runner(monkeypatch):
    walls = {"strategy": "ndx_gamma_walls", "mode": "live", "date": "2026-09-25", "ledger": True, "pid": 5151,
             "ppid": 1, "started": "x", "cmdline": "python -m api.runner_launch --strategy ndx_gamma_walls --poll 15"}
    monkeypatch.setattr(RN, "scan_processes", lambda: [walls])
    monkeypatch.setattr(RN, "fresh_heartbeats", lambda: {})
    mgr = RN.RunnerManager()
    assert mgr.running_elsewhere("ndx_0dte_tasty") is None                    # (a): the NDX arm is not skipped
    assert mgr.running_elsewhere("ndx_gamma_walls")["pid"] == 5151
    p = RN.parse_runner_cmdline(["python", "-m", "api.runner_launch", "--strategy", "ndx_gamma_walls", "--poll", "15"])
    assert p["strategy"] == "ndx_gamma_walls" and p["mode"] == "live" and "kind" not in p


def test_the_arm_starts_the_runner_from_this_checkout(tmp_path, monkeypatch):
    import psutil
    import subprocess
    monkeypatch.setattr(RN, "scan_processes", lambda: [])
    monkeypatch.setattr(RN, "fresh_heartbeats", lambda: {})
    spec = A.SPECS["ndx_gamma_walls"]
    assert spec.kind == "runner" and spec.at == _dt.time(9, 25) and spec.until == _dt.time(15, 0)
    cmd = A.runner_command("ndx_gamma_walls", Path(r"C:\l\w.log"), Path(r"C:\csv dir"), py=r"D:\v env\python.exe")
    assert cmd == ('cmd.exe /d /v:on /s /c ""D:\\v env\\python.exe" -m api.runner_launch --strategy ndx_gamma_walls '
                   '--poll 15 --log-dir "C:\\csv dir" > "C:\\l\\w.log" 2>&1 & echo !ERRORLEVEL! > "C:\\l\\w.log.exit""')
    procs = []

    def runner_launcher(strategy):
        pr = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        procs.append(pr)
        return {"pid": pr.pid, "created": psutil.Process(pr.pid).create_time(), "log": str(tmp_path / "r.log"),
                "exit_file": str(tmp_path / "r.log.exit"), "cmdline": "stand-in", "task_command": "stand-in"}
    runners = RN.RunnerManager(log_dir=tmp_path)
    clock = {"t": pd.Timestamp("2026-09-25 08:00", tz=NY)}
    sched = A.ArmScheduler(A.MemoryArmStore(), runners, clock=lambda: clock["t"],
                           launcher=lambda s: (_ for _ in ()).throw(AssertionError("not the task script")),
                           runner_launcher=runner_launcher)
    try:
        [row] = sched.arm("ndx_gamma_walls", "weekdays")
        assert row["next_run"] == "2026-09-25T09:25:00-04:00" and row["kind"] == "runner"
        assert sched.tick(pd.Timestamp("2026-09-25 09:24", tz=NY)) == []
        [ev] = sched.tick(pd.Timestamp("2026-09-25 09:25:05", tz=NY))
        assert ev["event"] == "started" and len(procs) == 1
        s = next(x for x in runners.sessions() if x["pid"] == procs[0].pid)
        assert s["kind"] == "runner" and s["launched_by"] == "arm" and s["managed_by"] == "service"
        # the NDX arm, due at 10:30, still starts: the walls runner is not its runner
        assert runners.running_elsewhere("ndx_0dte_tasty") is None
        assert sched.tick(pd.Timestamp("2026-09-28 15:00", tz=NY))[0]["event"] == "missed"   # after 15:00: missed
    finally:
        runners.stop_all()
        for pr in procs:
            if pr.poll() is None:
                pr.kill()
                pr.wait(5)


def test_friend_starts_before_its_gap_down_entries():
    """Friend trades from 10:00 after a gap-down (its gap_down_early_pct, 2026-10-02), so its run starts at 09:50 every
    day; the strategy keeps its 13:00 start on other days."""
    friend = A.SPECS["ndx_0dte_friend"]
    assert friend.kind == "script" and friend.at == _dt.time(9, 50) and friend.until == _dt.time(15, 30)
    sched = A.ArmScheduler(A.MemoryArmStore(), RN.RunnerManager(), clock=lambda: pd.Timestamp("2026-10-02 20:00", tz=NY),
                           launcher=lambda s: {}, runner_launcher=lambda s: {})
    [row] = sched.arm("ndx_0dte_friend", "weekdays")
    assert row["next_run"] == "2026-10-05T09:50:00-04:00"


def test_friend_w50_arms_beside_friend_and_is_never_taken_for_it():
    """The 50-wide Friend (2026-10-04) runs beside the 100-wide: the same start script, start and window, its own arm,
    and a runner of one is never read as the other ('ndx_0dte_friend' is the start of 'ndx_0dte_friend_w50')."""
    w50, friend = A.SPECS["ndx_0dte_friend_w50"], A.SPECS["ndx_0dte_friend"]
    assert (w50.kind, w50.at, w50.until, w50.variants) == (friend.kind, friend.at, friend.until, friend.variants)
    sched = A.ArmScheduler(A.MemoryArmStore(), RN.RunnerManager(), clock=lambda: pd.Timestamp("2026-10-04 12:00", tz=NY),
                           launcher=lambda s: {}, runner_launcher=lambda s: {})
    for slug in ("ndx_0dte_friend", "ndx_0dte_friend_w50"):
        [row] = sched.arm(slug, "weekdays")
        assert row["next_run"] == "2026-10-05T09:50:00-04:00"
    assert sorted(a["strategy"] for a in sched.store.active()) == ["ndx_0dte_friend", "ndx_0dte_friend_w50"]
    script = r"D:\Work\Project Dream\alan_trader\scripts\start_paper_runner.ps1"
    for slug in ("ndx_0dte_friend", "ndx_0dte_friend_w50"):
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-Strategy", slug]
        assert RN.parse_runner_cmdline(cmd)["strategy"] == slug
        assert RN.parse_runner_cmdline(["python", "-m", "scripts.paper_runner", "--strategy", slug, "--poll", "15"])["strategy"] == slug


def test_spx_gamma_walls_arms_like_ndx_gamma_walls():
    """NDX Gamma Walls' rule on SPX: the same runner kind, start and window; arming it never needs the NDX arm."""
    spx, ndx = A.SPECS["spx_gamma_walls"], A.SPECS["ndx_gamma_walls"]
    assert (spx.kind, spx.at, spx.until, spx.variants) == (ndx.kind, ndx.at, ndx.until, ndx.variants)
    cmd = A.runner_command("spx_gamma_walls", Path(r"C:\l\w.log"), Path(r"C:\csv"), py=r"D:\py.exe")
    assert "-m api.runner_launch --strategy spx_gamma_walls --poll 15" in cmd
    sched = A.ArmScheduler(A.MemoryArmStore(), RN.RunnerManager(), clock=lambda: pd.Timestamp("2026-09-30 20:00", tz=NY),
                           launcher=lambda s: {}, runner_launcher=lambda s: {})
    [row] = sched.arm("spx_gamma_walls", "weekdays")
    assert row["next_run"] == "2026-10-01T09:25:00-04:00" and row["kind"] == "runner"
    assert [a["strategy"] for a in sched.store.active()] == ["spx_gamma_walls"]


def test_one_broker_budget_across_checkouts(tmp_path):
    from paper.providers import RequestBudget
    ext = tmp_path / "main_paper_state"
    ext.mkdir()
    (ext / f"broker_calls_{_dt.date.today().isoformat()}.json").write_text(json.dumps({"calls": 2999}), encoding="utf-8")
    b = RequestBudget(min_interval_s=0, per_day=3000, shared_path=tmp_path / "own.json", external_dirs=[ext], sleep=lambda s: None)
    assert b.external_calls() == 2999
    b.take()                                                                    # 0 + 2999 < 3000: allowed
    with pytest.raises(RuntimeError, match="other checkouts"):
        b.take()                                                                # 1 + 2999: the day's cap
    alone = RequestBudget(min_interval_s=0, shared_path=tmp_path / "own2.json", sleep=lambda s: None)
    alone.take()                                                                # no external dirs: as before


def test_the_broker_day_cap_is_a_setting(tmp_path, monkeypatch):
    from paper.providers import DEFAULT_BROKER_DAY_CAP, RequestBudget
    monkeypatch.delenv("ALAN_TRADER_BROKER_DAY_CAP", raising=False)
    assert RequestBudget(shared_path=tmp_path / "a.json").per_day == DEFAULT_BROKER_DAY_CAP == 8000
    monkeypatch.setenv("ALAN_TRADER_BROKER_DAY_CAP", "5000")
    assert RequestBudget(shared_path=tmp_path / "b.json").per_day == 5000
    assert RequestBudget(per_day=7, shared_path=tmp_path / "c.json").per_day == 7   # an explicit cap wins
    monkeypatch.setenv("ALAN_TRADER_BROKER_DAY_CAP", "lots")
    assert RequestBudget(shared_path=tmp_path / "d.json").per_day == DEFAULT_BROKER_DAY_CAP


def test_the_day_balance_waits_for_the_other_runner_and_writes_the_account_total(tmp_path, monkeypatch):
    from paper import ledger as L
    from paper import runner as PR
    day = _dt.date.today()
    other = tmp_path / "other"
    other.mkdir()
    hb = other / "heartbeat_ndx_0dte_tasty.json"
    hb.write_text(json.dumps({"slug": "ndx_0dte_tasty", "day": day.isoformat(),
                              "at": _dt.datetime.now().isoformat(timespec="seconds"), "note": ""}), encoding="utf-8")
    monkeypatch.setenv("ALAN_TRADER_EXTERNAL_STATE_DIRS", str(other))
    ps = PR.PaperSession.__new__(PR.PaperSession)
    ps.slug, ps.state_dir, ps.db, ps.account_id = "ndx_gamma_walls", tmp_path, object(), 77
    assert ps._other_runners_active(day) == ["ndx_0dte_tasty"]
    written, slept = [], []
    monkeypatch.setattr(L, "account_day_pnl", lambda db, a, d: -1117.0 + 1188.0)
    monkeypatch.setattr(L, "record_day_balance", lambda db, a, d, pnl: written.append((a, d, pnl)))

    def sleep(s):
        slept.append(s)
        if len(slept) == 2:                                                     # the NDX runner finishes
            hb.write_text(json.dumps({"slug": "ndx_0dte_tasty", "day": day.isoformat(),
                                      "at": _dt.datetime.now().isoformat(timespec="seconds"), "note": "finished"}),
                          encoding="utf-8")
    ps._record_day_balance(day, sleep_fn=sleep)
    assert written == [(77, day, pytest.approx(71.0))] and slept[:2] == [30.0, 30.0] and slept[-1] == 60.0
