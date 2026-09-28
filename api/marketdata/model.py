"""
api/marketdata/model.py — the quote record the hub keeps per symbol, and its wire shape.

Providers deliver partial updates (a streamer sends the bid/ask, the last trade and the day
summary as separate events); ``QuoteState.update`` merges them, and ``to_message`` produces the
contract's quote message:

  {"type": "quote", "symbol", "bid", "ask", "last", "mid", "prev_close", "change", "change_pct",
   "volume", "time", "source", ...}

Additions beyond the contract, when known: ``open``, ``high``, ``low``, ``bid_size``, ``ask_size``,
``age_s`` and, for options, ``iv``, ``delta``, ``gamma``, ``theta``, ``vega``, ``oi``, ``theo``.
"""
from __future__ import annotations

import datetime as _dt
import math
import time
from dataclasses import dataclass, field
from typing import Any, Optional

QUOTE_FIELDS = ("bid", "ask", "last", "prev_close", "volume", "open", "high", "low", "bid_size", "ask_size",
                "iv", "delta", "gamma", "theta", "vega", "oi", "theo")


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


@dataclass
class QuoteState:
    symbol: str
    source: str = ""
    values: dict = field(default_factory=dict)
    time: Optional[float] = None          # epoch seconds of the market event (provider time)
    received: float = 0.0                 # monotonic time the hub last updated it

    def update(self, source: str, event_time: Optional[float] = None, **fields) -> bool:
        """Merge fields (None values ignored). Returns whether anything changed."""
        changed = False
        for k, v in fields.items():
            if k not in QUOTE_FIELDS:
                continue
            n = _num(v)
            if n is None:
                continue
            if self.values.get(k) != n:
                self.values[k] = n
                changed = True
        if source and source != self.source:
            self.source = source
            changed = True
        if event_time:
            self.time = max(self.time or 0.0, float(event_time))
        self.received = time.monotonic()
        return changed

    @property
    def has_price(self) -> bool:
        v = self.values
        return any(v.get(k) is not None for k in ("last", "bid", "ask"))

    def age(self) -> Optional[float]:
        return (time.monotonic() - self.received) if self.received else None

    def mid(self) -> Optional[float]:
        b, a = self.values.get("bid"), self.values.get("ask")
        if b is not None and a is not None and a >= b and a > 0:
            return (b + a) / 2.0
        return None

    def price(self) -> Optional[float]:
        """The number to value it at: the mid when two-sided, else the last trade."""
        m = self.mid()
        return m if m is not None else self.values.get("last")

    def to_message(self) -> dict:
        v = self.values
        last = v.get("last")
        mid = self.mid()
        ref = last if last is not None else mid
        prev = v.get("prev_close")
        change = (ref - prev) if (ref is not None and prev) else None
        ts = self.time or (time.time() if self.received else None)
        vol = v.get("volume")
        msg = {
            "type": "quote", "symbol": self.symbol,
            "bid": v.get("bid"), "ask": v.get("ask"), "last": last, "mid": mid,
            "prev_close": prev, "change": change,
            "change_pct": (change / prev * 100.0) if (change is not None and prev) else None,
            "volume": int(round(vol)) if vol is not None else None,
            "time": _dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="milliseconds") if ts else None,
            "source": self.source or None,
        }
        option = _is_option(self.symbol)
        for k in ("open", "high", "low", "bid_size", "ask_size", "iv", "delta", "gamma", "theta", "vega", "oi", "theo"):
            if v.get(k) is not None and (option or k not in ("oi", "theo")):
                msg[k] = v[k]
        age = self.age()
        msg["age_s"] = round(age, 1) if age is not None else None
        return msg


def _is_option(symbol: str) -> bool:
    from api.marketdata.symbols import is_option
    return is_option(symbol)


def empty_quote(symbol: str, reason: str = "") -> dict:
    """A quote message with no data (a symbol no provider could price right now)."""
    return {"type": "quote", "symbol": symbol, "bid": None, "ask": None, "last": None, "mid": None,
            "prev_close": None, "change": None, "change_pct": None, "volume": None, "time": None,
            "source": None, "age_s": None, **({"error": reason} if reason else {})}
