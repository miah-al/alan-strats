"""Ledger round trip on the live database (skips without it): open, add, close on a far-past
fake day, read back, delete. Leaves nothing behind."""
from __future__ import annotations

from datetime import date

import pytest

SLUG = "ndx_0dte_tasty"
DAY = date(2001, 1, 2)          # a day no real session will ever use


def _db():
    try:
        from db.client import get_engine
        eng = get_engine()
        with eng.connect() as c:
            c.exec_driver_sql("SELECT 1")
        return eng
    except Exception as exc:
        pytest.skip(f"database unavailable: {exc}")


def test_open_add_close_round_trip():
    eng = _db()
    from paper import ledger as L
    aid = L.ensure_paper_account(eng)
    L.delete_paper_day(eng, SLUG, DAY)
    try:
        opn = dict(m=661, kind="open", direction="bull", kl=29100.0, kh=29200.0, px=60.0, lots=1, cash=-6002.0, reason="trend")
        pid = L.record_fill(eng, aid, SLUG, "NDX", DAY, DAY, opn, "NDXP010102C29100000", "NDXP010102C29200000")
        assert pid is not None
        add = dict(m=670, kind="add", direction="bull", kl=29100.0, kh=29200.0, px=50.0, lots=1, cash=-5002.0, reason="add")
        assert L.record_fill(eng, aid, SLUG, "NDX", DAY, DAY, add, "NDXP010102C29100000", "NDXP010102C29200000", position_id=pid) == pid
        cls = dict(m=700, kind="close", direction="bull", kl=29100.0, kh=29200.0, px=60.0, lots=2, cash=11997.0, reason="target")
        L.record_fill(eng, aid, SLUG, "NDX", DAY, DAY, cls, "NDXP010102C29100000", "NDXP010102C29200000", position_id=pid)
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
    finally:
        n = L.delete_paper_day(eng, SLUG, DAY)
        assert n >= 1
        # only this test's own rows: asserting the table is empty fails whenever a real paper
        # session holds a position for the same strategy, which is exactly when the suite is most
        # likely to be run
        left = L.load_paper_positions(eng, SLUG, from_date=DAY)
        assert left.empty or pid not in set(left.PositionId)


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
    L.ensure_paper_account(eng, name=name, starting_cash=150_000.0)
    L.ensure_paper_account(eng, name=name)
    with eng.begin() as c:
        rows = c.execute(text("SELECT BalanceType, Amount FROM portfolio.Balance WHERE AccountId = :a"), {"a": aid}).fetchall()
        assert [(r[0], float(r[1])) for r in rows] == [("Cash", 150_000.0)]
        c.execute(text("DELETE FROM portfolio.Balance WHERE AccountId = :a"), {"a": aid})
        c.execute(text("DELETE FROM portfolio.Account WHERE AccountId = :a"), {"a": aid})


def test_leg_prices_split_the_spread_at_each_legs_own_market():
    """Each leg is booked near its own mid, and the two always difference to exactly the spread price
    paid; without leg quotes the old convention (all on the long leg) stands."""
    from paper.ledger import _leg_prices
    lpx, spx = _leg_prices(34.2, {"long_bid": 67.1, "long_ask": 78.2, "short_bid": 44.0, "short_ask": 47.2})
    assert abs((lpx - spx) - 34.2) < 1e-9 and 67.1 <= lpx <= 78.2 + 1 and 40 <= spx <= 47.2
    assert _leg_prices(34.2, None) == (34.2, 0.0)
    assert _leg_prices(90.0, {"long_bid": 50, "long_ask": 52, "short_bid": 1, "short_ask": 2}) == (90.0, 0.0)   # a split below zero is refused
