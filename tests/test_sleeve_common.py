"""The sleeves' shared helpers (api/services/sleeve_common.py, once the retired sector rotation's rotation_alloc.py): the
month-end calendar the momentum, trend and cash allocators decide on. Offline."""
from __future__ import annotations

import datetime as _dt

from api.services import sleeve_common as RA


def test_the_calendar():
    assert RA.is_month_end(_dt.date(2026, 9, 30)) and not RA.is_month_end(_dt.date(2026, 10, 6))
    assert RA.is_month_end(_dt.date(2026, 10, 30))                       # a Friday; the next session is in November
    assert RA.last_month_end_before(_dt.date(2026, 10, 6)) == _dt.date(2026, 9, 30)
    assert RA.last_month_end_before(_dt.date(2026, 11, 2)) == _dt.date(2026, 10, 30)
    assert RA.previous_trading_day(_dt.date(2026, 11, 2)) == _dt.date(2026, 10, 30)
    assert RA.trading_day(_dt.date(2026, 10, 30)) and not RA.trading_day(_dt.date(2026, 10, 31))


def test_live_inputs_name_their_sleeve():
    li = RA.LiveInputs(None, ledger="equity_trend", history_days=420)
    assert (li.ledger, li.history_days) == ("equity_trend", 420)
    assert RA.LiveInputs(None, ledger="btc_momentum").history_days == RA.HISTORY_DAYS == 160
    assert li.prices_now(("SPY",)) == {"SPY": None}                      # no hub: no price, never a guess
