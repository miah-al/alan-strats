"""A live session killed mid-day and restarted must end with the same trades as an unbroken run,
and a session that ends with open units must settle them. Uses the fake real-time provider from
the live-loop test on a stored day (skips without the database)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

DAY = date(2026, 8, 26)
SLUG = "ndx_0dte_tasty"


def _setup():
    try:
        from db.client import get_engine, get_option_minute_coverage
        eng = get_engine()
        if not get_option_minute_coverage(eng, "NDX"):
            pytest.skip("no option minute bars stored")
    except Exception as exc:
        pytest.skip(f"database unavailable: {exc}")
    from strategy_api import registry as R
    try:
        R.get_strategy(SLUG)
    except Exception as exc:
        pytest.skip(str(exc))
    from paper.providers import ReplayProvider
    # Loop mechanics, not execution realism: the OPTIMISTIC replay settings (legs carried 30 min, a flat half point) are
    # pinned so the day has fills to compare; tests/test_paper_replay_conservative.py covers the conservative defaults.
    replay = ReplayProvider(eng, "NDX", DAY, half_spread=0.5, carry_min=30)
    if not replay.has_option_data():
        pytest.skip("no prints for the test day")
    return eng, replay


def _clock(start: datetime):
    t = [start]
    return (lambda: t[0]), (lambda sec: t.__setitem__(0, t[0] + timedelta(seconds=20))), t


def test_killed_session_resumes_to_the_same_result(tmp_path):
    eng, replay = _setup()
    from tests.test_paper_live_loop import FakeLiveProvider
    from paper.runner import PaperSession
    start = datetime.combine(DAY, datetime.min.time()) + timedelta(hours=9, minutes=29)

    # unbroken run
    now1, sleep1, _ = _clock(start)
    ps1 = PaperSession(SLUG, FakeLiveProvider(replay, now1), eng, write_ledger=False, log_dir=tmp_path / "a", state_dir=tmp_path / "sa")
    full = ps1.run_live(day=DAY, poll_seconds=20, now_fn=now1, sleep_fn=sleep1)

    # killed at 12:30, restarted from state with a fresh process (new provider, new session object)
    now2, sleep2, t2 = _clock(start)
    ps2 = PaperSession(SLUG, FakeLiveProvider(replay, now2), eng, write_ledger=False, log_dir=tmp_path / "b", state_dir=tmp_path / "sb")
    part = ps2.run_live(day=DAY, poll_seconds=20, now_fn=now2, sleep_fn=sleep2, until=datetime(2026, 8, 26, 12, 30).time())
    st = json.loads((tmp_path / "sb" / f"{SLUG}_{DAY}.json").read_text(encoding="utf-8"))
    assert st["finished"] is True                                   # the runner marks a clean end as finished ...
    st["finished"] = False                                          # ... a crash would not; simulate that
    (tmp_path / "sb" / f"{SLUG}_{DAY}.json").write_text(json.dumps(st), encoding="utf-8")
    now3, sleep3, _ = _clock(datetime(2026, 8, 26, 12, 30, 5))
    prov3 = FakeLiveProvider(replay, now3)
    ps3 = PaperSession(SLUG, prov3, eng, write_ledger=False, log_dir=tmp_path / "b", state_dir=tmp_path / "sb")
    rest = ps3.run_live(day=DAY, poll_seconds=20, now_fn=now3, sleep_fn=sleep3)
    key = lambda x: (x["entry_time"], x["exit_time"], x["k_low"], x["k_high"], round(x["entry_px"], 2), round(x["exit_px"], 2), x["exit_reason"])
    assert [key(x) for x in rest.trades] == [key(x) for x in full.trades]
    assert abs(rest.day_pnl - full.day_pnl) < 1e-6
    assert len(part.trades) < len(full.trades)                       # the first process really was cut short
    # the paper log for the day has every event exactly once
    import pandas as pd
    log = pd.read_csv(tmp_path / "b" / f"{DAY}.csv")
    ev = log[log.event != "features"]
    assert len(ev) == len(rest.fills)
    hb = json.loads((tmp_path / "sb" / f"heartbeat_{SLUG}.json").read_text(encoding="utf-8"))
    assert hb["note"] == "finished" and hb["trades"] == len(rest.trades)


def test_open_units_are_settled_when_the_session_ends(tmp_path, monkeypatch):
    eng, replay = _setup()
    from tests.test_paper_live_loop import FakeLiveProvider
    from paper.runner import PaperSession
    start = datetime.combine(DAY, datetime.min.time()) + timedelta(hours=9, minutes=29)
    now, sleep, t = _clock(start)
    prov = FakeLiveProvider(replay, now)
    # a provider that stops producing bars after 15:30: the 15:59 bar never arrives, so the engine never sees is_last
    real_close = prov.close_minute
    def close_minute(minute_start):
        if minute_start.time() >= datetime(2026, 8, 26, 15, 30).time():
            return None
        return real_close(minute_start)
    monkeypatch.setattr(prov, "close_minute", close_minute)
    ps = PaperSession(SLUG, prov, eng, write_ledger=False, log_dir=tmp_path / "c", state_dir=tmp_path / "sc")
    ps.strategy = type(ps.strategy)(**{**ps.strategy.get_params(), "hold_to_settlement": True, "entry_end": "15:29"})
    res = ps.run_live(day=DAY, poll_seconds=20, now_fn=now, sleep_fn=sleep)
    st = json.loads((tmp_path / "sc" / f"{SLUG}_{DAY}.json").read_text(encoding="utf-8"))
    assert st["state"]["positions"] == []                            # nothing carried overnight
    assert all(f["kind"] != "open" or any(c["kind"] == "close" for c in res.fills if c["m"] >= f["m"]) for f in res.fills)
