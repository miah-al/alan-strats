"""The two experiments armed 2026-10-05 (ndx_0dte_always_bull, ndx_0dte_calm_theta) run the live checkout's start script
with a 60-second poll, so they stay inside the broker's daily call budget; every other script runner keeps the 15 s."""
from __future__ import annotations

from pathlib import Path

from api.services import arms as A


def test_the_experiments_poll_every_60_seconds_and_the_rest_keep_the_default():
    co = Path("D:/checkout")
    for slug in ("ndx_0dte_always_bull", "ndx_0dte_calm_theta", "ndx_0dte_friend_real"):
        spec = A.SPECS[slug]
        assert spec.kind == "script" and spec.poll == 60
        assert f"-Strategy {slug} -Poll 60" in A.task_command(slug, co)
    assert "-Poll" not in A.task_command("ndx_0dte_friend", co)
    assert A.SPECS["ndx_0dte_friend"].poll == 0
    assert A.SPECS["ndx_0dte_always_bull"].at.strftime("%H:%M") == "09:45"
    assert A.SPECS["ndx_0dte_calm_theta"].until.strftime("%H:%M") == "15:30"
    assert A.SPECS["ndx_0dte_friend_real"].at.strftime("%H:%M") == "10:45"


def test_the_spx_13_00_call_spread_runs_the_platform_runner_at_12_50_with_a_60_second_poll():
    spec = A.SPECS["spx_0dte_call13"]
    assert (spec.kind, spec.at.strftime("%H:%M"), spec.until.strftime("%H:%M"), spec.poll) == ("runner", "12:50", "13:02", 60)
    cmd = A.runner_command("spx_0dte_call13", Path("x.log"), Path("csv"), py="py")
    assert "-m api.runner_launch --strategy spx_0dte_call13 --poll 60 " in cmd
    # every other runner keeps the default
    assert "--strategy spx_gamma_walls --poll 15 " in A.runner_command("spx_gamma_walls", Path("x.log"), Path("csv"), py="py")
    assert A.runner_poll("ndx_gamma_walls") == A.RUNNER_POLL_S == 15 and A.runner_poll("no_such_strategy") == 15
