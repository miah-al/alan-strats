"""Ledger round trip for a straddle and the SYNTHETIC futures hedge on the live database (skips without it), on a
THROWAWAY account and a test-only strategy slug on a far-past day: never the real paper account (AccountId 1,
"Paper Account"). Open, adjust, close; read back through the Paper Trading page's own loaders; delete everything,
account included."""
from __future__ import annotations

from datetime import date

import pytest

SLUG = "zz_gamma_test"
DAY = date(2001, 1, 3)                       # a day no real session will ever use
ACCOUNT = "Paper Account (gamma scalp test)"


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
        # the synthetic future's Security row too, unless a real session's rows reference it
        c.execute(text("DELETE FROM portfolio.Security WHERE SecurityType = 'SynFuture' AND SecurityId NOT IN "
                       "(SELECT SecurityId FROM portfolio.[Transaction])"))


def test_straddle_and_synthetic_hedge_round_trip_on_a_throwaway_account():
    eng = _db()
    from sqlalchemy import text
    from paper import ledger as L
    from paper.ledger_structures import HEDGE_MULTIPLIER, HEDGE_SYMBOL
    from strategy_api.live import SYNTHETIC_FUTURE_TYPE
    from engine.positions import get_closed_trade_groups, get_open_trade_groups, load_transactions
    aid = L.ensure_paper_account(eng, name=ACCOUNT)
    assert aid != 1
    L.delete_paper_day(eng, SLUG, DAY)
    syms = ["NDXP010103C30325000", "NDXP010103P30325000"]
    try:
        # ── the straddle: open (two legs bought), later settled ──
        opn = dict(m=631, kind="open", direction="long", kl=30325.0, kh=30325.0, px=279.0, lots=1, cash=-27902.0, reason="through_ask",
                   struct="straddle", legs=[["C", 30325.0, 1, 139.5], ["P", 30325.0, 1, 139.5]], delta=-0.16, iv=0.09, ndx=30335.0)
        pid = L.record_structure_fill(eng, aid, SLUG, "NDX", DAY, DAY, opn, syms)
        assert pid is not None
        # ── the hedge: sell 0.8 at the entry, buy 0.3 back, flat at the close ──
        h1 = dict(m=631, kind="hedge", direction="sell", kl=0.0, kh=0.0, px=30334.875, lots=0.8, units=0.8, cash=0.8 * 30334.875 * 20 - 1.0,
                  reason="entry: sell 0.800 NQ-eq [SYNTHETIC]", struct="hedge", symbol=HEDGE_SYMBOL, synthetic=True, final=False, ndx=30335.0,
                  hedge_units=-0.8, hedge_avg=30334.875, hedge_pnl=-1.0, fee=1.0)
        hpid = L.record_synthetic_hedge(eng, aid, SLUG, "NDX", DAY, h1)
        assert hpid is not None and hpid != pid
        h2 = dict(m=700, kind="hedge", direction="buy", kl=0.0, kh=0.0, px=30300.125, lots=0.3, units=0.3, cash=-(0.3 * 30300.125 * 20) - 0.375,
                  reason="band: buy 0.300 NQ-eq [SYNTHETIC]", struct="hedge", symbol=HEDGE_SYMBOL, synthetic=True, final=False, ndx=30300.0,
                  hedge_units=-0.5, hedge_avg=30334.875, hedge_pnl=100.0, fee=0.375)
        assert L.record_synthetic_hedge(eng, aid, SLUG, "NDX", DAY, h2, position_id=hpid) == hpid
        txns = load_transactions(eng, aid)
        opened = get_open_trade_groups(txns)
        assert len(opened) == 2, "the straddle and the hedge book are two open groups"
        hg = [g for g in opened.values() if (g.SecurityType == SYNTHETIC_FUTURE_TYPE).all()][0]
        assert len(hg) == 2 and float(hg.Multiplier.iloc[0]) == HEDGE_MULTIPLIER and set(hg.Symbol) == {HEDGE_SYMBOL}
        assert set(hg.LegType) == {"Hedge"} and hg.Notes.str.contains("synthetic").all() and not hg.Notes.str.upper().str.contains("CLOSE").any()
        assert sorted(float(q) for q in hg.Quantity) == [0.3, 0.8]
        with eng.connect() as c:
            row = c.execute(text("SELECT PositionType, Direction, Quantity, Status, Tags FROM portfolio.Position WHERE PositionId = :p"), {"p": hpid}).fetchone()
        assert row[0] == "equity" and row[1] == "short" and float(row[2]) == 0.5 and row[3] == "open" and "SYNTHETIC" in row[4]
        # ── the close: the hedge bought back at the 16:00 print, the straddle settled ──
        h3 = dict(m=960, kind="hedge", direction="buy", kl=0.0, kh=0.0, px=30400.125, lots=0.5, units=0.5, cash=-(0.5 * 30400.125 * 20) - 0.625,
                  reason="settle: buy 0.500 NQ-eq [SYNTHETIC]", struct="hedge", symbol=HEDGE_SYMBOL, synthetic=True, final=True, ndx=30400.0,
                  hedge_units=0.0, hedge_avg=0.0, hedge_pnl=-1000.0, fee=0.625)
        assert L.record_synthetic_hedge(eng, aid, SLUG, "NDX", DAY, h3, position_id=hpid) == hpid
        cls = dict(m=960, kind="close", direction="long", kl=30325.0, kh=30325.0, px=75.0, lots=1, cash=7499.0, reason="settle",
                   struct="straddle", legs=[["C", 30325.0, 1, 75.0], ["P", 30325.0, 1, 0.0]], delta=1.0, iv=0.09, ndx=30400.0, hedge_pnl=-1000.0)
        assert L.record_structure_fill(eng, aid, SLUG, "NDX", DAY, DAY, cls, syms, position_id=pid) == pid
        df = L.load_paper_positions(eng, SLUG, from_date=DAY).set_index("PositionId")
        assert df.loc[pid, "Status"] == "expired" and float(df.loc[pid, "AvgEntryPrice"]) == 279.0 and float(df.loc[pid, "AvgExitPrice"]) == 75.0
        assert abs(float(df.loc[pid, "RealizedPnL"]) - (-27902.0 + 7499.0)) < 1e-6
        hedge_cash = h1["cash"] + h2["cash"] + h3["cash"]
        # Amount is DECIMAL(14,2): eighth-of-a-point fills round to the cent on the way in
        assert df.loc[hpid, "Status"] == "closed" and abs(float(df.loc[hpid, "RealizedPnL"]) - hedge_cash) < 0.02 and float(df.loc[hpid, "Quantity"]) == 0.0
        assert abs(hedge_cash - ((0.8 * 30334.875 - 0.3 * 30300.125 - 0.5 * 30400.125) * 20 - 2.0)) < 1e-6    # sold high, bought back higher, fees
        with eng.connect() as c:
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.Leg WHERE PositionId = :p"), {"p": pid}).scalar() == 4
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.Leg WHERE PositionId = :p"), {"p": hpid}).scalar() == 0
            assert c.execute(text("SELECT COUNT(*) FROM portfolio.[Transaction] WHERE PositionId = :p"), {"p": hpid}).scalar() == 3
            sec = c.execute(text("SELECT SecurityType, Multiplier, Underlying FROM portfolio.Security WHERE Symbol = :s"), {"s": HEDGE_SYMBOL}).fetchone()
        assert sec[0] == SYNTHETIC_FUTURE_TYPE and int(sec[1]) == HEDGE_MULTIPLIER and sec[2] == "NDX"
        # the Paper Trading page: both groups closed, the hedge's P&L the cash it moved, the day's account P&L the sum
        txns = load_transactions(eng, aid)
        assert not get_open_trade_groups(txns)
        closed = {r["TradeGroupId"]: r for r in get_closed_trade_groups(txns)}
        assert len(closed) == 2
        hrow = [r for r in closed.values() if r["TradeGroupId"].endswith(str(hpid))][0]
        assert abs(hrow["P&L $"] - hedge_cash) < 0.02
        assert abs(L.account_day_pnl(eng, aid, DAY) - (hedge_cash - 27902.0 + 7499.0)) < 0.02
    finally:
        _wipe(eng, aid)
        left = L.load_paper_positions(eng, SLUG, from_date=DAY)
        assert left.empty


def test_a_flat_hedge_book_that_never_traded_books_nothing():
    eng = _db()
    from paper import ledger as L
    aid = L.ensure_paper_account(eng, name=ACCOUNT)
    try:
        final = dict(m=960, kind="hedge", direction="flat", kl=0.0, kh=0.0, px=30400.0, lots=0.0, units=0.0, cash=0.0, reason="settle [SYNTHETIC]",
                     struct="hedge", symbol="NQ=NDX", synthetic=True, final=True, ndx=30400.0, hedge_units=0.0, hedge_avg=0.0, hedge_pnl=0.0, fee=0.0)
        assert L.record_synthetic_hedge(eng, aid, SLUG, "NDX", DAY, final) is None
        assert L.load_paper_positions(eng, SLUG, from_date=DAY).empty
    finally:
        _wipe(eng, aid)
