"""
api/services/coverage.py — what the database holds (the Tools → Data Manager coverage
view, for every ticker rather than a fixed list). SELECTs only.
"""
from __future__ import annotations

import logging

import pandas as pd

from api.serialize import table_from_df
from api.services.db import require_db

logger = logging.getLogger("alan_trader.api.coverage")

_PER_TICKER = {
    "price_bars": ("Daily price bars (mkt.PriceBar)", """
        SELECT t.Symbol AS ticker, COUNT(*) AS bars, MIN(pb.BarDate) AS first, MAX(pb.BarDate) AS last
        FROM mkt.PriceBar pb JOIN mkt.Ticker t ON t.TickerId = pb.TickerId
        GROUP BY t.Symbol ORDER BY t.Symbol"""),
    "option_snapshots": ("Option snapshots (mkt.OptionSnapshot)", """
        SELECT t.Symbol AS ticker, COUNT(DISTINCT o.SnapshotDate) AS days, COUNT(*) AS contracts,
               MIN(o.SnapshotDate) AS first, MAX(o.SnapshotDate) AS last
        FROM mkt.OptionSnapshot o JOIN mkt.Ticker t ON t.TickerId = o.TickerId
        GROUP BY t.Symbol ORDER BY t.Symbol"""),
    "minute_bars": ("1-minute bars (mkt.MinuteBar)", """
        SELECT t.Symbol AS ticker, COUNT(DISTINCT CAST(m.BarTs AS date)) AS sessions, COUNT(*) AS bars,
               CAST(MIN(m.BarTs) AS date) AS first, CAST(MAX(m.BarTs) AS date) AS last
        FROM mkt.MinuteBar m JOIN mkt.Ticker t ON t.TickerId = m.TickerId
        GROUP BY t.Symbol ORDER BY t.Symbol"""),
    "option_minute_bars": ("Option 1-minute prints (mkt.OptionMinuteBar)", """
        SELECT t.Symbol AS ticker, COUNT(*) AS bars, CAST(MIN(o.BarTs) AS date) AS first,
               CAST(MAX(o.BarTs) AS date) AS last
        FROM mkt.OptionMinuteBar o JOIN mkt.Ticker t ON t.TickerId = o.TickerId
        GROUP BY t.Symbol ORDER BY t.Symbol"""),
}

#: (label, table, date column) — the Data Manager's global datasets plus the event calendar.
_GLOBAL = [
    ("Treasury Yields", "mkt.TreasuryBar", "BarDate"),
    ("VIX Bars", "mkt.VixBar", "BarDate"),
    ("Macro (FRED)", "mkt.MacroBar", "BarDate"),
    ("CPI (FRED)", "mkt.CpiBar", "BarDate"),
    ("VIX Futures", "mkt.VixFuture", "TradeDate"),
    ("FOMC Calendar", "mkt.FomcCalendar", "MeetingDate"),
    ("Event Calendar", "mkt.EventCalendar", "EventDate"),
]


_HEADERS = {"ticker": "Ticker", "bars": "Bars", "days": "Days", "contracts": "Contracts", "sessions": "Sessions",
            "first": "From", "last": "To", "dataset": "Dataset", "table": "Table", "rows": "Rows"}


def coverage() -> dict:
    from sqlalchemy import text
    tables = []
    with require_db().connect() as c:
        for name, (label, sql) in _PER_TICKER.items():
            try:
                df = pd.read_sql(text(sql), c)
            except Exception as exc:
                logger.warning("coverage %s failed: %s", name, exc)
                df = pd.DataFrame()
            tables.append({"name": name, "label": label, "table": table_from_df(df, headers=_HEADERS)})
        rows = []
        for label, tbl, col in _GLOBAL:
            try:
                r = c.execute(text(f"SELECT MIN({col}), MAX({col}), COUNT(*) FROM {tbl}")).fetchone()
                rows.append({"dataset": label, "table": tbl, "first": r[0], "last": r[1], "rows": int(r[2] or 0)})
            except Exception:
                rows.append({"dataset": label, "table": tbl, "first": None, "last": None, "rows": None})
        gdf = pd.DataFrame(rows, columns=["dataset", "table", "first", "last", "rows"])
        gdf["rows"] = gdf["rows"].astype("Int64")          # a missing table is null, not NaN-as-float
        tables.append({"name": "global", "label": "Global datasets", "table": table_from_df(gdf, headers=_HEADERS)})
    return {"tables": tables}
