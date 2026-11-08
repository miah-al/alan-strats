"""
api/services/real_account.py — the owner's REAL tastytrade account, READ-ONLY, in the paper API's shapes.

The app's Paper | Real switch reads ``/api/real/*`` (api/routers/real.py) the way it reads ``/api/paper/*``: the
summary, the positions (open and closed), the transactions and the equity line, in the same JSON shapes, so every
view renders both. The numbers come from tastytrade's account endpoints through the platform's own OAuth login
(``TT_SECRET`` / ``TT_REFRESH``, engine.env), on one event-loop thread holding one session for the process.

READ-ONLY BY DESIGN. The only SDK calls here are ``Account.get``, ``get_balances``, ``get_positions``, ``get_history``
and ``get_net_liquidating_value_history``. Nothing places, replaces or cancels an order; tests/test_real_account.py
scans this file for the order methods, and live orders stay refused in api/services/orders.py.

Every REST call is counted by the platform's broker budget (ServiceBrokerBudget: the day cap shared with the streamer
and the runners), at a 1 s floor between this client's calls so a cold read stays inside the app's 10 s timeout.
Reads are cached: balances and positions 60 s in market hours (10 min outside), transactions 5 min, the net-liq
history 30 min.

Conventions (the paper ledger's): ``entry_net`` is the cash the opening legs moved (credit positive), ``market_value``
is the signed value of the open legs (a short leg is negative), so ``pnl = entry_net + market_value``.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import os
import re
import threading
import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Callable, Optional

import pandas as pd

from api.serialize import column, series, table_from_rows, to_jsonable

logger = logging.getLogger("alan_trader.api.real")

TTL_LIVE_S = 60.0          # balances + positions, 09:25-16:15 ET on weekdays
TTL_QUIET_S = 600.0        # the same outside market hours
TTL_HISTORY_S = 300.0      # the transaction history
TTL_NLV_S = 1800.0         # the net-liq history
HISTORY_DAYS = 400         # how far back the history read goes
MIN_INTERVAL_S = 1.0       # this client's floor between REST calls (the day and minute caps still hold)
SOURCE = "tastytrade (read-only)"

#: tastytrade transaction sub-types that move money in or out of the account (not P&L)
_DEPOSIT_SUBTYPES = {"deposit", "withdrawal", "transfer", "ach deposit", "ach withdrawal", "wire deposit",
                     "wire withdrawal", "journal entry"}
_OPTION_TYPES = {"equity option", "index option", "future option"}
_OCC = re.compile(r"^\s*([A-Z0-9./]+?)\s*(\d{6})([CP])(\d{8})\s*$")


class RealAccountUnavailable(RuntimeError):
    """No credentials, the broker budget is spent, or tastytrade refused: the router answers 503 with the reason."""


# ── helpers ───────────────────────────────────────────────────────────────────

def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _s(v) -> str:
    """An enum's value or the string itself (the SDK's InstrumentType / OrderAction are str enums)."""
    if v is None:
        return ""
    return str(getattr(v, "value", v))


def mask(account_number: str) -> str:
    n = str(account_number or "")
    return f"****{n[-4:]}" if len(n) > 4 else n


def parse_occ(symbol: str) -> Optional[dict]:
    """``SPXW  261106C07425000`` -> {root, expiry, right, strike}; None for a non-option symbol."""
    m = _OCC.match(str(symbol or ""))
    if not m:
        return None
    root, ymd, right, strike = m.groups()
    try:
        exp = _dt.datetime.strptime(ymd, "%y%m%d").date()
    except ValueError:
        return None
    return {"root": root, "expiry": exp, "right": "call" if right == "C" else "put", "strike": int(strike) / 1000.0}


def _now_et() -> _dt.datetime:
    from paper.providers import now_et
    return now_et()


def _market_hours(now: Optional[_dt.datetime] = None) -> bool:
    now = now or _now_et()
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    return 9 * 60 + 25 <= m <= 16 * 60 + 15


def _today() -> _dt.date:
    return _now_et().date()


# ── the client: one loop thread, one session, the broker budget, a small cache ─────────────────────────────────────

class RealAccountClient:
    def __init__(self, creds: Optional[tuple[str, str]] = None, budget=None,
                 session_factory: Optional[Callable] = None, account_api=None,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time):
        self._creds = creds
        self._budget = budget
        self._session_factory = session_factory          # tests inject a fake session class
        self._account_api = account_api                  # tests inject a fake Account class
        self._clock = clock
        self._wall = wall
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_lock = threading.Lock()
        self._session = None
        self._accounts: Optional[list] = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._key_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self.calls = 0

    # plumbing
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._loop_lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, name="real-account", daemon=True).start()
                self._loop = loop
            return self._loop

    def _run(self, coro, timeout: float = 45.0):
        return asyncio.run_coroutine_threadsafe(coro, self._ensure_loop()).result(timeout)

    def _take(self, n: int = 1) -> None:
        self.calls += n
        if self._budget is None:
            return
        from data.request_gate import ProviderUnavailable
        for _ in range(n):
            try:
                self._budget.take()
            except ProviderUnavailable as exc:
                raise RealAccountUnavailable(str(exc)) from None

    async def _get_session(self):
        if self._session is None:
            creds = self._creds
            if creds is None:
                from engine.env import tastytrade_credentials
                creds = tastytrade_credentials()
            if not creds:
                raise RealAccountUnavailable("no tastytrade login (TT_SECRET / TT_REFRESH) in the service's settings")
            factory = self._session_factory
            if factory is None:
                from tastytrade import Session as factory  # noqa: N813
            s = factory(*creds)
            self._session = await s.__aenter__()      # held for the process: the session owns one httpx client
        if self._wall() >= float(getattr(self._session, "session_expiration", 0.0) or 0.0) - 60:
            self._take()                              # the OAuth refresh the next request will make
        return self._session

    def _account_cls(self):
        if self._account_api is not None:
            return self._account_api
        from tastytrade import Account
        return Account

    async def _account(self, which: Optional[str] = None):
        s = await self._get_session()
        if self._accounts is None:
            self._take()
            accts = await self._account_cls().get(s)
            self._accounts = [a for a in accts if not getattr(a, "is_closed", False)]
        if not self._accounts:
            raise RealAccountUnavailable("the tastytrade login sees no open account")
        want = (which or os.environ.get("REAL_ACCOUNT", "")).strip()
        if want:
            for a in self._accounts:
                n = str(a.account_number)
                if n == want or n.endswith(want.lstrip("*")):
                    return s, a
            raise RealAccountUnavailable(f"no account matching {mask(want)} on this login")
        return s, self._accounts[0]

    def _cached(self, key: str, ttl: float, fetch: Callable):
        with self._key_locks[key]:
            hit = self._cache.get(key)
            if hit is not None and self._clock() - hit[0] < ttl:
                return hit[1]
            try:
                val = self._run(fetch())
            except RealAccountUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 - tastytrade or network: say so, keep a stale copy if we have one
                if hit is not None:
                    logger.warning("real account %s refresh failed (%s); serving the copy from %.0f s ago",
                                   key, exc, self._clock() - hit[0])
                    return hit[1]
                raise RealAccountUnavailable(f"tastytrade read failed: {type(exc).__name__}: {exc}") from None
            self._cache[key] = (self._clock(), val)
            return val

    def _live_ttl(self) -> float:
        return TTL_LIVE_S if _market_hours() else TTL_QUIET_S

    # the reads (each one GET; nothing else)
    def accounts(self) -> list:
        async def go():
            await self._account()
            return list(self._accounts or [])
        return self._cached("accounts", 24 * 3600.0, go)

    def balances(self, which: Optional[str] = None):
        async def go():
            s, a = await self._account(which)
            self._take()
            return a.account_number, await a.get_balances(s)
        return self._cached(f"bal:{which}", self._live_ttl(), go)

    def positions(self, which: Optional[str] = None) -> list:
        async def go():
            s, a = await self._account(which)
            self._take()
            return list(await a.get_positions(s, include_marks=True))
        return self._cached(f"pos:{which}", self._live_ttl(), go)

    def history(self, which: Optional[str] = None) -> list:
        async def go():
            s, a = await self._account(which)
            start = _today() - _dt.timedelta(days=HISTORY_DAYS)
            self._take()
            rows = list(await a.get_history(s, start_date=start, page_offset=None, per_page=250, sort="Asc"))
            if len(rows) > 250:
                self._take(len(rows) // 250)          # the extra pages the SDK fetched
            return rows
        return self._cached(f"hist:{which}", TTL_HISTORY_S, go)

    def net_liq_history(self, which: Optional[str] = None) -> list:
        async def go():
            s, a = await self._account(which)
            self._take()
            return list(await a.get_net_liquidating_value_history(s, time_back="1y"))
        return self._cached(f"nlv:{which}", TTL_NLV_S, go)


_CLIENT: Optional[RealAccountClient] = None
_CLIENT_LOCK = threading.Lock()


def client() -> RealAccountClient:
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            from api.config import external_state_dirs, service_state_dir
            from api.marketdata.providers.tastytrade import ServiceBrokerBudget
            budget = ServiceBrokerBudget(service_state_dir(), external_state_dirs(), min_interval_s=MIN_INTERVAL_S)
            _CLIENT = RealAccountClient(budget=budget)
        return _CLIENT


def set_client(c: Optional[RealAccountClient]) -> None:
    """Tests: install a client built on fakes."""
    global _CLIENT
    _CLIENT = c


# ── legs and groups ───────────────────────────────────────────────────────────

def _leg_from_position(p) -> dict:
    occ = parse_occ(p.symbol)
    sign = -1.0 if str(getattr(p, "quantity_direction", "")).lower().startswith("short") else 1.0
    qty = abs(_f(p.quantity) or 0.0)
    mult = _f(getattr(p, "multiplier", None)) or (100.0 if occ else 1.0)
    # mark_price is per share/contract unit (tastytrade's "mark" is the whole position's value): fall back to the
    # previous close when the mark is missing (a quiet weekend read)
    mark = _f(getattr(p, "mark_price", None))
    if mark is None:
        mark = _f(getattr(p, "close_price", None))
    exp = occ["expiry"] if occ else (getattr(p, "expires_at", None).date() if getattr(p, "expires_at", None) else None)
    return {"symbol": str(p.symbol).strip(), "underlying": str(getattr(p, "underlying_symbol", "") or (occ or {}).get("root", "")),
            "type": occ["right"] if occ else _s(getattr(p, "instrument_type", "")).lower() or "stock",
            "strike": occ["strike"] if occ else None, "expiry": exp, "qty": sign * qty, "multiplier": mult,
            "entry_price": _f(getattr(p, "average_open_price", None)), "mark": mark,
            "opened": getattr(p, "created_at", None)}


def _group_key(underlying: str, expiry: Optional[_dt.date], symbol: str) -> str:
    und = str(underlying or "").upper().replace("SPXW", "SPX").replace("NDXP", "NDX")
    return f"real:{und}:{expiry.isoformat()}" if expiry else f"real:{symbol.strip()}"


def describe(legs: list[dict]) -> str:
    """A plain structure label: "Call credit spread 7425/7435", "Long put 43", "Stock"."""
    opts = [l for l in legs if l.get("strike") is not None and abs(l.get("qty") or 0) > 0]
    if not opts:
        return "Stock" if legs else ""
    if len(opts) == 1:
        l = opts[0]
        return f"{'Long' if l['qty'] > 0 else 'Short'} {l['type']} {l['strike']:g}"
    if len(opts) == 2 and opts[0]["type"] == opts[1]["type"] and abs(opts[0]["qty"]) == abs(opts[1]["qty"]) \
            and (opts[0]["qty"] > 0) != (opts[1]["qty"] > 0):
        lo, hi = sorted(opts, key=lambda l: l["strike"])
        right = lo["type"]
        short = lo if lo["qty"] < 0 else hi
        credit = (right == "call" and short is lo) or (right == "put" and short is hi)
        return f"{right.capitalize()} {'credit' if credit else 'debit'} spread {lo['strike']:g}/{hi['strike']:g}"
    rights = sorted({l["type"] for l in opts})
    return f"{len(opts)}-leg {'/'.join(rights)}"


def _vertical_risk(legs: list[dict], entry_net: float) -> tuple[Optional[float], Optional[float]]:
    """(max_profit, max_loss) for a 2-leg same-right vertical; (None, None) otherwise."""
    opts = [l for l in legs if l.get("strike") is not None]
    if len(opts) != 2 or opts[0]["type"] != opts[1]["type"] or abs(opts[0]["qty"]) != abs(opts[1]["qty"]):
        return None, None
    width = abs(opts[0]["strike"] - opts[1]["strike"]) * abs(opts[0]["qty"]) * (opts[0]["multiplier"] or 100.0)
    if entry_net >= 0:                      # a credit: keep it all, or lose the width less it
        return entry_net, width - entry_net
    return width + entry_net, -entry_net    # a debit: the width less what was paid, or what was paid


# ── positions ─────────────────────────────────────────────────────────────────

_POS_FIELDS = ["trade_group_id", "strategy", "strategy_label", "underlying", "structure", "expiry", "dte", "contracts",
               "opened", "closed", "entry_net", "mark", "market_value", "pnl", "pnl_pct", "max_risk", "max_profit",
               "max_loss", "managed_by", "status", "priced_by", "is_live", "legs", "alert", "short_strikes"]
_POS_HEADERS = {"trade_group_id": "Trade Group", "strategy": "Strategy (slug)", "strategy_label": "Strategy",
                "underlying": "Underlying", "structure": "Structure", "expiry": "Expiry", "dte": "DTE",
                "contracts": "Contracts", "opened": "Opened", "closed": "Closed", "entry_net": "Net Entry",
                "mark": "Mark", "market_value": "Market Value", "pnl": "P&L", "pnl_pct": "P&L %",
                "max_risk": "Max Risk", "max_profit": "Max Profit", "max_loss": "Max Loss", "managed_by": "Managed By",
                "status": "Status", "priced_by": "Priced By", "is_live": "Live", "legs": "Legs", "alert": "Alert",
                "short_strikes": "Short Strikes"}
_POS_FORMATS = {"entry_net": "money", "market_value": "money", "pnl": "money", "max_risk": "money", "pnl_pct": "pct",
                "mark": "price", "contracts": "int", "dte": "int", "legs": "int", "max_profit": "money",
                "max_loss": "money", "short_strikes": "list"}
_POS_TYPES = {"trade_group_id": "string", "strategy": "string", "strategy_label": "string", "underlying": "string",
              "structure": "string", "expiry": "date", "dte": "integer", "contracts": "number", "opened": "date",
              "closed": "date", "entry_net": "number", "mark": "number", "market_value": "number", "pnl": "number",
              "pnl_pct": "number", "max_risk": "number", "max_profit": "number", "max_loss": "number",
              "managed_by": "string", "status": "string", "priced_by": "string", "is_live": "bool", "legs": "integer",
              "alert": "string", "short_strikes": "string"}


def _open_groups(which: Optional[str] = None) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in client().positions(which):
        leg = _leg_from_position(p)
        groups[_group_key(leg["underlying"], leg["expiry"], leg["symbol"])].append(leg)
    return dict(groups)


def _open_row(key: str, legs: list[dict]) -> dict:
    entry_net = sum(-(l["qty"]) * (l["entry_price"] or 0.0) * l["multiplier"] for l in legs)
    priced = [l for l in legs if l["mark"] is not None]
    market_value = sum(l["qty"] * l["mark"] * l["multiplier"] for l in priced)
    pnl = entry_net + market_value
    max_profit, max_loss = _vertical_risk(legs, entry_net)
    basis = max_loss if max_loss else (abs(entry_net) or None)
    exp = next((l["expiry"] for l in legs if l["expiry"]), None)
    contracts = max((abs(l["qty"]) for l in legs), default=None)
    opened = min((l["opened"] for l in legs if l["opened"] is not None), default=None)
    per_unit = (market_value / (contracts * legs[0]["multiplier"])) if contracts and priced else None
    return {"trade_group_id": key, "strategy": "real", "strategy_label": "Real (manual)",
            "underlying": legs[0]["underlying"], "structure": describe(legs), "expiry": exp,
            "dte": (exp - _today()).days if exp else None, "contracts": contracts,
            "opened": opened.date().isoformat() if hasattr(opened, "date") else None, "closed": None,
            "entry_net": round(entry_net, 2), "mark": per_unit, "market_value": round(market_value, 2),
            "pnl": round(pnl, 2), "pnl_pct": (pnl / basis * 100.0) if basis else None, "max_risk": max_loss,
            "max_profit": max_profit, "max_loss": max_loss, "managed_by": "you", "status": "open",
            "priced_by": "tastytrade mark", "is_live": len(priced) == len(legs), "legs": len(legs),
            "alert": "", "short_strikes": sorted({l["strike"] for l in legs if l["strike"] is not None and l["qty"] < 0})}


# ── history: transactions and closed round trips ──────────────────────────────

def _txn_row(t) -> dict:
    occ = parse_occ(getattr(t, "symbol", None) or "")
    fees = sum(abs(_f(getattr(t, k, None)) or 0.0) for k in
               ("commission", "clearing_fees", "regulatory_fees", "proprietary_index_option_fees", "other_charge"))
    when = getattr(t, "executed_at", None)
    return {"id": int(getattr(t, "id", 0) or 0), "date": _s(getattr(t, "transaction_date", "")) or (when.date().isoformat() if when else None),
            "time": when.astimezone().strftime("%H:%M:%S") if hasattr(when, "astimezone") else None,
            "type": str(getattr(t, "transaction_type", "") or ""), "sub_type": str(getattr(t, "transaction_sub_type", "") or ""),
            "action": _s(getattr(t, "action", None)), "symbol": str(getattr(t, "symbol", "") or "").strip(),
            "underlying": str(getattr(t, "underlying_symbol", "") or (occ or {}).get("root", "")),
            "option": f"{occ['expiry']:%d %b %y} {occ['strike']:g} {occ['right'].upper()}" if occ else "",
            "quantity": _f(getattr(t, "quantity", None)), "price": _f(getattr(t, "price", None)),
            "value": _f(getattr(t, "value", None)), "fees": round(fees, 2), "net_value": _f(getattr(t, "net_value", None)),
            "order_id": getattr(t, "order_id", None), "description": str(getattr(t, "description", "") or "")}


def _is_deposit(r: dict) -> bool:
    return r["type"].lower() == "money movement" and r["sub_type"].lower() in _DEPOSIT_SUBTYPES


def _is_position_txn(r: dict) -> bool:
    return r["type"].lower() in ("trade", "receive deliver") and bool(r["symbol"])


def _signed_qty(r: dict) -> float:
    q = abs(r["quantity"] or 0.0)
    a = r["action"].lower()
    if a.startswith("buy"):
        return q
    if a.startswith("sell"):
        return -q
    return 0.0          # expirations / exercises / assignments: they close whatever is open (handled by the group)


def round_trips(rows: list[dict]) -> list[dict]:
    """Group the position transactions by underlying + expiry (options) or symbol (stock) into round trips. A group is
    closed when every symbol nets to zero, or (options) once its expiry has passed and a settlement or expiration
    has posted for it."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if not _is_position_txn(r):
            continue
        occ = parse_occ(r["symbol"])
        groups[_group_key(r["underlying"], occ["expiry"] if occ else None, r["symbol"])].append(r)
    out = []
    today = _today()
    for key, txns in groups.items():
        net: dict[str, float] = defaultdict(float)
        settled = False
        for r in txns:
            if r["type"].lower() == "receive deliver":
                settled = True
                net[r["symbol"]] = 0.0
            else:
                net[r["symbol"]] += _signed_qty(r)
        exp = next((parse_occ(r["symbol"])["expiry"] for r in txns if parse_occ(r["symbol"])), None)
        flat = all(abs(v) < 1e-9 for v in net.values())
        closed = flat or (exp is not None and exp < today and settled)
        pending = exp is not None and exp <= today and not flat and not settled
        opens = [r for r in txns if r["action"].lower().endswith("to open")]
        entry_net = sum(r["net_value"] or 0.0 for r in opens)
        pnl = sum(r["net_value"] or 0.0 for r in txns)
        legs = [{"strike": parse_occ(r["symbol"])["strike"], "type": parse_occ(r["symbol"])["right"],
                 "qty": _signed_qty(r), "multiplier": 100.0} for r in opens if parse_occ(r["symbol"])]
        max_profit, max_loss = _vertical_risk(legs, entry_net) if legs else (None, None)
        out.append({"trade_group_id": key, "underlying": txns[0]["underlying"], "structure": describe(legs) if legs else "Stock",
                    "expiry": exp, "opened": min(r["date"] for r in txns), "closed": max(r["date"] for r in txns) if closed else None,
                    "contracts": max((abs(l["qty"]) for l in legs), default=None), "entry_net": round(entry_net, 2),
                    "pnl": round(pnl, 2), "max_profit": max_profit, "max_loss": max_loss,
                    "status": "closed" if closed else ("settling" if pending else "open"),
                    "short_strikes": sorted({l["strike"] for l in legs if l["qty"] < 0}), "n": len(txns)})
    return out


def _closed_row(rt: dict) -> dict:
    pnl = rt["pnl"]
    basis = rt["max_loss"] or (abs(rt["entry_net"]) or None)
    return {"trade_group_id": rt["trade_group_id"], "strategy": "real", "strategy_label": "Real (manual)",
            "underlying": rt["underlying"], "structure": rt["structure"], "expiry": rt["expiry"], "dte": None,
            "contracts": rt["contracts"], "opened": rt["opened"], "closed": rt["closed"], "entry_net": rt["entry_net"],
            "mark": None, "market_value": 0.0, "pnl": pnl, "pnl_pct": (pnl / basis * 100.0) if basis else None,
            "max_risk": rt["max_loss"], "max_profit": rt["max_profit"], "max_loss": rt["max_loss"], "managed_by": "you",
            "status": "closed", "priced_by": "closed", "is_live": False, "legs": rt["n"],
            "alert": "win" if pnl > 0 else ("loss" if pnl < 0 else "flat"), "short_strikes": rt["short_strikes"]}


def _history_rows(which: Optional[str] = None) -> list[dict]:
    return [_txn_row(t) for t in client().history(which)]


# ── the public reads (the paper API's shapes) ─────────────────────────────────

def accounts() -> dict:
    rows = [{"account": mask(a.account_number), "nickname": getattr(a, "nickname", None),
             "type": getattr(a, "account_type_name", None), "margin_or_cash": getattr(a, "margin_or_cash", None)}
            for a in client().accounts()]
    return to_jsonable({"accounts": rows, "source": SOURCE, "selected": os.environ.get("REAL_ACCOUNT") or (rows[0]["account"] if rows else None)})


def summary(which: Optional[str] = None) -> dict:
    c = client()
    number, bal = c.balances(which)
    open_rows = [_open_row(k, legs) for k, legs in _open_groups(which).items()]
    hist = _history_rows(which)
    trips = [t for t in round_trips(hist) if t["status"] == "closed"]
    deposits = sum(r["net_value"] or 0.0 for r in hist if _is_deposit(r))
    equity = _f(getattr(bal, "net_liquidating_value", None)) or 0.0
    cash = _f(getattr(bal, "cash_balance", None)) or 0.0
    try:
        nlv = c.net_liq_history(which)
    except RealAccountUnavailable:
        nlv = []
    prev = _previous_close(nlv, hist)
    starting = deposits if deposits else (_f(getattr(nlv[0], "close", None)) if nlv else equity) or equity
    realized = sum(t["pnl"] for t in trips)
    unrealized = sum(r["pnl"] for r in open_rows)
    today = _today().isoformat()
    wins = sum(1 for t in trips if t["pnl"] > 0)
    return to_jsonable({
        "starting_capital": starting, "cash": cash, "market_value": equity - cash, "equity": equity,
        "realized_pnl": realized, "unrealized_pnl": unrealized,
        "total_pnl": (equity - starting) if starting else realized + unrealized,
        "total_return": ((equity - starting) / starting) if starting else 0.0,
        "open_positions": len(open_rows), "closed_positions": len(trips),
        "asof": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "live_marks": all(r["is_live"] for r in open_rows) if open_rows else True,
        "total_return_pct": (((equity - starting) / starting) * 100.0) if starting else 0.0,
        "today_realized_pnl": sum(t["pnl"] for t in trips if str(t["closed"]) == today),
        "wins": wins, "win_rate": (wins / len(trips)) if trips else None, "deposits": deposits,
        # the real account's own figures
        "account": mask(number), "source": SOURCE, "previous_close": prev,
        "day_pnl": (equity - prev) if prev is not None else None,
        "buying_power": _f(getattr(bal, "derivative_buying_power", None)),
        "equity_buying_power": _f(getattr(bal, "equity_buying_power", None)),
        "pending_cash": _f(getattr(bal, "pending_cash", None)),
    })


def _nlv_series(nlv: list) -> pd.Series:
    pts = {}
    for p in nlv or []:
        t = pd.to_datetime(str(getattr(p, "time", "")), errors="coerce", utc=True)
        v = _f(getattr(p, "close", None))
        if t is not pd.NaT and t is not None and v is not None and not pd.isna(t):
            pts[t.tz_convert("America/New_York").normalize().tz_localize(None)] = v   # the day's last point wins
    return pd.Series(list(pts.values()), index=pd.DatetimeIndex(list(pts.keys())), dtype=float).sort_index()


def _deposits_by_day(hist_rows: list[dict]) -> pd.Series:
    """Net money in (+) or out (-) per day: deposits, withdrawals, transfers. Not P&L."""
    flows: dict = defaultdict(float)
    for r in hist_rows:
        if _is_deposit(r) and r.get("date"):
            flows[pd.Timestamp(str(r["date"])[:10])] += r["net_value"] or 0.0
    return pd.Series(list(flows.values()), index=pd.DatetimeIndex(list(flows.keys())), dtype=float).sort_index()


def _adjusted_nlv(nlv: list, hist_rows: list[dict]) -> pd.Series:
    """Net liq at each close PLUS the money deposited after that day, so a change between two points is P&L only: the
    owner's 11/02 $2,000 deposit read as "+$2,000 this week" on the raw net-liq line (smoke run, 2026-11-08)."""
    s = _nlv_series(nlv)
    if not len(s):
        return s
    dep = _deposits_by_day(hist_rows)
    if not len(dep):
        return s
    return pd.Series([v + float(dep[dep.index > d].sum()) for d, v in s.items()], index=s.index, dtype=float)


def _previous_close(nlv: list, hist_rows: Optional[list[dict]] = None) -> Optional[float]:
    s = _adjusted_nlv(nlv, hist_rows or [])
    s = s[s.index < pd.Timestamp(_today())]
    return float(s.iloc[-1]) if len(s) else None


def positions(status: str = "open", which: Optional[str] = None) -> dict:
    rows: list[dict] = []
    if status in ("open", "all"):
        rows += sorted((_open_row(k, legs) for k, legs in _open_groups(which).items()),
                       key=lambda r: (r["opened"] or "", r["trade_group_id"]), reverse=True)
    if status in ("closed", "all"):
        rows += sorted((_closed_row(t) for t in round_trips(_history_rows(which)) if t["status"] == "closed"),
                       key=lambda r: (str(r["closed"] or ""), r["trade_group_id"]), reverse=True)
    if not rows:
        return {"columns": [column(f, header=_POS_HEADERS.get(f, f), type=_POS_TYPES.get(f, "string"),
                                   format=_POS_FORMATS.get(f)) for f in _POS_FIELDS], "rows": []}
    return table_from_rows(rows, field_order=_POS_FIELDS, headers=_POS_HEADERS, formats=_POS_FORMATS, types=_POS_TYPES)


class UnknownTradeGroup(KeyError):
    pass


_LEG_FIELDS = ["symbol", "underlying", "type", "strike", "expiry", "side", "quantity", "multiplier", "entry_price",
               "mark", "pnl"]
_LEG_HEADERS = {"symbol": "Symbol", "underlying": "Underlying", "type": "Type", "strike": "Strike", "expiry": "Expiry",
                "side": "Side", "quantity": "Qty", "multiplier": "Mult", "entry_price": "Entry Price", "mark": "Mark",
                "pnl": "P&L"}


def legs(trade_group_id: str, which: Optional[str] = None) -> dict:
    groups = _open_groups(which)
    if trade_group_id in groups:
        rows = [{"symbol": l["symbol"], "underlying": l["underlying"], "type": l["type"], "strike": l["strike"],
                 "expiry": l["expiry"], "side": "SELL" if l["qty"] < 0 else "BUY", "quantity": abs(l["qty"]),
                 "multiplier": l["multiplier"], "entry_price": l["entry_price"], "mark": l["mark"],
                 "pnl": (None if l["mark"] is None else
                         round(l["qty"] * ((l["mark"] or 0.0) - (l["entry_price"] or 0.0)) * l["multiplier"], 2))}
                for l in groups[trade_group_id]]
        return table_from_rows(rows, field_order=_LEG_FIELDS, headers=_LEG_HEADERS,
                               formats={"entry_price": "price", "mark": "price", "pnl": "money", "strike": "price"})
    hist = [r for r in _history_rows(which) if _is_position_txn(r)]
    rows = []
    for r in hist:
        occ = parse_occ(r["symbol"])
        if _group_key(r["underlying"], occ["expiry"] if occ else None, r["symbol"]) == trade_group_id:
            rows.append(r)
    if not rows:
        raise UnknownTradeGroup(trade_group_id)
    return table_from_rows(rows, formats={"price": "price", "value": "money", "fees": "money", "net_value": "money"})


def transactions(limit: Optional[int] = None, which: Optional[str] = None) -> dict:
    rows = sorted(_history_rows(which), key=lambda r: (r["date"] or "", r["time"] or "", r["id"]), reverse=True)
    if limit:
        rows = rows[: int(limit)]
    if not rows:
        return {"columns": [], "rows": []}
    return table_from_rows(rows, formats={"price": "price", "value": "money", "fees": "money", "net_value": "money"})


def equity(from_date: Optional[str], to_date: Optional[str], which: Optional[str] = None) -> dict:
    end = _dt.date.fromisoformat(to_date[:10]) if to_date else _today()
    start = _dt.date.fromisoformat(from_date[:10]) if from_date else end - _dt.timedelta(days=30)
    s = _adjusted_nlv(client().net_liq_history(which), _history_rows(which))
    if len(s):
        s = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
    return to_jsonable({"series": [series(s if len(s) else None, "equity"), series(None, "cash")],
                        "from": start, "to": end,
                        "method": "tastytrade net liquidating value at each close, plus the money deposited after that day "
                                  "(so a change between two days is P&L, never a deposit)"})


def status() -> dict:
    """What the switch shows next to REAL: the account, the budget and the cache ages; it makes no broker call."""
    c = _CLIENT
    return to_jsonable({"source": SOURCE, "connected": bool(c and c._accounts),
                        "accounts": [mask(a.account_number) for a in (c._accounts or [])] if c else [],
                        "calls_this_process": c.calls if c else 0,
                        "cache_age_s": ({k: round(c._clock() - v[0], 1) for k, v in c._cache.items()} if c else {})})
