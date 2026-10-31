"""Ledger round trip on the live database (skips without it): open, add, close on a far-past fake day, read
back, delete. On a THROWAWAY account and a test-only strategy slug -- never the real paper account (AccountId 1,
"Paper Account", which the live runners share until 16:00 ET). Leaves nothing behind: the day's rows, the
account, and the option Security rows the fills created."""
from __future__ import annotations

from datetime import date

import pytest

SLUG = "zz_ledger_test"           # a slug no real session uses
DAY = date(2001, 1, 2)            # a day no real session will ever use
ACCOUNT = "Paper Account (ledger test)"
REAL_PAPER_ACCOUNT = 1
LONG, SHORT = "NDXP010102C29100000", "NDXP010102C29200000"


def _db():
    try:
        from db.client import get_engine
        eng = get_engine()
        with eng.connect() as c:
            c.exec_driver_sql("SELECT 1")
        return eng
    except Exception as exc:
        pytest.skip(f"database unavailable: {exc}")


def _wipe(eng, aid: int) -> int:
    """Everything this test wrote: the day's positions, then the account's rows, the account, and the two contracts'
    Security rows unless a real transaction references them. Returns the positions removed."""
    from sqlalchemy import text
    from paper import ledger as L
    assert aid != REAL_PAPER_ACCOUNT
    n = L.delete_paper_day(eng, SLUG, DAY)
    with eng.begin() as c:
        c.execute(text("DELETE FROM portfolio.[Transaction] WHERE AccountId = :a"), {"a": aid})
        c.execute(text("DELETE FROM portfolio.Balance WHERE AccountId = :a"), {"a": aid})
        c.execute(text("DELETE FROM portfolio.Account WHERE AccountId = :a"), {"a": aid})
        c.execute(text("DELETE FROM portfolio.Security WHERE Symbol IN (:l, :s) AND SecurityType = 'Option' AND NOT EXISTS "
                       "(SELECT 1 FROM portfolio.[Transaction] t WHERE t.SecurityId = portfolio.Security.SecurityId)"),
                  {"l": LONG, "s": SHORT})
    return n


def test_open_add_close_round_trip():
    eng = _db()
    from paper import ledger as L
    aid = L.ensure_paper_account(eng, name=ACCOUNT)
    assert aid != REAL_PAPER_ACCOUNT
    L.delete_paper_day(eng, SLUG, DAY)
    pid = None
    try:
        opn = dict(m=661, kind="open", direction="bull", kl=29100.0, kh=29200.0, px=60.0, lots=1, cash=-6002.0, reason="trend")
        pid = L.record_fill(eng, aid, SLUG, "NDX", DAY, DAY, opn, LONG, SHORT)
        assert pid is not None
        add = dict(m=670, kind="add", direction="bull", kl=29100.0, kh=29200.0, px=50.0, lots=1, cash=-5002.0, reason="add")
        assert L.record_fill(eng, aid, SLUG, "NDX", DAY, DAY, add, LONG, SHORT, position_id=pid) == pid
        cls = dict(m=700, kind="close", direction="bull", kl=29100.0, kh=29200.0, px=60.0, lots=2, cash=11997.0, reason="target")
        L.record_fill(eng, aid, SLUG, "NDX", DAY, DAY, cls, LONG, SHORT, position_id=pid)
        L.record_session(eng, DAY, "NDX", SLUG, False, "", note="test")
        df = L.load_paper_positions(eng, SLUG, from_date=DAY)
        row = df[df.PositionId == pid].iloc[0]
        assert row.Status == "closed" and float(row.Quantity) == 2.0
        assert abs(float(row.AvgEntryPrice) - 55.0) < 1e-6 and float(row.AvgExitPrice) == 60.0
        # Realised P&L is the cash the position moved, not a price difference with the commission
        # column deducted: -6002 - 5002 + 11997 = 993. The old expectation of 996 counted the $4 of
        # commission and silently dropped the $3 of round-trip fees, so it read better than the
        # account did -- by a little per trade, and by more every trade after that.
        assert abs(float(row.RealizedPnL) - (-6002.0 - 5002.0 + 11997.0)) < 1e-6
        assert abs(float(row.RealizedPnL) - 993.0) < 1e-6
        from sqlalchemy import text
        with eng.connect() as c:
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.Leg WHERE PositionId = :p"), {"p": pid}).scalar() == 6
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.[Transaction] WHERE PositionId = :p"), {"p": pid}).scalar() == 6   # one row per leg per fill
            # every row this test wrote sits on the throwaway account
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.[Transaction] WHERE PositionId = :p AND AccountId <> :a"),
                             {"p": pid, "a": aid}).scalar() == 0
    finally:
        n = _wipe(eng, aid)
        assert n >= 1
        left = L.load_paper_positions(eng, SLUG, from_date=DAY)
        assert left.empty or pid not in set(left.PositionId)
        from sqlalchemy import text
        with eng.connect() as c:
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.Account WHERE AccountId = :a"), {"a": aid}).scalar() == 0


def test_paper_account_is_seeded_once_with_starting_cash():
    """The first call with a starting cash writes one Cash deposit row; later calls never add another."""
    eng = _db()
    from paper import ledger as L
    from sqlalchemy import text
    name = "Paper Account (seed test)"
    with eng.begin() as c:
        row = c.execute(text("SELECT AccountId FROM portfolio.Account WHERE Name = :n"), {"n": name}).fetchone()
        if row:
            c.execute(text("DELETE FROM portfolio.Balance WHERE AccountId = :a"), {"a": row[0]})
            c.execute(text("DELETE FROM portfolio.Account WHERE AccountId = :a"), {"a": row[0]})
    aid = L.ensure_paper_account(eng, name=name, starting_cash=150_000.0)
    assert aid != REAL_PAPER_ACCOUNT
    try:
        L.ensure_paper_account(eng, name=name, starting_cash=150_000.0)
        L.ensure_paper_account(eng, name=name)
        with eng.connect() as c:
            rows = c.execute(text("SELECT BalanceType, Amount FROM portfolio.Balance WHERE AccountId = :a"), {"a": aid}).fetchall()
        assert [(r[0], float(r[1])) for r in rows] == [("Cash", 150_000.0)]
    finally:
        with eng.begin() as c:
            c.execute(text("DELETE FROM portfolio.Balance WHERE AccountId = :a"), {"a": aid})
            c.execute(text("DELETE FROM portfolio.Account WHERE AccountId = :a"), {"a": aid})


def test_the_real_paper_account_is_refused_under_the_suite():
    """The suite's guard (tests/conftest.py, api/bootstrap.py): a ledger write for AccountId 1 raises before
    reaching the server, whatever test happens to run first."""
    eng = _db()
    from sqlalchemy import text
    from api.bootstrap import ReadOnlyViolation, db_guard_installed
    assert db_guard_installed()
    with pytest.raises(ReadOnlyViolation):
        with eng.begin() as c:
            c.execute(text("INSERT INTO portfolio.Balance (AccountId, BalanceDate, CashBalance, PortfolioValue, TotalEquity, "
                           "BalanceType, Amount, BusinessDate) VALUES (:a, :d, 0, 0, 0, 'Cash', 0, :d)"),
                      {"a": REAL_PAPER_ACCOUNT, "d": DAY})


def test_leg_prices_split_the_spread_at_each_legs_own_market():
    """Each leg is booked near its own mid, and the two always difference to exactly the spread price
    paid; without leg quotes the old convention (all on the long leg) stands."""
    from paper.ledger import _leg_prices
    lpx, spx = _leg_prices(34.2, {"long_bid": 67.1, "long_ask": 78.2, "short_bid": 44.0, "short_ask": 47.2})
    assert abs((lpx - spx) - 34.2) < 1e-9 and 67.1 <= lpx <= 78.2 + 1 and 40 <= spx <= 47.2
    assert _leg_prices(34.2, None) == (34.2, 0.0)
    assert _leg_prices(90.0, {"long_bid": 50, "long_ask": 52, "short_bid": 1, "short_ask": 2}) == (90.0, 0.0)   # a split below zero is refused
