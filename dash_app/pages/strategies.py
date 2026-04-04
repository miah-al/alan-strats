"""
dash_app/pages/strategies.py — Full Strategies page.

Phase 1: Shell — strategy selector, outer per-strategy tabs, inner sub-tabs.
Phase 2: Screener tab wired for all 6 strategies via engine/screener.py +
         engine/iv_metrics.py + db/client.py.
Phase 2 (Guide): Markdown articles from dashboard/tabs/guide_articles/{slug}.md.
"""
from __future__ import annotations

import importlib
import logging
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as _pd
from scipy.stats import norm as _scipy_norm

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update

from dash_app import theme as T, get_polygon_api_key

_DD = {**T.STYLE_DROPDOWN}  # shorthand for dropdown style

logger = logging.getLogger(__name__)

# ── Strategy registry ─────────────────────────────────────────────────────────

_STRATEGIES_RULES = [
    {"label": "Iron Condor (Rules)", "value": "iron_condor_rules"},
    {"label": "VIX Spike Fade",      "value": "vix_spike_fade"},
    {"label": "IVR Credit Spread",   "value": "ivr_credit_spread"},
    {"label": "Vol Arbitrage",       "value": "vol_arbitrage"},
    {"label": "GEX Positioning",     "value": "gex_positioning"},
]

_STRATEGIES_AI = [
    {"label": "Iron Condor (AI)",    "value": "iron_condor_ai"},
]

# flat list kept for label lookup and scan-callback registration
_STRATEGIES = _STRATEGIES_RULES + _STRATEGIES_AI

_SLUG_TO_LABEL: dict[str, str] = {s["value"]: s["label"] for s in _STRATEGIES}

# ── Universe options ──────────────────────────────────────────────────────────

_UNIVERSE_TICKERS: dict[str, list[str]] = {
    "ETF Core":  ["SPY", "QQQ", "IWM", "GLD", "TLT", "EEM", "XLF", "XLE", "XLV", "XLK"],
    "Mega Cap":  ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "BRK-B", "JPM", "JNJ"],
    "High IV":   ["TSLA", "NVDA", "AMD", "META", "NFLX", "COIN", "MSTR", "PLTR", "SMCI", "ARM"],
}

_UNIVERSE_OPTIONS = [{"label": k, "value": k} for k in _UNIVERSE_TICKERS] + [
    {"label": "Custom", "value": "Custom"},
]

# ── Guide articles directory ──────────────────────────────────────────────────

_GUIDE_DIR = Path(__file__).parent.parent / "guide_articles"


# ── AG Grid column definitions per strategy ───────────────────────────────────

def _col(field: str, width: int | None = None, flex: int | None = None,
         min_width: int = 70, numeric: bool = False, pinned: str | None = None,
         sort: str | None = None) -> dict:
    d: dict = {"field": field, "resizable": True, "sortable": True, "filter": True,
                "minWidth": min_width}
    if width:
        d["width"] = width
    if flex:
        d["flex"] = flex
    if numeric:
        d["type"] = "numericColumn"
    if pinned:
        d["pinned"] = pinned
    if sort:
        d["sort"] = sort
    return d


_IC_COLS = [
    _col("Ticker",  width=150, pinned="left"),
    _col("Price",   width=150, numeric=True),
    _col("ATM IV",  width=150, numeric=True),
    _col("IVR",     width=150, numeric=True),
    _col("HV20",    width=150, numeric=True),
    _col("VRP",     width=150, numeric=True),
    _col("IV/HV",   width=150, numeric=True),
    _col("VIX",     width=150, numeric=True),
    _col("ADX",     width=150, numeric=True),
    _col("ATR%",    width=150, numeric=True),
    _col("Score",   width=150, numeric=True, sort="desc"),
    _col("Status",  width=150),
    {"field": "Chart", "flex": 1, "minWidth": 150, "sortable": False, "filter": False,
     "cellStyle": {"textAlign": "center", "cursor": "pointer"},
     "valueGetter": {"function": "'📊 View'"},
     "cellClass": "ic-chart-btn"},
    {"field": "_chain",      "hide": True},
    {"field": "_atm_iv_raw", "hide": True},
]

_VSF_COLS = [
    _col("Ticker",      width=150, pinned="left"),
    _col("Price",       width=150, numeric=True),
    _col("VIX",         width=150, numeric=True),
    _col("VIX 20d avg", width=150, numeric=True),
    _col("VIX / 20d",   width=150, numeric=True),
    _col("ATM IV",      width=150, numeric=True),
    _col("HV20",        width=150, numeric=True),
    _col("IVR",         width=150, numeric=True),
    _col("ATR%",        width=150, numeric=True),
    _col("MA200",       width=150, numeric=True),
    _col("Score",       width=150, numeric=True, sort="desc"),
    _col("Status",      width=150),
]

_IVR_COLS = [
    _col("Ticker",      width=150, pinned="left"),
    _col("Price",       width=150, numeric=True),
    _col("ATM IV",      width=150, numeric=True),
    _col("IVR",         width=150, numeric=True),
    _col("VRP",         width=150, numeric=True),
    _col("HV20",        width=150, numeric=True),
    _col("IV/HV",       width=150, numeric=True),
    _col("VIX",         width=150, numeric=True),
    _col("ADX",         width=150, numeric=True),
    _col("ATR%",        width=150, numeric=True),
    _col("Trend",       width=150),
    _col("Spread Type", width=150),
    _col("Score",       width=150, numeric=True, sort="desc"),
    _col("Status",      width=150),
]

_VA_COLS = [
    _col("Ticker",  width=150, pinned="left"),
    _col("Price",   width=150, numeric=True),
    _col("ATM IV",  width=150, numeric=True),
    _col("HV20",    width=150, numeric=True),
    _col("IV/HV",   width=150, numeric=True),
    _col("VRP",     width=150, numeric=True),
    _col("IVR",     width=150, numeric=True),
    _col("VIX",     width=150, numeric=True),
    _col("ATR%",    width=150, numeric=True),
    _col("Score",   width=150, numeric=True, sort="desc"),
    _col("Status",  width=150),
]

_GEX_COLS = [
    _col("Ticker",       width=150, pinned="left"),
    _col("Price",        width=150, numeric=True),
    _col("VIX",          width=150, numeric=True),
    _col("Regime",       width=150),
    _col("SPY Weight",   width=150, numeric=True),
    _col("Signal",       width=150),
    _col("ATR%",         width=150, numeric=True),
    _col("5d Return",    width=150, numeric=True),
    _col("Regime Label", width=200),
]

_COLS_BY_SLUG: dict[str, list[dict]] = {
    "iron_condor_rules": _IC_COLS,
    "iron_condor_ai":    _IC_COLS,
    "vix_spike_fade":    _VSF_COLS,
    "ivr_credit_spread": _IVR_COLS,
    "vol_arbitrage":     _VA_COLS,
    "gex_positioning":   _GEX_COLS,
}


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_pct(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v)*100:.1f}%"
    except Exception:
        return "—"


def _fmt2(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "—"


def _fmt_price(v) -> str:
    if v is None:
        return "—"
    try:
        return f"${float(v):.2f}"
    except Exception:
        return "—"


# ── VIX banner ────────────────────────────────────────────────────────────────

def _vix_banner(vix_series, slug: str) -> html.Div:
    """4-pill VIX context banner for screener top."""
    from engine.screener import _vix_ivr, _vix_20d_avg
    if vix_series is None or len(vix_series) == 0:
        return html.Div()

    current_vix = float(vix_series.iloc[-1])
    vix_20d_avg = _vix_20d_avg(vix_series)
    current_ivr = _vix_ivr(vix_series)
    n_pts       = len(vix_series)

    vix_color = (T.DANGER if current_vix > 35 else
                 T.WARNING if current_vix > 25 else T.SUCCESS)

    if slug in ("iron_condor_rules", "iron_condor_ai"):
        if 14 <= current_vix <= 45:
            status_text = "VIX in IC sweet spot (14–45)"
            status_color = T.SUCCESS
        elif current_vix > 45:
            status_text = "VIX > 45 — fear regime, ICs risky"
            status_color = T.DANGER
        else:
            status_text = "VIX < 14 — premium too thin"
            status_color = T.WARNING
    elif slug == "vix_spike_fade":
        ratio = current_vix / max(vix_20d_avg, 0.01)
        if ratio >= 1.3:
            status_text  = f"VIX spike: {ratio:.1f}× above 20d avg — fade signal ACTIVE"
            status_color = T.DANGER
        else:
            status_text  = f"VIX / 20d avg = {ratio:.1f}× — no spike yet (need ≥ 1.3×)"
            status_color = T.WARNING
    else:
        status_text  = f"VIX 20d avg: {vix_20d_avg:.1f}"
        status_color = T.TEXT_SEC

    def pill(label: str, value: str, color: str = T.TEXT_PRIMARY) -> html.Div:
        return html.Div([
            html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "11px", "fontWeight": "500"}),
            html.Div(value, style={"color": color, "fontSize": "1.25rem", "fontWeight": "700",
                                   "lineHeight": "1.2"}),
        ], style={"minWidth": "100px"})

    return html.Div([
        pill("VIX (current)", f"{current_vix:.2f}", vix_color),
        pill("VIX 20d avg",   f"{vix_20d_avg:.2f}"),
        pill("VIX-IVR",       f"{current_ivr:.2f}"),
        pill("VIX data pts",  str(n_pts)),
        html.Div(status_text, style={
            "flex": "1", "alignSelf": "center",
            "color": status_color, "fontSize": "12px", "fontWeight": "500",
        }),
    ], style={
        "display": "flex", "gap": "32px", "padding": "10px 16px",
        "backgroundColor": T.BG_CARD, "borderRadius": "8px",
        "border": f"1px solid {T.BORDER}", "marginBottom": "12px",
    })


# ── Status pills ──────────────────────────────────────────────────────────────

def _status_pills(rows: list[dict]) -> html.Div:
    ready   = sum(1 for r in rows if r.get("all_pass"))
    partial = sum(1 for r in rows if not r.get("all_pass") and r.get("n_pass", 0) > 0)
    blocked = sum(1 for r in rows if r.get("n_pass", 0) == 0)
    total   = len(rows)

    def badge(text: str, color: str, count: int) -> dbc.Badge:
        return dbc.Badge(
            f"{text}: {count}",
            color="light",
            style={
                "backgroundColor": "transparent",
                "border": f"1px solid {color}",
                "color": color,
                "fontSize": "12px",
                "fontWeight": "600",
                "padding": "4px 10px",
                "borderRadius": "12px",
                "marginRight": "6px",
            },
        )

    return html.Div([
        badge("Trade-Ready", T.SUCCESS,  ready),
        badge("Partial",     T.WARNING,  partial),
        badge("Blocked",     T.DANGER,   blocked),
        html.Span(f"Scanned: {total}", style={
            "color": T.TEXT_MUTED, "fontSize": "12px", "marginLeft": "8px",
        }),
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"})


# ── Guide loader ──────────────────────────────────────────────────────────────

def _load_guide(slug: str) -> str:
    md_path = _GUIDE_DIR / f"{slug}.md"
    if md_path.exists():
        return md_path.read_text(encoding="utf-8")
    return f"*No guide article found for `{slug}`.*"


# ── Per-strategy screener layouts ─────────────────────────────────────────────

def _screener_layout(slug: str) -> html.Div:
    """Controls + grid layout for one strategy's Screener sub-tab."""
    universe_id   = f"str-{slug}-universe"
    custom_id     = f"str-{slug}-custom"
    scan_id       = f"str-{slug}-scan-btn"
    grid_id       = f"str-{slug}-grid"
    status_id     = f"str-{slug}-status"
    vix_banner_id = f"str-{slug}-vix-banner"
    loading_id    = f"str-{slug}-loading"
    cols          = _COLS_BY_SLUG.get(slug, _IC_COLS)

    return html.Div([
        # VIX banner — populated by callback
        html.Div(id=vix_banner_id),

        # Controls
        html.Div(
            html.Div([
                dbc.Select(
                    id=universe_id,
                    options=[{"label": o["label"], "value": o["value"]}
                             for o in _UNIVERSE_OPTIONS],
                    value="ETF Core",
                    style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                           "border": f"1px solid {T.BORDER}", "fontSize": "13px",
                           "width": "150px", "height": "34px"},
                ),
                dbc.Input(
                    id=custom_id,
                    placeholder="Custom tickers: SPY,QQQ,IWM",
                    style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                           "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY,
                           "width": "260px", "height": "34px"},
                ),
                dbc.Button("Scan", id=scan_id,
                    style={"backgroundColor": T.ACCENT, "border": "none",
                           "fontSize": "13px", "fontWeight": "600",
                           "height": "34px", "padding": "0 20px",
                           "whiteSpace": "nowrap"}),
            ], style={"display": "flex", "gap": "8px", "alignItems": "center",
                      "padding": "10px 0", "marginBottom": "10px"}),
        ),

        # Status pills
        html.Div(id=status_id),

        # Results grid
        dcc.Loading(
            html.Div(
                dag.AgGrid(
                    id=grid_id,
                    columnDefs=cols,
                    rowData=[],
                    defaultColDef={"resizable": True, "sortable": True, "filter": True,
                                   "cellStyle": {"fontSize": "12px"}},
                    dashGridOptions={
                        "domLayout": "autoHeight", "animateRows": True,
                        "rowSelection": {"mode": "singleRow", "checkboxes": False,
                                        "enableClickSelection": True},
                    },
                    className=T.AGGRID_THEME,
                    style={"width": "100%"},
                ),
                id=loading_id,
            ),
            type="circle", color=T.ACCENT,
        ),
    ])


def _guide_layout(slug: str) -> html.Div:
    content = _load_guide(slug)
    return html.Div([
        html.Div([
            dcc.Markdown(
                content,
                dangerously_allow_html=False,
                style={"color": T.TEXT_PRIMARY, "fontSize": "14px", "lineHeight": "1.7",
                       "maxWidth": "860px"},
            ),
        ], style={"padding": "4px 0"}),
    ], style={
        "backgroundColor": T.BG_CARD,
        "border": f"1px solid {T.BORDER}",
        "borderRadius": "10px",
        "padding": "24px 32px",
    })


def _backtest_tab(slug: str) -> html.Div:
    """Full backtest UI — controls, dynamic parameter sliders, results area."""
    # ── Load strategy's UI params (needs the class) ───────────────────────────
    _STRATEGY_CLASSES = {
        "iron_condor_rules": ("alan_trader.strategies.iron_condor_rules", "IronCondorRulesStrategy"),
        "iron_condor_ai":    ("alan_trader.strategies.iron_condor_ai",    "IronCondorAIStrategy"),
        "vix_spike_fade":    ("alan_trader.strategies.vix_spike_fade",    "VixSpikeFadeStrategy"),
        "ivr_credit_spread": ("alan_trader.strategies.ivr_credit_spread", "IVRCreditSpreadStrategy"),
        "vol_arbitrage":     ("alan_trader.strategies.vol_arbitrage",     "VolArbitrageStrategy"),
        "gex_positioning":   ("alan_trader.strategies.gex_positioning",   "GEXPositioningStrategy"),
    }

    ui_params = []
    if slug in _STRATEGY_CLASSES:
        try:
            mod_path, cls_name = _STRATEGY_CLASSES[slug]
            mod = importlib.import_module(mod_path)
            strategy_cls = getattr(mod, cls_name)
            ui_params = strategy_cls().get_backtest_ui_params()
        except Exception:
            ui_params = []

    today_str = date.today().isoformat()

    # ── Controls row ──────────────────────────────────────────────────────────
    controls = dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col([
                html.Label("Ticker", style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                             "fontWeight": "600", "textTransform": "uppercase",
                                             "marginBottom": "4px"}),
                dbc.Input(
                    id=f"str-{slug}-bt-ticker",
                    value="SPY",
                    placeholder="e.g. SPY",
                    style={"backgroundColor": T.BG_ELEVATED, "border": f"1px solid {T.BORDER}",
                           "color": T.TEXT_PRIMARY, "fontSize": "13px"},
                ),
            ], width=2),
            dbc.Col([
                html.Label("From", style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                           "fontWeight": "600", "textTransform": "uppercase",
                                           "marginBottom": "4px"}),
                dbc.Input(
                    id=f"str-{slug}-bt-from",
                    type="date",
                    value="2022-01-01",
                    style={"backgroundColor": T.BG_ELEVATED, "border": f"1px solid {T.BORDER}",
                           "color": T.TEXT_PRIMARY, "fontSize": "13px"},
                ),
            ], width=2),
            dbc.Col([
                html.Label("To", style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                         "fontWeight": "600", "textTransform": "uppercase",
                                         "marginBottom": "4px"}),
                dbc.Input(
                    id=f"str-{slug}-bt-to",
                    type="date",
                    value=today_str,
                    style={"backgroundColor": T.BG_ELEVATED, "border": f"1px solid {T.BORDER}",
                           "color": T.TEXT_PRIMARY, "fontSize": "13px"},
                ),
            ], width=2),
            dbc.Col([
                html.Label("Starting Capital ($)", style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                                           "fontWeight": "600",
                                                           "textTransform": "uppercase",
                                                           "marginBottom": "4px"}),
                dbc.Input(
                    id=f"str-{slug}-bt-capital",
                    type="number",
                    value=100000,
                    min=1000,
                    step=1000,
                    style={"backgroundColor": T.BG_ELEVATED, "border": f"1px solid {T.BORDER}",
                           "color": T.TEXT_PRIMARY, "fontSize": "13px"},
                ),
            ], width=3),
            dbc.Col([
                html.Label("\u00a0", style={"fontSize": "11px", "marginBottom": "4px",
                                             "display": "block"}),
                dbc.Button(
                    "Run Backtest",
                    id=f"str-{slug}-bt-run",
                    color="primary",
                    style={"fontWeight": "600", "fontSize": "13px", "width": "100%"},
                ),
            ], width=3, style={"display": "flex", "flexDirection": "column",
                               "justifyContent": "flex-end"}),
        ], className="g-2", align="end"),
    ]), style={**T.STYLE_CARD, "marginBottom": "12px"})

    # ── Parameter sliders (grouped by row field) ──────────────────────────────
    param_rows_by_row: dict[int, list[dict]] = {}
    for p in ui_params:
        row_idx = p.get("row", 0)
        param_rows_by_row.setdefault(row_idx, [])
        param_rows_by_row[row_idx].append(p)

    slider_cards = []
    if ui_params:
        slider_children = []
        for row_idx in sorted(param_rows_by_row.keys()):
            row_params = sorted(param_rows_by_row[row_idx], key=lambda p: p.get("col", 0))
            cols = []
            for p in row_params:
                key   = p["key"]
                label = p.get("label", key)
                mn    = p.get("min", 0)
                mx    = p.get("max", 1)
                dflt  = p.get("default", mn)
                step  = p.get("step", (mx - mn) / 10)
                help_ = p.get("help", "")

                # Build marks: just the endpoints + default
                marks_vals = sorted({mn, mx, dflt})
                marks = {v: {"label": str(round(v, 4)).rstrip("0").rstrip("."),
                             "style": {"color": T.TEXT_MUTED, "fontSize": "10px"}}
                         for v in marks_vals}

                cols.append(dbc.Col([
                    html.Div([
                        html.Span(label, style={"color": T.TEXT_SEC, "fontSize": "12px",
                                                "fontWeight": "600"}),
                        html.Span(
                            id=f"str-{slug}-bt-param-{key}-val",
                            children=str(dflt),
                            style={"color": T.ACCENT, "fontSize": "12px",
                                   "fontWeight": "700", "marginLeft": "8px"},
                        ),
                    ], style={"marginBottom": "6px", "display": "flex",
                              "alignItems": "center"}),
                    dcc.Slider(
                        id=f"str-{slug}-bt-param-{key}",
                        min=mn, max=mx, value=dflt, step=step,
                        marks=marks,
                        tooltip={"placement": "bottom", "always_visible": False},
                        className="bt-slider",
                    ),
                    html.Div(help_, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                           "marginTop": "4px", "lineHeight": "1.4"}),
                ], width=4, style={"padding": "0 12px"}))

            slider_children.append(dbc.Row(cols, className="g-2 mb-2"))

        slider_cards = [dbc.Card(dbc.CardBody([
            html.Div("Strategy Parameters", style={
                "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "12px",
            }),
            html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 14px"}),
        ] + slider_children), style={**T.STYLE_CARD, "marginBottom": "12px"})]

    # ── Results area ──────────────────────────────────────────────────────────
    results_area = dcc.Loading(
        html.Div(id=f"str-{slug}-bt-results"),
        type="circle",
        color=T.ACCENT,
    )

    return html.Div([controls] + slider_cards + [results_area], style={"padding": "4px 0"})


def _performance_stub(slug: str) -> html.Div:
    return dbc.Card(
        dbc.CardBody(html.P(
            "Performance tab — coming in Phase 4.",
            style={"color": T.TEXT_MUTED, "fontSize": "14px"},
        )),
        style=T.STYLE_CARD,
    )


def _simulator_stub(slug: str) -> html.Div:
    return dbc.Card(
        dbc.CardBody(html.P(
            "Simulator tab — coming in Phase 7.",
            style={"color": T.TEXT_MUTED, "fontSize": "14px"},
        )),
        style=T.STYLE_CARD,
    )


# ── Model details tab (Iron Condor AI only) ───────────────────────────────────

_IC_AI_FEATURES = [
    ("ivr",               "Option Chain", "IV Rank (0–1). Fraction of time VIX was below current level over past year. Entry requires ≥ 0.35."),
    ("iv_term_slope",     "Option Chain", "VIX 5-day diff / 5. Positive = vol rising (contango). Negative = backwardation (vol falling, sellers favored)."),
    ("put_call_skew",     "Option Chain", "vol_1m / vol_3m ratio (0.5–2.0). >1.1 signals elevated put premium — structural edge for condor seller."),
    ("atm_iv",            "Option Chain", "ATM implied vol as decimal (VIX/100). Proxy for option pricing richness."),
    ("realized_vol_20d",  "Volatility",  "20-day annualized realized vol from daily returns. Compares to IV to compute VRP."),
    ("vrp",               "Volatility",  "Vol Risk Premium = atm_iv − realized_vol_20d. Positive = implied > realized → structural edge to sell premium."),
    ("atr_pct",           "Volatility",  "ATR(14) / close price. Daily range as % of spot — measures intraday momentum/choppiness."),
    ("ret_5d",            "Momentum",    "5-day price return. High |ret_5d| → trending → bad condor environment."),
    ("ret_20d",           "Momentum",    "20-day price return. Strong directional move → model should reduce P(range-bound)."),
    ("dist_from_ma50",    "Momentum",    "(close − MA50) / MA50. Measures deviation from trend. Far from MA50 = extended, prone to mean-revert or continue."),
    ("vix_level",         "VIX",         "Absolute VIX level. 16–28 = condor-friendly. >35 = too much gap risk, model should suppress signal."),
    ("vix_5d_change",     "VIX",         "VIX 5-day % change. Spike (>+20%) → avoid entry. Fast collapse → vol likely cheap."),
    ("vix_ma_ratio",      "VIX",         "VIX / 20-day VIX MA. >1.2 = elevated vs recent history. Backwardation signal."),
    ("rate_10y",          "Macro",       "10-year Treasury yield (decimal). Higher rates → higher carry cost, slightly cheaper puts."),
    ("yield_curve_2y10y", "Macro",       "10Y−2Y spread. Inversion (<0) historically precedes vol spikes + bear markets."),
    ("days_to_month_end", "Calendar",    "Days remaining to month end. Options expiry clusters at month-end; liquidity peaks."),
    ("oi_put_call_proxy", "Option Chain", "OI put/call proxy (reuses put_call_skew). Elevated = market skewed for downside protection."),
]

_SAVED_MODEL_PATH = Path(__file__).parent.parent.parent / "saved_models" / "iron_condor_ai.pkl"
_SAMPLE_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "sample_ic_training_data.csv"


def _model_tab(slug: str) -> html.Div:
    if slug != "iron_condor_ai":
        return html.Div()

    # ── Model status ──────────────────────────────────────────────────────────
    model_trained = _SAVED_MODEL_PATH.exists()
    status_color  = T.SUCCESS if model_trained else T.WARNING
    status_text   = f"Trained model found: {_SAVED_MODEL_PATH.name}" if model_trained \
                    else "No saved model — run a backtest to train the GBM classifier"

    status_card = dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col(html.Div([
                html.Span("●  ", style={"color": status_color, "fontSize": "16px"}),
                html.Span("Model Status: ", style={"color": T.TEXT_MUTED, "fontSize": "12px",
                                                    "fontWeight": "600", "textTransform": "uppercase",
                                                    "letterSpacing": "0.06em"}),
                html.Span(status_text, style={"color": T.TEXT_PRIMARY, "fontSize": "13px"}),
            ]), width=True),
            dbc.Col(html.Div([
                html.Span("Algorithm: ", style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                                 "fontWeight": "600", "textTransform": "uppercase"}),
                html.Span("Gradient Boosting Classifier (sklearn)",
                          style={"color": T.ACCENT, "fontSize": "12px",
                                 "fontFamily": "JetBrains Mono, monospace"}),
            ]), width="auto"),
        ], align="center"),
    ]), style={**T.STYLE_CARD,
               "borderLeft": f"3px solid {status_color}",
               "marginBottom": "16px"})

    # ── Feature importance chart (from model or placeholder) ──────────────────
    feat_names = [f[0] for f in _IC_AI_FEATURES]

    if model_trained:
        try:
            import pickle
            with open(_SAVED_MODEL_PATH, "rb") as f:
                saved = pickle.load(f)
            # Support both raw model and dict wrapper
            clf = saved.get("clf") if isinstance(saved, dict) else saved
            importances = clf.feature_importances_.tolist() if hasattr(clf, "feature_importances_") else None
        except Exception:
            importances = None
    else:
        importances = None

    # Placeholder importances based on domain knowledge if no model
    if importances is None:
        importances = [
            0.18,  # ivr            ← most important
            0.08,  # iv_term_slope
            0.07,  # put_call_skew
            0.07,  # atm_iv
            0.09,  # realized_vol_20d
            0.10,  # vrp            ← second most important
            0.05,  # atr_pct
            0.04,  # ret_5d
            0.04,  # ret_20d
            0.04,  # dist_from_ma50
            0.06,  # vix_level
            0.04,  # vix_5d_change
            0.04,  # vix_ma_ratio
            0.02,  # rate_10y
            0.03,  # yield_curve_2y10y
            0.02,  # days_to_month_end
            0.03,  # oi_put_call_proxy
        ]
        importance_note = " (illustrative — run backtest to see trained importances)"
    else:
        importance_note = " (from trained model)"

    # Sort by importance descending
    paired = sorted(zip(feat_names, importances), key=lambda x: x[1], reverse=True)
    sorted_names, sorted_imps = zip(*paired)
    bar_colors = [T.ACCENT if v > 0.08 else (T.TEXT_SEC if v > 0.04 else T.BORDER_BRT)
                  for v in sorted_imps]

    fig_imp = go.Figure(go.Bar(
        x=list(sorted_imps),
        y=list(sorted_names),
        orientation="h",
        marker=dict(color=bar_colors),
        text=[f"{v:.1%}" for v in sorted_imps],
        textposition="outside",
        textfont=dict(color=T.TEXT_SEC, size=11),
    ))
    fig_imp.update_layout(
        paper_bgcolor=T.BG_BASE,
        plot_bgcolor=T.BG_ELEVATED,
        font=dict(color=T.TEXT_PRIMARY, family="Inter, sans-serif", size=12),
        height=420,
        margin=dict(l=160, r=60, t=30, b=30),
        title=dict(text=f"Feature Importances{importance_note}",
                   font=dict(size=12, color=T.TEXT_MUTED)),
        xaxis=dict(gridcolor=T.BORDER, tickformat=".0%", showgrid=True),
        yaxis=dict(gridcolor=T.BORDER, showgrid=False),
        showlegend=False,
    )

    importance_card = dbc.Card(dbc.CardBody([
        html.Div("Feature Importances", style={
            "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "8px",
        }),
        html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 12px"}),
        dcc.Graph(figure=fig_imp, config={"displayModeBar": False}),
    ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

    # ── Hyperparameters table ─────────────────────────────────────────────────
    hyperparam_rows = [
        ("n_estimators",      "100",   "Number of boosting trees. More = slower but better calibration. Default 100 balances speed and accuracy."),
        ("max_depth",         "3",     "Tree depth. Shallow (3) prevents overfitting — GBM with deep trees memorizes noise."),
        ("learning_rate",     "0.05",  "Shrinkage factor per tree. Smaller = more regularization, needs more trees."),
        ("signal_threshold",  "0.60",  "P(range-bound) must exceed this to trigger entry. Higher = fewer but higher-quality signals."),
        ("ivr_min",           "0.35",  "Hard IVR floor — no entry below this regardless of model score. Ensures option premium is sufficient."),
        ("vix_max",           "38.0",  "Hard VIX ceiling — suppress entries during volatility regime breaks (crash risk)."),
        ("delta_short",       "0.16",  "Default short strike delta (≈ 1 std dev). Model adjusts asymmetrically in directional regimes."),
        ("wing_width_pct",    "5%",    "Wing width as % of spot price. Defines max loss (wing − credit)."),
        ("dte_target",        "45",    "Target days-to-expiry at entry. Theta decay accelerates after ~45 DTE."),
        ("dte_exit",          "21",    "Force-close DTE. Avoids gamma risk in final weeks. Non-negotiable rule."),
        ("profit_target_pct", "50%",   "Take profit at 50% of max credit. Statistically optimal for IC strategies."),
        ("stop_loss_mult",    "2×",    "Stop loss at 2× credit received. Limits tail loss on gap moves."),
        ("position_size_pct", "3%",    "Capital at risk per trade (max loss ÷ account = 3%). Kelly-conservative sizing."),
        ("warmup_bars",       "180",   "Bars before first ML prediction. Ensures sufficient training data (~9 months)."),
        ("retrain_every",     "30",    "Bars between model retrains (≈ monthly). Walk-forward prevents lookahead bias."),
    ]

    hyp_table = dbc.Table([
        html.Thead(html.Tr([
            html.Th(h, style={"color": T.TEXT_MUTED, "fontSize": "10px", "fontWeight": "700",
                              "textTransform": "uppercase", "letterSpacing": "0.07em",
                              "padding": "8px 12px"})
            for h in ["Parameter", "Default", "Rationale"]
        ])),
        html.Tbody([
            html.Tr([
                html.Td(p, style={"color": T.ACCENT, "fontSize": "12px", "fontWeight": "600",
                                   "fontFamily": "JetBrains Mono, monospace",
                                   "padding": "7px 12px", "whiteSpace": "nowrap"}),
                html.Td(v, style={"color": T.SUCCESS, "fontSize": "12px", "fontWeight": "700",
                                   "fontFamily": "JetBrains Mono, monospace",
                                   "padding": "7px 12px"}),
                html.Td(r, style={"color": T.TEXT_SEC, "fontSize": "12px",
                                   "padding": "7px 12px", "lineHeight": "1.5"}),
            ]) for p, v, r in hyperparam_rows
        ]),
    ], bordered=False, hover=True, size="sm",
        style={"borderColor": T.BORDER, "--bs-table-bg": T.BG_ELEVATED,
               "--bs-table-color": T.TEXT_PRIMARY,
               "--bs-table-hover-bg": "#1a2235",
               "--bs-table-border-color": T.BORDER})

    hyperparam_card = dbc.Card(dbc.CardBody([
        html.Div("GBM Hyperparameters & Strategy Parameters", style={
            "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "8px",
        }),
        html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 12px"}),
        hyp_table,
    ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

    # ── Feature descriptions table ────────────────────────────────────────────
    feat_table = dbc.Table([
        html.Thead(html.Tr([
            html.Th(h, style={"color": T.TEXT_MUTED, "fontSize": "10px", "fontWeight": "700",
                              "textTransform": "uppercase", "letterSpacing": "0.07em",
                              "padding": "8px 12px"})
            for h in ["Feature", "Category", "Description"]
        ])),
        html.Tbody([
            html.Tr([
                html.Td(name, style={"color": T.ACCENT, "fontSize": "11px", "fontWeight": "600",
                                      "fontFamily": "JetBrains Mono, monospace",
                                      "padding": "6px 12px", "whiteSpace": "nowrap"}),
                html.Td(cat, style={"color": T.WARNING, "fontSize": "11px", "fontWeight": "500",
                                     "padding": "6px 12px", "whiteSpace": "nowrap"}),
                html.Td(desc, style={"color": T.TEXT_SEC, "fontSize": "12px",
                                      "padding": "6px 12px", "lineHeight": "1.5"}),
            ]) for name, cat, desc in _IC_AI_FEATURES
        ]),
    ], bordered=False, hover=True, size="sm",
        style={"borderColor": T.BORDER, "--bs-table-bg": T.BG_ELEVATED,
               "--bs-table-color": T.TEXT_PRIMARY,
               "--bs-table-hover-bg": "#1a2235",
               "--bs-table-border-color": T.BORDER})

    feat_card = dbc.Card(dbc.CardBody([
        html.Div("Feature Engineering — 17 Input Features", style={
            "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "8px",
        }),
        html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 12px"}),
        html.P([
            "All 17 features are derived from ", html.Strong("price, VIX, and macro data"),
            " — no options chain required. VIX serves as the IV proxy. "
            "Features are constructed without lookahead: only data available at bar ", html.Em("t"),
            " is used to generate predictions for bar ", html.Em("t+1"), ".",
        ], style={"color": T.TEXT_SEC, "fontSize": "13px", "lineHeight": "1.6",
                  "marginBottom": "14px"}),
        feat_table,
    ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

    # ── Label construction note ───────────────────────────────────────────────
    label_card = dbc.Card(dbc.CardBody([
        html.Div("Label Construction", style={
            "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "8px",
        }),
        html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 12px"}),
        dbc.Row([
            dbc.Col([
                html.P("Binary classification target:", style={"color": T.TEXT_MUTED,
                       "fontSize": "11px", "fontWeight": "600", "textTransform": "uppercase",
                       "letterSpacing": "0.06em", "marginBottom": "8px"}),
                html.Div([
                    html.Div([
                        html.Span("1  ", style={"color": T.SUCCESS, "fontWeight": "700",
                                                 "fontFamily": "JetBrains Mono, monospace",
                                                 "fontSize": "14px"}),
                        html.Span("Range-bound — IC profitable. Max excursion over next 45 days "
                                  "≤ 1σ expected N-day move.",
                                  style={"color": T.TEXT_PRIMARY, "fontSize": "13px"}),
                    ], style={"marginBottom": "8px", "padding": "8px 12px",
                              "background": f"{T.SUCCESS}11",
                              "border": f"1px solid {T.SUCCESS}33",
                              "borderRadius": "6px"}),
                    html.Div([
                        html.Span("0  ", style={"color": T.DANGER, "fontWeight": "700",
                                                 "fontFamily": "JetBrains Mono, monospace",
                                                 "fontSize": "14px"}),
                        html.Span("Trending / gapping — IC loses. Stock breaks outside the "
                                  "expected 1σ volatility band.",
                                  style={"color": T.TEXT_PRIMARY, "fontSize": "13px"}),
                    ], style={"padding": "8px 12px",
                              "background": f"{T.DANGER}11",
                              "border": f"1px solid {T.DANGER}33",
                              "borderRadius": "6px"}),
                ]),
            ], width=7),
            dbc.Col([
                html.P("Expected positive rate:", style={"color": T.TEXT_MUTED,
                       "fontSize": "11px", "fontWeight": "600", "textTransform": "uppercase",
                       "letterSpacing": "0.06em", "marginBottom": "8px"}),
                html.Div([
                    html.Div("~48–55%", style={"color": T.SUCCESS, "fontSize": "2rem",
                                                "fontWeight": "700",
                                                "fontFamily": "JetBrains Mono, monospace"}),
                    html.Div("of days are range-bound (45-day window on SPY/QQQ)",
                             style={"color": T.TEXT_MUTED, "fontSize": "12px",
                                    "lineHeight": "1.5", "marginTop": "4px"}),
                    html.Div(["Formula: ", html.Code(
                        "max_excursion ≤ σ × √(N/252)",
                        style={"background": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                               "padding": "2px 6px", "borderRadius": "4px",
                               "fontSize": "11px"})],
                        style={"color": T.TEXT_MUTED, "fontSize": "12px", "marginTop": "10px"}),
                ], style={"padding": "14px 16px", "background": T.BG_ELEVATED,
                          "borderRadius": "8px", "border": f"1px solid {T.BORDER}"}),
            ], width=5),
        ]),
    ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

    # ── Sample data section ───────────────────────────────────────────────────
    sample_exists = _SAMPLE_DATA_PATH.exists()
    sample_card = dbc.Card(dbc.CardBody([
        html.Div("Sample Training Data", style={
            "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "8px",
        }),
        html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 12px"}),
        html.Div(id="str-ic-ai-sample-data-body"),
        dcc.Store(id="str-ic-ai-sample-exists", data=sample_exists),
    ]), style=T.STYLE_CARD)

    return html.Div([
        status_card,
        dbc.Row([
            dbc.Col(importance_card, width=12),
        ]),
        dbc.Row([
            dbc.Col(hyperparam_card, width=6),
            dbc.Col(label_card,      width=6),
        ], className="g-3 mb-0"),
        html.Div(style={"marginBottom": "16px"}),
        feat_card,
        sample_card,
    ], style={"padding": "8px 0"})


@callback(
    Output("str-ic-ai-sample-data-body", "children"),
    Input("str-ic-ai-sample-exists",     "data"),
)
def _render_sample_data_preview(exists: bool):
    if not exists or not _SAMPLE_DATA_PATH.exists():
        return dbc.Alert([
            html.Strong("Sample data not yet generated. "),
            "Run the generator script: ",
            html.Code("python data/generate_sample_data.py",
                      style={"background": "#1f2937", "padding": "2px 8px",
                             "borderRadius": "4px", "fontSize": "12px"}),
        ], color="warning", style={"fontSize": "13px"})

    try:
        import pandas as pd
        df = pd.read_csv(_SAMPLE_DATA_PATH)
        n_rows   = len(df)
        n_cols   = len(df.columns)
        pos_rate = f"{df['label'].mean():.1%}" if "label" in df.columns else "—"
        date_rng = f"{df['date'].iloc[0]} → {df['date'].iloc[-1]}" if "date" in df.columns else "—"

        stats_row = dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Rows", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                        "fontWeight": "700", "textTransform": "uppercase"}),
                html.Div(f"{n_rows:,}", style={"color": T.TEXT_PRIMARY, "fontSize": "1.4rem",
                                               "fontWeight": "700",
                                               "fontFamily": "JetBrains Mono, monospace"}),
            ], style={"padding": "10px 14px"}), style=T.STYLE_CARD), width="auto"),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Features", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                             "fontWeight": "700", "textTransform": "uppercase"}),
                html.Div(f"{n_cols - 3}", style={"color": T.TEXT_PRIMARY, "fontSize": "1.4rem",
                                                  "fontWeight": "700",
                                                  "fontFamily": "JetBrains Mono, monospace"}),
            ], style={"padding": "10px 14px"}), style=T.STYLE_CARD), width="auto"),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Positive Rate", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                                  "fontWeight": "700", "textTransform": "uppercase"}),
                html.Div(pos_rate, style={"color": T.SUCCESS, "fontSize": "1.4rem",
                                          "fontWeight": "700",
                                          "fontFamily": "JetBrains Mono, monospace"}),
            ], style={"padding": "10px 14px"}), style=T.STYLE_CARD), width="auto"),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.Div("Date Range", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                               "fontWeight": "700", "textTransform": "uppercase"}),
                html.Div(date_rng, style={"color": T.TEXT_PRIMARY, "fontSize": "13px",
                                           "fontWeight": "600",
                                           "fontFamily": "JetBrains Mono, monospace"}),
            ], style={"padding": "10px 14px"}), style=T.STYLE_CARD), width="auto"),
        ], className="g-2 mb-3")

        # Preview last 10 rows
        preview = df.tail(10).round(4)
        col_defs = [{"field": c, "width": 80 if c == "date" else 70,
                     "minWidth": 60} for c in preview.columns]
        col_defs[0]["width"] = 100  # date column wider

        grid = dag.AgGrid(
            rowData=preview.to_dict("records"),
            columnDefs=col_defs,
            defaultColDef={"resizable": True, "sortable": True},
            dashGridOptions={"domLayout": "autoHeight",
                             "suppressColumnVirtualisation": True},
            className=T.AGGRID_THEME,
            style={"width": "100%"},
        )

        return html.Div([
            html.P([
                html.Span(f"File: ", style={"color": T.TEXT_MUTED, "fontSize": "11px"}),
                html.Code(str(_SAMPLE_DATA_PATH.name),
                          style={"background": T.BG_ELEVATED, "color": T.ACCENT,
                                 "padding": "2px 6px", "borderRadius": "4px",
                                 "fontSize": "11px"}),
                html.Span("  ·  Showing last 10 rows",
                          style={"color": T.TEXT_MUTED, "fontSize": "11px"}),
            ], style={"marginBottom": "10px"}),
            stats_row,
            grid,
        ])
    except Exception as e:
        return dbc.Alert(f"Could not load sample data: {e}", color="danger")


# ── Test tab ─────────────────────────────────────────────────────────────────

_TEST_SUITES = {
    "iron_condor_rules": [
        {"id": "phase4",        "label": "Phase 4 Bug Fixes",       "module": "test_phase4_fixes"},
        {"id": "ic_integration","label": "IC Integration (DB + Polygon)", "module": "test_ic_rules_integration"},
    ],
    "vix_spike_fade":    [{"id": "phase4", "label": "Phase 4 Bug Fixes", "module": "test_phase4_fixes"}],
    "vol_arbitrage":     [{"id": "phase4", "label": "Phase 4 Bug Fixes", "module": "test_phase4_fixes"}],
    "iron_condor_ai":    [{"id": "phase4", "label": "Phase 4 Bug Fixes", "module": "test_phase4_fixes"}],
    "ivr_credit_spread": [{"id": "phase4", "label": "Phase 4 Bug Fixes", "module": "test_phase4_fixes"}],
    "gex_positioning":   [],
}

_TEST_MARK_OPTIONS = [
    {"label": "All tests",    "value": "all"},
    {"label": "Unit only",    "value": "not db and not polygon"},
    {"label": "DB tests",     "value": "db"},
    {"label": "Polygon live", "value": "polygon"},
]


def _test_tab(slug: str) -> html.Div:
    suites = _TEST_SUITES.get(slug, [])
    suite_options = [{"label": s["label"], "value": s["id"]} for s in suites]
    default_suite = suites[0]["id"] if suites else None

    return html.Div([
        html.Div([
            html.Div("Unit & Integration Tests", style={
                "color": T.TEXT_SEC, "fontSize": "11px", "fontWeight": "600",
                "textTransform": "uppercase", "letterSpacing": "0.07em",
            }),
            html.Div([
                dcc.Dropdown(
                    id=f"str-{slug}-test-suite",
                    options=suite_options,
                    value=default_suite,
                    clearable=False,
                    style={"width": "260px", "fontSize": "12px",
                           "backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY},
                ),
                dcc.Dropdown(
                    id=f"str-{slug}-test-marks",
                    options=_TEST_MARK_OPTIONS,
                    value="all",
                    clearable=False,
                    style={"width": "160px", "fontSize": "12px",
                           "backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY},
                ),
                dbc.Button("▶ Run Tests", id=f"str-{slug}-test-run-btn",
                           color="primary", size="sm",
                           style={"fontSize": "12px",
                                  "backgroundColor": T.ACCENT, "border": "none"}),
            ], style={"display": "flex", "gap": "8px", "alignItems": "center"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "center", "borderBottom": f"1px solid {T.BORDER}",
                  "paddingBottom": "8px", "marginBottom": "16px"}),

        html.Div(
            html.P("Select a test suite and click ▶ Run Tests.",
                   style={"color": T.TEXT_MUTED, "fontSize": "12px",
                          "fontStyle": "italic", "margin": "4px 0"}),
            id=f"str-{slug}-test-summary",
            style={"marginBottom": "10px"},
        ),

        dcc.Loading(
            html.Div(id=f"str-{slug}-test-output",
                     style={"fontFamily": "JetBrains Mono, monospace",
                            "fontSize": "11px", "whiteSpace": "pre-wrap",
                            "backgroundColor": T.BG_ELEVATED,
                            "border": f"1px solid {T.BORDER}",
                            "borderRadius": "6px", "padding": "12px",
                            "color": T.TEXT_PRIMARY,
                            "maxHeight": "600px", "overflowY": "auto",
                            "display": "none"}),
            type="circle", color=T.ACCENT,
        ),
    ], style={"padding": "16px 0"})


def _make_test_callback(slug: str):
    @callback(
        Output(f"str-{slug}-test-output",  "children"),
        Output(f"str-{slug}-test-output",  "style"),
        Output(f"str-{slug}-test-summary", "children"),
        Input(f"str-{slug}-test-run-btn", "n_clicks"),
        State(f"str-{slug}-test-suite",   "value"),
        State(f"str-{slug}-test-marks",   "value"),
        prevent_initial_call=True,
    )
    def _run_tests(n_clicks, suite_id, marks):
        import subprocess, sys, os, time
        suites = _TEST_SUITES.get(slug, [])
        suite  = next((s for s in suites if s["id"] == suite_id), None)
        if not suite:
            return "No test suite selected.", {"display": "block"}, html.P("No suite.")

        test_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "tests",
            f"{suite['module']}.py",
        )
        if not os.path.exists(test_file):
            return f"Test file not found: {test_file}", {"display": "block"}, html.P("File missing.")

        cmd = [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short", "--no-header"]
        if marks and marks != "all":
            cmd += ["-m", marks]

        _output_style = {
            "fontFamily": "JetBrains Mono, monospace",
            "fontSize": "11px", "whiteSpace": "pre-wrap",
            "backgroundColor": T.BG_ELEVATED,
            "border": f"1px solid {T.BORDER}",
            "borderRadius": "6px", "padding": "12px",
            "color": T.TEXT_PRIMARY,
            "maxHeight": "600px", "overflowY": "auto",
            "display": "block",
        }

        t0 = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True,
                timeout=120,
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            )
            output  = result.stdout + result.stderr
            elapsed = time.time() - t0
            passed  = output.count(" PASSED")
            failed  = output.count(" FAILED")
            errored = output.count(" ERROR")
            skipped = output.count(" SKIPPED")
            total   = passed + failed + errored

            summary_color = T.SUCCESS if failed == 0 and errored == 0 else T.DANGER
            summary = html.Div([
                html.Span(f"✅ {passed} passed", style={"color": T.SUCCESS, "fontWeight": "700",
                                                         "marginRight": "12px", "fontSize": "13px"}),
                html.Span(f"❌ {failed} failed", style={"color": T.DANGER if failed else T.TEXT_MUTED,
                                                         "fontWeight": "700", "marginRight": "12px",
                                                         "fontSize": "13px"}),
                html.Span(f"⏭ {skipped} skipped", style={"color": T.TEXT_MUTED,
                                                           "marginRight": "12px", "fontSize": "12px"}),
                html.Span(f"({elapsed:.1f}s)", style={"color": T.TEXT_MUTED, "fontSize": "11px"}),
            ])
        except subprocess.TimeoutExpired:
            output  = "Test run timed out after 120 seconds."
            summary = html.P(output, style={"color": T.DANGER, "fontSize": "13px"})
        except Exception as exc:
            output  = f"Error running tests: {exc}"
            summary = html.P(output, style={"color": T.DANGER, "fontSize": "13px"})

        return output, _output_style, summary

    _run_tests.__name__ = f"_run_tests_{slug}"
    return _run_tests


# Register test callbacks for all strategies
for _slug in [s["value"] for s in _STRATEGIES]:
    _make_test_callback(_slug)


# ── Inner tabs per strategy ───────────────────────────────────────────────────

def _inner_tabs(slug: str) -> dbc.Tabs:
    tab_style     = {"fontSize": "13px", "padding": "6px 14px"}
    tab_act_style = {**tab_style, "borderTop": f"2px solid {T.ACCENT}"}
    tabs = [
        dbc.Tab(
            _screener_layout(slug),
            label="Screener",
            tab_id=f"str-{slug}-inner-screener",
            tab_style=tab_style,
            active_tab_style=tab_act_style,
        ),
        dbc.Tab(
            _backtest_tab(slug),
            label="Backtest",
            tab_id=f"str-{slug}-inner-backtest",
            tab_style=tab_style,
            active_tab_style=tab_act_style,
        ),
        dbc.Tab(
            _performance_stub(slug),
            label="Performance",
            tab_id=f"str-{slug}-inner-performance",
            tab_style=tab_style,
            active_tab_style=tab_act_style,
        ),
        dbc.Tab(
            _guide_layout(slug),
            label="Guide",
            tab_id=f"str-{slug}-inner-guide",
            tab_style=tab_style,
            active_tab_style=tab_act_style,
        ),
    ]

    # Model tab — Iron Condor AI only
    if slug == "iron_condor_ai":
        tabs.append(dbc.Tab(
            _model_tab(slug),
            label="Model",
            tab_id=f"str-{slug}-inner-model",
            tab_style=tab_style,
            active_tab_style={**tab_act_style, "borderTop": f"2px solid #a78bfa"},
        ))

    tabs.append(dbc.Tab(
        _test_tab(slug),
        label="Test",
        tab_id=f"str-{slug}-inner-test",
        tab_style=tab_style,
        active_tab_style={**tab_act_style, "borderTop": f"2px solid #34d399"},
    ))

    tabs.append(dbc.Tab(
        _simulator_stub(slug),
        label="Simulator",
        tab_id=f"str-{slug}-inner-simulator",
        tab_style=tab_style,
        disabled=True,
    ))

    return dbc.Tabs(
        tabs,
        id=f"str-{slug}-inner-tabs",
        active_tab=f"str-{slug}-inner-screener",
        style={"marginBottom": "16px"},
    )


# ── Layout ────────────────────────────────────────────────────────────────────

def layout() -> html.Div:
    return html.Div(
        [
            html.H2("Strategies", style={
                "color": T.TEXT_PRIMARY, "fontSize": "1.35rem",
                "fontWeight": "700", "marginBottom": "4px",
            }),
            html.P(
                "Select strategies to screen opportunities, run backtests, and read guides.",
                style={"color": T.TEXT_MUTED, "fontSize": "13px", "marginBottom": "16px"},
            ),

            # ── Strategy selector (AI vs Rules-Based) ────────────────────────
            dbc.Card(dbc.CardBody([
                # Row: two groups side by side
                html.Div([

                    # ── Rules-Based group ─────────────────────────────────────
                    html.Div([
                        html.Div([
                            html.Span("⚙", style={"marginRight": "5px", "fontSize": "11px"}),
                            html.Span("Rules-Based", style={"fontSize": "11px",
                                "fontWeight": "700", "letterSpacing": "0.06em",
                                "textTransform": "uppercase", "color": T.ACCENT}),
                        ], style={"marginBottom": "8px"}),
                        dbc.Checklist(
                            id="str-strategy-select-rules",
                            options=_STRATEGIES_RULES,
                            value=["iron_condor_rules"],
                            inline=True,
                            inputStyle={"marginRight": "4px", "accentColor": T.ACCENT},
                            labelStyle={
                                "color": T.TEXT_PRIMARY, "fontSize": "13px",
                                "marginRight": "18px", "cursor": "pointer",
                            },
                        ),
                    ], style={"flex": "1", "minWidth": "0"}),

                    # ── Divider ───────────────────────────────────────────────
                    html.Div(style={
                        "width": "1px", "backgroundColor": T.BORDER,
                        "margin": "0 20px", "alignSelf": "stretch",
                    }),

                    # ── AI-Powered group ──────────────────────────────────────
                    html.Div([
                        html.Div([
                            html.Span("🤖", style={"marginRight": "5px", "fontSize": "11px"}),
                            html.Span("AI-Powered", style={"fontSize": "11px",
                                "fontWeight": "700", "letterSpacing": "0.06em",
                                "textTransform": "uppercase",
                                "color": "#a78bfa"}),  # purple tint
                        ], style={"marginBottom": "8px"}),
                        dbc.Checklist(
                            id="str-strategy-select-ai",
                            options=_STRATEGIES_AI,
                            value=[],
                            inline=True,
                            inputStyle={"marginRight": "4px", "accentColor": "#a78bfa"},
                            labelStyle={
                                "color": T.TEXT_PRIMARY, "fontSize": "13px",
                                "marginRight": "18px", "cursor": "pointer",
                            },
                        ),
                    ], style={"flex": "0 0 auto"}),

                ], style={"display": "flex", "alignItems": "flex-start",
                          "flexWrap": "wrap", "gap": "4px"}),

                # Hidden combined store consumed by update_outer_tabs
                dcc.Store(id="str-strategy-select"),
            ]), style={**T.STYLE_CARD, "marginBottom": "16px"}),

            # ── API key note ──────────────────────────────────────────────────
            html.Div(
                (
                    html.Span("Polygon API key loaded", style={"color": T.SUCCESS, "fontSize": "12px"})
                    if get_polygon_api_key()
                    else html.Span(
                        "No Polygon API key — set POLYGON_API_KEY env var before scanning.",
                        style={"color": T.WARNING, "fontSize": "12px"},
                    )
                ),
                style={"marginBottom": "12px"},
            ),

            # ── IC payoff modal ───────────────────────────────────────────────
            dbc.Modal([
                dbc.ModalHeader(
                    dbc.ModalTitle(id="str-ic-modal-title", children="Payoff Chart"),
                    style={"backgroundColor": T.BG_ELEVATED,
                           "borderBottom": f"1px solid {T.BORDER}"},
                    close_button=True,
                ),
                dbc.ModalBody(
                    dcc.Loading(
                        html.Div(id="str-ic-modal-body"),
                        type="circle", color=T.ACCENT,
                    ),
                    style={"backgroundColor": T.BG_BASE, "padding": "20px"},
                ),
                dbc.ModalFooter([
                    html.Div([
                        html.Label("Contracts", style={"color": T.TEXT_SEC,
                            "fontSize": "12px", "marginRight": "6px",
                            "lineHeight": "32px"}),
                        dbc.Input(id="str-ic-contracts", type="number",
                            value=1, min=1, max=100, step=1,
                            style={"width": "70px", "fontSize": "13px",
                                   "backgroundColor": T.BG_ELEVATED,
                                   "border": f"1px solid {T.BORDER}",
                                   "color": T.TEXT_PRIMARY}),
                    ], style={"display": "flex", "alignItems": "center",
                              "gap": "6px"}),
                    dbc.Button("Paper Trade", id="str-ic-paper-btn",
                        color="success", size="sm",
                        style={"fontWeight": "600"}),
                    html.Div(id="str-ic-paper-feedback",
                             style={"fontSize": "12px", "lineHeight": "32px"}),
                ], style={"backgroundColor": T.BG_ELEVATED,
                          "borderTop": f"1px solid {T.BORDER}",
                          "gap": "12px"}),
            ], id="str-ic-modal", size="xl", is_open=False, scrollable=True),

            # ── Store: selected IC row for modal ─────────────────────────────
            dcc.Store(id="str-ic-row-store"),

            # ── Signal detail modal (VSF / IVR / VA / GEX) ───────────────────
            dbc.Modal([
                dbc.ModalHeader(
                    dbc.ModalTitle(id="str-sig-modal-title", children="Signal Detail"),
                    style={"backgroundColor": T.BG_ELEVATED,
                           "borderBottom": f"1px solid {T.BORDER}"},
                    close_button=True,
                ),
                dbc.ModalBody(
                    dcc.Loading(html.Div(id="str-sig-modal-body"),
                                type="circle", color=T.ACCENT),
                    style={"backgroundColor": T.BG_BASE, "padding": "20px"},
                ),
                dbc.ModalFooter(
                    dbc.Button("Dismiss", id="str-sig-modal-dismiss",
                               color="secondary", size="sm"),
                    style={"backgroundColor": T.BG_ELEVATED,
                           "borderTop": f"1px solid {T.BORDER}"},
                ),
            ], id="str-sig-modal", size="lg", is_open=False, scrollable=True),
            dcc.Store(id="str-sig-row-store"),

            # ── Store + outer tabs container ──────────────────────────────────
            dcc.Store(id="str-strategy-tabs-store", data=["iron_condor_rules"]),
            html.Div(id="str-outer-tabs-container", children=[
                dbc.Tabs([
                    dbc.Tab(
                        _inner_tabs("iron_condor_rules"),
                        label="Iron Condor (Rules)",
                        tab_id="str-outer-iron_condor_rules",
                        tab_style={"fontSize": "13px", "padding": "6px 16px"},
                    )
                ], id="str-outer-tabs", active_tab="str-outer-iron_condor_rules",
                   style={"marginTop": "4px"}),
            ]),
        ],
        style=T.STYLE_PAGE,
    )


# ── Callback: merge AI + rules selections into combined store ─────────────────

@callback(
    Output("str-strategy-select", "data"),
    Input("str-strategy-select-rules", "value"),
    Input("str-strategy-select-ai",    "value"),
)
def _combine_selections(rules, ai):
    combined = list(rules or []) + list(ai or [])
    # Preserve original _STRATEGIES order
    order = [s["value"] for s in _STRATEGIES]
    return [s for s in order if s in combined]


# ── Callback: update outer tabs when strategy selection changes ───────────────

@callback(
    Output("str-outer-tabs-container", "children"),
    Output("str-strategy-tabs-store",  "data"),
    Input("str-strategy-select",       "data"),
)
def update_outer_tabs(selected: list[str] | None):
    if not selected:
        return html.P(
            "Select at least one strategy above.",
            style={"color": T.TEXT_MUTED, "fontSize": "14px"},
        ), []

    tab_style = {"fontSize": "13px", "padding": "6px 16px"}
    tabs = [
        dbc.Tab(
            _inner_tabs(slug),
            label=_SLUG_TO_LABEL.get(slug, slug),
            tab_id=f"str-outer-{slug}",
            tab_style=tab_style,
        )
        for slug in selected
    ]

    return dbc.Tabs(
        tabs,
        id="str-outer-tabs",
        active_tab=f"str-outer-{selected[0]}",
        style={"marginTop": "4px"},
    ), selected


# ── Shared scan helper ────────────────────────────────────────────────────────

def _get_vix_series(api_key: str | None = None):
    """Load VIX close series — DB first, Polygon fallback."""
    # Try DB first
    try:
        from db.client import get_engine, get_vix_bars
        engine = get_engine()
        vix_df = get_vix_bars(engine, date.today() - timedelta(days=400), date.today())
        if not vix_df.empty:
            return vix_df["close"].astype(float)
    except Exception:
        pass

    # Polygon fallback — fetch VIX as a ticker (^VIX / VIXW)
    if api_key:
        try:
            from engine.screener import _fetch_ohlcv
            for sym in ["I:VIX", "VIX"]:
                df = _fetch_ohlcv(sym, api_key, bars=400)
                if not df.empty and "close" in df.columns:
                    return df["close"].astype(float)
        except Exception:
            pass

    return None


def _resolve_tickers(universe: str, custom: str | None) -> list[str]:
    if universe == "Custom":
        raw = custom or ""
        return [t.strip().upper() for t in raw.split(",") if t.strip()]
    return _UNIVERSE_TICKERS.get(universe, [])


def _fetch_ic_strikes(ticker: str, api_key: str, spot: float, adx_ok: bool) -> dict | None:
    """Fetch real options chain for ticker and return IC strike data. Returns None on failure."""
    from engine.screener import _get_options_chain, _find_strike, _get_chain_mid
    target_delta = 0.16 if adx_ok else 0.10
    wing_pct     = 0.05

    exp_chain, best_exp, dte_used, err = _get_options_chain(ticker, api_key, spot)
    if err or exp_chain is None or exp_chain.empty:
        return None

    calls = exp_chain[exp_chain["type"].str.lower() == "call"].sort_values("strike")
    puts  = exp_chain[exp_chain["type"].str.lower() == "put"].sort_values("strike", ascending=False)

    short_call_k, short_call_mid = _find_strike(calls, "call", spot, target_delta)
    short_put_k,  short_put_mid  = _find_strike(puts,  "put",  spot, target_delta)
    if short_call_k is None or short_put_k is None:
        return None

    wing_w = round(spot * wing_pct, 0)

    # Long call wing must be ABOVE short call (further OTM). Filter to calls > short_call_k.
    calls_above = calls[calls["strike"] > short_call_k]
    if calls_above.empty:
        return None
    long_call_mid, long_call_k = _get_chain_mid(calls_above, short_call_k + wing_w,
                                                 exclude_strike=short_call_k)

    # Long put wing must be BELOW short put (further OTM). Filter to puts < short_put_k.
    puts_below = puts[puts["strike"] < short_put_k]
    if puts_below.empty:
        return None
    long_put_mid, long_put_k = _get_chain_mid(puts_below, short_put_k - wing_w,
                                               exclude_strike=short_put_k)

    def _m(v): return v if v is not None else 0.0

    net_credit    = _m(short_call_mid) + _m(short_put_mid) - _m(long_call_mid) - _m(long_put_mid)
    call_width    = long_call_k  - short_call_k
    put_width     = short_put_k  - long_put_k
    max_loss      = min(call_width, put_width) - net_credit

    return {
        "short_call_k":   short_call_k,
        "long_call_k":    long_call_k,
        "short_put_k":    short_put_k,
        "long_put_k":     long_put_k,
        "short_call_mid": _m(short_call_mid),
        "long_call_mid":  _m(long_call_mid),
        "short_put_mid":  _m(short_put_mid),
        "long_put_mid":   _m(long_put_mid),
        "net_credit":     net_credit,
        "max_loss":       max_loss,
        "best_exp":       best_exp,
        "dte_used":       dte_used,
        "target_delta":   target_delta,
    }


def _build_ic_payoff_fig(spot, short_call_k, long_call_k, short_put_k, long_put_k,
                          net_credit, dte_used, atm_iv, ticker, best_exp):
    """Build IC payoff chart matching the Streamlit version."""
    r = 0.045
    prices = np.linspace(spot * 0.75, spot * 1.25, 400)

    def pnl_expiry(S):
        call_spread = np.minimum(0, short_call_k - S) + np.maximum(0, S - long_call_k)
        put_spread  = np.minimum(0, S - short_put_k)  + np.maximum(0, long_put_k - S)
        return (net_credit + call_spread + put_spread) * 100

    def pnl_today(S_arr):
        T      = max(dte_used / 252, 0.001)
        iv     = max(atm_iv or 0.25, 0.01)
        sqT    = math.sqrt(T)
        exp_rT = math.exp(-r * T)

        def _call(K):
            d1 = (np.log(S_arr / K) + (r + 0.5 * iv ** 2) * T) / (iv * sqT)
            return S_arr * _scipy_norm.cdf(d1) - K * exp_rT * _scipy_norm.cdf(d1 - sqT * iv)

        def _put(K):
            d1 = (np.log(S_arr / K) + (r + 0.5 * iv ** 2) * T) / (iv * sqT)
            return K * exp_rT * _scipy_norm.cdf(sqT * iv - d1) - S_arr * _scipy_norm.cdf(-d1)

        sc = _call(short_call_k)
        lc = _call(long_call_k)
        sp = _put(short_put_k)
        lp = _put(long_put_k)
        return (net_credit + (-sc + lc - sp + lp)) * 100

    pe = pnl_expiry(prices)
    pt = pnl_today(prices)
    profit_close  = net_credit * 0.50 * 100
    stop_loss_val = -net_credit * 2.0  * 100
    be_upper      = short_call_k + net_credit
    be_lower      = short_put_k  - net_credit

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prices, y=np.where(pe >= 0, pe, 0),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prices, y=np.where(pe < 0, pe, 0),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prices, y=pe,
        line=dict(color="#6366f1", width=2), name="P&L at expiry",
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>At expiry</extra>"))
    fig.add_trace(go.Scatter(x=prices, y=pt,
        line=dict(color="#10b981", width=1.5, dash="dot"), name="P&L today (BS)",
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>Today</extra>"))

    fig.add_hline(y=profit_close, line=dict(color="#10b981", width=1.5, dash="dash"),
        annotation_text=f"✅ 50% target: +${profit_close:.0f}",
        annotation_position="top left", annotation_font_color="#10b981")
    fig.add_hline(y=stop_loss_val, line=dict(color="#ef4444", width=1.5, dash="dash"),
        annotation_text=f"🛑 2× stop: -${abs(stop_loss_val):.0f}",
        annotation_position="bottom left", annotation_font_color="#ef4444")
    fig.add_hline(y=0, line=dict(color="#374151", width=1))
    fig.add_vline(x=spot,     line=dict(color="#f59e0b", width=1.5, dash="dash"),
        annotation_text=f"Spot ${spot:.0f}", annotation_font_color="#f59e0b")
    fig.add_vline(x=be_upper, line=dict(color="#9ca3af", width=1, dash="dot"),
        annotation_text=f"BE ${be_upper:.0f}", annotation_font_color="#9ca3af")
    fig.add_vline(x=be_lower, line=dict(color="#9ca3af", width=1, dash="dot"),
        annotation_text=f"BE ${be_lower:.0f}", annotation_font_color="#9ca3af")

    fig.update_layout(
        title=dict(text=f"{ticker} Iron Condor  |  {best_exp} ({dte_used} DTE)  |  "
                        "Exit: 50% profit · 2× stop · 21 DTE", font=dict(size=13)),
        xaxis_title="Underlying Price", yaxis_title="P&L per Contract ($)",
        height=380, margin=dict(l=0, r=0, t=50, b=0),
        paper_bgcolor=T.BG_BASE, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=12),
        xaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f"),
        yaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
        template="plotly_dark",
    )
    return fig


def _fetch_data(tickers: list[str], api_key: str):
    """Returns (vix_series, price_dfs, iv_all). Raises on fatal error."""
    from engine.screener import _fetch_ohlcv
    from engine.iv_metrics import get_iv_metrics_batch

    vix_series = _get_vix_series(api_key)
    if vix_series is None:
        raise RuntimeError("No VIX data available (DB offline and Polygon VIX fetch failed).")

    price_dfs: dict = {}
    for ticker in tickers:
        df = _fetch_ohlcv(ticker, api_key)
        if not df.empty:
            price_dfs[ticker] = df

    if not price_dfs:
        raise RuntimeError("No price data returned from Polygon for any ticker. Check API key.")

    iv_all = get_iv_metrics_batch(
        tickers=list(price_dfs.keys()),
        api_key=api_key,
        price_dfs=price_dfs,
    )
    return vix_series, price_dfs, iv_all


def _status_pill_row(rows: list[dict]) -> html.Div:
    return _status_pills(rows)


# ── Format display rows ───────────────────────────────────────────────────────

def _display_row_ic(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":      r.get("Ticker", ""),
        "Price":       round(r.get("Price", 0), 2),
        "ATM IV":      _fmt_pct(r.get("ATM IV")),
        "IVR":         _fmt_pct(r.get("IVR")),
        "HV20":        _fmt_pct(r.get("HV20")),
        "VRP":         _fmt_pct(r.get("VRP")),
        "IV/HV":       _fmt2(r.get("IV/HV")),
        "VIX":         round(r.get("VIX", 0), 2),
        "ADX":         round(r.get("ADX", 0), 1),
        "ATR%":        f"{r.get('ATR%', 0):.2%}",
        "Score":       round(r.get("score", 0), 1),
        "Status":      status,
        "all_pass":    r.get("all_pass", False),
        "n_pass":      r.get("n_pass", 0),
        "_chain":      r.get("_chain"),        # real strikes dict or None
        "_atm_iv_raw": r.get("ATM IV"),        # raw float for BS calc
    }


def _display_row_vsf(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":      r.get("Ticker", ""),
        "Price":       round(r.get("Price", 0), 2),
        "VIX":         round(r.get("VIX", 0), 2),
        "VIX 20d avg": round(r.get("VIX 20d avg", 0), 2),
        "VIX / 20d":   _fmt2(r.get("VIX / 20d")),
        "ATM IV":      _fmt_pct(r.get("ATM IV")),
        "HV20":        _fmt_pct(r.get("HV20")),
        "IVR":         _fmt_pct(r.get("IVR")),
        "ATR%":        f"{r.get('ATR%', 0):.2%}",
        "MA200":       _fmt2(r.get("MA200")),
        "Score":       round(r.get("score", 0), 1),
        "Status":      status,
        "all_pass":    r.get("all_pass", False),
        "n_pass":      r.get("n_pass", 0),
    }


def _display_row_ivr(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":      r.get("Ticker", ""),
        "Price":       round(r.get("Price", 0), 2),
        "ATM IV":      _fmt_pct(r.get("ATM IV")),
        "IVR":         _fmt_pct(r.get("IVR")),
        "VRP":         _fmt_pct(r.get("VRP")),
        "HV20":        _fmt_pct(r.get("HV20")),
        "IV/HV":       _fmt2(r.get("IV/HV")),
        "VIX":         round(r.get("VIX", 0), 2),
        "ADX":         round(r.get("ADX", 0), 1),
        "ATR%":        f"{r.get('ATR%', 0):.2%}",
        "Trend":       r.get("Trend", "—"),
        "Spread Type": r.get("Spread Type", "—"),
        "Score":       round(r.get("score", 0), 1),
        "Status":      status,
        "all_pass":    r.get("all_pass", False),
        "n_pass":      r.get("n_pass", 0),
    }


def _display_row_va(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":   r.get("Ticker", ""),
        "Price":    round(r.get("Price", 0), 2),
        "ATM IV":   _fmt_pct(r.get("ATM IV")),
        "HV20":     _fmt_pct(r.get("HV20")),
        "IV/HV":    _fmt2(r.get("IV/HV")),
        "VRP":      _fmt_pct(r.get("VRP")),
        "IVR":      _fmt_pct(r.get("IVR")),
        "VIX":      round(r.get("VIX", 0), 2),
        "ATR%":     f"{r.get('ATR%', 0):.2%}",
        "Score":    round(r.get("score", 0), 1),
        "Status":   status,
        "all_pass": r.get("all_pass", False),
        "n_pass":   r.get("n_pass", 0),
    }


def _display_row_gex(r: dict) -> dict:
    return {
        "Ticker":       r.get("Ticker", ""),
        "Price":        round(r.get("Price", 0), 2),
        "VIX":          round(r.get("VIX", 0), 2),
        "Regime":       r.get("Regime", "—"),
        "SPY Weight":   f"{r.get('SPY Weight', 0)*100:.0f}%",
        "Signal":       r.get("Signal", "—"),
        "ATR%":         f"{r.get('ATR%', 0):.2f}%",
        "5d Return":    f"{r.get('5d Return', 0)*100:.1f}%",
        "Regime Label": r.get("Regime Label", "—"),
        "all_pass":     True,
        "n_pass":       1,
    }


# ── Core scan logic ───────────────────────────────────────────────────────────

def _run_scan(slug: str, universe: str, custom: str | None, api_key: str):
    """
    Returns (row_data, status_children, vix_banner_children) or raises.
    All error handling is done by callers via try/except.
    """
    from engine.screener import (
        _score_ic_rules,
        _score_vix_spike_fade,
        _score_ivr_credit_spread,
        _score_vol_arbitrage,
        _score_gex_positioning,
        _DEFAULT_PARAMS,
    )

    tickers = _resolve_tickers(universe, custom)
    if not tickers:
        return [], html.P("No tickers in universe.", style={"color": T.WARNING}), html.Div()

    vix_series, price_dfs, iv_all = _fetch_data(tickers, api_key)
    params = _DEFAULT_PARAMS.get(slug, {})

    raw_rows: list[dict] = []

    if slug in ("iron_condor_rules", "iron_condor_ai"):
        ic_params = params or {"ivr_min": 0.20, "vix_min": 14.0, "vix_max": 45.0,
                               "adx_max": 35.0, "atr_pct_max": 0.030}
        for ticker in price_dfs:
            r = _score_ic_rules(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                ic_params,
            )
            if r:
                # Fetch real options chain for real strikes
                chain = _fetch_ic_strikes(
                    ticker, api_key,
                    spot=r["Price"],
                    adx_ok=r.get("adx_ok", True),
                )
                r["_chain"] = chain
                raw_rows.append(r)

    elif slug == "vix_spike_fade":
        for ticker in price_dfs:
            r = _score_vix_spike_fade(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
            )
            if r:
                raw_rows.append(r)

    elif slug == "ivr_credit_spread":
        for ticker in price_dfs:
            r = _score_ivr_credit_spread(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params or {"ivr_min": 0.40, "vix_max": 50.0},
            )
            if r:
                raw_rows.append(r)

    elif slug == "vol_arbitrage":
        for ticker in price_dfs:
            r = _score_vol_arbitrage(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
            )
            if r:
                raw_rows.append(r)

    elif slug == "gex_positioning":
        raw_rows = _score_gex_positioning(
            tickers=list(price_dfs.keys()),
            api_key=api_key,
            vix_series=vix_series,
            price_dfs=price_dfs,
            params={},
        )

    # Format rows for AG Grid
    fmt_map = {
        "iron_condor_rules": _display_row_ic,
        "iron_condor_ai":    _display_row_ic,
        "vix_spike_fade":    _display_row_vsf,
        "ivr_credit_spread": _display_row_ivr,
        "vol_arbitrage":     _display_row_va,
        "gex_positioning":   _display_row_gex,
    }
    fmt_fn = fmt_map.get(slug, _display_row_ic)
    display_rows = [fmt_fn(r) for r in raw_rows]

    # Sort by score descending
    display_rows.sort(
        key=lambda r: (r.get("Score") or 0) if isinstance(r.get("Score"), (int, float)) else 0,
        reverse=True,
    )

    status_div   = _status_pill_row(display_rows)
    vix_banner   = _vix_banner(vix_series, slug)

    # IVR fallback warning: if any ticker used VIX proxy instead of real options IVR
    ivr_fallback_count = sum(
        1 for r in raw_rows
        if str(r.get("ivr_confidence", "")).startswith("low")
    )
    if ivr_fallback_count > 0:
        ivr_warn = dbc.Alert(
            [
                html.Strong("IVR data quality warning: "),
                f"{ivr_fallback_count}/{len(raw_rows)} ticker(s) are using VIX proxy IVR — "
                "real options bid/ask unavailable. Rescan on a market day for accurate IVR values.",
            ],
            color="warning",
            style={"fontSize": "12px", "padding": "8px 12px", "marginBottom": "8px"},
        )
        vix_banner = html.Div([ivr_warn, vix_banner])

    return display_rows, status_div, vix_banner


# ── Callbacks — one per strategy ──────────────────────────────────────────────
# We generate callbacks dynamically to avoid 6× code duplication.

def _make_scan_callback(slug: str):
    grid_id      = f"str-{slug}-grid"
    status_id    = f"str-{slug}-status"
    vix_id       = f"str-{slug}-vix-banner"
    scan_id      = f"str-{slug}-scan-btn"
    universe_id  = f"str-{slug}-universe"
    custom_id    = f"str-{slug}-custom"

    @callback(
        Output(grid_id,   "rowData"),
        Output(status_id, "children"),
        Output(vix_id,    "children"),
        Input(scan_id,    "n_clicks"),
        State(universe_id, "value"),
        State(custom_id,   "value"),
        prevent_initial_call=True,
    )
    def _scan(n_clicks, universe, custom):
        api_key = get_polygon_api_key()
        if not api_key:
            msg = html.P(
                "No Polygon API key found. Set POLYGON_API_KEY env var.",
                style={"color": T.WARNING, "fontSize": "13px"},
            )
            return no_update, msg, no_update

        try:
            rows, status_div, vix_div = _run_scan(slug, universe or "ETF Core", custom, api_key)
            return rows, status_div, vix_div
        except Exception as exc:
            logger.exception(f"Scan error for {slug}: {exc}")
            err = html.P(f"Scan error: {exc}", style={"color": T.DANGER, "fontSize": "13px"})
            return [], err, no_update

    # Give the function a unique name so Dash doesn't complain about duplicates
    _scan.__name__ = f"_scan_{slug}"
    return _scan


# Register callbacks for all 6 strategies at module import time
for _slug in [s["value"] for s in _STRATEGIES]:
    _make_scan_callback(_slug)


# ── Backtest tab ──────────────────────────────────────────────────────────────

_STRATEGY_CLASSES_BT = {
    "iron_condor_rules": ("alan_trader.strategies.iron_condor_rules", "IronCondorRulesStrategy"),
    "iron_condor_ai":    ("alan_trader.strategies.iron_condor_ai",    "IronCondorAIStrategy"),
    "vix_spike_fade":    ("alan_trader.strategies.vix_spike_fade",    "VixSpikeFadeStrategy"),
    "ivr_credit_spread": ("alan_trader.strategies.ivr_credit_spread", "IVRCreditSpreadStrategy"),
    "vol_arbitrage":     ("alan_trader.strategies.vol_arbitrage",     "VolArbitrageStrategy"),
    "gex_positioning":   ("alan_trader.strategies.gex_positioning",   "GEXPositioningStrategy"),
}


def _get_ui_params_for_slug(slug: str) -> list:
    """Instantiate strategy and return its get_backtest_ui_params()."""
    if slug not in _STRATEGY_CLASSES_BT:
        return []
    try:
        mod_path, cls_name = _STRATEGY_CLASSES_BT[slug]
        mod = importlib.import_module(mod_path)
        return getattr(mod, cls_name)().get_backtest_ui_params()
    except Exception:
        return []


def _render_backtest_results(result, slug: str) -> html.Div:
    """Build the full results display: metric cards, equity curve, monthly heatmap, trades table."""
    m = result.metrics

    # ── 6 metric cards ────────────────────────────────────────────────────────
    def _card(label: str, value: str, color: str = T.TEXT_PRIMARY) -> html.Div:
        return html.Div([
            html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                   "fontWeight": "700", "textTransform": "uppercase",
                                   "letterSpacing": "0.05em", "marginBottom": "4px"}),
            html.Div(value, style={"color": color, "fontSize": "1.35rem",
                                   "fontWeight": "700", "fontFamily": "JetBrains Mono, monospace"}),
        ], style={**T.STYLE_CARD, "flex": "1", "minWidth": "130px", "padding": "12px 16px"})

    total_ret  = m.get("total_return_pct", 0.0)
    sharpe     = m.get("sharpe", 0.0)
    max_dd     = m.get("max_drawdown_pct", 0.0)
    win_rate   = m.get("win_rate_pct", 0.0)
    pf         = m.get("profit_factor", 0.0)
    n_trades   = m.get("num_trades", 0)

    metric_row = html.Div([
        _card("Total Return",  f"{total_ret:+.2f}%",
              T.SUCCESS if total_ret >= 0 else T.DANGER),
        _card("Sharpe Ratio",  f"{sharpe:.3f}",
              T.SUCCESS if sharpe >= 1.0 else T.WARNING if sharpe >= 0 else T.DANGER),
        _card("Max Drawdown",  f"{max_dd:.2f}%",
              T.DANGER if max_dd < -15 else T.WARNING if max_dd < -5 else T.SUCCESS),
        _card("Win Rate",      f"{win_rate:.1f}%",
              T.SUCCESS if win_rate >= 55 else T.WARNING if win_rate >= 40 else T.DANGER),
        _card("Profit Factor", f"{pf:.3f}" if pf != float("inf") else "∞",
              T.SUCCESS if pf >= 1.5 else T.WARNING if pf >= 1.0 else T.DANGER),
        _card("Total Trades",  str(n_trades)),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "16px"})

    # ── Equity curve ──────────────────────────────────────────────────────────
    eq = result.equity_curve
    start_cap = float(eq.iloc[0]) if not eq.empty else 100_000

    # Drawdown shading
    roll_max = eq.cummax()

    fig_eq = go.Figure()

    # Shade drawdown regions (red fill between equity and its running max)
    if not eq.empty:
        fig_eq.add_trace(go.Scatter(
            x=list(eq.index), y=list(roll_max),
            line=dict(width=0), showlegend=False, hoverinfo="skip",
            name="peak",
        ))
        fig_eq.add_trace(go.Scatter(
            x=list(eq.index), y=list(eq),
            fill="tonexty",
            fillcolor="rgba(239,68,68,0.12)",
            line=dict(width=0), showlegend=False, hoverinfo="skip",
            name="drawdown_fill",
        ))

    # Equity line
    fig_eq.add_trace(go.Scatter(
        x=list(eq.index), y=list(eq),
        line=dict(color=T.ACCENT, width=2),
        name="Equity",
        hovertemplate="%{x|%Y-%m-%d}  $%{y:,.0f}<extra>Equity</extra>",
    ))

    # Starting capital reference
    fig_eq.add_hline(
        y=start_cap,
        line=dict(color=T.BORDER_BRT, width=1, dash="dot"),
        annotation_text=f"Start ${start_cap:,.0f}",
        annotation_position="bottom right",
        annotation_font_color=T.TEXT_MUTED,
        annotation_font_size=10,
    )

    fig_eq.update_layout(
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_PRIMARY, family="Inter, sans-serif", size=12),
        height=350, margin=dict(l=10, r=10, t=30, b=10),
        title=dict(text="Equity Curve", font=dict(size=12, color=T.TEXT_MUTED)),
        xaxis=dict(gridcolor=T.BORDER, showgrid=True),
        yaxis=dict(gridcolor=T.BORDER, showgrid=True, tickformat="$,.0f"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        showlegend=False,
        template="plotly_dark",
    )

    equity_chart = dbc.Card(dbc.CardBody([
        dcc.Graph(figure=fig_eq, config={"displayModeBar": False}),
    ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

    # ── Monthly returns heatmap ───────────────────────────────────────────────
    dr = result.daily_returns
    heatmap_card = html.Div()
    if not dr.empty:
        try:
            dr_idx = _pd.to_datetime(dr.index)
            dr_df  = _pd.DataFrame({
                "year":  dr_idx.year,
                "month": dr_idx.month,
                "ret":   dr.values,
            })
            # Aggregate to monthly
            monthly = (dr_df.groupby(["year", "month"])["ret"]
                       .apply(lambda x: (1 + x).prod() - 1)
                       .reset_index())
            pivot = monthly.pivot(index="year", columns="month", values="ret").fillna(0)
            month_labels = ["Jan","Feb","Mar","Apr","May","Jun",
                            "Jul","Aug","Sep","Oct","Nov","Dec"]
            col_labels = [month_labels[c - 1] for c in pivot.columns]

            fig_heat = go.Figure(go.Heatmap(
                z=(pivot.values * 100).tolist(),
                x=col_labels,
                y=[str(y) for y in pivot.index],
                colorscale="RdYlGn",
                zmid=0,
                hovertemplate="%{y} %{x}: %{z:.2f}%<extra></extra>",
                colorbar=dict(
                    tickformat=".1f",
                    ticksuffix="%",
                    thickness=12,
                    len=0.8,
                    title=dict(text="%", side="right"),
                ),
            ))
            fig_heat.update_layout(
                paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
                font=dict(color=T.TEXT_PRIMARY, family="Inter, sans-serif", size=11),
                height=max(180, 40 + 35 * len(pivot)),
                margin=dict(l=10, r=60, t=30, b=10),
                title=dict(text="Monthly Returns (%)", font=dict(size=12, color=T.TEXT_MUTED)),
                xaxis=dict(side="top"),
                template="plotly_dark",
            )
            heatmap_card = dbc.Card(dbc.CardBody([
                dcc.Graph(figure=fig_heat, config={"displayModeBar": False}),
            ]), style={**T.STYLE_CARD, "marginBottom": "16px"})
        except Exception:
            pass

    # ── Trades table ──────────────────────────────────────────────────────────
    trades_card = html.Div()
    trades_df = result.trades
    if trades_df is not None and not trades_df.empty:
        # Select displayable key columns; keep only those that exist
        preferred = ["entry_date", "exit_date", "ticker", "pnl", "pnl_pct",
                     "hold_days", "dte_held", "exit_reason", "contracts",
                     "credit", "status", "winner"]
        display_cols = [c for c in preferred if c in trades_df.columns]
        # Add remaining columns not in the preferred list
        extra_cols = [c for c in trades_df.columns if c not in display_cols]
        display_cols = display_cols + extra_cols

        col_defs = []
        for c in display_cols:
            cd = {"field": c, "resizable": True, "sortable": True, "filter": True,
                  "minWidth": 70}
            if c == "pnl":
                cd["cellStyle"] = {
                    "function": "params.value >= 0 ? {'color': '#10b981', 'fontWeight': '600'} : {'color': '#ef4444', 'fontWeight': '600'}"
                }
                cd["width"] = 100
            elif c in ("entry_date", "exit_date"):
                cd["width"] = 105
            elif c == "exit_reason":
                cd["flex"] = 1
                cd["minWidth"] = 120
            elif c in ("pnl_pct",):
                cd["cellStyle"] = {
                    "function": "params.value >= 0 ? {'color': '#10b981'} : {'color': '#ef4444'}"
                }
                cd["width"] = 90
            elif c == "winner":
                cd["cellStyle"] = {
                    "function": "params.value ? {'color': '#10b981'} : {'color': '#ef4444'}"
                }
                cd["width"] = 75
            col_defs.append(cd)

        tbl_height = min(400, 50 + len(trades_df) * 40)
        trades_grid = dag.AgGrid(
            rowData=trades_df[display_cols].astype(str).to_dict("records"),
            columnDefs=col_defs,
            defaultColDef={"resizable": True, "sortable": True,
                           "cellStyle": {"fontSize": "12px"}},
            dashGridOptions={"domLayout": "autoHeight" if tbl_height < 400 else "normal",
                             "animateRows": True},
            columnSize="sizeToFit",
            className=T.AGGRID_THEME,
            style={"width": "100%", "height": f"{tbl_height}px"},
        )
        trades_card = dbc.Card(dbc.CardBody([
            html.Div("Trades", style={
                "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "letterSpacing": "0.08em",
                "marginBottom": "8px",
            }),
            html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 10px"}),
            trades_grid,
        ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

    return html.Div([
        metric_row,
        equity_chart,
        heatmap_card,
        trades_card,
    ])


def _make_backtest_callback(slug: str):
    """Register a backtest run callback for the given strategy slug."""
    ui_params = _get_ui_params_for_slug(slug)
    results_id = f"str-{slug}-bt-results"
    run_id     = f"str-{slug}-bt-run"
    ticker_id  = f"str-{slug}-bt-ticker"
    from_id    = f"str-{slug}-bt-from"
    to_id      = f"str-{slug}-bt-to"
    capital_id = f"str-{slug}-bt-capital"
    param_ids  = [f"str-{slug}-bt-param-{p['key']}" for p in ui_params]

    # Build slider value display callbacks (one per param)
    for p in ui_params:
        key      = p["key"]
        val_id   = f"str-{slug}-bt-param-{key}-val"
        slider_id = f"str-{slug}-bt-param-{key}"

        @callback(
            Output(val_id, "children"),
            Input(slider_id, "value"),
        )
        def _update_val(v):
            if v is None:
                return ""
            # Format: trim trailing zeros for floats
            if isinstance(v, float) and v == int(v):
                return str(int(v))
            return str(round(v, 6)).rstrip("0").rstrip(".")

        _update_val.__name__ = f"_bt_val_{slug}_{key}"

    @callback(
        Output(results_id, "children"),
        Input(run_id, "n_clicks"),
        State(ticker_id, "value"),
        State(from_id, "value"),
        State(to_id, "value"),
        State(capital_id, "value"),
        *[State(pid, "value") for pid in param_ids],
        prevent_initial_call=True,
    )
    def _run_backtest(n, ticker, from_date, to_date, capital, *param_values):
        if not n:
            return no_update

        ticker     = (ticker or "SPY").upper().strip()
        from_date  = from_date  or "2022-01-01"
        to_date    = to_date    or date.today().isoformat()
        capital    = float(capital or 100_000)

        # ── Load price data ───────────────────────────────────────────────────
        try:
            from db.client import get_engine, get_vix_bars, get_macro_bars, get_price_bars
            engine = get_engine()
        except Exception as e:
            return dbc.Alert(
                f"Database not available — ensure DB connection is configured. ({e})",
                color="warning",
            )

        try:
            fd = date.fromisoformat(from_date)
            td = date.fromisoformat(to_date)
            price_data = get_price_bars(engine, ticker, fd, td)
        except Exception as e:
            return dbc.Alert(
                f"Error loading price data for {ticker}: {e}",
                color="danger",
            )

        if price_data is None or price_data.empty:
            return dbc.Alert(
                f"No price data found for {ticker} in {from_date} → {to_date}. "
                "Sync data first via Tools → Data Manager.",
                color="warning",
            )

        # Set date index
        if "date" in price_data.columns:
            price_data = price_data.set_index("date")
        price_data.index = _pd.to_datetime(price_data.index)

        # ── Load auxiliary data ───────────────────────────────────────────────
        try:
            vix_df  = get_vix_bars(engine, fd, td)
            rate_df = get_macro_bars(engine, fd, td)
        except Exception:
            vix_df  = _pd.DataFrame()
            rate_df = _pd.DataFrame()

        if not vix_df.empty:
            vix_df.index = _pd.to_datetime(vix_df.index)
        if not rate_df.empty:
            rate_df.index = _pd.to_datetime(rate_df.index)

        auxiliary_data = {"vix": vix_df, "rate10y": rate_df}

        # ── Instantiate strategy + run backtest ───────────────────────────────
        try:
            if slug not in _STRATEGY_CLASSES_BT:
                return dbc.Alert(f"No backtest class registered for strategy '{slug}'.",
                                 color="danger")
            mod_path, cls_name = _STRATEGY_CLASSES_BT[slug]
            mod      = importlib.import_module(mod_path)
            strategy = getattr(mod, cls_name)()

            params = dict(zip([p["key"] for p in ui_params], param_values))
            result = strategy.backtest(
                price_data, auxiliary_data,
                starting_capital=capital,
                **params,
            )
        except NotImplementedError:
            return dbc.Alert(
                f"Strategy '{slug}' backtest is not yet implemented.",
                color="warning",
            )
        except Exception as e:
            logger.exception(f"Backtest error for {slug}: {e}")
            return dbc.Alert(f"Backtest error: {str(e)}", color="danger")

        # ── Render results ────────────────────────────────────────────────────
        try:
            return _render_backtest_results(result, slug)
        except Exception as e:
            logger.exception(f"Result render error for {slug}: {e}")
            return dbc.Alert(f"Error rendering results: {str(e)}", color="danger")

    _run_backtest.__name__ = f"_run_backtest_{slug}"
    return _run_backtest


# Register backtest callbacks for all strategies
for _slug in [s["value"] for s in _STRATEGIES]:
    _make_backtest_callback(_slug)


# ── IC chart modal: two-step (open instantly → populate via store) ────────────

def _make_ic_chart_callback(slug: str):
    grid_id = f"str-{slug}-grid"

    # Step 1: row selected → open modal immediately + store row data
    @callback(
        Output("str-ic-modal",      "is_open",  allow_duplicate=True),
        Output("str-ic-modal-title","children", allow_duplicate=True),
        Output("str-ic-row-store",  "data",     allow_duplicate=True),
        Input(grid_id, "selectedRows"),
        prevent_initial_call=True,
    )
    def _open_modal(selected_rows):
        if not selected_rows:
            return no_update, no_update, no_update
        row = selected_rows[0]
        if not row:
            return no_update, no_update, no_update
        row = {**row, "_slug": slug}   # tag the strategy slug for paper trade
        ticker = row.get("Ticker", "")
        chain  = row.get("_chain")
        title  = (f"{ticker} Iron Condor  ·  {chain['best_exp']} ({chain['dte_used']} DTE)  ·  "
                  f"~{chain['target_delta']:.0%}-delta  ·  Net credit ${chain['net_credit']*100:.0f}/contract"
                  if chain else ticker)
        return True, title, row

    _open_modal.__name__ = f"_open_modal_{slug}"
    return _open_modal


# Step 2: store change → build and populate modal body (runs after modal is open)
@callback(
    Output("str-ic-modal-body", "children"),
    Input("str-ic-row-store", "data"),
    prevent_initial_call=True,
)
def _build_modal_body(row):
    if not row:
        return no_update
    ticker = row.get("Ticker", "")
    chain  = row.get("_chain")

    if not chain:
        return dbc.Alert(
            f"No options chain data for {ticker} "
            "(Polygon returned no data for the 30–60 DTE window).",
            color="warning",
        )

    spot          = row.get("Price", 0)
    atm_iv        = row.get("_atm_iv_raw") or 0.25
    net_credit    = chain["net_credit"]
    max_loss      = chain["max_loss"]
    be_upper      = chain["short_call_k"] + net_credit
    be_lower      = chain["short_put_k"]  - net_credit
    profit_target = net_credit * 0.50

    def _mc(label, val, color=T.TEXT_PRIMARY):
        return html.Div([
            html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                   "fontWeight": "600", "textTransform": "uppercase",
                                   "marginBottom": "4px"}),
            html.Div(val,   style={"color": color, "fontSize": "1.1rem",
                                   "fontWeight": "700"}),
        ], style={**T.STYLE_CARD, "minWidth": "110px", "flex": "1", "padding": "10px 12px"})

    nc100 = net_credit * 100
    ml100 = max_loss   * 100
    pt100 = profit_target * 100
    _has_prices = any(chain.get(k, 0) > 0
                      for k in ["short_call_mid", "short_put_mid",
                                "long_call_mid",  "long_put_mid"])
    metrics = html.Div([
        _mc("Net Credit",   f"${nc100:.0f}/contract" if _has_prices else "— (no quotes)",
            T.SUCCESS if net_credit > 0 else (T.WARNING if not _has_prices else T.DANGER)),
        _mc("Max Loss",     f"${ml100:.0f}/contract" if _has_prices else "—", T.DANGER),
        _mc("50% Target",   f"${pt100:.0f}/contract" if _has_prices else "—", T.SUCCESS),
        _mc("Upper BE",     f"${be_upper:.2f}"),
        _mc("Lower BE",     f"${be_lower:.2f}"),
        _mc("Expiry",       f"{chain['best_exp']} ({chain['dte_used']} DTE)"),
        _mc("Delta target", f"~{chain['target_delta']:.0%}"),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "16px"})

    def _fmt_mid(v):
        return f"${v:.2f}" if v and v > 0 else "—"

    def _cash(mid, action):
        if not mid or mid == 0:
            return "—"
        val = mid * 100 * (1 if action == "SELL" else -1)
        return f"+${val:.0f}" if val >= 0 else f"-${abs(val):.0f}"

    net_cash = net_credit * 100
    leg_rows = [
        {"Leg": "Long call (wing)", "Strike": f"${chain['long_call_k']:.0f}",
         "Mid": _fmt_mid(chain['long_call_mid']), "Action": "BUY",
         "$/Contract": _cash(chain['long_call_mid'], "BUY")},
        {"Leg": "Short call",       "Strike": f"${chain['short_call_k']:.0f}",
         "Mid": _fmt_mid(chain['short_call_mid']), "Action": "SELL",
         "$/Contract": _cash(chain['short_call_mid'], "SELL")},
        {"Leg": "Short put",        "Strike": f"${chain['short_put_k']:.0f}",
         "Mid": _fmt_mid(chain['short_put_mid']), "Action": "SELL",
         "$/Contract": _cash(chain['short_put_mid'], "SELL")},
        {"Leg": "Long put (wing)",  "Strike": f"${chain['long_put_k']:.0f}",
         "Mid": _fmt_mid(chain['long_put_mid']), "Action": "BUY",
         "$/Contract": _cash(chain['long_put_mid'], "BUY")},
        {"Leg": "NET CREDIT", "Strike": "", "Mid": "", "Action": "",
         "$/Contract": (f"+${net_cash:.0f}" if net_cash >= 0 else f"-${abs(net_cash):.0f}")
                       if _has_prices else "—"},
    ]
    leg_table = dag.AgGrid(
        columnDefs=[
            {"field": "Leg",        "width": 200,
             "cellStyle": {"function": "params.data.Leg === 'NET CREDIT' ? {'fontWeight':'700','borderTop':'1px solid #374151'} : {}"}},
            {"field": "Strike",     "width": 150,
             "cellStyle": {"function": "params.data.Leg === 'NET CREDIT' ? {'borderTop':'1px solid #374151'} : {}"}},
            {"field": "Mid",        "width": 150,
             "cellStyle": {"function": "params.data.Leg === 'NET CREDIT' ? {'borderTop':'1px solid #374151'} : {}"}},
            {"field": "Action",     "width": 150,
             "cellStyle": {"function": "params.data.Leg === 'NET CREDIT' ? {'borderTop':'1px solid #374151'} : {}"}},
            {"field": "$/Contract", "flex": 1, "minWidth": 150,
             "cellStyle": {"function": "params.data.Leg === 'NET CREDIT' ? {'fontWeight':'700','borderTop':'1px solid #374151','color': params.value.startsWith('+') ? '#10b981' : '#ef4444'} : params.value.startsWith('+') ? {'color':'#10b981','fontWeight':'600'} : {'color':'#ef4444','fontWeight':'600'}"}},
        ],
        rowData=leg_rows,
        defaultColDef={"resizable": True},
        dashGridOptions={"domLayout": "autoHeight"},
        className=T.AGGRID_THEME,
        style={"width": "100%", "marginBottom": "16px"},
    )

    fig = _build_ic_payoff_fig(
        spot=spot,
        short_call_k=chain["short_call_k"], long_call_k=chain["long_call_k"],
        short_put_k=chain["short_put_k"],   long_put_k=chain["long_put_k"],
        net_credit=net_credit, dte_used=chain["dte_used"],
        atm_iv=atm_iv, ticker=ticker, best_exp=chain["best_exp"],
    )

    return html.Div([
        metrics,
        leg_table,
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
        html.P(
            "Solid purple = P&L at expiry · Dotted green = P&L today (BS) · "
            "Green dashed = 50% profit target · Red dashed = 2× stop",
            style={"color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "8px"},
        ),
    ])


for _slug in ("iron_condor_rules", "iron_condor_ai"):
    _make_ic_chart_callback(_slug)


# ── Paper Trade callback ──────────────────────────────────────────────────────

@callback(
    Output("str-ic-paper-feedback", "children"),
    Input("str-ic-paper-btn", "n_clicks"),
    State("str-ic-row-store", "data"),
    State("str-ic-contracts", "value"),
    prevent_initial_call=True,
)
def _paper_trade_ic(n_clicks, row, contracts):
    if not n_clicks or not row:
        return no_update
    chain = row.get("_chain")
    if not chain:
        return html.Span("No chain data.", style={"color": T.DANGER})
    ticker = row.get("Ticker", "")
    slug   = row.get("_slug", "iron_condor_rules")
    label  = _SLUG_TO_LABEL.get(slug, slug)
    try:
        from engine.positions import insert_open_ic_trade
        from db.client import get_engine
        engine = get_engine()
        n = int(contracts or 1)
        err = insert_open_ic_trade(
            engine=engine,
            account_id=1,
            ticker=ticker,
            chain=chain,
            strategy_name=label,
            contracts=n,
        )
        if err:
            return html.Span(f"Error: {err}", style={"color": T.DANGER})
        return html.Span(
            f"✓ {ticker} IC saved ({n} contract(s))",
            style={"color": T.SUCCESS},
        )
    except Exception as e:
        return html.Span(f"Error: {e}", style={"color": T.DANGER})


# ── Signal detail modal for VSF / IVR / VA / GEX ─────────────────────────────

def _make_signal_callback(slug: str):
    grid_id = f"str-{slug}-grid"

    @callback(
        Output("str-sig-modal",       "is_open",  allow_duplicate=True),
        Output("str-sig-modal-title", "children", allow_duplicate=True),
        Output("str-sig-row-store",   "data",     allow_duplicate=True),
        Input(grid_id, "selectedRows"),
        prevent_initial_call=True,
    )
    def _open_sig_modal(selected_rows):
        if not selected_rows:
            return no_update, no_update, no_update
        row    = {**selected_rows[0], "_slug": slug}
        ticker = row.get("Ticker", "")
        label  = _SLUG_TO_LABEL.get(slug, slug)
        score  = row.get("Score", "")
        title  = f"{ticker}  ·  {label}  ·  Score {score}"
        return True, title, row

    _open_sig_modal.__name__ = f"_open_sig_modal_{slug}"
    return _open_sig_modal


@callback(
    Output("str-sig-modal-body", "children"),
    Input("str-sig-row-store",   "data"),
    prevent_initial_call=True,
)
def _build_signal_body(row):
    if not row:
        return no_update

    slug   = row.get("_slug", "")
    ticker = row.get("Ticker", "")
    status = row.get("Status", "—")

    status_color = (T.SUCCESS if status == "Trade-Ready" else
                    T.WARNING if status == "Partial" else T.DANGER)

    def _mc(label, val, color=T.TEXT_PRIMARY):
        return html.Div([
            html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                   "fontWeight": "600", "textTransform": "uppercase",
                                   "marginBottom": "4px"}),
            html.Div(val,   style={"color": color, "fontSize": "1.05rem",
                                   "fontWeight": "700"}),
        ], style={**T.STYLE_CARD, "flex": "1", "minWidth": "100px", "padding": "10px 12px"})

    def _row(*cards):
        return html.Div(list(cards),
                        style={"display": "flex", "gap": "10px",
                               "flexWrap": "wrap", "marginBottom": "14px"})

    # ── Strategy-specific content ─────────────────────────────────────────────
    if slug == "vix_spike_fade":
        vix     = row.get("VIX", "—")
        vix20   = row.get("VIX 20d avg", "—")
        ratio   = row.get("VIX / 20d", "—")
        atm_iv  = row.get("ATM IV", "—")
        hv20    = row.get("HV20", "—")
        ivr     = row.get("IVR", "—")
        ma200   = row.get("MA200", "—")
        signal  = ("Buy put spread — VIX elevated, fade the spike back toward mean"
                   if float(str(ratio).rstrip("%") or 0) > 1.2
                   else "Monitor — VIX spike not sufficient")
        metrics = _row(
            _mc("VIX",        str(vix),   T.DANGER if float(str(vix) or 0) > 25 else T.TEXT_PRIMARY),
            _mc("VIX 20d Avg",str(vix20)),
            _mc("VIX / 20d",  str(ratio)),
            _mc("ATM IV",     str(atm_iv)),
            _mc("HV20",       str(hv20)),
            _mc("IVR",        str(ivr)),
            _mc("MA200",      str(ma200)),
            _mc("Status",     status, status_color),
        )

    elif slug == "ivr_credit_spread":
        atm_iv   = row.get("ATM IV", "—")
        ivr      = row.get("IVR", "—")
        vrp      = row.get("VRP", "—")
        hv20     = row.get("HV20", "—")
        iv_hv    = row.get("IV/HV", "—")
        trend    = row.get("Trend", "—")
        sp_type  = row.get("Spread Type", "—")
        signal   = f"{sp_type} — sell premium into elevated IV (IVR {ivr})"
        metrics  = _row(
            _mc("ATM IV",     str(atm_iv)),
            _mc("IVR",        str(ivr),  T.SUCCESS if status == "Trade-Ready" else T.TEXT_PRIMARY),
            _mc("VRP",        str(vrp)),
            _mc("HV20",       str(hv20)),
            _mc("IV/HV",      str(iv_hv)),
            _mc("Trend",      str(trend)),
            _mc("Spread Type",str(sp_type)),
            _mc("Status",     status, status_color),
        )

    elif slug == "vol_arbitrage":
        atm_iv = row.get("ATM IV", "—")
        hv20   = row.get("HV20", "—")
        iv_hv  = row.get("IV/HV", "—")
        vrp    = row.get("VRP", "—")
        ivr    = row.get("IVR", "—")
        try:
            ratio_f = float(str(iv_hv) or 0)
        except Exception:
            ratio_f = 0
        signal = (f"Sell straddle/strangle — IV {ratio_f:.1f}× HV, collect the vol premium"
                  if ratio_f >= 1.3 else "IV/HV spread insufficient for arb")
        metrics = _row(
            _mc("ATM IV", str(atm_iv)),
            _mc("HV20",   str(hv20)),
            _mc("IV/HV",  str(iv_hv),
                T.SUCCESS if ratio_f >= 1.3 else T.TEXT_PRIMARY),
            _mc("VRP",    str(vrp)),
            _mc("IVR",    str(ivr)),
            _mc("Status", status, status_color),
        )

    else:  # gex_positioning
        regime  = row.get("Regime", "—")
        sig     = row.get("Signal", "—")
        weight  = row.get("SPY Weight", "—")
        atr     = row.get("ATR%", "—")
        ret5d   = row.get("5d Return", "—")
        label_r = row.get("Regime Label", "—")
        sig_color = (T.SUCCESS if str(sig).upper() == "LONG" else
                     T.DANGER  if str(sig).upper() == "SHORT" else T.TEXT_MUTED)
        signal  = str(label_r)
        metrics = _row(
            _mc("Signal",     str(sig), sig_color),
            _mc("Regime",     str(regime)),
            _mc("SPY Weight", str(weight)),
            _mc("ATR%",       str(atr)),
            _mc("5d Return",  str(ret5d)),
        )

    score_val = row.get("Score", 0)
    score_color = (T.SUCCESS if float(str(score_val) or 0) >= 70 else
                   T.WARNING if float(str(score_val) or 0) >= 40 else T.DANGER)

    return html.Div([
        metrics,
        html.Div([
            html.Div("Signal", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                      "fontWeight": "600", "textTransform": "uppercase",
                                      "marginBottom": "6px"}),
            html.Div(signal, style={"color": T.TEXT_PRIMARY, "fontSize": "13px"}),
        ], style={**T.STYLE_CARD, "marginBottom": "14px", "padding": "12px 16px"}),
        html.Div([
            html.Span("Score  ", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
            html.Span(str(score_val), style={"color": score_color,
                                              "fontSize": "1.4rem", "fontWeight": "700"}),
            html.Span(" / 100", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
        ]),
    ])


@callback(
    Output("str-sig-modal", "is_open", allow_duplicate=True),
    Input("str-sig-modal-dismiss", "n_clicks"),
    prevent_initial_call=True,
)
def _dismiss_sig_modal(n):
    return False


for _slug in ("vix_spike_fade", "ivr_credit_spread", "vol_arbitrage", "gex_positioning"):
    _make_signal_callback(_slug)
