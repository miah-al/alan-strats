"""
api/marketdata/symbols.py — one spelling per instrument inside the service, each vendor's outside.

Canonical forms (what the API speaks):
  equity / ETF   ``SPY``, ``BRK.B``
  index          ``SPX``, ``NDX``, ``VIX`` … (``^VIX``, ``$VIX``, ``I:VIX`` are accepted)
  option         compact OCC: root + YYMMDD + C/P + strike x 1000 in 8 digits,
                 ``SPY261030C00770000`` (the padded OCC form and ``O:``-prefixed Polygon form are accepted)

Vendor forms: tastytrade DXLink ``SPY`` / ``SPX`` / ``.SPY261030C770``; Polygon ``SPY`` /
``I:SPX`` / ``O:SPY261030C00770000``; yfinance ``SPY`` / ``^SPX``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

#: Cash indices the service knows by name (canonical -> yfinance symbol)
INDICES = {
    "SPX": "^SPX", "NDX": "^NDX", "RUT": "^RUT", "DJI": "^DJI", "VIX": "^VIX", "VIX9D": "^VIX9D",
    "VIX3M": "^VIX3M", "VIX6M": "^VIX6M", "VIX1Y": "^VIX1Y", "VXN": "^VXN", "OEX": "^OEX", "XSP": "^XSP",
    "RVX": "^RVX", "SKEW": "^SKEW",
}
#: option roots whose underlying has another name (SPXW options are on SPX …)
ROOT_UNDERLYING = {"SPXW": "SPX", "NDXP": "NDX", "RUTW": "RUT", "VIXW": "VIX", "XSPW": "XSP"}

_OCC = re.compile(r"^([A-Z][A-Z0-9.]{0,5})(\d{6})([CP])(\d{8})$")
_OCC_PADDED = re.compile(r"^([A-Z][A-Z0-9.]{0,5})\s+(\d{6})([CP])(\d{8})$")
_STREAMER_OPT = re.compile(r"^\.([A-Z][A-Z0-9.]{0,5})(\d{6})([CP])(\d+(?:\.\d+)?)$")
_TICKER = re.compile(r"^[A-Z][A-Z0-9.\-/]{0,9}$")


@dataclass(frozen=True)
class OptionSymbol:
    root: str
    expiry: date
    right: str          # "C" | "P"
    strike: float

    @property
    def underlying(self) -> str:
        return ROOT_UNDERLYING.get(self.root, self.root)

    @property
    def occ(self) -> str:
        return f"{self.root}{self.expiry:%y%m%d}{self.right}{int(round(self.strike * 1000)):08d}"

    @property
    def streamer(self) -> str:
        k = self.strike
        ks = f"{k:.0f}" if float(k).is_integer() else (f"{k:.3f}".rstrip("0").rstrip("."))
        return f".{self.root}{self.expiry:%y%m%d}{self.right}{ks}"

    @property
    def polygon(self) -> str:
        return "O:" + self.occ

    @property
    def type(self) -> str:
        return "call" if self.right == "C" else "put"


def parse_option(sym: str) -> Optional[OptionSymbol]:
    s = str(sym or "").strip().upper()
    if s.startswith("O:"):
        s = s[2:]
    m = _OCC.match(s) or _OCC_PADDED.match(s)
    if m:
        root, ymd, cp, k = m.groups()
        try:
            exp = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
        except ValueError:
            return None
        return OptionSymbol(root.strip(), exp, cp, int(k) / 1000.0)
    m = _STREAMER_OPT.match(s)
    if m:
        root, ymd, cp, k = m.groups()
        try:
            exp = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
        except ValueError:
            return None
        return OptionSymbol(root, exp, cp, float(k))
    return None


def make_option(underlying_or_root: str, expiry: date, right: str, strike: float) -> OptionSymbol:
    r = str(right).strip().upper()[:1]
    if r not in ("C", "P"):
        raise ValueError(f"option right must be call/put, not {right!r}")
    return OptionSymbol(str(underlying_or_root).upper(), expiry, r, float(strike))


def normalize(sym: str) -> str:
    """The canonical spelling, or raises ValueError for something that is not a symbol."""
    s = str(sym or "").strip().upper()
    if not s:
        raise ValueError("empty symbol")
    opt = parse_option(s)
    if opt is not None:
        return opt.occ
    for prefix in ("^", "$", "I:"):
        if s.startswith(prefix) and s[len(prefix):] in INDICES:
            return s[len(prefix):]
    if s.startswith("^"):
        s = s[1:]
    if not _TICKER.match(s):
        raise ValueError(f"not a symbol: {sym!r}")
    return s


def is_option(sym: str) -> bool:
    return parse_option(sym) is not None


def is_index(sym: str) -> bool:
    return sym in INDICES


def to_streamer(sym: str) -> str:
    opt = parse_option(sym)
    return opt.streamer if opt else sym


def from_streamer(sym: str) -> str:
    opt = parse_option(sym) if sym.startswith(".") else None
    return opt.occ if opt else sym


def to_yfinance(sym: str) -> str:
    return INDICES.get(sym, sym.replace(".", "-") if not is_option(sym) else sym)


def to_polygon(sym: str) -> str:
    opt = parse_option(sym)
    if opt:
        return opt.polygon
    return f"I:{sym}" if sym in INDICES else sym
