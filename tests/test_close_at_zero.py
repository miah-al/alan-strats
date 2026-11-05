"""A closing fill at 0.00 books 0.00 (engine/positions.py insert_closing_transactions), not the leg's opening price:
2026-11-05, the desk's 7320/7300 put spread was flattened at 15:55 with the long 7300 put sold at its 0.00 bid, and
the ledger booked it at 4.375 (its 13:31 entry), +$432 the spread never made. Over a throwaway account (deleted)."""
from __future__ import annotations

import datetime as _dt
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()


def _db_ok() -> bool:
    try:
        from api.services.db import ping
        return ping()[0]
    except Exception:
        return False


@pytest.mark.skipif(not _db_ok(), reason="AlanStrats database unreachable")
def test_a_leg_closed_at_zero_books_zero_not_its_entry(monkeypatch):
    from sqlalchemy import text
    from api.bootstrap import db_guard_installed, install_db_read_only_guard, uninstall_db_read_only_guard
    from api.services import paper as P
    from api.services.db import require_db
    from engine.positions import insert_closing_transactions, insert_paper_legs
    had = db_guard_installed()
    install_db_read_only_guard()
    eng = require_db()
    name = f"alan_trader service tests {uuid.uuid4().hex[:8]}"
    with eng.begin() as c:
        c.execute(text("INSERT INTO portfolio.Account (Name, BrokerName, AccountType, Notes) VALUES (:n, 'Paper', "
                       "'paper', 'throwaway: tests/test_close_at_zero.py')"), {"n": name})
        aid = int(c.execute(text("SELECT AccountId FROM portfolio.Account WHERE Name = :n"), {"n": name}).scalar())
    assert aid != 1
    monkeypatch.setenv("ALAN_TRADER_PAPER_ACCOUNT_ID", str(aid))
    exp = _dt.date.today() + _dt.timedelta(days=20)

    def leg(k, side, px):
        return {"symbol": f"ZZQZ{exp:%y%m%d}P{int(k * 1000):08d}", "security_type": "option", "option_type": "put",
                "strike": k, "expiry": exp.isoformat(), "direction": side, "quantity": 1, "price": px}
    try:
        # 11/05: sold the 7320 put at 6.825, bought the 7300 put at 4.375
        assert insert_paper_legs(eng, aid, "ZZQZ", [leg(7320, "Sell", 6.825), leg(7300, "Buy", 4.375)], "zz_desk",
                                 "ZZQZ-1", source="Order", notes="test", commission=0.0, book_amount=True) is None
        grp = P.open_group("ZZQZ-1")
        short, long_ = (grp[grp["Direction"].str.upper().str.startswith(d)]["Symbol"].iloc[0] for d in ("S", "B"))
        # 15:55: bought the 7320 back at 0.10, sold the 7300 at its 0.00 bid
        assert insert_closing_transactions(eng, aid, grp, {short: {"price": 0.10, "fee_per_contract": 0.0},
                                                           long_: {"price": 0.0, "fee_per_contract": 0.0}},
                                           book_amount=True) is None
        with eng.connect() as c:
            rows = c.execute(text("SELECT s.Symbol, t.Direction, t.TransactionPrice, t.Amount FROM portfolio.[Transaction] t "
                                  "JOIN portfolio.Security s ON s.SecurityId = t.SecurityId WHERE t.AccountId = :a "
                                  "AND t.Source = 'Close'"), {"a": aid}).fetchall()
        closes = {(str(r[0]), str(r[1]).upper()): (float(r[2]), float(r[3])) for r in rows}
        assert closes[(long_, "SELL")] == (0.0, 0.0)              # was (4.375, +437.5)
        assert closes[(short, "BUY")] == (pytest.approx(0.10), pytest.approx(-10.0))
        # no price given at all still falls back as before (the leg's opening price)
        assert insert_paper_legs(eng, aid, "ZZQZ", [leg(7300, "Buy", 4.375)], "zz_desk", "ZZQZ-2", source="Order",
                                 notes="test", commission=0.0, book_amount=True) is None
        g2 = P.open_group("ZZQZ-2")
        assert insert_closing_transactions(eng, aid, g2, {}, book_amount=True) is None
    finally:
        with eng.begin() as c:
            c.execute(text("DELETE FROM portfolio.[Transaction] WHERE AccountId = :a"), {"a": aid})
            c.execute(text("DELETE FROM portfolio.Security WHERE Underlying = 'ZZQZ' AND NOT EXISTS (SELECT 1 FROM "
                           "portfolio.[Transaction] t WHERE t.SecurityId = portfolio.Security.SecurityId)"))
            c.execute(text("DELETE FROM portfolio.Account WHERE AccountId = :a"), {"a": aid})
        if not had:
            uninstall_db_read_only_guard()
