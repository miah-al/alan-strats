"""
api/services/event_alloc.py — the event desk's paper allocators (EXPERIMENTAL; never armed by default).

  oil_fade   at 15:45 ET on an armed day: when the crude playbook says ``fade`` and nothing is open, one USO
             put vertical (long ~ATM, short ~6% lower, 3–6 weeks out) at a limit of net mid + slippage through
             the paper order book; ``add`` (a de-escalation after the entry) adds one more spread, once.
             Exits, never before one night: crude back at its 20-day mean, 10 sessions, the spread worth
             ≤ 50% of its debit, or two sessions to expiry. One position (campaign) at a time.
  btc_dip    at 09:31 ET: when the BTC playbook fired, ~$5k of IBIT shares (or one IBIT call vertical) with
             a market order; out (no minimum hold: a crypto ETP counts as crypto, 0 nights) after 3 sessions, at −4% of the entry, or when BTC is
             back at the pre-shock close.

Both decide once per trading day (app.EventDeskLog is unique on playbook + day; client order ids carry the
day), log every decision — trade or not — and trade the paper account only (the order book refuses anything
else). The paper order engine fills at the quotes' mids: with no quote the decision is ``no_quote``.
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
from typing import Callable, Optional

import pandas as pd

from api.services import event_desk as ED

logger = logging.getLogger("alan_trader.api.event_alloc")

NY = "America/New_York"


# ── the exit rules (pure) ─────────────────────────────────────────────────────

def nights_ok(opened: Optional[str], today: _dt.date, min_nights: int) -> bool:
    if not opened:
        return False
    return (today - _dt.date.fromisoformat(str(opened)[:10])).days >= int(min_nights)


def oil_exit_reason(trade: dict, crude_last: Optional[float], crude_mean20: Optional[float], today: _dt.date,
                    params: dict) -> Optional[str]:
    """Why an open oil_fade spread should be closed today, or None. The hold-night rule comes first."""
    if not nights_ok(trade.get("opened"), today, params["min_nights"]):
        return None
    if crude_last is not None and crude_mean20 is not None and crude_last <= crude_mean20:
        return f"target: crude {crude_last:.2f} is back at its 20-day mean {crude_mean20:.2f}"
    held = trade.get("days_held")
    if held is None and trade.get("opened"):
        held = ED.sessions_between(_dt.date.fromisoformat(str(trade["opened"])[:10]), today)
    if held is not None and held >= params["max_sessions"]:
        return f"time: {held} sessions held (max {params['max_sessions']})"
    entry, mark = trade.get("entry"), trade.get("mark")
    if entry and mark is not None and mark <= entry * (1 - params["stop_pct"]):
        return f"stop: spread {mark:.2f} is {(1 - mark / entry) * 100:.0f}% under the {entry:.2f} debit"
    exp = trade.get("expiry")
    if exp and ED.sessions_between(today, _dt.date.fromisoformat(str(exp)[:10])) <= 2:
        return f"expiry: {exp} is within two sessions"
    return None


def btc_exit_reason(trade: dict, btc_last: Optional[float], pre_shock: Optional[float], today: _dt.date,
                    params: dict) -> Optional[str]:
    if not nights_ok(trade.get("opened"), today, params["min_nights"]):
        return None
    if btc_last is not None and pre_shock and btc_last >= pre_shock:
        return f"target: BTC {btc_last:,.0f} is back at the pre-shock {pre_shock:,.0f}"
    entry, mark = trade.get("entry"), trade.get("mark")
    if entry and mark is not None and mark <= entry * (1 - params["stop_pct"]):
        return f"stop: {mark:.2f} is {(1 - mark / entry) * 100:.1f}% under the {entry:.2f} entry"
    held = trade.get("days_held")
    if held is None and trade.get("opened"):
        held = ED.sessions_between(_dt.date.fromisoformat(str(trade["opened"])[:10]), today)
    if held is not None and held >= params["max_sessions"]:
        return f"time: {held} sessions held (max {params['max_sessions']})"
    return None


# ── the allocators ────────────────────────────────────────────────────────────

class EventAllocator:
    playbook = ""
    title = ""
    experimental = True

    def __init__(self, desk: ED.EventDesk, orders, hub=None, publish: Optional[Callable[[dict], None]] = None,
                 store=None, clock: Optional[Callable[[], pd.Timestamp]] = None, params: Optional[dict] = None):
        self.desk = desk
        self.orders = orders
        self.hub = hub
        self.publish = publish
        self.store = store if store is not None else desk.store
        self.clock = clock or desk.clock
        self.params = dict(self.default_params(), **(params or {}))
        self._lock = threading.Lock()

    def default_params(self) -> dict:
        return {}

    @property
    def ledger(self) -> str:
        return ED.LEDGER[self.playbook]

    # ── one day's decision ───────────────────────────────────────────────────
    def run(self, variant: str = "", now: Optional[pd.Timestamp] = None) -> dict:
        if self.store is None:
            raise RuntimeError("the event desk's store is off (ALAN_TRADER_ARMS=off)")
        now = now or self.clock()
        day = now.date()
        with self._lock:
            prior = self.store.decided(self.playbook, day)
            if prior is not None:
                return {"playbook": self.playbook, "date": day, "status": "already_decided",
                        "summary": f"{self.playbook}: already decided today ({prior['status']})", "prior": prior}
            row = {"playbook": self.playbook, "date": day, "ledger_strategy": self.ledger, "action": None,
                   "trade_group_id": None, "verdict": None}
            try:
                ctx = self.desk.context()
                pb = self.desk.playbook(self.playbook, ctx)
                row["verdict"] = pb["verdict"]
                mine = [t for t in ctx["trades"] if t.get("playbook") == self.playbook]
                detail = {"verdict": pb["verdict"], "headline": pb["headline"], "reasons": pb["reasons"],
                          "checklist": pb["checklist"], "open_trades": mine, "params": self.params, "orders": [],
                          "playbook_detail": pb.get("detail") or {}}
                exits = self._exits(mine, ctx, pb)
                if exits:
                    orders = [self._close(t, why, day) for t, why in exits]
                    detail["orders"] = orders
                    bad = [o for o in orders if o.get("status") != "filled"]
                    row.update(status="closed" if not bad else "order_failed", action="exit",
                               trade_group_id=exits[0][0].get("trade_group_id"),
                               summary=f"{self.playbook}: " + "; ".join(o["text"] for o in orders))
                else:
                    body, action, why = self._entry(pb, ctx, mine)
                    if body is None:
                        row.update(status="held" if mine else "no_trade", action=None,
                                   summary=f"{self.playbook}: {why}")
                    elif body == "no_quote":
                        row.update(status="no_quote", action=action, summary=f"{self.playbook}: {why}")
                    else:
                        o = self._place(body, action, day)
                        detail["orders"] = [o]
                        row.update(status=("opened" if action == "open" else "added") if o.get("status") == "filled"
                                   else "order_failed", action=action, trade_group_id=o.get("trade_group_id"),
                                   summary=f"{self.playbook}: {why}; {o['text']}")
                    detail["why"] = why
                row["detail"] = detail
            except Exception as exc:  # noqa: BLE001 — a failed decision is logged, never half-done silently
                logger.exception("%s allocator failed", self.playbook)
                row.update(status="failed", detail={"error": f"{type(exc).__name__}: {exc}"[:400]},
                           summary=f"{self.playbook}: failed — {type(exc).__name__}: {exc}"[:400])
            self.store.add_decision(row)
            self._emit(row)
            return row

    # ── orders ───────────────────────────────────────────────────────────────
    def _tag(self, day: _dt.date) -> str:
        return f"event-{self.playbook}-{day.isoformat()}"

    def _place(self, body: dict, action: str, day: _dt.date) -> dict:
        body = dict(body, account="paper", strategy=self.ledger, client_order_id=f"{self._tag(day)}-{action}"[:64],
                    label=(body.get("label") or f"event desk {self.playbook} {action}")[:200])
        try:
            r = self.orders.place(body)
            px = r.get("fill_price")
            return {"side": "open" if action == "open" else "add", "order_id": r.get("order_id"), "status": r.get("status"),
                    "fill_price": px, "trade_group_id": r.get("trade_group_id"), "message": r.get("message"),
                    "limit_price": body.get("limit_price"), "legs": body.get("legs"),
                    "text": f"{action} {r.get('status')}" + (f" @ {px:+.2f}" if px is not None else "")}
        except Exception as exc:  # noqa: BLE001
            return {"side": action, "status": "error", "message": f"{type(exc).__name__}: {exc}"[:300],
                    "legs": body.get("legs"), "text": f"{action} failed: {exc}"[:300]}

    def _close(self, trade: dict, why: str, day: _dt.date) -> dict:
        tgid = trade.get("trade_group_id")
        try:
            r = self.orders.close_position(tgid, {"order_type": "market",
                                                  "client_order_id": f"{self._tag(day)}-close-{tgid}"[:64]})
            return {"side": "close", "closes_trade_group_id": tgid, "order_id": r.get("order_id"), "status": r.get("status"),
                    "fill_price": r.get("fill_price"), "message": r.get("message"), "reason": why,
                    "text": f"closed {tgid} ({why}) {r.get('status')}"}
        except Exception as exc:  # noqa: BLE001
            return {"side": "close", "closes_trade_group_id": tgid, "status": "error", "reason": why,
                    "message": f"{type(exc).__name__}: {exc}"[:300], "text": f"close of {tgid} failed: {exc}"[:300]}

    def _emit(self, row: dict) -> None:
        from api.serialize import to_jsonable
        logger.info("event allocator %s %s: %s", self.playbook, row["date"], row.get("summary"))
        if self.publish is not None:
            try:
                self.publish(to_jsonable({"type": "event_alloc", **{k: v for k, v in row.items() if k != "detail"},
                                          "orders": (row.get("detail") or {}).get("orders", [])}))
            except Exception:
                logger.debug("allocator event publish failed", exc_info=True)

    # ── to implement ─────────────────────────────────────────────────────────
    def _exits(self, mine: list[dict], ctx: dict, pb: dict) -> list[tuple[dict, str]]:
        raise NotImplementedError

    def _entry(self, pb: dict, ctx: dict, mine: list[dict]):
        """(order body | None | "no_quote", action, why)."""
        raise NotImplementedError

    # ── reading ──────────────────────────────────────────────────────────────
    def status(self, variant: str = "") -> dict:
        try:
            mine = [t for t in self.desk.trades() if t.get("playbook") == self.playbook]
        except Exception as exc:  # noqa: BLE001
            mine = None
            logger.debug("event trades unavailable: %s", exc)
        last = None
        if self.store is not None:
            rec = self.store.decisions_since(self.clock().date() - _dt.timedelta(days=14), self.playbook)
            last = rec[0] if rec else None
        return {"playbook": self.playbook, "ledger_strategy": self.ledger, "experimental": self.experimental,
                "open_trades": mine, "params": self.params,
                "last_decision": ({k: last.get(k) for k in ("date", "status", "verdict", "action", "trade_group_id", "summary")}
                                  if last else None)}

    def log(self, days: int = 30) -> dict:
        return {"playbook": self.playbook, "days": int(days), "decisions": self.desk.decisions(days, self.playbook)}


class OilFadeAllocator(EventAllocator):
    playbook = "oil_fade"
    title = "USO put vertical on a threat-only crude spike"

    def default_params(self) -> dict:
        return dict(ED.OIL_PARAMS)

    def _exits(self, mine, ctx, pb):
        cl = ctx["signals"]["CL"]
        today = ctx["now"].date()
        out = []
        for t in mine:
            why = oil_exit_reason(t, cl.get("last"), cl.get("mean20"), today, self.params)
            if why:
                out.append((t, why))
        return out

    def _entry(self, pb, ctx, mine):
        v = pb["verdict"]
        if v == "fade" and not mine:
            action = "open"
        elif v == "add" and mine and len(mine) <= self.params["max_adds"]:
            action = "add"
        else:
            why = pb["headline"]
            if mine:
                why = f"holding {len(mine)} spread(s): " + (pb["reasons"][0] if pb["reasons"] else "no exit rule hit")
            return None, None, why
        t = pb.get("trade")
        if not t or not t.get("order_legs"):
            return "no_quote", action, f"{v}: no USO chain to build the spread from"
        if t.get("est_debit") is None:
            return "no_quote", action, f"{v}: no two-sided quotes for {t['legs']}"
        limit = round(float(t["est_debit"]) + float(self.params["slippage"]), 2)
        body = {"underlying": "USO", "order_type": "limit", "limit_price": limit, "tif": "day",
                "legs": [{k: l[k] for k in ("type", "side", "strike", "expiry", "quantity")} for l in t["order_legs"]],
                "label": f"event desk oil_fade {action}: {t['legs']}"}
        return body, action, f"{v}: {t['legs']} at {limit:.2f} (mid {t['est_debit']:.2f} + {self.params['slippage']:.2f})"


class BtcDipAllocator(EventAllocator):
    playbook = "btc_dip"
    title = "IBIT at the next NYSE open after a geopolitical BTC dip"

    def default_params(self) -> dict:
        return dict(ED.BTC_PARAMS)

    def _pre_shock(self, pb: dict) -> Optional[float]:
        """The pre-shock close the open position was entered against (stored with the entry decision)."""
        if self.store is None:
            return None
        for r in self.store.decisions_since(self.clock().date() - _dt.timedelta(days=30), self.playbook):
            if r.get("status") == "opened":
                return ((r.get("detail") or {}).get("playbook_detail") or {}).get("pre_shock")
        return (pb.get("detail") or {}).get("pre_shock")

    def _exits(self, mine, ctx, pb):
        btc = ctx["signals"]["BTC"]
        today = ctx["now"].date()
        pre = self._pre_shock(pb)
        out = []
        for t in mine:
            why = btc_exit_reason(t, btc.get("last"), pre, today, self.params)
            if why:
                out.append((t, why))
        return out

    def _entry(self, pb, ctx, mine):
        if pb["verdict"] != "fade" or mine:
            why = pb["headline"] if not mine else f"holding {len(mine)} position(s): no exit rule hit"
            return None, None, why
        t = pb.get("trade")
        if not t or not t.get("order_legs"):
            return "no_quote", "open", "buy: no IBIT price to size against"
        if t.get("structure") == "IBIT shares":
            body = {"underlying": "IBIT", "order_type": "market", "tif": "day", "legs": t["order_legs"],
                    "label": f"event desk btc_dip open: {t['legs']}"}
            why = f"buy {t['quantity']} IBIT (~${self.params['dollars']:,.0f}) at the open"
        else:
            if t.get("est_debit") is None:
                return "no_quote", "open", f"buy: no two-sided quotes for {t['legs']}"
            limit = round(float(t["est_debit"]) + float(self.params["slippage"]), 2)
            body = {"underlying": "IBIT", "order_type": "limit", "limit_price": limit, "tif": "day",
                    "legs": [{k: l[k] for k in ("type", "side", "strike", "expiry", "quantity")} for l in t["order_legs"]],
                    "label": f"event desk btc_dip open: {t['legs']}"}
            why = f"buy {t['legs']} at {limit:.2f}"
        return body, "open", why
