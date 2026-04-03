"""
dash_app/pages/tools.py — stub placeholder for Phase 3.
"""
import dash_bootstrap_components as dbc
from dash import html

from dash_app import theme as T

_TITLE = "Tools"


def layout() -> html.Div:
    return html.Div(
        [
            html.H2(_TITLE, style={
                "color": T.TEXT_PRIMARY, "fontSize": "1.35rem",
                "fontWeight": "700", "marginBottom": "16px",
            }),
            dbc.Card(
                dbc.CardBody(
                    html.P(
                        f"{_TITLE} — coming in Phase 3.",
                        style={"color": T.TEXT_MUTED, "fontSize": "14px"},
                    )
                ),
                style=T.STYLE_CARD,
            ),
        ],
        style=T.STYLE_PAGE,
    )
