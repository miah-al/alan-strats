"""Ledger writes for multi-leg option structures and the SYNTHETIC futures hedge (ndx_gamma_scalp), beside
``paper.ledger.record_fill`` (the vertical's, untouched).

A straddle / iron fly is one portfolio.Position (option_spread, Direction long | short) with a Leg and a
Transaction per leg (two or four, same expiry), grouped for the Paper Trading page by TradeGroupId like a
vertical. The synthetic NQ-equivalent hedge is one Position per session in the ledger's only fitting
PositionType ('equity'), a portfolio.Security of type SynFuture (symbol NQ=NDX, multiplier 20) and one
Transaction per hedge trade with the fractional NQ-equivalents in Quantity, the index level paid in Price and
the cash it moved (fee included) in Amount. Nothing about the hedge is a real future: the security type, the
Tags and every Notes field say synthetic, and its P&L is the cash its rows moved. No Leg rows for the hedge:
portfolio.Leg is the option-contract table (integer Contracts, a strike, an expiry).
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional

from sqlalchemy import text

from strategy_api.live import SYNTHETIC_FUTURE_TYPE

HEDGE_SYMBOL = "NQ=NDX"
HEDGE_MULTIPLIER = 20


def _no_close_word(text_: str) -> str:
    """The Paper Trading page closes a trade group on any transaction whose Notes contain CLOSE (engine.positions);
    a hedge adjustment's note must never say it."""
    return re.sub(r"close", "clse", text_, flags=re.I)


def record_structure_fill(engine, account_id: int, slug: str, underlying: str, expiry: date, day: date, fill: dict,
                          symbols: list, position_id: Optional[int] = None, extra: Optional[dict] = None) -> Optional[int]:
    """Write one structure fill (``struct`` straddle | iron_fly, ``direction`` long | short, ``legs`` =
    [[cp, strike, sign, price], ...] in long-structure terms, ``px`` the structure price, ``cash`` the net cash).
    ``open`` creates the Position and returns its id; ``close`` needs ``position_id``. ``symbols`` are the legs'
    option symbols in the same order."""
    from . import ledger as L
    kind = fill["kind"]
    if kind not in ("open", "close"):
        return position_id
    legs = list(fill.get("legs") or [])
    if not legs or len(symbols) != len(legs):
        raise ValueError(f"structure fill needs its legs and one symbol per leg ({len(legs)} legs, {len(symbols)} symbols)")
    long_side = str(fill["direction"]) == "long"
    px, lots = float(fill["px"]), int(fill["lots"])
    struct = str(fill.get("struct"))
    notes = json.dumps({"structure_px": px, "struct": struct, "kind": kind, "reason": fill["reason"], "minute": fill["m"], "lots": lots,
                        "k_low": fill["kl"], "k_high": fill["kh"], "direction": fill["direction"], "delta": fill.get("delta"),
                        "iv": fill.get("iv"), "ndx": fill.get("ndx"), **(extra or {})}, default=str)[:500]
    opening = kind == "open"
    comm = len(legs) * lots * L.COMMISSION_PER_LEG if opening else 0.0
    body = (float(fill["kl"]) + float(fill["kh"])) / 2.0
    tag = (f"{underlying} {struct} {body:.0f}" + (f" wings {float(fill['kl']):.0f}/{float(fill['kh']):.0f}" if struct == "iron_fly" else "")
           + f" {expiry} {fill['direction']}")
    with engine.begin() as conn:
        sid = L._security_id(conn, underlying)
        if kind == "open":
            conn.execute(text("""
                INSERT INTO portfolio.Position (AccountId, SecurityId, PositionType, Direction, Quantity, OpenDate, Status,
                                                AvgEntryPrice, Commission, StrategyName, Source, Tags, Notes)
                VALUES (:aid, :sid, 'option_spread', :dir, :qty, :d, 'open', :px, :comm, :strat, 'paper', :tags, :notes)"""),
                {"aid": account_id, "sid": sid, "dir": ("long" if long_side else "short"), "qty": lots, "d": day, "px": px, "comm": comm,
                 "strat": slug, "tags": tag[:200], "notes": notes})
            position_id = int(conn.execute(text("SELECT MAX(PositionId) FROM portfolio.Position WHERE AccountId = :aid AND StrategyName = :s"),
                                           {"aid": account_id, "s": slug}).fetchone()[0])
        if position_id is None:
            raise ValueError(f"{kind} without a position id")
        n_legs = int(conn.execute(text("SELECT COUNT(*) FROM portfolio.Leg WHERE PositionId = :p"), {"p": position_id}).fetchone()[0])
        tgid = f"{underlying[:4]}-{slug[:8].upper()}-{position_id}"
        src = "Paper" if opening else {"stop": "Stop", "flatten": "Time", "settle": "Settle"}.get(fill["reason"], "Close")
        page_notes = (("" if opening else "CLOSE ") + notes)[:500]
        for i, ((cp, K, sign, leg_px), sym) in enumerate(zip(legs, symbols)):
            bought = (int(sign) > 0) == long_side            # this leg is bought by THIS position when opening
            action = ("BTO" if bought else "STO") if opening else ("STC" if bought else "BTC")
            conn.execute(text("""
                INSERT INTO portfolio.Leg (PositionId, Symbol, OptionSymbol, InstrumentType, Action, Contracts, Strike, Expiration,
                                           ContractType, FillPrice, Commission, FillDate, LegOrder)
                VALUES (:p, :u, :os, 'option', :a, :n, :k, :e, :cp, :fp, :c, :d, :lo)"""),
                {"p": position_id, "u": underlying[:10], "os": str(sym)[:30], "a": action, "n": lots, "k": float(K), "e": expiry,
                 "cp": str(cp)[0].upper(), "fp": float(leg_px), "c": (L.COMMISSION_PER_LEG * lots if opening else 0.0), "d": day,
                 "lo": min(255, n_legs + i + 1)})
            psid = L._page_security_id(conn, str(sym), underlying, str(cp)[0].upper(), float(K), expiry)
            buy = bought if opening else (not bought)
            conn.execute(text("""
                INSERT INTO portfolio.[Transaction] (AccountId, SecurityId, PositionId, TransactionDate, Action, Quantity, Price, Amount,
                                                     Commission, StrategyName, Notes, BusinessDate, TradeGroupId, Direction, TransactionPrice,
                                                     LegType, Source)
                VALUES (:aid, :sid, :p, :d, :a, :q, :px, :amt, :c, :s, :n, :d, :tg, :dir, :px, :lt, :src)"""),
                {"aid": account_id, "sid": psid, "p": position_id, "d": day, "a": ("BUY" if buy else "SELL"), "q": lots, "px": float(leg_px),
                 "amt": (float(fill["cash"]) if i == 0 else 0.0), "c": (L.COMMISSION_PER_LEG * lots if opening else 0.0), "s": slug,
                 "n": page_notes, "tg": tgid, "dir": ("Buy" if buy else "Sell"), "lt": ("LongLeg" if bought else "ShortLeg"), "src": src})
        if kind == "close":
            cash_pnl = conn.execute(text("SELECT SUM(Amount) FROM portfolio.[Transaction] WHERE PositionId = :p"), {"p": position_id}).fetchone()[0]
            conn.execute(text("""UPDATE portfolio.Position SET Status = :st, CloseDate = :d, AvgExitPrice = :px, RealizedPnL = :pnl,
                                 UpdatedAt = SYSUTCDATETIME() WHERE PositionId = :p"""),
                         {"st": ("expired" if fill["reason"] == "settle" else "closed"), "d": day, "px": px,
                          "pnl": (float(cash_pnl) if cash_pnl is not None else 0.0), "p": position_id})
    return position_id


def _hedge_security_id(conn, symbol: str, underlying: str) -> int:
    row = conn.execute(text("SELECT SecurityId FROM portfolio.Security WHERE Symbol = :s AND SecurityType = :t"),
                       {"s": symbol[:40], "t": SYNTHETIC_FUTURE_TYPE}).fetchone()
    if row:
        return int(row[0])
    conn.execute(text("INSERT INTO portfolio.Security (Symbol, Underlying, SecurityType, OptionType, Strike, Expiration, Multiplier) "
                      "VALUES (:s, :u, :t, NULL, NULL, NULL, :m)"),
                 {"s": symbol[:40], "u": underlying[:10], "t": SYNTHETIC_FUTURE_TYPE, "m": HEDGE_MULTIPLIER})
    return int(conn.execute(text("SELECT SecurityId FROM portfolio.Security WHERE Symbol = :s AND SecurityType = :t"),
                            {"s": symbol[:40], "t": SYNTHETIC_FUTURE_TYPE}).fetchone()[0])


def record_synthetic_hedge(engine, account_id: int, slug: str, underlying: str, day: date, fill: dict,
                           position_id: Optional[int] = None, extra: Optional[dict] = None) -> Optional[int]:
    """Write one SYNTHETIC hedge trade (``kind`` hedge: ``direction`` buy | sell | flat, ``units`` NQ-equivalents,
    ``px`` the index level paid, ``cash`` the cash it moved, ``hedge_units`` the book after it, ``final`` for the
    row that closes the book). The first trade of the day opens the Position (returned); later ones adjust it;
    ``final`` closes it with RealizedPnL = the cash every row moved."""
    if fill.get("kind") != "hedge":
        return position_id
    units = abs(float(fill.get("units", fill.get("lots", 0)) or 0.0))
    px = float(fill["px"])
    after = float(fill.get("hedge_units", 0.0) or 0.0)
    final = bool(fill.get("final"))
    direction = str(fill.get("direction", "flat"))
    symbol = str(fill.get("symbol") or HEDGE_SYMBOL)
    fee = float(fill.get("fee", 0.0) or 0.0)
    notes = json.dumps({"synthetic": True, "hedge": "NQ-equivalent priced at the NDX index level (never a real order)", "units": units,
                        "px": px, "book_after": after, "reason": fill["reason"], "minute": fill["m"], "ndx": fill.get("ndx"),
                        "delta": fill.get("delta"), "iv": fill.get("iv"), "hedge_pnl": fill.get("hedge_pnl"), "fee": fee,
                        **(extra or {})}, default=str)[:480]
    with engine.begin() as conn:
        sid = _hedge_security_id(conn, symbol, underlying)
        if position_id is None:
            if units == 0.0 and final:                                   # a flat book that never traded: nothing to book
                return None
            conn.execute(text("""
                INSERT INTO portfolio.Position (AccountId, SecurityId, PositionType, Direction, Quantity, OpenDate, Status,
                                                AvgEntryPrice, Commission, StrategyName, Source, Tags, Notes)
                VALUES (:aid, :sid, 'equity', :dir, :qty, :d, 'open', :px, :comm, :strat, 'paper', :tags, :notes)"""),
                {"aid": account_id, "sid": sid, "dir": ("long" if after > 0 or (after == 0 and direction == "buy") else "short"),
                 "qty": abs(after), "d": day, "px": px, "comm": fee, "strat": slug,
                 "tags": f"{underlying} SYNTHETIC future hedge {symbol} x{HEDGE_MULTIPLIER} {day}"[:200], "notes": _no_close_word(notes)})
            position_id = int(conn.execute(text("SELECT MAX(PositionId) FROM portfolio.Position WHERE AccountId = :aid AND StrategyName = :s"),
                                           {"aid": account_id, "s": slug}).fetchone()[0])
        tgid = f"{underlying[:4]}-{slug[:8].upper()}-{position_id}"
        page_notes = (("CLOSE " + notes) if final else _no_close_word(notes))[:500]
        if units > 0.0 or final:
            conn.execute(text("""
                INSERT INTO portfolio.[Transaction] (AccountId, SecurityId, PositionId, TransactionDate, Action, Quantity, Price, Amount,
                                                     Commission, StrategyName, Notes, BusinessDate, TradeGroupId, Direction, TransactionPrice,
                                                     LegType, Source)
                VALUES (:aid, :sid, :p, :d, :a, :q, :px, :amt, :c, :s, :n, :d, :tg, :dir, :px, 'Hedge', :src)"""),
                {"aid": account_id, "sid": sid, "p": position_id, "d": day, "a": ("SELL" if direction == "sell" else "BUY"), "q": units,
                 "px": px, "amt": float(fill["cash"]), "c": fee, "s": slug, "n": page_notes, "tg": tgid,
                 "dir": ("Sell" if direction == "sell" else "Buy"), "src": ("Settle" if final else "Paper")})
        row = conn.execute(text("SELECT Commission FROM portfolio.Position WHERE PositionId = :p"), {"p": position_id}).fetchone()
        comm = float(row[0]) if row and row[0] is not None else 0.0
        if final:
            cash_pnl = conn.execute(text("SELECT SUM(Amount) FROM portfolio.[Transaction] WHERE PositionId = :p"), {"p": position_id}).fetchone()[0]
            conn.execute(text("""UPDATE portfolio.Position SET Status = 'closed', CloseDate = :d, AvgExitPrice = :px, RealizedPnL = :pnl,
                                 Quantity = 0, Commission = :c, UpdatedAt = SYSUTCDATETIME() WHERE PositionId = :p"""),
                         {"d": day, "px": px, "pnl": (float(cash_pnl) if cash_pnl is not None else 0.0), "c": comm + fee, "p": position_id})
        else:
            conn.execute(text("""UPDATE portfolio.Position SET Quantity = :q, Direction = :dir, AvgEntryPrice = :px, Commission = :c,
                                 UpdatedAt = SYSUTCDATETIME() WHERE PositionId = :p"""),
                         {"q": abs(after), "dir": ("long" if after >= 0 else "short"), "px": float(fill.get("hedge_avg", px) or px),
                          "c": comm + fee, "p": position_id})
    return position_id
