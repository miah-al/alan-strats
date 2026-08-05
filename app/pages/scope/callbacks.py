"""
app/pages/scope/callbacks.py — behaviour for the Scope page.

Importing this module registers its callbacks as a side effect, which is why
`__init__.py` imports it. Dropping that import silently unregisters the page's
interactivity.
"""
from __future__ import annotations

from dash import html, dcc, callback, Input, Output

from app import theme as T
from app.pages.scope.content import load_document
from app.pages.scope.layout import DOC_PICKER_ID, DOC_BODY_ID


@callback(
    Output(DOC_BODY_ID, "children"),
    Input(DOC_PICKER_ID, "value"),
)
def _render_document(path_str):
    """Render the selected markdown document."""
    return dcc.Markdown(
        load_document(path_str),
        className="guide-md",
        dangerously_allow_html=False,
        link_target="_blank",
        style={
            "color": T.TEXT_PRIMARY,
            "fontSize": "14px",
            "lineHeight": "1.7",
            "maxWidth": "1200px",
        },
    )
