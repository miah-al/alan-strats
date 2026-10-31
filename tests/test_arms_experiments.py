"""Arm specs: the live 13:00 runners poll once a minute, every other runner keeps the 15 s default, and the retired
strategies' specs are gone (2026-10-25: the clone and ratio robots; 2026-10-31, the owner: "Remove failed strategies
code": the Friend family, the 10/05 experiments, the gamma walls, the GEX allocator, the sector rotation and the
overlay-only rally fade, gamma scalp and NDX condor)."""
from __future__ import annotations

from pathlib import Path

from api.services import arms as A

RETIRED = ("ndx_0dte_friend_real", "ndx_spx_ratio", "ndx_0dte_friend", "ndx_0dte_friend_w50", "ndx_0dte_always_bull",
           "ndx_0dte_calm_theta", "gex_positioning", "ndx_gamma_walls", "spx_gamma_walls", "sector_rotation",
           "ndx_0dte_rally_fade", "ndx_gamma_scalp", "ndx_0dte_condor")


def test_the_retired_strategies_have_no_spec():
    assert not set(RETIRED) & set(A.SPECS)
    for slug in ("spx_0dte_call13", "spx_0dte_event13", "ndx_0dte_call14", "nq_vol_breakout", "btc_momentum",
                 "sol_momentum", "equity_trend", "gold_trend", "cash_sleeve", "event_signal_log"):
        assert slug in A.SPECS, slug


def test_the_spx_13_00_call_spread_runs_the_platform_runner_at_12_50_with_a_60_second_poll():
    spec = A.SPECS["spx_0dte_call13"]
    assert (spec.kind, spec.at.strftime("%H:%M"), spec.until.strftime("%H:%M"), spec.poll) == ("runner", "12:50", "13:02", 60)
    cmd = A.runner_command("spx_0dte_call13", Path("x.log"), Path("csv"), py="py")
    assert "-m api.runner_launch --strategy spx_0dte_call13 --poll 60 " in cmd
    # every other runner keeps the default
    assert "--strategy nq_vol_breakout --poll 15 " in A.runner_command("nq_vol_breakout", Path("x.log"), Path("csv"), py="py")
    assert A.runner_poll("nq_vol_breakout") == A.RUNNER_POLL_S == 15 and A.runner_poll("no_such_strategy") == 15
