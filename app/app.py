"""
app/app.py
AlanTrader — Dash frontend (Phase 2 skeleton).

Run from the alan_trader/ directory:
    python app/app.py

Or from the project root (d:/Work/ClaudeCodeTest/):
    python -m alan_trader.app.app
"""
from __future__ import annotations

import os
import sys

# ── Path bootstrap ────────────────────────────────────────────────────────────
# This file: alan_trader/app/app.py
# We need the alan_trader/ directory on sys.path so that
# engine/, db/, app/ etc. are all importable as top-level packages.
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

from app import theme as T
from app.navbar import build_sidebar
from app.pages.broker import build_broker_panel, BROKER_WIDTH

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
# NOTE: use `from app.pages import X`, NOT `import app.pages.X`. The latter binds
# the name `app` in this module's namespace to the *package* `app`, shadowing the
# local `app = Dash(...)` instance above and breaking `@app.callback` below (the
# package has no `.callback`). The `from ... import` form binds only the submodule.
from app.pages import (  # noqa: F401  (imported for callback-registration side effects)
    paper_trading as _pg_paper_trading,
    market as _pg_market,
    strategies as _pg_strategies,
    tools as _pg_tools,
    models as _pg_models,
    course as _pg_course,
    broker as _pg_broker,  # registers broker panel callbacks
)

# ── Routing ───────────────────────────────────────────────────────────────────
@app.callback(Output("page-content", "children"), Input("url", "pathname"))
def render_page(pathname: str):
    try:
        if pathname in (None, "/", "/paper-trading"):
            from app.pages.paper_trading import layout
            return layout()
        if pathname == "/market":
            from app.pages.market import layout
            return layout()
        if pathname == "/strategies":
            from app.pages.strategies import layout
            return layout()
        if pathname == "/tools":
            from app.pages.tools import layout
            return layout()
        if pathname == "/models":
            from app.pages.models import layout
            return layout()
        if pathname == "/course":
            from app.pages.course import layout
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
