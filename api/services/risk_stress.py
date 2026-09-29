"""
api/services/risk_stress.py — the paper book under stress: every open position, each strategy and the whole
portfolio repriced over a grid of underlying moves × implied-vol shocks, with the greeks re-computed at every cell.

  gather(hub)            the open positions exactly as /api/paper/positions shows them (the same ledger groups, runner
                         marks, hub quotes and P&L), each with its netted legs, its underlying's spot and an IV per leg
  cached_inputs(hub)     gather(), kept INPUT_TTL_S: a request costs no broker call beyond the positions table's own
  position_inputs(...)   one ledger group + its positions row → a StressPosition (pure: tests build stand-ins with it)
  compute(...)           the report itself (pure): greeks now, a grid per position / strategy / portfolio, worst cells
  report(hub, ...)       GET /api/risk

Pricing. Every leg is revalued in full with Black-Scholes (``paper.views._bs_full``, the helper api/services/risk.py
prices with) at the moved spot S·(1 + move%) and its IV + the shock — never a Taylor expansion — and the greeks of each
cell come from that same revaluation. A leg's IV is implied from its own mark (the hub's mid, else the paper runner's
leg price; a put the runner booked by call parity from the call at its strike) on the clock the grid prices on, so the
model reproduces the mark now. A leg whose mark cannot be inverted (a deep in-the-money 0DTE leg quoted at intrinsic)
borrows the nearest strike's IV on the same underlying and expiry, else the broker's quoted IV, else 20% (said so).

Clock. A same-day option is priced on the session clock, T = trading minutes left to 16:00 ET / 390 / 252 years
(risk.years_to_expiry's convention), floored at MIN_MINUTES so its greeks stay finite into the bell; a later expiry on
calendar time to its 16:00 ET close. Horizons: ``now``; ``1h`` (the clock an hour on: a same-day option past the close
has settled); ``settlement`` (the close of the nearest expiry held: legs expiring by then are worth their intrinsic
value at the moved spot and carry no greeks; later legs are priced with the time they have left).

P&L. ``pnl`` of a cell is the change from now. For now / +1h it is model against model (the same legs, IVs and
clock), so an unchanged market reads $0; at settlement it is the expiry value against the Paper page's market value,
so ``pnl_total`` (the P&L since entry: the page's P&L now + the change) is exactly the expiry payoff against entry.

Units (dollars, signed for the position): ``delta`` $ per +1% move of the underlying, ``delta_units`` the same delta in
units of the underlying (shares / index units); ``gamma`` the change in that $ delta per +1% move, ``gamma_units`` the
change in delta units per 1 point (risk.py's shares per $1); ``theta`` $ per day (a same-day option: per session) and
``theta_hour`` $ per hour; ``vega`` $ per +1 vol point. Units figures are null across more than one underlying.
Multipliers are the ledger's (100 for NDX/NDXP, SPX/SPXW options).
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

import pandas as pd

from api.services import risk as RK

logger = logging.getLogger("alan_trader.api.risk_stress")

NY = RK.NY
DEFAULT_MOVES: tuple[float, ...] = (-3.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0)
DEFAULT_VOLS: tuple[float, ...] = (-5.0, 0.0, 5.0, 10.0)
HORIZONS = ("now", "1h", "settlement")
HORIZON_LABELS = {"now": "Now", "1h": "+1h", "settlement": "Settlement"}

MIN_MINUTES = 5.0             # a same-day option keeps at least this much session time
SESSION_MINUTES = 390.0
SESSION_DAYS = 252.0
DEFAULT_IV = 0.20
MIN_IV = 0.01                 # a vol shock never takes a leg below 1%
INPUT_TTL_S = 20.0            # positions, marks and IVs are re-read at most this often
MAX_MOVES, MAX_VOLS = 25, 12
MOVE_LIMIT, VOL_LIMIT = 50.0, 100.0

_GREEK_KEYS = ("delta", "delta_units", "gamma", "gamma_units", "theta", "theta_hour", "vega")
_UNIT_KEYS = ("delta_units", "gamma_units")


# ── inputs ────────────────────────────────────────────────────────────────────

@dataclass
class StressLeg:
    symbol: str
    ledger_symbol: str
    type: str                          # call | put | stock
    strike: Optional[float]
    expiry: Optional[_dt.date]
    qty: float                         # signed: long +, short -
    mult: float
    mark: Optional[float] = None
    mark_source: Optional[str] = None
    iv: Optional[float] = None
    iv_source: Optional[str] = None
    quoted_iv: Optional[float] = None  # the broker's / provider's IV, a fallback only (its clock may not be ours)
    frozen: Optional[float] = None     # an option past its expiry: a fixed per-unit value, no greeks

    @property
    def is_option(self) -> bool:
        return self.type in ("call", "put")


@dataclass
class StressPosition:
    trade_group_id: str
    strategy: str
    strategy_label: str
    underlying: str
    structure: str
    legs: list[StressLeg]
    spot: Optional[float]
    entry_net: float                   # the cash the position moved: credits +, debits -
    market_value: float                # the Paper page's liquidation value now
    pnl: float                         # the Paper page's P&L now (entry_net + market_value)
    contracts: Optional[float] = None
    expiry: Optional[_dt.date] = None
    priced_by: Optional[str] = None
    max_loss: Optional[float] = None   # at expiry against entry (negative dollars); None with max_loss_unbounded
    max_loss_unbounded: bool = False
    max_profit: Optional[float] = None
    paper_greeks: dict = field(default_factory=dict)

    @property
    def priced(self) -> bool:
        return bool(self.spot) and float(self.spot) > 0 and bool(self.legs)


@dataclass
class Inputs:
    at: pd.Timestamp
    positions: list[StressPosition]
    warnings: list[str]
    monotonic: float = 0.0


# ── the clock ─────────────────────────────────────────────────────────────────

def _close(d: _dt.date) -> pd.Timestamp:
    return pd.Timestamp(_dt.datetime.combine(d, _dt.time(16, 0)), tz=NY)


def years_left(expiry: Optional[_dt.date], at: pd.Timestamp) -> Optional[tuple[float, str]]:
    """(T in years, "session" | "calendar") for an option at ``at``; None once it has settled (its close has passed)."""
    if expiry is None:
        return None
    day = at.date()
    if expiry < day:
        return None
    if expiry == day:
        minutes = (_close(expiry) - at).total_seconds() / 60.0
        if minutes <= 0:
            return None
        return min(max(minutes, MIN_MINUTES), SESSION_MINUTES) / SESSION_MINUTES / SESSION_DAYS, "session"
    return (_close(expiry) - at).total_seconds() / (365.0 * 86400.0), "calendar"


def settlement_time(positions: Iterable[StressPosition], now: pd.Timestamp) -> pd.Timestamp:
    """The close of the nearest expiry held (today's close at the earliest), never before ``now``."""
    exps = [l.expiry for p in positions for l in p.legs
            if l.is_option and l.frozen is None and l.expiry is not None and l.expiry >= now.date()]
    return max(_close(min(exps) if exps else now.date()), now)


def normalize_horizon(h: Optional[str]) -> str:
    k = str(h or "now").strip().lower().lstrip("+").strip()
    k = {"hour": "1h", "60m": "1h", "settle": "settlement", "expiry": "settlement", "close": "settlement"}.get(k, k)
    if k not in HORIZONS:
        raise ValueError(f"horizon must be one of now, +1h, settlement (got {h!r})")
    return k


def parse_grid(text: Optional[str], default: tuple[float, ...], name: str, limit: float, cap: int) -> tuple[float, ...]:
    """A comma-separated list of numbers ("-3,-1,0,1,3"), sorted and de-duplicated; ``default`` when empty."""
    if text is None or not str(text).strip():
        return default
    vals = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip().rstrip("%")
        if not part:
            continue
        try:
            v = float(part)
        except ValueError:
            raise ValueError(f"{name}: {part!r} is not a number")
        if not (-limit <= v <= limit):
            raise ValueError(f"{name}: {v:g} is outside ±{limit:g}")
        vals.append(v)
    vals = sorted(set(vals))
    if not vals:
        return default
    if len(vals) > cap:
        raise ValueError(f"{name}: at most {cap} values")
    return tuple(vals)


# ── one leg, one position ─────────────────────────────────────────────────────

def leg_state(leg: StressLeg, S: float, iv: float, at: pd.Timestamp) -> tuple[float, Optional[dict]]:
    """(value per unit, per-unit greeks) of a leg at spot ``S``, vol ``iv`` and time ``at``. Greeks per unit: delta,
    gamma per $1, theta per day and per hour, vega per vol point. A settled leg is worth its intrinsic value; no greeks."""
    if leg.frozen is not None:
        return float(leg.frozen), None
    if not leg.is_option:
        return float(S), {"delta": 1.0, "gamma": 0.0, "theta": 0.0, "theta_hour": 0.0, "vega": 0.0}
    k = float(leg.strike)
    tl = years_left(leg.expiry, at)
    if tl is None:
        return (max(S - k, 0.0) if leg.type == "call" else max(k - S, 0.0)), None
    T, clock = tl
    from paper.views import _bs_full
    px, d, g, v, th, _va = _bs_full(float(S), k, T, RK.RISK_FREE, max(float(iv), MIN_IV), leg.type)
    if clock == "session":        # T runs on sessions: a day is 1/252 of a year, an hour 1/6.5 of a session
        annual = float(th) * 365.0
        th_day, th_hour = annual / SESSION_DAYS, annual / SESSION_DAYS / (SESSION_MINUTES / 60.0)
    else:
        th_day, th_hour = float(th), float(th) / 24.0
    return float(px), {"delta": float(d), "gamma": float(g), "theta": th_day, "theta_hour": th_hour, "vega": float(v)}


def position_value(p: StressPosition, S: float, shock: float, at: pd.Timestamp) -> tuple[float, Optional[dict]]:
    """(liquidation value $, greeks totals) of a position at spot ``S``, every leg's IV + ``shock`` vol points, time
    ``at``. Totals are signed and × quantity × multiplier: delta / gamma in units of the underlying, the rest in $."""
    value = 0.0
    tot = {"delta_units": 0.0, "gamma_units": 0.0, "theta": 0.0, "theta_hour": 0.0, "vega": 0.0}
    live = False
    for l in p.legs:
        n = l.qty * l.mult
        px, g = leg_state(l, S, (l.iv if l.iv else DEFAULT_IV) + shock / 100.0, at)
        value += px * n
        if g is None:
            continue
        live = True
        tot["delta_units"] += g["delta"] * n
        tot["gamma_units"] += g["gamma"] * n
        tot["theta"] += g["theta"] * n
        tot["theta_hour"] += g["theta_hour"] * n
        tot["vega"] += g["vega"] * n
    return value, (tot if live else None)


def dollar_greeks(tot: Optional[dict], S: float) -> Optional[dict]:
    """Totals in units → the report's greeks: $ delta and $ gamma per 1% move of ``S`` beside the units."""
    if tot is None:
        return None
    one = S * 0.01
    return {"delta": tot["delta_units"] * one, "delta_units": tot["delta_units"],
            "gamma": tot["gamma_units"] * one * one, "gamma_units": tot["gamma_units"],
            "theta": tot["theta"], "theta_hour": tot["theta_hour"], "vega": tot["vega"]}


def position_inputs(tgid: str, grp: pd.DataFrame, row: dict, quotes: Optional[dict], at: pd.Timestamp,
                    live_legs: Optional[dict] = None, session_spot: Optional[float] = None,
                    parity_calls: Optional[dict] = None) -> StressPosition:
    """One open trade group (``grp``: its non-cash ledger rows; ``row``: its /api/paper/positions row) as the stress
    grid prices it: netted legs with a mark and an IV each (missing IVs are filled across the book by gather()).
    ``quotes``: the hub snapshot (canonical symbol -> quote); ``live_legs``: the runner's leg prices by ledger symbol;
    ``parity_calls``: put leg -> the call at its strike, for a put vertical the runner marks by call parity."""
    quotes = quotes or {}
    live_legs = live_legs or {}
    parity_calls = parity_calls or {}
    und = str(row.get("underlying") or "")
    spot = row.get("spot") or session_spot
    spot = float(spot) if spot else None
    legs: list[StressLeg] = []
    for nl in RK.net_legs(grp):
        q = quotes.get(nl.symbol) or {}
        mark, src = q.get("mid"), q.get("source")
        if mark is None and not nl.is_option:
            mark = q.get("last")
        if mark is None and (live_legs.get(nl.ledger_symbol) or {}).get("price") is not None:
            mark, src = float(live_legs[nl.ledger_symbol]["price"]), "paper runner feed"
        leg = StressLeg(symbol=nl.symbol, ledger_symbol=nl.ledger_symbol, type=nl.type, strike=nl.strike,
                        expiry=nl.expiry, qty=nl.qty, mult=nl.mult, mark=float(mark) if mark is not None else None,
                        mark_source=src if mark is not None else None,
                        quoted_iv=float(q["iv"]) if q.get("iv") else None)
        if leg.is_option and leg.expiry is not None and leg.expiry < at.date():
            # past its close and still on the books: held at its value now, whatever the grid does to spot
            leg.frozen = (max(spot - leg.strike, 0.0) if leg.type == "call" else max(leg.strike - spot, 0.0)) if spot else 0.0
            leg.iv_source = "expired: held at intrinsic"
        elif leg.is_option and spot:
            tl = years_left(leg.expiry, at)
            if tl is not None:
                T = tl[0]
                if leg.mark is not None and leg.mark > 0:
                    leg.iv = RK.implied_vol(leg.mark, spot, float(leg.strike), T, leg.type)
                    leg.iv_source = "implied from its mark" if leg.iv else None
                cq = quotes.get(parity_calls.get(leg.symbol, "")) or {}
                if leg.iv is None and cq.get("mid"):
                    leg.iv = RK.implied_vol(float(cq["mid"]), spot, float(leg.strike), T, "call")
                    leg.iv_source = "implied from the call at its strike (parity)" if leg.iv else None
        legs.append(leg)
    if "max_loss" in row:                       # the positions row's own payoff figures (risk.payoff_stats)
        max_loss, max_profit = row.get("max_loss"), row.get("max_profit")
    else:
        try:
            st = RK.payoff_stats(grp, spot)
            max_loss, max_profit = st["max_loss"], st["max_profit"]
        except Exception:  # noqa: BLE001
            max_loss = max_profit = None
    # None from payoff_stats is either unbounded or a position that cannot lose at expiry
    unbounded = max_loss is None and _unbounded_loss(grp)
    paper_greeks = {k: row.get(k) for k in ("delta", "gamma", "theta", "vega", "greeks_source") if k in row}
    exp = row.get("expiry")
    return StressPosition(
        trade_group_id=str(tgid), strategy=str(row.get("strategy") or ""),
        strategy_label=str(row.get("strategy_label") or row.get("strategy") or ""), underlying=und,
        structure=str(row.get("structure") or RK.describe_structure(RK.net_legs(grp))), legs=legs, spot=spot,
        entry_net=float(row.get("entry_net") or 0.0), market_value=float(row.get("market_value") or 0.0),
        pnl=float(row.get("pnl") or 0.0), contracts=row.get("contracts"),
        expiry=exp if isinstance(exp, _dt.date) or exp is None else pd.Timestamp(exp).date(),
        priced_by=row.get("priced_by"), max_loss=float(max_loss) if max_loss is not None else (None if unbounded else 0.0),
        max_loss_unbounded=unbounded, max_profit=max_profit, paper_greeks=paper_greeks)


def _unbounded_loss(grp: pd.DataFrame) -> bool:
    """True when the expiry payoff keeps falling as the underlying rises (an uncovered short call, short stock)."""
    from paper.views import _expiry_payoff_pnl
    try:
        strikes = [float(k) for k in pd.to_numeric(grp.get("Strike", pd.Series(dtype=float)), errors="coerce").dropna() if k > 0]
        prices = [float(x) for x in pd.to_numeric(grp.get("TransactionPrice", pd.Series(dtype=float)), errors="coerce").dropna() if x > 0]
        far = max(strikes + prices + [1.0]) * 3.0
        return _expiry_payoff_pnl(grp, far * 2.0) < _expiry_payoff_pnl(grp, far) - 1e-6
    except Exception:
        return False


def fill_missing_ivs(positions: list[StressPosition], at: pd.Timestamp) -> list[str]:
    """A leg with no IV of its own: the nearest strike's implied IV on the same underlying and expiry (a same-day leg
    first; the broker's quoted IV runs on a clock that may not be ours), else its quoted IV, else DEFAULT_IV.
    Returns a warning per leg left on the default."""
    pool: dict[tuple, list[tuple[float, float]]] = {}
    for p in positions:
        for l in p.legs:
            if l.is_option and l.iv and l.iv_source and l.iv_source.startswith("implied"):
                pool.setdefault((p.underlying, l.expiry), []).append((float(l.strike), float(l.iv)))
    notes = []
    for p in positions:
        for l in p.legs:
            if not l.is_option or l.iv or l.frozen is not None:
                continue
            near = sorted(pool.get((p.underlying, l.expiry), []), key=lambda kv: abs(kv[0] - float(l.strike)))
            nearest = (near[0][1], f"nearest strike's IV ({near[0][0]:g})") if near else None
            quoted = (l.quoted_iv, "the broker's quoted IV") if l.quoted_iv else None
            same_day = l.expiry == at.date()
            for choice in ((nearest, quoted) if same_day else (quoted, nearest)):
                if choice is not None:
                    l.iv, l.iv_source = choice
                    break
            if not l.iv:
                l.iv, l.iv_source = DEFAULT_IV, f"assumed {DEFAULT_IV:.0%} (no mark, quote or neighbour)"
                notes.append(f"{p.trade_group_id} {l.symbol}: no IV to be had, priced at an assumed {DEFAULT_IV:.0%}")
    return notes


# ── gathering the book ────────────────────────────────────────────────────────

def gather(hub) -> Inputs:
    """The open positions as the Paper page builds them (api/services/paper.py: the same load, runner marks and one
    hub snapshot of every leg and underlying), each turned into a StressPosition."""
    from api.services import paper as P
    pd_ = P.PD()
    at = pd.Timestamp.now(tz=NY)
    open_groups, _closed, _txns = P.load()
    labels = P._labels()
    marks = pd_.paper_runner_marks()
    quotes = P._hub_quotes(open_groups, marks, hub, all_groups=True)
    positions: list[StressPosition] = []
    warnings: list[str] = []
    for tgid, grp in open_groups.items():
        try:
            row = P._open_row(tgid, grp, marks, labels, quotes, hub)
            legs = P._noncash(grp)
            try:
                live_legs, session_spot = pd_.live_leg_prices(legs)
            except Exception:
                live_legs, session_spot = {}, None
            parity = P._parity_call_symbols(grp) if P._parity_group(grp) else {}
            positions.append(position_inputs(str(tgid), legs, row, quotes, at, live_legs=live_legs,
                                             session_spot=session_spot, parity_calls=parity))
        except Exception as exc:  # noqa: BLE001 — one bad group must not cost the report
            logger.warning("risk inputs for %s failed: %s", tgid, exc)
            warnings.append(f"{tgid}: left out ({type(exc).__name__}: {exc})")
    warnings += fill_missing_ivs(positions, at)
    return Inputs(at=at, positions=positions, warnings=warnings, monotonic=time.monotonic())


_CACHE: dict = {"inputs": None}
_CACHE_LOCK = threading.Lock()


def cached_inputs(hub) -> Inputs:
    """gather(), reused for INPUT_TTL_S (one refresh at a time): the page polls every 30 s and flips horizons."""
    with _CACHE_LOCK:
        hit = _CACHE.get("inputs")
        if hit is not None and time.monotonic() - hit.monotonic < INPUT_TTL_S:
            return hit
        fresh = gather(hub)
        _CACHE["inputs"] = fresh
        return fresh


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE["inputs"] = None


# ── the report ────────────────────────────────────────────────────────────────

def _r(v: Optional[float], n: int = 2) -> Optional[float]:
    return None if v is None else round(float(v), n)


def _round_greeks(g: Optional[dict]) -> Optional[dict]:
    if g is None:
        return None
    return {"delta": _r(g["delta"]), "delta_units": _r(g.get("delta_units"), 4), "gamma": _r(g["gamma"]),
            "gamma_units": _r(g.get("gamma_units"), 6), "theta": _r(g["theta"]), "theta_hour": _r(g["theta_hour"]),
            "vega": _r(g["vega"])}


def _sum_greeks(items: list[Optional[dict]], single: bool) -> Optional[dict]:
    items = [g for g in items if g is not None]
    if not items:
        return None
    out = {k: sum(float(g.get(k) or 0.0) for g in items) for k in _GREEK_KEYS}
    if not single:
        for k in _UNIT_KEYS:
            out[k] = None
    return out


def _scenario(underlyings: list[str], move: float, vol: float) -> str:
    who = underlyings[0] if len(underlyings) == 1 else "all"
    m = "unch." if move == 0 else f"{move:+g}%"
    v = "IV unch." if vol == 0 else f"IV {vol:+g}"
    return f"{who} {m} · {v}"


def _extremes(cells: list[list[dict]], underlyings: list[str]) -> tuple[Optional[dict], Optional[dict]]:
    flat = [c for row in cells for c in row]
    if not flat:
        return None, None

    def lite(c):
        return {"move": c["move"], "vol": c["vol"], "spot": c.get("spot"), "pnl": c["pnl"], "pnl_total": c["pnl_total"],
                "scenario": _scenario(underlyings, c["move"], c["vol"])}

    def nearest(target):
        # a spread at its full loss ties across many cells: name the smallest move (then shock) that gets there
        return min((c for c in flat if abs(c["pnl"] - target) < 0.5), key=lambda c: (abs(c["move"]), abs(c["vol"])))
    return lite(nearest(min(c["pnl"] for c in flat))), lite(nearest(max(c["pnl"] for c in flat)))


def _position_entity(p: StressPosition, moves, vols, horizon: str, at: pd.Timestamp, now: pd.Timestamp) -> dict:
    ent = {
        "kind": "position", "key": p.trade_group_id, "trade_group_id": p.trade_group_id, "label": p.structure,
        "strategy": p.strategy, "strategy_label": p.strategy_label, "underlying": p.underlying,
        "underlyings": [p.underlying], "structure": p.structure, "contracts": p.contracts, "expiry": p.expiry,
        "spot": p.spot, "priced_by": p.priced_by, "priced": p.priced, "positions": 1,
        "pnl": _r(p.pnl), "entry_net": _r(p.entry_net), "market_value": _r(p.market_value),
        "max_loss": _r(p.max_loss), "max_loss_unbounded": p.max_loss_unbounded, "max_profit": _r(p.max_profit),
        "paper_greeks": p.paper_greeks,
        "legs": [{"symbol": l.symbol, "type": l.type, "strike": l.strike, "expiry": l.expiry, "qty": l.qty,
                  "multiplier": l.mult, "mark": _r(l.mark, 4), "mark_source": l.mark_source, "iv": _r(l.iv, 4),
                  "iv_source": l.iv_source} for l in p.legs],
        "greeks": None, "stress": None,
    }
    if not p.priced:
        return ent
    S0 = float(p.spot)
    ref, tot_now = position_value(p, S0, 0.0, now)
    ent["model_value"] = _r(ref)
    ent["greeks"] = dollar_greeks(tot_now, S0)
    cells = []
    for m in moves:
        S = S0 * (1.0 + m / 100.0)
        row = []
        for v in vols:
            val, tot = position_value(p, S, v, at)
            change = val - (p.market_value if horizon == "settlement" else ref)
            row.append({"move": m, "vol": v, "spot": S, "pnl": change, "pnl_total": p.pnl + change,
                        "greeks": dollar_greeks(tot, S)})
        cells.append(row)
    ent["stress"] = {"cells": cells}
    return ent


def _group_entity(kind: str, key: str, label: str, members: list[dict], moves, vols) -> dict:
    priced = [m for m in members if m["priced"]]
    unds = sorted({m["underlying"] for m in members})
    single = len(unds) == 1
    unpriced_pnl = sum(m["pnl"] or 0.0 for m in members if not m["priced"])
    unbounded = any(m["max_loss_unbounded"] for m in members)
    ent = {"kind": kind, "key": key, "label": label, "underlyings": unds, "positions": len(members),
           "priced": bool(priced), "unpriced": [m["trade_group_id"] for m in members if not m["priced"]],
           "spot": priced[0]["spot"] if single and priced else None,
           "pnl": sum(m["pnl"] or 0.0 for m in members),
           "max_loss": None if unbounded else sum(m["max_loss"] or 0.0 for m in members),
           "max_loss_unbounded": unbounded,
           "greeks": _sum_greeks([m["greeks"] for m in priced], single), "stress": None}
    if priced:
        cells = []
        for i, m in enumerate(moves):
            row = []
            for j, v in enumerate(vols):
                parts = [x["stress"]["cells"][i][j] for x in priced]
                row.append({"move": m, "vol": v, "spot": parts[0]["spot"] if single else None,
                            "pnl": sum(c["pnl"] for c in parts),
                            "pnl_total": sum(c["pnl_total"] for c in parts) + unpriced_pnl,
                            "greeks": _sum_greeks([c["greeks"] for c in parts], single)})
            cells.append(row)
        ent["stress"] = {"cells": cells}
    return ent


def _finish(ent: dict) -> dict:
    """Worst / best cells, then rounding."""
    st = ent.get("stress")
    if st is not None:
        st["worst"], st["best"] = _extremes(st["cells"], ent["underlyings"])
        for row in st["cells"]:
            for c in row:
                c["pnl"], c["pnl_total"] = _r(c["pnl"]), _r(c["pnl_total"])
                c["spot"] = _r(c.get("spot"), 4)
                c["greeks"] = _round_greeks(c["greeks"])
        for k in ("worst", "best"):
            if st[k] is not None:
                st[k].update(pnl=_r(st[k]["pnl"]), pnl_total=_r(st[k]["pnl_total"]), spot=_r(st[k]["spot"], 4))
    ent["greeks"] = _round_greeks(ent.get("greeks"))
    for k in ("pnl", "max_loss"):
        ent[k] = _r(ent.get(k))
    return ent


def compute(positions: list[StressPosition], moves: Iterable[float] = DEFAULT_MOVES, vols: Iterable[float] = DEFAULT_VOLS,
            horizon: str = "now", now: Optional[pd.Timestamp] = None, warnings: Optional[list[str]] = None) -> dict:
    """The report for ``positions`` (pure): see the module docstring for the shape's meaning."""
    now = now if now is not None else pd.Timestamp.now(tz=NY)
    horizon = normalize_horizon(horizon)
    moves, vols = [float(m) for m in moves], [float(v) for v in vols]
    settle_at = settlement_time([p for p in positions if p.priced], now)
    times = {"now": now, "1h": now + pd.Timedelta(hours=1), "settlement": settle_at}
    at = times[horizon]
    pos = [_position_entity(p, moves, vols, horizon, at, now) for p in positions]
    by_strategy: dict[str, list[dict]] = {}
    for e in pos:
        by_strategy.setdefault(e["strategy"], []).append(e)
    strategies = [_group_entity("strategy", slug, members[0]["strategy_label"] or slug, members, moves, vols)
                  | {"strategy": slug, "strategy_label": members[0]["strategy_label"] or slug}
                  for slug, members in sorted(by_strategy.items(), key=lambda kv: (kv[1][0]["strategy_label"] or kv[0]).lower())]
    portfolio = _group_entity("portfolio", "portfolio", "Portfolio", pos, moves, vols)
    spots = {e["underlying"]: e["spot"] for e in pos if e["spot"]}
    notes = list(warnings or [])
    unpriced = [e["trade_group_id"] for e in pos if not e["priced"]]
    if unpriced:
        notes.append("no underlying price for " + ", ".join(unpriced) + ": left out of the greeks and the grid "
                     "(their P&L now still counts in the totals)")
    assumptions = [
        "Each cell revalues every leg in full with Black-Scholes (r = 4.5%) at spot × (1 + move) and its IV + the shock "
        "(vol points, floored at 1%); the greeks are re-computed there, not extrapolated.",
        "Now and +1h: the change from the model's value now (same legs, IVs and clock), so an unchanged market reads $0. "
        "Settlement: legs expiring by then are worth their intrinsic value at the moved spot; the change is against the "
        "Paper page's value now, and the total is the expiry payoff against entry.",
        f"A same-day option runs on the session clock (trading minutes left to 16:00 ET / 390 / 252 years, at least "
        f"{MIN_MINUTES:g} minutes); later expiries on calendar time. Each leg's IV is implied from its own mark on that clock.",
        "Greeks in dollars: delta = $ per +1% move of the underlying; gamma = change in that $ delta per +1% move; "
        "theta = $ per day (a same-day option: per session) and per hour; vega = $ per +1 vol point.",
    ]
    if len(spots) > 1:
        assumptions.insert(0, "More than one underlying: every underlying moves by the same percentage at once "
                              "(" + ", ".join(sorted(spots)) + "); unit greeks are left blank across them.")
    return {
        "asof": now, "horizon": horizon,
        "horizons": [{"key": k, "label": HORIZON_LABELS[k], "at": times[k]} for k in HORIZONS],
        "settlement_at": settle_at, "moves": moves, "vols": vols, "spots": spots,
        "assumptions": assumptions, "warnings": notes,
        "portfolio": _finish(portfolio),
        "by_strategy": [_finish(s) for s in strategies],
        "positions": [_finish(e) for e in pos],
    }


def _same_group(a: str, b: str) -> bool:
    """'NDX-NDX_0DTE-10116' or its ledger tail '10116' (the runner's own spelling)."""
    a, b = str(a), str(b)
    return a == b or a.rsplit("-", 1)[-1] == b.rsplit("-", 1)[-1]


def report(hub, moves: Optional[str] = None, vols: Optional[str] = None, horizon: Optional[str] = "now",
           strategy: Optional[str] = None, trade_group_id: Optional[str] = None) -> dict:
    """GET /api/risk. ValueError for a bad parameter (the router answers 422)."""
    from api.serialize import to_jsonable
    h = normalize_horizon(horizon)
    mv = parse_grid(moves, DEFAULT_MOVES, "moves", MOVE_LIMIT, MAX_MOVES)
    vs = parse_grid(vols, DEFAULT_VOLS, "vols", VOL_LIMIT, MAX_VOLS)
    inputs = cached_inputs(hub)
    positions = [p for p in inputs.positions
                 if (not strategy or p.strategy == strategy)
                 and (not trade_group_id or _same_group(p.trade_group_id, trade_group_id))]
    out = compute(positions, mv, vs, h, now=inputs.at, warnings=inputs.warnings)
    out["filter"] = {"strategy": strategy or None, "trade_group_id": trade_group_id or None}
    out["inputs_age_s"] = round(time.monotonic() - inputs.monotonic, 1)
    return to_jsonable(out)
