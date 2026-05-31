"""
app/pages/tools/layout.py -- top-level Tools page layout.

The dbc.Tabs shell + the pre-rendered first tab in #tools-tab-content. The tab
routing callback lives in callbacks.py. All component ids match the original.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from app import theme as T
from app.ui import tokens as D, components as C

from app.pages.tools.tabs import _data_manager_tab


_TAB_STYLE     = {"fontSize": D.TEXT_MD, "padding": "6px 14px"}
_TAB_ACT_STYLE = {**_TAB_STYLE, "borderTop": f"2px solid {D.COLOR.accent}"}


def layout() -> html.Div:
    return html.Div([
        C.page_header(
            "Tools",
            "Data syncing, IV metrics, portfolio risk, the strategy registry, "
            "models, the quant course, guides, and the Polygon explorer.",
        ),
        dbc.Tabs(
            [
                dbc.Tab(label="Data Manager",     tab_id="data-manager",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(label="IV Metrics",       tab_id="iv-metrics",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(label="Risk",             tab_id="risk",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(label="Registry",         tab_id="registry",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(label="Models",           tab_id="models",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(label="Quant Course",     tab_id="course",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(label="Guide",            tab_id="guide",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(label="Polygon Explorer", tab_id="polygon-explorer",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
            ],
            id="tools-tabs",
            active_tab="data-manager",
            style={"marginBottom": "0"},
        ),
        # Pre-render the first tab so it shows instantly; other tabs lazy-load
        # via the callback below on first click.
        html.Div(_data_manager_tab(), id="tools-tab-content"),
    ], style=T.STYLE_PAGE)
