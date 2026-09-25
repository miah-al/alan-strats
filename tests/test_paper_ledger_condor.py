"""Ledger round trip for a four-leg iron condor (ndx_0dte_condor) on the live database (skips without it), on a
THROWAWAY account and a test-only strategy slug on a far-past day: never the real paper account (AccountId 1,
"Paper Account"). Sold, then settled through a short strike; read back through the Paper Trading page's own
loaders; everything deleted, account included."""
from __future__ import annotations

from datetime import date

import pytest

SLUG = "zz_condor_test"
DAY = date(2001, 1, 4)
ACCOUNT = "Paper Account (condor test)"
KP, KC = 29950.0, 30675.0


def _db():
    try:
        from db.client import get_engine
        eng = get_engine()
        with eng.connect() as c:
            c.exec_driver_sql("SELECT 1")
        return eng
    except Exception as exc:
        pytest.skip(f"database unavailable: {exc}")


def _wipe(eng, aid):
    from sqlalchemy import text
    from paper import ledger as L
    L.delete_paper_day(eng, SLUG, DAY)
    with eng.begin() as c:
        c.execute(text("DELETE FROM portfolio.[Transaction] WHERE AccountId = :a"), {"a": aid})
        c.execute(text("DELETE FROM portfolio.Balance WHERE AccountId = :a"), {"a": aid})
        c.execute(text("DELETE FROM portfolio.Account WHERE AccountId = :a"), {"a": aid})


def test_a_short_condor_books_as_one_position_with_four_legs_and_settles_through_a_short():
    eng = _db()
    from sqlalchemy import text
    from paper import ledger as L
    from engine.positions import get_closed_trade_groups, get_open_trade_groups, load_transactions
    from api.services import risk as RK
    aid = L.ensure_paper_account(eng, name=ACCOUNT)
    assert aid != 1
    L.delete_paper_day(eng, SLUG, DAY)
    syms = ["NDXP010104P29950000", "NDXP010104C30675000", "NDXP010104P29850000", "NDXP010104C30775000"]
    legs_open = [["P", KP, 1, 40.0], ["C", KC, 1, 39.0], ["P", KP - 100, -1, 31.0], ["C", KC + 100, -1, 32.0]]     # 16.0 credit
    try:
        opn = dict(m=600, kind="open", direction="short", kl=KP, kh=KC, px=16.0, lots=1, cash=1596.0, reason="through_bid",
                   struct="iron_condor:100", legs=legs_open, delta=-0.02, iv=0.20, ndx=30300.0, width=4.0, capture=-0.5)
        pid = L.record_structure_fill(eng, aid, SLUG, "NDX", DAY, DAY, opn, syms)
        assert pid is not None
        txns = load_transactions(eng, aid)
        grp = get_open_trade_groups(txns)
        assert len(grp) == 1
        g = list(grp.values())[0]
        assert len(g) == 4 and set(g.Symbol) == set(syms) and (g.SecurityType == "Option").all()
        # the SELLER of the structure: the shorts are sold, the wings bought
        by_sym = {r.Symbol: r for _, r in g.iterrows()}
        assert by_sym[syms[0]].Direction == "Sell" and by_sym[syms[1]].Direction == "Sell"
        assert by_sym[syms[2]].Direction == "Buy" and by_sym[syms[3]].Direction == "Buy"
        assert float(by_sym[syms[0]].TransactionPrice) == 40.0 and float(by_sym[syms[3]].TransactionPrice) == 32.0
        assert abs(float(g.Amount.sum()) - 1596.0) < 1e-6
        nl = RK.net_legs(g)
        assert sorted(l.qty for l in nl) == [-1.0, -1.0, 1.0, 1.0] and "condor" in RK.describe_structure(nl).lower()
        with eng.connect() as c:
            row = c.execute(text("SELECT PositionType, Direction, Quantity, Status, Tags, AvgEntryPrice FROM portfolio.Position WHERE PositionId = :p"),
                            {"p": pid}).fetchone()
            assert row[0] == "option_spread" and row[1] == "short" and float(row[2]) == 1.0 and row[3] == "open" and float(row[5]) == 16.0
            assert "iron_condor:100" in row[4] and "29950" in row[4] and "30675" in row[4]
            acts = [r[0] for r in c.execute(text("SELECT Action FROM portfolio.Leg WHERE PositionId = :p ORDER BY LegOrder"), {"p": pid})]
            assert acts == ["STO", "STO", "BTO", "BTO"]
        # settled 40 through the short call: the call leg is worth 40, the rest nothing
        cls = dict(m=960, kind="close", direction="short", kl=KP, kh=KC, px=40.0, lots=1, cash=-4000.0, reason="settle",
                   struct="iron_condor:100", legs=[["P", KP, 1, 0.0], ["C", KC, 1, 40.0], ["P", KP - 100, -1, 0.0], ["C", KC + 100, -1, 0.0]],
                   delta=1.0, iv=0.20, ndx=KC + 40.0, full_width=False)
        assert L.record_structure_fill(eng, aid, SLUG, "NDX", DAY, DAY, cls, syms, position_id=pid) == pid
        df = L.load_paper_positions(eng, SLUG, from_date=DAY).set_index("PositionId")
        assert df.loc[pid, "Status"] == "expired" and float(df.loc[pid, "AvgExitPrice"]) == 40.0
        assert abs(float(df.loc[pid, "RealizedPnL"]) - (1596.0 - 4000.0)) < 1e-6
        txns = load_transactions(eng, aid)
        assert not get_open_trade_groups(txns)
        closed = get_closed_trade_groups(txns)
        assert len(closed) == 1 and abs(closed[0]["P&L $"] - (1596.0 - 4000.0)) < 1e-6
        assert abs(L.account_day_pnl(eng, aid, DAY) - (1596.0 - 4000.0)) < 1e-6
        with eng.connect() as c:
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.Leg WHERE PositionId = :p"), {"p": pid}).scalar() == 8
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.[Transaction] WHERE PositionId = :p"), {"p": pid}).scalar() == 8
            acts = [r[0] for r in c.execute(text("SELECT Action FROM portfolio.Leg WHERE PositionId = :p ORDER BY LegOrder"), {"p": pid})][4:]
            assert acts == ["BTC", "BTC", "STC", "STC"]
    finally:
        _wipe(eng, aid)
        assert L.load_paper_positions(eng, SLUG, from_date=DAY).empty
