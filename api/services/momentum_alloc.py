"""
api/services/momentum_alloc.py — the shock-momentum paper allocators, one instance per plugin: btc_momentum (IBIT,
$4,000) and sol_momentum (BSOL, $1,500), each armed weekdays at 15:50 ET.

The rule is the plugin's (strategies/btc_momentum/strategy.py: ``shock_z``, ``entry_signal``, ``target_shares``,
``exit_due``): on an IBIT up day of at least ``k`` sigma (the sd of its 20 prior daily log returns), buy ``notional``
dollars of IBIT at 15:50 and sell them ``hold`` sessions later at 15:50. Long only, one position at a time, and the day
that closes a position opens nothing (as the backtest trades).

Once per armed day it decides (app.EventDeskLog, playbook ``btc_momentum``, one row a day):
  * exits first: every open lot held ``hold`` sessions or more is sold (market);
  * then, with nothing open and nothing sold today: today's 15:50 price against the stored closes up to yesterday.
    The stored closes must reach yesterday's session, else nothing is bought (a stale close would mis-measure the
    move). At z >= k it buys floor(notional / price) shares (market).
Paper only: market orders through the service's paper order book, which fills at the quote's mid.
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
import sys
import threading
from typing import Callable, Optional

import pandas as pd

from api.services import sleeve_common as RA

logger = logging.getLogger("alan_trader.api.momentum_alloc")

NY = "America/New_York"
SLUG = "btc_momentum"
PLAYBOOK = "btc_momentum"              # its row in app.EventDeskLog
LEDGER = "btc_momentum"                # the StrategyName its paper positions carry


def trading_day(d: _dt.date) -> bool:
    return RA.trading_day(d)


def previous_trading_day(d: _dt.date) -> _dt.date:
    return RA.previous_trading_day(d)


def sessions_held(opened: _dt.date, today: _dt.date) -> int:
    """Trading sessions after ``opened`` up to and including ``today`` (0 on the entry day)."""
    n, d = 0, opened
    while d < today:
        d += _dt.timedelta(days=1)
        if trading_day(d):
            n += 1
    return n


def strategy(slug: str = SLUG):
    """A fresh instance of the momentum plugin ``slug`` with its default parameters (from the plugin, read only)."""
    from alan_trader.strategy_api import registry as R
    return R.get_strategy(slug)


def _module(s):
    return sys.modules[type(s).__module__]


class MomentumAllocator:
    def __init__(self, store, orders, hub=None, publish: Optional[Callable[[dict], None]] = None, inputs=None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None, strategy_factory: Optional[Callable] = None,
                 slug: str = SLUG):
        # one instance per momentum plugin: btc_momentum (IBIT) and, from 2026-10-11, sol_momentum (BSOL); each has its
        # own decision rows (playbook = slug) and its own paper positions (StrategyName = slug)
        self.slug = self.playbook = self.ledger = str(slug)
        self.store = store
        self.orders = orders
        self.publish = publish
        self.inputs = inputs or RA.LiveInputs(hub, ledger=self.ledger)
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self.strategy_factory = strategy_factory or (lambda: strategy(self.slug))
        self._lock = threading.Lock()

    def run(self, variant: str = "", now: Optional[pd.Timestamp] = None) -> dict:
        if self.store is None:
            raise RuntimeError("the decision store is off (ALAN_TRADER_ARMS=off)")
        now = now or self.clock()
        day = now.date()
        with self._lock:
            prior = self.store.decided(self.playbook, day)
            if prior is not None:
                return {"playbook": self.playbook, "date": day, "status": "already_decided",
                        "summary": f"{self.playbook}: already decided today ({prior['status']})", "prior": prior}
            row = {"playbook": self.playbook, "date": day, "ledger_strategy": self.ledger, "action": None, "trade_group_id": None,
                   "verdict": None}
            try:
                row.update(self._decide(day))
            except Exception as exc:  # noqa: BLE001 — a failed decision is logged, never half-done silently
                logger.exception("%s allocator failed", self.slug)
                row.update(status="failed", detail={"error": f"{type(exc).__name__}: {exc}"[:400]},
                           summary=f"{self.playbook}: failed — {type(exc).__name__}: {exc}"[:400])
            self.store.add_decision(row)
            self._emit(row)
            return row

    def _decide(self, day: _dt.date) -> dict:
        if not trading_day(day):
            return {"status": "no_session", "summary": f"{self.playbook}: {day} is not a trading day", "detail": {}}
        s = self.strategy_factory()
        mod = _module(s)
        sym = s.symbol
        lots = self.inputs.lots()
        held = [{**l, "opened": str(l["opened"]), "sessions": sessions_held(l["opened"], day)} for l in lots]
        detail = {"symbol": sym, "k": s.k, "hold": s.hold, "window": s.window, "notional": s.notional,
                  "lots": held, "orders": []}
        due = [l for l in lots if mod.exit_due(sessions_held(l["opened"], day), s.hold)]
        if due:
            orders = self._close(day, due)
            detail["orders"] = orders
            bad = [o for o in orders if o.get("status") != "filled"]
            return {"status": "closed" if not bad else "order_failed", "verdict": "exit", "action": "close",
                    "detail": detail,
                    "summary": (f"{self.playbook}: {s.hold} sessions held; " + "; ".join(o["text"] for o in orders))[:400]}
        if lots:
            n = max(h["sessions"] for h in held)
            return {"status": "held", "verdict": "hold", "detail": detail,
                    "summary": f"{self.playbook}: holding {sum(int(l['shares']) for l in lots)} {sym}, {n} of {s.hold} "
                               f"sessions"}
        prev = previous_trading_day(day)
        hist = self.inputs.closes((sym,), prev)
        closes = pd.to_numeric(hist[sym], errors="coerce").dropna() if sym in getattr(hist, "columns", []) else pd.Series(dtype=float)
        price = self.inputs.prices_now((sym,)).get(sym)
        detail.update(price=price, last_close_date=(str(closes.index[-1].date()) if len(closes) else None),
                      prev_session=str(prev))
        if price is None:
            return {"status": "no_quote", "verdict": "none", "detail": detail,
                    "summary": f"{self.playbook}: no {sym} price at 15:50; nothing bought"}
        if not len(closes) or closes.index[-1].date() != prev:
            return {"status": "stale_closes", "verdict": "none", "detail": detail,
                    "summary": f"{self.playbook}: the stored {sym} closes end {detail['last_close_date']}, not {prev}; "
                               f"nothing bought"}
        z, move, sigma = mod.shock_z(list(closes.values), float(price), s.window)
        detail.update(z=None if not math.isfinite(z) else round(z, 3), move=move, sigma=sigma,
                      prev_close=float(closes.iloc[-1]))
        if not mod.entry_signal(z, s.k):
            zt = f"{z:+.2f}" if math.isfinite(z) else "n/a"
            return {"status": "no_signal", "verdict": "none", "detail": detail,
                    "summary": f"{self.playbook}: {sym} {move * 100:+.2f}% = {zt} sigma (needs +{s.k:g}); nothing bought"}
        q = mod.target_shares(float(price), s.notional)
        if q <= 0:
            return {"status": "no_quote", "verdict": "none", "detail": detail,
                    "summary": f"{self.playbook}: {sym} at {price} buys no whole share of ${s.notional:,.0f}"}
        orders = self._buy(day, sym, q, z)
        detail["orders"] = orders
        o = orders[0]
        return {"status": "opened" if o.get("status") == "filled" else "order_failed", "verdict": "entry",
                "action": "open", "trade_group_id": o.get("trade_group_id"), "detail": detail,
                "summary": f"{self.playbook}: {sym} {move * 100:+.2f}% = {z:+.2f} sigma; {o['text']}; out in {s.hold} sessions"}

    def _buy(self, day: _dt.date, sym: str, q: int, z: float) -> list[dict]:
        body = {"account": "paper", "underlying": sym, "order_type": "market", "tif": "day",
                "legs": [{"type": "stock", "side": "buy", "quantity": int(q)}], "strategy": self.ledger,
                "label": f"{self.slug}: {sym} after a {z:+.2f} sigma day",
                "client_order_id": f"{self.slug}-{day.isoformat()}-buy-{sym}"[:64]}
        try:
            r = self.orders.place(body)
            return [{"side": "buy", "symbol": sym, "quantity": int(q), "order_id": r.get("order_id"),
                     "status": r.get("status"), "fill_price": r.get("fill_price"),
                     "trade_group_id": r.get("trade_group_id"), "message": r.get("message"),
                     "text": f"bought {q} {sym} {r.get('status')}"
                             + (f" @ {r['fill_price']:.2f}" if r.get("fill_price") else "")}]
        except Exception as exc:  # noqa: BLE001
            return [{"side": "buy", "symbol": sym, "quantity": int(q), "status": "error",
                     "message": f"{type(exc).__name__}: {exc}"[:300], "text": f"buy of {q} {sym} failed: {exc}"}]

    def _close(self, day: _dt.date, lots: list[dict]) -> list[dict]:
        out = []
        for l in lots:
            try:
                r = self.orders.close_position(l["trade_group_id"], {
                    "order_type": "market", "client_order_id": f"{self.slug}-{day.isoformat()}-close-{l['trade_group_id']}"[:64]})
                out.append({"side": "sell", "symbol": l["symbol"], "quantity": l["shares"],
                            "closes_trade_group_id": l["trade_group_id"], "order_id": r.get("order_id"),
                            "status": r.get("status"), "fill_price": r.get("fill_price"), "message": r.get("message"),
                            "text": f"sold {l['shares']} {l['symbol']} {r.get('status')}"
                                    + (f" @ {r['fill_price']:.2f}" if r.get("fill_price") else "")})
            except Exception as exc:  # noqa: BLE001
                out.append({"side": "sell", "symbol": l["symbol"], "quantity": l["shares"],
                            "closes_trade_group_id": l["trade_group_id"], "status": "error",
                            "message": f"{type(exc).__name__}: {exc}"[:300],
                            "text": f"sell of {l['shares']} {l['symbol']} failed: {exc}"})
        return out

    def _emit(self, row: dict) -> None:
        from api.serialize import to_jsonable
        logger.info("%s %s: %s", self.slug, row["date"], row.get("summary"))
        if self.publish is not None:
            try:
                self.publish(to_jsonable({"type": "momentum_alloc", **{k: v for k, v in row.items() if k != "detail"},
                                          "orders": (row.get("detail") or {}).get("orders", [])}))
            except Exception:
                logger.debug("allocator event publish failed", exc_info=True)

    # ── reading ───────────────────────────────────────────────────────────────
    def status(self, variant: str = "") -> dict:
        try:
            lots = self.inputs.lots()
        except Exception as exc:  # noqa: BLE001
            lots = None
            logger.debug("momentum lots unavailable: %s", exc)
        last = None
        if self.store is not None:
            rec = self.store.decisions_since(self.clock().date() - _dt.timedelta(days=30), self.playbook)
            last = rec[0] if rec else None
        return {"strategy": self.slug, "ledger_strategy": self.ledger,
                "holdings": ({l["symbol"]: l["shares"] for l in lots} if lots is not None else None),
                "last_decision": ({k: last.get(k) for k in ("date", "status", "verdict", "summary")} if last else None)}
