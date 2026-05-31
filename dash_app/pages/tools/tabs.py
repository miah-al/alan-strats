"""
dash_app/pages/tools/tabs.py -- per-tab layout builders + _get_tab_builder.

Each builder returns the layout for one sub-tab; _get_tab_builder maps a tab id
to its builder. The Models and Course tabs embed the existing page layouts
(dash_app.pages.models / dash_app.pages.course).

Adopts the shared design system (dash_app.ui) tokens; all component ids are
identical to the original tools.py.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc, no_update

from dash_app import theme as T, get_polygon_api_key
from dash_app.ui import tokens as D, components as C

# NOTE: models.layout()/course.layout() are imported lazily inside _models_tab /
# _course_tab (verbatim from the original) to avoid any import-cycle surprises.
from dash_app.pages.tools.data import _col, _metric_card, _compute_risk_metrics

_GUIDE_DIR = Path(__file__).parent.parent.parent / "guide_articles"
_BROKER_GUIDE = Path(__file__).parent.parent.parent / "guide_articles" / "broker_integration.md"


def _card_header(txt: str) -> html.Span:
    return html.Span(txt, style={
        "fontSize": D.TEXT_XS, "fontWeight": D.WEIGHT_BOLD,
        "textTransform": "uppercase", "letterSpacing": "0.08em",
        "color": D.COLOR.accent,
    })


def _section_label(txt: str) -> html.Div:
    return html.Div(txt, style={
        "color": D.COLOR.text_sec, "fontSize": D.TEXT_XS, "fontWeight": D.WEIGHT_MED,
        "letterSpacing": "0.05em", "textTransform": "uppercase",
        "marginBottom": D.SPACE_2, "marginTop": D.SPACE_1,
    })


def _sync_row(label: str, btn_id: str, status_id: str, caption_id: str,
              disabled_id: str | None = None) -> html.Div:
    """One sync button + status badge + DB caption row."""
    return html.Div([
        dbc.Button(
            label,
            id=btn_id,
            color="secondary",
            outline=True,
            size="sm",
            className="w-100 mb-2",
            style={"fontSize": "12px"},
        ),
        html.Div([
            html.Span(id=status_id, style={"fontSize": "12px"}),
            html.Div(id=caption_id, style={"color": T.TEXT_MUTED, "fontSize": "11px"}),
        ], style={"marginTop": "2px"}),
    ], style={"marginBottom": "10px"})


def _data_manager_tab() -> html.Div:
    return html.Div([
        # ── Top controls ──────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Label("Ticker", style={"color": T.TEXT_SEC, "fontSize": "12px",
                                            "marginBottom": "4px", "display": "block"}),
                dbc.Input(
                    id="tools-dm-ticker",
                    placeholder="SPY, TLT, AAPL…",
                    value="SPY",
                    style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                           "border": f"1px solid {T.BORDER}", "fontSize": "13px",
                           "width": "180px"},
                    debounce=False,
                ),
            ], style={"flex": "0 0 auto"}),
            html.Div([
                html.Label("Backfill from", style={"color": T.TEXT_SEC, "fontSize": "12px",
                                                    "marginBottom": "4px", "display": "block"}),
                dbc.Input(
                    id="tools-dm-from-date",
                    type="date",
                    value="2020-01-01",
                    style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                           "border": f"1px solid {T.BORDER}", "fontSize": "13px",
                           "width": "160px"},
                ),
            ], style={"flex": "0 0 auto"}),
            html.Div([
                dbc.Checklist(
                    options=[{"label": "Force full re-sync", "value": "force"}],
                    value=[],
                    id="tools-dm-force-full",
                    style={"color": T.TEXT_SEC, "fontSize": "12px"},
                    switch=True,
                ),
            ], style={"flex": "0 0 auto", "alignSelf": "flex-end", "paddingBottom": "4px"}),
            html.Div([
                dbc.Button(
                    "Sync All (excl. Options)",
                    id="tools-dm-sync-all",
                    color="primary",
                    size="sm",
                    style={"fontSize": "12px"},
                ),
            ], style={"flex": "0 0 auto", "alignSelf": "flex-end", "paddingBottom": "4px"}),
        ], style={"display": "flex", "gap": "16px", "marginBottom": "20px",
                  "flexWrap": "wrap", "alignItems": "flex-start"}),

        # ── Sync All progress state (drives the progressive callback) ────────
        dcc.Store(id="tools-dm-sync-all-state", data=None),

        # ── Sync cards ────────────────────────────────────────────────────────
        dbc.Row([
            dbc.Col(
                C.section("Polygon", [
                    _sync_row("Sync Price Bars",   "tools-dm-btn-price",    "tools-dm-st-price",    "tools-dm-cap-price"),
                    _sync_row("Sync News",          "tools-dm-btn-news",     "tools-dm-st-news",     "tools-dm-cap-news"),
                    _sync_row("Sync Options",       "tools-dm-btn-options",  "tools-dm-st-options",  "tools-dm-cap-options"),
                    _sync_row("Sync Dividends",     "tools-dm-btn-divs",     "tools-dm-st-divs",     "tools-dm-cap-divs"),
                    _sync_row("Sync Earnings",      "tools-dm-btn-earnings", "tools-dm-st-earnings", "tools-dm-cap-earnings"),
                ]),
                width=6),
            dbc.Col(
                C.section("Free Sources (FRED / CBOE)", [
                    _sync_row("Sync Treasury Yields — FRED", "tools-dm-btn-treasury", "tools-dm-st-treasury", "tools-dm-cap-treasury"),
                    _sync_row("Sync VIX Bars — CBOE",        "tools-dm-btn-vix",      "tools-dm-st-vix",      "tools-dm-cap-vix"),
                    _sync_row("Sync Macro — FRED",            "tools-dm-btn-macro",    "tools-dm-st-macro",    "tools-dm-cap-macro"),
                    _sync_row("Sync CPI — FRED",              "tools-dm-btn-cpi",      "tools-dm-st-cpi",      "tools-dm-cap-cpi"),
                    _sync_row("Sync FOMC Calendar",           "tools-dm-btn-fomc",     "tools-dm-st-fomc",     "tools-dm-cap-fomc"),
                ]),
                width=6),
        ], className="g-3", style={"marginBottom": D.SPACE_3}),

        C.section("Alpha Vantage", [
            dbc.Input(
                id="tools-dm-av-key",
                placeholder="Alpha Vantage API key (free at alphavantage.co)",
                type="password",
                style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                       "border": f"1px solid {T.BORDER}", "fontSize": "12px",
                       "marginBottom": "10px"},
                debounce=True,
            ),
            dbc.Row([
                dbc.Col(_sync_row("Sync EPS Estimates", "tools-dm-btn-eps",
                                  "tools-dm-st-eps", "tools-dm-cap-eps"), width=4),
            ]),
        ]),

        html.Hr(style={"borderColor": D.COLOR.border}),

        # ── Coverage ──────────────────────────────────────────────────────────
        html.H5("Coverage", style={"color": D.COLOR.text, "fontSize": D.TEXT_LG,
                                    "fontWeight": D.WEIGHT_MED, "marginBottom": D.SPACE_3}),
        dbc.Button("Refresh Coverage", id="tools-dm-refresh-cov", color="secondary",
                   size="sm", style={"fontSize": D.TEXT_SM, "marginBottom": D.SPACE_3}),
        dcc.Loading(
            html.Div(id="tools-dm-coverage-tables"),
            type="circle", color=T.ACCENT,
        ),

        html.Hr(style={"borderColor": D.COLOR.border}),

        # ── Training validation ───────────────────────────────────────────────
        html.H5("Training Data Validation", style={"color": D.COLOR.text,
                                                    "fontSize": D.TEXT_LG,
                                                    "fontWeight": D.WEIGHT_MED,
                                                    "marginBottom": D.SPACE_3}),
        html.Div([
            dbc.Input(
                id="tools-dm-val-ticker",
                placeholder="e.g. SPY, TLT…",
                style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                       "border": f"1px solid {T.BORDER}", "fontSize": "13px",
                       "width": "180px"},
                debounce=True,
            ),
            dbc.Button("Validate", id="tools-dm-validate-btn", color="secondary",
                       size="sm", style={"fontSize": "12px"}),
        ], style={"display": "flex", "gap": "8px", "alignItems": "center",
                  "marginBottom": "12px"}),
        dcc.Loading(
            html.Div(id="tools-dm-val-result"),
            type="circle", color=T.ACCENT,
        ),
    ], style={"padding": "16px 0"})


_IV_TICKERS = ["SPY", "QQQ", "IWM", "AAPL", "TSLA", "NVDA", "GLD", "TLT"]


def _iv_metrics_tab() -> html.Div:
    return html.Div([
        html.Div([
            html.Div([
                html.Label("Tickers (comma-sep)", style={"color": T.TEXT_SEC,
                                                          "fontSize": "12px",
                                                          "marginBottom": "4px",
                                                          "display": "block"}),
                dbc.Input(
                    id="tools-iv-tickers",
                    value=", ".join(_IV_TICKERS),
                    style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                           "border": f"1px solid {T.BORDER}", "fontSize": "13px",
                           "width": "380px"},
                    debounce=True,
                ),
            ]),
            html.Div([
                html.Label("Polygon API Key", style={"color": T.TEXT_SEC,
                                                       "fontSize": "12px",
                                                       "marginBottom": "4px",
                                                       "display": "block"}),
                dbc.Input(
                    id="tools-iv-api-key",
                    placeholder="Leave blank to use .env key",
                    type="password",
                    style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                           "border": f"1px solid {T.BORDER}", "fontSize": "13px",
                           "width": "280px"},
                    debounce=True,
                ),
            ]),
            html.Div([
                dbc.Button("Run IV Scan", id="tools-iv-run-btn", color="primary",
                           size="sm", style={"fontSize": "12px"}),
            ], style={"alignSelf": "flex-end", "paddingBottom": "4px"}),
        ], style={"display": "flex", "gap": "16px", "marginBottom": "20px",
                  "flexWrap": "wrap", "alignItems": "flex-start"}),

        dcc.Loading(
            html.Div(id="tools-iv-content"),
            type="circle", color=T.ACCENT,
        ),
    ], style={"padding": "16px 0"})


_AI_SLUGS = {
    "iron_condor_ai", "ml_gradient_boost", "ml_transformer_seq",
    "ml_ensemble_stacking", "reinforcement_agent", "neural_regime_transformer",
    "online_adaptive_model",
}


def _guide_options() -> tuple[list[dict], str | None]:
    """Build grouped dcc.Dropdown options: AI/ML first, then Rules-Based."""
    ai_opts, rules_opts = [], []
    if _GUIDE_DIR.exists():
        for p in sorted(_GUIDE_DIR.glob("*.md")):
            slug = p.stem
            label = slug.replace("_", " ").title()
            entry = {"label": label, "value": slug}
            (ai_opts if slug in _AI_SLUGS else rules_opts).append(entry)

    groups: list[dict] = []
    if ai_opts:
        groups.append({"label": "🤖  AI / ML Strategies", "value": "__ai__",
                       "disabled": True})
        groups.extend(ai_opts)
    if rules_opts:
        groups.append({"label": "⚙  Rules-Based Strategies", "value": "__rules__",
                       "disabled": True})
        groups.extend(rules_opts)

    default = (rules_opts[0]["value"] if rules_opts
               else ai_opts[0]["value"] if ai_opts else None)
    return groups, default


def _guide_tab() -> html.Div:
    opts, default = _guide_options()
    return html.Div([
        html.Div([
            html.Label("Select Article", style={"color": T.TEXT_SEC, "fontSize": "12px",
                                                 "marginBottom": "4px", "display": "block"}),
            dbc.Select(
                id="tools-guide-select",
                options=opts,
                value=default,
                style={**T.STYLE_DROPDOWN, "width": "440px"},
            ),
        ], style={"marginBottom": "16px"}),
        html.Div(id="tools-guide-content", style={
            **D.CARD,
            "padding": D.SPACE_6,
        }),
    ], style={"padding": "16px 0"})


def _px_input(id_: str, placeholder: str = "", value: str = "",
              type_: str = "text", width: str = "120px") -> dbc.Input:
    return dbc.Input(
        id=id_,
        placeholder=placeholder,
        value=value,
        type=type_,
        style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
               "border": f"1px solid {T.BORDER}", "fontSize": "12px",
               "width": width},
        debounce=True,
    )


def _px_label(txt: str) -> html.Div:
    return html.Div(txt, style={"color": T.TEXT_SEC, "fontSize": "11px",
                                 "marginBottom": "3px"})


def _px_fetch_btn(id_: str, label: str = "Fetch") -> dbc.Button:
    return dbc.Button(label, id=id_, color="primary", size="sm",
                      style={"fontSize": "12px"})


def _polygon_explorer_tab() -> html.Div:
    today_str = date.today().isoformat()
    month_ago = (date.today() - timedelta(days=30)).isoformat()

    return html.Div([
        # ── API key test ──────────────────────────────────────────────────────
        C.section("API Key", [
            html.Div([
                dbc.Input(
                    id="tools-px-api-key",
                    placeholder="Leave blank to use .env POLYGON_API_KEY",
                    type="password",
                    style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                           "border": f"1px solid {T.BORDER}", "fontSize": "12px",
                           "flex": "1"},
                    debounce=True,
                ),
                dbc.Button("Test Key", id="tools-px-test-btn", color="secondary",
                           outline=True, size="sm", style={"fontSize": "12px"}),
            ], style={"display": "flex", "gap": D.SPACE_2, "alignItems": "center"}),
            html.Div(id="tools-px-test-result",
                     style={"marginTop": D.SPACE_2, "fontSize": D.TEXT_SM}),
        ]),

        # ── Ticker input ──────────────────────────────────────────────────────
        html.Div([
            _px_label("Ticker"),
            _px_input("tools-px-ticker", placeholder="SPY", width="140px"),
        ], style={"marginBottom": "16px"}),

        # ── Accordion ─────────────────────────────────────────────────────────
        dbc.Accordion([

            # 1. Market Snapshot
            dbc.AccordionItem([
                html.Div([
                    _px_fetch_btn("tools-px-snap-btn"),
                ], style={"marginBottom": "10px"}),
                dcc.Loading(html.Div(id="tools-px-snap-content"), type="dot", color=T.ACCENT),
            ], title="Market Snapshot"),

            # 2. OHLCV Bars
            dbc.AccordionItem([
                html.Div([
                    html.Div([
                        _px_label("Multiplier"),
                        _px_input("tools-px-bars-mult", value="1", type_="number", width="70px"),
                    ]),
                    html.Div([
                        _px_label("Timespan"),
                        dbc.Select(
                            id="tools-px-bars-timespan",
                            options=[{"label": t, "value": t}
                                     for t in ["minute","hour","day","week","month"]],
                            value="day",
                            style={**T.STYLE_DROPDOWN, "width": "110px"},
                        ),
                    ]),
                    html.Div([
                        _px_label("From"),
                        _px_input("tools-px-bars-from", value=month_ago, type_="date", width="140px"),
                    ]),
                    html.Div([
                        _px_label("To"),
                        _px_input("tools-px-bars-to", value=today_str, type_="date", width="140px"),
                    ]),
                    html.Div(_px_fetch_btn("tools-px-bars-btn"),
                             style={"alignSelf": "flex-end"}),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                           "alignItems": "flex-start", "marginBottom": "10px"}),
                dcc.Loading(html.Div(id="tools-px-bars-content"), type="dot", color=T.ACCENT),
            ], title="OHLCV Bars"),

            # 3. Technical Indicators
            dbc.AccordionItem([
                html.Div([
                    html.Div([
                        _px_label("Indicator"),
                        dbc.Select(
                            id="tools-px-ind-type",
                            options=[{"label": i.upper(), "value": i}
                                     for i in ["rsi","macd","sma","ema"]],
                            value="rsi",
                            style={**T.STYLE_DROPDOWN, "width": "100px"},
                        ),
                    ]),
                    html.Div([
                        _px_label("Window"),
                        _px_input("tools-px-ind-window", value="14", type_="number", width="70px"),
                    ]),
                    html.Div([
                        _px_label("Timespan"),
                        dbc.Select(
                            id="tools-px-ind-timespan",
                            options=[{"label": t, "value": t}
                                     for t in ["minute","hour","day","week"]],
                            value="day",
                            style={**T.STYLE_DROPDOWN, "width": "100px"},
                        ),
                    ]),
                    html.Div([
                        _px_label("From"),
                        _px_input("tools-px-ind-from", value=month_ago, type_="date", width="140px"),
                    ]),
                    html.Div([
                        _px_label("To"),
                        _px_input("tools-px-ind-to", value=today_str, type_="date", width="140px"),
                    ]),
                    html.Div(_px_fetch_btn("tools-px-ind-btn"),
                             style={"alignSelf": "flex-end"}),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                           "alignItems": "flex-start", "marginBottom": "10px"}),
                dcc.Loading(html.Div(id="tools-px-ind-content"), type="dot", color=T.ACCENT),
            ], title="Technical Indicators"),

            # 4. Options Expirations
            dbc.AccordionItem([
                html.Div([
                    _px_fetch_btn("tools-px-exp-btn"),
                ], style={"marginBottom": "10px"}),
                dcc.Loading(html.Div(id="tools-px-exp-content"), type="dot", color=T.ACCENT),
            ], title="Options Expirations"),

            # 5. Options Chain
            dbc.AccordionItem([
                dcc.Store(id="tools-px-expirations-store"),
                html.Div([
                    dbc.Button("Load Expirations", id="tools-px-load-exp-btn",
                               color="secondary", outline=True, size="sm",
                               style={"fontSize": "12px"}),
                    html.Div([
                        _px_label("Expiration"),
                        dbc.Select(
                            id="tools-px-chain-exp",
                            options=[{"label": "Load first…", "value": "", "disabled": True}],
                            value="",
                            style={**T.STYLE_DROPDOWN, "width": "140px"},
                        ),
                    ]),
                    html.Div([
                        _px_label("Contract type"),
                        dbc.Select(
                            id="tools-px-chain-type",
                            options=[{"label": t.title(), "value": t}
                                     for t in ["all","call","put"]],
                            value="all",
                            style={**T.STYLE_DROPDOWN, "width": "90px"},
                        ),
                    ]),
                    html.Div([
                        _px_label("Strike range (% of spot)"),
                        dcc.RangeSlider(
                            id="tools-px-chain-strike-range",
                            min=70, max=130, step=5,
                            value=[80, 120],
                            marks={v: f"{v}%" for v in [70,80,90,100,110,120,130]},
                            tooltip={"placement": "bottom"},
                        ),
                    ], style={"flex": "1", "minWidth": "280px"}),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                           "alignItems": "flex-start", "marginBottom": "8px"}),
                html.Div([
                    dbc.Checkbox(id="tools-px-chain-historical", label="Historical mode",
                                 value=False,
                                 style={"color": T.TEXT_SEC, "fontSize": "12px"}),
                    _px_input("tools-px-chain-date", placeholder="YYYY-MM-DD",
                               type_="date", width="140px"),
                    _px_fetch_btn("tools-px-chain-btn", "Fetch Chain"),
                ], style={"display": "flex", "gap": "12px", "alignItems": "center",
                           "marginBottom": "10px"}),
                dcc.Loading(html.Div(id="tools-px-chain-content"), type="dot", color=T.ACCENT),
            ], title="Options Chain"),

            # 6. Ticker Details
            dbc.AccordionItem([
                html.Div([
                    _px_fetch_btn("tools-px-details-btn"),
                ], style={"marginBottom": "10px"}),
                dcc.Loading(html.Div(id="tools-px-details-content"), type="dot", color=T.ACCENT),
            ], title="Ticker Details"),

            # 7. News
            dbc.AccordionItem([
                html.Div([
                    html.Div([
                        _px_label("From"),
                        _px_input("tools-px-news-from", value=month_ago, type_="date", width="140px"),
                    ]),
                    html.Div([
                        _px_label("To"),
                        _px_input("tools-px-news-to", value=today_str, type_="date", width="140px"),
                    ]),
                    html.Div([
                        _px_label("Max articles"),
                        _px_input("tools-px-news-max", value="20", type_="number", width="80px"),
                    ]),
                    html.Div(_px_fetch_btn("tools-px-news-btn"),
                             style={"alignSelf": "flex-end"}),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                           "alignItems": "flex-start", "marginBottom": "10px"}),
                dcc.Loading(html.Div(id="tools-px-news-content"), type="dot", color=T.ACCENT),
            ], title="News"),

            # 8. EPS Financials
            dbc.AccordionItem([
                html.Div([
                    html.Div([
                        _px_label("Timeframe"),
                        dbc.Select(
                            id="tools-px-fin-timeframe",
                            options=[{"label": t.title(), "value": t}
                                     for t in ["quarterly","annual"]],
                            value="quarterly",
                            style={**T.STYLE_DROPDOWN, "width": "120px"},
                        ),
                    ]),
                    html.Div([
                        _px_label("Periods"),
                        _px_input("tools-px-fin-periods", value="8", type_="number", width="70px"),
                    ]),
                    html.Div(_px_fetch_btn("tools-px-fin-btn"),
                             style={"alignSelf": "flex-end"}),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                           "alignItems": "flex-start", "marginBottom": "10px"}),
                dcc.Loading(html.Div(id="tools-px-fin-content"), type="dot", color=T.ACCENT),
            ], title="EPS Financials"),

            # 10. Price Check — Polygon vs Robinhood
            dbc.AccordionItem([
                dbc.Alert(
                    [
                        html.Strong("Robinhood API not configured. "),
                        "To enable live price comparison, set ",
                        html.Code("ROBINHOOD_USERNAME"),
                        ", ",
                        html.Code("ROBINHOOD_PASSWORD"),
                        " (and optionally ",
                        html.Code("ROBINHOOD_MFA_CODE"),
                        ") as environment variables, then install ",
                        html.Code("robin_stocks"),
                        ".",
                    ],
                    id="tools-pc-rh-warning",
                    color="warning",
                    style={"fontSize": "12px", "padding": "8px 12px", "marginBottom": "12px"},
                    dismissable=False,
                    is_open=True,
                ),
                html.Div([
                    html.Div([
                        _px_label("Ticker"),
                        _px_input("tools-pc-ticker", placeholder="SPY", width="90px"),
                    ]),
                    html.Div([
                        _px_label("Option expiry (YYYY-MM-DD, optional)"),
                        _px_input("tools-pc-expiry", placeholder="2025-04-17", width="160px"),
                    ]),
                    html.Div([
                        _px_label("Strike (optional)"),
                        _px_input("tools-pc-strike", placeholder="500", width="90px"),
                    ]),
                    html.Div([
                        _px_label("Type"),
                        dcc.Dropdown(
                            id="tools-pc-opt-type",
                            options=[{"label": "Call", "value": "call"},
                                     {"label": "Put",  "value": "put"}],
                            value="call",
                            clearable=False,
                            style={"width": "100px", "fontSize": "12px",
                                   "backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY},
                        ),
                    ]),
                    html.Div(
                        _px_fetch_btn("tools-pc-run-btn", "Check Prices"),
                        style={"alignSelf": "flex-end"},
                    ),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                          "alignItems": "flex-start", "marginBottom": "10px"}),
                dcc.Loading(html.Div(id="tools-pc-content"), type="dot", color=T.ACCENT),
            ], title="Price Check — Polygon vs Robinhood"),

            # 9. Raw API Call
            dbc.AccordionItem([
                html.Div([
                    html.Div([
                        _px_label("Endpoint path (e.g. /v2/aggs/ticker/SPY/…)"),
                        _px_input("tools-px-raw-path",
                                  placeholder="/v2/snapshot/locale/us/markets/stocks/tickers/SPY",
                                  width="420px"),
                    ], style={"flex": "1"}),
                    html.Div(_px_fetch_btn("tools-px-raw-btn"),
                             style={"alignSelf": "flex-end"}),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                           "alignItems": "flex-start", "marginBottom": "8px"}),
                html.Div([
                    _px_label("Extra params (JSON, e.g. {\"adjusted\": \"true\"})"),
                    dcc.Textarea(
                        id="tools-px-raw-params",
                        placeholder='{}',
                        style={"width": "100%", "height": "80px",
                               "backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                               "border": f"1px solid {T.BORDER}", "fontSize": "12px",
                               "borderRadius": "6px", "padding": "8px",
                               "fontFamily": "monospace"},
                    ),
                ], style={"marginBottom": "10px"}),
                dcc.Loading(html.Div(id="tools-px-raw-content"), type="dot", color=T.ACCENT),
            ], title="Raw API Call"),

        ], start_collapsed=True, always_open=False,
           style={"backgroundColor": "transparent"}),

    ], style={"padding": "16px 0"})


def _models_tab() -> html.Div:
    from dash_app.pages.models import layout as _models_layout
    return html.Div(_models_layout(), style={"padding": "16px 0"})


def _course_tab() -> html.Div:
    from dash_app.pages.course import layout as _course_layout
    return html.Div(_course_layout(), style={"padding": "16px 0"})


def _get_tab_builder(tab_id: str):
    # Lazy lookup — some *_tab functions are defined below layout() in this
    # file, so resolve by name at call time rather than at module-import time.
    return {
        "data-manager":     _data_manager_tab,
        "iv-metrics":       _iv_metrics_tab,
        "risk":             _risk_tab,
        "registry":         _registry_tab,
        "models":           _models_tab,
        "course":           _course_tab,
        "guide":            _guide_tab,
        "polygon-explorer": _polygon_explorer_tab,
    }.get(tab_id)


def _risk_tab() -> html.Div:
    metrics, series = _compute_risk_metrics()

    def _val(m, key, fmt):
        return fmt.format(m[key]) if m else "—"

    var_str    = _val(metrics, "var_95",  "{:.2f}%")
    cvar_str   = _val(metrics, "cvar_95", "{:.2f}%")
    maxdd_str  = _val(metrics, "max_dd",  "{:.1f}%")
    sharpe_str = _val(metrics, "sharpe",  "{:.2f}")
    sort_str   = _val(metrics, "sortino", "{:.2f}")

    cards = C.kpi_row([
        ("VaR 95% (daily)",  var_str,  "danger"  if metrics else "muted"),
        ("CVaR 95% (daily)", cvar_str, "danger"  if metrics else "muted"),
        ("Max Drawdown",     maxdd_str,"warning" if metrics else "muted"),
        ("Sharpe Ratio", sharpe_str,
         "success" if metrics and metrics["sharpe"] >= 1 else
         ("warning" if metrics else "muted")),
        ("Sortino Ratio", sort_str,
         "success" if metrics and metrics["sortino"] >= 1.5 else
         ("warning" if metrics else "muted")),
    ])

    charts_section = html.Div()
    if series is not None:
        equity, rets, drawdowns = series
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=list(equity.index), y=list(equity.values),
            name="Portfolio Equity", line=dict(color=D.COLOR.accent, width=2),
            fill="tozeroy", fillcolor=D.COLOR.accent_soft,
        ))
        fig_eq.update_layout(**D.plotly_layout(
            height=260, margin=dict(l=50, r=20, t=30, b=40),
            title=dict(text="Portfolio Equity Curve", font=dict(size=13)),
            yaxis=dict(gridcolor=D.COLOR.border, tickprefix="$", tickformat=",.0f"),
            showlegend=False,
        ))

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=list(drawdowns.index), y=(drawdowns * 100).tolist(),
            name="Drawdown", line=dict(color=D.COLOR.danger, width=1.5),
            fill="tozeroy", fillcolor="rgba(239,68,68,0.12)",
        ))
        fig_dd.update_layout(**D.plotly_layout(
            height=200, margin=dict(l=50, r=20, t=30, b=40),
            title=dict(text="Drawdown (%)", font=dict(size=13)),
            yaxis=dict(gridcolor=D.COLOR.border, ticksuffix="%"),
            showlegend=False,
        ))

        charts_section = C.section("Equity & Drawdown", [
            dcc.Graph(figure=fig_eq, config=D.PLOTLY_CONFIG),
            dcc.Graph(figure=fig_dd, config=D.PLOTLY_CONFIG),
        ])

    no_data = dbc.Alert(
        "No portfolio history yet. Paper-trade some positions to generate risk metrics.",
        color="warning", style={"fontSize": D.TEXT_MD},
    ) if not metrics else html.Div()

    ref_rows = [
        ("Sharpe Ratio",  "(Return − RF) / StdDev × √252",              "> 1.0"),
        ("Sortino Ratio", "(Return − RF) / Downside StdDev × √252",      "> 1.5"),
        ("VaR 95%",       "Worst daily loss 95% of the time",             "< −2% concerning"),
        ("CVaR 95%",      "Mean loss in worst 5% of days",               "< −3% concerning"),
        ("Max Drawdown",  "Peak-to-trough equity decline",               "< −20% concerning"),
    ]
    ref_table = dbc.Table([
        html.Thead(html.Tr([
            html.Th(h, style={"color": D.COLOR.text_sec, "fontSize": D.TEXT_XS,
                              "fontWeight": D.WEIGHT_BOLD, "textTransform": "uppercase"})
            for h in ["Metric", "Definition", "Good Range"]
        ])),
        html.Tbody([
            html.Tr([
                html.Td(m, style={"color": D.COLOR.accent, "fontWeight": D.WEIGHT_MED,
                                  "fontSize": D.TEXT_MD}),
                html.Td(d, style={"color": D.COLOR.text, "fontSize": D.TEXT_SM}),
                html.Td(g, style={"color": D.COLOR.text_sec, "fontSize": D.TEXT_SM,
                                  "fontFamily": D.FONT_MONO}),
            ]) for m, d, g in ref_rows
        ]),
    ], bordered=False, hover=True, size="sm",
        style={"borderColor": D.COLOR.border, "--bs-table-bg": D.COLOR.elevated,
               "--bs-table-color": D.COLOR.text,
               "--bs-table-hover-bg": "#1a2235"})

    return html.Div([
        no_data,
        cards,
        charts_section,
        C.section("Risk Metric Reference", [
            ref_table,
            html.P([
                html.Strong("Kelly fraction tip: ", style={"color": D.COLOR.text}),
                "Use 0.10–0.25× full Kelly. VaR caveat: historical VaR assumes tomorrow "
                "looks like history — tail events are systematically underestimated.",
            ], style={"color": D.COLOR.text_sec, "fontSize": D.TEXT_SM,
                      "lineHeight": "1.6", "marginTop": D.SPACE_3, "marginBottom": "0"}),
        ]),
    ], style={"padding": "16px 0"})


def _registry_tab() -> html.Div:
    try:
        from strategies.registry import STRATEGY_METADATA
    except ImportError:
        return dbc.Alert("Could not load strategy registry.", color="warning")

    total  = len(STRATEGY_METADATA)
    active = sum(1 for m in STRATEGY_METADATA.values() if m.get("status") == "active")
    stub   = sum(1 for m in STRATEGY_METADATA.values() if m.get("status") == "stub")
    ai     = sum(1 for m in STRATEGY_METADATA.values() if m.get("type") == "ai")
    rule   = sum(1 for m in STRATEGY_METADATA.values() if m.get("type") == "rule")

    counter_row = C.kpi_row([
        ("Total Strategies", str(total),  "accent"),
        ("Implemented",      str(active), "success"),
        ("Roadmap (Stubs)",  str(stub),   "warning"),
        ("AI / ML",          str(ai),     "accent"),
        ("Rules-Based",      str(rule),   "default"),
    ])

    pct = active / total * 100 if total else 0
    progress_bar = C.card([
        dbc.Row([
            dbc.Col(html.Span("Strategies implemented",
                              style={"color": D.COLOR.text_sec, "fontSize": D.TEXT_MD}),
                    width="auto"),
            dbc.Col(html.Span(f"{active} / {total} · {pct:.0f}%",
                              style={"color": D.COLOR.success, "fontWeight": D.WEIGHT_BOLD,
                                     "fontFamily": D.FONT_MONO, "fontSize": D.TEXT_LG}),
                    width="auto", style={"marginLeft": "auto"}),
        ], align="center", className="mb-2"),
        dbc.Progress(value=pct, color="success", style={"height": "8px"}),
    ])

    rows = [
        {
            "Strategy":      m.get("display_name", slug),
            "Type":          m.get("type", "—").upper(),
            "Status":        m.get("status", "—").capitalize(),
            "Asset Class":   m.get("asset_class", "—").replace("_", " ").title(),
            "Hold (days)":   m.get("typical_holding_days", "—"),
            "Target Sharpe": m.get("target_sharpe", "—"),
            "ML":            "Yes" if m.get("uses_ml") else "No",
        }
        for slug, m in STRATEGY_METADATA.items()
    ]

    col_defs = [
        {"field": "Strategy",       "flex": 2, "minWidth": 180},
        {"field": "Type",           "width": 70},
        {"field": "Status",         "width": 100},
        {"field": "Asset Class",    "flex": 1, "minWidth": 130},
        {"field": "Hold (days)",    "width": 100, "type": "numericColumn"},
        {"field": "Target Sharpe",  "width": 110, "type": "numericColumn"},
        {"field": "ML",             "width": 60},
    ]

    grid = dag.AgGrid(
        rowData=rows,
        columnDefs=col_defs,
        dashGridOptions={"suppressColumnVirtualisation": True, "rowSelection": "single"},
        defaultColDef={"resizable": True, "sortable": True, "filter": True},
        className="ag-theme-quartz-dark",
        style={"height": "480px"},
        id="reg-grid",
    )

    detail_options = [
        {"label": f"{m.get('icon', '')} {m.get('display_name', s)}", "value": s}
        for s, m in STRATEGY_METADATA.items()
    ]
    first_slug = next(iter(STRATEGY_METADATA))

    return html.Div([
        counter_row,
        progress_bar,
        C.section("All Strategies", grid),
        C.section("Strategy Detail", [
            dbc.Select(options=detail_options, value=first_slug,
                       id="reg-detail-select",
                       style={**T.STYLE_DROPDOWN, "marginBottom": D.SPACE_4}),
            html.Div(id="reg-detail-body"),
        ]),
    ], style={"padding": "16px 0"})


def _broker_tab() -> html.Div:
    if _BROKER_GUIDE.exists():
        content = _BROKER_GUIDE.read_text(encoding="utf-8")
        return html.Div([
            C.section("Broker Integration Guide",
                      dcc.Markdown(content, className="guide-md",
                                   style={"color": D.COLOR.text, "fontSize": D.TEXT_MD,
                                          "lineHeight": "1.7"})),
        ], style={"padding": "16px 0"})
    return dbc.Alert("Broker integration guide not found.", color="warning")
