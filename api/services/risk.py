"""
api/services/risk.py — the risk of a paper position: what it is, what it can make or lose, how it moves.

  net_legs(grp)            a trade group's ledger rows netted per contract (long +, short -)
  describe_structure(legs) "put credit spread 750/745", "iron condor 740/745/790/795", "long call 770" …
  payoff_stats(grp, ref)   max profit / max loss / breakevens at expiry (the platform's expiry payoff)
  leg_greeks(hub, legs, S) per-leg mark, IV and greeks: the market-data hub's quote (the broker's
                           streamed greeks, yfinance's Black-Scholes greeks); else Black-Scholes on the
                           quote's IV; else Black-Scholes on the IV implied by the leg's mark
  position_risk_fields     everything the positions table adds for managing a position
  beta_spy(symbol)         1-year daily beta to SPY from stored daily bars (cached a day)

Greek units: per-leg greeks are per share of the option (delta, gamma per $1, theta per day, vega per
1 vol point); position totals are × quantity × multiplier with sign — delta in shares, gamma in shares
per $1, theta in $ per day, vega in $ per vol point. ``beta_delta_spy`` is the position's delta as SPY
shares: delta × spot × beta / SPY.
"""
from __future__ import annotations

import datetime as _dt
import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from api.marketdata import symbols as SYM

logger = logging.getLogger("alan_trader.api.risk")

RISK_FREE = 0.045
NY = "America/New_York"


@dataclass
class NetLeg:
    symbol: str                   # canonical (compact OCC for options, the ticker for stock)
    ledger_symbol: str
    type: str                     # call | put | stock
    strike: Optional[float]
    expiry: Optional[_dt.date]
    qty: float                    # signed: long +, short -
    mult: float

    @property
    def is_option(self) -> bool:
        return self.type in ("call", "put")


def net_legs(grp: pd.DataFrame) -> list[NetLeg]:
    out: dict[str, NetLeg] = {}
    for _, r in grp.iterrows():
        st = str(r.get("SecurityType") or "").lower()
        if st == "cash":
            continue
        sym = str(r.get("Symbol") or "")
        sign = 1.0 if str(r.get("Direction", "")).upper().startswith("B") else -1.0
        qty = sign * abs(float(r.get("Quantity") or 0))
        if sym in out:
            out[sym].qty += qty
            continue
        # anything that is not an option (stock, equity, the paper runner's SynFuture hedge) is a linear leg: a
        # SecurityType with no OptionType used to fall through to "put" and be priced as one
        typ = "stock" if st != "option" else ("call" if str(r.get("OptionType") or "").upper().startswith("C") else "put")
        try:
            canon = SYM.normalize(sym)
        except ValueError:
            canon = sym
        exp = r.get("Expiration")
        exp = pd.Timestamp(exp).date() if exp is not None and not pd.isna(exp) else None
        k = r.get("Strike")
        out[sym] = NetLeg(symbol=canon, ledger_symbol=sym, type=typ,
                          strike=float(k) if (typ != "stock" and k is not None and not pd.isna(k)) else None,
                          expiry=exp if typ != "stock" else None, qty=qty,
                          mult=float(r.get("Multiplier") or (1 if typ == "stock" else 100)))
    return [l for l in out.values() if abs(l.qty) > 1e-9]


# ── what it is ────────────────────────────────────────────────────────────────

def _k(v: float) -> str:
    return f"{v:g}"


def describe_structure(legs: list[NetLeg]) -> str:
    """A trader's name for the position, strikes listed from the leg that defines it."""
    if not legs:
        return ""
    opts = [l for l in legs if l.is_option]
    stock = [l for l in legs if not l.is_option]
    if stock and not opts:
        s = stock[0]
        return f"{'long' if s.qty > 0 else 'short'} stock {abs(s.qty):g}"
    if stock and len(opts) == 1 and len(stock) == 1:
        o, s = opts[0], stock[0]
        if s.qty > 0 and o.type == "call" and o.qty < 0:
            return f"covered call {_k(o.strike)}"
        if s.qty > 0 and o.type == "put" and o.qty > 0:
            return f"protective put {_k(o.strike)}"
    if stock:
        return f"custom ({len(legs)} legs)"
    exps = sorted({l.expiry for l in opts if l.expiry})
    qty = {abs(l.qty) for l in opts}
    calls = sorted([l for l in opts if l.type == "call"], key=lambda l: l.strike)
    puts = sorted([l for l in opts if l.type == "put"], key=lambda l: l.strike)
    if len(opts) == 1:
        o = opts[0]
        return f"{'long' if o.qty > 0 else 'short'} {o.type} {_k(o.strike)}"
    if len(exps) > 1:
        if len(opts) == 2 and opts[0].type == opts[1].type and opts[0].strike == opts[1].strike:
            return f"{opts[0].type} calendar {_k(opts[0].strike)}"
        if len(opts) == 2 and opts[0].type == opts[1].type:
            return f"{opts[0].type} diagonal {'/'.join(_k(l.strike) for l in opts)}"
        return f"custom ({len(opts)} legs, {len(exps)} expiries)"
    if len(opts) == 2 and len(qty) == 1:
        a, b = opts
        if a.type == b.type and (a.qty > 0) != (b.qty > 0):
            short, long_ = (a, b) if a.qty < 0 else (b, a)
            t = a.type
            # a call spread short the lower strike, or a put spread short the higher one, is a credit spread
            credit = (short.strike < long_.strike) if t == "call" else (short.strike > long_.strike)
            first, second = (short, long_) if credit else (long_, short)
            return f"{t} {'credit' if credit else 'debit'} spread {_k(first.strike)}/{_k(second.strike)}"
        if a.type != b.type and (a.qty > 0) == (b.qty > 0):
            side = "long" if a.qty > 0 else "short"
            c = a if a.type == "call" else b
            p = b if c is a else a
            if c.strike == p.strike:
                return f"{side} straddle {_k(c.strike)}"
            return f"{side} strangle {_k(p.strike)}/{_k(c.strike)}"
        if a.type != b.type:
            c = a if a.type == "call" else b
            p = b if c is a else a
            return f"{'risk reversal' if c.qty > 0 else 'collar'} {_k(p.strike)}/{_k(c.strike)}"
    if len(opts) == 4 and len(calls) == 2 and len(puts) == 2 and len(qty) == 1:
        ps, pl = (puts[1], puts[0])
        cs, cl = (calls[0], calls[1])
        if ps.qty < 0 < pl.qty and cs.qty < 0 < cl.qty:
            name = "iron butterfly" if ps.strike == cs.strike else "iron condor"
            return f"{name} {_k(pl.strike)}/{_k(ps.strike)}/{_k(cs.strike)}/{_k(cl.strike)}"
        if ps.qty > 0 > pl.qty and cs.qty > 0 > cl.qty:
            return f"reverse iron condor {_k(pl.strike)}/{_k(ps.strike)}/{_k(cs.strike)}/{_k(cl.strike)}"
    if len(opts) == 3 and len({l.type for l in opts}) == 1:
        s = sorted(opts, key=lambda l: l.strike)
        if s[0].qty * s[2].qty > 0 and s[1].qty * s[0].qty < 0 and abs(s[1].qty) == 2 * abs(s[0].qty):
            return f"{'long' if s[0].qty > 0 else 'short'} {s[0].type} butterfly " + "/".join(_k(l.strike) for l in s)
    return f"custom ({len(opts)} legs)"


def direction(legs: list[NetLeg], delta: Optional[float]) -> Optional[str]:
    if delta is None:
        return None
    return "bullish" if delta > 1e-6 else ("bearish" if delta < -1e-6 else "neutral")


# ── what it can make or lose ──────────────────────────────────────────────────

def payoff_stats(grp: pd.DataFrame, ref: Optional[float]) -> dict:
    """max_profit / max_loss (negative dollars; None = unbounded) and breakevens at expiry, from the
    ledger rows (net entry + intrinsic liquidation: the platform's expiry payoff)."""
    from paper.views import _expiry_payoff_pnl, position_risk
    strikes = sorted({float(k) for k in pd.to_numeric(grp.get("Strike", pd.Series(dtype=float)), errors="coerce").dropna()
                      if k > 0})
    ref = float(ref) if ref else (strikes[len(strikes) // 2] if strikes else 1.0)
    far = max([ref] + strikes) * 3.0
    pts = sorted({0.0, *strikes, ref, far})
    vals = [_expiry_payoff_pnl(grp, S) for S in pts]
    unbounded_up = _expiry_payoff_pnl(grp, far * 2.0) > vals[-1] + 1e-6
    max_profit = None if unbounded_up else max(vals)
    risk = position_risk(grp)
    max_loss = -risk if risk is not None else None
    breakevens = []
    for (s0, v0), (s1, v1) in zip(zip(pts, vals), zip(pts[1:], vals[1:])):
        if v0 == 0 and s0 > 0 and round(s0, 4) not in breakevens:
            breakevens.append(round(s0, 4))
        elif (v0 < 0 < v1) or (v0 > 0 > v1):
            breakevens.append(round(s0 + (s1 - s0) * (-v0) / (v1 - v0), 4))
    return {"max_profit": round(max_profit, 2) if max_profit is not None else None,
            "max_loss": round(max_loss, 2) if max_loss is not None else None, "breakevens": breakevens}


# ── how it moves ──────────────────────────────────────────────────────────────

def years_to_expiry(expiry: Optional[_dt.date], now: Optional[pd.Timestamp] = None) -> float:
    """Calendar years to expiry; on its last day, the trading time left (a session is 1/252 of a year)."""
    if expiry is None:
        return 0.0
    now = now or pd.Timestamp.now(tz=NY)
    days = (expiry - now.date()).days
    if days >= 1:
        return days / 365.0
    if days < 0:
        return 0.0
    close = now.normalize() + pd.Timedelta(hours=16)
    minutes = max((close - now).total_seconds() / 60.0, 1.0)
    return min(minutes, 390.0) / 390.0 / 252.0


def implied_vol(price: float, S: float, K: float, T: float, otype: str, r: float = RISK_FREE) -> Optional[float]:
    """Black-Scholes IV by bisection; None when the price is outside the no-arbitrage range."""
    if not (price and S and K and T and T > 0):
        return None
    intrinsic = max(S - K, 0.0) if otype == "call" else max(K - S, 0.0)
    if price <= intrinsic + 1e-6 or price >= (S if otype == "call" else K):
        return None
    lo, hi = 1e-4, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _bs_price(S, K, T, mid, otype, r) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def _bs_price(S, K, T, sigma, otype, r=RISK_FREE) -> float:
    from scipy.stats import norm
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if otype == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def leg_greeks(hub, legs: list[NetLeg], spot: Optional[float], wait: float = 2.0,
               quotes: Optional[dict] = None) -> dict[str, dict]:
    """symbol -> {"mark", "iv", "delta", "gamma", "theta", "vega", "source", "mark_source"} per share.
    ``quotes`` (symbol -> quote message) skips the hub snapshot when the caller already has one."""
    from paper.views import _bs_full
    out: dict[str, dict] = {}
    quotes = dict(quotes or {})
    syms = [l.symbol for l in legs if l.symbol not in quotes]
    if hub is not None and getattr(hub, "providers", None) and syms:
        try:
            quotes.update({q["symbol"]: q for q in hub.snapshot(syms, wait=wait)})
        except Exception as exc:
            logger.info("leg quotes unavailable: %s", exc)
    today = _dt.date.today()
    for l in legs:
        q = quotes.get(l.symbol) or {}
        mark = q.get("mid") if q.get("mid") is not None else q.get("last")
        g = {"mark": mark, "mark_source": q.get("source") if mark is not None else None,
             "iv": q.get("iv"), "delta": q.get("delta"), "gamma": q.get("gamma"), "theta": q.get("theta"),
             "vega": q.get("vega"), "source": q.get("source") if q.get("delta") is not None else None}
        if not l.is_option:
            g.update(delta=1.0, gamma=0.0, theta=0.0, vega=0.0, iv=None, source="stock")
            out[l.symbol] = g
            continue
        if l.expiry is not None and l.expiry < today:
            intrinsic = (max(0.0, (spot or 0) - l.strike) if l.type == "call" else max(0.0, l.strike - (spot or 0))) \
                if spot else None
            g.update(mark=intrinsic, mark_source="expired (intrinsic)", iv=None, delta=0.0, gamma=0.0, theta=0.0,
                     vega=0.0, source="expired")
            out[l.symbol] = g
            continue
        if g["delta"] is None and spot:
            T = years_to_expiry(l.expiry)
            iv = g["iv"]
            src = "black-scholes on quoted IV"
            if iv is None and mark is not None:
                iv = implied_vol(float(mark), float(spot), float(l.strike), T, l.type)
                src = "black-scholes on the mark's implied vol"
            if iv:
                _p, d, gm, v, th, _va = _bs_full(float(spot), float(l.strike), T, RISK_FREE, float(iv), l.type)
                g.update(iv=float(iv), delta=float(d), gamma=float(gm), vega=float(v), theta=float(th), source=src)
        out[l.symbol] = g
    return out


# ── beta ──────────────────────────────────────────────────────────────────────

_BETA: dict[str, tuple[float, Optional[float]]] = {}
_BETA_LOCK = threading.Lock()
BETA_TTL_S = 6 * 3600


def daily_closes(symbol: str, days: int = 400) -> pd.Series:
    """Stored daily closes (mkt.PriceBar; VIX from mkt.VixBar), date-indexed."""
    from db.client import get_price_bars
    from api.services.db import engine
    try:
        df = get_price_bars(engine(), symbol, _dt.date.today() - _dt.timedelta(days=days), _dt.date.today())
    except Exception:
        return pd.Series(dtype=float)
    if df is None or df.empty:
        return pd.Series(dtype=float)
    s = pd.Series(pd.to_numeric(df["close"], errors="coerce").values, index=pd.to_datetime(df["date"])).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def beta_spy(symbol: str) -> Optional[float]:
    """1-year daily-return beta to SPY from stored bars (None with under 120 common days)."""
    sym = str(symbol).upper()
    if sym == "SPY":
        return 1.0
    with _BETA_LOCK:
        hit = _BETA.get(sym)
        if hit is not None and time.monotonic() - hit[0] < BETA_TTL_S:
            return hit[1]
    a, b = daily_closes(sym, 400), daily_closes("SPY", 400)
    val = None
    if not a.empty and not b.empty:
        cutoff = pd.Timestamp(_dt.date.today() - _dt.timedelta(days=365))
        r = pd.concat([a, b], axis=1, join="inner").loc[lambda d: d.index >= cutoff].pct_change().dropna()
        if len(r) >= 120 and r.iloc[:, 1].var() > 0:
            val = round(float(np.cov(r.iloc[:, 0], r.iloc[:, 1])[0, 1] / r.iloc[:, 1].var()), 3)
    with _BETA_LOCK:
        _BETA[sym] = (time.monotonic(), val)
    return val


# ── the position ──────────────────────────────────────────────────────────────

def position_risk_fields(hub, grp: pd.DataFrame, underlying: str, spot: Optional[float] = None,
                         spy: Optional[float] = None, greeks: Optional[dict] = None) -> dict:
    """The management fields for one open trade group (``grp``: its ledger rows)."""
    legs = net_legs(grp)
    if spot is None and hub is not None and getattr(hub, "providers", None):
        try:
            spot = hub.price(underlying, wait=2.0)
        except Exception:
            spot = None
    g = greeks if greeks is not None else leg_greeks(hub, legs, spot)
    units = math.gcd(*[int(round(abs(l.qty))) for l in legs]) if legs and all(float(abs(l.qty)).is_integer() for l in legs) else 1
    units = max(units, 1)
    mult = max((l.mult for l in legs), default=100.0)
    from paper.views import _net_entry
    ne = _net_entry(grp)
    stats = payoff_stats(grp, spot)
    tot = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    complete = True
    for l in legs:
        lg = g.get(l.symbol) or {}
        for f in tot:
            v = lg.get(f)
            if v is None:
                complete = False
                continue
            tot[f] += float(v) * l.qty * l.mult
    shorts = [l for l in legs if l.is_option and l.qty < 0]
    short_delta, sigma_to_short, nearest = None, None, None
    tested = None
    for l in shorts:
        d = (g.get(l.symbol) or {}).get("delta")
        if d is not None and (tested is None or abs(d) > abs(tested[1])):
            tested = (l, float(d))
    if tested is not None:
        short_delta = round(tested[1], 4)
    if spot and shorts:
        best = None
        for l in shorts:
            iv = (g.get(l.symbol) or {}).get("iv")
            T = years_to_expiry(l.expiry)
            if not iv or T <= 0:
                continue
            dist = (l.strike - spot) if l.type == "call" else (spot - l.strike)     # + while out of the money
            z = dist / (spot * float(iv) * math.sqrt(T))
            if best is None or z < best[0]:
                best = (z, l.strike)
        if best is not None:
            sigma_to_short, nearest = round(best[0], 4), best[1]
    beta = beta_spy(underlying) if spot else None
    beta_delta = None
    if complete and spot and spy and beta is not None:
        beta_delta = round(tot["delta"] * spot * beta / spy, 2)
    exps = [l.expiry for l in legs if l.expiry]
    first_exp = min(exps) if exps else None
    return {
        "spot": spot,
        "structure": describe_structure(legs),
        "direction": direction(legs, tot["delta"] if complete else None),
        "units": units,
        "entry_credit_debit": round(ne / (units * mult), 4) if units and mult else None,
        "entry_type": ("credit" if ne > 0 else "debit") if ne else None,
        "max_profit": stats["max_profit"], "max_loss": stats["max_loss"], "breakevens": stats["breakevens"],
        "short_strikes": sorted({l.strike for l in shorts}),
        "short_delta": short_delta, "nearest_short_strike": nearest, "sigma_to_short": sigma_to_short,
        "delta": round(tot["delta"], 4) if complete else None,
        "gamma": round(tot["gamma"], 6) if complete else None,
        "theta": round(tot["theta"], 4) if complete else None,
        "vega": round(tot["vega"], 4) if complete else None,
        "beta_spy": beta, "beta_delta_spy": beta_delta,
        "greeks_source": ", ".join(sorted({str((g.get(l.symbol) or {}).get("source")) for l in legs
                                           if (g.get(l.symbol) or {}).get("source")})) or None,
        "first_expiry": first_exp,
    }
