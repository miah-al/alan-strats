"""The news desk's rules (scripts/claude_news.py) that are code, not judgment: themes, the share rails, the exits.
No network: nothing here calls the service, a broker or a news source."""
from __future__ import annotations

import pandas as pd

from scripts import claude_news as N

NY = "America/New_York"


def test_items_get_themes_and_instruments():
    assert N.themes_of("Bitcoin will be the currency of the world") == ["crypto"]
    assert set(N.themes_of("Iran threatens to close the Strait of Hormuz")) == {"oil", "war"}
    assert N.themes_of("Powell says a rate cut is coming") == ["rates"]
    assert N.themes_of("A lovely day at the golf club") == []
    assert N.instruments_for(["crypto"]) == ["IBIT"]
    assert N.instruments_for(["oil", "war"]) == ["USO", "SPY", "GLD"]           # no duplicates, theme order
    assert N.instruments_for([]) == ["SPY"]


def test_share_orders_are_sized_against_the_rails(monkeypatch):
    monkeypatch.setattr(N, "MAX_RISK", 1000.0)
    monkeypatch.setattr(N, "MAX_NOTIONAL", 10000.0)
    assert N.share_rails(100, 47.0, 45.0, "buy") == []                          # $200 to the stop, $4,700 in
    why = N.share_rails(600, 47.0, 45.0, "buy")                                 # $1,200 to the stop, $28,200 in
    assert any("over $1,000" in w and "at most 500 shares" in w for w in why) and any("over $10,000" in w for w in why)
    assert any("wrong side" in w for w in N.share_rails(10, 47.0, 48.0, "buy"))
    assert N.share_rails(100, 47.0, 48.0, "sell") == []                         # a short's stop is above


def test_exits_on_the_underlyings_last_price():
    now = pd.Timestamp("2026-09-30 11:00", tz=NY)
    long_ = {"kind": "shares", "side": "buy", "stop": 45.0, "target": 50.0}
    assert N.exit_reason(long_, 46.0, now) is None
    assert N.exit_reason(long_, 44.9, now).startswith("stop 45.0 hit")
    assert N.exit_reason(long_, 50.2, now).startswith("target 50.0")
    short = {"kind": "shares", "side": "sell", "stop": 48.0, "target": 44.0}
    assert N.exit_reason(short, 48.1, now).startswith("stop") and N.exit_reason(short, 43.9, now).startswith("target")
    spread = {"kind": "spread", "side": "buy", "stop_under": 77.5, "target": None, "until": "2026-09-30T10:30"}
    assert N.exit_reason(spread, 77.4, now).startswith("underlying under 77.5")
    assert N.exit_reason(spread, 80.0, now).startswith("time exit")             # past 10:30


def test_item_times_read_both_formats():
    now = pd.Timestamp("2026-09-29 16:40", tz=NY)
    assert N._item_time({"time": "2026-09-29 13:45"}, now) == pd.Timestamp("2026-09-29 13:45", tz=NY)
    assert N._item_time({"time": "14:05"}, now) == pd.Timestamp("2026-09-29 14:05", tz=NY)
    assert N._item_time({"time": "2026-09-29 18:00:00+00:00"}, now) == pd.Timestamp("2026-09-29 14:00", tz=NY)
    assert N._item_time({"time": None}, now) == now
