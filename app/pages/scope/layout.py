"""
app/pages/scope/layout.py — presentation for the Scope page.

Layout only: builds the component tree and owns no data access or callback
logic. Content comes from `content.py`, behaviour from `callbacks.py`.
"""
from __future__ import annotations

from dash import html, dcc

from app import theme as T
from app.ui import components as C
from app.pages.scope.content import document_options, default_document

DOC_PICKER_ID = "scope-doc-picker"
DOC_BODY_ID = "scope-doc-body"


def layout() -> html.Div:
    options = document_options()

    picker = dcc.Dropdown(
        id=DOC_PICKER_ID,
        options=options,
        value=default_document(),
        clearable=False,
        style={"width": "420px", "fontSize": "13px"},
    )

    if not options:
        body = C.card([
            html.Div("No documents found.", style={
                "color": T.TEXT_SEC, "fontSize": "14px", "marginBottom": "6px",
            }),
            html.Div(
                "Expected docs/strategy_scope.md or reports under docs/reviews/.",
                style={"color": T.TEXT_MUTED, "fontSize": "12px"},
            ),
        ], pad="lg")
    else:
        body = C.card([
            dcc.Loading(
                html.Div(id=DOC_BODY_ID, className="guide-md"),
                type="default",
                color=T.ACCENT,
            ),
        ], pad="lg")

    return html.Div([
        C.page_header(
            "Scope",
            "What each strategy is, what it actually earned on real data, "
            "and whether it is worth deploying",
            actions=[picker] if options else None,
        ),
        body,
    ])
