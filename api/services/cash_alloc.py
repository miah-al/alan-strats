"""
api/services/cash_alloc.py — the cash sleeve: idle paper cash earns the T-bill rate (cash_sleeve; armed weekdays at 15:55 ET).

The paper account sits mostly in cash. Once a day, after the 15:50 allocators have traded, this sweep keeps ``RESERVE``
dollars of cash for the strategies and holds the rest in BOXX, a 1-3 month T-bill-like ETF that pays no distributions
(its price rises at about the T-bill rate: +4.06% over the year to 2026-10-09, worst dip -0.11%). A distributing
T-bill ETF (SGOV, BIL) would not work here: the paper ledger books no dividends, so their yield would never show.
2026-10-09, the owner: "Yes" to putting idle cash in T-bills.

Once per armed day it decides (app.EventDeskLog, playbook ``cash_sleeve``, one row a day):
  * surplus: cash above RESERVE + MIN_TRADE -> buy whole BOXX shares worth (cash - RESERVE);
  * shortfall: cash below RESERVE - MIN_TRADE -> sell whole BOXX lots (newest first, held at least one night: the
    account's ETF rule) until the cash is back at the reserve or no lot is left;
  * otherwise hold.
Paper only: market orders through the service's paper order book, which fills at the quote's mid.
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
import threading
from typing import Callable, Optional

import pandas as pd

from api.services import rotation_alloc as RA

logger = logging.getLogger("alan_trader.api.cash_alloc")

NY = "America/New_York"
PLAYBOOK = "cash_sleeve"               # its row in app.EventDeskLog
LEDGER = "cash_sleeve"                 # the StrategyName its paper positions carry
SYMBOL = "BOXX"
RESERVE = 7500.0                       # cash kept for the strategies: btc_momentum $4,000, SPX 13:00 ~$900, the desks
MIN_TRADE = 1000.0                     # no trade for a smaller difference
MIN_HOLD_NIGHTS = 1


def trading_day(d: _dt.date) -> bool:
    return RA.trading_day(d)


def plan(cash: float, lots: list[dict], price: float, today: _dt.date, reserve: float = RESERVE,
         min_trade: float = MIN_TRADE, min_nights: int = MIN_HOLD_NIGHTS) -> dict:
    """{"buy": shares, "close": [lots], "notes": [str]} for this cash and these BOXX lots at ``price``."""
    surplus = float(cash) - float(reserve)
    if surplus >= float(min_trade):
        return {"buy": int(math.floor(surplus / float(price))), "close": [], "notes": []}
    if surplus <= -float(min_trade):
        need, close, notes = -surplus, [], []
        ok = sorted((l for l in lots if (today - l["opened"]).days >= min_nights),
                    key=lambda l: (l["opened"], str(l["trade_group_id"])), reverse=True)
        for l in ok:
            if need <= 0:
                break
            close.append(l)
            need -= int(l["shares"]) * float(price)
        if len(ok) < len(lots):
            notes.append(f"{len(lots) - len(ok)} lot(s) opened less than {min_nights} night(s) ago stay")
        return {"buy": 0, "close": close, "notes": notes}
    return {"buy": 0, "close": [], "notes": []}


class CashSleeveAllocator:
    def __init__(self, store, orders, hub=None, publish: Optional[Callable[[dict], None]] = None, inputs=None,
                 cash_fn: Optional[Callable[[], Optional[float]]] = None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None):
        self.store = store
        self.orders = orders
        self.publish = publish
        self.inputs = inputs or RA.LiveInputs(hub, ledger=LEDGER)
        self.cash_fn = cash_fn or (lambda: _paper_cash(hub))
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self._lock = threading.Lock()

    def run(self, variant: str = "", now: Optional[pd.Timestamp] = None) -> dict:
        if self.store is None:
            raise RuntimeError("the decision store is off (ALAN_TRADER_ARMS=off)")
        now = now or self.clock()
        day = now.date()
        with self._lock:
            prior = self.store.decided(PLAYBOOK, day)
            if prior is not None:
                return {"playbook": PLAYBOOK, "date": day, "status": "already_decided",
                        "summary": f"{PLAYBOOK}: already decided today ({prior['status']})", "prior": prior}
            row = {"playbook": PLAYBOOK, "date": day, "ledger_strategy": LEDGER, "action": None, "trade_group_id": None,
                   "verdict": None}
            try:
                row.update(self._decide(day))
            except Exception as exc:  # noqa: BLE001 — a failed decision is logged, never half-done silently
                logger.exception("cash sleeve allocator failed")
                row.update(status="failed", detail={"error": f"{type(exc).__name__}: {exc}"[:400]},
                           summary=f"{PLAYBOOK}: failed — {type(exc).__name__}: {exc}"[:400])
            self.store.add_decision(row)
            self._emit(row)
            return row

    def _decide(self, day: _dt.date) -> dict:
        if not trading_day(day):
            return {"status": "no_session", "summary": f"{PLAYBOOK}: {day} is not a trading day", "detail": {}}
        cash = self.cash_fn()
        price = self.inputs.prices_now((SYMBOL,)).get(SYMBOL)
        lots = self.inputs.lots()
        held = sum(int(l["shares"]) for l in lots)
        detail = {"cash": cash, "reserve": RESERVE, "min_trade": MIN_TRADE, "price": price, "held_shares": held,
                  "lots": [{**l, "opened": str(l["opened"])} for l in lots], "orders": []}
        if cash is None or price is None:
            return {"status": "no_quote", "verdict": "none", "detail": detail,
                    "summary": f"{PLAYBOOK}: no {'cash figure' if cash is None else SYMBOL + ' price'}; nothing traded"}
        p = plan(float(cash), lots, float(price), day)
        detail["plan_notes"] = p["notes"]
        if not p["buy"] and not p["close"]:
            return {"status": "held", "verdict": "hold", "detail": detail,
                    "summary": f"{PLAYBOOK}: cash ${cash:,.0f} vs the ${RESERVE:,.0f} reserve; holding {held} {SYMBOL}"
                               + (f"; {'; '.join(p['notes'])}" if p["notes"] else "")}
        orders = self._execute(day, p)
        detail["orders"] = orders
        bad = [o for o in orders if o.get("status") != "filled"]
        return {"status": "swept" if not bad else "order_failed", "verdict": "buy" if p["buy"] else "sell",
                "action": "rebalance",
                "trade_group_id": next((o.get("trade_group_id") for o in orders if o.get("trade_group_id")), None),
                "detail": detail,
                "summary": (f"{PLAYBOOK}: cash ${cash:,.0f} vs the ${RESERVE:,.0f} reserve; "
                            + "; ".join(o["text"] for o in orders)
                            + (f"; {'; '.join(p['notes'])}" if p["notes"] else ""))[:400]}

    def _execute(self, day: _dt.date, p: dict) -> list[dict]:
        out = []
        tag = f"cash-{day.isoformat()}"
        for l in p["close"]:
            try:
                r = self.orders.close_position(l["trade_group_id"], {"order_type": "market",
                                                                     "client_order_id": f"{tag}-close-{l['trade_group_id']}"[:64]})
                out.append({"side": "sell", "symbol": SYMBOL, "quantity": l["shares"], "closes_trade_group_id": l["trade_group_id"],
                            "order_id": r.get("order_id"), "status": r.get("status"), "fill_price": r.get("fill_price"),
                            "message": r.get("message"), "text": f"sold {l['shares']} {SYMBOL} {r.get('status')}"})
            except Exception as exc:  # noqa: BLE001
                out.append({"side": "sell", "symbol": SYMBOL, "quantity": l["shares"], "closes_trade_group_id": l["trade_group_id"],
                            "status": "error", "message": f"{type(exc).__name__}: {exc}"[:300],
                            "text": f"sell of {l['shares']} {SYMBOL} failed: {exc}"})
        if p["buy"] > 0:
            body = {"account": "paper", "underlying": SYMBOL, "order_type": "market", "tif": "day",
                    "legs": [{"type": "stock", "side": "buy", "quantity": int(p["buy"])}], "strategy": LEDGER,
                    "label": f"Cash sleeve: {SYMBOL} (T-bills)", "client_order_id": f"{tag}-buy-{SYMBOL}"[:64]}
            try:
                r = self.orders.place(body)
                out.append({"side": "buy", "symbol": SYMBOL, "quantity": int(p["buy"]), "order_id": r.get("order_id"),
                            "status": r.get("status"), "fill_price": r.get("fill_price"),
                            "trade_group_id": r.get("trade_group_id"), "message": r.get("message"),
                            "text": f"bought {p['buy']} {SYMBOL} {r.get('status')}"
                                    + (f" @ {r['fill_price']:.2f}" if r.get("fill_price") else "")})
            except Exception as exc:  # noqa: BLE001
                out.append({"side": "buy", "symbol": SYMBOL, "quantity": int(p["buy"]), "status": "error",
                            "message": f"{type(exc).__name__}: {exc}"[:300], "text": f"buy of {p['buy']} {SYMBOL} failed: {exc}"})
        return out

    def _emit(self, row: dict) -> None:
        from api.serialize import to_jsonable
        logger.info("cash sleeve %s: %s", row["date"], row.get("summary"))
        if self.publish is not None:
            try:
                self.publish(to_jsonable({"type": "cash_alloc", **{k: v for k, v in row.items() if k != "detail"},
                                          "orders": (row.get("detail") or {}).get("orders", [])}))
            except Exception:
                logger.debug("allocator event publish failed", exc_info=True)

    def status(self, variant: str = "") -> dict:
        try:
            lots = self.inputs.lots()
        except Exception as exc:  # noqa: BLE001
            lots = None
            logger.debug("cash sleeve lots unavailable: %s", exc)
        last = None
        if self.store is not None:
            rec = self.store.decisions_since(self.clock().date() - _dt.timedelta(days=30), PLAYBOOK)
            last = rec[0] if rec else None
        return {"strategy": PLAYBOOK, "ledger_strategy": LEDGER, "reserve": RESERVE,
                "holdings": ({SYMBOL: sum(int(l["shares"]) for l in lots)} if lots is not None else None),
                "last_decision": ({k: last.get(k) for k in ("date", "status", "verdict", "summary")} if last else None)}


def _paper_cash(hub) -> Optional[float]:
    """The paper account's cash (the paper summary's ``cash``), None when unreadable."""
    try:
        from api.services import paper as P
        c = P.summary(hub).get("cash")
        return float(c) if c is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.info("paper cash unavailable: %s", exc)
        return None
