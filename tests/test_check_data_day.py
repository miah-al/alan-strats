"""The post-close data check: a complete stored session passes, a weekend is skipped, a future day
reports what is missing (needs the database; skips without it)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest


def _db():
    try:
        from db.client import get_engine, get_minute_bar_coverage
        eng = get_engine()
        cov = get_minute_bar_coverage(eng, "NDX")
        if not cov:
            pytest.skip("no NDX minute bars stored")
        return cov
    except Exception as exc:
        pytest.skip(f"database unavailable: {exc}")


def test_complete_day_passes_and_gaps_are_reported(capsys):
    cov = _db()
    from scripts.check_data_day import main
    last = cov[1]
    assert main(["--day", last.isoformat()]) == 0
    out = capsys.readouterr().out
    assert "OK" in out and "minute bars 390" in out or "minute bars 211" in out
    # a Saturday is not a session
    sat = last + timedelta(days=(5 - last.weekday()) % 7 or 7)
    assert main(["--day", sat.isoformat()]) == 0
    # a session far in the future has nothing stored
    future = last + timedelta(days=30)
    while future.weekday() >= 5:
        future += timedelta(days=1)
    assert main(["--day", future.isoformat()]) == 1
    out = capsys.readouterr().out
    assert "MISSING" in out and "minute bars: 0" in out
