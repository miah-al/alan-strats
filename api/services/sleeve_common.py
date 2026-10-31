"""
api/services/sleeve_common.py — what the service's paper sleeves share: the exchange calendar's month-ends and the live
inputs (stored daily closes, the hub's prices, a sleeve's own open ETF lots).

Used by the momentum (btc_momentum, sol_momentum), trend (equity_trend, gold_trend) and cash (cash_sleeve) allocators.
It was the sector rotation's allocator module (rotation_alloc.py) until the rotation was retired (2026-10-11, replaced
by equity_trend; the allocator and its arm spec were deleted 2026-10-31, the owner: "Remove failed strategies code";
alan-strats #115). Only the parts the live sleeves import stayed.
"""
from __future__ import annotations

import datetime as _dt
import logging

import pandas as pd

logger = logging.getLogger("alan_trader.api.sleeve_common")

NY = "America/New_York"
HISTORY_DAYS = 160                      # calendar days of stored closes ``LiveInputs.closes`` reads by default


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


# ── the live inputs (each replaceable in tests) ──────────────────────────────

class LiveInputs:
    def __init__(self, hub, ledger: str, history_days: int = HISTORY_DAYS):
        self.hub = hub
        self.ledger = ledger                    # whose open lots ``lots`` returns: the sleeve's StrategyName in the ledger
        self.history_days = int(history_days)   # calendar days of stored closes ``closes`` reads

    def closes(self, symbols: tuple, until: _dt.date) -> pd.DataFrame:
        """Stored daily closes (mkt.PriceBar, topped up when behind) up to ``until``: rows = dates, columns = symbols."""
        from api.services.db import require_db
        from db.client import get_price_bars
        eng = require_db()
        start = until - _dt.timedelta(days=self.history_days)
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
            if grp.empty or str(grp["StrategyName"].iloc[0]) != self.ledger:
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
