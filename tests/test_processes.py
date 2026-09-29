"""The process monitor's health rules (api/services/processes.runner_status) and its table on a stand-in app state."""
from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace

from api.services import processes as P

T = _dt.time


def at(hh, mm):
    return _dt.datetime(2026, 9, 29, hh, mm)


def test_runner_status_rules():
    kw = dict(at=T(12, 30), until=T(15, 30))
    assert P.runner_status(at(12, 0), alive=False, ran_today=False, hb_age_s=None, **kw) == ("idle", "starts 12:30")
    assert P.runner_status(at(12, 31), alive=False, ran_today=False, hb_age_s=None, **kw)[0] == "warn"   # due, not started
    assert P.runner_status(at(15, 40), alive=False, ran_today=False, hb_age_s=None, **kw)[1].startswith("missed")
    assert P.runner_status(at(13, 0), alive=True, ran_today=True, hb_age_s=20, **kw) == ("ok", "running")
    s, r = P.runner_status(at(15, 20), alive=True, ran_today=True, hb_age_s=250, hb_note="fetch failing (6)", **kw)
    assert s == "warn" and "silent 250s" in r and "fetch failing" in r                 # backing off: still alive
    assert P.runner_status(at(15, 20), alive=True, ran_today=True, hb_age_s=900, **kw)[0] == "bad"
    assert P.runner_status(at(14, 0), alive=False, ran_today=True, hb_age_s=600, returncode=1, **kw) == ("bad", "stopped early (exit 1)")
    assert P.runner_status(at(16, 5), alive=False, ran_today=True, hb_age_s=300, **kw) == ("idle", "finished")
    assert P.runner_status(at(14, 0), alive=False, ran_today=True, hb_age_s=30, hb_note="finished", **kw) == ("idle", "finished")
    assert P.runner_status(at(9, 0), alive=False, ran_today=False, hb_age_s=None, kind="allocator", at=T(9, 31), until=T(10, 30)) == ("idle", "runs 09:31")


def test_snapshot_lists_every_armed_run_even_when_nothing_runs(monkeypatch):
    monkeypatch.setattr(P, "_heartbeat", lambda slug: (None, "", None))
    monkeypatch.setattr(P, "_desk_feed", lambda: {"alive": False})
    arms = [{"strategy": "ndx_gamma_walls", "kind": "runner", "window": {"at": "09:25", "until": "15:00"}, "last_run_date": None},
            {"strategy": "ndx_0dte_friend", "kind": "script", "window": {"at": "12:30", "until": "15:30"}, "last_run_date": None}]
    state = SimpleNamespace(market=None, quote_recorder=None, runner=SimpleNamespace(sessions=lambda: []),
                            arms=SimpleNamespace(arms=lambda: arms))
    snap = P.snapshot(state, now=at(11, 0))
    by = {r["name"]: r for r in snap["rows"]}
    assert by["runner: ndx_gamma_walls"]["status"] == "warn"            # due since 09:25, not running
    assert by["runner: ndx_0dte_friend"] == {**by["runner: ndx_0dte_friend"], "status": "idle", "reason": "starts 12:30"}
    assert by["stream: tastytrade"]["status"] == "bad" and by["service"]["status"] == "ok"
    assert by["desk: claude (feed)"]["status"] == "warn"                # in session, no feed running
    assert sum(snap["summary"].values()) == len(snap["rows"])
