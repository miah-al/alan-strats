"""
dash_app/app.py
AlanTrader — Dash frontend (Phase 2 skeleton).

Run from the alan_trader/ directory:
    python dash_app/app.py

Or from the project root (d:/Work/ClaudeCodeTest/):
    python -m alan_trader.dash_app.app
"""
from __future__ import annotations

import os
import sys

# ── Path bootstrap ────────────────────────────────────────────────────────────
# This file: alan_trader/dash_app/app.py
# We need the alan_trader/ directory on sys.path so that
# engine/, db/, dash_app/ etc. are all importable as top-level packages.
_HERE   = os.path.dirname(os.path.abspath(__file__))
_ROOT   = os.path.dirname(_HERE)          # alan_trader/
_PARENT = os.path.dirname(_ROOT)          # ClaudeCodeTest/ (needed for alan_trader.* imports)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import dash
import dash_bootstrap_components as dbc
from dash import Dash, html, dcc, Input, Output

from dash_app import theme as T
from dash_app.navbar import build_sidebar
from dash_app.pages.broker import build_broker_panel, BROKER_WIDTH

# ── App ───────────────────────────────────────────────────────────────────────
app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap",
    ],
    suppress_callback_exceptions=True,
    title="Project Dream",
    update_title=None,
)
server = app.server  # WSGI entry point for production

# ── Layout ────────────────────────────────────────────────────────────────────
app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        build_sidebar(),
        build_broker_panel(),
        # Global busy indicator — shown by assets/busy_indicator.js during callbacks.
        html.Div(
            [
                html.Div(className="app-busy-dot"),
                html.Span("Working", className="app-busy-text"),
            ],
            id="app-busy-indicator",
        ),
        html.Div(
            id="page-content",
            style={
                "marginLeft":      T.SIDEBAR_WIDTH,
                "marginRight":     BROKER_WIDTH,
                "backgroundColor": T.BG_BASE,
                "minHeight":       "100vh",
                "color":           T.TEXT_PRIMARY,
            },
        ),
    ],
    style={"backgroundColor": T.BG_BASE, "fontFamily": "'Inter', sans-serif"},
)

# ── Pre-import all page modules so callbacks register at startup ──────────────
import dash_app.pages.paper_trading
import dash_app.pages.market
import dash_app.pages.strategies
import dash_app.pages.tools
import dash_app.pages.models
import dash_app.pages.course
import dash_app.pages.broker  # registers broker panel callbacks

# ── Routing ───────────────────────────────────────────────────────────────────
@app.callback(Output("page-content", "children"), Input("url", "pathname"))
def render_page(pathname: str):
    try:
        if pathname in (None, "/", "/paper-trading"):
            from dash_app.pages.paper_trading import layout
            return layout()
        if pathname == "/market":
            from dash_app.pages.market import layout
            return layout()
        if pathname == "/strategies":
            from dash_app.pages.strategies import layout
            return layout()
        if pathname == "/tools":
            from dash_app.pages.tools import layout
            return layout()
        if pathname == "/models":
            from dash_app.pages.models import layout
            return layout()
        if pathname == "/course":
            from dash_app.pages.course import layout
            return layout()
        return html.Div(
            [
                html.H3("404 — Page not found", style={"color": T.DANGER}),
                dcc.Link("← Paper Trading", href="/paper-trading",
                         style={"color": T.ACCENT}),
            ],
            style={**T.STYLE_PAGE},
        )
    except Exception as _e:
        import traceback
        return html.Div([
            html.H3("Page Error", style={"color": T.DANGER}),
            html.Pre(traceback.format_exc(),
                     style={"color": T.TEXT_SEC, "fontSize": "12px",
                            "background": T.BG_CARD, "padding": "12px",
                            "borderRadius": "6px", "overflowX": "auto"}),
        ], style=T.STYLE_PAGE)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8051, threaded=True, use_reloader=False)
