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


def test_the_account_cannot_short_and_the_rails_read_the_share_price(monkeypatch, capsys):
    """2026-09-30: the owner's account cannot short ("Use a long call or put to get the exposure"), so a share sale is
    refused before any order. And the preview's net is signed (a sale is a credit: -145.85): the rails must read the
    share price, or a long's risk and notional come out wrong."""
    from types import SimpleNamespace
    calls: list = []

    def fake_api(method, path, body=None, timeout=20.0):
        calls.append((method, path))
        if path == "/orders/preview":
            sign = -1.0 if body["legs"][0]["side"] == "sell" else 1.0
            return {"ok": True, "net_mid": sign * 145.85, "legs": [{"source": "tastytrade"}]}
        if path.startswith("/paper/positions"):
            return {"rows": []}
        if path == "/orders":
            return {"status": "filled", "trade_group_id": "TG1", "fill_price": 145.85}
        raise AssertionError(path)

    monkeypatch.setattr(N, "api", fake_api)
    monkeypatch.setattr(N, "now_et", lambda: pd.Timestamp("2026-09-30 10:00", tz=NY))
    monkeypatch.setattr(N, "journal", lambda *a, **k: None)
    monkeypatch.setattr(N, "load_state", lambda: {})
    monkeypatch.setattr(N, "save_state", lambda st: None)
    monkeypatch.setattr(N, "MAX_RISK", 1000.0)
    monkeypatch.setattr(N, "MAX_NOTIONAL", 10000.0)
    args = SimpleNamespace(symbol="USO", side="sell", qty=68, stop=146.45, target=144.0, leg=None, lots=1, stop_under=None,
                           stop_over=None, until=None, event=None, thesis="t", exit_plan="e", wrong="w")
    assert N.cmd_open(args) == 2
    assert "cannot short" in capsys.readouterr().out and ("POST", "/orders") not in calls
    args.side, args.stop, args.target = "buy", 145.20, 148.0                    # long 68: $44 to the stop, $9,918 in
    assert N.cmd_open(args) == 0 and ("POST", "/orders") in calls


def test_shock_follow_flags_a_3_sigma_day_and_sizes_the_trade():
    """Multi-day shock follows (2026-10-01 study; the owner: "Then etf is fine"): a 3-sigma close in USO / IBIT is a
    trigger; up = shares with the stop 2 sigma of the hold away, sized so the stop costs the risk cap; down = a put."""
    from datetime import date
    import numpy as np
    from scripts import claude_news as N
    rng = np.random.default_rng(7)
    closes = list(100 * np.exp(np.cumsum(rng.normal(0, 0.02, 30))))             # ~2% daily sigma
    z, move, sigma = N.shock_z(closes, closes[-1] * 1.08)                       # an +8% day
    assert 0.015 < sigma < 0.03 and z >= 3 and abs(move - np.log(1.08)) < 1e-9
    assert N.add_sessions(date(2026, 10, 1), 5) == date(2026, 10, 8)            # Thu + 5 weekdays (the weekend skipped)
    plan = N.shock_plan("USO", 150.0, z, sigma, date(2026, 10, 1), 1000.0, 10000.0)
    stop_pct = 2 * sigma * np.sqrt(5)
    assert plan["side"] == "buy" and plan["until"] == "2026-10-08T15:45"
    assert plan["qty"] == int(min(10000 / 150, 1000 / (150 * stop_pct)))          # the stop costs at most $1,000
    assert abs(plan["stop"] - round(150 * (1 - stop_pct), 2)) < 1e-9 and "--side buy" in plan["cmd"]
    down = N.shock_plan("IBIT", 48.0, -3.2, 0.027, date(2026, 10, 1), 1000.0, 10000.0)
    assert down["side"] == "put" and down["strike"] == 48 and down["expiry_from"] == "2026-10-22"   # 10 + 5 sessions
    assert "buy:P:48" in down["cmd"] and "--side sell" not in down["cmd"]          # never short shares
    assert N.shock_plan("USO", 150.0, 2.9, sigma, date(2026, 10, 1), 1000.0, 10000.0) is None
