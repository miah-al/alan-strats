"""
strategy_api/columns.py — screener grid column definitions, headless.

A strategy's ``StrategyUI.columns`` is a list of ag-grid style column dicts; ``col()`` builds
one and ``GENERIC_COLS`` is the set used when a strategy declares none. Plain data: the
service turns them into its Table columns, a grid renders them as they are. Plugins still
reach these through ``app.ui.strategy_widgets`` while the Dash app exists.
"""
from __future__ import annotations


def col(field: str, width: int | None = None, flex: int | None = None,
        min_width: int = 70, numeric: bool = False, pinned: str | None = None,
        sort: str | None = None) -> dict:
    d: dict = {"field": field, "resizable": True, "sortable": True, "filter": True,
               "minWidth": min_width}
    if width:
        d["width"] = width
    if flex:
        d["flex"] = flex
    if numeric:
        d["type"] = "numericColumn"
    if pinned:
        d["pinned"] = pinned
    if sort:
        d["sort"] = sort
    return d


#: Generic column set used when a strategy declares none.
GENERIC_COLS = [
    col("Ticker", width=130, pinned="left"),
    col("Price",  width=110, numeric=True),
    col("Signal", width=110),
    col("Score",  width=110, numeric=True, sort="desc"),
    col("Status", width=160),
]
