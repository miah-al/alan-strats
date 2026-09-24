"""
api/services/orders.py — paper orders: preview, place, work, cancel, close.

An order is ``{"account": "paper", "underlying", "legs": [{"type": call|put|stock, "strike", "expiry",
"side": buy|sell, "quantity"}], "order_type": limit|market, "limit_price", "tif", "strategy", "label",
"client_order_id"}``. ``limit_price`` is the net price per unit — the legs' quantities divided by their
greatest common divisor — positive for a debit, negative for a credit. ``account: live`` is refused:
live trading is not armed, and nothing here talks to a broker's order API.

Fills are paper fills against the market-data hub's current quotes, each leg at its mid: a market
order fills at once; a limit order fills when it is marketable at mid (net mid <= limit price, in the
debit-positive convention) and otherwise works — the hub re-checks it on every quote for its legs and
every 15 s, and a ``day`` order still working at the close is cancelled. A fill becomes one trade group
in the paper ledger the Paper views and the runner use (``engine.positions.insert_paper_legs``; a close
is ``insert_closing_transactions``), each row booking its own cash in Amount, commission included, so
the group's P&L is the cash it moved. The order itself — as sent, status, fills, the trade group it
made — is kept in ``app.PaperOrder``; ``client_order_id`` makes placing idempotent.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd

from api.marketdata import symbols as SYM
from api.serialize import table_from_rows, to_jsonable
from api.services.db import require_db

logger = logging.getLogger("alan_trader.api.orders")

NY = "America/New_York"
MAX_LEGS = 8
MAX_QUANTITY = 1000
COMMISSION_PER_LEG = 1.00                 # the platform's paper commission (engine.positions._COMMISSION)
RECHECK_S = 15.0
WORKING, FILLED, REJECTED, CANCELLED = "working", "filled", "rejected", "cancelled"


class OrderError(ValueError):
    """The order cannot be accepted as sent (422)."""


class LiveNotArmed(PermissionError):
    """An order for the live account (403)."""


class UnknownOrder(KeyError):
    pass


class OrderConflict(RuntimeError):
    """The request conflicts with the order's or position's state (409)."""


# ── the order ─────────────────────────────────────────────────────────────────

@dataclass
class Leg:
    type: str                    # call | put | stock
    side: str                    # buy | sell
    quantity: int
    strike: Optional[float] = None
    expiry: Optional[_dt.date] = None
    symbol: str = ""
    ledger_symbol: str = ""      # the ledger's own spelling (closing an existing group)

    @property
    def is_option(self) -> bool:
        return self.type in ("call", "put")

    def to_dict(self) -> dict:
        return {"type": self.type, "side": self.side, "quantity": self.quantity, "strike": self.strike,
                "expiry": self.expiry.isoformat() if self.expiry else None, "symbol": self.symbol}


@dataclass
class Order:
    underlying: str
    legs: list[Leg]
    order_type: str
    limit_price: Optional[float]
    tif: str
    strategy: str
    label: str
    client_order_id: Optional[str]
    closes: Optional[str] = None             # the trade group this order closes
    units: int = 1
    ratios: list[int] = field(default_factory=list)


def _gcd(values: list[int]) -> int:
    g = 0
    for v in values:
        g = math.gcd(g, int(v))
    return max(g, 1)


def parse_order(body: dict) -> Order:
    """Validate an order request; raises LiveNotArmed / OrderError."""
    if not isinstance(body, dict):
        raise OrderError("an order is a JSON object")
    account = str(body.get("account") or "paper").strip().lower()
    if account == "live":
        raise LiveNotArmed("live trading is not armed")
    if account != "paper":
        raise OrderError(f"account must be 'paper' (or 'live', which is refused), not {account!r}")
    try:
        und = SYM.normalize(body.get("underlying") or "")
    except ValueError as exc:
        raise OrderError(f"underlying: {exc}")
    if SYM.is_option(und):
        raise OrderError("underlying must be a stock, ETF or index, not an option")
    raw_legs = body.get("legs") or []
    if not isinstance(raw_legs, list) or not raw_legs:
        raise OrderError("legs: at least one leg")
    if len(raw_legs) > MAX_LEGS:
        raise OrderError(f"legs: at most {MAX_LEGS}")
    today = _dt.date.today()
    legs: list[Leg] = []
    for i, r in enumerate(raw_legs):
        if not isinstance(r, dict):
            raise OrderError(f"legs[{i}]: an object")
        typ = str(r.get("type") or "").strip().lower()
        side = str(r.get("side") or "").strip().lower()
        if typ not in ("call", "put", "stock"):
            raise OrderError(f"legs[{i}].type must be call, put or stock")
        if side not in ("buy", "sell"):
            raise OrderError(f"legs[{i}].side must be buy or sell")
        try:
            qty = int(r.get("quantity"))
            if qty != float(r.get("quantity")):
                raise ValueError
        except (TypeError, ValueError):
            raise OrderError(f"legs[{i}].quantity must be a whole number")
        if not 1 <= qty <= MAX_QUANTITY:
            raise OrderError(f"legs[{i}].quantity must be between 1 and {MAX_QUANTITY}")
        leg = Leg(type=typ, side=side, quantity=qty)
        if typ == "stock":
            leg.symbol = und
        else:
            try:
                leg.strike = float(r.get("strike"))
            except (TypeError, ValueError):
                raise OrderError(f"legs[{i}].strike must be a number")
            if not leg.strike > 0:
                raise OrderError(f"legs[{i}].strike must be positive")
            try:
                leg.expiry = _dt.date.fromisoformat(str(r.get("expiry"))[:10])
            except ValueError:
                raise OrderError(f"legs[{i}].expiry must be an ISO date (YYYY-MM-DD)")
            if leg.expiry < today:
                raise OrderError(f"legs[{i}].expiry {leg.expiry} has passed")
            if r.get("symbol"):                       # an explicit OCC symbol (e.g. SPXW) wins
                opt = SYM.parse_option(str(r["symbol"]))
                if opt is None or opt.expiry != leg.expiry or abs(opt.strike - leg.strike) > 1e-6 \
                        or opt.type != typ or opt.underlying != und:
                    raise OrderError(f"legs[{i}].symbol {r['symbol']!r} does not match the leg")
                leg.symbol = opt.occ
            else:
                leg.symbol = SYM.make_option(und, leg.expiry, typ, leg.strike).occ
        legs.append(leg)
    if len({(l.symbol) for l in legs}) != len(legs):
        raise OrderError("legs: the same contract appears twice")
    otype = str(body.get("order_type") or "limit").strip().lower()
    if otype not in ("limit", "market"):
        raise OrderError("order_type must be limit or market")
    limit = body.get("limit_price")
    if otype == "limit":
        try:
            limit = float(limit)
        except (TypeError, ValueError):
            raise OrderError("limit_price: a number is required for a limit order (net per unit, + debit / - credit)")
        if not math.isfinite(limit):
            raise OrderError("limit_price must be finite")
    else:
        limit = None
    tif = str(body.get("tif") or "day").strip().lower()
    if tif not in ("day", "gtc"):
        raise OrderError("tif must be day or gtc")
    strategy = str(body.get("strategy") or "manual").strip()[:50] or "manual"
    coid = body.get("client_order_id")
    coid = str(coid).strip()[:64] if coid not in (None, "") else None
    units = _gcd([l.quantity for l in legs])
    return Order(underlying=und, legs=legs, order_type=otype, limit_price=limit, tif=tif, strategy=strategy,
                 label=str(body.get("label") or "")[:200], client_order_id=coid, units=units,
                 ratios=[l.quantity // units for l in legs])


# ── pricing ───────────────────────────────────────────────────────────────────

def _leg_price(q: dict) -> Optional[float]:
    if q.get("mid") is not None:
        return float(q["mid"])
    return None


def quote_legs(hub, order: Order, wait: float = 3.0) -> list[dict]:
    syms = [l.symbol for l in order.legs]
    got = {q["symbol"]: q for q in hub.snapshot(syms, wait=wait)} if hub is not None else {}
    out = []
    for l in order.legs:
        q = got.get(l.symbol) or {}
        mid = _leg_price(q)
        if mid is None and not l.is_option and q.get("last") is not None:
            mid = float(q["last"])                       # a stock quoted without bid/ask: its last trade
        out.append({"symbol": l.symbol, "side": l.side, "quantity": l.quantity, "bid": q.get("bid"),
                    "ask": q.get("ask"), "mid": mid, "last": q.get("last"), "source": q.get("source")})
    return out


def _signed(side: str) -> float:
    return 1.0 if side == "buy" else -1.0


def net_price(order: Order, quotes: list[dict]) -> Optional[float]:
    """Net mid per unit, debit positive; None when any leg has no price."""
    total = 0.0
    for l, r, q in zip(order.legs, order.ratios, quotes):
        if q.get("mid") is None:
            return None
        total += _signed(l.side) * r * float(q["mid"])
    return round(total, 4)


def _mult(l: Leg) -> float:
    return 100.0 if l.is_option else 1.0


def _payoff_frame(order: Order, quotes: list[dict]) -> pd.DataFrame:
    """The order's legs in the ledger's shape, for paper.views' expiry-payoff arithmetic."""
    rows = []
    for l, q in zip(order.legs, quotes):
        rows.append({"SecurityType": "Option" if l.is_option else "Stock", "Direction": l.side.upper(),
                     "Quantity": float(l.quantity), "Multiplier": _mult(l), "Strike": l.strike,
                     "OptionType": (l.type.upper() if l.is_option else None),
                     "TransactionPrice": float(q.get("mid") or 0.0)})
    return pd.DataFrame(rows)


def economics(order: Order, quotes: list[dict], spot: Optional[float]) -> dict:
    from paper.views import _expiry_payoff_pnl, position_risk
    grp = _payoff_frame(order, quotes)
    strikes = sorted({float(l.strike) for l in order.legs if l.is_option})
    ref = spot or (strikes[len(strikes) // 2] if strikes else None) or 1.0
    far = max([ref] + strikes) * 3.0
    pts = sorted({0.0, *strikes, ref, far})
    vals = [_expiry_payoff_pnl(grp, S) for S in pts]
    beyond = _expiry_payoff_pnl(grp, far * 2.0)
    unbounded_up = beyond > vals[-1] + 1e-6
    max_profit = None if unbounded_up else max(vals)
    risk = position_risk(grp)
    max_loss = -risk if risk is not None else None       # negative dollars (None = unbounded)
    breakevens = []
    for (s0, v0), (s1, v1) in zip(zip(pts, vals), zip(pts[1:], vals[1:])):
        if v0 == 0 and s0 not in breakevens and s0 > 0:
            breakevens.append(round(s0, 4))
        elif (v0 < 0 < v1) or (v0 > 0 > v1):
            breakevens.append(round(s0 + (s1 - s0) * (-v0) / (v1 - v0), 4))
    return {"max_profit": round(max_profit, 2) if max_profit is not None else None,
            "max_loss": round(max_loss, 2) if max_loss is not None else None,
            "breakevens": breakevens}


def buying_power(order: Order, quotes: list[dict], spot: Optional[float], econ: dict) -> tuple[float, list[str]]:
    """Defined risk: the worst loss at expiry. Undefined: a Reg-T style estimate per short leg
    (20% of the underlying less the out-of-the-money amount, at least 10%, plus the premium; 50% of
    a short stock position)."""
    notes = []
    if econ["max_loss"] is not None:
        return abs(econ["max_loss"]), notes
    s = float(spot or 0.0)
    bp = 0.0
    for l, q in zip(order.legs, quotes):
        if l.side != "sell":
            continue
        if not l.is_option:
            bp += 0.5 * s * l.quantity
            continue
        otm = max(0.0, (l.strike - s) if l.type == "call" else (s - l.strike))
        prem = float(q.get("mid") or 0.0)
        bp += (max(0.20 * s - otm, 0.10 * s) + prem) * 100.0 * l.quantity
    notes.append("undefined risk: buying power is a Reg-T style estimate")
    return round(bp, 2), notes


def market_open_now() -> bool:
    now = pd.Timestamp.now(tz=NY)
    if now.weekday() >= 5:
        return False
    return _dt.time(9, 30) <= now.time() < _dt.time(16, 0)


def preview(hub, body: dict) -> dict:
    order = parse_order(body)
    quotes = quote_legs(hub, order)
    spot = hub.price(order.underlying, wait=2.0) if hub is not None else None
    warnings: list[str] = []
    missing = [q["symbol"] for q in quotes if q.get("mid") is None]
    if missing:
        warnings.append("no two-sided quote for " + ", ".join(missing))
    for q in quotes:
        b, a, m = q.get("bid"), q.get("ask"), q.get("mid")
        if b is not None and a is not None and m and (a - b) > max(0.10, 0.25 * m):
            warnings.append(f"{q['symbol']}: wide market {b:.2f} / {a:.2f}")
    exps = {l.expiry for l in order.legs if l.is_option}
    if len(exps) > 1:
        warnings.append("legs expire on different dates: profit / loss figures are at the first expiry with the "
                        "later legs at intrinsic value, so they understate a calendar's value")
    if any(e == _dt.date.today() for e in exps):
        warnings.append("expires today")
    if not market_open_now():
        warnings.append("market closed: a paper fill now uses the last quotes")
    net = net_price(order, quotes)
    econ = economics(order, quotes, spot) if net is not None else {"max_profit": None, "max_loss": None, "breakevens": []}
    if net is not None and order.limit_price is not None:
        gap = order.limit_price - net
        if gap < 0:
            warnings.append(f"limit {order.limit_price:+.2f} is not marketable at mid {net:+.2f}: the order will work")
        elif abs(net) > 0 and gap > 0.2 * abs(net) + 0.05:
            warnings.append(f"limit {order.limit_price:+.2f} is well through mid {net:+.2f}: paper fills at mid")
    bp, bp_notes = buying_power(order, quotes, spot, econ) if net is not None else (None, [])
    warnings += bp_notes
    mult = max((_mult(l) for l in order.legs), default=1.0)
    return to_jsonable({
        "ok": net is not None, "underlying": order.underlying, "spot": spot, "legs": quotes,
        "net_mid": net, "debit_credit": (None if net is None else ("debit" if net > 0 else "credit")),
        "max_profit": econ["max_profit"], "max_loss": econ["max_loss"], "breakevens": econ["breakevens"],
        "buying_power_effect": bp, "warnings": warnings,
        "units": order.units, "ratios": order.ratios,
        "net_total": (round(net * order.units * mult, 2) if net is not None else None),
        "order_type": order.order_type, "limit_price": order.limit_price,
    })


# ── the order book ────────────────────────────────────────────────────────────

_COLS = ["OrderId", "AccountId", "ClientOrderId", "Underlying", "Strategy", "Label", "OrderType", "LimitPrice",
         "Tif", "Status", "LegsJson", "FillsJson", "FillPrice", "TradeGroupId", "ClosesTradeGroupId", "Message",
         "TradeDate", "CreatedAt", "UpdatedAt", "FilledAt"]


def _iso_utc(v) -> Optional[str]:
    if v is None:
        return None
    ts = pd.Timestamp(v)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(NY).isoformat()


def _row_to_order(r) -> dict:
    d = dict(zip(_COLS, r))
    legs = json.loads(d["LegsJson"] or "[]")
    fills = json.loads(d["FillsJson"] or "[]")
    return {"order_id": d["OrderId"], "account_id": d["AccountId"], "client_order_id": d["ClientOrderId"],
            "underlying": d["Underlying"], "strategy": d["Strategy"], "label": d["Label"],
            "order_type": d["OrderType"],
            "limit_price": float(d["LimitPrice"]) if d["LimitPrice"] is not None else None,
            "tif": d["Tif"], "status": d["Status"], "legs": legs, "fills": fills,
            "fill_price": float(d["FillPrice"]) if d["FillPrice"] is not None else None,
            "trade_group_id": d["TradeGroupId"], "closes_trade_group_id": d["ClosesTradeGroupId"],
            "message": d["Message"] or "", "trade_date": d["TradeDate"],
            "created": _iso_utc(d["CreatedAt"]), "updated": _iso_utc(d["UpdatedAt"]), "filled": _iso_utc(d["FilledAt"])}


def result_of(o: dict) -> dict:
    """The contract's order result."""
    return to_jsonable({"order_id": o["order_id"], "status": o["status"], "fills": o["fills"],
                        "trade_group_id": o["trade_group_id"], "message": o["message"],
                        "client_order_id": o["client_order_id"], "fill_price": o["fill_price"],
                        "closes_trade_group_id": o["closes_trade_group_id"], "order": o})


class OrderBook:
    """Paper orders for one account (``account_id()`` is read per call, so a test can point it at
    its own account)."""

    def __init__(self, hub, account_id: Callable[[], int], publish: Optional[Callable[[dict], None]] = None):
        self.hub = hub
        self.account_id = account_id
        self.publish = publish
        self._lock = threading.RLock()
        self._working: dict[int, tuple[Order, dict]] = {}
        self._dirty: set[str] = set()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._eval_lock = threading.RLock()          # one evaluation / cancel at a time: no fill after a cancel
        self._thread: Optional[threading.Thread] = None
        self.loaded = False

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self.hub is not None:
            self.hub.listeners.append(self.on_quote)
        self._thread = threading.Thread(target=self._run, name="paper-orders", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self.hub is not None:
            try:
                self.hub.listeners.remove(self.on_quote)
            except ValueError:
                pass

    def _load_working(self) -> None:
        """Working orders survive a restart: re-read them and watch their legs again."""
        from sqlalchemy import text
        try:
            with require_db().connect() as c:
                # read only: the table is created by the first order, not by a service start
                if c.execute(text("SELECT OBJECT_ID('app.PaperOrder', 'U')")).scalar() is None:
                    self.loaded = True
                    return
                rows = c.execute(text(f"SELECT {', '.join(_COLS)} FROM app.PaperOrder WHERE AccountId = :aid "
                                      f"AND Status = 'working'"), {"aid": self.account_id()}).fetchall()
        except Exception as exc:
            logger.warning("working paper orders not loaded: %s", exc)
            return
        for r in rows:
            o = _row_to_order(r)
            try:
                order = self._order_from_stored(o)
            except Exception as exc:
                logger.warning("paper order %s unreadable: %s", o["order_id"], exc)
                continue
            self._track(order, o)
        self.loaded = True

    @staticmethod
    def _order_from_stored(o: dict) -> Order:
        legs = []
        for l in o["legs"]:
            legs.append(Leg(type=l["type"], side=l["side"], quantity=int(l["quantity"]), strike=l.get("strike"),
                            expiry=_dt.date.fromisoformat(l["expiry"]) if l.get("expiry") else None,
                            symbol=l["symbol"], ledger_symbol=l.get("ledger_symbol") or ""))
        units = _gcd([l.quantity for l in legs])
        return Order(underlying=o["underlying"], legs=legs, order_type=o["order_type"], limit_price=o["limit_price"],
                     tif=o["tif"], strategy=o["strategy"], label=o["label"] or "",
                     client_order_id=o["client_order_id"], closes=o["closes_trade_group_id"], units=units,
                     ratios=[l.quantity // units for l in legs])

    def _track(self, order: Order, o: dict) -> None:
        with self._lock:
            self._working[o["order_id"]] = (order, o)
        if self.hub is not None:
            self.hub.watch(f"order:{o['order_id']}", [l.symbol for l in order.legs])

    def _untrack(self, order_id: int) -> None:
        with self._lock:
            got = self._working.pop(order_id, None)
        if got is not None and self.hub is not None:
            self.hub.unwatch_all(f"order:{order_id}")

    # ── storage ───────────────────────────────────────────────────────────────
    def _get(self, order_id: int) -> Optional[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("PaperOrder"):
            return None
        with require_db().connect() as c:
            r = c.execute(text(f"SELECT {', '.join(_COLS)} FROM app.PaperOrder WHERE OrderId = :id AND AccountId = :aid"),
                          {"id": int(order_id), "aid": self.account_id()}).fetchone()
        return _row_to_order(r) if r is not None else None

    def _by_client_id(self, coid: str) -> Optional[dict]:
        from sqlalchemy import text
        with require_db().connect() as c:
            r = c.execute(text(f"SELECT {', '.join(_COLS)} FROM app.PaperOrder WHERE AccountId = :aid AND ClientOrderId = :c"),
                          {"aid": self.account_id(), "c": coid}).fetchone()
        return _row_to_order(r) if r is not None else None

    def _insert(self, order: Order, status: str, message: str) -> Optional[int]:
        """New order row; None when the client_order_id is already taken (a concurrent duplicate)."""
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        legs = [dict(l.to_dict(), ledger_symbol=l.ledger_symbol or None) for l in order.legs]
        try:
            with require_db().begin() as c:
                r = c.execute(text("""
                    INSERT INTO app.PaperOrder (AccountId, ClientOrderId, Underlying, Strategy, Label, OrderType,
                        LimitPrice, Tif, Status, LegsJson, ClosesTradeGroupId, Message, TradeDate)
                    OUTPUT INSERTED.OrderId
                    VALUES (:aid, :coid, :und, :strat, :label, :ot, :lp, :tif, :st, :legs, :closes, :msg, :td)"""),
                    {"aid": self.account_id(), "coid": order.client_order_id, "und": order.underlying,
                     "strat": order.strategy, "label": order.label, "ot": order.order_type, "lp": order.limit_price,
                     "tif": order.tif, "st": status, "legs": json.dumps(legs), "closes": order.closes,
                     "msg": message[:400], "td": _trade_date()}).fetchone()
            return int(r[0])
        except IntegrityError:
            return None

    def _update(self, order_id: int, **cols) -> None:
        from sqlalchemy import text
        sets = ", ".join(f"{k} = :{k}" for k in cols)
        params = {"id": int(order_id), "aid": self.account_id(), **cols}
        with require_db().begin() as c:
            c.execute(text(f"UPDATE app.PaperOrder SET {sets}, UpdatedAt = SYSUTCDATETIME() "
                           f"WHERE OrderId = :id AND AccountId = :aid"), params)

    def _emit(self, o: dict) -> None:
        if self.publish is not None and o is not None:
            try:
                self.publish({"type": "order", "order": to_jsonable(o)})
            except Exception:
                logger.debug("order event publish failed", exc_info=True)

    # ── placing ───────────────────────────────────────────────────────────────
    def place(self, body: dict) -> dict:
        order = parse_order(body)
        return self._place(order)

    def _place(self, order: Order) -> dict:
        from api.services import appdb
        appdb.ensure("PaperOrder")
        if order.client_order_id:
            prior = self._by_client_id(order.client_order_id)
            if prior is not None:
                return result_of(prior)
        order_id = self._insert(order, "pending", "received")
        if order_id is None:                                     # lost a race on the same client_order_id
            prior = self._by_client_id(order.client_order_id)
            return result_of(prior)
        try:
            with self._eval_lock:
                o = self._evaluate(order_id, order, first=True)
        except Exception as exc:  # noqa: BLE001 — the order must end in a definite state
            logger.exception("paper order %s failed", order_id)
            self._update(order_id, Status=REJECTED, Message=f"{type(exc).__name__}: {exc}"[:400])
            o = self._get(order_id)
        self._emit(o)
        return result_of(o)

    def _evaluate(self, order_id: int, order: Order, first: bool = False) -> dict:
        """Fill if marketable (market: always, when every leg is priced), else work or reject."""
        quotes = quote_legs(self.hub, order, wait=3.0 if first else 0.0)
        net = net_price(order, quotes)
        missing = [q["symbol"] for q in quotes if q.get("mid") is None]
        if order.order_type == "market":
            if net is None:
                if order.closes and self._all_expired(order):
                    return self._fill(order_id, order, quotes, net)
                self._update(order_id, Status=REJECTED, Message=f"no quote to fill against for {', '.join(missing)}")
                return self._get(order_id)
            return self._fill(order_id, order, quotes, net)
        if net is not None and net <= float(order.limit_price) + 1e-9:
            return self._fill(order_id, order, quotes, net)
        msg = (f"working: net mid {net:+.2f} vs limit {order.limit_price:+.2f}" if net is not None
               else f"working: waiting for quotes on {', '.join(missing)}")
        if first:
            self._update(order_id, Status=WORKING, Message=msg)
            o = self._get(order_id)
            self._track(order, o)
            return o
        return None

    def _all_expired(self, order: Order) -> bool:
        today = _dt.date.today()
        return all(l.is_option and l.expiry is not None and l.expiry < today for l in order.legs)

    def _fill(self, order_id: int, order: Order, quotes: list[dict], net: Optional[float]) -> dict:
        now = _dt.datetime.now().astimezone().isoformat(timespec="seconds")
        fills = [{"symbol": q["symbol"], "side": l.side, "quantity": l.quantity, "price": q.get("mid"), "time": now}
                 for l, q in zip(order.legs, quotes)]
        if order.closes:
            tgid, err = self._write_close(order_id, order, fills)
        else:
            tgid, err = self._write_open(order_id, order, fills)
        if err:
            self._update(order_id, Status=REJECTED, Message=f"ledger write failed: {err}"[:400])
            self._untrack(order_id)
            return self._get(order_id)
        self._update(order_id, Status=FILLED, FillsJson=json.dumps(fills), FillPrice=net, TradeGroupId=tgid,
                     Message=("filled at the quotes' mids" + (f", net {net:+.2f}" if net is not None else "")
                              + ("; stock at its last trade" if any(not l.is_option and q.get("bid") is None
                                                                        for l, q in zip(order.legs, quotes)) else "")
                              + (" (closing)" if order.closes else "")),
                     FilledAt=_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None))
        self._untrack(order_id)
        logger.info("paper order %s filled: %s %s legs=%d net=%s tg=%s", order_id, order.underlying, order.strategy,
                    len(order.legs), net, tgid)
        return self._get(order_id)

    def _write_open(self, order_id: int, order: Order, fills: list[dict]) -> tuple[Optional[str], Optional[str]]:
        from engine.positions import insert_paper_legs
        tgid = f"{order.underlying[:4]}-{order.strategy[:6].upper()}-{uuid.uuid4().hex[:6].upper()}"
        legs = []
        for l, f in zip(order.legs, fills):
            legs.append({"symbol": l.symbol, "security_type": "option" if l.is_option else "stock",
                         "option_type": l.type if l.is_option else None, "strike": l.strike,
                         "expiry": l.expiry.isoformat() if l.expiry else None,
                         "direction": "Buy" if l.side == "buy" else "Sell", "quantity": l.quantity,
                         "price": f["price"], "leg_type": f"{l.side.title()}{l.type.title()}"[:12]})
        # the ledger note must never say "close": the Paper views read it to find closing rows
        err = insert_paper_legs(require_db(), self.account_id(), order.underlying, legs, order.strategy, tgid,
                                source="Order", notes=f"paper order #{order_id} (service)",
                                commission=COMMISSION_PER_LEG, book_amount=True)
        return tgid, err

    def _write_close(self, order_id: int, order: Order, fills: list[dict]) -> tuple[Optional[str], Optional[str]]:
        from engine.positions import insert_closing_transactions, settle_expired_legs
        from api.services import paper as P
        grp = P.open_group(order.closes)
        if grp is None:
            return order.closes, f"trade group {order.closes} is no longer open"
        prices = {}
        for l, f in zip(order.legs, fills):
            prices[l.ledger_symbol or l.symbol] = f["price"]
        today = _dt.date.today()
        expired = grp[pd.to_datetime(grp["Expiration"], errors="coerce").dt.date.apply(
            lambda d: d is not None and not pd.isna(d) and d < today)] if "Expiration" in grp.columns else grp.iloc[0:0]
        live = grp.drop(expired.index)
        if not expired.empty:
            from paper.views import _expired_option_intrinsic
            cache: dict = {}
            settle = {str(r["Symbol"]): (_expired_option_intrinsic(r, None, cache) or 0.0) for _, r in expired.iterrows()}
            err = settle_expired_legs(require_db(), self.account_id(), expired, settle)
            if err:
                return order.closes, err
        if not live.empty:
            err = insert_closing_transactions(
                require_db(), self.account_id(), live, {s: {"price": p} for s, p in prices.items() if p is not None},
                book_amount=True, notes=f"CLOSE of {order.closes} by paper order #{order_id} (service)")
            if err:
                return order.closes, err
        return order.closes, None

    # ── closing a position ────────────────────────────────────────────────────
    def close_position(self, trade_group_id: str, body: dict) -> dict:
        from api.services import paper as P
        from paper.views import managed_by_runner
        owner = managed_by_runner(trade_group_id)
        if owner:
            raise OrderConflict(f"trade group {trade_group_id} is held by a live paper runner ({owner}); "
                                f"only that runner may close it")
        grp = P.open_group(trade_group_id)
        if grp is None:
            if P.known_group(trade_group_id):
                raise OrderConflict(f"trade group {trade_group_id} is already closed")
            raise UnknownOrder(trade_group_id)
        with self._lock:
            pending = [oid for oid, (o, _) in self._working.items() if o.closes == trade_group_id]
        if pending:
            raise OrderConflict(f"a closing order (#{pending[0]}) is already working for {trade_group_id}")
        net: dict[str, dict] = {}
        for _, r in grp.iterrows():
            sym = str(r["Symbol"])
            q = abs(float(r.get("Quantity") or 0)) * (1 if str(r.get("Direction", "")).upper().startswith("B") else -1)
            e = net.setdefault(sym, {"qty": 0.0, "row": r})
            e["qty"] += q
        legs = []
        for sym, e in net.items():
            if abs(e["qty"]) < 1e-9:
                continue
            r = e["row"]
            st = str(r.get("SecurityType") or "").lower()
            typ = "stock" if st == "stock" else ("call" if str(r.get("OptionType") or "").upper().startswith("C") else "put")
            leg = Leg(type=typ, side="sell" if e["qty"] > 0 else "buy", quantity=int(round(abs(e["qty"]))),
                      ledger_symbol=sym)
            if st != "stock":
                leg.strike = float(r.get("Strike"))
                leg.expiry = pd.Timestamp(r.get("Expiration")).date()
                opt = SYM.parse_option(sym)
                leg.symbol = opt.occ if opt else SYM.make_option(str(r.get("Underlying") or ""), leg.expiry, leg.type,
                                                               leg.strike).occ
            else:
                leg.symbol = SYM.normalize(sym)
            legs.append(leg)
        if not legs:
            raise OrderConflict(f"trade group {trade_group_id} nets to nothing")
        und = str(grp["Underlying"].dropna().iloc[0]) if "Underlying" in grp.columns and not grp["Underlying"].dropna().empty \
            else legs[0].symbol
        otype = str((body or {}).get("order_type") or "market").lower()
        if otype not in ("limit", "market"):
            raise OrderError("order_type must be limit or market")
        limit = (body or {}).get("limit_price")
        if otype == "limit":
            try:
                limit = float(limit)
            except (TypeError, ValueError):
                raise OrderError("limit_price: a number is required for a limit order")
        units = _gcd([l.quantity for l in legs])
        strategy = str(grp["StrategyName"].iloc[0])[:50] if "StrategyName" in grp.columns else "manual"
        order = Order(underlying=SYM.normalize(und), legs=legs, order_type=otype,
                      limit_price=limit if otype == "limit" else None, tif=str((body or {}).get("tif") or "day"),
                      strategy=strategy, label=f"close {trade_group_id}",
                      client_order_id=((body or {}).get("client_order_id") or None), closes=trade_group_id,
                      units=units, ratios=[l.quantity // units for l in legs])
        return self._place(order)

    # ── listing / cancelling ──────────────────────────────────────────────────
    def list(self, status: str = "all", limit: int = 500) -> dict:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("PaperOrder"):
            return orders_table([])
        where = "AccountId = :aid"
        if status in (WORKING, FILLED, CANCELLED, REJECTED):
            where += " AND Status = :st"
        with require_db().connect() as c:
            rows = c.execute(text(f"SELECT TOP {int(limit)} {', '.join(_COLS)} FROM app.PaperOrder WHERE {where} "
                                  f"ORDER BY OrderId DESC"), {"aid": self.account_id(), "st": status}).fetchall()
        return orders_table([_row_to_order(r) for r in rows])

    def cancel(self, order_id: int) -> dict:
        with self._eval_lock:
            o = self._get(order_id)
            if o is None:
                raise UnknownOrder(order_id)
            if o["status"] != WORKING:
                raise OrderConflict(f"order {order_id} is {o['status']}, not working")
            self._untrack(int(order_id))
            self._update(int(order_id), Status=CANCELLED, Message="cancelled")
            o = self._get(order_id)
        self._emit(o)
        return result_of(o)

    # ── the working-order loop ────────────────────────────────────────────────
    def on_quote(self, symbol: str, msg: dict) -> None:
        """Hub listener (event loop thread): note the symbol and wake the worker; no work here."""
        with self._lock:
            if not self._working:
                return
            self._dirty.add(symbol)
        self._wake.set()

    def _run(self) -> None:
        self._load_working()
        last_full = 0.0
        while not self._stop.is_set():
            self._wake.wait(timeout=RECHECK_S)
            self._wake.clear()
            if self._stop.is_set():
                break
            time.sleep(0.25)                                    # coalesce a burst of quotes
            with self._lock:
                dirty, self._dirty = self._dirty, set()
                working = dict(self._working)
            full = time.monotonic() - last_full >= RECHECK_S
            if full:
                last_full = time.monotonic()
            for oid, (order, o) in working.items():
                if not full and not any(l.symbol in dirty for l in order.legs):
                    continue
                try:
                    with self._eval_lock:
                        with self._lock:
                            if oid not in self._working:          # cancelled meanwhile
                                continue
                        if self._expired_day_order(o):
                            self._untrack(oid)
                            self._update(oid, Status=CANCELLED, Message="day order not filled by the close: cancelled")
                            self._emit(self._get(oid))
                            continue
                        done = self._evaluate(oid, order)
                    if done is not None:
                        self._emit(done)
                except Exception:
                    logger.exception("working paper order %s re-check failed", oid)

    @staticmethod
    def _expired_day_order(o: dict) -> bool:
        if o.get("tif") != "day":
            return False
        now = pd.Timestamp.now(tz=NY)
        td = o.get("trade_date")
        td = _dt.date.fromisoformat(str(td)[:10]) if td else now.date()
        return now.date() > td or (now.date() == td and now.time() >= _dt.time(16, 0))

    def working_count(self) -> int:
        with self._lock:
            return len(self._working)


def _trade_date() -> _dt.date:
    """The session an order belongs to: after the close, the next weekday's."""
    now = pd.Timestamp.now(tz=NY)
    d = now.date()
    if now.time() >= _dt.time(16, 0) or now.weekday() >= 5:
        d += _dt.timedelta(days=1)
        while d.weekday() >= 5:
            d += _dt.timedelta(days=1)
    return d


_TABLE_FIELDS = ["order_id", "client_order_id", "created", "status", "underlying", "strategy", "label", "order_type",
                 "limit_price", "fill_price", "tif", "legs", "trade_group_id", "closes_trade_group_id", "message",
                 "filled", "updated"]
_TABLE_HEADERS = {"order_id": "Order", "client_order_id": "Client Id", "created": "Created", "status": "Status",
                  "underlying": "Underlying", "strategy": "Strategy", "label": "Label", "order_type": "Type",
                  "limit_price": "Limit", "fill_price": "Fill", "tif": "TIF", "legs": "Legs",
                  "trade_group_id": "Trade Group", "closes_trade_group_id": "Closes", "message": "Message",
                  "filled": "Filled", "updated": "Updated"}
_TABLE_TYPES = {"order_id": "integer", "created": "datetime", "filled": "datetime", "updated": "datetime",
                "limit_price": "number", "fill_price": "number"}


def _legs_text(legs: list[dict]) -> str:
    parts = []
    for l in legs:
        if l.get("type") == "stock":
            parts.append(f"{l['side']} {l['quantity']} {l.get('symbol')}")
        else:
            parts.append(f"{l['side']} {l['quantity']} {l.get('expiry')} {l.get('strike'):g}{str(l.get('type'))[:1].upper()}")
    return "; ".join(parts)


def orders_table(orders: list[dict]) -> dict:
    rows = [{**{k: o.get(k) for k in _TABLE_FIELDS if k != "legs"}, "legs": _legs_text(o.get("legs") or [])}
            for o in orders]
    return table_from_rows(rows, field_order=_TABLE_FIELDS, headers=_TABLE_HEADERS, types=_TABLE_TYPES,
                           formats={"limit_price": "price", "fill_price": "price"})
