"""
api/services/trend_alloc.py — the month-end trend paper allocators (equity_trend, gold_trend; armed weekdays at
15:50 ET). One class serves both by ``slug`` (2026-10-25, gold_trend added: the owner, "Yes, build and arm it"); each
strategy's rule, sleeve and tickers are its plugin's.

The rule is the plugin's (strategies/equity_trend/strategy.py: ``decide``, ``target_shares``): on the month's last
trading day, SPY's 15:50 price against the average of its last 10 month-end closes decides in or out, and the weight is
min(1, 10% / SPY's 21-day volatility); the sleeve (the plugin's ``sleeve``, $8,000) holds that weight in SPYM, the rest
in cash (which the cash sleeve keeps in BOXX). It replaced the sector rotation on 2026-10-11.

Once per armed day it decides (app.EventDeskLog, playbook ``equity_trend``, one row a day):
  * the month's last trading day: decide at the 15:50 price (the stored SPY closes must reach yesterday), and trade to
    the target when the holding is off by at least the plugin's ``band`` (5%) of the sleeve;
  * any other day: the standing target is the last month-end's decision (stored closes only); trade only when the
    holding is off by at least the band -- the first run, or a month-end that was missed -- and otherwise hold.
Reducing closes whole lots (newest first, held at least one night: the account's ETF rule) and buys back what is
left below the target. Market orders through the service's paper order book, which fills at the quote's mid; paper
only. The stored SPY closes are dividend-adjusted while the 15:50 price is not: a ~0.5% bias toward "in" on the trend
test at most, accepted (the study's adjusted-close variant made 8.18%/yr vs 8.38%).
"""
from __future__ import annotations

import datetime as _dt
import logging
import sys
import threading
from typing import Callable, Optional

import pandas as pd

from api.services import rotation_alloc as RA

logger = logging.getLogger("alan_trader.api.trend_alloc")

NY = "America/New_York"
SLUG = PLAYBOOK = LEDGER = "equity_trend"     # the default slug; TrendAllocator(slug=...) serves any trend sleeve
HISTORY_DAYS = 420                      # calendar days of stored closes: 10 month-ends + 21 sessions, with margin
MIN_HOLD_NIGHTS = 1


def trading_day(d: _dt.date) -> bool:
    return RA.trading_day(d)


def previous_trading_day(d: _dt.date) -> _dt.date:
    return RA.previous_trading_day(d)


def is_month_end(d: _dt.date) -> bool:
    return RA.is_month_end(d)


def last_month_end_before(d: _dt.date) -> _dt.date:
    return RA.last_month_end_before(d)


def strategy(slug: str = SLUG):
    """A fresh instance of the trend strategy ``slug`` with its default parameters (from the plugin, read only)."""
    from alan_trader.strategy_api import registry as R
    return R.get_strategy(slug)


def _module(s):
    return sys.modules[type(s).__module__]


class TrendAllocator:
    def __init__(self, store, orders, hub=None, publish: Optional[Callable[[dict], None]] = None, inputs=None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None, strategy_factory: Optional[Callable] = None,
                 slug: str = SLUG):
        self.slug = self.playbook = self.ledger = slug
        self.store = store
        self.orders = orders
        self.publish = publish
        self.inputs = inputs or RA.LiveInputs(hub, ledger=self.ledger, history_days=HISTORY_DAYS)
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self.strategy_factory = strategy_factory or (lambda: strategy(slug))
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
        sig, hold = s.signal, s.holding
        prev = previous_trading_day(day)
        hist = self.inputs.closes((sig,), prev)
        closes = pd.to_numeric(hist[sig], errors="coerce").dropna() if sig in getattr(hist, "columns", []) else pd.Series(dtype=float)
        prices = self.inputs.prices_now((sig, hold))
        lots = self.inputs.lots()
        held = int(sum(int(l["shares"]) for l in lots))
        month_end = is_month_end(day)
        detail = {"signal": sig, "holding": hold, "sleeve": s.sleeve, "band": s.band, "month_end": month_end,
                  "prices": prices, "held_shares": held, "lots": [{**l, "opened": str(l["opened"])} for l in lots],
                  "last_close_date": (str(closes.index[-1].date()) if len(closes) else None), "orders": []}
        if month_end:
            if prices.get(sig) is None:
                return {"status": "no_quote", "verdict": "none", "detail": detail,
                        "summary": f"{self.playbook}: no {sig} price at 15:50 on the month-end; nothing traded"}
            if not len(closes) or closes.index[-1].date() != prev:
                return {"status": "stale_closes", "verdict": "none", "detail": detail,
                        "summary": f"{self.playbook}: the stored {sig} closes end {detail['last_close_date']}, not {prev}; "
                                   f"nothing traded"}
            d = mod.decide(closes, float(prices[sig]), s.sma_months, s.vol_days, s.target_vol, day=pd.Timestamp(day))
            basis = f"the {day} month-end decision at 15:50"
        else:
            me = last_month_end_before(day)
            d = mod.decide(closes[closes.index <= pd.Timestamp(me)], None, s.sma_months, s.vol_days, s.target_vol)
            basis = f"the {me} month-end decision"
        detail.update(decision=d, basis=basis)
        if d.get("w") is None:
            return {"status": "no_history", "verdict": "none", "detail": detail,
                    "summary": f"{self.playbook}: not enough {sig} history for {basis}; nothing traded"}
        px = prices.get(hold)
        if px is None:
            return {"status": "no_quote", "verdict": "none", "detail": detail,
                    "summary": f"{self.playbook}: no {hold} price; nothing traded ({basis}: w {d['w']:.2f})"}
        target = mod.target_shares(d["w"], s.sleeve, float(px))
        detail["target_shares"] = target
        state = "in" if d["in"] else "out"
        head = (f"{self.playbook}: {sig} {d['price']:.2f} vs its {s.sma_months}-month average {d['sma']:.2f} -> "
                f"{state}, sigma {d['sigma'] * 100:.1f}% -> w {d['w']:.2f} ({basis}); target {target} {hold}, "
                f"held {held}")
        if abs(target - held) * float(px) < float(s.band) * float(s.sleeve):
            return {"status": "held", "verdict": "hold", "detail": detail, "summary": head[:400]}
        orders = self._trade(day, hold, lots, held, target, s)
        detail["orders"] = orders
        bad = [o for o in orders if o.get("status") != "filled"]
        return {"status": "rebalanced" if not bad else "order_failed", "verdict": "month_end" if month_end else "catch_up",
                "action": "rebalance",
                "trade_group_id": next((o.get("trade_group_id") for o in orders if o.get("trade_group_id")), None),
                "detail": detail, "summary": (head + "; " + "; ".join(o["text"] for o in orders))[:400]}

    def _trade(self, day: _dt.date, hold: str, lots: list[dict], held: int, target: int, s=None) -> list[dict]:
        out, after = [], held
        tag = f"{self.slug}-{day.isoformat()}"
        if target < held:                       # close whole lots, newest first, then buy back below the target
            for l in sorted((l for l in lots if (day - l["opened"]).days >= MIN_HOLD_NIGHTS),
                            key=lambda l: (l["opened"], str(l["trade_group_id"])), reverse=True):
                if after <= target:
                    break
                try:
                    r = self.orders.close_position(l["trade_group_id"], {
                        "order_type": "market", "client_order_id": f"{tag}-close-{l['trade_group_id']}"[:64]})
                    out.append({"side": "sell", "symbol": hold, "quantity": l["shares"], "status": r.get("status"),
                                "closes_trade_group_id": l["trade_group_id"], "fill_price": r.get("fill_price"),
                                "text": f"sold {l['shares']} {hold} {r.get('status')}"})
                    if r.get("status") == "filled":
                        after -= int(l["shares"])
                except Exception as exc:  # noqa: BLE001
                    out.append({"side": "sell", "symbol": hold, "quantity": l["shares"], "status": "error",
                                "message": f"{type(exc).__name__}: {exc}"[:300], "text": f"sell of {l['shares']} {hold} failed"})
        buy = target - after
        if buy > 0:
            body = {"account": "paper", "underlying": hold, "order_type": "market", "tif": "day",
                    "legs": [{"type": "stock", "side": "buy", "quantity": int(buy)}], "strategy": self.ledger,
                    "label": f"{getattr(s, 'display_name', self.slug)}: {hold}", "client_order_id": f"{tag}-buy-{hold}"[:64]}
            try:
                r = self.orders.place(body)
                out.append({"side": "buy", "symbol": hold, "quantity": int(buy), "order_id": r.get("order_id"),
                            "status": r.get("status"), "fill_price": r.get("fill_price"),
                            "trade_group_id": r.get("trade_group_id"),
                            "text": f"bought {buy} {hold} {r.get('status')}"
                                    + (f" @ {r['fill_price']:.2f}" if r.get("fill_price") else "")})
            except Exception as exc:  # noqa: BLE001
                out.append({"side": "buy", "symbol": hold, "quantity": int(buy), "status": "error",
                            "message": f"{type(exc).__name__}: {exc}"[:300], "text": f"buy of {buy} {hold} failed: {exc}"})
        return out

    def _emit(self, row: dict) -> None:
        from api.serialize import to_jsonable
        logger.info("%s %s: %s", self.slug, row["date"], row.get("summary"))
        if self.publish is not None:
            try:
                self.publish(to_jsonable({"type": "trend_alloc", **{k: v for k, v in row.items() if k != "detail"},
                                          "orders": (row.get("detail") or {}).get("orders", [])}))
            except Exception:
                logger.debug("allocator event publish failed", exc_info=True)

    def status(self, variant: str = "") -> dict:
        try:
            lots = self.inputs.lots()
        except Exception as exc:  # noqa: BLE001
            lots = None
            logger.debug("trend lots unavailable: %s", exc)
        last = None
        if self.store is not None:
            rec = self.store.decisions_since(self.clock().date() - _dt.timedelta(days=40), self.playbook)
            last = rec[0] if rec else None
        return {"strategy": self.slug, "ledger_strategy": self.ledger,
                "holdings": ({l["symbol"]: l["shares"] for l in lots} if lots is not None else None),
                "last_decision": ({k: last.get(k) for k in ("date", "status", "verdict", "summary")} if last else None)}
