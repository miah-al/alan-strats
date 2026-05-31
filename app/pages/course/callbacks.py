"""
app/pages/course/callbacks.py — Quant Course interactivity.

Importing this module registers all four callbacks with Dash (the @callback
decorator runs at import). The package __init__ imports it for that side effect,
so callbacks vanish if that import is removed — keep it.
"""
from __future__ import annotations

from dash import html, dcc, callback, Input, Output, no_update, ALL, ctx

from app import theme as T
from app.ui import tokens as D
from app.pages.course.content import (
    _GUIDE_DIR, rewrite_figure_paths, convert_math_fences,
)


@callback(
    Output("course-print-one-btn", "href"),
    Input("course-chapter", "data"),
    prevent_initial_call=False,
)
def _print_one_href(chapter_slug):
    return f"/course/print?chapter={chapter_slug}" if chapter_slug else "/course/print"


@callback(
    Output("course-chapter", "data"),
    Input({"type": "course-chapter-part", "part": ALL}, "value"),
    prevent_initial_call=True,
)
def _route_part_clicks(values):
    # Whichever Part's RadioItems was just clicked carries the new chapter slug.
    if not ctx.triggered:
        return no_update
    picked = next((v for v in values if v), None)
    return picked or no_update


@callback(
    Output("course-show-overview", "data"),
    Input("course-overview-btn", "n_clicks"),
    Input("course-chapter", "data"),
    prevent_initial_call=False,
)
def _toggle_overview(n, chapter_change):
    # Any chapter change resets to chapter mode; the overview button forces it on.
    if ctx.triggered_id == "course-overview-btn":
        return True
    return False


@callback(
    Output("course-content", "children"),
    Input("course-chapter", "data"),
    Input("course-show-overview", "data"),
)
def _render(chapter_slug, show_overview):
    if show_overview:
        p = _GUIDE_DIR / "README.md"
    elif chapter_slug:
        p = _GUIDE_DIR / f"{chapter_slug}.md"
    else:
        return html.Div("Select a chapter", style={"color": D.COLOR.text_muted})

    if not p.is_file():
        return html.Div(f"Not found: {p.name}", style={"color": D.COLOR.danger})

    content = convert_math_fences(rewrite_figure_paths(p.read_text(encoding="utf-8")))
    return dcc.Markdown(
        content, mathjax=True, className="guide-md",
        style={"color": D.COLOR.text, "fontSize": "14px", "lineHeight": "1.75"},
    )
