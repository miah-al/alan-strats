"""The account-wide day stop (api/services/day_stop.py): when the whole paper account is the system limit's amount
down on the day, every armed strategy's new entries go off (sup_entries = 0, by "system"), once a day, during the
session only. An in-memory limits store and a scripted usage; no database, no runner."""
from __future__ import annotations

import datetime as dt

from api.bootstrap import bootstrap

bootstrap()

from api.services import limits as LM  # noqa: E402
from api.services.day_stop import AccountDayStop  # noqa: E402

THU = dt.date(2026, 10, 8)


def rig(day_pnls: dict, stop=None):
    store = LM.MemoryLimitStore()
    lim = LM.Limits(store, strategies=lambda: ["ndx_spx_ratio", "spx_0dte_call13"], specs_for=lambda s: [],
                    values_for=lambda s: {})
    if stop is not None:
        lim.set("system", "account_day_stop", stop, by="owner")
    usage = {**{s: {"day_pnl": v} for s, v in day_pnls.items()}, "system": {"broker_calls": 10}}
    return store, lim, AccountDayStop(lambda: lim, lambda: usage)


def at(h, m, day=THU):
    return dt.datetime.combine(day, dt.time(h, m))


def test_it_turns_every_strategy_off_once_the_account_is_down_the_limit():
    store, lim, ds = rig({"ndx_spx_ratio": -900.0, "ndx_0dte_friend_real": -215.0, "spx_0dte_call13": 120.0})
    out = ds.tick(at(14, 0))                                     # -995: not yet (default limit 1,000)
    assert out is None
    store2, lim2, ds2 = rig({"ndx_spx_ratio": -1000.0, "claude_events": -50.0, "spx_0dte_call13": 40.0})
    out = ds2.tick(at(14, 0))                                    # -1,010: across every scope, desks included
    assert out and out["day_pnl"] == -1010.0 and out["limit"] == 1000.0
    assert sorted(out["strategies"]) == ["ndx_spx_ratio", "spx_0dte_call13"]
    vals = store2.all()
    for s in ("ndx_spx_ratio", "spx_0dte_call13"):
        assert vals[(s, "sup_entries")]["value"] == 0 and vals[(s, "sup_entries")]["updated_by"] == "system"
    assert ("claude_events", "sup_entries") not in vals            # desks have their own day stops
    assert ds2.tick(at(14, 5)) is None                              # once a day


def test_off_hours_weekends_and_a_zero_limit_do_nothing():
    _, _, ds = rig({"ndx_spx_ratio": -5000.0})
    assert ds.tick(at(9, 29)) is None and ds.tick(at(16, 0)) is None
    assert ds.tick(at(11, 0, dt.date(2026, 10, 10))) is None        # Saturday
    _, _, off = rig({"ndx_spx_ratio": -5000.0}, stop=0)
    assert off.tick(at(11, 0)) is None
    _, _, tight = rig({"ndx_spx_ratio": -300.0}, stop=250)
    assert tight.tick(at(11, 0))["limit"] == 250.0


def test_the_limits_page_shows_the_account_day_against_the_stop():
    usage = {"a": {"day_pnl": -600.0}, "b": {"day_pnl": -300.0}, "system": {"broker_calls": 5, "day_pnl": -900.0}}
    used, status = LM._usage_of("account_day_stop", 1000, usage["system"], usage)
    assert used == -900.0 and status == "near"
    assert AccountDayStop.account_day_pnl(usage) == -900.0
