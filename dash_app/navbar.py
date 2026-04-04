"""
dash_app/navbar.py
Left-side navigation sidebar component.
"""
import dash_bootstrap_components as dbc
from dash import html

from dash_app import theme as T

NAV_ITEMS = [
    ("Blotter",       "🏠", "/"),
    ("Paper Trading", "📋", "/paper-trading"),
    ("Market Data",   "📈", "/market"),
    ("Screener",      "🔍", "/screener"),
    ("Strategies",    "🧠", "/strategies"),
    ("Backtest",      "📊", "/backtest"),
    ("Tools",         "🛠",  "/tools"),
]


def build_sidebar() -> html.Div:
    brand = html.Div(
        [
            html.Div("📈", style={
                "width": "32px", "height": "32px", "borderRadius": "8px",
                "background": "linear-gradient(135deg,#6366f1,#4f46e5)",
                "display": "flex", "alignItems": "center",
                "justifyContent": "center", "fontSize": "16px", "flexShrink": "0",
            }),
            html.Div([
                html.Div("Project Dream", style={
                    "color": T.TEXT_PRIMARY, "fontSize": "15px",
                    "fontWeight": "700", "lineHeight": "1.2",
                }),
                html.Div("v2 · Dash", style={
                    "color": T.TEXT_MUTED, "fontSize": "10px",
                    "fontWeight": "500", "letterSpacing": "0.06em",
                }),
            ]),
        ],
        style={"display": "flex", "alignItems": "center", "gap": "10px",
               "padding": "18px 16px 14px",
               "borderBottom": f"1px solid {T.BORDER}", "marginBottom": "8px"},
    )

    links = [
        dbc.NavLink(
            [html.Span(icon, style={"marginRight": "9px", "fontSize": "13px"}),
             html.Span(label)],
            href=href,
            active="exact",
            style={
                "color": T.TEXT_SEC, "padding": "8px 14px",
                "borderRadius": "6px", "marginBottom": "2px",
                "fontSize": "13px", "fontWeight": "500",
                "display": "flex", "alignItems": "center",
            },
        )
        for label, icon, href in NAV_ITEMS
    ]

    return html.Div(
        [brand, dbc.Nav(links, vertical=True, pills=True)],
        style={
            "width":           T.SIDEBAR_WIDTH,
            "minHeight":       "100vh",
            "backgroundColor": T.SIDEBAR_BG,
            "borderRight":     f"1px solid {T.BORDER}",
            "padding":         "0 8px 24px",
            "position":        "fixed",
            "top": "0", "left": "0",
            "overflowY":       "auto",
            "zIndex":          "100",
        },
    )
