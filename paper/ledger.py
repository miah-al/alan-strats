"""Portfolio-ledger writes for the paper runner, in the schema db/schema.sql defines (the layout the
database actually has): one portfolio.Position per unit, two portfolio.Leg rows per fill (long and
short leg), one portfolio.Transaction per fill (cash flow), one portfolio.ModelSignal per session
(the gate verdict) and one portfolio.Balance row per day. Positions carry the spread price as
AvgEntryPrice / AvgExitPrice; the legs carry the spread price on the long leg and 0 on the short
leg so a group nets to the spread. ``load_paper_positions`` reads it back for reports.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text

logger = logging.getLogger("paper.ledger")
COMMISSION_PER_LEG = 1.00
MULT = 100.0


def ensure_paper_account(engine, name: str = "Paper Account", broker: str = "Paper", starting_cash: Optional[float] = None) -> int:
    """The paper account, created on first use. ``starting_cash`` seeds one Cash deposit row (the
    strategy's risk capital) when the account has none, so the Paper Trading page shows an account
    value and a P&L percentage instead of zeros."""
    with engine.begin() as conn:
        row = conn.execute(text("SELECT AccountId FROM portfolio.Account WHERE Name = :n"), {"n": name}).fetchone()
        if row:
            _seed_cash(conn, int(row[0]), starting_cash)
            return int(row[0])
        conn.execute(text("INSERT INTO portfolio.Account (Name, BrokerName, AccountType, Notes) VALUES (:n, :b, 'paper', 'automated paper runner')"),
                     {"n": name, "b": broker})
        row = conn.execute(text("SELECT AccountId FROM portfolio.Account WHERE Name = :n"), {"n": name}).fetchone()
        _seed_cash(conn, int(row[0]), starting_cash)
        return int(row[0])


def _seed_cash(conn, account_id: int, starting_cash: Optional[float]) -> None:
    if not starting_cash or starting_cash <= 0:
        return
    has = conn.execute(text("SELECT 1 FROM portfolio.Balance WHERE AccountId = :a AND BalanceType = 'Cash'"), {"a": account_id}).fetchone()
    if has:
        return
    today = date.today()
    conn.execute(text("INSERT INTO portfolio.Balance (AccountId, BalanceDate, CashBalance, PortfolioValue, TotalEquity, BalanceType, Amount, BusinessDate) "
                      "VALUES (:a, :d, :c, 0, :c, 'Cash', :c, :d)"), {"a": account_id, "d": today, "c": float(starting_cash)})


def _security_id(conn, underlying: str) -> int:
    """Position.SecurityId is the underlying's mkt.Ticker id (created if missing)."""
    row = conn.execute(text("SELECT TickerId FROM mkt.Ticker WHERE Symbol = :s"), {"s": underlying.upper()}).fetchone()
    if row:
        return int(row[0])
    conn.execute(text("INSERT INTO mkt.Ticker (Symbol, Name, AssetClass) VALUES (:s, :s, 'index')"), {"s": underlying.upper()})
    return int(conn.execute(text("SELECT TickerId FROM mkt.Ticker WHERE Symbol = :s"), {"s": underlying.upper()}).fetchone()[0])


def _page_security_id(conn, symbol: str, underlying: str, cp: str, strike: float, expiry: date) -> int:
    """portfolio.Security row per option contract (what the Paper Trading page joins on)."""
    row = conn.execute(text("SELECT SecurityId FROM portfolio.Security WHERE Symbol = :s AND SecurityType = 'Option'"), {"s": symbol[:40]}).fetchone()
    if row:
        return int(row[0])
    conn.execute(text("INSERT INTO portfolio.Security (Symbol, Underlying, SecurityType, OptionType, Strike, Expiration, Multiplier) "
                      "VALUES (:s, :u, 'Option', :ot, :k, :e, 100)"),
                 {"s": symbol[:40], "u": underlying, "ot": ("CALL" if cp == "C" else "PUT"), "k": float(strike), "e": expiry})
    return int(conn.execute(text("SELECT SecurityId FROM portfolio.Security WHERE Symbol = :s AND SecurityType = 'Option'"), {"s": symbol[:40]}).fetchone()[0])


def _leg_prices(px: float, extra: dict | None) -> tuple[float, float]:
    """Split a spread's fill price across its two legs, at each leg's own market.

    The long leg used to carry the whole debit and the short leg a flat 0.00. Cash and net entry
    came out right, so nothing downstream that only reads totals ever noticed -- but anything
    reading a single leg saw a position nobody holds: a naked long put and a worthless short. That
    is what the greeks, the payoff chart and the position popup all read.

    Each leg is booked at its own mid, both shifted by half of whatever gap remains, so the two
    still difference to exactly the spread price that was paid. Without leg quotes the old
    convention stands, since a wrong split would be worse than an obviously conventional one.
    """
    e = extra or {}
    try:
        lb, la = float(e["long_bid"]), float(e["long_ask"])
        sb, sa = float(e["short_bid"]), float(e["short_ask"])
    except (KeyError, TypeError, ValueError):
        return float(px), 0.0
    lm, sm = (lb + la) / 2.0, (sb + sa) / 2.0
    gap = (lm - sm) - float(px)          # the mids need not difference to what was actually paid
    lpx, spx = lm - gap / 2.0, sm + gap / 2.0
    if lpx <= 0 or spx < 0:              # a split that prices a leg at or below zero is not a split
        return float(px), 0.0
    return round(lpx, 4), round(spx, 4)


def _legs(fill: dict) -> tuple[str, float, float]:
    cp = "C" if fill["direction"] == "bull" else "P"
    long_k, short_k = (fill["kl"], fill["kh"]) if cp == "C" else (fill["kh"], fill["kl"])
    return cp, float(long_k), float(short_k)


def record_fill(engine, account_id: int, slug: str, underlying: str, expiry: date, day: date, fill: dict,
                long_symbol: str, short_symbol: str, position_id: Optional[int] = None,
                extra: Optional[dict] = None) -> Optional[int]:
    """Write one engine fill. ``open`` creates the Position and returns its id; ``add`` and ``close``
    need ``position_id``. ``fill``: m, kind, direction, kl, kh, px (spread points), lots, cash, reason."""
    kind = fill["kind"]
    if kind not in ("open", "add", "close"):
        return position_id
    cp, long_k, short_k = _legs(fill)
    px, lots = float(fill["px"]), int(fill["lots"])
    notes = json.dumps({"spread_px": px, "kind": kind, "reason": fill["reason"], "minute": fill["m"], "lots": lots,
                        "k_low": fill["kl"], "k_high": fill["kh"], "direction": fill["direction"], **(extra or {})}, default=str)[:500]
    opening = kind in ("open", "add")
    comm = 2 * lots * COMMISSION_PER_LEG if opening else 0.0
    with engine.begin() as conn:
        sid = _security_id(conn, underlying)
        if kind == "open":
            conn.execute(text("""
                INSERT INTO portfolio.Position (AccountId, SecurityId, PositionType, Direction, Quantity, OpenDate, Status,
                                                AvgEntryPrice, Commission, StrategyName, Source, Tags, Notes)
                VALUES (:aid, :sid, 'option_spread', 'long', :qty, :d, 'open', :px, :comm, :strat, 'paper', :tags, :notes)"""),
                {"aid": account_id, "sid": sid, "qty": lots, "d": day, "px": px, "comm": comm, "strat": slug,
                 "tags": f"{underlying} {'call' if cp == 'C' else 'put'} {fill['kl']:.0f}/{fill['kh']:.0f} {expiry}", "notes": notes})
            position_id = int(conn.execute(text("SELECT MAX(PositionId) FROM portfolio.Position WHERE AccountId = :aid AND StrategyName = :s"),
                                           {"aid": account_id, "s": slug}).fetchone()[0])
        if position_id is None:
            raise ValueError(f"{kind} without a position id")
        n_legs = int(conn.execute(text("SELECT COUNT(*) FROM portfolio.Leg WHERE PositionId = :p"), {"p": position_id}).fetchone()[0])
        lpx, spx = _leg_prices(px, extra)
        leg_rows = [(long_symbol, "BTO" if opening else "STC", long_k, lpx), (short_symbol, "STO" if opening else "BTC", short_k, spx)]
        for i, (sym, action, k, fpx) in enumerate(leg_rows):
            conn.execute(text("""
                INSERT INTO portfolio.Leg (PositionId, Symbol, OptionSymbol, InstrumentType, Action, Contracts, Strike, Expiration,
                                           ContractType, FillPrice, Commission, FillDate, LegOrder)
                VALUES (:p, :u, :os, 'option', :a, :n, :k, :e, :cp, :fp, :c, :d, :lo)"""),
                {"p": position_id, "u": underlying, "os": sym[:30], "a": action, "n": lots, "k": k, "e": expiry, "cp": cp, "fp": fpx,
                 "c": (COMMISSION_PER_LEG * lots if opening else 0.0), "d": day, "lo": min(255, n_legs + i + 1)})
        # One transaction per leg, in the layout the Paper Trading page groups (TradeGroupId = the
        # unit's PositionId). Each leg carries its own price (see _leg_prices); the net cash stays
        # whole on the long leg, because the page sums Amount to get cash and that total is the one
        # number here that has always been right.
        tgid = f"{underlying[:4]}-{slug[:8].upper()}-{position_id}"
        src = "Paper" if opening else {"target": "Target", "stop": "Stop", "daycap": "DayCap", "time": "Time", "settle": "Settle"}.get(fill["reason"], "Close")
        page_notes = (("" if opening else "CLOSE ") + notes)[:500]
        for i, (sym, action, k, fpx) in enumerate(leg_rows):
            psid = _page_security_id(conn, sym, underlying, cp, k, expiry)
            conn.execute(text("""
                INSERT INTO portfolio.[Transaction] (AccountId, SecurityId, PositionId, TransactionDate, Action, Quantity, Price, Amount,
                                                     Commission, StrategyName, Notes, BusinessDate, TradeGroupId, Direction, TransactionPrice,
                                                     LegType, Source)
                VALUES (:aid, :sid, :p, :d, :a, :q, :px, :amt, :c, :s, :n, :d, :tg, :dir, :px, :lt, :src)"""),
                {"aid": account_id, "sid": psid, "p": position_id, "d": day, "a": ("BUY" if opening else "SELL"), "q": lots, "px": fpx,
                 "amt": (float(fill["cash"]) if i == 0 else 0.0), "c": (COMMISSION_PER_LEG * lots if opening else 0.0), "s": slug, "n": page_notes,
                 "tg": tgid, "dir": (("Buy" if action.startswith("B") else "Sell")), "lt": ("LongLeg" if i == 0 else "ShortLeg"), "src": src})
        if kind == "add":
            row = conn.execute(text("SELECT Quantity, AvgEntryPrice, Commission FROM portfolio.Position WHERE PositionId = :p"), {"p": position_id}).fetchone()
            q0, px0, c0 = float(row[0]), float(row[1]), float(row[2])
            conn.execute(text("UPDATE portfolio.Position SET Quantity = :q, AvgEntryPrice = :px, Commission = :c, UpdatedAt = SYSUTCDATETIME() WHERE PositionId = :p"),
                         {"q": q0 + lots, "px": (q0 * px0 + lots * px) / (q0 + lots), "c": c0 + comm, "p": position_id})
        elif kind == "close":
            row = conn.execute(text("SELECT Quantity, AvgEntryPrice, Commission FROM portfolio.Position WHERE PositionId = :p"), {"p": position_id}).fetchone()
            q0, px0, c0 = float(row[0]), float(row[1]), float(row[2])
            # Realised P&L is the cash this position actually moved -- every leg of every fill,
            # closing row included. Recomputing it from entry and exit prices and then subtracting
            # the Commission column misses anything that is not commission: the per-round-trip fees
            # leave cash but live in no column, so the figure read $3 better than the account did and
            # would have drifted further with every trade. Summing Amount cannot disagree with cash.
            cash_pnl = conn.execute(text("SELECT SUM(Amount) FROM portfolio.[Transaction] WHERE PositionId = :p"),
                                    {"p": position_id}).fetchone()[0]
            pnl = float(cash_pnl) if cash_pnl is not None else ((px - px0) * MULT * q0 - c0)
            conn.execute(text("""UPDATE portfolio.Position SET Status = :st, CloseDate = :d, AvgExitPrice = :px, RealizedPnL = :pnl,
                                 UpdatedAt = SYSUTCDATETIME() WHERE PositionId = :p"""),
                         {"st": ("expired" if fill["reason"] == "settle" else "closed"), "d": day, "px": px, "pnl": pnl, "p": position_id})
    return position_id


def record_session(engine, day: date, underlying: str, slug: str, blocked: bool, reason: str, note: str = "") -> None:
    """One ModelSignal row per session: PredictedLabel 1 = open for trading, 0 = blocked."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM portfolio.ModelSignal WHERE SignalDate = :d AND Symbol = :s AND SpreadType = :t"),
                     {"d": day, "s": underlying, "t": slug[:30]})
        conn.execute(text("""INSERT INTO portfolio.ModelSignal (SignalDate, Symbol, SpreadType, PredictedLabel, Confidence, ModelVersion, WasTaken, Notes)
                             VALUES (:d, :s, :t, :lab, 1.0, 'paper-runner', :taken, :n)"""),
                     {"d": day, "s": underlying, "t": slug[:30], "lab": (0 if blocked else 1), "taken": (0 if blocked else 1),
                      "n": (f"blocked: {reason}" if blocked else ("open" + (f"; {note}" if note else "")))[:500]})


def record_day_balance(engine, account_id: int, day: date, day_pnl: float) -> None:
    with engine.begin() as conn:
        prev = conn.execute(text("SELECT TOP 1 TotalEquity, RealizedYTD FROM portfolio.Balance WHERE AccountId = :a AND BalanceDate < :d AND BalanceType IS NULL ORDER BY BalanceDate DESC"),
                            {"a": account_id, "d": day}).fetchone()
        seed = conn.execute(text("SELECT TOP 1 Amount FROM portfolio.Balance WHERE AccountId = :a AND BalanceType = 'Cash' ORDER BY BusinessDate DESC"), {"a": account_id}).fetchone()
        base_eq = float(prev[0]) if prev and prev[0] is not None else (float(seed[0]) if seed and seed[0] is not None else 100_000.0)
        ytd = float(prev[1]) if prev and prev[1] is not None else 0.0
        conn.execute(text("DELETE FROM portfolio.Balance WHERE AccountId = :a AND BalanceDate = :d AND BalanceType IS NULL"), {"a": account_id, "d": day})
        conn.execute(text("""INSERT INTO portfolio.Balance (AccountId, BalanceDate, CashBalance, PortfolioValue, TotalEquity, DayPnL, RealizedYTD)
                             VALUES (:a, :d, :c, 0, :e, :p, :y)"""),
                     {"a": account_id, "d": day, "c": base_eq + day_pnl, "e": base_eq + day_pnl, "p": day_pnl, "y": ytd + day_pnl})


def account_day_pnl(engine, account_id: int, day: date) -> float:
    """Realised P&L of every paper position of the account closed on ``day`` (all runners, all strategies)."""
    with engine.connect() as conn:
        v = conn.execute(text("SELECT SUM(RealizedPnL) FROM portfolio.Position WHERE AccountId = :a AND Source = 'paper' "
                              "AND CloseDate = :d"), {"a": account_id, "d": day}).fetchone()[0]
    return float(v) if v is not None else 0.0


def load_paper_positions(engine, slug: str, from_date: Optional[date] = None) -> pd.DataFrame:
    """Positions written by the runner for ``slug``: one row per unit with entry/exit, P&L, status, notes."""
    q = ("SELECT PositionId, OpenDate, CloseDate, Status, Quantity, AvgEntryPrice, AvgExitPrice, RealizedPnL, Commission, Tags, Notes "
         "FROM portfolio.Position WHERE StrategyName = :s AND Source = 'paper'")
    params: dict = {"s": slug}
    if from_date is not None:
        q += " AND OpenDate >= :d"; params["d"] = from_date
    q += " ORDER BY OpenDate, PositionId"
    with engine.connect() as conn:
        res = conn.execute(text(q), params)
        return pd.DataFrame(res.fetchall(), columns=res.keys())


def delete_paper_day(engine, slug: str, day: date) -> int:
    """Remove everything the runner wrote for one session (a replay written by mistake, a re-run)."""
    with engine.begin() as conn:
        ids = [int(r[0]) for r in conn.execute(text("SELECT PositionId FROM portfolio.Position WHERE StrategyName = :s AND Source = 'paper' AND OpenDate = :d"),
                                               {"s": slug, "d": day}).fetchall()]
        for pid in ids:
            conn.execute(text("DELETE FROM portfolio.Leg WHERE PositionId = :p"), {"p": pid})
            conn.execute(text("DELETE FROM portfolio.[Transaction] WHERE PositionId = :p"), {"p": pid})
            conn.execute(text("DELETE FROM portfolio.DailyMark WHERE PositionId = :p"), {"p": pid})
            conn.execute(text("DELETE FROM portfolio.ModelSignal WHERE PositionId = :p"), {"p": pid})
            conn.execute(text("DELETE FROM portfolio.Position WHERE PositionId = :p"), {"p": pid})
        conn.execute(text("DELETE FROM portfolio.ModelSignal WHERE SpreadType = :s AND SignalDate = :d"), {"s": slug[:30], "d": day})
    return len(ids)


# multi-leg structures and the SYNTHETIC futures hedge (ndx_gamma_scalp): new code paths in their own module, exposed
# here so the runner has one ledger namespace
from .ledger_structures import record_structure_fill, record_synthetic_hedge  # noqa: E402,F401
