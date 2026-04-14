"""
dash_app/pages/broker.py
Right-panel broker integration: RobinHood + Webull.
Credentials sourced from environment variables.
"""
from __future__ import annotations

import os

import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback

from dash_app import theme as T

# ── Constants ─────────────────────────────────────────────────────────────────
_RH_USER = "ROBINHOOD_USERNAME"
_RH_PASS = "ROBINHOOD_PASSWORD"
_RH_MFA  = "ROBINHOOD_MFA_CODE"
_WB_USER = "WEBULL_EMAIL"
_WB_PASS = "WEBULL_PASSWORD"
_WB_MFA  = "WEBULL_MFA_CODE"

BROKER_WIDTH = "240px"


# ═══════════════════════════════════════════════════════════════════════════════
# Availability helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _rh_configured() -> bool:
    return bool(os.environ.get(_RH_USER) and os.environ.get(_RH_PASS))

def _wb_configured() -> bool:
    return bool(os.environ.get(_WB_USER) and os.environ.get(_WB_PASS))

def _rh_available() -> bool:
    try:
        import robin_stocks  # noqa: F401
        return _rh_configured()
    except ImportError:
        return False

def _wb_available() -> bool:
    try:
        import webull  # noqa: F401
        return _wb_configured()
    except ImportError:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Data fetchers — RobinHood
# ═══════════════════════════════════════════════════════════════════════════════

def _rh_fetch_account() -> dict:
    try:
        import robin_stocks.robinhood as rh
        rh.login(
            os.environ[_RH_USER], os.environ[_RH_PASS],
            mfa_code=os.environ.get(_RH_MFA), store_session=True,
        )
        profile   = rh.profiles.load_account_profile()
        portfolio = rh.profiles.load_portfolio_profile()
        rh.authentication.logout()
        return {
            "equity":       float(portfolio.get("equity", 0) or 0),
            "cash":         float(profile.get("cash", 0) or 0),
            "buying_power": float(profile.get("buying_power", 0) or 0),
        }
    except Exception as e:
        return {"error": str(e)}


def _rh_fetch_positions() -> list[dict]:
    try:
        import robin_stocks.robinhood as rh
        rh.login(
            os.environ[_RH_USER], os.environ[_RH_PASS],
            mfa_code=os.environ.get(_RH_MFA), store_session=True,
        )
        raw     = rh.account.get_open_stock_positions()
        tickers = rh.stocks.get_symbols_by_url([p["instrument"] for p in raw])
        rh.authentication.logout()
        rows = []
        for pos, sym in zip(raw, tickers):
            qty = float(pos.get("quantity", 0))
            avg = float(pos.get("average_buy_price", 0))
            if qty > 0:
                rows.append({"ticker": sym, "qty": qty, "avg_cost": avg})
        return rows
    except Exception as e:
        return [{"error": str(e)}]


# ═══════════════════════════════════════════════════════════════════════════════
# Data fetchers — Webull
# ═══════════════════════════════════════════════════════════════════════════════

def _wb_fetch_account() -> dict:
    try:
        from webull import webull as Webull
        wb = Webull()
        wb.login(
            username=os.environ[_WB_USER],
            password=os.environ[_WB_PASS],
            save_token=True,
            mfa=os.environ.get(_WB_MFA, ""),
        )
        acct = wb.get_account()
        wb.logout()
        return {
            "equity":       float(acct.get("netLiquidation", 0) or 0),
            "cash":         float(acct.get("cashBalance", 0) or 0),
            "buying_power": float(acct.get("dayBuyingPower", 0) or 0),
        }
    except Exception as e:
        return {"error": str(e)}


def _wb_fetch_positions() -> list[dict]:
    try:
        from webull import webull as Webull
        wb = Webull()
        wb.login(
            username=os.environ[_WB_USER],
            password=os.environ[_WB_PASS],
            save_token=True,
            mfa=os.environ.get(_WB_MFA, ""),
        )
        positions = wb.get_positions()
        wb.logout()
        rows = []
        for p in (positions or []):
            qty = float(p.get("position", 0))
            avg = float(p.get("costPrice", 0))
            sym = p.get("ticker", {}).get("symbol", "?")
            if qty != 0:
                rows.append({"ticker": sym, "qty": qty, "avg_cost": avg})
        return rows
    except Exception as e:
        return [{"error": str(e)}]


# ═══════════════════════════════════════════════════════════════════════════════
# UI helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _dot(color: str) -> html.Span:
    return html.Span(style={
        "display": "inline-block", "width": "8px", "height": "8px",
        "borderRadius": "50%", "backgroundColor": color,
        "marginRight": "6px", "verticalAlign": "middle",
    })


def _section_label(text: str) -> html.Div:
    return html.Div(text, style={
        "color": T.TEXT_MUTED, "fontSize": "9px", "fontWeight": "700",
        "letterSpacing": "0.08em", "textTransform": "uppercase",
        "marginBottom": "6px", "marginTop": "10px",
    })


def _kv(label: str, value: str) -> html.Div:
    return html.Div([
        html.Span(label, style={"color": T.TEXT_MUTED, "fontSize": "11px"}),
        html.Span(value, style={"color": T.TEXT_PRIMARY, "fontSize": "12px",
                                "fontWeight": "600", "float": "right"}),
    ], style={"marginBottom": "4px", "overflow": "hidden"})


def _broker_status_row(name: str, configured: bool, lib_ok: bool,
                       lib_name: str) -> html.Div:
    if lib_ok:
        color, note = T.SUCCESS, "Ready"
    elif configured:
        color, note = T.WARNING, f"pip install {lib_name}"
    else:
        color, note = T.TEXT_MUTED, "Not configured"
    return html.Div([
        html.Div([
            _dot(color),
            html.Span(name, style={"color": T.TEXT_PRIMARY, "fontSize": "12px",
                                   "fontWeight": "600"}),
        ]),
        html.Div(note, style={"color": color, "fontSize": "10px",
                              "marginLeft": "14px"}),
    ], style={"marginBottom": "8px"})


def _positions_table(rows: list[dict]) -> html.Div:
    if not rows:
        return html.Div("No open positions.", style={"color": T.TEXT_MUTED,
                                                     "fontSize": "11px"})
    if "error" in rows[0]:
        return html.Div(rows[0]["error"][:100], style={"color": T.DANGER,
                                                        "fontSize": "9px",
                                                        "wordBreak": "break-all"})
    th = {"color": T.TEXT_MUTED, "fontSize": "9px", "fontWeight": "700",
          "textTransform": "uppercase", "letterSpacing": "0.05em",
          "borderBottom": f"1px solid {T.BORDER}", "paddingBottom": "4px",
          "paddingRight": "4px"}
    td = {"color": T.TEXT_PRIMARY, "fontSize": "11px",
          "borderBottom": f"1px solid {T.BORDER}", "padding": "3px 4px 3px 0"}
    return html.Table([
        html.Thead(html.Tr([
            html.Th("Symbol", style={**th, "width": "45%"}),
            html.Th("Qty",    style={**th, "width": "20%", "textAlign": "right"}),
            html.Th("Avg",    style={**th, "width": "35%", "textAlign": "right"}),
        ])),
        html.Tbody([
            html.Tr([
                html.Td(r["ticker"], style={**td, "fontWeight": "600"}),
                html.Td(f"{r['qty']:.0f}", style={**td, "textAlign": "right"}),
                html.Td(f"${r['avg_cost']:.2f}", style={**td, "textAlign": "right",
                                                         "color": T.TEXT_SEC}),
            ]) for r in rows
        ]),
    ], style={"width": "100%", "borderCollapse": "collapse"})


def _account_panel(data: dict, broker_label: str) -> html.Div:
    if "error" in data:
        return html.Div([
            html.Div("Connection error:", style={"color": T.DANGER,
                                                  "fontSize": "10px",
                                                  "fontWeight": "600",
                                                  "marginTop": "10px"}),
            html.Div(data["error"][:120], style={"color": T.TEXT_MUTED,
                                                  "fontSize": "9px",
                                                  "wordBreak": "break-all"}),
        ])
    return html.Div([
        _section_label(f"{broker_label} Account"),
        _kv("Net Liq",      f"${data['equity']:,.0f}"),
        _kv("Cash",         f"${data['cash']:,.0f}"),
        _kv("Buying Power", f"${data['buying_power']:,.0f}"),
    ], style={"marginTop": "10px"})


def _setup_help() -> html.Div:
    code_style = {
        "color": T.TEXT_MUTED, "fontSize": "9px",
        "backgroundColor": T.BG_CARD, "padding": "6px",
        "borderRadius": "4px", "overflowX": "auto",
        "whiteSpace": "pre-wrap", "margin": "0 0 8px 0",
    }
    return html.Div([
        _section_label("Setup"),
        html.Div("Set env vars to connect:", style={"color": T.TEXT_MUTED,
                                                     "fontSize": "10px",
                                                     "marginBottom": "6px"}),
        html.Div("RobinHood", style={"color": T.TEXT_SEC, "fontSize": "10px",
                                     "fontWeight": "600", "marginBottom": "2px"}),
        html.Pre("pip install robin_stocks\n"
                 "ROBINHOOD_USERNAME=...\n"
                 "ROBINHOOD_PASSWORD=...\n"
                 "ROBINHOOD_MFA_CODE=...",
                 style=code_style),
        html.Div("Webull", style={"color": T.TEXT_SEC, "fontSize": "10px",
                                   "fontWeight": "600", "marginBottom": "2px"}),
        html.Pre("pip install webull\n"
                 "WEBULL_EMAIL=...\n"
                 "WEBULL_PASSWORD=...\n"
                 "WEBULL_MFA_CODE=...",
                 style=code_style),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# Panel layout — IDs always in DOM
# ═══════════════════════════════════════════════════════════════════════════════

def build_broker_panel() -> html.Div:
    rh_ok  = _rh_available()
    wb_ok  = _wb_available()
    rh_cfg = _rh_configured()
    wb_cfg = _wb_configured()
    any_ok = rh_ok or wb_ok

    opts = []
    if rh_ok:
        opts.append({"label": "RobinHood", "value": "rh"})
    if wb_ok:
        opts.append({"label": "Webull", "value": "wb"})
    default_broker = opts[0]["value"] if opts else None

    return html.Div(
        id="broker-panel",
        children=[
            # Header
            html.Div(
                html.Div("BROKER", style={
                    "color": T.TEXT_PRIMARY, "fontSize": "11px",
                    "fontWeight": "700", "letterSpacing": "0.1em",
                }),
                style={
                    "padding": "14px 12px 10px",
                    "borderBottom": f"1px solid {T.BORDER}",
                    "marginBottom": "4px",
                },
            ),

            html.Div([
                # Status dots
                _section_label("Status"),
                _broker_status_row("RobinHood", rh_cfg, rh_ok, "robin_stocks"),
                _broker_status_row("Webull",    wb_cfg, wb_ok, "webull"),

                # Broker selector — always in DOM (callback uses State on it)
                html.Div([
                    _section_label("Active Broker"),
                    dcc.Dropdown(
                        id="broker-select",
                        options=opts,
                        value=default_broker,
                        clearable=False,
                        style={**T.STYLE_DROPDOWN, "fontSize": "11px"},
                    ),
                ], style={"display": "block" if len(opts) > 1 else "none"}),

                # Refresh button — always in DOM
                html.Button(
                    "↻ Refresh",
                    id="broker-refresh-btn",
                    n_clicks=0,
                    style={
                        "width": "100%", "marginTop": "10px",
                        "backgroundColor": T.ACCENT if any_ok else T.TEXT_MUTED,
                        "color": "#fff", "border": "none",
                        "borderRadius": "5px", "padding": "5px",
                        "fontSize": "11px", "cursor": "pointer" if any_ok else "default",
                        "fontWeight": "600",
                        "display": "block" if any_ok else "none",
                    },
                ),

                # Content area
                dcc.Loading(
                    id="broker-loading",
                    type="circle",
                    color=T.ACCENT,
                    children=html.Div(id="broker-panel-content"),
                ),

                # Auto-refresh every 5 min
                dcc.Interval(
                    id="broker-interval",
                    interval=5 * 60 * 1000,
                    n_intervals=0,
                    disabled=not any_ok,
                ),

                # Setup help shown only when nothing is configured
                html.Div(
                    _setup_help(),
                    style={"display": "none" if any_ok else "block"},
                ),
            ], style={"padding": "0 12px 16px"}),
        ],
        style={
            "width":           BROKER_WIDTH,
            "minHeight":       "100vh",
            "backgroundColor": T.SIDEBAR_BG,
            "borderLeft":      f"1px solid {T.BORDER}",
            "position":        "fixed",
            "top":  "0",
            "right": "0",
            "overflowY": "auto",
            "zIndex": "100",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Callback
# ═══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("broker-panel-content", "children"),
    Input("broker-refresh-btn", "n_clicks"),
    Input("broker-interval",    "n_intervals"),
    State("broker-select",      "value"),
    prevent_initial_call=False,
)
def _refresh_broker(n_clicks, n_intervals, broker: str | None):
    if not broker:
        # Determine from available
        if _rh_available():
            broker = "rh"
        elif _wb_available():
            broker = "wb"
        else:
            return html.Div()

    if broker == "rh":
        if not _rh_available():
            return html.Div("RobinHood not configured.", style={"color": T.TEXT_MUTED,
                                                                 "fontSize": "10px",
                                                                 "marginTop": "10px"})
        acct = _rh_fetch_account()
        body = [_account_panel(acct, "RobinHood")]
        if "error" not in acct:
            pos = _rh_fetch_positions()
            body += [_section_label("Positions"), _positions_table(pos)]
        return html.Div(body)

    if broker == "wb":
        if not _wb_available():
            return html.Div("Webull not configured.", style={"color": T.TEXT_MUTED,
                                                              "fontSize": "10px",
                                                              "marginTop": "10px"})
        acct = _wb_fetch_account()
        body = [_account_panel(acct, "Webull")]
        if "error" not in acct:
            pos = _wb_fetch_positions()
            body += [_section_label("Positions"), _positions_table(pos)]
        return html.Div(body)

    return html.Div()
