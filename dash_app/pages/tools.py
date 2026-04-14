"""
dash_app/pages/tools.py — Tools page.

Tabs:
  1. Data Manager      — sync controls, coverage tables, training validation
  2. IV Metrics        — IVR chart, IV vs HV comparison, term structure
  3. Guide             — browse all strategy guide articles
  4. Polygon Explorer  — interactive Polygon.io API explorer
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update

from dash_app import theme as T, get_polygon_api_key

logger = logging.getLogger(__name__)

_GUIDE_DIR = Path(__file__).parent.parent / "guide_articles"

# ── Coverage symbols ──────────────────────────────────────────────────────────

_COVERAGE_SYMBOLS = ["HOOD", "SPY", "QQQ", "AAPL", "TSLA", "MARA", "TLT"]

# ── Tab style helper ──────────────────────────────────────────────────────────

_TAB_STYLE     = {"fontSize": "13px", "padding": "6px 14px"}
_TAB_ACT_STYLE = {**_TAB_STYLE, "borderTop": f"2px solid {T.ACCENT}"}

# ── Card header helper ────────────────────────────────────────────────────────

def _card_header(txt: str) -> html.Span:
    return html.Span(txt, style={
        "fontSize": "11px", "fontWeight": "700",
        "textTransform": "uppercase", "letterSpacing": "0.08em",
        "color": "#6366f1",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Layout helpers — Data Manager
# ═══════════════════════════════════════════════════════════════════════════════

def _section_label(txt: str) -> html.Div:
    return html.Div(txt, style={
        "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
        "letterSpacing": "0.05em", "textTransform": "uppercase",
        "marginBottom": "8px", "marginTop": "4px",
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
                    style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                           "border": f"1px solid {T.BORDER}", "fontSize": "13px",
                           "width": "180px"},
                    debounce=True,
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

        # ── Sync cards ────────────────────────────────────────────────────────
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(
                        dbc.CardHeader(_card_header("POLYGON"),
                                       style={"backgroundColor": T.BG_ELEVATED,
                                              "borderBottom": f"1px solid {T.BORDER}",
                                              "padding": "8px 14px"}),
                        style={"backgroundColor": T.BG_ELEVATED,
                               "borderBottom": f"1px solid {T.BORDER}",
                               "padding": "8px 14px"},
                    ),
                    dbc.CardBody([
                        _sync_row("Sync Price Bars",   "tools-dm-btn-price",    "tools-dm-st-price",    "tools-dm-cap-price"),
                        _sync_row("Sync News",          "tools-dm-btn-news",     "tools-dm-st-news",     "tools-dm-cap-news"),
                        _sync_row("Sync Options",       "tools-dm-btn-options",  "tools-dm-st-options",  "tools-dm-cap-options"),
                        _sync_row("Sync Dividends",     "tools-dm-btn-divs",     "tools-dm-st-divs",     "tools-dm-cap-divs"),
                        _sync_row("Sync Earnings",      "tools-dm-btn-earnings", "tools-dm-st-earnings", "tools-dm-cap-earnings"),
                    ], style={"padding": "12px 14px"}),
                ], style={**T.STYLE_CARD, "marginBottom": "0", "padding": "0"}),
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(
                        dbc.CardHeader(_card_header("FREE SOURCES (FRED / CBOE)"),
                                       style={"backgroundColor": T.BG_ELEVATED,
                                              "borderBottom": f"1px solid {T.BORDER}",
                                              "padding": "8px 14px"}),
                        style={"backgroundColor": T.BG_ELEVATED,
                               "borderBottom": f"1px solid {T.BORDER}",
                               "padding": "8px 14px"},
                    ),
                    dbc.CardBody([
                        _sync_row("Sync Treasury Yields — FRED", "tools-dm-btn-treasury", "tools-dm-st-treasury", "tools-dm-cap-treasury"),
                        _sync_row("Sync VIX Bars — CBOE",        "tools-dm-btn-vix",      "tools-dm-st-vix",      "tools-dm-cap-vix"),
                        _sync_row("Sync Macro — FRED",            "tools-dm-btn-macro",    "tools-dm-st-macro",    "tools-dm-cap-macro"),
                        _sync_row("Sync CPI — FRED",              "tools-dm-btn-cpi",      "tools-dm-st-cpi",      "tools-dm-cap-cpi"),
                        _sync_row("Sync FOMC Calendar",           "tools-dm-btn-fomc",     "tools-dm-st-fomc",     "tools-dm-cap-fomc"),
                    ], style={"padding": "12px 14px"}),
                ], style={**T.STYLE_CARD, "marginBottom": "0", "padding": "0"}),
            ], width=6),
        ], className="g-3", style={"marginBottom": "12px"}),

        dbc.Card([
            dbc.CardHeader(
                dbc.CardHeader(_card_header("ALPHA VANTAGE"),
                               style={"backgroundColor": T.BG_ELEVATED,
                                      "borderBottom": f"1px solid {T.BORDER}",
                                      "padding": "8px 14px"}),
                style={"backgroundColor": T.BG_ELEVATED,
                       "borderBottom": f"1px solid {T.BORDER}",
                       "padding": "8px 14px"},
            ),
            dbc.CardBody([
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
            ], style={"padding": "12px 14px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "20px", "padding": "0"}),

        html.Hr(style={"borderColor": T.BORDER}),

        # ── Coverage ──────────────────────────────────────────────────────────
        html.H5("Coverage", style={"color": T.TEXT_PRIMARY, "fontSize": "14px",
                                    "fontWeight": "600", "marginBottom": "12px"}),
        dbc.Button("Refresh Coverage", id="tools-dm-refresh-cov", color="secondary",
                   size="sm", style={"fontSize": "12px", "marginBottom": "12px"}),
        dcc.Loading(
            html.Div(id="tools-dm-coverage-tables"),
            type="circle", color=T.ACCENT,
        ),

        html.Hr(style={"borderColor": T.BORDER}),

        # ── Training validation ───────────────────────────────────────────────
        html.H5("Training Data Validation", style={"color": T.TEXT_PRIMARY,
                                                     "fontSize": "14px",
                                                     "fontWeight": "600",
                                                     "marginBottom": "12px"}),
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


# ═══════════════════════════════════════════════════════════════════════════════
# Layout helpers — IV Metrics
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# Layout helpers — Guide
# ═══════════════════════════════════════════════════════════════════════════════

# Slugs that are AI/ML-based strategies
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
            "backgroundColor": T.BG_CARD,
            "border": f"1px solid {T.BORDER}",
            "borderRadius": "10px",
            "padding": "24px",
        }),
    ], style={"padding": "16px 0"})


# ═══════════════════════════════════════════════════════════════════════════════
# Layout helpers — Polygon Explorer
# ═══════════════════════════════════════════════════════════════════════════════

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
        dbc.Card([
            dbc.CardHeader(_card_header("API KEY"), style={
                "backgroundColor": T.BG_ELEVATED,
                "borderBottom": f"1px solid {T.BORDER}", "padding": "8px 14px",
            }),
            dbc.CardBody([
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
                ], style={"display": "flex", "gap": "8px", "alignItems": "center"}),
                html.Div(id="tools-px-test-result",
                         style={"marginTop": "8px", "fontSize": "12px"}),
            ], style={"padding": "12px 14px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "12px", "padding": "0"}),

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


# ═══════════════════════════════════════════════════════════════════════════════
# Main layout
# ═══════════════════════════════════════════════════════════════════════════════

def layout() -> html.Div:
    return html.Div([
        html.H2("Tools", style={
            "color": T.TEXT_PRIMARY, "fontSize": "1.35rem",
            "fontWeight": "700", "marginBottom": "16px",
        }),
        dbc.Tabs(
            [
                dbc.Tab(_data_manager_tab(),     label="Data Manager",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(_iv_metrics_tab(),       label="IV Metrics",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(_risk_tab(),             label="Risk",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(_registry_tab(),         label="Registry",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(_guide_tab(),            label="Guide",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(_polygon_explorer_tab(), label="Polygon Explorer",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
            ],
            style={"marginBottom": "0"},
        ),
    ], style=T.STYLE_PAGE)


# ═══════════════════════════════════════════════════════════════════════════════
# Utility — AG Grid column def
# ═══════════════════════════════════════════════════════════════════════════════

def _col(field: str, flex: int = 1, width: int | None = None,
         min_width: int = 60, numeric: bool = False) -> dict:
    d: dict = {"field": field, "resizable": True, "sortable": True,
                "filter": True, "minWidth": min_width}
    if width:
        d["width"] = width
    else:
        d["flex"] = flex
    if numeric:
        d["type"] = "numericColumn"
    return d


def _metric_card(label: str, value: str) -> dbc.Card:
    return dbc.Card(dbc.CardBody([
        html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                "fontWeight": "600", "textTransform": "uppercase",
                                "letterSpacing": "0.05em", "marginBottom": "4px"}),
        html.Div(value, style={"color": T.TEXT_PRIMARY, "fontSize": "18px",
                                "fontWeight": "700"}),
    ], style={"padding": "12px 16px"}),
    style={**T.STYLE_CARD, "minWidth": "100px"})


def _status_badge(txt: str, color: str) -> html.Span:
    return html.Span(txt, style={
        "backgroundColor": color, "color": "#fff",
        "borderRadius": "4px", "padding": "1px 7px",
        "fontSize": "11px", "fontWeight": "600",
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Callbacks — Data Manager
# ═══════════════════════════════════════════════════════════════════════════════

def _run_sync(data_type: str, ticker: str, from_date_str: str,
              force: list, av_key: str = "") -> tuple[str, str]:
    """Execute one sync and return (status_html, caption_str)."""
    try:
        from db.sync import (
            sync_price_bars, sync_news, sync_dividends, sync_earnings,
            sync_option_snapshots, sync_treasury_bars, sync_vix_bars,
            sync_macro_bars, sync_cpi, sync_fomc_calendar, sync_eps_estimates,
        )
        from db.client import get_engine
        from datetime import date as _date

        api_key = get_polygon_api_key()
        try:
            from_date = _date.fromisoformat(from_date_str) if from_date_str else _date(2020, 1, 1)
        except Exception:
            from_date = _date(2020, 1, 1)

        do_force = bool(force)

        if do_force and data_type in ("price", "options") and ticker:
            from db.client import get_ticker_id
            from sqlalchemy import text as _t
            engine = get_engine()
            tid = get_ticker_id(engine, ticker)
            if tid:
                table_map = {
                    "price":   ("mkt.PriceBar",       "PriceBar"),
                    "options": ("mkt.OptionSnapshot",  "OptionSnapshot"),
                }
                tbl, dtype = table_map[data_type]
                with engine.begin() as c:
                    c.execute(_t(f"DELETE FROM {tbl} WHERE TickerId=:tid"), {"tid": tid})
                    c.execute(_t("DELETE FROM mkt.SyncLog WHERE DataType=:dt AND TickerId=:tid"),
                              {"dt": dtype, "tid": tid})

        ticker_types = {"price", "news", "options", "divs", "earnings", "eps_estimates"}
        fn_map = {
            "price":        (sync_price_bars,    (ticker, api_key), {"from_date": from_date}),
            "news":         (sync_news,           (ticker, api_key), {"from_date": from_date}),
            "options":      (sync_option_snapshots, (ticker, api_key), {"from_date": from_date}),
            "divs":         (sync_dividends,      (ticker, api_key), {"from_date": from_date}),
            "earnings":     (sync_earnings,        (ticker, api_key), {"from_date": from_date}),
            "treasury":     (sync_treasury_bars,   (), {"from_date": from_date}),
            "vix":          (sync_vix_bars,        (), {"from_date": from_date}),
            "macro":        (sync_macro_bars,      (), {"from_date": from_date}),
            "cpi":          (sync_cpi,             (), {"from_date": from_date}),
            "fomc":         (sync_fomc_calendar,   (), {}),
        }

        if data_type == "eps_estimates":
            if not av_key:
                return "AV key required", ""
            r = sync_eps_estimates(ticker, av_key)
            rows = r.get("updated", 0) + r.get("inserted", 0)
            return f"Done — {rows} rows", ""

        if data_type not in fn_map:
            return "Unknown type", ""

        if data_type in ticker_types and not ticker:
            return "Enter a ticker first", ""

        fn, args, kwargs = fn_map[data_type]
        r = fn(*args, **kwargs)
        s = r.get("status", "ok")
        rows = r.get("rows", 0)
        if s == "up_to_date":
            return "Already up to date", ""
        elif s in ("no_data", "no_calendar"):
            detail = r.get("detail", r.get("message", ""))
            return f"No data: {detail}", ""
        else:
            return f"Done — {rows:,} rows", ""

    except Exception as e:
        logger.exception("Sync error")
        return f"Error: {e}", ""


def _coverage_label(mn, mx, cnt) -> str:
    if not cnt:
        return "no data"
    return f"{int(cnt):,} rows · {mn} → {mx}"


def _build_coverage_tables() -> html.Div:
    try:
        from db.client import get_engine
        from sqlalchemy import text as _t
        engine = get_engine()
        syms_str = "','".join(_COVERAGE_SYMBOLS)

        with engine.connect() as conn:
            price_rows = conn.execute(_t(f"""
                SELECT t.Symbol, COUNT(*) AS Bars,
                       MIN(pb.BarDate) AS [From], MAX(pb.BarDate) AS [To]
                FROM   mkt.PriceBar pb
                JOIN   mkt.Ticker t ON t.TickerId = pb.TickerId
                WHERE  t.Symbol IN ('{syms_str}')
                GROUP BY t.Symbol
            """)).fetchall()

            opt_rows = conn.execute(_t(f"""
                SELECT t.Symbol,
                       COUNT(DISTINCT o.SnapshotDate) AS OptDays,
                       MIN(o.SnapshotDate) AS [From], MAX(o.SnapshotDate) AS [To]
                FROM   mkt.OptionSnapshot o
                JOIN   mkt.Ticker t ON t.TickerId = o.TickerId
                WHERE  t.Symbol IN ('{syms_str}')
                GROUP BY t.Symbol
            """)).fetchall()

            def _safe(sql):
                try:
                    return conn.execute(_t(sql)).fetchone()
                except Exception:
                    return None

            vix_row   = _safe("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.VixBar")
            macro_row = _safe("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.MacroBar")
            cpi_row   = _safe("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.CpiBar")
            fomc_row  = _safe("SELECT MIN(MeetingDate), MAX(MeetingDate), COUNT(*) FROM mkt.FomcCalendar")
            vxf_row   = _safe("SELECT MIN(TradeDate), MAX(TradeDate), COUNT(*) FROM mkt.VixFuture")
            tsy_row   = _safe("SELECT MIN(BarDate), MAX(BarDate), COUNT(*) FROM mkt.TreasuryBar")

        price_map = {r[0]: r for r in price_rows}
        opt_map   = {r[0]: r for r in opt_rows}
        ticker_data = []
        for sym in _COVERAGE_SYMBOLS:
            p = price_map.get(sym)
            o = opt_map.get(sym)
            ticker_data.append({
                "Ticker":     sym,
                "Price Bars": f"{int(p[1]):,}" if p else "—",
                "Price From": str(p[2]) if p else "—",
                "Price To":   str(p[3]) if p else "—",
                "Opt Days":   f"{int(o[1]):,}" if o else "—",
                "Opt From":   str(o[2]) if o else "—",
                "Opt To":     str(o[3]) if o else "—",
            })

        ticker_cols = [
            _col("Ticker",     width=80),
            _col("Price Bars", min_width=100, flex=1, numeric=True),
            _col("Price From", min_width=120, flex=1),
            _col("Price To",   min_width=120, flex=1),
            _col("Opt Days",   min_width=100, flex=1, numeric=True),
            _col("Opt From",   min_width=120, flex=1),
            _col("Opt To",     min_width=120, flex=1),
        ]

        def _cov(row, label):
            if row and row[2]:
                return {"Dataset": label, "From": str(row[0]),
                        "To": str(row[1]), "Rows": f"{int(row[2]):,}"}
            return {"Dataset": label, "From": "—", "To": "—", "Rows": "0"}

        global_data = [
            _cov(tsy_row,   "Treasury Yields"),
            _cov(vix_row,   "VIX Bars"),
            _cov(macro_row, "Macro (FRED)"),
            _cov(cpi_row,   "CPI (FRED)"),
            _cov(vxf_row,   "VIX Futures"),
            _cov(fomc_row,  "FOMC Calendar"),
        ]
        global_cols = [
            _col("Dataset", width=180),
            _col("From",    width=120),
            _col("To",      width=120),
            _col("Rows",    width=100, numeric=True),
        ]

        return html.Div([
            html.P("Per-ticker", style={"color": T.TEXT_MUTED, "fontSize": "12px",
                                        "marginBottom": "6px"}),
            dag.AgGrid(
                rowData=ticker_data,
                columnDefs=ticker_cols,
                defaultColDef={"resizable": True},
                className=T.AGGRID_THEME,
                style={"height": "260px", "width": "100%", "marginBottom": "16px"},
            ),
            html.P("Global datasets", style={"color": T.TEXT_MUTED, "fontSize": "12px",
                                              "marginBottom": "6px"}),
            dag.AgGrid(
                rowData=global_data,
                columnDefs=global_cols,
                defaultColDef={"resizable": True},
                className=T.AGGRID_THEME,
                style={"height": "230px", "width": "100%"},
            ),
        ])

    except Exception as e:
        return html.Div(f"Could not load coverage: {e}",
                        style={"color": T.DANGER, "fontSize": "13px"})


def _build_validation(val_ticker: str) -> html.Div:
    if not val_ticker:
        return html.Div()
    try:
        from db.loader import validate_training_data
        report = validate_training_data(val_ticker)
    except Exception as e:
        return html.Div(f"Validation error: {e}", style={"color": T.DANGER, "fontSize": "13px"})

    parts: list = []
    if report.get("issues"):
        for issue in report["issues"]:
            parts.append(dbc.Alert(f"BLOCKER: {issue}", color="danger",
                                   style={"fontSize": "13px", "padding": "8px 12px"}))
    if not report.get("issues") and report.get("warnings"):
        parts.append(dbc.Alert(
            f"{val_ticker} price data is ready for training, but some data is missing.",
            color="warning", style={"fontSize": "13px", "padding": "8px 12px"},
        ))
    if not report.get("issues") and not report.get("warnings"):
        parts.append(dbc.Alert(
            f"{val_ticker} data is ready for training.",
            color="success", style={"fontSize": "13px", "padding": "8px 12px"},
        ))

    for w in report.get("warnings", []):
        parts.append(html.Div(f"Warning: {w}",
                               style={"color": T.WARNING, "fontSize": "12px",
                                      "marginBottom": "4px"}))

    cov = report.get("coverage", {})
    if cov:
        cov_rows = []
        for label, vals in cov.items():
            mn, mx, cnt = vals
            rows_str = f"{cnt:,}" if isinstance(cnt, int) and cnt > 0 else str(cnt)
            cov_rows.append({"Data": label, "From": str(mn), "To": str(mx), "Rows": rows_str})
        cov_cols = [
            _col("Data", width=180),
            _col("From", width=120),
            _col("To",   width=120),
            _col("Rows", width=100, numeric=True),
        ]
        parts.append(dag.AgGrid(
            rowData=cov_rows,
            columnDefs=cov_cols,
            defaultColDef={"resizable": True},
            className=T.AGGRID_THEME,
            style={"height": str(40 + len(cov_rows) * 40) + "px", "width": "100%",
                   "marginTop": "12px"},
        ))

    return html.Div(parts)


# Sync button → status callbacks (one per data type)
_SYNC_BUTTONS = [
    ("tools-dm-btn-price",    "tools-dm-st-price",    "tools-dm-cap-price",    "price"),
    ("tools-dm-btn-news",     "tools-dm-st-news",     "tools-dm-cap-news",     "news"),
    ("tools-dm-btn-options",  "tools-dm-st-options",  "tools-dm-cap-options",  "options"),
    ("tools-dm-btn-divs",     "tools-dm-st-divs",     "tools-dm-cap-divs",     "divs"),
    ("tools-dm-btn-earnings", "tools-dm-st-earnings", "tools-dm-cap-earnings", "earnings"),
    ("tools-dm-btn-eps",      "tools-dm-st-eps",      "tools-dm-cap-eps",      "eps_estimates"),
    ("tools-dm-btn-treasury", "tools-dm-st-treasury", "tools-dm-cap-treasury", "treasury"),
    ("tools-dm-btn-vix",      "tools-dm-st-vix",      "tools-dm-cap-vix",      "vix"),
    ("tools-dm-btn-macro",    "tools-dm-st-macro",    "tools-dm-cap-macro",    "macro"),
    ("tools-dm-btn-cpi",      "tools-dm-st-cpi",      "tools-dm-cap-cpi",      "cpi"),
    ("tools-dm-btn-fomc",     "tools-dm-st-fomc",     "tools-dm-cap-fomc",     "fomc"),
]


def _register_sync_callback(btn_id, st_id, cap_id, dtype):
    @callback(
        Output(st_id,  "children"),
        Output(cap_id, "children"),
        Input(btn_id,  "n_clicks"),
        State("tools-dm-ticker",    "value"),
        State("tools-dm-from-date", "value"),
        State("tools-dm-force-full","value"),
        State("tools-dm-av-key",    "value"),
        prevent_initial_call=True,
    )
    def _cb(n, ticker, from_date, force, av_key, _dt=dtype):
        if not n:
            return no_update, no_update
        t = (ticker or "").strip().upper()
        fd = from_date or "2020-01-01"
        av = av_key or ""
        status, cap = _run_sync(_dt, t, fd, force or [], av)
        return status, cap


for _btn, _st, _cap, _dt in _SYNC_BUTTONS:
    _register_sync_callback(_btn, _st, _cap, _dt)


@callback(
    Output("tools-dm-st-price",    "children", allow_duplicate=True),
    Output("tools-dm-st-news",     "children", allow_duplicate=True),
    Output("tools-dm-st-divs",     "children", allow_duplicate=True),
    Output("tools-dm-st-earnings", "children", allow_duplicate=True),
    Output("tools-dm-st-treasury", "children", allow_duplicate=True),
    Output("tools-dm-st-vix",      "children", allow_duplicate=True),
    Output("tools-dm-st-macro",    "children", allow_duplicate=True),
    Output("tools-dm-st-cpi",      "children", allow_duplicate=True),
    Output("tools-dm-st-fomc",     "children", allow_duplicate=True),
    Input("tools-dm-sync-all", "n_clicks"),
    State("tools-dm-ticker",    "value"),
    State("tools-dm-from-date", "value"),
    State("tools-dm-force-full","value"),
    prevent_initial_call=True,
)
def _sync_all(n, ticker, from_date, force):
    if not n:
        return [no_update] * 9
    t  = (ticker or "").strip().upper()
    fd = from_date or "2020-01-01"
    fr = force or []
    results = []
    for dt in ("price", "news", "divs", "earnings",
               "treasury", "vix", "macro", "cpi", "fomc"):
        s, _ = _run_sync(dt, t, fd, fr)
        results.append(s)
    return results


@callback(
    Output("tools-dm-coverage-tables", "children"),
    Input("tools-dm-refresh-cov", "n_clicks"),
    prevent_initial_call=True,
)
def _refresh_coverage(n):
    if not n:
        return no_update
    return _build_coverage_tables()


@callback(
    Output("tools-dm-val-result", "children"),
    Input("tools-dm-validate-btn", "n_clicks"),
    State("tools-dm-val-ticker", "value"),
    prevent_initial_call=True,
)
def _validate(n, val_ticker):
    if not n:
        return no_update
    return _build_validation((val_ticker or "").strip().upper())


# ═══════════════════════════════════════════════════════════════════════════════
# Callbacks — IV Metrics
# ═══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("tools-iv-content", "children"),
    Input("tools-iv-run-btn", "n_clicks"),
    State("tools-iv-tickers",  "value"),
    State("tools-iv-api-key",  "value"),
    prevent_initial_call=True,
)
def _run_iv_scan(n, tickers_str, user_api_key):
    if not n:
        return no_update

    api_key = get_polygon_api_key(user_api_key or "")
    if not api_key:
        return dbc.Alert("Polygon API key required — set in .env or enter above.",
                         color="warning", style={"fontSize": "13px"})

    raw = [t.strip().upper() for t in (tickers_str or "").split(",") if t.strip()]
    if not raw:
        return dbc.Alert("Enter at least one ticker.", color="warning",
                         style={"fontSize": "13px"})

    try:
        from engine.iv_metrics import get_iv_metrics_batch
        from engine.screener import _fetch_ohlcv

        price_dfs = {}
        for tk in raw:
            try:
                df = _fetch_ohlcv(tk, api_key)
                if df is not None and not df.empty:
                    price_dfs[tk] = df
            except Exception:
                pass

        metrics = get_iv_metrics_batch(
            tickers=raw,
            api_key=api_key,
            price_dfs=price_dfs,
            fetch_ivr_history=True,
        )
    except Exception as e:
        return dbc.Alert(f"IV scan error: {e}", color="danger",
                         style={"fontSize": "13px"})

    # ── Build summary table ───────────────────────────────────────────────────
    rows = []
    for tk in raw:
        m = metrics.get(tk, {})

        def _p(v):
            if v is None:
                return "—"
            try:
                return f"{float(v)*100:.1f}%"
            except Exception:
                return "—"

        def _f2(v):
            if v is None:
                return "—"
            try:
                return f"{float(v):.2f}"
            except Exception:
                return "—"

        rows.append({
            "Ticker":    tk,
            "ATM IV":    _p(m.get("atm_iv")),
            "IVR":       _p(m.get("ivr")),
            "HV20":      _p(m.get("hv20")),
            "VRP":       _p(m.get("vrp")),
            "IV/HV":     _f2(m.get("iv_over_hv")),
            "DTE":       str(m.get("dte_used") or "—"),
            "Strike":    _f2(m.get("atm_strike")),
            "Conf":      m.get("ivr_confidence", "—"),
            "Source":    m.get("iv_source", "—"),
            "Error":     m.get("error") or "",
        })

    tbl_cols = [
        {"field": "Ticker",  "width": 80,  "resizable": True, "sortable": True, "filter": True},
        {"field": "ATM IV",  "minWidth": 85,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "IVR",     "minWidth": 75,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "HV20",    "minWidth": 75,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "VRP",     "minWidth": 75,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "IV/HV",   "minWidth": 75,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "DTE",     "minWidth": 65,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "Strike",  "minWidth": 85,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "Conf",    "minWidth": 80,  "flex": 1, "resizable": True, "sortable": True, "filter": True},
        {"field": "Source",  "minWidth": 160, "flex": 2, "resizable": True, "sortable": True, "filter": True},
        {"field": "Error",   "minWidth": 120, "flex": 2, "resizable": True, "sortable": True, "filter": True},
    ]

    summary_grid = dag.AgGrid(
        rowData=rows,
        columnDefs=tbl_cols,
        defaultColDef={"resizable": True},
        className=T.AGGRID_THEME,
        dashGridOptions={"suppressColumnVirtualisation": True},
        style={"height": str(60 + len(rows) * 42) + "px", "width": "100%",
               "marginBottom": "24px"},
    )

    # ── IV vs HV bar chart ────────────────────────────────────────────────────
    chart_tickers = [r["Ticker"] for r in rows]
    atm_ivs = []
    hv20s   = []
    for tk in chart_tickers:
        m = metrics[tk]
        atm_ivs.append(round(m["atm_iv"] * 100, 1) if m.get("atm_iv") is not None else None)
        hv20s.append(round(m["hv20"]   * 100, 1) if m.get("hv20")   is not None else None)

    fig_iv_hv = go.Figure()
    fig_iv_hv.add_trace(go.Bar(
        name="ATM IV",
        x=chart_tickers,
        y=atm_ivs,
        marker_color=T.ACCENT,
        opacity=0.85,
    ))
    fig_iv_hv.add_trace(go.Bar(
        name="HV20",
        x=chart_tickers,
        y=hv20s,
        marker_color=T.SUCCESS,
        opacity=0.75,
    ))
    fig_iv_hv.update_layout(
        barmode="group",
        title="ATM IV vs HV20 (%)",
        paper_bgcolor=T.BG_CARD,
        plot_bgcolor=T.BG_CARD,
        template="plotly_dark",
        font={"color": T.TEXT_PRIMARY, "size": 12},
        legend={"font": {"color": T.TEXT_SEC}},
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        yaxis={"title": "Volatility (%)", "gridcolor": T.BORDER},
        xaxis={"gridcolor": T.BORDER},
        height=300,
    )

    # ── IVR bar chart ─────────────────────────────────────────────────────────
    ivr_vals = []
    ivr_colors = []
    for tk in chart_tickers:
        m = metrics[tk]
        ivr = m.get("ivr")
        ivr_vals.append(round(ivr * 100, 1) if ivr is not None else None)
        if ivr is None:
            ivr_colors.append(T.BORDER_BRT)
        elif ivr >= 0.7:
            ivr_colors.append(T.DANGER)
        elif ivr >= 0.5:
            ivr_colors.append(T.WARNING)
        else:
            ivr_colors.append(T.SUCCESS)

    fig_ivr = go.Figure()
    fig_ivr.add_trace(go.Bar(
        name="IVR",
        x=chart_tickers,
        y=ivr_vals,
        marker_color=ivr_colors,
        opacity=0.85,
    ))
    fig_ivr.add_hline(y=50, line_dash="dash", line_color=T.TEXT_MUTED,
                      annotation_text="50% threshold")
    fig_ivr.update_layout(
        title="IV Rank (IVR %)",
        paper_bgcolor=T.BG_CARD,
        plot_bgcolor=T.BG_CARD,
        template="plotly_dark",
        font={"color": T.TEXT_PRIMARY, "size": 12},
        legend={"font": {"color": T.TEXT_SEC}},
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        yaxis={"title": "IVR (%)", "range": [0, 110], "gridcolor": T.BORDER},
        xaxis={"gridcolor": T.BORDER},
        height=280,
    )

    # ── VRP chart ─────────────────────────────────────────────────────────────
    vrp_vals = []
    vrp_colors = []
    for tk in chart_tickers:
        m = metrics[tk]
        vrp = m.get("vrp")
        vrp_vals.append(round(vrp * 100, 1) if vrp is not None else None)
        if vrp is None:
            vrp_colors.append(T.BORDER_BRT)
        elif vrp > 0:
            vrp_colors.append(T.SUCCESS)
        else:
            vrp_colors.append(T.DANGER)

    fig_vrp = go.Figure()
    fig_vrp.add_trace(go.Bar(
        name="VRP",
        x=chart_tickers,
        y=vrp_vals,
        marker_color=vrp_colors,
        opacity=0.85,
    ))
    fig_vrp.add_hline(y=0, line_color=T.TEXT_MUTED)
    fig_vrp.update_layout(
        title="Variance Risk Premium = IV − HV20 (%)",
        paper_bgcolor=T.BG_CARD,
        plot_bgcolor=T.BG_CARD,
        template="plotly_dark",
        font={"color": T.TEXT_PRIMARY, "size": 12},
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        yaxis={"title": "VRP (%)", "gridcolor": T.BORDER},
        xaxis={"gridcolor": T.BORDER},
        height=260,
    )

    return html.Div([
        summary_grid,
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_iv_hv, config={"displayModeBar": False})),
                 style={**T.STYLE_CARD, "marginBottom": "16px"}),
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_ivr,   config={"displayModeBar": False})),
                 style={**T.STYLE_CARD, "marginBottom": "16px"}),
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_vrp,   config={"displayModeBar": False})),
                 style={**T.STYLE_CARD}),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# Callbacks — Guide
# ═══════════════════════════════════════════════════════════════════════════════

@callback(
    Output("tools-guide-content", "children"),
    Input("tools-guide-select", "value"),
)
def _render_guide(slug):
    if not slug:
        return html.Div("Select an article above.",
                        style={"color": T.TEXT_MUTED, "fontSize": "13px"})
    md_path = _GUIDE_DIR / f"{slug}.md"
    if not md_path.exists():
        return html.Div(f"Article not found: {slug}",
                        style={"color": T.DANGER, "fontSize": "13px"})
    content = md_path.read_text(encoding="utf-8")

    md = dcc.Markdown(
        content,
        className="guide-md",
        style={"color": T.TEXT_PRIMARY, "fontSize": "14px", "lineHeight": "1.75"},
    )

    # ── Per-article interactive charts ────────────────────────────────────────
    _GUIDE_CHART_MODULES = {
        "vol_arbitrage":         "dash_app.guide_charts.vol_arbitrage_charts",
        "iron_condor":           "dash_app.guide_charts.iron_condor_charts",
        "iron_condor_weekly":    "dash_app.guide_charts.iron_condor_charts",
        "iron_condor_rules":     "dash_app.guide_charts.iron_condor_charts",
        "bull_put_spread":       "dash_app.guide_charts.bull_put_spread_charts",
        "bear_call_spread":      "dash_app.guide_charts.bull_put_spread_charts",
        "earnings_iv_crush":     "dash_app.guide_charts.earnings_iv_crush_charts",
        "earnings_vol_crush":    "dash_app.guide_charts.earnings_iv_crush_charts",
        "earnings_straddle":     "dash_app.guide_charts.earnings_iv_crush_charts",
        "pairs_spy_qqq":         "dash_app.guide_charts.pairs_spy_qqq_charts",
        "pairs_spy_iwm":         "dash_app.guide_charts.pairs_spy_qqq_charts",
        "pairs_spy_dia":         "dash_app.guide_charts.pairs_spy_qqq_charts",
        "stat_arb_etf_basket":   "dash_app.guide_charts.stat_arb_etf_basket_charts",
        "vix_mean_reversion":    "dash_app.guide_charts.vix_mean_reversion_charts",
        "vix_spike_fade":        "dash_app.guide_charts.vix_mean_reversion_charts",
        "momentum_factor":       "dash_app.guide_charts.momentum_factor_charts",
        "momentum_12_1":         "dash_app.guide_charts.momentum_factor_charts",
        "momentum_cross_sector": "dash_app.guide_charts.momentum_factor_charts",
    }

    extra: list = []
    module_path = _GUIDE_CHART_MODULES.get(slug)
    if module_path:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            extra.append(mod.render_charts())
        except Exception as e:
            logger.warning("Guide charts failed for %s: %s", slug, e)

    return html.Div([md, *extra])


# ═══════════════════════════════════════════════════════════════════════════════
# Callbacks — Polygon Explorer
# ═══════════════════════════════════════════════════════════════════════════════

def _get_px_client(user_key: str | None):
    """Build a PolygonClient, preferring user-supplied key then .env."""
    from data.polygon_client import PolygonClient
    key = get_polygon_api_key(user_key or "")
    if not key:
        raise ValueError("No Polygon API key — set POLYGON_API_KEY in .env or enter above.")
    return PolygonClient(api_key=key)


def _px_error(msg: str) -> html.Div:
    return dbc.Alert(str(msg), color="danger",
                     style={"fontSize": "13px", "marginTop": "8px"})


def _px_df_grid(df, height: int = 300) -> dag.AgGrid:
    """Render a DataFrame as an AG Grid."""
    cols = [{"field": c, "resizable": True, "sortable": True, "filter": True,
              "minWidth": 80, "flex": 1} for c in df.columns]
    return dag.AgGrid(
        rowData=df.astype(str).to_dict("records"),
        columnDefs=cols,
        defaultColDef={"resizable": True},
        className=T.AGGRID_THEME,
        style={"height": f"{height}px", "width": "100%"},
    )


# ── API key test ──────────────────────────────────────────────────────────────

@callback(
    Output("tools-px-test-result", "children"),
    Input("tools-px-test-btn", "n_clicks"),
    State("tools-px-api-key", "value"),
    prevent_initial_call=True,
)
def _px_test_key(n, api_key):
    if not n:
        return no_update
    try:
        client = _get_px_client(api_key)
        snap = client.get_snapshot("SPY")
        price = snap.get("day", {}).get("c") or snap.get("lastTrade", {}).get("p", "?")
        return html.Span(f"Key valid — SPY last: {price}",
                         style={"color": T.SUCCESS, "fontSize": "13px"})
    except Exception as e:
        return _px_error(f"Key test failed: {e}")


# ── Market Snapshot ───────────────────────────────────────────────────────────

@callback(
    Output("tools-px-snap-content", "children"),
    Input("tools-px-snap-btn", "n_clicks"),
    State("tools-px-ticker", "value"),
    State("tools-px-api-key", "value"),
    prevent_initial_call=True,
)
def _px_snapshot(n, ticker, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        snap = client.get_snapshot(tk)
    except Exception as e:
        return _px_error(e)

    day  = snap.get("day", {}) or {}
    prev = snap.get("prevDay", {}) or {}
    chg_pct = snap.get("todaysChangePerc")
    price = day.get("c") or snap.get("lastTrade", {}).get("p", "—")
    vol   = day.get("v", "—")
    hi    = day.get("h", "—")
    lo    = day.get("l", "—")

    cards = html.Div([
        _metric_card("Price",   f"{price}"),
        _metric_card("Change%", f"{chg_pct:.2f}%" if chg_pct is not None else "—"),
        _metric_card("Volume",  f"{int(vol):,}"   if isinstance(vol, (int, float)) else str(vol)),
        _metric_card("High",    f"{hi}"),
        _metric_card("Low",     f"{lo}"),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "12px"})

    # flatten snap dict for table
    flat = {}
    for k, v in snap.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                flat[f"{k}.{k2}"] = v2
        else:
            flat[k] = v
    import pandas as pd
    df = pd.DataFrame([{"Key": k, "Value": str(v)} for k, v in flat.items()])
    return html.Div([cards, _px_df_grid(df, height=280)])


# ── OHLCV Bars ────────────────────────────────────────────────────────────────

@callback(
    Output("tools-px-bars-content", "children"),
    Input("tools-px-bars-btn", "n_clicks"),
    State("tools-px-ticker",       "value"),
    State("tools-px-bars-mult",    "value"),
    State("tools-px-bars-timespan","value"),
    State("tools-px-bars-from",    "value"),
    State("tools-px-bars-to",      "value"),
    State("tools-px-api-key",      "value"),
    prevent_initial_call=True,
)
def _px_bars(n, ticker, mult, timespan, from_date, to_date, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        df = client.get_aggregates(
            ticker=tk,
            from_date=from_date or (date.today() - timedelta(days=30)).isoformat(),
            to_date=to_date or date.today().isoformat(),
            timespan=timespan or "day",
            multiplier=int(mult or 1),
        )
    except Exception as e:
        return _px_error(e)
    if df.empty:
        return _px_error("No data returned.")

    df = df.reset_index()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["date"].astype(str),
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name=tk,
    ))
    fig.update_layout(
        title=f"{tk} OHLCV ({timespan})",
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        template="plotly_dark",
        font={"color": T.TEXT_PRIMARY, "size": 12},
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        height=360,
        xaxis_rangeslider_visible=False,
    )
    return html.Div([
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
        _px_df_grid(df.tail(100), height=260),
    ])


# ── Technical Indicators ──────────────────────────────────────────────────────

@callback(
    Output("tools-px-ind-content", "children"),
    Input("tools-px-ind-btn", "n_clicks"),
    State("tools-px-ticker",      "value"),
    State("tools-px-ind-type",    "value"),
    State("tools-px-ind-window",  "value"),
    State("tools-px-ind-timespan","value"),
    State("tools-px-ind-from",    "value"),
    State("tools-px-ind-to",      "value"),
    State("tools-px-api-key",     "value"),
    prevent_initial_call=True,
)
def _px_indicators(n, ticker, ind_type, window, timespan, from_date, to_date, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        result = client.get_technical_indicator(
            ticker=tk,
            indicator=ind_type or "rsi",
            from_date=from_date or (date.today() - timedelta(days=30)).isoformat(),
            to_date=to_date or date.today().isoformat(),
            window=int(window or 14),
            timespan=timespan or "day",
        )
    except Exception as e:
        return _px_error(e)

    import pandas as pd
    if isinstance(result, pd.Series):
        df = result.reset_index()
        df.columns = ["date", ind_type or "value"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["date"].astype(str), y=df.iloc[:, 1],
                                  mode="lines", name=(ind_type or "value").upper(),
                                  line={"color": T.ACCENT}))
    elif isinstance(result, pd.DataFrame):
        df = result.reset_index()
        fig = go.Figure()
        for col in [c for c in df.columns if c != "date"]:
            fig.add_trace(go.Scatter(x=df["date"].astype(str), y=df[col],
                                      mode="lines", name=col))
    else:
        return _px_error("Unexpected result format.")

    fig.update_layout(
        title=f"{tk} {(ind_type or 'indicator').upper()}(window={window})",
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        template="plotly_dark",
        font={"color": T.TEXT_PRIMARY, "size": 12},
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        height=300,
    )
    return html.Div([
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
        _px_df_grid(df.tail(100), height=240),
    ])


# ── Options Expirations ───────────────────────────────────────────────────────

@callback(
    Output("tools-px-exp-content", "children"),
    Input("tools-px-exp-btn", "n_clicks"),
    State("tools-px-ticker",  "value"),
    State("tools-px-api-key", "value"),
    prevent_initial_call=True,
)
def _px_expirations(n, ticker, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        exps = client.get_expirations(tk, as_of=date.today().isoformat())
    except Exception as e:
        return _px_error(e)
    if not exps:
        return _px_error("No expirations found.")
    import pandas as pd
    df = pd.DataFrame({"Expiration": exps})
    return _px_df_grid(df, height=min(40 + len(exps) * 40, 400))


# ── Load expirations → store → populate dropdown ──────────────────────────────

@callback(
    Output("tools-px-expirations-store", "data"),
    Input("tools-px-load-exp-btn", "n_clicks"),
    State("tools-px-ticker",  "value"),
    State("tools-px-api-key", "value"),
    prevent_initial_call=True,
)
def _px_load_expirations(n, ticker, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return []
    try:
        client = _get_px_client(api_key)
        return client.get_expirations(tk, as_of=date.today().isoformat())
    except Exception:
        return []


@callback(
    Output("tools-px-chain-exp", "options"),
    Output("tools-px-chain-exp", "value"),
    Input("tools-px-expirations-store", "data"),
    prevent_initial_call=True,
)
def _px_populate_exp_dropdown(exps):
    if not exps:
        return [], None
    opts = [{"label": e, "value": e} for e in exps]
    return opts, exps[0]


# ── Options Chain ─────────────────────────────────────────────────────────────

@callback(
    Output("tools-px-chain-content", "children"),
    Input("tools-px-chain-btn", "n_clicks"),
    State("tools-px-ticker",            "value"),
    State("tools-px-chain-exp",         "value"),
    State("tools-px-chain-type",        "value"),
    State("tools-px-chain-strike-range","value"),
    State("tools-px-chain-historical",  "value"),
    State("tools-px-chain-date",        "value"),
    State("tools-px-api-key",           "value"),
    prevent_initial_call=True,
)
def _px_chain(n, ticker, expiration, contract_type, strike_range,
              historical, hist_date, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    if not expiration:
        return _px_error("Load and select an expiration.")

    snapshot_date = hist_date if historical else None

    try:
        client = _get_px_client(api_key)
        # Get current spot to compute strike range
        snap = client.get_snapshot(tk)
        spot = (snap.get("day", {}) or {}).get("c") or (snap.get("lastTrade", {}) or {}).get("p")
        spot = float(spot) if spot else None

        kwargs = {"expiration_date": expiration}
        if snapshot_date:
            kwargs["snapshot_date"] = snapshot_date
        if spot and strike_range:
            lo_pct, hi_pct = strike_range
            kwargs["strike_price_gte"] = round(spot * lo_pct / 100, 2)
            kwargs["strike_price_lte"] = round(spot * hi_pct / 100, 2)

        df = client.get_options_chain(tk, **kwargs)
    except Exception as e:
        return _px_error(e)

    if df.empty:
        return _px_error("No chain data returned.")

    # Filter by contract type
    if contract_type and contract_type != "all":
        df = df[df["type"] == contract_type]

    import pandas as pd
    import numpy as np

    # ── Metric cards ─────────────────────────────────────────────────────────
    dte_val = df["dte"].median() if "dte" in df.columns and not df["dte"].isna().all() else None
    calls = df[df["type"] == "call"] if "type" in df.columns else pd.DataFrame()
    puts  = df[df["type"] == "put"]  if "type" in df.columns else pd.DataFrame()
    c_oi  = calls["open_interest"].sum() if not calls.empty and "open_interest" in calls.columns else 0
    p_oi  = puts["open_interest"].sum()  if not puts.empty  and "open_interest" in puts.columns  else 0
    pc_ratio = f"{p_oi/c_oi:.2f}" if c_oi else "—"

    # ATM IV
    atm_iv_c = atm_iv_p = None
    if spot and not calls.empty and "strike" in calls.columns and "iv" in calls.columns:
        c_atm = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]
        atm_iv_c = c_atm["iv"].values[0] if not c_atm.empty else None
    if spot and not puts.empty and "strike" in puts.columns and "iv" in puts.columns:
        p_atm = puts.iloc[(puts["strike"] - spot).abs().argsort()[:1]]
        atm_iv_p = p_atm["iv"].values[0] if not p_atm.empty else None
    atm_iv_str = (
        f"C {atm_iv_c*100:.1f}% / P {atm_iv_p*100:.1f}%"
        if atm_iv_c is not None and atm_iv_p is not None
        else "—"
    )

    # Max pain
    max_pain_strike = None
    if "strike" in df.columns and "open_interest" in df.columns:
        strikes = sorted(df["strike"].dropna().unique())
        pain = {}
        for s in strikes:
            c_pain = calls[calls["strike"] >= s]["open_interest"].fillna(0).sum() * (calls[calls["strike"] >= s]["strike"] - s).fillna(0).values
            p_pain = puts[puts["strike"] <= s]["open_interest"].fillna(0).sum() * (s - puts[puts["strike"] <= s]["strike"]).fillna(0).values
            pain[s] = float(np.sum(c_pain)) + float(np.sum(p_pain))
        if pain:
            max_pain_strike = min(pain, key=pain.get)

    cards = html.Div([
        _metric_card("Spot",        f"{spot:.2f}" if spot else "—"),
        _metric_card("DTE",         f"{int(dte_val)}" if dte_val is not None else "—"),
        _metric_card("P/C OI Ratio",pc_ratio),
        _metric_card("ATM IV (C/P)",atm_iv_str),
        _metric_card("Max Pain",    f"{max_pain_strike:.0f}" if max_pain_strike else "—"),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "16px"})

    # ── IV Smile chart ────────────────────────────────────────────────────────
    fig_smile = go.Figure()
    if not calls.empty and "strike" in calls.columns and "iv" in calls.columns:
        c_sorted = calls.dropna(subset=["strike", "iv"]).sort_values("strike")
        fig_smile.add_trace(go.Scatter(
            x=c_sorted["strike"], y=c_sorted["iv"] * 100,
            mode="lines+markers", name="Call IV",
            line={"color": T.SUCCESS},
        ))
    if not puts.empty and "strike" in puts.columns and "iv" in puts.columns:
        p_sorted = puts.dropna(subset=["strike", "iv"]).sort_values("strike")
        fig_smile.add_trace(go.Scatter(
            x=p_sorted["strike"], y=p_sorted["iv"] * 100,
            mode="lines+markers", name="Put IV",
            line={"color": T.DANGER},
        ))
    if spot:
        fig_smile.add_vline(x=spot, line_dash="dash", line_color=T.TEXT_MUTED,
                             annotation_text="Spot")
    fig_smile.update_layout(
        title=f"{tk} IV Smile — {expiration}",
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        template="plotly_dark",
        font={"color": T.TEXT_PRIMARY, "size": 12},
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        height=300,
        xaxis={"title": "Strike", "gridcolor": T.BORDER},
        yaxis={"title": "IV (%)",  "gridcolor": T.BORDER},
    )

    # ── OI chart ──────────────────────────────────────────────────────────────
    fig_oi = go.Figure()
    if not calls.empty and "strike" in calls.columns and "open_interest" in calls.columns:
        c_oi_df = calls.dropna(subset=["strike"]).sort_values("strike")
        fig_oi.add_trace(go.Bar(
            x=c_oi_df["strike"], y=c_oi_df["open_interest"].fillna(0),
            name="Call OI", marker_color=T.SUCCESS, opacity=0.7,
        ))
    if not puts.empty and "strike" in puts.columns and "open_interest" in puts.columns:
        p_oi_df = puts.dropna(subset=["strike"]).sort_values("strike")
        fig_oi.add_trace(go.Bar(
            x=p_oi_df["strike"], y=p_oi_df["open_interest"].fillna(0),
            name="Put OI", marker_color=T.DANGER, opacity=0.7,
        ))
    if max_pain_strike:
        fig_oi.add_vline(x=max_pain_strike, line_dash="dot", line_color=T.WARNING,
                          annotation_text=f"Max Pain {max_pain_strike:.0f}")
    fig_oi.update_layout(
        title=f"{tk} Open Interest — {expiration}",
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        template="plotly_dark",
        barmode="overlay",
        font={"color": T.TEXT_PRIMARY, "size": 12},
        margin={"t": 40, "b": 40, "l": 40, "r": 20},
        height=280,
        xaxis={"title": "Strike", "gridcolor": T.BORDER},
        yaxis={"title": "Open Interest", "gridcolor": T.BORDER},
    )

    # ── Chain grid ────────────────────────────────────────────────────────────
    chain_display = df.copy()
    if "iv" in chain_display.columns:
        chain_display["IV%"] = chain_display["iv"].apply(
            lambda v: f"{v*100:.1f}%" if v is not None and not (isinstance(v, float) and np.isnan(v)) else "—"
        )
    for col in ["bid", "ask", "delta", "gamma", "theta", "vega"]:
        if col in chain_display.columns:
            chain_display[col] = chain_display[col].apply(
                lambda v: f"{v:.4f}" if v is not None and not (isinstance(v, float) and np.isnan(v)) else "—"
            )
    if "bid" in chain_display.columns and "ask" in chain_display.columns:
        chain_display["Mid"] = chain_display.apply(
            lambda r: f"{(float(r['bid'].replace('—','nan')) + float(r['ask'].replace('—','nan')))/2:.4f}"
            if r["bid"] != "—" and r["ask"] != "—" else "—", axis=1
        )
        chain_display["Spread"] = chain_display.apply(
            lambda r: f"{float(r['ask'].replace('—','nan')) - float(r['bid'].replace('—','nan')):.4f}"
            if r["bid"] != "—" and r["ask"] != "—" else "—", axis=1
        )

    display_cols_order = ["strike", "type", "bid", "ask", "Mid", "Spread",
                           "IV%", "delta", "gamma", "theta", "vega",
                           "open_interest", "volume"]
    display_cols_order = [c for c in display_cols_order if c in chain_display.columns]
    rename_map = {
        "strike": "Strike", "type": "Type", "bid": "Bid", "ask": "Ask",
        "delta": "Delta", "gamma": "Gamma", "theta": "Theta", "vega": "Vega",
        "open_interest": "OI", "volume": "Volume",
    }
    chain_display = chain_display[display_cols_order].rename(columns=rename_map)

    chain_cols = [{"field": c, "resizable": True, "sortable": True, "filter": True,
                   "minWidth": 70, "flex": 1} for c in chain_display.columns]
    chain_grid = dag.AgGrid(
        rowData=chain_display.astype(str).to_dict("records"),
        columnDefs=chain_cols,
        defaultColDef={"resizable": True},
        className=T.AGGRID_THEME,
        dashGridOptions={"suppressColumnVirtualisation": True},
        style={"height": "400px", "width": "100%"},
    )

    return html.Div([
        cards,
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_smile, config={"displayModeBar": False})),
                 style={**T.STYLE_CARD, "marginBottom": "12px"}),
        dbc.Card(dbc.CardBody(dcc.Graph(figure=fig_oi, config={"displayModeBar": False})),
                 style={**T.STYLE_CARD, "marginBottom": "12px"}),
        chain_grid,
    ])


# ── Ticker Details ────────────────────────────────────────────────────────────

@callback(
    Output("tools-px-details-content", "children"),
    Input("tools-px-details-btn", "n_clicks"),
    State("tools-px-ticker",  "value"),
    State("tools-px-api-key", "value"),
    prevent_initial_call=True,
)
def _px_details(n, ticker, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        data = client._get(f"/v3/reference/tickers/{tk}")
        info = data.get("results", {})
    except Exception as e:
        return _px_error(e)
    if not info:
        return _px_error("No details found.")
    import pandas as pd
    df = pd.DataFrame([{"Field": k, "Value": str(v)} for k, v in info.items()])
    return _px_df_grid(df, height=min(40 + len(df) * 40, 500))


# ── News ──────────────────────────────────────────────────────────────────────

@callback(
    Output("tools-px-news-content", "children"),
    Input("tools-px-news-btn", "n_clicks"),
    State("tools-px-ticker",    "value"),
    State("tools-px-news-from", "value"),
    State("tools-px-news-to",   "value"),
    State("tools-px-news-max",  "value"),
    State("tools-px-api-key",   "value"),
    prevent_initial_call=True,
)
def _px_news(n, ticker, from_date, to_date, max_art, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        df = client.get_news(
            ticker=tk,
            from_date=from_date or (date.today() - timedelta(days=30)).isoformat(),
            to_date=to_date or date.today().isoformat(),
            limit=int(max_art or 20),
        )
    except Exception as e:
        return _px_error(e)
    if df.empty:
        return _px_error("No news found.")
    show_cols = [c for c in ["date", "published_utc", "title", "description"] if c in df.columns]
    return _px_df_grid(df[show_cols].head(int(max_art or 20)), height=360)


# ── EPS Financials ────────────────────────────────────────────────────────────

@callback(
    Output("tools-px-fin-content", "children"),
    Input("tools-px-fin-btn", "n_clicks"),
    State("tools-px-ticker",       "value"),
    State("tools-px-fin-timeframe","value"),
    State("tools-px-fin-periods",  "value"),
    State("tools-px-api-key",      "value"),
    prevent_initial_call=True,
)
def _px_financials(n, ticker, timeframe, periods, api_key):
    if not n:
        return no_update
    tk = (ticker or "").strip().upper()
    if not tk:
        return _px_error("Enter a ticker.")
    try:
        client = _get_px_client(api_key)
        params = {
            "ticker": tk,
            "timeframe": timeframe or "quarterly",
            "limit": int(periods or 8),
            "order": "desc",
            "include_sources": "false",
        }
        data = client._get("/vX/reference/financials", params)
        results = data.get("results", [])
    except Exception as e:
        return _px_error(e)
    if not results:
        return _px_error("No financial data found.")

    import pandas as pd
    rows = []
    for r in results:
        fin = r.get("financials", {})
        ic  = fin.get("income_statement", {})
        row = {
            "Period":    r.get("fiscal_period"),
            "End Date":  r.get("end_date"),
            "Revenue":   ic.get("revenues", {}).get("value"),
            "Net Income":ic.get("net_income_loss", {}).get("value"),
            "EPS Basic": ic.get("basic_earnings_per_share", {}).get("value"),
            "EPS Diluted":ic.get("diluted_earnings_per_share", {}).get("value"),
        }
        rows.append(row)
    df = pd.DataFrame(rows)
    return _px_df_grid(df, height=min(40 + len(df) * 42, 400))


# ── Raw API Call ──────────────────────────────────────────────────────────────

@callback(
    Output("tools-px-raw-content", "children"),
    Input("tools-px-raw-btn", "n_clicks"),
    State("tools-px-raw-path",   "value"),
    State("tools-px-raw-params", "value"),
    State("tools-px-api-key",    "value"),
    prevent_initial_call=True,
)
def _px_raw(n, path, params_json, api_key):
    if not n:
        return no_update
    if not path:
        return _px_error("Enter an endpoint path.")
    try:
        client = _get_px_client(api_key)
        try:
            params = json.loads(params_json or "{}")
        except Exception:
            params = {}
        data = client._get(path.strip(), params)
    except Exception as e:
        return _px_error(e)

    import pandas as pd
    # Try to render as a grid if there's a results list
    results = data.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        df = pd.DataFrame(results)
        return html.Div([
            html.Pre(json.dumps({k: v for k, v in data.items() if k != "results"},
                                indent=2),
                     style={"color": T.TEXT_SEC, "fontSize": "11px",
                            "marginBottom": "8px", "whiteSpace": "pre-wrap"}),
            _px_df_grid(df, height=400),
        ])
    # Otherwise show raw JSON
    return html.Pre(
        json.dumps(data, indent=2, default=str),
        style={"color": T.TEXT_PRIMARY, "fontSize": "12px",
               "backgroundColor": T.BG_ELEVATED,
               "border": f"1px solid {T.BORDER}",
               "borderRadius": "6px", "padding": "12px",
               "whiteSpace": "pre-wrap", "maxHeight": "500px",
               "overflowY": "auto"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Layout helper — Risk Management tab
# ═══════════════════════════════════════════════════════════════════════════════

_PORTFOLIO_HISTORY = Path(__file__).parent.parent.parent / "portfolio_history.json"


def _compute_risk_metrics():
    """Load portfolio_history.json and compute VaR/CVaR/Sharpe/Sortino/MaxDD."""
    import numpy as np
    try:
        with open(_PORTFOLIO_HISTORY) as f:
            hist = json.load(f)
        snaps = hist.get("snapshots", [])
        if len(snaps) < 5:
            return None, None
        import pandas as pd
        equity = pd.Series(
            {s["date"]: float(s["equity"]) for s in snaps if s.get("equity")},
            name="equity",
        ).sort_index()
        rets = equity.pct_change().dropna()
        if len(rets) < 5:
            return None, None
        var_95  = float(np.percentile(rets, 5))
        cvar_95 = float(rets[rets <= var_95].mean()) if any(rets <= var_95) else var_95
        rolling_max = equity.cummax()
        drawdowns   = (equity - rolling_max) / rolling_max
        max_dd = float(drawdowns.min())
        ann = np.sqrt(252)
        sharpe  = float(rets.mean() / rets.std() * ann) if rets.std() > 0 else 0.0
        neg     = rets[rets < 0]
        sortino = float(rets.mean() / neg.std() * ann) if len(neg) > 1 else 0.0
        metrics = {
            "var_95":  var_95 * 100,
            "cvar_95": cvar_95 * 100,
            "max_dd":  max_dd * 100,
            "sharpe":  sharpe,
            "sortino": sortino,
        }
        return metrics, (equity, rets, drawdowns)
    except Exception as e:
        logger.warning("Risk metrics error: %s", e)
        return None, None


def _risk_tab() -> html.Div:
    metrics, series = _compute_risk_metrics()

    def _val(m, key, fmt):
        return fmt.format(m[key]) if m else "—"

    def _risk_card(label, value, accent):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                   "fontWeight": "700", "textTransform": "uppercase",
                                   "letterSpacing": "0.07em", "marginBottom": "4px"}),
            html.Div(value, style={"color": accent, "fontSize": "1.3rem",
                                   "fontWeight": "700",
                                   "fontFamily": "JetBrains Mono, monospace"}),
        ], style={"padding": "14px 16px"}), style=T.STYLE_CARD), width="auto")

    var_str    = _val(metrics, "var_95",  "{:.2f}%")
    cvar_str   = _val(metrics, "cvar_95", "{:.2f}%")
    maxdd_str  = _val(metrics, "max_dd",  "{:.1f}%")
    sharpe_str = _val(metrics, "sharpe",  "{:.2f}")
    sort_str   = _val(metrics, "sortino", "{:.2f}")

    cards = dbc.Row([
        _risk_card("VaR 95% (daily)",  var_str,    T.DANGER   if metrics else T.TEXT_MUTED),
        _risk_card("CVaR 95% (daily)", cvar_str,   T.DANGER   if metrics else T.TEXT_MUTED),
        _risk_card("Max Drawdown",     maxdd_str,  T.WARNING if metrics else T.TEXT_MUTED),
        _risk_card("Sharpe Ratio", sharpe_str,
                   T.SUCCESS if metrics and metrics["sharpe"] >= 1 else
                   (T.WARNING if metrics else T.TEXT_MUTED)),
        _risk_card("Sortino Ratio", sort_str,
                   T.SUCCESS if metrics and metrics["sortino"] >= 1.5 else
                   (T.WARNING if metrics else T.TEXT_MUTED)),
    ], className="g-3 mb-4")

    charts_section = html.Div()
    if series is not None:
        equity, rets, drawdowns = series
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=list(equity.index), y=list(equity.values),
            name="Portfolio Equity", line=dict(color=T.ACCENT, width=2),
            fill="tozeroy", fillcolor="rgba(99,102,241,0.08)",
        ))
        fig_eq.update_layout(
            paper_bgcolor=T.BG_BASE, plot_bgcolor=T.BG_ELEVATED,
            font=dict(color=T.TEXT_PRIMARY, family="Inter, sans-serif"),
            height=260, margin=dict(l=50, r=20, t=30, b=40),
            title=dict(text="Portfolio Equity Curve", font=dict(size=13)),
            xaxis=dict(gridcolor=T.BORDER),
            yaxis=dict(gridcolor=T.BORDER, tickprefix="$", tickformat=",.0f"),
            showlegend=False,
        )

        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(
            x=list(drawdowns.index), y=(drawdowns * 100).tolist(),
            name="Drawdown", line=dict(color=T.DANGER, width=1.5),
            fill="tozeroy", fillcolor="rgba(239,68,68,0.12)",
        ))
        fig_dd.update_layout(
            paper_bgcolor=T.BG_BASE, plot_bgcolor=T.BG_ELEVATED,
            font=dict(color=T.TEXT_PRIMARY, family="Inter, sans-serif"),
            height=200, margin=dict(l=50, r=20, t=30, b=40),
            title=dict(text="Drawdown (%)", font=dict(size=13)),
            xaxis=dict(gridcolor=T.BORDER),
            yaxis=dict(gridcolor=T.BORDER, ticksuffix="%"),
            showlegend=False,
        )

        charts_section = dbc.Card(dbc.CardBody([
            _card_header("Equity & Drawdown"),
            html.Hr(style={"borderColor": T.BORDER, "margin": "8px 0 12px"}),
            dcc.Graph(figure=fig_eq, config={"displayModeBar": False}),
            dcc.Graph(figure=fig_dd, config={"displayModeBar": False}),
        ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

    no_data = dbc.Alert(
        "No portfolio history yet. Paper-trade some positions to generate risk metrics.",
        color="warning", style={"fontSize": "13px"},
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
            html.Th(h, style={"color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "700",
                              "textTransform": "uppercase"})
            for h in ["Metric", "Definition", "Good Range"]
        ])),
        html.Tbody([
            html.Tr([
                html.Td(m, style={"color": T.ACCENT, "fontWeight": "600", "fontSize": "13px"}),
                html.Td(d, style={"color": T.TEXT_PRIMARY, "fontSize": "12px"}),
                html.Td(g, style={"color": T.TEXT_SEC, "fontSize": "12px",
                                   "fontFamily": "JetBrains Mono, monospace"}),
            ]) for m, d, g in ref_rows
        ]),
    ], bordered=False, hover=True, size="sm",
        style={"borderColor": T.BORDER, "--bs-table-bg": T.BG_ELEVATED,
               "--bs-table-color": T.TEXT_PRIMARY,
               "--bs-table-hover-bg": "#1a2235"})

    return html.Div([
        no_data,
        cards,
        charts_section,
        dbc.Card(dbc.CardBody([
            _card_header("Risk Metric Reference"),
            html.Hr(style={"borderColor": T.BORDER, "margin": "8px 0 12px"}),
            ref_table,
            html.P([
                html.Strong("Kelly fraction tip: ", style={"color": T.TEXT_PRIMARY}),
                "Use 0.10–0.25× full Kelly. VaR caveat: historical VaR assumes tomorrow "
                "looks like history — tail events are systematically underestimated.",
            ], style={"color": T.TEXT_SEC, "fontSize": "12px", "lineHeight": "1.6",
                      "marginTop": "12px", "marginBottom": "0"}),
        ]), style=T.STYLE_CARD),
    ], style={"padding": "16px 0"})


# ═══════════════════════════════════════════════════════════════════════════════
# Layout helper — Strategy Registry tab
# ═══════════════════════════════════════════════════════════════════════════════

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

    def _counter_card(label, value, accent):
        return dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                   "fontWeight": "700", "textTransform": "uppercase",
                                   "letterSpacing": "0.07em", "marginBottom": "4px"}),
            html.Div(str(value), style={"color": accent, "fontSize": "1.6rem",
                                        "fontWeight": "700",
                                        "fontFamily": "JetBrains Mono, monospace"}),
        ], style={"padding": "14px 16px"}),
            style={**T.STYLE_CARD, "borderTop": f"2px solid {accent}"}), width="auto")

    counter_row = dbc.Row([
        _counter_card("Total Strategies", total,  T.ACCENT),
        _counter_card("Implemented",      active, T.SUCCESS),
        _counter_card("Roadmap (Stubs)",  stub,   T.WARNING),
        _counter_card("AI / ML",          ai,     "#a78bfa"),
        _counter_card("Rules-Based",      rule,   "#38bdf8"),
    ], className="g-3 mb-4")

    pct = active / total * 100 if total else 0
    progress_bar = dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col(html.Span("Strategies implemented",
                              style={"color": T.TEXT_SEC, "fontSize": "13px"}), width="auto"),
            dbc.Col(html.Span(f"{active} / {total} · {pct:.0f}%",
                              style={"color": T.SUCCESS, "fontWeight": "700",
                                     "fontFamily": "JetBrains Mono, monospace",
                                     "fontSize": "14px"}),
                    width="auto", style={"marginLeft": "auto"}),
        ], align="center", className="mb-2"),
        dbc.Progress(value=pct, color="success", style={"height": "8px"}),
    ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

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
        dbc.Card(dbc.CardBody([
            _card_header("All Strategies"),
            html.Hr(style={"borderColor": T.BORDER, "margin": "8px 0 12px"}),
            grid,
        ]), style={**T.STYLE_CARD, "marginBottom": "16px"}),
        dbc.Card(dbc.CardBody([
            _card_header("Strategy Detail"),
            html.Hr(style={"borderColor": T.BORDER, "margin": "8px 0 12px"}),
            dbc.Select(options=detail_options, value=first_slug,
                       id="reg-detail-select",
                       style={**T.STYLE_DROPDOWN, "marginBottom": "16px"}),
            html.Div(id="reg-detail-body"),
        ]), style=T.STYLE_CARD),
    ], style={"padding": "16px 0"})


@callback(
    Output("reg-detail-body", "children"),
    Input("reg-detail-select", "value"),
)
def _render_strategy_detail(slug: str):
    if not slug:
        return html.Div()
    try:
        from strategies.registry import STRATEGY_METADATA
    except ImportError:
        return dbc.Alert("Registry unavailable.", color="warning")

    meta = STRATEGY_METADATA.get(slug, {})

    _STATUS_COLOR = {
        "active": T.SUCCESS, "stub": T.WARNING,
        "inactive": T.TEXT_MUTED, "archived": T.DANGER,
    }
    _TYPE_COLOR = {"ai": "#a78bfa", "rule": T.ACCENT, "hybrid": T.WARNING}

    status_col = _STATUS_COLOR.get(meta.get("status", ""), T.TEXT_MUTED)
    type_col   = _TYPE_COLOR.get(meta.get("type", ""), T.TEXT_MUTED)

    def _badge(txt, color):
        return html.Span(txt, style={
            "background": f"{color}22", "color": color,
            "border": f"1px solid {color}55",
            "borderRadius": "10px", "padding": "2px 9px",
            "fontSize": "11px", "fontWeight": "600", "marginRight": "6px",
        })

    detail_rows = [
        ("Asset Class",  meta.get("asset_class", "—").replace("_", " ").title()),
        ("Typical Hold", f"{meta.get('typical_holding_days', '—')} days"),
        ("Target Sharpe", str(meta.get("target_sharpe", "—"))),
        ("ML Required",  "Yes" if meta.get("uses_ml") else "No"),
        ("Training Req", "Yes" if meta.get("requires_training") else "No"),
        ("Class Path",   meta.get("class_path") or "(stub)"),
    ]

    return dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div([
                html.Div(meta.get("display_name", slug),
                         style={"color": T.TEXT_PRIMARY, "fontSize": "1.05rem",
                                "fontWeight": "700", "marginBottom": "8px"}),
                _badge(meta.get("type", "—").upper(), type_col),
                _badge(meta.get("status", "—").capitalize(), status_col),
            ], style={"marginBottom": "12px"}),
            html.P(meta.get("description", "No description."),
                   style={"color": T.TEXT_SEC, "fontSize": "13px",
                          "lineHeight": "1.6", "marginBottom": "16px"}),
            html.Table([
                html.Tr([
                    html.Td(label, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                          "fontWeight": "600", "textTransform": "uppercase",
                                          "letterSpacing": "0.06em", "padding": "6px 20px 6px 0",
                                          "whiteSpace": "nowrap"}),
                    html.Td(val, style={"color": T.ACCENT if label == "Class Path" else T.TEXT_SEC,
                                        "fontSize": "12px", "padding": "6px 0",
                                        "fontFamily": "JetBrains Mono, monospace"
                                        if label == "Class Path" else "inherit",
                                        "wordBreak": "break-all"}),
                ]) for label, val in detail_rows
            ], style={"width": "100%", "borderCollapse": "collapse"}),
        ]), style=T.STYLE_CARD), width=8),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.Div("Run a backtest in the Strategies tab to see live performance metrics.",
                     style={"color": T.TEXT_MUTED, "fontSize": "12px",
                            "lineHeight": "1.6", "textAlign": "center", "padding": "20px 0"}),
        ]), style=T.STYLE_CARD), width=4),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# Callbacks — Price Check (Polygon vs Robinhood)
# ═══════════════════════════════════════════════════════════════════════════════

def _rh_available() -> bool:
    """Return True if robin_stocks is installed and RH credentials are configured."""
    try:
        import robin_stocks  # noqa: F401
        import os
        return bool(os.environ.get("ROBINHOOD_USERNAME") and os.environ.get("ROBINHOOD_PASSWORD"))
    except ImportError:
        return False


def _rh_get_stock_price(ticker: str) -> float | None:
    """Fetch Robinhood last trade price for a stock."""
    try:
        import robin_stocks.robinhood as rh
        import os
        rh.login(
            os.environ["ROBINHOOD_USERNAME"],
            os.environ["ROBINHOOD_PASSWORD"],
            mfa_code=os.environ.get("ROBINHOOD_MFA_CODE"),
            store_session=False,
        )
        quote = rh.stocks.get_latest_price(ticker)
        rh.authentication.logout()
        return float(quote[0]) if quote else None
    except Exception:
        return None


def _rh_get_option_ask(ticker: str, expiry: str, strike: str, opt_type: str) -> float | None:
    """Fetch Robinhood ask price for a specific option contract."""
    try:
        import robin_stocks.robinhood as rh
        import os
        rh.login(
            os.environ["ROBINHOOD_USERNAME"],
            os.environ["ROBINHOOD_PASSWORD"],
            mfa_code=os.environ.get("ROBINHOOD_MFA_CODE"),
            store_session=False,
        )
        data = rh.options.find_options_by_expiration_and_strike(
            ticker, expiry, strike, opt_type
        )
        rh.authentication.logout()
        if data and len(data) > 0:
            ask = data[0].get("ask_price")
            return float(ask) if ask else None
        return None
    except Exception:
        return None


@callback(
    Output("tools-pc-rh-warning", "is_open"),
    Output("tools-pc-content", "children"),
    Input("tools-pc-run-btn", "n_clicks"),
    State("tools-pc-ticker",   "value"),
    State("tools-pc-expiry",   "value"),
    State("tools-pc-strike",   "value"),
    State("tools-pc-opt-type", "value"),
    prevent_initial_call=True,
)
def _run_price_check(n_clicks, ticker, expiry, strike, opt_type):
    from dash_app import get_polygon_api_key
    ticker = (ticker or "SPY").upper().strip()
    api_key = get_polygon_api_key()

    rh_ok = _rh_available()
    show_warning = not rh_ok

    rows: list[html.Tr] = []

    def _flag(poly_val, rh_val, threshold: float) -> str:
        if poly_val is None or rh_val is None:
            return "—"
        diff = abs(poly_val - rh_val)
        return "✅" if diff <= threshold else f"⚠️ diff ${diff:.2f}"

    def _cell(txt, color=None, bold=False):
        s = {"fontSize": "13px", "padding": "6px 12px", "whiteSpace": "nowrap"}
        if color:
            s["color"] = color
        if bold:
            s["fontWeight"] = "700"
        return html.Td(txt, style=s)

    # ── Stock price row ────────────────────────────────────────────────────────
    poly_stock: float | None = None
    try:
        if api_key:
            from data.polygon_client import PolygonClient
            c = PolygonClient(api_key=api_key)
            snap = c._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}", {})
            day = snap.get("ticker", {}).get("day") or {}
            poly_stock = day.get("c") or None
    except Exception:
        pass

    rh_stock: float | None = _rh_get_stock_price(ticker) if rh_ok else None

    flag_s = _flag(poly_stock, rh_stock, 0.10)
    flag_color = T.SUCCESS if flag_s == "✅" else (T.WARNING if flag_s.startswith("⚠️") else T.TEXT_MUTED)
    rows.append(html.Tr([
        _cell("Stock last", bold=True),
        _cell(f"${poly_stock:.2f}" if poly_stock else "—"),
        _cell(f"${rh_stock:.2f}" if rh_stock else "—"),
        _cell(flag_s, color=flag_color),
        _cell("flag if diff > $0.10", color=T.TEXT_MUTED),
    ]))

    # ── Option mid / ask row ───────────────────────────────────────────────────
    if expiry and strike:
        poly_mid: float | None = None
        try:
            if api_key:
                from data.polygon_client import PolygonClient
                c = PolygonClient(api_key=api_key)
                sym_suffix = f"{expiry.replace('-', '')}{opt_type[0].upper()}{int(float(strike) * 1000):08d}"
                opt_sym = f"O:{ticker}{sym_suffix}"
                snap = c._get(f"/v3/snapshot/options/{ticker}/{opt_sym}", {})
                details = snap.get("results", {}) or {}
                day = details.get("day") or {}
                bid = day.get("bid") or 0
                ask = day.get("ask") or 0
                if bid and ask:
                    poly_mid = (bid + ask) / 2
        except Exception:
            pass

        rh_ask: float | None = _rh_get_option_ask(ticker, expiry, strike, opt_type) if rh_ok else None

        flag_o = _flag(poly_mid, rh_ask, 0.20)
        flag_o_color = T.SUCCESS if flag_o == "✅" else (T.WARNING if flag_o.startswith("⚠️") else T.TEXT_MUTED)
        rows.append(html.Tr([
            _cell(f"{opt_type.upper()} {strike} {expiry} mid/ask", bold=True),
            _cell(f"${poly_mid:.2f}" if poly_mid else "—"),
            _cell(f"${rh_ask:.2f}" if rh_ask else "—"),
            _cell(flag_o, color=flag_o_color),
            _cell("flag if diff > $0.20", color=T.TEXT_MUTED),
        ]))

    if not rh_ok:
        note = dbc.Alert(
            "Robinhood prices unavailable — showing Polygon only. Configure RH credentials to enable comparison.",
            color="secondary",
            style={"fontSize": "12px", "padding": "6px 12px", "marginBottom": "10px"},
        )
    else:
        note = html.Div()

    hdr_style = {"fontSize": "11px", "fontWeight": "700", "color": T.TEXT_MUTED,
                 "padding": "4px 12px", "borderBottom": f"1px solid {T.BORDER}",
                 "textTransform": "uppercase", "letterSpacing": "0.05em"}
    table = html.Table([
        html.Thead(html.Tr([
            html.Th("Instrument", style=hdr_style),
            html.Th("Polygon", style=hdr_style),
            html.Th("Robinhood", style=hdr_style),
            html.Th("Status", style=hdr_style),
            html.Th("Threshold", style=hdr_style),
        ])),
        html.Tbody(rows, style={"backgroundColor": T.BG_CARD}),
    ], style={"width": "100%", "borderCollapse": "collapse",
              "border": f"1px solid {T.BORDER}", "borderRadius": "6px"})

    return show_warning, html.Div([note, table])


# ═══════════════════════════════════════════════════════════════════════════════
# Layout helper — Broker Integration tab
# ═══════════════════════════════════════════════════════════════════════════════

_BROKER_GUIDE = (Path(__file__).parent.parent.parent
                 / "guide_articles" / "broker_integration.md")


def _broker_tab() -> html.Div:
    if _BROKER_GUIDE.exists():
        content = _BROKER_GUIDE.read_text(encoding="utf-8")
        return html.Div([
            dbc.Card(dbc.CardBody([
                _card_header("Broker Integration Guide"),
                html.Hr(style={"borderColor": T.BORDER, "margin": "8px 0 16px"}),
                dcc.Markdown(content, className="guide-md", style={"color": T.TEXT_PRIMARY,
                                             "fontSize": "13px", "lineHeight": "1.7"}),
            ]), style=T.STYLE_CARD),
        ], style={"padding": "16px 0"})
    return dbc.Alert("Broker integration guide not found.", color="warning")
