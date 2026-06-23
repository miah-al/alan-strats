"""Shared Mantine React Table helpers — single source of truth for the app's
post-AgGrid grid component.

Why this file exists
--------------------
`dash-mantine-react-table` v0.0.1 must be imported at module-load time (Dash
raises ImportedInsideCallbackError otherwise). To avoid duplicating that
import + the long mrtProps boilerplate across paper_trading.py / strategies /
tools / market, we centralise the wrapper here. Every page imports
`from app.grid_helpers import mrt_grid, aggrid_cols_to_mrt`.
"""
from __future__ import annotations

from dash import dcc, html

from dash_mantine_react_table import DashMantineReactTable as _MRT

from app import theme as T


def aggrid_cols_to_mrt(cols: list) -> list:
    """Convert AgGrid columnDefs to dash-mantine-react-table column defs.

    Drops `width` / `minWidth` so MRT can flex columns to container width
    (no horizontal scroll). Numeric columns get right-aligned in body+head.

    Columns marked `hide: True` are skipped entirely — MRT has no `hide` prop, so
    a hidden AG-Grid column would otherwise become a VISIBLE MRT column. That is
    fatal for columns whose value is a dict (e.g. `_chain`): React throws
    "Objects are not valid as a React child". The row `data` still carries those
    keys (data is independent of columns), so row-click callbacks that read
    `_chain` from the row keep working — the value just isn't displayed.
    """
    out = []
    for c in cols:
        if "field" not in c:
            continue
        if c.get("hide"):
            continue
        mc = {
            "accessorKey": c["field"],
            "header":      c.get("headerName", c["field"]),
        }
        if c.get("type") == "numericColumn":
            mc["mantineTableBodyCellProps"] = {"align": "right"}
            mc["mantineTableHeadCellProps"] = {"align": "right"}
        out.append(mc)
    return out


def mrt_grid(
    *,
    id: str | None = None,
    data: list | None = None,
    columns: list | None = None,
    aggrid_cols: list | None = None,
    height: int = 400,
    enable_pagination: bool = True,
    page_size: int = 25,
    density: str = "xs",
    layout_mode: str = "grid",
    header_menu: bool = True,
):
    """Build a DashMantineReactTable wrapped with the app's dark theme.

    Accepts EITHER:
      - `columns` (MRT-native column defs), OR
      - `aggrid_cols` (legacy AgGrid columnDefs — will be converted in place).

    Returns a Dash component. Use `data` prop in callbacks (NOT `rowData`).
    """
    if columns is None:
        if aggrid_cols is None:
            raise ValueError("mrt_grid requires either `columns` or `aggrid_cols`")
        columns = aggrid_cols_to_mrt(aggrid_cols)

    kwargs = {}
    if id is not None:
        kwargs["id"] = id

    return _MRT(
        data=data or [],
        columns=columns,
        mrtProps={
            "enableColumnFilters":   True,
            "enableGlobalFilter":    True,
            "enableSorting":         True,
            "enableDensityToggle":   True,
            "enableColumnOrdering":  header_menu,
            "enableColumnActions":   header_menu,
            "enableColumnDragging":  header_menu,
            "enableColumnResizing":  True,
            "enablePagination":      bool(enable_pagination),
            "enableStickyHeader":    True,   # header pinned while body scrolls
            "layoutMode":            layout_mode,
            "initialState": {
                "density": density,
                "pagination": {"pageIndex": 0, "pageSize": page_size},
            },
            "defaultColumn": {"minSize": 80, "maxSize": 400, "size": 130},
            "mantineTableProps": {
                "striped": False,
                "highlightOnHover": True,
                "withTableBorder": False,
                "withColumnBorders": False,
                "horizontalSpacing": "md",
                "verticalSpacing": "xs",
            },
            "mantineTableHeadCellProps": {
                # Belt-and-suspenders: even if enableStickyHeader has any quirk
                # under specific Mantine versions, the inline style forces it.
                "style": {
                    "position": "sticky",
                    "top": 0,
                    "backgroundColor": T.BG_CARD,
                    "zIndex": 2,
                },
            },
            "mantineTableContainerProps": {
                "style": {"maxHeight": f"{height}px", "width": "100%",
                          "overflowY": "auto"},
            },
            "mantinePaperProps": {
                "shadow": "0",
                "withBorder": False,
                "style": {"backgroundColor": "transparent", "width": "100%"},
            },
        },
        mantineProviderProps={
            "theme": {
                "colorScheme": "dark",
                "primaryColor": "indigo",
                "fontFamily": "Inter, system-ui, sans-serif",
            },
        },
        className="alan-mrt",
        **kwargs,
    )


# ── Clickable variant — bridges row clicks back to Dash via assets/mrt_row_click.js ──

def clickable_mrt_grid(
    *,
    grid_id: str,
    data: list | None = None,
    columns: list | None = None,
    aggrid_cols: list | None = None,
    height: int = 400,
    enable_pagination: bool = True,
    page_size: int = 25,
):
    """An MRT grid wrapped so that row clicks fire a Dash callback.

    Server-side pattern:
        # Layout:
        clickable_mrt_grid(grid_id="my-grid", aggrid_cols=COLS, data=rows)

        # Callback:
        @callback(
            Output("my-modal", "is_open"),
            Input(f"my-grid-clicked", "value"),
            State("my-grid", "data"),
            prevent_initial_call=True,
        )
        def on_row_click(payload_json, all_rows):
            if not payload_json or not all_rows:
                return no_update
            import json
            payload = json.loads(payload_json)
            row_index = payload.get("rowIndex", -1)
            if 0 <= row_index < len(all_rows):
                row = all_rows[row_index]
                # ... open modal with row data ...

    The hidden input id is f"{grid_id}-clicked" (must match in callback).
    """
    grid = mrt_grid(
        id=grid_id,
        data=data,
        columns=columns,
        aggrid_cols=aggrid_cols,
        height=height,
        enable_pagination=enable_pagination,
        page_size=page_size,
    )
    hidden_input_id = f"{grid_id}-clicked"
    return html.Div(
        children=[
            grid,
            dcc.Input(
                id=hidden_input_id,
                type="hidden",
                value="",
            ),
        ],
        **{
            "data-mrt-clickable": "1",
            "data-mrt-target":    hidden_input_id,
            "style":              {"width": "100%", "cursor": "pointer"},
        },
    )
