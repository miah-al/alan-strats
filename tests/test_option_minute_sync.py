"""Offline tests for the option minute-bar sync helpers (no network, no database)."""
from datetime import date

import pandas as pd

from db.sync import parse_option_ticker, select_option_strikes, sync_option_minute_bars, _session_ref_level


def test_parse_option_ticker_ndxp():
    assert parse_option_ticker("O:NDXP260826C29270000") == ("NDXP", date(2026, 8, 26), "C", 29270.0)
    assert parse_option_ticker("O:SPXW241018P05800000") == ("SPXW", date(2024, 10, 18), "P", 5800.0)
    assert parse_option_ticker("NDX251219C00020000") == ("NDX", date(2025, 12, 19), "C", 20.0)


def test_select_option_strikes_band_and_grid():
    strikes = [k for k in range(28700, 29700, 5)]            # the 5-point grid Polygon lists near the money
    out = select_option_strikes(strikes, ref_level=29160.4, band=400, step=25)
    assert out[0] == 28775 and out[-1] == 29550                # within +-400 of 29160.4, on the 25s
    assert all(k % 25 == 0 for k in out)
    assert len(out) == 32
    assert select_option_strikes(strikes, 29160.4, band=100, step=50) == [29100, 29150, 29200, 29250]
    assert select_option_strikes([], 29160.4) == []


def test_sync_without_key_is_an_error_not_a_crash():
    out = sync_option_minute_bars("NDX", "")
    assert out["status"] == "error" and out["rows"] == 0


def test_session_ref_level_uses_first_bar_at_or_after_ref_time(monkeypatch):
    ts = pd.date_range("2026-08-26 09:30", "2026-08-26 15:59", freq="1min")
    bars = pd.DataFrame({"ts": ts, "open": 1.0, "high": 1.0, "low": 1.0, "close": range(len(ts)), "volume": 0})
    import alan_trader.db.client as client
    monkeypatch.setattr(client, "get_minute_bars", lambda *a, **k: bars)
    lvl = _session_ref_level(None, "NDX", date(2026, 8, 26), "13:00")
    assert lvl == float(bars.loc[bars.ts == pd.Timestamp("2026-08-26 13:00"), "close"].iloc[0])
    morning = bars[bars.ts < "2026-08-26 12:00"]
    monkeypatch.setattr(client, "get_minute_bars", lambda *a, **k: morning)
    assert _session_ref_level(None, "NDX", date(2026, 8, 26), "13:00") == float(morning.close.iloc[-1])
    monkeypatch.setattr(client, "get_minute_bars", lambda *a, **k: bars.iloc[0:0])
    assert _session_ref_level(None, "NDX", date(2026, 8, 26)) is None
