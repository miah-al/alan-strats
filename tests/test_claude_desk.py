"""The NDX desk's discipline that is code, not judgment (scripts/claude_desk.py, 2026-09-30): the playbook line for the
gamma regime and the clock, and the trades-per-day cap. No network: nothing here calls the service or a broker."""
from __future__ import annotations

import pandas as pd

from scripts import claude_desk as D

NY = "America/New_York"


def at(hm: str) -> pd.Timestamp:
    return pd.Timestamp(f"2026-09-30 {hm}", tz=NY)


def test_the_playbook_follows_the_regime_and_the_clock():
    lv = "OR 30,563/30,415 | gamma: call wall 30,800, put wall 30,400, flip 29,268, max pain 30,350 (positive)"
    assert "no trades" in D.playbook(lv, at("09:50"))                                   # the first 30 minutes
    pos = D.playbook(lv, at("11:00"))
    assert "breaks fail" in pos and "no break trades" in pos and "sell premium" in pos
    neg = D.playbook(lv.replace("(positive)", "(negative)"), at("11:00"))
    assert "never fade" in neg and "block Friend's adds" in neg
    assert "flip" in D.playbook(lv.replace("(positive)", "(near_flip)"), at("11:00"))
    assert "15:50" in D.playbook(lv, at("15:41"))                                       # no short gamma into the imbalances
    assert "no gamma regime" in D.playbook("OR 30,563/30,415", at("11:00"))


def test_trades_a_day_count_opens_not_trims():
    st = {"positions": {"A": {"lots": 2}, "B": {"lots": 1, "trim_of": "A"}, "C": {"lots": 2}}}
    assert D.trades_today(st) == 2
    assert D.trades_today({}) == 0 and D.trades_today({"positions": {}}) == 0


def test_spx_walls_are_shown_in_ndx_points_at_the_live_ratio():
    g = {"spot": 7674.0, "call_wall": 7750.0, "put_wall": 7600.0, "flip": 7694.0, "max_pain": 7700.0, "regime": "negative"}
    line = D.spx_walls_in_ndx(g, 30417.0)                              # ratio 3.9636
    assert line.startswith("SPX gamma in NDX pts: call wall 30,718 (7,750)") and "put wall 30,124 (7,600)" in line
    assert line.endswith("(SPX negative)")
    assert D.spx_walls_in_ndx(g, None) == "" and D.spx_walls_in_ndx({"call_wall": 7750.0}, 30417.0) == ""
