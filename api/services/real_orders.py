"""
api/services/real_orders.py — the ONE path that may send an order to the owner's REAL tastytrade account.

The owner's decision (2026-11-09): at 1:00 PM Claude shows the SPX call credit spread ticket and asks; on the owner's
yes it places that order (1 lot) in the real account, cancels it if it has not filled by the cut-off, and holds it to
the 4:00 PM cash settlement. Everything else stays paper.

How nothing else can reach the real account:

* Only ``scripts/real_order.py`` imports this module, and it runs only when started by hand after the owner's yes
  (tests/test_real_orders.py scans the repo for any other import, and for the order-login names). The service, the
  paper order book (api/services/orders.py, which still refuses ``account: live``), the paper runners, the desk
  scripts and the agents never load it.
* ``<paper_state>/real_orders/permission.json`` is the owner's switch. No file, a bad file or ``"mode": "off"`` and
  every order is refused; ``"dry_run"`` allows only tastytrade's test orders (checked by tastytrade, never routed);
  ``"live"`` allows real ones. Strategy names live in that file's allow-list, never in platform code.
* An order must match an allow-list entry exactly: the underlying and option root, a CALL credit vertical of the
  entry's width (sell the lower strike, buy the higher), expiring today, 1..max_lots (never above HARD_MAX_LOTS), a
  LIMIT DAY credit in 0.05 steps of at least min_credit and under the width, the short strike at least min_room points
  above the index at the signal, sent inside the entry's window, at most one live order a day (an O_EXCL slot file
  taken BEFORE the order goes out, so a crash or a second process cannot send twice), and not once the realized loss
  since ``since`` has reached ``loss_pause``.
* Every live order is preceded by a tastytrade dry run of the same order; a dry run with errors stops the send.
* After the send the order is watched and cancelled at the entry's cancel_at if it has not filled. The broker budget
  counts these calls but never blocks one (a cancel must always go out).
* CLOSING (2026-11-14; on 11/13 the owner said "Close" three times and there was no reviewed path): ``close_spread``
  buys back the day's OWN filled spread and nothing else. The account must hold exactly that short and long call, no
  other order may be working on them, the debit is a LIMIT DAY in 0.05 steps no higher than the width, and a
  tastytrade dry run goes first. An unfilled closing order is cancelled after ``wait_s``, so one is never left working;
  at most HARD_MAX_CLOSES_PER_DAY attempts a day, one at a time. The loss pause does not apply: a close only reduces
  risk. Closing is the owner's call: it runs only on the owner's word at the time.

The full account number is never printed or recorded: ``mask`` it.
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
import logging
import os
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("alan_trader.real_orders")

MODES = ("off", "dry_run", "live")
#: which login places the order: the order-only grant, or the platform's own login
KEYS = {"trade": ("TT_TRADE_SECRET", "TT_TRADE_REFRESH"), "platform": ("TT_SECRET", "TT_REFRESH")}
#: raising either is a reviewed code change, by design (the permission file can only lower them)
HARD_MAX_LOTS = 1
HARD_MAX_LIVE_PER_DAY = 1
TICK = 0.05
TERMINAL = {"Filled", "Cancelled", "Rejected", "Expired", "Removed", "Partially Removed"}
POLL_S = 3.0
AFTER_CANCEL_S = 60.0
RESULT_COLS = ["day", "strategy", "short", "long", "lots", "credit", "fees", "spx_close", "settle_value", "pnl"]
#: closing the day's own spread
HARD_MAX_CLOSES_PER_DAY = 5          # closing attempts a day; one at a time, each cancelled if unfilled before the next
CLOSE_WAIT_S = 45.0                  # a closing order not filled in this long is cancelled; run close again at a new limit
CLOSE_HOURS = (_dt.time(9, 30), _dt.time(15, 59, 30))   # SPXW 0DTE options stop trading at 16:00
#: tastytrade's fee per contract for each leg cash-settled IN the money (seen 11/10 on both legs, 11/13 on the short)
SETTLE_FEE_PER_ITM_LEG = 5.0


class Refused(RuntimeError):
    """The order may not go; the message says why. Nothing was sent."""


class _SdkErrors(logging.Handler):
    """The SDK logs (at DEBUG) a tastytrade error it cannot format, e.g. ``Token has insufficient scopes``, and raises
    an EMPTY TastytradeError. Keep the last few so a refusal can say what tastytrade said."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.last: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if msg.startswith("Unknown error type:"):
            self.last = (self.last + [msg.split(":", 1)[1].strip()])[-3:]


_SDK_ERRORS = _SdkErrors()
_HINTS = {"insufficient scopes": "this login cannot trade: create an OAuth grant with the 'trade' scope"}


def capture_sdk_errors() -> None:
    """Attach the capture to the SDK's logger (idempotent). The caller decides what reaches the console."""
    lg = logging.getLogger("tastytrade")
    if _SDK_ERRORS not in lg.handlers:
        lg.addHandler(_SDK_ERRORS)


def describe_error(exc: BaseException) -> str:
    """``Type: message``, with what tastytrade said when the SDK raised an empty error, and a hint for known ones."""
    text = str(exc).strip()
    if not text and _SDK_ERRORS.last:
        text = _SDK_ERRORS.last[-1]
        _SDK_ERRORS.last = []
    for k, hint in _HINTS.items():
        if k in text.lower():
            text += f" ({hint})"
    return f"{type(exc).__name__}: {text or '(tastytrade gave no message)'}"


# ── the permission file and the ticket ───────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Rule:
    strategy: str
    underlying: str
    root: str
    right: str
    width: float
    max_lots: int
    min_credit: float
    min_room: float
    window: tuple[_dt.time, _dt.time]
    cancel_at: _dt.time
    max_live_per_day: int = 1


@dataclass(frozen=True)
class Permission:
    mode: str
    key: str
    account: str
    rules: tuple[Rule, ...]
    loss_pause: float
    since: _dt.date


@dataclass(frozen=True)
class Ticket:
    strategy: str
    day: _dt.date
    underlying: str
    root: str
    right: str
    short: float
    long: float
    lots: int
    limit: float          # the credit per spread, in points
    spot: float           # the index at the signal


def mask(account_number: str) -> str:
    n = str(account_number or "")
    return f"****{n[-4:]}" if len(n) > 4 else "****"


def orders_dir(state_dir: Path) -> Path:
    d = Path(state_dir) / "real_orders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def permission_path(state_dir: Path) -> Path:
    return Path(state_dir) / "real_orders" / "permission.json"


def _rule(r: dict) -> Rule:
    w0, w1 = r["window"]
    rule = Rule(strategy=str(r["strategy"]).strip(), underlying=str(r["underlying"]).strip().upper(),
                root=str(r["root"]).strip().upper(), right=str(r.get("right", "C")).strip().upper(),
                width=float(r["width"]), max_lots=int(r["max_lots"]), min_credit=float(r["min_credit"]),
                min_room=float(r["min_room"]), window=(_dt.time.fromisoformat(str(w0)), _dt.time.fromisoformat(str(w1))),
                cancel_at=_dt.time.fromisoformat(str(r["cancel_at"])), max_live_per_day=int(r.get("max_live_per_day", 1)))
    if not rule.strategy:
        raise ValueError("an allow-list entry has no strategy")
    if rule.right != "C":
        raise ValueError("only CALL credit spreads are supported")
    if not (rule.width > 0 and rule.max_lots >= 1 and rule.min_credit > 0 and rule.min_room >= 0
            and rule.max_live_per_day >= 1):
        raise ValueError(f"an allow-list entry has an impossible limit: {r}")
    if not (rule.window[0] < rule.window[1] < rule.cancel_at):
        raise ValueError("the window must open, close, then reach cancel_at, in that order")
    return rule


def load_permission(state_dir: Path) -> Permission:
    p = permission_path(state_dir)
    if not p.exists():
        raise Refused("no permission file: real orders are off")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        mode = str(d.get("mode", "off")).strip().lower()
        if mode not in MODES:
            raise ValueError(f"mode {mode!r} is not one of {MODES}")
        key = str(d.get("key", "trade")).strip().lower()
        if key not in KEYS:
            raise ValueError(f"key {key!r} is not one of {tuple(KEYS)}")
        account = str(d["account"]).strip().lstrip("*")
        if len(account) < 4:
            raise ValueError("account must give at least its last 4 characters")
        rules = tuple(_rule(r) for r in d["allow"])
        if not rules:
            raise ValueError("the allow-list is empty")
        if len({r.strategy for r in rules}) != len(rules):
            raise ValueError("a strategy is listed twice")
        loss_pause = float(d["loss_pause"])
        if loss_pause > 0:
            raise ValueError("loss_pause is a loss: zero or negative")
        since = _dt.date.fromisoformat(str(d["since"]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Refused(f"the permission file is not valid ({type(exc).__name__}: {exc}): real orders are off") from None
    return Permission(mode=mode, key=key, account=account, rules=rules, loss_pause=loss_pause, since=since)


def parse_ticket(d: dict) -> Ticket:
    try:
        lots = d["lots"]
        if isinstance(lots, bool) or float(lots) != int(float(lots)):
            raise ValueError(f"lots must be a whole number, not {lots!r}")
        t = Ticket(strategy=str(d["strategy"]).strip(), day=_dt.date.fromisoformat(str(d["day"])),
                   underlying=str(d["underlying"]).strip().upper(), root=str(d["root"]).strip().upper(),
                   right=str(d.get("right", "C")).strip().upper(), short=float(d["short"]), long=float(d["long"]),
                   lots=int(float(lots)), limit=round(float(d["limit"]), 2), spot=float(d["spot"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise Refused(f"the ticket is not valid ({type(exc).__name__}: {exc})") from None
    return t


# ── the day's ledger, the live slot, the results ─────────────────────────────────────────────────────────────────

def ledger_path(state_dir: Path, day: _dt.date) -> Path:
    return orders_dir(state_dir) / f"{day}.jsonl"


def record(state_dir: Path, day: _dt.date, event: str, at: Optional[_dt.datetime] = None, **data) -> dict:
    row = {"at": (at or _dt.datetime.now()).isoformat(timespec="seconds"), "event": event, **data}
    with open(ledger_path(state_dir, day), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return row


def read_ledger(state_dir: Path, day: _dt.date) -> list[dict]:
    p = ledger_path(state_dir, day)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def live_slots_used(state_dir: Path, day: _dt.date) -> int:
    return len(list(orders_dir(state_dir).glob(f"{day}.live.*.lock")))


def take_live_slot(state_dir: Path, day: _dt.date, per_day: int) -> Path:
    """Claim one of the day's live-order slots atomically (O_EXCL), BEFORE the order is sent. A slot is never given
    back: a send that failed may still have reached tastytrade."""
    for i in range(1, max(1, min(per_day, HARD_MAX_LIVE_PER_DAY)) + 1):
        p = orders_dir(state_dir) / f"{day}.live.{i}.lock"
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_dt.datetime.now().isoformat(timespec="seconds"))
        return p
    raise Refused(f"a live order was already sent on {day} (one a day)")


def close_slots_used(state_dir: Path, day: _dt.date) -> int:
    return len(list(orders_dir(state_dir).glob(f"{day}.close.*.lock")))


def take_close_slot(state_dir: Path, day: _dt.date) -> Path:
    """Claim one of the day's closing attempts atomically (O_EXCL), BEFORE the order is sent; never given back."""
    for i in range(1, HARD_MAX_CLOSES_PER_DAY + 1):
        p = orders_dir(state_dir) / f"{day}.close.{i}.lock"
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_dt.datetime.now().isoformat(timespec="seconds"))
        return p
    raise Refused(f"all {HARD_MAX_CLOSES_PER_DAY} closing attempts of {day} are used")


def results_path(state_dir: Path) -> Path:
    return orders_dir(state_dir) / "results.csv"


def read_results(state_dir: Path) -> list[dict]:
    p = results_path(state_dir)
    if not p.exists():
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def realized_since(state_dir: Path, since: _dt.date) -> float:
    total = 0.0
    for r in read_results(state_dir):
        try:
            if _dt.date.fromisoformat(r["day"]) >= since:
                total += float(r["pnl"])
        except (KeyError, ValueError):
            continue
    return round(total, 2)


def add_result(state_dir: Path, row: dict) -> dict:
    existing = read_results(state_dir)
    if any(r.get("day") == str(row["day"]) and r.get("strategy") == row["strategy"] for r in existing):
        raise Refused(f"{row['day']} {row['strategy']} is already in the results")
    p = results_path(state_dir)
    new = not p.exists()
    with open(p, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_COLS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in RESULT_COLS})
    return row


# ── the guard ────────────────────────────────────────────────────────────────────────────────────────────────────

def _close(a: float, b: float) -> bool:
    return abs(a - b) < 1e-6


def check(t: Ticket, perm: Permission, now: _dt.datetime, live: bool, state_dir: Path) -> Rule:
    """The allow-list entry this ticket matches, or Refused. ``now`` is naive US/Eastern."""
    if perm.mode == "off":
        raise Refused("real orders are off (permission mode 'off')")
    if live and perm.mode != "live":
        raise Refused(f"live orders are not allowed (permission mode {perm.mode!r}); only test orders")
    rule = next((r for r in perm.rules if r.strategy == t.strategy), None)
    if rule is None:
        raise Refused(f"strategy {t.strategy!r} may not trade the real account")
    if t.underlying != rule.underlying:
        raise Refused(f"underlying {t.underlying} is not {rule.underlying}")
    if t.root != rule.root:
        raise Refused(f"option root {t.root} is not {rule.root}")
    if t.right != rule.right:
        raise Refused(f"only {rule.right} spreads are allowed, not {t.right}")
    if t.day != now.date():
        raise Refused(f"the ticket expires {t.day}, not today ({now.date()})")
    if not _close(t.long - t.short, rule.width):
        raise Refused(f"the spread must be {rule.width:g} wide with the short strike below the long "
                      f"(short {t.short:g}, long {t.long:g})")
    cap = min(rule.max_lots, HARD_MAX_LOTS)
    if not (1 <= t.lots <= cap):
        raise Refused(f"{t.lots} lots: the limit is {cap}")
    steps = t.limit / TICK
    if not _close(steps, round(steps)):
        raise Refused(f"limit {t.limit} is not in {TICK:.2f} steps")
    if t.limit < rule.min_credit - 1e-9:
        raise Refused(f"credit {t.limit:.2f} is under the {rule.min_credit:.2f} minimum")
    if t.limit >= rule.width:
        raise Refused(f"credit {t.limit:.2f} is not under the width {rule.width:g}")
    if t.short - t.spot < rule.min_room - 1e-9:
        raise Refused(f"the short strike {t.short:g} is only {t.short - t.spot:.1f} pts above {t.underlying} "
                      f"{t.spot:,.2f} (the minimum is {rule.min_room:g})")
    loss = realized_since(state_dir, perm.since)
    if loss <= perm.loss_pause:
        raise Refused(f"paused: the real result since {perm.since} is {loss:+,.2f}, at or past the "
                      f"{perm.loss_pause:,.0f} pause")
    if live:
        if not (rule.window[0] <= now.time() <= rule.window[1]):
            raise Refused(f"{now:%H:%M:%S} is outside the {rule.window[0]:%H:%M:%S}-{rule.window[1]:%H:%M:%S} window")
        if live_slots_used(state_dir, t.day) >= min(rule.max_live_per_day, HARD_MAX_LIVE_PER_DAY):
            raise Refused(f"a live order was already sent on {t.day} (one a day)")
    return rule


def check_close(o: dict, perm: Permission, debit: float, now: _dt.datetime, live: bool,
                state_dir: Path) -> tuple[Ticket, Rule]:
    """The day's filled spread (``o`` is ``day_order``) and its allow-list entry, if a closing order at ``debit`` may
    go; else Refused. ``now`` is naive US/Eastern."""
    if perm.mode == "off":
        raise Refused("real orders are off (permission mode 'off')")
    if live and perm.mode != "live":
        raise Refused(f"live orders are not allowed (permission mode {perm.mode!r}); only test orders")
    if o.get("status") != "Filled" or not o.get("ticket"):
        raise Refused("no filled real order to close")
    if (o.get("close") or {}).get("status") == "Filled":
        raise Refused("the day's spread is already closed")
    t = parse_ticket(o["ticket"])
    rule = next((r for r in perm.rules if r.strategy == t.strategy), None)
    if rule is None:
        raise Refused(f"strategy {t.strategy!r} may not trade the real account")
    if t.day != now.date():
        raise Refused(f"the spread expired {t.day}: only today's spread can be closed")
    if not (CLOSE_HOURS[0] <= now.time() < CLOSE_HOURS[1]):
        raise Refused(f"{now:%H:%M:%S} is outside {CLOSE_HOURS[0]:%H:%M}-{CLOSE_HOURS[1]:%H:%M:%S}, when a close can go")
    steps = debit / TICK
    if not _close(steps, round(steps)):
        raise Refused(f"limit {debit} is not in {TICK:.2f} steps")
    if not (TICK - 1e-9 <= debit <= rule.width + 1e-9):
        raise Refused(f"a debit of {debit:.2f} is not between {TICK:.2f} and the width {rule.width:g}")
    if live and close_slots_used(state_dir, t.day) >= HARD_MAX_CLOSES_PER_DAY:
        raise Refused(f"all {HARD_MAX_CLOSES_PER_DAY} closing attempts of {t.day} are used")
    return t, rule


# ── the order ────────────────────────────────────────────────────────────────────────────────────────────────────

def occ_symbol(root: str, day: _dt.date, right: str, strike: float) -> str:
    """tastytrade's option symbol: the root padded to 6, then yymmdd, C/P and the strike x 1000 in 8 digits."""
    return f"{root:<6}{day:%y%m%d}{right}{int(round(strike * 1000)):08d}"


def build_order(t: Ticket):
    """SELL TO OPEN the lower call, BUY TO OPEN the higher one, as one LIMIT DAY order for a credit."""
    from tastytrade.order import InstrumentType, Leg, LimitOrder, OrderAction, OrderTimeInForce
    legs = [Leg(instrument_type=InstrumentType.EQUITY_OPTION, symbol=occ_symbol(t.root, t.day, t.right, t.short),
                action=OrderAction.SELL_TO_OPEN, quantity=t.lots),
            Leg(instrument_type=InstrumentType.EQUITY_OPTION, symbol=occ_symbol(t.root, t.day, t.right, t.long),
                action=OrderAction.BUY_TO_OPEN, quantity=t.lots)]
    return LimitOrder(time_in_force=OrderTimeInForce.DAY, legs=legs, price=Decimal(f"{t.limit:.2f}"))  # + = credit


def build_close_order(t: Ticket, debit: float):
    """BUY TO CLOSE the short call, SELL TO CLOSE the long one, as one LIMIT DAY order for a debit."""
    from tastytrade.order import InstrumentType, Leg, LimitOrder, OrderAction, OrderTimeInForce
    legs = [Leg(instrument_type=InstrumentType.EQUITY_OPTION, symbol=occ_symbol(t.root, t.day, t.right, t.short),
                action=OrderAction.BUY_TO_CLOSE, quantity=t.lots),
            Leg(instrument_type=InstrumentType.EQUITY_OPTION, symbol=occ_symbol(t.root, t.day, t.right, t.long),
                action=OrderAction.SELL_TO_CLOSE, quantity=t.lots)]
    return LimitOrder(time_in_force=OrderTimeInForce.DAY, legs=legs, price=Decimal(f"-{debit:.2f}"))  # - = debit


def _bare(symbol) -> str:
    return "".join(str(symbol or "").split())


def held(positions, t: Ticket) -> tuple[int, int]:
    """(short leg, long leg): the contracts the account holds in the ticket's two calls, negative when short."""
    short_sym = _bare(occ_symbol(t.root, t.day, t.right, t.short))
    long_sym = _bare(occ_symbol(t.root, t.day, t.right, t.long))
    s = lg = 0
    for p in positions or []:
        sym = _bare(getattr(p, "symbol", ""))
        if sym not in (short_sym, long_sym):
            continue
        q = abs(int(Decimal(str(getattr(p, "quantity", 0) or 0))))
        q = -q if _s(getattr(p, "quantity_direction", "")).lower() == "short" else q
        if sym == short_sym:
            s += q
        else:
            lg += q
    return s, lg


def _touches(order, t: Ticket) -> bool:
    syms = {_bare(occ_symbol(t.root, t.day, t.right, k)) for k in (t.short, t.long)}
    return any(_bare(getattr(leg, "symbol", "")) in syms for leg in getattr(order, "legs", None) or [])


def _s(v) -> str:
    return "" if v is None else str(getattr(v, "value", v))


def _num(v) -> Optional[float]:
    try:
        return None if v is None else round(float(v), 2)
    except (TypeError, ValueError):
        return None


def summarize(resp) -> dict:
    """tastytrade's answer to an order: the buying-power change, the fees, its warnings and errors."""
    bpe = getattr(resp, "buying_power_effect", None)
    fee = getattr(resp, "fee_calculation", None)
    return {"bp_change": _num(getattr(bpe, "change_in_buying_power", None)),
            "fees": abs(_num(getattr(fee, "total_fees", None)) or 0.0) if fee is not None else None,
            "warnings": [str(m) for m in (getattr(resp, "warnings", None) or [])],
            "errors": [str(m) for m in (getattr(resp, "errors", None) or [])]}


def net_fill(order, lots: int) -> Optional[float]:
    """The credit per spread from the legs' fills (sells add, buys subtract); None when no fill is reported."""
    total, seen = Decimal(0), False
    for leg in getattr(order, "legs", None) or []:
        sign = 1 if "Sell" in _s(getattr(leg, "action", "")) else -1
        for f in getattr(leg, "fills", None) or []:
            total += sign * Decimal(str(f.quantity)) * Decimal(str(f.fill_price))
            seen = True
    return float(round(total / max(1, lots), 2)) if seen else None


# ── the broker: one session, the order calls only ────────────────────────────────────────────────────────────────

def credentials(key: str) -> tuple[str, str]:
    names = KEYS[key]
    secret, refresh = (os.environ.get(n, "") for n in names)
    if not (secret and refresh):
        raise Refused(f"no {names[0]} / {names[1]} in the settings: that login is not set up")
    return secret, refresh


def keys_present() -> dict:
    """Which logins are set up (True/False only; never the values)."""
    return {k: all(os.environ.get(n) for n in names) for k, names in KEYS.items()}


class Broker:
    """The real account's order calls on one tastytrade session. Tests pass a fake session class and a fake
    Account class. Every call is counted by the broker budget when one is given, which never blocks a call."""

    def __init__(self, creds: tuple[str, str], budget=None, session_factory: Optional[Callable] = None,
                 account_api=None):
        self._creds = creds
        self._budget = budget
        self._session_factory = session_factory
        self._account_api = account_api
        self._cm = None
        self.session = None
        self.calls = 0
        self.account_number = ""

    async def __aenter__(self) -> "Broker":
        factory = self._session_factory
        if factory is None:
            from tastytrade import Session as factory  # noqa: N813
        self._cm = factory(*self._creds)
        self.session = await self._cm.__aenter__()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._cm is not None and hasattr(self._cm, "__aexit__"):
            await self._cm.__aexit__(*exc)

    def _count(self) -> None:
        self.calls += 1
        if self._budget is None:
            return
        try:
            self._budget.take()
        except Exception as exc:  # noqa: BLE001 - counted, never blocking: a cancel must always go out
            logger.warning("broker budget: %s (the real-order call goes ahead)", exc)

    def scrub(self, text: str) -> str:
        n = self.account_number
        return str(text).replace(n, mask(n)) if n else str(text)

    async def account(self, last4: str):
        api = self._account_api
        if api is None:
            from tastytrade import Account as api  # noqa: N813
        self._count()
        for a in await api.get(self.session):
            n = str(getattr(a, "account_number", ""))
            if n.endswith(last4) and not getattr(a, "is_closed", False):
                self.account_number = n
                return a
        raise Refused(f"this login sees no open account ending {last4}")

    async def dry_run(self, acct, order):
        self._count()
        return await acct.place_order(self.session, order, dry_run=True)

    async def send(self, acct, order):
        self._count()
        return await acct.place_order(self.session, order, dry_run=False)

    async def get(self, acct, order_id: int):
        self._count()
        return await acct.get_order(self.session, order_id)

    async def cancel(self, acct, order_id: int) -> None:
        self._count()
        await acct.delete_order(self.session, order_id)

    async def live_orders(self, acct) -> list:
        self._count()
        return list(await acct.get_live_orders(self.session))

    async def positions(self, acct) -> list:
        self._count()
        return list(await acct.get_positions(self.session))


# ── place, watch, settle ─────────────────────────────────────────────────────────────────────────────────────────

async def _sleep(s: float) -> None:
    import asyncio
    await asyncio.sleep(s)


async def place(t: Ticket, perm: Permission, rule: Rule, broker: Broker, state_dir: Path, *, live: bool,
                now: Callable[[], _dt.datetime], sleep: Callable = _sleep, poll_s: float = POLL_S,
                say: Callable[[str], Any] = print) -> dict:
    """A tastytrade dry run of the ticket's order; with ``live`` (and a clean dry run, inside the window, with the
    day's slot free) the real order, watched to its fill or cancelled at the cut-off."""
    order = build_order(t)
    acct = await broker.account(perm.account)
    tk = {k: (str(v) if isinstance(v, _dt.date) else v) for k, v in asdict(t).items()}
    try:
        dry = await broker.dry_run(acct, order)
    except Exception as exc:  # noqa: BLE001 - tastytrade's refusal: say it, send nothing
        msg = broker.scrub(describe_error(exc))
        record(state_dir, t.day, "dry_run_refused", now(), ticket=tk, error=msg)
        raise Refused(f"tastytrade refused the test order: {msg}") from None
    ds = summarize(dry)
    record(state_dir, t.day, "dry_run", now(), ticket=tk, **ds)
    out: dict = {"dry_run": ds, "account": mask(broker.account_number)}
    if ds["errors"]:
        raise Refused("tastytrade's test order has errors: " + "; ".join(ds["errors"]))
    if not live:
        return out

    n = now()
    if not (rule.window[0] <= n.time() <= rule.window[1]):
        raise Refused(f"{n:%H:%M:%S} is outside the {rule.window[0]:%H:%M:%S}-{rule.window[1]:%H:%M:%S} window: "
                      "nothing sent")
    slot = take_live_slot(state_dir, t.day, rule.max_live_per_day)
    record(state_dir, t.day, "live_sending", n, ticket=tk, slot=slot.name)
    try:
        resp = await broker.send(acct, order)
    except Exception as exc:  # noqa: BLE001
        msg = broker.scrub(describe_error(exc))
        record(state_dir, t.day, "live_send_failed", now(), error=msg)
        raise RuntimeError(f"the live send failed ({msg}); the day's slot stays used: run `status` to see whether "
                           "tastytrade has the order") from None
    po = resp.order
    oid = int(po.id)
    ls = summarize(resp)
    record(state_dir, t.day, "live_sent", now(), order_id=oid, status=_s(po.status), **ls)
    say(f"{now():%H:%M:%S} SENT: order {oid}, status {_s(po.status)}")
    out["live"] = {"order_id": oid, "status": _s(po.status), **ls}
    out["live"].update(await watch(broker, acct, oid, t, rule, state_dir, now=now, sleep=sleep, poll_s=poll_s, say=say))
    return out


async def watch(broker: Broker, acct, oid: int, t: Ticket, rule: Rule, state_dir: Path, *,
                now: Callable[[], _dt.datetime], sleep: Callable = _sleep, poll_s: float = POLL_S,
                say: Callable[[str], Any] = print, deadline: Optional[_dt.datetime] = None,
                prefix: str = "live") -> dict:
    """Poll the order until it is final; at the cut-off (the entry's cancel_at, or ``deadline``) cancel it, retrying
    until tastytrade takes the cancel. ``prefix`` names the ledger events: ``live`` for the opening order, ``close`` for
    a closing one, whose fill is booked as a debit."""
    cancel_sent_at: Optional[_dt.datetime] = None
    last = ""
    while True:
        try:
            po = await broker.get(acct, oid)
            st = _s(po.status)
        except Exception as exc:  # noqa: BLE001 - keep watching; the cancel below does not depend on this read
            po, st = None, ""
            logger.warning("order %s status read failed: %s", oid, broker.scrub(describe_error(exc)))
        if st and st != last:
            say(f"{now():%H:%M:%S} order {oid}: {st}")
            last = st
        if st in TERMINAL:
            res: dict = {"status": st}
            if st == "Filled":
                fill = net_fill(po, t.lots)
                if prefix == "close":
                    res["fill_debit"] = None if fill is None else round(-fill, 2)
                else:
                    res["fill_credit"] = fill
            record(state_dir, t.day, f"{prefix}_final", now(), order_id=oid, **res)
            return res
        n = now()
        due = n >= deadline if deadline is not None else n.time() >= rule.cancel_at
        if cancel_sent_at is None and due:
            cut = f"{deadline:%H:%M:%S}" if deadline is not None else f"{rule.cancel_at:%H:%M}"
            try:
                await broker.cancel(acct, oid)
                cancel_sent_at = n
                record(state_dir, t.day, f"{prefix}_cancel_sent", n, order_id=oid)
                say(f"{n:%H:%M:%S} not filled by {cut}: cancel sent")
            except Exception as exc:  # noqa: BLE001 - it may have just filled; the next read tells, else retry
                record(state_dir, t.day, f"{prefix}_cancel_failed", n, order_id=oid,
                       error=broker.scrub(describe_error(exc)))
        if cancel_sent_at is not None and (n - cancel_sent_at).total_seconds() >= AFTER_CANCEL_S:
            record(state_dir, t.day, f"{prefix}_watch_ended", n, order_id=oid, status=st or "unknown")
            return {"status": st or "unknown",
                    "warning": "cancel sent but no final status after 60 s: check the order in tastytrade"}
        await sleep(poll_s)


async def close_spread(t: Ticket, perm: Permission, rule: Rule, debit: float, broker: Broker, state_dir: Path, *,
                       live: bool, now: Callable[[], _dt.datetime], sleep: Callable = _sleep, poll_s: float = POLL_S,
                       wait_s: float = CLOSE_WAIT_S, say: Callable[[str], Any] = print) -> dict:
    """Close the day's own spread (``check_close`` passed): the account must hold it exactly as opened and no order may
    be working on it; then a tastytrade dry run; with ``live`` the real closing order, cancelled if it has not filled
    in ``wait_s`` seconds."""
    order = build_close_order(t, debit)
    acct = await broker.account(perm.account)
    s, lg = held(await broker.positions(acct), t)
    if (s, lg) != (-t.lots, t.lots):
        record(state_dir, t.day, "close_refused", now(), held={"short": s, "long": lg})
        raise Refused(f"the account does not hold the spread as opened (short {s:+d}, long {lg:+d}; expected "
                      f"-{t.lots}/+{t.lots}): nothing sent")
    working = [o for o in await broker.live_orders(acct)
               if _s(getattr(o, "status", "")) not in TERMINAL and _touches(o, t)]
    if working:
        ids = ", ".join(str(getattr(o, "id", "?")) for o in working)
        record(state_dir, t.day, "close_refused", now(), working=ids)
        raise Refused(f"order {ids} is still working on this spread: cancel it first; nothing sent")
    try:
        dry = await broker.dry_run(acct, order)
    except Exception as exc:  # noqa: BLE001 - tastytrade's refusal: say it, send nothing
        msg = broker.scrub(describe_error(exc))
        record(state_dir, t.day, "close_dry_run_refused", now(), debit=debit, error=msg)
        raise Refused(f"tastytrade refused the test closing order: {msg}") from None
    ds = summarize(dry)
    record(state_dir, t.day, "close_dry_run", now(), debit=debit, **ds)
    out: dict = {"dry_run": ds, "account": mask(broker.account_number)}
    if ds["errors"]:
        raise Refused("tastytrade's test closing order has errors: " + "; ".join(ds["errors"]))
    if not live:
        return out

    n = now()
    if not (CLOSE_HOURS[0] <= n.time() < CLOSE_HOURS[1]):
        raise Refused(f"{n:%H:%M:%S} is outside {CLOSE_HOURS[0]:%H:%M}-{CLOSE_HOURS[1]:%H:%M:%S}: nothing sent")
    slot = take_close_slot(state_dir, t.day)
    record(state_dir, t.day, "close_sending", n, debit=debit, slot=slot.name)
    try:
        resp = await broker.send(acct, order)
    except Exception as exc:  # noqa: BLE001
        msg = broker.scrub(describe_error(exc))
        record(state_dir, t.day, "close_send_failed", now(), error=msg)
        raise RuntimeError(f"the closing send failed ({msg}): run `status --broker` to see whether tastytrade has the "
                           "order before trying again") from None
    po = resp.order
    oid = int(po.id)
    ls = summarize(resp)
    record(state_dir, t.day, "close_sent", now(), order_id=oid, status=_s(po.status), **ls)
    say(f"{now():%H:%M:%S} SENT: closing order {oid}, status {_s(po.status)}")
    out["live"] = {"order_id": oid, "status": _s(po.status), **ls}
    out["live"].update(await watch(broker, acct, oid, t, rule, state_dir, now=now, sleep=sleep, poll_s=poll_s, say=say,
                                   deadline=n + _dt.timedelta(seconds=wait_s), prefix="close"))
    return out


def day_order(state_dir: Path, day: _dt.date) -> dict:
    """The day's live order as the ledger has it: the ticket, the order id, the final status and fill; and under
    ``close`` the latest closing order sent (the filled one, once one filled): its limit, id, fees, status and fill."""
    out: dict = {}
    for r in read_ledger(state_dir, day):
        ev = r.get("event")
        if ev == "live_sending":
            out["ticket"] = r.get("ticket")
        elif ev == "live_sent":
            out.update(order_id=r.get("order_id"), fees=r.get("fees"))
        elif ev == "live_final":
            out.update(status=r.get("status"), fill_credit=r.get("fill_credit"))
        elif ev == "dry_run" and out.get("dry_fees") is None:
            out["dry_fees"] = r.get("fees")
        elif ev in ("close_sending", "close_sent", "close_final") and (out.get("close") or {}).get("status") != "Filled":
            if ev == "close_sending":
                out["close"] = {"debit": r.get("debit"), "order_id": None, "fees": None, "status": None,
                                "fill_debit": None}
            elif ev == "close_sent":
                out.setdefault("close", {}).update(order_id=r.get("order_id"), fees=r.get("fees"))
            else:
                out.setdefault("close", {}).update(status=r.get("status"), fill_debit=r.get("fill_debit"))
    return out


def settle(state_dir: Path, day: _dt.date, index_close: Optional[float]) -> dict:
    """Book the day's filled real order. Closed early: (credit - the closing debit) x 100 x lots - both orders' fees.
    Held: (credit - the spread's value at ``index_close``) x 100 x lots - the fees, with tastytrade's fee for each leg
    settled in the money."""
    o = day_order(state_dir, day)
    if o.get("status") != "Filled" or not o.get("ticket"):
        raise Refused(f"no filled real order on {day}")
    tk = o["ticket"]
    short, long_, lots = float(tk["short"]), float(tk["long"]), int(tk["lots"])
    credit = o.get("fill_credit")
    credit = float(credit) if credit is not None else float(tk["limit"])
    fees = o.get("fees") if o.get("fees") is not None else o.get("dry_fees")
    fees = abs(float(fees)) if fees is not None else 0.0
    c = o.get("close") or {}
    if c.get("status") == "Filled":
        how = "closed"
        value = float(c["fill_debit"] if c.get("fill_debit") is not None else c["debit"])
        fees += abs(float(c.get("fees") or 0.0))
    else:
        if index_close is None:
            raise Refused(f"the {day} spread was held to the settlement: give the index's official close")
        how = "settled"
        x = float(index_close)
        value = max(0.0, min(long_ - short, x - short))
        fees += SETTLE_FEE_PER_ITM_LEG * lots * (int(x > short) + int(x > long_))
    pnl = round((credit - value) * 100 * lots - fees, 2)
    row = {"day": str(day), "strategy": tk["strategy"], "short": short, "long": long_, "lots": lots,
           "credit": credit, "fees": round(fees, 2), "spx_close": "" if index_close is None else float(index_close),
           "settle_value": round(value, 2), "pnl": pnl}
    add_result(state_dir, row)
    record(state_dir, day, "settled", None, result=dict(row, how=how))
    return dict(row, how=how)
