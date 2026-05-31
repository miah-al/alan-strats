"""
app/pages/market/layout.py - the Market Data page view.

Builds every section (quote strip, price chart, options chain, vol surface,
activity, GEX, momentum, correlation, screener, futures). Adopts the shared
design system (app.ui) for the page header; every component id is identical
to the original monolithic market.py. Split verbatim.
"""
from __future__ import annotations

from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_ag_grid as dag

from app import theme as T, get_polygon_api_key
from app.ui import tokens as D, components as C
from app.pages.market.data import (
    _section, _pill, _hint, _scr_empty_fig, _SCR_CFG,
    _SCR_UNIVERSE_OPTIONS, _SCR_DEFAULT_UNIVERSE,
    _FUTURES_CATEGORIES, _fut_cell_style, _fmt_pct,
)
from app.pages.market.guides import (
    _gex_guide, _vol_surface_guide, _momentum_guide, _yield_guide,
)


def _build_futures_table(data: dict[str, dict]) -> html.Div:
    """Render the 4-category futures performance table."""
    _col_w = {"name": "180px", "last": "90px", "pct": "80px"}
    _hdr_style = {
        "color": T.TEXT_MUTED, "fontSize": "11px", "fontWeight": "700",
        "padding": "4px 10px", "textAlign": "right",
        "borderBottom": f"1px solid {T.BORDER}",
    }
    _cell_base = {"fontSize": "12px", "padding": "4px 10px", "whiteSpace": "nowrap"}

    def header_row() -> html.Tr:
        return html.Tr([
            html.Th("", style={**_hdr_style, "width": "90px", "textAlign": "left"}),
            html.Th("Contract",  style={**_hdr_style, "width": _col_w["name"], "textAlign": "left"}),
            html.Th("Last",  style={**_hdr_style, "width": _col_w["last"]}),
            html.Th("1D",    style={**_hdr_style, "width": _col_w["pct"]}),
            html.Th("5D",    style={**_hdr_style, "width": _col_w["pct"]}),
            html.Th("1M",    style={**_hdr_style, "width": _col_w["pct"]}),
            html.Th("YTD",   style={**_hdr_style, "width": _col_w["pct"]}),
        ])

    rows: list[html.Tr] = [header_row()]

    for cat in _FUTURES_CATEGORIES:
        cat_color = cat["color"]
        for i, (ticker, name) in enumerate(cat["tickers"]):
            d = data.get(ticker, {})
            last_v = d.get("last")
            last_s = f"${last_v:,.2f}" if last_v is not None else "—"

            cat_cell = html.Td(
                cat["label"] if i == 0 else "",
                style={
                    **_cell_base,
                    "color": cat_color, "fontWeight": "700", "fontSize": "11px",
                    "borderLeft": f"3px solid {cat_color}",
                    "verticalAlign": "middle", "textAlign": "left",
                },
            )
            name_cell = html.Td(
                name,
                style={**_cell_base, "color": T.TEXT_PRIMARY, "textAlign": "left"},
            )
            last_cell = html.Td(
                last_s,
                style={**_cell_base, "color": T.TEXT_PRIMARY, "textAlign": "right",
                       "fontWeight": "600"},
            )
            pct_cells = [
                html.Td(
                    _fmt_pct(d.get(col)),
                    style={**_cell_base, "textAlign": "right",
                           **_fut_cell_style(d.get(col), col)},
                )
                for col in ("1D", "5D", "1M", "YTD")
            ]

            row_style: dict = {}
            if i == 0 and rows:
                row_style["borderTop"] = f"1px solid {T.BORDER}"

            rows.append(html.Tr(
                [cat_cell, name_cell, last_cell] + pct_cells,
                style=row_style,
            ))

    return html.Div(
        html.Table(
            rows,
            style={"width": "100%", "borderCollapse": "collapse"},
        ),
        style={"overflowX": "auto"},
    )


def layout() -> html.Div:
    key_loaded = bool(get_polygon_api_key())
    return html.Div([
        C.page_header(
            "Market Data",
            actions=[
                dbc.Input(
                    id="mkt-apikey", type="password",
                    placeholder="API key loaded ✓" if key_loaded else "Polygon API key",
                    style={"fontSize": "12px", "width": "280px",
                           "backgroundColor": T.BG_ELEVATED,
                           "border": f"1px solid {'#10b981' if key_loaded else T.BORDER}",
                           "color": T.TEXT_PRIMARY},
                ),
                dbc.Input(id="mkt-ticker", type="text", value="F",
                          style={"fontSize": "12px", "width": "80px",
                                 "backgroundColor": T.BG_ELEVATED,
                                 "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY}),
                dbc.Button("Load", id="mkt-load-btn", color="primary", size="sm",
                           style={"backgroundColor": T.ACCENT, "border": "none", "fontSize": "12px"}),
            ],
        ),

        # Quote strip
        dcc.Loading(html.Div(id="mkt-quote-strip"), type="circle", color=T.ACCENT),
        html.Div(style={"height": "12px"}),

        # Charts — all rendered on Load click
        html.Div([
            html.Div([
                html.Div("Price Chart", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                dbc.Switch(
                    id="mkt-eod-toggle",
                    label="EOD History",
                    value=False,
                    style={"color": T.TEXT_MUTED, "fontSize": "12px"},
                ),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-candle-content",
                                 children=_hint("Loading…")),
                        type="circle", color=T.ACCENT),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
        html.Div([
            html.Div([
                html.Div("Dealer GEX — Gamma Exposure by Strike", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                dbc.Button("How to read this chart",
                           id="mkt-gex-guide-toggle",
                           size="sm", color="link",
                           style={"color": T.ACCENT, "fontSize": "11px",
                                  "padding": "0", "fontWeight": "500"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-gex-content", children=_hint("Loading…")),
                        type="circle", color=T.ACCENT),
            dbc.Collapse(_gex_guide(), id="mkt-gex-guide-collapse", is_open=False),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
        html.Div([
            html.Div([
                html.Div([
                    html.Div("Volatility Surface", style={
                        "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                        "textTransform": "uppercase", "letterSpacing": "0.07em",
                        "marginRight": "10px",
                    }),
                    html.Div([
                        dbc.Button("3D Surface", id="mkt-vol-3d-btn", size="sm",
                                   color="secondary", outline=True,
                                   style={"fontSize": "11px", "padding": "2px 10px",
                                          "borderRadius": "4px 0 0 4px"}),
                        dbc.Button("Chain Table", id="mkt-vol-chain-btn", size="sm",
                                   color="primary",
                                   style={"fontSize": "11px", "padding": "2px 10px",
                                          "borderRadius": "0 4px 4px 0"}),
                    ], style={"display": "flex"}),
                ], style={"display": "flex", "alignItems": "center"}),
                dbc.Button("How to read this chart", id="mkt-vol-guide-toggle",
                           size="sm", color="link",
                           style={"color": T.ACCENT, "fontSize": "11px",
                                  "padding": "0", "fontWeight": "500"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "8px"}),
            # Expiry + moneyness controls — shown only in chain view
            html.Div([
                html.Label("Expiry:", style={"color": T.TEXT_MUTED, "fontSize": "12px",
                                             "marginRight": "8px", "whiteSpace": "nowrap",
                                             "lineHeight": "32px"}),
                dbc.Select(id="mkt-chain-expiry", options=[], value=None,
                           placeholder="Loading expiries…",
                           style={"width": "220px", "fontSize": "12px",
                                  "backgroundColor": T.BG_ELEVATED,
                                  "color": T.TEXT_PRIMARY,
                                  "border": f"1px solid {T.BORDER}"}),
                html.Div(style={"width": "20px"}),
                html.Label("Show:", style={"color": T.TEXT_MUTED, "fontSize": "12px",
                                           "marginRight": "8px", "whiteSpace": "nowrap",
                                           "lineHeight": "32px"}),
                dbc.RadioItems(
                    id="mkt-chain-moneyness",
                    options=[
                        {"label": "All",  "value": "all"},
                        {"label": "ITM",  "value": "itm"},
                        {"label": "OTM",  "value": "otm"},
                        {"label": "±10%", "value": "near"},
                    ],
                    value="all", inline=True,
                    inputStyle={"marginRight": "4px"},
                    labelStyle={"marginRight": "14px", "fontSize": "12px",
                                "color": T.TEXT_SEC, "cursor": "pointer"},
                ),
            ], id="mkt-chain-expiry-row",
               style={"display": "flex", "alignItems": "center",
                      "marginBottom": "10px"}),
            dcc.Loading(html.Div(id="mkt-vol-content", children=_hint("Loading…")),
                        type="circle", color=T.ACCENT),
            dbc.Collapse(_vol_surface_guide(), id="mkt-vol-guide-collapse", is_open=False),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
        _section("Market Activity — Top Movers & Dealer GEX",
                 dcc.Loading(html.Div(id="mkt-activity-content",
                                      children=_hint("Loading…")),
                             type="circle", color=T.ACCENT)),
        html.Div([
            html.Div([
                html.Div("Momentum Indicators — RSI & MACD", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                dbc.Button("How to read this chart", id="mkt-momentum-guide-toggle",
                           size="sm", color="link",
                           style={"color": T.ACCENT, "fontSize": "11px",
                                  "padding": "0", "fontWeight": "500"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-momentum-content", children=_hint("Loading…")),
                        type="circle", color=T.ACCENT),
            dbc.Collapse(_momentum_guide(), id="mkt-momentum-guide-collapse", is_open=False),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),
        _section("Correlation Analysis", html.Div([
            html.Div([
                html.Label("Compare with:", style={"color": T.TEXT_SEC, "fontSize": "12px",
                                                   "marginRight": "8px"}),
                dbc.Input(id="mkt-corr-ticker", type="text", value="QQQ",
                          style={"width": "80px", "fontSize": "12px",
                                 "backgroundColor": T.BG_ELEVATED,
                                 "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY}),
                dbc.Button("Run Correlation", id="mkt-corr-run", color="secondary", size="sm",
                           style={"marginLeft": "8px", "fontSize": "12px",
                                  "border": f"1px solid {T.BORDER}"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-corr-content"), type="circle", color=T.ACCENT),
        ])),

        html.Div([
            html.Div([
                html.Div("Treasury Term Structure — Yield Curve & 3D Surface (FRED, free)", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                dbc.Button("How to read this chart", id="mkt-yield-guide-toggle",
                           size="sm", color="link",
                           style={"color": T.ACCENT, "fontSize": "11px",
                                  "padding": "0", "fontWeight": "500"}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "12px"}),
            dcc.Loading(html.Div(id="mkt-yield-content", children=_hint("Loading…")),
                        type="circle", color=T.ACCENT),
            dbc.Collapse(_yield_guide(), id="mkt-yield-guide-collapse", is_open=False),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),

        # ── Global Futures ───────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div("Global Futures — Performance Overview", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                html.Div(
                    html.Small("via Yahoo Finance · delayed", style={
                        "color": T.TEXT_MUTED, "fontSize": "10px",
                    }),
                    style={"display": "flex", "alignItems": "center", "gap": "10px"},
                ),
                dbc.Button("↻ Refresh", id="mkt-futures-refresh-btn", size="sm",
                           color="secondary",
                           style={"fontSize": "11px", "padding": "2px 10px",
                                  "border": f"1px solid {T.BORDER}",
                                  "backgroundColor": T.BG_ELEVATED}),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                      "paddingBottom": "8px", "marginBottom": "12px"}),
            dcc.Loading(
                html.Div(id="mkt-futures-content", children=_hint("Click ↻ Refresh to load futures data.")),
                type="circle", color=T.ACCENT,
            ),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),

        # ── Market Screener ───────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Div("Market Screener", style={
                    "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.07em",
                }),
                html.Div(
                    [dbc.Button(
                        opt["label"],
                        id={"type": "scr-univ-btn", "index": opt["value"]},
                        size="sm",
                        style={
                            "fontSize": "12px", "fontWeight": "500",
                            "padding": "4px 12px",
                            "backgroundColor": T.ACCENT if opt["value"] == _SCR_DEFAULT_UNIVERSE else T.BG_ELEVATED,
                            "border": f"1px solid {T.ACCENT if opt['value'] == _SCR_DEFAULT_UNIVERSE else T.BORDER}",
                            "color": T.TEXT_PRIMARY,
                            "borderRadius": "6px",
                        },
                    ) for opt in _SCR_UNIVERSE_OPTIONS],
                    style={"display": "flex", "gap": "6px"},
                ),
                dcc.Store(id="mkt-scr-universe", data=_SCR_DEFAULT_UNIVERSE),
            ], style={
                "display": "flex", "justifyContent": "space-between",
                "alignItems": "center",
                "borderBottom": f"1px solid {T.BORDER}",
                "paddingBottom": "8px", "marginBottom": "16px",
            }),

            dcc.Loading(type="circle", color=T.ACCENT, children=html.Div([
                # Row 1: Movers full width
                html.Div([
                    html.Div("Movers", style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                              "fontWeight": "600", "marginBottom": "6px",
                                              "borderLeft": f"3px solid {T.ACCENT}",
                                              "paddingLeft": "8px"}),
                    dcc.Graph(id="mkt-scr-movers-fig", figure=_scr_empty_fig(),
                              config=_SCR_CFG),
                ], style={"marginBottom": "16px"}),
                # Row 2: Momentum | Volatility
                html.Div([
                    html.Div([
                        html.Div("Momentum — top 15 by absolute 20d return",
                                 style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                        "fontWeight": "600", "marginBottom": "6px",
                                        "borderLeft": f"3px solid {T.ACCENT}",
                                        "paddingLeft": "8px"}),
                        dcc.Graph(id="mkt-scr-mom-fig", figure=_scr_empty_fig(),
                                  config=_SCR_CFG, style={"height": "420px"}),
                    ]),
                    html.Div([
                        html.Div("Volatility — HV20 vs IV (amber = IV > 1.5× HV)",
                                 style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                        "fontWeight": "600", "marginBottom": "6px",
                                        "borderLeft": f"3px solid {T.ACCENT}",
                                        "paddingLeft": "8px"}),
                        dcc.Graph(id="mkt-scr-vol-fig", figure=_scr_empty_fig(),
                                  config=_SCR_CFG, style={"height": "420px"}),
                    ]),
                ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr",
                          "gap": "16px", "marginBottom": "16px"}),
                # Row 3: Volume Alerts
                html.Div([
                    html.Div("Volume Alerts — today vs 20-day average",
                             style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                    "fontWeight": "600", "marginBottom": "6px",
                                    "borderLeft": f"3px solid {T.ACCENT}",
                                    "paddingLeft": "8px"}),
                    dcc.Graph(id="mkt-scr-volalert-fig", figure=_scr_empty_fig(),
                              config=_SCR_CFG),
                ]),
            ])),
        ], style={**T.STYLE_CARD, "marginBottom": "16px"}),

        dcc.Store(id="mkt-ticker-store",    data="F"),
        dcc.Store(id="mkt-apikey-store",    data=get_polygon_api_key()),
        dcc.Store(id="mkt-vol-view-store",  data="chain"),
        dcc.Store(id="mkt-chain-data-store"),
    ], style=T.STYLE_PAGE)
