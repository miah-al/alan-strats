"""The paper account's equity at each close, recorded from the live marks (api/services/close_mark.py).

The equity history is otherwise rebuilt from daily closes, and an option's daily close is its last trade: on
2026-11-12 that left the account's close $677 under the live marks, so the next day's "Day P&L" and the account day
stop both started from the wrong number.
"""
import datetime as dt
import json

import pandas as pd

from api.services import close_mark as CM

WEEKDAYS = lambda d: d.weekday() < 5          # noqa: E731 — a calendar without holidays


def _series(first: str, values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.date_range(first, periods=len(values), freq="D"), dtype=float)


def _mark(equity: float, cash: float) -> dict:
    return {"equity": equity, "cash": cash, "at": "x", "live_marks": True}


# ── apply: a recorded close replaces the rebuilt figure, and is carried over the weekend ──────────────────────────────

def test_a_recorded_close_replaces_its_day_and_is_carried_over_the_weekend():
    # Thu 11/12 .. Mon 11/16; the rebuilt Thursday close is 677 under the live marks, and the weekend repeats Friday
    eq = _series("2026-11-12", [34776.20, 36100.00, 36100.00, 36100.00, 36150.00])
    cash = _series("2026-11-12", [16000.00, 16059.24, 16059.24, 16059.24, 16059.24])
    marks = {dt.date(2026, 11, 12): _mark(35453.20, 16000.00), dt.date(2026, 11, 13): _mark(36138.32, 16059.24)}
    out, used = CM.apply(eq, cash, marks, trading_day=WEEKDAYS)
    assert list(out.round(2)) == [35453.20, 36138.32, 36138.32, 36138.32, 36150.00]
    assert used == [dt.date(2026, 11, 12), dt.date(2026, 11, 13), dt.date(2026, 11, 14), dt.date(2026, 11, 15)]
    # the app's "last close before today" on Monday is Sunday's point: Friday's record, not the rebuilt figure
    assert out[pd.Timestamp("2026-11-15")] == 36138.32
    assert list(eq.round(2))[0] == 34776.20                       # the input is not changed


def test_a_record_the_ledger_no_longer_agrees_with_is_ignored():
    # Friday was restated after the close: the ledger's cash through Friday is no longer what the record was taken with
    eq = _series("2026-11-13", [36000.00, 36000.00, 36000.00])
    cash = _series("2026-11-13", [15900.00, 15900.00, 15900.00])
    out, used = CM.apply(eq, cash, {dt.date(2026, 11, 13): _mark(36138.32, 16059.24)}, trading_day=WEEKDAYS)
    assert list(out) == [36000.00, 36000.00, 36000.00] and used == []


def test_a_record_stops_being_carried_when_the_cash_moves_on_a_non_trading_day():
    eq = _series("2026-11-13", [36000.00, 36000.00, 37000.00])     # a deposit lands on Sunday
    cash = _series("2026-11-13", [16059.24, 16059.24, 17059.24])
    out, used = CM.apply(eq, cash, {dt.date(2026, 11, 13): _mark(36138.32, 16059.24)}, trading_day=WEEKDAYS)
    assert list(out.round(2)) == [36138.32, 36138.32, 37000.00]
    assert used == [dt.date(2026, 11, 13), dt.date(2026, 11, 14)]


def test_a_trading_day_without_a_record_is_rebuilt_and_ends_the_carry():
    # Friday recorded; the PC was off on Monday (no record): Monday and Tuesday morning are the rebuilt figures
    eq = _series("2026-11-13", [36000.00, 36000.00, 36000.00, 36400.00, 36400.00])
    cash = _series("2026-11-13", [16059.24] * 5)
    out, used = CM.apply(eq, cash, {dt.date(2026, 11, 13): _mark(36138.32, 16059.24)}, trading_day=WEEKDAYS)
    assert list(out.round(2)) == [36138.32, 36138.32, 36138.32, 36400.00, 36400.00]
    assert used == [dt.date(2026, 11, 13), dt.date(2026, 11, 14), dt.date(2026, 11, 15)]


def test_a_holiday_carries_the_last_record_like_a_weekend():
    eq = _series("2026-11-25", [36000.00, 36000.00, 36500.00])     # Wed, Thanksgiving, Fri
    cash = _series("2026-11-25", [16000.00] * 3)
    cal = lambda d: d.weekday() < 5 and d != dt.date(2026, 11, 26)  # noqa: E731
    out, _used = CM.apply(eq, cash, {dt.date(2026, 11, 25): _mark(36100.00, 16000.00)}, trading_day=cal)
    assert list(out.round(2)) == [36100.00, 36100.00, 36500.00]


def test_nothing_recorded_or_nothing_to_mark_changes_nothing():
    eq = _series("2026-11-13", [36000.00, 36000.00])
    cash = _series("2026-11-13", [16000.00, 16000.00])
    out, used = CM.apply(eq, cash, {}, trading_day=WEEKDAYS)
    assert out is eq and used == []
    assert CM.apply(None, cash, {dt.date(2026, 11, 13): _mark(1.0, 1.0)}) == (None, [])


def test_the_cash_line_may_start_earlier_than_the_equity_line():
    eq = _series("2026-11-13", [36000.00, 36000.00])
    cash = _series("2026-11-01", [16059.24] * 14)                  # the ledger's cash from its first trade
    out, _used = CM.apply(eq, cash, {dt.date(2026, 11, 13): _mark(36138.32, 16059.24)}, trading_day=WEEKDAYS)
    assert list(out.round(2)) == [36138.32, 36138.32]


# ── the store ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_store_keeps_one_entry_a_day_per_account_and_survives_a_damaged_file(tmp_path):
    st = CM.CloseMarkStore(tmp_path / "state" / "close_marks.json")
    assert st.read(1) == {}
    st.put(1, dt.date(2026, 11, 13), 36100.0, 16059.24, "2026-11-13T16:00:10", True)
    st.put(1, dt.date(2026, 11, 13), 36138.321, 16059.24, "2026-11-13T16:20:10", True)     # the later tick replaces it
    st.put(2, dt.date(2026, 11, 13), 5.0, 5.0, "x", False)
    assert st.read(1) == {dt.date(2026, 11, 13): {"equity": 36138.32, "cash": 16059.24, "at": "2026-11-13T16:20:10",
                                                  "live_marks": True}}
    assert list(st.read(2)) == [dt.date(2026, 11, 13)] and st.read(3) == {}
    assert not list(tmp_path.glob("state/*.tmp"))                                           # written whole, then renamed
    doc = json.loads(st.path.read_text(encoding="utf-8"))
    doc["1"]["2026-11-12"] = {"equity": "not a number"}
    doc["1"]["not a day"] = {"equity": 1, "cash": 1}
    st.path.write_text(json.dumps(doc), encoding="utf-8")
    assert list(st.read(1)) == [dt.date(2026, 11, 13)]                                      # the damaged entries are no record
    st.path.write_text("{ not json", encoding="utf-8")
    assert st.read(1) == {}


# ── the job ──────────────────────────────────────────────────────────────────────────────────────────────────────────

class Clock:
    def __init__(self, at: str):
        self.t = dt.datetime.fromisoformat(at)

    def __call__(self) -> dt.datetime:
        return self.t


def _job(tmp_path, clock, summary):
    st = CM.CloseMarkStore(tmp_path / "close_marks.json")
    return CM.CloseMark(lambda: summary, lambda: 1, store=st, clock=clock, trading_day=WEEKDAYS), st


def test_the_job_records_only_between_1600_and_1620_on_a_trading_day(tmp_path):
    summary = {"equity": 36000.0, "cash": 16059.24, "open_positions": 4, "live_marks": True}
    clock = Clock("2026-11-13 15:59:59")
    job, st = _job(tmp_path, clock, summary)
    assert job.tick() is None and st.read(1) == {}                                          # before the bell
    clock.t = dt.datetime(2026, 11, 13, 16, 0, 0)
    assert job.tick() == {"day": "2026-11-13", "equity": 36000.0, "cash": 16059.24, "at": "2026-11-13T16:00:00",
                          "live_marks": True}
    summary["equity"] = 36138.32                                                            # the settlements are booked
    clock.t = dt.datetime(2026, 11, 13, 16, 20, 59)
    assert job.tick()["equity"] == 36138.32
    summary["equity"] = 36500.0                                                             # after-hours drift: not kept
    clock.t = dt.datetime(2026, 11, 13, 16, 21, 0)
    assert job.tick() is None
    assert st.read(1)[dt.date(2026, 11, 13)]["equity"] == 36138.32
    clock.t = dt.datetime(2026, 11, 14, 16, 5, 0)                                           # Saturday
    assert job.tick() is None and list(st.read(1)) == [dt.date(2026, 11, 13)]


def test_the_job_keeps_no_close_taken_from_fallback_prices(tmp_path):
    summary = {"equity": 36000.0, "cash": 16059.24, "open_positions": 4, "live_marks": False}
    job, st = _job(tmp_path, Clock("2026-11-13 16:05:00"), summary)
    assert job.tick() is None and st.read(1) == {}                                          # the stream is down: no record
    summary.update(open_positions=0, equity=16059.24)                                       # all cash: nothing to mark
    assert job.tick()["equity"] == 16059.24
    job2, st2 = _job(tmp_path / "b", Clock("2026-11-13 16:05:00"), {"equity": None, "cash": 1.0})
    assert job2.tick() is None and st2.read(1) == {}


# ── the equity endpoint and the day stop read the record ─────────────────────────────────────────────────────────────

def test_the_equity_series_and_the_account_day_use_the_recorded_close(tmp_path, monkeypatch):
    from api.services import limits as LM
    from api.services import paper as P

    days = pd.date_range("2026-11-12", "2026-11-16", freq="D")
    rebuilt = pd.DataFrame({"BusinessDate": days, "Amount": [34776.20, 36100.0, 36100.0, 36100.0, 36150.0]})

    class Views:
        @staticmethod
        def mtm_equity_series(txns, start, end, account_id=None):
            return rebuilt

    monkeypatch.setattr(P, "PD", lambda: Views)
    monkeypatch.setattr(P, "load", lambda: ({}, [], pd.DataFrame({"BusinessDate": ["2026-11-12"]})))
    monkeypatch.setattr(P, "_cash_series", lambda txns, start, end: pd.Series([16000.0, 16059.24, 16059.24, 16059.24, 16059.24],
                                                                             index=days))
    monkeypatch.setattr(P, "account_id", lambda: 1)
    st = CM.CloseMarkStore(tmp_path / "close_marks.json")
    monkeypatch.setattr(CM, "_STORE", st)

    e = P.equity("2026-11-12", "2026-11-16")
    assert e["series"][0]["v"] == [34776.2, 36100.0, 36100.0, 36100.0, 36150.0] and e["recorded_closes"] == []

    st.put(1, dt.date(2026, 11, 13), 36138.32, 16059.24, "2026-11-13T16:20:00", True)
    e = P.equity("2026-11-12", "2026-11-16")
    assert e["series"][0]["v"] == [34776.2, 36138.32, 36138.32, 36138.32, 36150.0]
    assert e["recorded_closes"] == ["2026-11-13", "2026-11-14", "2026-11-15"]
    assert e["series"][1]["v"][1] == 16059.24                                               # the cash line is untouched

    # Monday's day P&L: net liq now against Friday's recorded close, not the rebuilt 36,100
    monkeypatch.setattr(P, "summary", lambda hub=None: {"equity": 36238.32})
    LM._PRIOR_EQUITY.clear()
    assert LM.account_day_change(today=dt.date(2026, 11, 16)) == 100.0
    LM._PRIOR_EQUITY.clear()
