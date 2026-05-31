"""
dash_app/pages/course/layout.py — the Quant Course view.

Builds the sidebar (chapter nav + print buttons) and the reading pane. Uses the
shared design system (dash_app.ui) for the page header and surface tokens so it
matches every other page; chapter-specific bits stay local.
"""
from __future__ import annotations

from pathlib import Path

import dash_bootstrap_components as dbc
from dash import html, dcc

from dash_app import theme as T
from dash_app.ui import tokens as D, components as C
from dash_app.pages.course.content import (
    grouped_chapter_options, figure_count, _GUIDE_DIR,
)


def _sidebar() -> html.Div:
    groups = grouped_chapter_options()
    default = groups[0][1][0]["value"] if groups and groups[0][1] else None
    readme_exists = (_GUIDE_DIR / "README.md").is_file()

    part_blocks = [
        html.Div([
            html.Div(part_name, style={
                "color": D.COLOR.accent, "fontSize": "10.5px",
                "fontWeight": D.WEIGHT_BOLD, "letterSpacing": "0.06em",
                "textTransform": "uppercase",
                "marginTop": D.SPACE_3 if idx > 0 else "0",
                "marginBottom": D.SPACE_1,
            }),
            dbc.RadioItems(
                id={"type": "course-chapter-part", "part": idx},
                options=part_opts,
                value=default if (idx == 0 and part_opts
                                  and part_opts[0]["value"] == default) else None,
                className="course-chapter-list",
                labelStyle={
                    "display": "block", "color": D.COLOR.text, "fontSize": D.TEXT_MD,
                    "padding": "6px 10px", "borderRadius": D.RADIUS_SM,
                    "cursor": "pointer", "marginBottom": "1px",
                },
                inputStyle={"display": "none"},
            ),
        ])
        for idx, (part_name, part_opts) in enumerate(groups)
    ]

    return html.Div([
        html.Div("Quant Course", style={
            "color": D.COLOR.accent, "fontSize": D.TEXT_XS, "fontWeight": D.WEIGHT_BOLD,
            "letterSpacing": "0.08em", "textTransform": "uppercase",
            "marginBottom": D.SPACE_2}),
        dbc.Button("📖 Overview (README)", id="course-overview-btn",
                   color="secondary", outline=True, size="sm", className="w-100 mb-2",
                   style={"fontSize": D.TEXT_SM, "textAlign": "left"},
                   disabled=not readme_exists),
        dbc.Button("📄 Print this chapter (fast)", id="course-print-one-btn",
                   color="primary", outline=True, size="sm", className="w-100 mb-2",
                   style={"fontSize": D.TEXT_SM, "textAlign": "left"},
                   external_link=True, target="_blank"),
        dbc.Button("📚 Full guide (slow: ~3 min MathJax)", id="course-print-btn",
                   color="secondary", outline=True, size="sm", className="w-100 mb-3",
                   style={"fontSize": D.TEXT_XS, "textAlign": "left"},
                   href="/course/print", external_link=True, target="_blank"),
        *part_blocks,
        dcc.Store(id="course-chapter", data=default),
        html.Div([
            html.Hr(style={"borderColor": D.COLOR.border, "margin": "14px 0 10px"}),
            html.Div(f"📊 {figure_count()} figures",
                     style={"color": D.COLOR.text_muted, "fontSize": D.TEXT_XS}),
        ]),
        dcc.Store(id="course-show-overview", data=False),
    ], style={**D.CARD, "marginBottom": "0", "position": "sticky", "top": "20px"})


def _main() -> html.Div:
    return html.Div([
        dcc.Loading(
            html.Div(id="course-content", className="guide-md",
                     style={"color": D.COLOR.text, "fontSize": "14px",
                            "lineHeight": "1.75", "minHeight": "400px"}),
            type="circle", color=D.COLOR.accent,
        ),
    ], style={**D.CARD})


def layout() -> html.Div:
    return html.Div([
        C.page_header(
            "Quant Course",
            "16-chapter study guide on arbitrage pricing, stochastic-vol, "
            "short-rate models and rate derivatives.",
        ),
        dbc.Row([
            dbc.Col(_sidebar(), md=3),
            dbc.Col(_main(), md=9),
        ]),
    ], style=D.PAGE)
