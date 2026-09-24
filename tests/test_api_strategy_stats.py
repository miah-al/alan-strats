"""strategy-stats: the per-strategy numbers on their own, and the endpoint over a throwaway account's
ledger (created and deleted by the test; account 1 is protected by the guard)."""
from __future__ import annotations

import datetime as _dt
import sys
import uuid
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
for _p in (str(REPO), str(REPO.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.bootstrap import bootstrap  # noqa: E402

bootstrap()

from api.services import strategy_stats as SS  # noqa: E402


def test_summary_numbers():
    t = pd.DataFrame({"pnl": [100.0, -50.0, 200.0, -300.0, 50.0],
                      "opened": pd.to_datetime(["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05"]),
                      "closed": pd.to_datetime(["2026-09-02", "2026-09-02", "2026-09-06", "2026-09-07", "2026-09-05"])})
    s = SS.summarize(t)
    assert s["trades"] == 5 and s["wins"] == 3 and s["win_rate"] == pytest.approx(0.6)
    assert s["pnl"] == pytest.approx(0.0) and s["avg_win"] == pytest.approx(350 / 3, abs=0.01)
    assert s["avg_loss"] == pytest.approx(-175.0) and s["profit_factor"] == pytest.approx(1.0)
    # closed order: +100, -50 (09-02), +50 (09-05), +200 (09-06), -300 (09-07): peak 300, trough 0
    assert s["max_drawdown"] == pytest.approx(-300.0)
    assert s["avg_days_held"] == pytest.approx((1 + 0 + 3 + 3 + 0) / 5)
    assert SS.summarize(t.iloc[0:0])["trades"] == 0 and SS.summarize(t.iloc[:1])["profit_factor"] is None


def _db_ok() -> bool:
    try:
        from api.services.db import ping
        return ping()[0]
    except Exception:
        return False


@pytest.mark.skipif(not _db_ok(), reason="AlanStrats database unreachable")
def test_strategy_stats_over_a_throwaway_account(monkeypatch):
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
                       "'paper', 'throwaway: tests/test_api_strategy_stats.py')"), {"n": name})
        aid = int(c.execute(text("SELECT AccountId FROM portfolio.Account WHERE Name = :n"), {"n": name}).scalar())
    assert aid != 1
    monkeypatch.setenv("ALAN_TRADER_PAPER_ACCOUNT_ID", str(aid))
    exp = _dt.date.today() + _dt.timedelta(days=20)
    try:
        def leg(k, side, px):
            return {"symbol": f"ZZQS{exp:%y%m%d}C{int(k * 1000):08d}", "security_type": "option",
                    "option_type": "call", "strike": k, "expiry": exp.isoformat(), "direction": side,
                    "quantity": 1, "price": px}

        # zz_strat_a: one win (+1.00), one loss (-0.50), both closed; manual: one open
        for tg, (buy, sell) in (("ZZQS-A-1", (2.0, 3.0)), ("ZZQS-A-2", (2.0, 1.5))):
            assert insert_paper_legs(eng, aid, "ZZQS", [leg(100, "Buy", buy)], "zz_strat_a", tg, source="Order",
                                     notes="test", commission=0.0, book_amount=True) is None
            grp = P.open_group(tg)
            assert insert_closing_transactions(eng, aid, grp, {grp["Symbol"].iloc[0]: {"price": sell}},
                                               book_amount=True) is None
        assert insert_paper_legs(eng, aid, "ZZQS", [leg(105, "Buy", 1.0)], "manual", "ZZQS-M-1", source="Order",
                                 notes="test", commission=0.0, book_amount=True) is None
        out = SS.stats()
        by = {r["strategy"]: r for r in out["strategies"]}
        a = by["zz_strat_a"]
        # the closes book the platform's $1 commission: +100 - 1 and -50 - 1
        assert a["trades"] == 2 and a["wins"] == 1 and a["pnl"] == pytest.approx(48.0) and a["open_positions"] == 0
        assert a["win_rate"] == pytest.approx(0.5) and a["max_drawdown"] <= 0
        assert by["manual"]["trades"] == 0 and by["manual"]["open_positions"] == 1
        assert out["total"]["trades"] == 2 and out["account_id"] == aid
        assert [c["field"] for c in out["table"]["columns"]][:3] == ["strategy", "strategy_label", "trades"]
        later = SS.stats(from_date=(_dt.date.today() + _dt.timedelta(days=1)).isoformat())
        assert {r["strategy"]: r["trades"] for r in later["strategies"]}.get("zz_strat_a", 0) == 0
        with pytest.raises(ValueError):
            SS.stats("2026-09-10", "2026-09-01")
    finally:
        with eng.begin() as c:
            c.execute(text("DELETE FROM portfolio.[Transaction] WHERE AccountId = :a"), {"a": aid})
            c.execute(text("DELETE FROM portfolio.Security WHERE Underlying = 'ZZQS' AND NOT EXISTS (SELECT 1 FROM "
                           "portfolio.[Transaction] t WHERE t.SecurityId = portfolio.Security.SecurityId)"))
            c.execute(text("DELETE FROM portfolio.Account WHERE AccountId = :a"), {"a": aid})
        if not had:
            uninstall_db_read_only_guard()


def test_backtest_summary_is_stored_only_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(SS, "store_backtests", lambda: False)
    import api.services.appdb as appdb
    monkeypatch.setattr(appdb, "ensure", lambda *a: calls.append(a))
    SS.record_backtest("x", "SPY", "2026-01-01", "2026-06-01", 1e5, {}, {"win_rate_pct": 60}, None)
    assert calls == []                                    # disabled under test: nothing touched
