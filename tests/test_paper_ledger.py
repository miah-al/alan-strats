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
        assert abs(float(row.RealizedPnL) - ((60.0 - 55.0) * 100 * 2 - 4.0)) < 1e-6     # 4 opening legs at $1
        from sqlalchemy import text
        with eng.connect() as c:
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.Leg WHERE PositionId = :p"), {"p": pid}).scalar() == 6
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.[Transaction] WHERE PositionId = :p"), {"p": pid}).scalar() == 3
    finally:
        n = L.delete_paper_day(eng, SLUG, DAY)
        assert n >= 1
        assert L.load_paper_positions(eng, SLUG, from_date=DAY).empty
