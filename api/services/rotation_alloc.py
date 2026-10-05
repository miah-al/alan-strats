"""
api/services/rotation_alloc.py — the sector-rotation paper allocator (sector_rotation; armed weekdays at 15:50 ET).

The rule is the plugin's (strategies/sector_rotation/strategy.py: ``picks``, ``target_shares``): the 3 sector SPDRs
with the best 21-day return over 60-day volatility, a third each of a FIXED sleeve (the strategy's ``sleeve``,
$5,000: the owner on 2026-10-05, "cannot put too much money. 20k is all I got across the board"), re-ranked on the
last trading day of each month with the 15:50 prices standing in for the close.

Once per armed day it decides (app.EventDeskLog, playbook ``sector_rotation``, one row a day):
  * the month's last trading day: rank on the stored closes up to yesterday plus today's 15:50 prices, and trade to
    the new picks (a pick that stays is resized only when the difference is worth ``min_trade_frac`` of the sleeve);
  * any other day: the standing picks are the last month-end's (stored closes only). It trades only when the held
    symbols differ from them -- the first run, or a month-end that was missed -- and otherwise holds.
Sales close whole lots held at least one night (the account's ETF rule). Market orders through the service's paper
order book, which fills at the quote's mid; paper only.
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
import sys
import threading
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger("alan_trader.api.rotation_alloc")

NY = "America/New_York"
SLUG = "sector_rotation"
PLAYBOOK = "sector_rotation"            # its row in app.EventDeskLog
LEDGER = "sector_rotation"              # the StrategyName its paper positions carry
HISTORY_DAYS = 160                      # calendar days of stored closes: > 60 returns + 21 days + holidays
MIN_HOLD_NIGHTS = 1


# ── the calendar ──────────────────────────────────────────────────────────────

def trading_day(d: _dt.date) -> bool:
    from api.services.gex_recorder import trading_day as td
    return td(d)


def previous_trading_day(d: _dt.date) -> _dt.date:
    from api.services.gex_recorder import previous_trading_day as ptd
    return ptd(d)


def is_month_end(d: _dt.date) -> bool:
    """Is ``d`` its month's last trading day?"""
    n = d + _dt.timedelta(days=1)
    while not trading_day(n):
        n += _dt.timedelta(days=1)
    return n.month != d.month


def last_month_end_before(d: _dt.date) -> _dt.date:
    """The previous month's last trading day."""
    p = d.replace(day=1) - _dt.timedelta(days=1)
    while not trading_day(p):
        p -= _dt.timedelta(days=1)
    return p


# ── the plan (pure) ──────────────────────────────────────────────────────────

def plan(targets: dict, lots: list[dict], today: _dt.date, prices: dict, sleeve: float, min_frac: float,
         resize: bool, min_nights: int = MIN_HOLD_NIGHTS) -> dict:
    """targets: {symbol: shares}; lots: [{"trade_group_id", "symbol", "shares", "opened"}] of this allocator.
    Returns {"close": [lots], "buy": {symbol: shares}, "notes": [str]}: drop what is no longer picked, buy what is
    newly picked, and (``resize``) bring a kept pick to its target when that moves at least ``min_frac`` x sleeve."""
    held: dict[str, list[dict]] = {}
    for l in lots:
        held.setdefault(str(l["symbol"]).upper(), []).append(l)
    close, buy, notes = [], {}, []

    def closable(ls):
        return sorted((l for l in ls if (today - l["opened"]).days >= min_nights),
                      key=lambda l: (l["opened"], str(l["trade_group_id"])))

    for sym, ls in sorted(held.items()):
        if int(targets.get(sym, 0)) > 0:
            continue
        ok = closable(ls)
        close += ok
        if len(ok) < len(ls):
            notes.append(f"{sym}: {len(ls) - len(ok)} lot(s) opened less than {min_nights} night(s) ago stay "
                         f"(the account's ETF holding rule)")
    for sym, tgt in sorted(targets.items()):
        tgt = int(tgt)
        if tgt <= 0:
            if prices.get(sym) is None:
                notes.append(f"{sym}: no price, not bought")
            continue
        ls = held.get(sym, [])
        cur = int(sum(int(l["shares"]) for l in ls))
        if not ls:
            buy[sym] = tgt
            continue
        diff = tgt - cur
        px = float(prices.get(sym) or 0.0)
        if not resize or diff == 0 or abs(diff) * px < float(min_frac) * float(sleeve):
            continue
        if diff > 0:
            buy[sym] = diff
            continue
        after = cur
        for l in closable(ls):
            if after <= tgt:
                break
            close.append(l)
            after -= int(l["shares"])
        if after > tgt:
            notes.append(f"{sym}: reduce to {tgt} blocked by lots opened less than {min_nights} night(s) ago")
        if after < tgt:
            buy[sym] = tgt - after
    return {"close": close, "buy": buy, "notes": notes}


# ── the live inputs (each replaceable in tests) ──────────────────────────────

class LiveInputs:
    def __init__(self, hub):
        self.hub = hub

    def closes(self, symbols: tuple, until: _dt.date) -> pd.DataFrame:
        """Stored daily closes (mkt.PriceBar, topped up when behind) up to ``until``: rows = dates, columns = symbols."""
        from api.services.db import require_db
        from db.client import get_price_bars
        eng = require_db()
        start = until - _dt.timedelta(days=HISTORY_DAYS)
        cols = {}
        for s in symbols:
            try:
                from api.services.bars_topup import top_up
                top_up(s, until)
            except Exception as exc:  # noqa: BLE001 — the stored bars may still be enough
                logger.info("%s daily bars not topped up: %s", s, exc)
            b = get_price_bars(eng, s, start, until)
            if b is not None and not b.empty:
                cols[s] = pd.Series(pd.to_numeric(b["close"], errors="coerce").values, index=pd.to_datetime(b["date"]))
        df = pd.DataFrame(cols).sort_index()
        return df[df.index <= pd.Timestamp(until)]

    def prices_now(self, symbols: tuple) -> dict:
        """The market-data hub's price per symbol (None where it has none)."""
        out = {}
        for s in symbols:
            px = None
            if self.hub is not None and getattr(self.hub, "providers", None):
                try:
                    px = self.hub.price(s, wait=3.0)
                except Exception as exc:  # noqa: BLE001
                    logger.info("hub %s unavailable: %s", s, exc)
            out[s] = float(px) if px else None
        return out

    def lots(self) -> list[dict]:
        """This allocator's open long ETF lots: [{"trade_group_id", "symbol", "shares", "opened"}]."""
        from api.services import paper as P
        open_groups, _closed, _t = P.load()
        out = []
        for tgid, grp in (open_groups or {}).items():
            if grp.empty or str(grp["StrategyName"].iloc[0]) != LEDGER:
                continue
            g = grp[grp["SecurityType"].astype(str).str.lower() == "stock"]
            if g.empty:
                continue
            q = sum(abs(float(r["Quantity"] or 0)) * (1 if str(r["Direction"]).upper().startswith("B") else -1)
                    for _, r in g.iterrows())
            if round(q) <= 0:
                continue
            out.append({"trade_group_id": str(tgid), "symbol": str(g["Symbol"].iloc[0]).upper(), "shares": int(round(q)),
                        "opened": pd.Timestamp(g["BusinessDate"].min()).date()})
        return out


def strategy():
    """A fresh sector_rotation instance with its default parameters (imported read only from the plugin)."""
    from alan_trader.strategy_api import registry as R
    return R.get_strategy(SLUG)


def _module(s):
    return sys.modules[type(s).__module__]


# ── the allocator ─────────────────────────────────────────────────────────────

class RotationAllocator:
    def __init__(self, store, orders, hub=None, publish: Optional[Callable[[dict], None]] = None, inputs=None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None, strategy_factory: Optional[Callable] = None):
        self.store = store
        self.orders = orders
        self.publish = publish
        self.inputs = inputs or LiveInputs(hub)
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self.strategy_factory = strategy_factory or strategy
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
                logger.exception("sector rotation allocator failed")
                row.update(status="failed", detail={"error": f"{type(exc).__name__}: {exc}"[:400]},
                           summary=f"{PLAYBOOK}: failed — {type(exc).__name__}: {exc}"[:400])
            self.store.add_decision(row)
            self._emit(row)
            return row

    def _decide(self, day: _dt.date) -> dict:
        if not trading_day(day):
            return {"status": "no_session", "summary": f"{PLAYBOOK}: {day} is not a trading day", "detail": {}}
        s = self.strategy_factory()
        mod = _module(s)
        uni = tuple(s.universe)
        month_end = is_month_end(day)
        hist = self.inputs.closes(uni, previous_trading_day(day))
        prices = self.inputs.prices_now(uni)
        if month_end:
            today = pd.DataFrame([{k: v for k, v in prices.items() if v}], index=[pd.Timestamp(day)])
            closes = pd.concat([hist, today]).sort_index()
            basis = f"the {day} ranking at 15:50 (month-end)"
        else:
            me = last_month_end_before(day)
            closes = hist[hist.index <= pd.Timestamp(me)]
            basis = f"the {me} month-end ranking"
        chosen = mod.picks(closes, s.top_k, s.lookback, s.vol_window)
        sc = mod.scores(closes, s.lookback, s.vol_window).sort_values(ascending=False)
        if len(chosen) < s.top_k:
            raise LookupError(f"only {len(chosen)} sector(s) could be ranked from {basis} "
                              f"({len(closes)} rows of closes)")
        targets = mod.target_shares(chosen, prices, s.sleeve)
        lots = self.inputs.lots()
        held = sorted({l["symbol"] for l in lots})
        detail = {"basis": basis, "picks": chosen, "scores": {k: round(float(v), 3) for k, v in sc.dropna().items()},
                  "targets": targets, "prices": prices, "sleeve": s.sleeve, "held": held,
                  "lots": [{**l, "opened": str(l["opened"])} for l in lots], "orders": []}
        if not month_end and set(held) == set(chosen):
            return {"status": "held", "verdict": "hold", "detail": detail,
                    "summary": f"{PLAYBOOK}: holding {', '.join(chosen)} ({basis}); next re-rank on the month's last "
                               f"trading day"}
        p = plan(targets, lots, day, prices, s.sleeve, s.min_trade_frac, resize=month_end)
        detail["plan_notes"] = p["notes"]
        if not p["close"] and not p["buy"]:
            return {"status": "held", "verdict": "month_end" if month_end else "catch_up", "detail": detail,
                    "summary": f"{PLAYBOOK}: {', '.join(chosen)} already held ({basis})"
                               + (f"; {'; '.join(p['notes'])}" if p["notes"] else "")}
        orders = self._execute(day, p)
        detail["orders"] = orders
        bad = [o for o in orders if o.get("status") != "filled"]
        verdict = "month_end" if month_end else ("catch_up" if not held else "repair")
        return {"status": "rebalanced" if not bad else "order_failed", "verdict": verdict, "action": "rebalance",
                "trade_group_id": next((o.get("trade_group_id") for o in orders if o.get("trade_group_id")), None),
                "detail": detail,
                "summary": (f"{PLAYBOOK}: picks {', '.join(chosen)} ({basis}); " + "; ".join(o["text"] for o in orders)
                            + (f"; {'; '.join(p['notes'])}" if p["notes"] else ""))[:400]}

    def _execute(self, day: _dt.date, p: dict) -> list[dict]:
        out = []
        tag = f"rotation-{day.isoformat()}"
        for l in p["close"]:
            try:
                r = self.orders.close_position(l["trade_group_id"], {"order_type": "market",
                                                                     "client_order_id": f"{tag}-close-{l['trade_group_id']}"[:64]})
                out.append({"side": "sell", "symbol": l["symbol"], "quantity": l["shares"],
                            "closes_trade_group_id": l["trade_group_id"], "order_id": r.get("order_id"),
                            "status": r.get("status"), "fill_price": r.get("fill_price"), "message": r.get("message"),
                            "text": f"sold {l['shares']} {l['symbol']} {r.get('status')}"})
            except Exception as exc:  # noqa: BLE001
                out.append({"side": "sell", "symbol": l["symbol"], "quantity": l["shares"],
                            "closes_trade_group_id": l["trade_group_id"], "status": "error",
                            "message": f"{type(exc).__name__}: {exc}"[:300],
                            "text": f"sell of {l['shares']} {l['symbol']} failed: {exc}"})
        for sym, q in sorted(p["buy"].items()):
            body = {"account": "paper", "underlying": sym, "order_type": "market", "tif": "day",
                    "legs": [{"type": "stock", "side": "buy", "quantity": int(q)}], "strategy": LEDGER,
                    "label": f"Sector rotation: {sym}", "client_order_id": f"{tag}-buy-{sym}"[:64]}
            try:
                r = self.orders.place(body)
                out.append({"side": "buy", "symbol": sym, "quantity": int(q), "order_id": r.get("order_id"),
                            "status": r.get("status"), "fill_price": r.get("fill_price"),
                            "trade_group_id": r.get("trade_group_id"), "message": r.get("message"),
                            "text": f"bought {q} {sym} {r.get('status')}"
                                    + (f" @ {r['fill_price']:.2f}" if r.get("fill_price") else "")})
            except Exception as exc:  # noqa: BLE001
                out.append({"side": "buy", "symbol": sym, "quantity": int(q), "status": "error",
                            "message": f"{type(exc).__name__}: {exc}"[:300], "text": f"buy of {q} {sym} failed: {exc}"})
        return out

    def _emit(self, row: dict) -> None:
        from api.serialize import to_jsonable
        logger.info("sector rotation %s: %s", row["date"], row.get("summary"))
        if self.publish is not None:
            try:
                self.publish(to_jsonable({"type": "rotation_alloc", **{k: v for k, v in row.items() if k != "detail"},
                                          "orders": (row.get("detail") or {}).get("orders", [])}))
            except Exception:
                logger.debug("allocator event publish failed", exc_info=True)

    # ── reading ───────────────────────────────────────────────────────────────
    def status(self, variant: str = "") -> dict:
        try:
            lots = self.inputs.lots()
        except Exception as exc:  # noqa: BLE001
            lots = None
            logger.debug("rotation lots unavailable: %s", exc)
        last = None
        if self.store is not None:
            rec = self.store.decisions_since(self.clock().date() - _dt.timedelta(days=40), PLAYBOOK)
            last = rec[0] if rec else None
        return {"strategy": SLUG, "ledger_strategy": LEDGER,
                "holdings": ({l["symbol"]: l["shares"] for l in lots} if lots is not None else None),
                "last_decision": ({k: last.get(k) for k in ("date", "status", "verdict", "summary")} if last else None)}
