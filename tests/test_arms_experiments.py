"""The two experiments armed 2026-10-05 (ndx_0dte_always_bull, ndx_0dte_calm_theta) run the live checkout's start script
with a 60-second poll, so they stay inside the broker's daily call budget; every other script runner keeps the 15 s."""
from __future__ import annotations

from pathlib import Path

from api.services import arms as A


def test_the_experiments_poll_every_60_seconds_and_the_rest_keep_the_default():
    co = Path("D:/checkout")
    for slug in ("ndx_0dte_always_bull", "ndx_0dte_calm_theta"):
        spec = A.SPECS[slug]
        assert spec.kind == "script" and spec.poll == 60
        assert f"-Strategy {slug} -Poll 60" in A.task_command(slug, co)
    assert "-Poll" not in A.task_command("ndx_0dte_friend", co)
    assert A.SPECS["ndx_0dte_friend"].poll == 0
    assert A.SPECS["ndx_0dte_always_bull"].at.strftime("%H:%M") == "09:45"
    assert A.SPECS["ndx_0dte_calm_theta"].until.strftime("%H:%M") == "15:30"
