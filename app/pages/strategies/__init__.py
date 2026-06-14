"""
app/pages/strategies.py — Full Strategies page.

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

from dash_mantine_react_table import DashMantineReactTable as _MRT
from app.grid_helpers import (
    mrt_grid as _mrt_grid_shared,
    clickable_mrt_grid as _mrt_clickable,
)
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import html, dcc, callback, Input, Output, State, no_update, ALL

from app import theme as T, get_polygon_api_key

_DD = {**T.STYLE_DROPDOWN}  # shorthand for dropdown style

logger = logging.getLogger(__name__)

# ── Submodule imports — extracted into separate files for maintainability ────
# registry.py : strategy lists, universes, slug-set constants, _GUIDE_DIR
# columns.py  : AG-Grid column definitions per strategy + _COLS_BY_SLUG map
# format.py   : numeric formatters, _vix_banner, _status_pills, _load_guide
from app.pages.strategies.registry import (
    _STRATEGIES_RULES, _STRATEGIES_AI, _STRATEGIES, _SLUG_TO_LABEL,
    _UNIVERSE_TICKERS, _SPY_ONLY_SLUGS, _SECTOR_ETFS_LIST, _SECTOR_ONLY_SLUGS,
    _UNIVERSE_OPTIONS, _GUIDE_DIR, _STATUS_COLORS, get_strategy_status,
    get_strategy_score, get_score_color,
)


# ── AG Grid column definitions ───────────────────────────────────────────────
# Extracted to columns.py (pure dict literals, no callbacks).
from app.pages.strategies.columns import (
    _col, _COLS_BY_SLUG,
    _IC_COLS, _VSF_COLS, _IVR_COLS, _VA_COLS, _GEX_COLS, _BWB_COLS,
    _CAL_COLS, _EARN_COLS, _WHEEL_COLS, _BPS_COLS, _VTS_COLS, _EVC_COLS,
    _MRS_COLS, _CCA_COLS, _RCS_COLS, _PS_COLS, _HMM_COLS, _EMP_COLS,
    _SSD_COLS, _TRP_COLS, _NSN_COLS,
)


# ── Formatting helpers + VIX banner + status pills + guide loader ────────────
# Extracted to format.py.
from app.pages.strategies.format import (
    _fmt_pct, _fmt2, _fmt_price,
    _vix_banner, _status_pills, _load_guide,
)


# ── Strategy selector option builders (with review-status colour dots) ───────

def _checklist_options_with_status(strategies: list[dict]) -> list[dict]:
    """Convert a list of `{"label","value"}` entries to dbc.Checklist options
    where each label is prefixed with a coloured dot reflecting the strategy's
    review status (ready/reviewed/reviewing/avoid)."""
    out = []
    for s in strategies:
        slug = s["value"]
        status = get_strategy_status(slug)
        dot_color = _STATUS_COLORS[status]["dot"]
        out.append({
            "label": html.Span([
                html.Span("●", style={"color": dot_color, "marginRight": "5px",
                                       "fontSize": "12px",
                                       "verticalAlign": "middle"}),
                html.Span(s["label"], style={"verticalAlign": "middle"}),
            ], title=f"Status: {_STATUS_COLORS[status]['label']}"),
            "value": slug,
        })
    return out


# ── Screener filter param specs ───────────────────────────────────────────────

_SCREENER_PARAMS: dict[str, list[dict]] = {
    "iron_condor_rules": [
        {"id": "ivr_min",    "label": "IVR min",    "min": 0.0, "max": 1.0,  "step": 0.05, "default": 0.20, "fmt": ".0%"},
        {"id": "vix_min",    "label": "VIX min",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 14.0, "fmt": ".0f"},
        {"id": "vix_max",    "label": "VIX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 45.0, "fmt": ".0f"},
        {"id": "adx_max",    "label": "ADX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 35.0, "fmt": ".0f"},
        {"id": "atr_pct_max","label": "ATR% max",   "min": 0.0, "max": 0.10, "step": 0.005,"default": 0.030,"fmt": ".1%"},
    ],
    "iron_condor_ai": [
        {"id": "ivr_min",    "label": "IVR min",    "min": 0.0, "max": 1.0,  "step": 0.05, "default": 0.20, "fmt": ".0%"},
        {"id": "vix_min",    "label": "VIX min",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 14.0, "fmt": ".0f"},
        {"id": "vix_max",    "label": "VIX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 45.0, "fmt": ".0f"},
        {"id": "adx_max",    "label": "ADX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 35.0, "fmt": ".0f"},
        {"id": "atr_pct_max","label": "ATR% max",   "min": 0.0, "max": 0.10, "step": 0.005,"default": 0.030,"fmt": ".1%"},
    ],
    "vix_spike_fade": [
        {"id": "vix_spike_ratio","label": "VIX spike ratio","min": 1.0,"max": 3.0,"step": 0.1,"default": 1.20,"fmt": ".1f"},
        {"id": "vix_max",        "label": "VIX max",        "min": 0.0,"max": 80.0,"step": 1.0,"default": 45.0,"fmt": ".0f"},
    ],
    "ivr_credit_spread": [
        {"id": "ivr_min",    "label": "IVR min",    "min": 0.0, "max": 1.0,  "step": 0.05, "default": 0.40, "fmt": ".0%"},
        {"id": "vix_max",    "label": "VIX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 50.0, "fmt": ".0f"},
    ],
    "broken_wing_butterfly": [
        {"id": "ivr_max",    "label": "IVR max",    "min": 0.0, "max": 1.0,  "step": 0.05, "default": 0.35, "fmt": ".0%"},
        {"id": "adx_max",    "label": "ADX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 28.0, "fmt": ".0f"},
        {"id": "vix_max",    "label": "VIX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 30.0, "fmt": ".0f"},
    ],
    "calendar_spread": [
        {"id": "adx_max",           "label": "ADX max",        "min": 0.0, "max": 80.0, "step": 1.0,  "default": 22.0, "fmt": ".0f"},
        {"id": "vix_min",           "label": "VIX min",        "min": 0.0, "max": 40.0, "step": 1.0,  "default": 14.0, "fmt": ".0f"},
        {"id": "vix_max",           "label": "VIX max",        "min": 0.0, "max": 80.0, "step": 1.0,  "default": 25.0, "fmt": ".0f"},
        {"id": "hv_iv_spread_min",  "label": "IV>HV spread",   "min": 0.0, "max": 0.20, "step": 0.01, "default": 0.03, "fmt": ".0%"},
    ],
    "earnings_straddle": [
        {"id": "ivr_min",              "label": "IVR min",          "min": 0.0, "max": 1.0,  "step": 0.05, "default": 0.60, "fmt": ".0%"},
        {"id": "atm_iv_min",           "label": "ATM IV min",       "min": 0.0, "max": 1.0,  "step": 0.05, "default": 0.40, "fmt": ".0%"},
        {"id": "dte_to_earnings_min",  "label": "DTE to earn. min", "min": 1,   "max": 30,   "step": 1,    "default": 5,    "fmt": ".0f"},
        {"id": "dte_to_earnings_max",  "label": "DTE to earn. max", "min": 1,   "max": 30,   "step": 1,    "default": 10,   "fmt": ".0f"},
    ],
    "wheel_strategy": [
        {"id": "ivr_min",    "label": "IVR min",    "min": 0.0, "max": 1.0,  "step": 0.05, "default": 0.40, "fmt": ".0%"},
        {"id": "adx_max",    "label": "ADX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 30.0, "fmt": ".0f"},
        {"id": "vix_max",    "label": "VIX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 35.0, "fmt": ".0f"},
    ],
    "bull_put_spread": [
        {"id": "ivr_min",    "label": "IVR min",    "min": 0.0, "max": 1.0,  "step": 0.05, "default": 0.40, "fmt": ".0%"},
        {"id": "adx_max",    "label": "ADX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 30.0, "fmt": ".0f"},
        {"id": "vix_max",    "label": "VIX max",    "min": 0.0, "max": 80.0, "step": 1.0,  "default": 35.0, "fmt": ".0f"},
    ],
    "hmm_regime": [
        {"id": "vix_ceiling",           "label": "VIX ceiling",  "min": 20.0, "max": 60.0, "step": 1.0,  "default": 40.0, "fmt": ".0f"},
        {"id": "regime_confidence_min", "label": "Min P(state)", "min": 0.40, "max": 0.90, "step": 0.05, "default": 0.55, "fmt": ".2f"},
    ],
    "expiry_max_pain": [
        {"id": "vix_ceiling",   "label": "VIX ceiling", "min": 14.0, "max": 40.0, "step": 1.0,  "default": 25.0, "fmt": ".0f"},
        {"id": "min_dist_pct",  "label": "Min spot–pin",  "min": 0.001, "max": 0.020, "step": 0.001, "default": 0.005, "fmt": ".1%"},
        {"id": "max_dist_pct",  "label": "Max spot–pin",  "min": 0.010, "max": 0.060, "step": 0.005, "default": 0.035, "fmt": ".1%"},
    ],
    "short_squeeze_detector": [
        {"id": "max_vix",          "label": "VIX max",         "min": 20.0, "max": 50.0, "step": 1.0,  "default": 32.0, "fmt": ".0f"},
        {"id": "volume_ratio_min", "label": "Vol spike min",   "min": 1.5,  "max": 5.0,  "step": 0.1,  "default": 2.5,  "fmt": ".1f"},
        {"id": "signal_threshold", "label": "P(squeeze) min",  "min": 0.40, "max": 0.80, "step": 0.05, "default": 0.55, "fmt": ".2f"},
    ],
    "tail_risk_put_spread": [
        {"id": "vix_max_at_entry", "label": "VIX max",       "min": 20.0, "max": 60.0, "step": 1.0,  "default": 35.0, "fmt": ".0f"},
        {"id": "long_otm_pct",     "label": "Long leg OTM%", "min": 0.03, "max": 0.12, "step": 0.01, "default": 0.07, "fmt": ".0%"},
        {"id": "short_otm_pct",    "label": "Short leg OTM%","min": 0.12, "max": 0.25, "step": 0.01, "default": 0.18, "fmt": ".0%"},
        {"id": "dte_target",       "label": "Target DTE",    "min": 45,   "max": 120,  "step": 5,    "default": 75,   "fmt": ".0f"},
    ],
    "news_sentiment_nlp": [
        {"id": "vix_max",                "label": "VIX max",      "min": 20.0, "max": 60.0, "step": 1.0,  "default": 35.0, "fmt": ".0f"},
        {"id": "sentiment_z_threshold",  "label": "|z| min",      "min": 1.0,  "max": 3.5,  "step": 0.1,  "default": 2.0,  "fmt": ".1f"},
        {"id": "signal_threshold",       "label": "Model P min",  "min": 0.45, "max": 0.80, "step": 0.05, "default": 0.55, "fmt": ".2f"},
    ],
}


def _param_input(slug: str, p: dict) -> html.Div:
    """Single labelled number input for one screener filter param."""
    inp_id = {"type": f"str-{slug}-param", "index": p["id"]}
    return html.Div([
        html.Label(p["label"], style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                      "marginBottom": "2px", "display": "block"}),
        dbc.Input(id=inp_id, type="number", value=p["default"],
                  min=p["min"], max=p["max"], step=p["step"],
                  style={"width": "90px", "fontSize": "12px", "height": "30px",
                         "backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                         "border": f"1px solid {T.BORDER}"}),
    ], style={"display": "flex", "flexDirection": "column"})


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

    params_spec  = _SCREENER_PARAMS.get(slug, [])
    filter_tog   = f"str-{slug}-filter-toggle"
    filter_col   = f"str-{slug}-filter-collapse"

    spy_only     = slug in _SPY_ONLY_SLUGS
    sector_only  = slug in _SECTOR_ONLY_SLUGS
    locked       = spy_only or sector_only
    locked_label = "SPY only" if spy_only else "11 Sector ETFs" if sector_only else ""
    locked_value = "SPY" if spy_only else ",".join(_SECTOR_ETFS_LIST) if sector_only else None

    # Strategy-specific info banner (e.g., HMM doesn't really use the screener)
    info_banner = None
    if slug == "hmm_regime":
        info_banner = dbc.Alert([
            html.Strong("HMM is a single-ticker strategy. "),
            "The Screener scans a universe for candidates, but HMM has ",
            html.Code("max_concurrent = 1"),
            " and is normally run on a single broad-market ticker (SPY). ",
            "For today's signal and model status, use the ",
            html.Strong("Live & Model"),
            " tab instead. Scanning here will only return tickers that have a trained ",
            html.Code(".pkl"),
            " in ", html.Code("saved_models/"), " and ≥ 252 bars of history.",
        ],
            color="info",
            style={"fontSize": "12px", "padding": "10px 14px",
                   "marginBottom": "14px", "borderLeft": f"3px solid {T.ACCENT}",
                   "backgroundColor": "rgba(99,102,241,0.08)", "color": T.TEXT_PRIMARY,
                   "border": f"1px solid {T.BORDER}"},
            dismissable=False,
        )

    return html.Div([
        # Optional strategy-specific info banner
        *([info_banner] if info_banner is not None else []),

        # VIX banner — populated by callback
        html.Div(id=vix_banner_id),

        # Controls row
        html.Div([
            html.Div([
                # Universe selector — hidden for locked strategies
                dbc.Select(
                    id=universe_id,
                    options=[{"label": o["label"], "value": o["value"]}
                             for o in _UNIVERSE_OPTIONS],
                    value="ETF Core",
                    style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                           "border": f"1px solid {T.BORDER}", "fontSize": "13px",
                           "width": "150px", "height": "34px",
                           "display": "none" if locked else "block"},
                ),
                # Custom input — hidden for locked strategies; value pre-set
                dbc.Input(
                    id=custom_id,
                    value=locked_value,
                    placeholder="Custom tickers: SPY,QQQ,IWM",
                    disabled=locked,
                    style={"fontSize": "13px", "backgroundColor": T.BG_ELEVATED,
                           "border": f"1px solid {T.BORDER}", "color": T.TEXT_PRIMARY,
                           "width": "260px", "height": "34px",
                           "display": "none" if locked else "block"},
                ),
                # Locked badge shown for strategies with fixed universes
                html.Span(locked_label, style={
                    "fontSize": "12px", "fontWeight": "600",
                    "backgroundColor": "#1a3a5c", "color": "#60a5fa",
                    "border": "1px solid #2563eb", "borderRadius": "6px",
                    "padding": "5px 12px", "height": "34px",
                    "display": "flex" if locked else "none",
                    "alignItems": "center",
                }) if locked else html.Div(),
                dbc.Button("Scan", id=scan_id,
                    style={"backgroundColor": T.ACCENT, "border": "none",
                           "fontSize": "13px", "fontWeight": "600",
                           "height": "34px", "padding": "0 20px",
                           "whiteSpace": "nowrap"}),
                dbc.Button("⚙ Filters", id=filter_tog, size="sm", color="secondary",
                           outline=True,
                           style={"fontSize": "12px", "height": "34px",
                                  "padding": "0 12px"}) if params_spec else html.Div(),
            ], style={"display": "flex", "gap": "8px", "alignItems": "center",
                      "padding": "10px 0"}),

            # Collapsible filter panel
            dbc.Collapse(
                html.Div([
                    *[_param_input(slug, p) for p in params_spec],
                    html.Div(
                        dbc.Button("Reset defaults", id=f"str-{slug}-param-reset",
                                   size="sm", color="secondary", outline=True,
                                   style={"fontSize": "11px", "height": "30px",
                                          "alignSelf": "flex-end"}),
                        style={"display": "flex", "alignItems": "flex-end"}
                    ),
                ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                          "padding": "10px 12px", "marginBottom": "8px",
                          "backgroundColor": T.BG_ELEVATED,
                          "borderRadius": "6px", "border": f"1px solid {T.BORDER}"}),
                id=filter_col, is_open=False,
            ) if params_spec else html.Div(),
        ], style={"marginBottom": "10px"}),

        # Status pills
        html.Div(id=status_id),

        # Results grid — clickable MRT (rows fire JS-bridged callback into
        # f"{grid_id}-clicked" hidden Dash input; old cellClicked callbacks are
        # rewritten in _make_signal_callback / _make_ic_chart_callback).
        dcc.Loading(
            html.Div(
                _mrt_clickable(
                    grid_id=grid_id,
                    aggrid_cols=cols,
                    data=[],
                    height=340,
                ),
                id=loading_id,
            ),
            type="circle", color=T.ACCENT,
        ),
    ])


def _score_badge(slug: str) -> html.Div:
    """Credibility score/grade banner shown above a strategy's guide article.

    Reflects the 2026-05-30 hardening review (edge realism + implementation
    quality), NOT realized P&L. Renders nothing for unscored slugs.
    """
    sc = get_strategy_score(slug)
    if not sc:
        return html.Div()
    score, grade = sc
    color = get_score_color(score)
    return html.Div([
        html.Div([
            html.Span(grade, style={"fontSize": "20px", "fontWeight": "700",
                                    "color": color, "marginRight": "10px"}),
            html.Span(f"{score}/100", style={"fontSize": "13px", "fontWeight": "600",
                                             "color": T.TEXT_PRIMARY, "marginRight": "8px"}),
            html.Span("credibility score", style={"fontSize": "11px", "color": T.TEXT_MUTED,
                                                  "textTransform": "uppercase",
                                                  "letterSpacing": "0.05em"}),
        ], style={"display": "flex", "alignItems": "baseline"}),
        html.Div("Edge realism + implementation quality (post-hardening review). "
                 "Not realized P&L — pending clean backtest re-run.",
                 style={"fontSize": "11px", "color": T.TEXT_MUTED, "marginTop": "4px"}),
    ], style={
        "padding": "10px 14px", "marginBottom": "16px",
        "borderLeft": f"3px solid {color}",
        "background": "rgba(255,255,255,0.03)", "borderRadius": "4px",
    })


def _guide_layout(slug: str) -> html.Div:
    content = _load_guide(slug)
    return html.Div([
        _score_badge(slug),
        html.Div([
            dcc.Markdown(
                content,
                className="guide-md",
                dangerously_allow_html=False,
                style={"color": T.TEXT_PRIMARY, "fontSize": "14px", "lineHeight": "1.7",
                       "maxWidth": "1200px"},
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
    # ── Load strategy's UI params via the shared registry ────────────────────
    ui_params = _get_ui_params_for_slug(slug)

    today_str = date.today().isoformat()

    # ── Controls row ──────────────────────────────────────────────────────────
    def _lbl(text):
        return html.Label(text, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                       "fontWeight": "600", "textTransform": "uppercase",
                                       "marginBottom": "4px", "display": "block"})
    _inp = {"backgroundColor": T.BG_ELEVATED, "border": f"1px solid {T.BORDER}",
            "color": T.TEXT_PRIMARY, "fontSize": "13px", "height": "34px"}

    controls = dbc.Card(dbc.CardBody([
        html.Div([
            html.Div([_lbl("Ticker"),
                dbc.Input(id=f"str-{slug}-bt-ticker", value="SPY", placeholder="e.g. SPY",
                          style={**_inp, "width": "100px"})]),
            html.Div([_lbl("From"),
                dbc.Input(id=f"str-{slug}-bt-from", type="date", value="2022-01-01",
                          style={**_inp, "width": "160px"})]),
            html.Div([_lbl("To"),
                dbc.Input(id=f"str-{slug}-bt-to", type="date", value=today_str,
                          style={**_inp, "width": "160px"})]),
            html.Div([_lbl("Starting Capital ($)"),
                dbc.Input(id=f"str-{slug}-bt-capital", type="number", value=10000,
                          min=1000, step=1000,
                          style={**_inp, "width": "160px"})]),
            html.Div([_lbl("\u00a0"),
                dbc.Button("Run Backtest", id=f"str-{slug}-bt-run", color="primary",
                           style={"fontWeight": "600", "fontSize": "13px",
                                  "height": "34px", "padding": "0 20px",
                                  "whiteSpace": "nowrap"})]),
        ], style={"display": "flex", "gap": "10px", "alignItems": "flex-end",
                  "padding": "2px 0"}),
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
                def _fmt_mark(v):
                    if isinstance(v, float) and v != int(v):
                        return str(round(v, 4)).rstrip("0").rstrip(".")
                    return str(int(v))

                marks_vals = sorted({mn, mx, dflt})
                marks = {v: {"label": _fmt_mark(v),
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
            "Performance analytics coming soon.",
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


# ── Live Signal + Model tab (HMM Regime) ──────────────────────────────────────

_HMM_MODEL_DIR = Path(__file__).parent.parent.parent.parent / "saved_models"

_HMM_STATE_REF = [
    ("State 0", "Bull / quiet drift",  "Bull put credit spread", "0.20Δ short, 5% wing, 30 DTE", T.SUCCESS),
    ("State 1", "Chop / mean-reverting", "Iron condor",          "0.16Δ both sides, 5% wings, 35 DTE", T.WARNING),
    ("State 2", "Crisis / bear",        "Long put debit spread", "0.30Δ long put, 5% short, 45 DTE", T.DANGER),
]

_HMM_ENTRY_GATES = [
    ("p_state >= 0.60",                  "Posterior confidence floor"),
    ("VIX <= 40",                        "Dislocation circuit breaker"),
    ("spot/forward posterior agree",     "Regime stability check"),
    ("No open trade (max_concurrent=1)", "Single-position discipline"),
    ("Not a known event day",            "FOMC / CPI / NFP / OpEx pause"),
]


def _hmm_load_model(ticker: str = "spy"):
    """Try to load the saved HMM model. Returns (model, status_text, status_color, fit_date)."""
    path = _HMM_MODEL_DIR / f"hmm_regime_{ticker.lower()}.pkl"
    if not path.exists():
        return None, f"No saved model at {path.name} — run a backtest to train.", T.WARNING, None
    try:
        import pickle
        with open(path, "rb") as f:
            model = pickle.load(f)
        if model is None or not getattr(model, "_fitted", False):
            return None, "Model file present but not fitted — re-run backtest.", T.DANGER, None
        from datetime import datetime
        fit_date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        backend = getattr(model, "backend", "unknown")
        return model, f"Loaded ({backend}) — last fit {fit_date}", T.SUCCESS, fit_date
    except Exception as e:
        return None, f"Failed to load model: {e}", T.DANGER, None


def _hmm_live_signal_tab(slug: str) -> html.Div:
    if slug != "hmm_regime":
        return html.Div()

    model, status_text, status_color, fit_date = _hmm_load_model("spy")

    # ── Model status banner ──────────────────────────────────────────────────
    status_card = dbc.Card(dbc.CardBody([
        dbc.Row([
            dbc.Col(html.Div([
                html.Span("●  ", style={"color": status_color, "fontSize": "16px"}),
                html.Span("Model status: ", style={
                    "color": T.TEXT_MUTED, "fontSize": "12px", "fontWeight": "600",
                    "textTransform": "uppercase", "letterSpacing": "0.06em"}),
                html.Span(status_text, style={"color": T.TEXT_PRIMARY, "fontSize": "13px"}),
            ]), width=True),
            dbc.Col(html.Div([
                html.Span("Algorithm: ", style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                                 "fontWeight": "600", "textTransform": "uppercase"}),
                html.Span("3-state Gaussian HMM (hmmlearn)",
                          style={"color": T.ACCENT, "fontSize": "12px",
                                 "fontFamily": "JetBrains Mono, monospace"}),
            ]), width="auto"),
        ], align="center"),
    ]), style={**T.STYLE_CARD, "borderLeft": f"3px solid {status_color}", "marginBottom": "16px"})

    # ── Sanity check row (only if model loaded) ──────────────────────────────
    sanity_card = None
    if model is not None:
        try:
            sm = model.sorted_means()  # (3, 3) array
            tmat = model.sorted_transmat()  # (3, 3) or None
            rv_means = [float(sm[i, 2]) for i in range(3)]
            rv_ratio = rv_means[2] / max(rv_means[0], 1e-6)
            rv_ok = rv_ratio >= 2.0
            if tmat is not None:
                diag = [float(tmat[i, i]) for i in range(3)]
                diag_ok = all(d >= 0.85 for d in diag)
                diag_text = f"{diag[0]:.2f} / {diag[1]:.2f} / {diag[2]:.2f}"
            else:
                diag_ok = None
                diag_text = "n/a (GMM fallback)"
        except Exception as e:
            rv_means, rv_ratio, rv_ok = [0, 0, 0], 0, False
            diag_ok, diag_text = False, f"error: {e}"

        def _check_row(label: str, value: str, ok: bool | None) -> html.Div:
            if ok is True:
                ind = "✓"; color = T.SUCCESS
            elif ok is False:
                ind = "✗"; color = T.DANGER
            else:
                ind = "—"; color = T.TEXT_MUTED
            return html.Div([
                html.Span(ind, style={"color": color, "fontSize": "14px",
                                       "fontWeight": "700", "marginRight": "10px",
                                       "fontFamily": "JetBrains Mono, monospace"}),
                html.Span(label, style={"color": T.TEXT_PRIMARY, "fontSize": "12px"}),
                html.Span(f"  →  {value}", style={"color": T.TEXT_MUTED, "fontSize": "12px",
                                                    "fontFamily": "JetBrains Mono, monospace"}),
            ], style={"marginBottom": "6px"})

        sanity_card = dbc.Card(dbc.CardBody([
            html.Div("Model sanity checks", style={
                "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
                "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "10px"}),
            html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 10px"}),
            _check_row("rv20 mean(state 2) > 2× mean(state 0)",
                       f"{rv_means[0]:.3f} / {rv_means[1]:.3f} / {rv_means[2]:.3f}  (ratio {rv_ratio:.2f}×)",
                       rv_ok),
            _check_row("Transition matrix diagonal > 0.85 (regime persistence)",
                       diag_text, diag_ok),
        ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

    # ── State reference cards ────────────────────────────────────────────────
    state_cards = []
    for label, desc, trade, struct, color in _HMM_STATE_REF:
        state_cards.append(dbc.Col(dbc.Card(dbc.CardBody([
            html.Div(label, style={"color": color, "fontSize": "11px",
                                    "fontWeight": "700", "textTransform": "uppercase",
                                    "letterSpacing": "0.08em", "marginBottom": "4px"}),
            html.Div(desc, style={"color": T.TEXT_PRIMARY, "fontSize": "13px",
                                   "fontWeight": "600", "marginBottom": "8px"}),
            html.Div(trade, style={"color": T.ACCENT, "fontSize": "12px",
                                    "fontFamily": "JetBrains Mono, monospace",
                                    "marginBottom": "4px"}),
            html.Div(struct, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                     "fontFamily": "JetBrains Mono, monospace"}),
        ]), style={**T.STYLE_CARD, "borderTop": f"3px solid {color}", "height": "100%"}), md=4))

    state_ref_row = dbc.Row(state_cards, style={"marginBottom": "16px"})

    # ── Entry checklist (static reference) ───────────────────────────────────
    gate_rows = [html.Div([
        html.Span("□  ", style={"color": T.TEXT_MUTED, "fontFamily": "JetBrains Mono, monospace"}),
        html.Span(gate, style={"color": T.TEXT_PRIMARY, "fontSize": "12px",
                                "fontFamily": "JetBrains Mono, monospace"}),
        html.Span(f"   — {note}", style={"color": T.TEXT_MUTED, "fontSize": "11px"}),
    ], style={"marginBottom": "5px"}) for gate, note in _HMM_ENTRY_GATES]

    gates_card = dbc.Card(dbc.CardBody([
        html.Div("Entry checklist (all must pass to open a trade)", style={
            "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "10px"}),
        html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 10px"}),
        *gate_rows,
    ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

    # ── Compute today's signal — placeholder (callback to be wired) ──────────
    compute_card = dbc.Card(dbc.CardBody([
        html.Div("Today's signal", style={
            "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "10px"}),
        html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 10px"}),
        html.P(
            "Click below to fetch the latest SPY + VIX data, run the loaded model, "
            "and display today's regime posterior and trade recommendation.",
            style={"color": T.TEXT_MUTED, "fontSize": "12px", "marginBottom": "12px"},
        ),
        dbc.Button(
            "Compute today's signal",
            id=f"str-{slug}-live-compute-btn",
            color="primary", size="sm",
            disabled=(model is None),
            style={"marginBottom": "12px"},
        ),
        html.Div(
            id=f"str-{slug}-live-signal-output",
            children=html.P("(Awaiting compute — output will appear here)",
                            style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                   "fontStyle": "italic", "margin": "0"}),
        ),
    ]), style={**T.STYLE_CARD, "marginBottom": "16px"})

    return html.Div([
        status_card,
        *([sanity_card] if sanity_card is not None else []),
        state_ref_row,
        gates_card,
        compute_card,
    ])


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

_SAVED_MODEL_PATH = Path(__file__).parent.parent.parent.parent / "saved_models" / "iron_condor_ai.pkl"
_SAMPLE_DATA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "sample_ic_training_data.csv"


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

        grid = _mrt_grid_shared(
            data=preview.to_dict("records"),
            aggrid_cols=col_defs,
            height=400,
            enable_pagination=False,
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
        {"id": "ic",            "label": "Iron Condor Tests",             "module": "test_iron_condor_rules"},
        {"id": "ic_integration","label": "IC Integration (DB + Polygon)", "module": "test_ic_rules_integration"},
    ],
    "vix_spike_fade":        [{"id": "vsf",   "label": "VIX Spike Fade Tests",        "module": "test_vix_spike_fade"}],
    "vol_arbitrage":         [{"id": "va",    "label": "Vol Arbitrage Tests",          "module": "test_vol_arbitrage"}],
    "iron_condor_ai":        [{"id": "icai",  "label": "IC AI Tests",                 "module": "test_iron_condor_ai"}],
    "ivr_credit_spread":     [{"id": "ivr",   "label": "IVR Credit Spread Tests",     "module": "test_ivr_credit_spread"}],
    "gex_positioning":       [{"id": "gex",   "label": "GEX Positioning Tests",       "module": "test_gex_positioning"}],
    "dealer_gamma_regime":   [{"id": "dgr",   "label": "Dealer Gamma Regime Tests",   "module": "test_dealer_gamma_regime"}],
    "broken_wing_butterfly": [{"id": "bwb",   "label": "BWB Strategy Tests",          "module": "test_broken_wing_butterfly"}],
    "calendar_spread":       [{"id": "cal",   "label": "Calendar Spread Tests",       "module": "test_calendar_spread"}],
    "earnings_straddle":     [{"id": "earn",  "label": "Earnings Short Condor Tests", "module": "test_earnings_straddle"}],
    "wheel_strategy":        [{"id": "wheel", "label": "Wheel (CSP) Tests",           "module": "test_wheel_strategy"}],
    "bull_put_spread":       [{"id": "bps",   "label": "Bull Put Spread Tests",       "module": "test_bull_put_spread"}],
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
                    searchable=False,
                    style={"width": "260px", "fontSize": "12px",
                           "backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY},
                ),
                dcc.Dropdown(
                    id=f"str-{slug}-test-marks",
                    options=_TEST_MARK_OPTIONS,
                    value="all",
                    clearable=False,
                    searchable=False,
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
            html.Div([
                html.Span("▸ ", style={"color": T.ACCENT}),
                html.Span("Select a test suite and click ",
                          style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
                html.Span("▶ Run Tests", style={"color": T.TEXT_PRIMARY,
                          "fontSize": "12px", "fontWeight": "600"}),
                html.Span(" to execute.", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
            ]),
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
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
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
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
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

    # Live Signal & Model tab — HMM Regime only
    if slug == "hmm_regime":
        tabs.append(dbc.Tab(
            _hmm_live_signal_tab(slug),
            label="Live & Model",
            tab_id=f"str-{slug}-inner-live",
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
            html.Div([
                html.H1("Strategies", style={
                    "color": T.TEXT_PRIMARY, "fontSize": "26px",
                    "fontWeight": "800", "letterSpacing": "-0.02em", "margin": "0",
                }),
                html.P(
                    "Select strategies to screen opportunities, run backtests, and read guides.",
                    style={"color": T.TEXT_MUTED, "fontSize": "13px",
                           "margin": "2px 0 0 0"},
                ),
            ], style={"marginBottom": "18px"}),

            # ── Strategy selector (AI vs Rules-Based) ────────────────────────
            dbc.Card(dbc.CardBody([
                # Legend row — status colour key
                html.Div([
                    html.Span("Review status:", style={
                        "color": T.TEXT_MUTED, "fontSize": "10px",
                        "fontWeight": "700", "textTransform": "uppercase",
                        "letterSpacing": "0.06em", "marginRight": "10px"}),
                    *[html.Span([
                        html.Span("●", style={"color": meta["dot"],
                            "marginRight": "4px", "fontSize": "12px"}),
                        html.Span(meta["label"], style={
                            "color": T.TEXT_MUTED, "fontSize": "11px",
                            "marginRight": "14px"}),
                    ]) for st, meta in _STATUS_COLORS.items()],
                ], style={"display": "flex", "alignItems": "center",
                          "marginBottom": "12px", "flexWrap": "wrap"}),

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
                            options=_checklist_options_with_status(_STRATEGIES_RULES),
                            value=[],
                            inline=True,
                            inputStyle={"marginRight": "4px", "accentColor": T.ACCENT},
                            labelStyle={
                                "color": T.TEXT_PRIMARY, "fontSize": "13px",
                                "marginRight": "18px", "cursor": "pointer",
                                "whiteSpace": "nowrap",
                            },
                        ),
                    ], style={"flex": "1 1 500px", "minWidth": "320px"}),

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
                            options=_checklist_options_with_status(_STRATEGIES_AI),
                            value=[],
                            inline=True,
                            inputStyle={"marginRight": "4px", "accentColor": "#a78bfa"},
                            labelStyle={
                                "color": T.TEXT_PRIMARY, "fontSize": "13px",
                                "marginRight": "18px", "cursor": "pointer",
                                "whiteSpace": "nowrap",
                            },
                        ),
                    ], style={"flex": "1 1 500px", "minWidth": "320px"}),

                ], style={"display": "flex", "alignItems": "flex-start",
                          "flexWrap": "wrap", "gap": "12px", "rowGap": "16px"}),

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
                        color="success", size="sm", disabled=True,
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
                dbc.ModalFooter([
                    html.Span(id="str-sig-paper-feedback",
                              style={"fontSize": "12px", "marginRight": "auto"}),
                    html.Div([
                        html.Span("Contracts",
                                  style={"color": T.TEXT_MUTED, "fontSize": "12px",
                                         "alignSelf": "center", "marginRight": "6px"}),
                        dbc.Input(id="str-sig-contracts", type="number", value=1,
                                  min=1, max=50, step=1,
                                  style={"width": "60px", "fontSize": "13px",
                                         "height": "32px",
                                         "backgroundColor": T.BG_ELEVATED,
                                         "border": f"1px solid {T.BORDER}",
                                         "color": T.TEXT_PRIMARY}),
                    ], style={"display": "flex", "alignItems": "center",
                              "marginRight": "10px"}),
                    dbc.Button("Paper Trade", id="str-sig-paper-btn",
                               disabled=False,
                               style={"backgroundColor": T.SUCCESS, "border": "none",
                                      "fontWeight": "600", "fontSize": "13px",
                                      "marginRight": "8px"}),
                    dbc.Button("Dismiss", id="str-sig-modal-dismiss",
                               color="secondary", size="sm"),
                ], style={"backgroundColor": T.BG_ELEVATED,
                          "borderTop": f"1px solid {T.BORDER}",
                          "display": "flex", "alignItems": "center"}),
            ], id="str-sig-modal", size="xl", is_open=False, scrollable=True),
            dcc.Store(id="str-sig-row-store"),

            # ── Store + outer tabs container ──────────────────────────────────
            dcc.Store(id="str-strategy-tabs-store", data=[]),
            html.Div(id="str-outer-tabs-container", children=[
                html.P(
                    "Select at least one strategy above.",
                    style={"color": T.TEXT_MUTED, "fontSize": "14px"},
                )
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
    # If user typed anything in the custom field, always use it (overrides dropdown)
    if custom and custom.strip():
        return [t.strip().upper() for t in custom.split(",") if t.strip()]
    return _UNIVERSE_TICKERS.get(universe, [])


def _fetch_ic_strikes(ticker: str, api_key: str, spot: float, adx_ok: bool) -> tuple[dict | None, str | None]:
    """Fetch real options chain for ticker and return (chain_dict, err_str). chain is None on failure."""
    from engine.screener import _get_options_chain, _find_strike, _get_chain_mid
    target_delta = 0.16 if adx_ok else 0.10
    wing_pct     = 0.05

    exp_chain, best_exp, dte_used, err = _get_options_chain(ticker, api_key, spot)
    if err:
        return None, err
    if exp_chain is None or exp_chain.empty:
        return None, "Polygon returned no contracts in the 30–60 DTE window"

    calls = exp_chain[exp_chain["type"].str.lower() == "call"].sort_values("strike")
    puts  = exp_chain[exp_chain["type"].str.lower() == "put"].sort_values("strike", ascending=False)

    short_call_k, short_call_mid = _find_strike(calls, "call", spot, target_delta)
    short_put_k,  short_put_mid  = _find_strike(puts,  "put",  spot, target_delta)
    if short_call_k is None or short_put_k is None:
        n_calls = len(calls); n_puts = len(puts)
        return None, f"Could not find {target_delta:.0%}-delta strikes (chain had {n_calls} calls, {n_puts} puts in window)"

    wing_w = round(spot * wing_pct, 0)

    # Long call wing must be ABOVE short call (further OTM).
    calls_above = calls[calls["strike"] > short_call_k]
    if calls_above.empty:
        return None, f"No call strikes above short call ${short_call_k:.0f} — chain too narrow"
    long_call_mid, long_call_k = _get_chain_mid(calls_above, short_call_k + wing_w,
                                                 exclude_strike=short_call_k)
    if long_call_k <= short_call_k:
        return None, f"Call wing ${long_call_k:.0f} ≤ short call ${short_call_k:.0f} — invalid spread"

    # Long put wing must be BELOW short put (further OTM).
    puts_below = puts[puts["strike"] < short_put_k]
    if puts_below.empty:
        return None, f"No put strikes below short put ${short_put_k:.0f} — chain too narrow"
    long_put_mid, long_put_k = _get_chain_mid(puts_below, short_put_k - wing_w,
                                               exclude_strike=short_put_k)
    if long_put_k >= short_put_k:
        return None, f"Put wing ${long_put_k:.0f} ≥ short put ${short_put_k:.0f} — invalid spread"

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
    }, None


def _fetch_ps_strikes(ticker: str, api_key: str, spot: float,
                      itm_pct: float = 0.05, wing_pct: float = 0.04) -> tuple[dict | None, str | None]:
    """
    Fetch real Polygon options chain for Put Steal and find ITM put strikes.
    short_put target: spot × (1 - itm_pct)  — slightly ITM
    long_put  target: short_put × (1 - wing_pct) — wing below
    Returns (chain_dict, err_str).
    """
    from engine.screener import _get_options_chain, _get_chain_mid

    exp_chain, best_exp, dte_used, err = _get_options_chain(ticker, api_key, spot)
    if err:
        return None, err
    if exp_chain is None or exp_chain.empty:
        return None, "No contracts in 15–45 DTE window"

    puts = exp_chain[exp_chain["type"].str.lower() == "put"].sort_values("strike", ascending=False)
    if puts.empty:
        return None, "No put contracts found"

    target_short = spot * (1.0 - itm_pct)
    target_long  = target_short * (1.0 - wing_pct)

    # Find closest real strike to target_short
    puts_sorted_short = puts.copy()
    puts_sorted_short["_dist"] = (puts_sorted_short["strike"] - target_short).abs()
    best_short = puts_sorted_short.nsmallest(1, "_dist")
    if best_short.empty:
        return None, "Could not find short put strike"
    short_put_k   = float(best_short["strike"].iloc[0])
    short_put_mid = float(best_short["mid"].iloc[0]) if not best_short["mid"].isna().iloc[0] else None

    # Find closest real strike to target_long (must be below short)
    puts_below = puts[puts["strike"] < short_put_k].copy()
    if puts_below.empty:
        return None, f"No put strikes below short put ${short_put_k:.0f}"
    long_put_mid, long_put_k = _get_chain_mid(puts_below, target_long, exclude_strike=short_put_k)

    if long_put_k >= short_put_k:
        return None, f"Long put ${long_put_k:.0f} ≥ short put ${short_put_k:.0f}"

    def _m(v): return v if v is not None else 0.0

    net_credit = _m(short_put_mid) - _m(long_put_mid)
    put_width  = short_put_k - long_put_k
    max_loss   = put_width - net_credit

    return {
        "short_put_k":   short_put_k,
        "long_put_k":    long_put_k,
        "short_put_mid": _m(short_put_mid),
        "long_put_mid":  _m(long_put_mid),
        "net_credit":    net_credit,
        "put_width":     put_width,
        "max_loss":      max_loss,
        "best_exp":      best_exp,
        "dte_used":      dte_used,
    }, None


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


def _hmm_trade_preview(state: int, spot: float, vix: float, ticker: str = "SPY") -> dict | None:
    """Build a state-specific trade preview for the HMM Regime modal.

    Mirrors the strategy's actual structures (see strategies/hmm_regime.py):
      state 0  → bull put credit spread (short 0.20Δ put, long 5% wider)        30 DTE
      state 1  → iron condor (0.16Δ both sides, 5% wings)                       35 DTE
      state 2  → long put debit spread (long 0.30Δ put, short 5% lower)         45 DTE

    Strikes are computed via BS delta inversion at IV proxy = VIX / 100 (same
    approximation the strategy uses internally). Returns a dict with:
        metrics     : html.Div  — metric cards row
        legs_table  : dash component — leg-by-leg breakdown (MRT)
        chart       : dcc.Graph — payoff diagram (P&L at expiry)
    Or None if inputs are degenerate.
    """
    if spot <= 0 or vix <= 0 or state not in (0, 1, 2):
        return None

    iv = max(vix / 100.0, 0.05)
    r  = 0.045

    sqT_per_yr = math.sqrt
    cdf = _scipy_norm.cdf

    def bs_call(S, K, T, sig):
        if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
            return max(0.0, S - K)
        d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqT_per_yr(T))
        d2 = d1 - sig * sqT_per_yr(T)
        return float(S * cdf(d1) - K * math.exp(-r * T) * cdf(d2))

    def bs_put(S, K, T, sig):
        if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
            return max(0.0, K - S)
        d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqT_per_yr(T))
        d2 = d1 - sig * sqT_per_yr(T)
        return float(K * math.exp(-r * T) * cdf(-d2) - S * cdf(-d1))

    def bs_delta(S, K, T, sig, option_type):
        if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
            return (1.0 if S > K else 0.0) if option_type == "call" else (-1.0 if S < K else 0.0)
        d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqT_per_yr(T))
        return float(cdf(d1)) if option_type == "call" else float(cdf(d1) - 1.0)

    def strike_for_delta(target_abs_delta, T, option_type):
        from scipy.optimize import brentq
        def obj(K):
            return abs(bs_delta(spot, K, T, iv, option_type)) - target_abs_delta
        try:
            return float(brentq(obj, spot * 0.40, spot * 1.60, xtol=0.01, maxiter=60))
        except (ValueError, RuntimeError):
            sign = 1.0 if option_type == "call" else -1.0
            return spot * math.exp(sign * iv * sqT_per_yr(T))

    # ── Build per-state structure ──────────────────────────────────────────
    if state == 0:
        # Bull put credit spread — 30 DTE
        dte = 30
        tau = dte / 365.0
        short_put_K = strike_for_delta(0.20, tau, "put")
        long_put_K  = short_put_K * 0.95
        sp = bs_put(spot, short_put_K, tau, iv)
        lp = bs_put(spot, long_put_K,  tau, iv)
        net_credit = max(0.01, sp - lp)
        wing       = short_put_K - long_put_K
        max_loss   = max(0.01, wing - net_credit)
        profit_target = net_credit * 0.50
        stop_loss     = -net_credit * 2.0
        be_lower      = short_put_K - net_credit
        be_upper      = None  # bull put has no upper BE (unbounded profit cap)

        trade_label = "Bull put credit spread"
        delta_target = 0.20
        is_credit = True

        # Payoff at expiry
        prices = np.linspace(spot * 0.85, spot * 1.10, 400)
        pnl_exp = np.where(
            prices >= short_put_K, net_credit * 100,
            np.where(prices >= long_put_K,
                     (net_credit - (short_put_K - prices)) * 100,
                     -max_loss * 100)
        )
        leg_rows = [
            {"Leg": "Short put",        "Strike": f"${short_put_K:.0f}",
             "Mid": f"${sp:.2f}", "Action": "SELL",
             "$/Contract": f"+${sp*100:.2f}"},
            {"Leg": "Long put (wing)",  "Strike": f"${long_put_K:.0f}",
             "Mid": f"${lp:.2f}", "Action": "BUY",
             "$/Contract": f"-${lp*100:.2f}"},
            {"Leg": "NET CREDIT",       "Strike": "", "Mid": "", "Action": "",
             "$/Contract": f"+${net_credit*100:.2f}"},
        ]
        be_marks = [("BE", be_lower)]

    elif state == 1:
        # Iron condor — 35 DTE
        dte = 35
        tau = dte / 365.0
        short_call_K = strike_for_delta(0.16, tau, "call")
        short_put_K  = strike_for_delta(0.16, tau, "put")
        long_call_K  = short_call_K * 1.05
        long_put_K   = short_put_K  * 0.95
        cs = bs_call(spot, short_call_K, tau, iv)
        cl = bs_call(spot, long_call_K,  tau, iv)
        sp = bs_put (spot, short_put_K,  tau, iv)
        lp = bs_put (spot, long_put_K,   tau, iv)
        net_credit = max(0.01, (cs - cl) + (sp - lp))
        wing       = max(short_call_K - long_call_K, short_put_K - long_put_K) * -1 + (long_call_K - short_call_K)
        # wing width is symmetric; use call-side
        wing       = long_call_K - short_call_K
        max_loss   = max(0.01, wing - net_credit)
        profit_target = net_credit * 0.50
        stop_loss     = -net_credit * 2.0
        be_lower      = short_put_K  - net_credit
        be_upper      = short_call_K + net_credit

        trade_label  = "Iron condor"
        delta_target = 0.16
        is_credit    = True

        prices = np.linspace(spot * 0.85, spot * 1.15, 400)
        call_spread = np.minimum(0, short_call_K - prices) + np.maximum(0, prices - long_call_K)
        put_spread  = np.minimum(0, prices - short_put_K)  + np.maximum(0, long_put_K  - prices)
        pnl_exp     = (net_credit + call_spread + put_spread) * 100

        leg_rows = [
            {"Leg": "Long call (wing)", "Strike": f"${long_call_K:.0f}",
             "Mid": f"${cl:.2f}", "Action": "BUY",
             "$/Contract": f"-${cl*100:.2f}"},
            {"Leg": "Short call",       "Strike": f"${short_call_K:.0f}",
             "Mid": f"${cs:.2f}", "Action": "SELL",
             "$/Contract": f"+${cs*100:.2f}"},
            {"Leg": "Short put",        "Strike": f"${short_put_K:.0f}",
             "Mid": f"${sp:.2f}", "Action": "SELL",
             "$/Contract": f"+${sp*100:.2f}"},
            {"Leg": "Long put (wing)",  "Strike": f"${long_put_K:.0f}",
             "Mid": f"${lp:.2f}", "Action": "BUY",
             "$/Contract": f"-${lp*100:.2f}"},
            {"Leg": "NET CREDIT",       "Strike": "", "Mid": "", "Action": "",
             "$/Contract": f"+${net_credit*100:.2f}"},
        ]
        be_marks = [("BE", be_lower), ("BE", be_upper)]

    else:  # state == 2
        # Long put debit spread — 45 DTE
        dte = 45
        tau = dte / 365.0
        long_put_K  = strike_for_delta(0.30, tau, "put")
        short_put_K = long_put_K * 0.95
        lp = bs_put(spot, long_put_K,  tau, iv)
        sp = bs_put(spot, short_put_K, tau, iv)
        net_debit  = max(0.01, lp - sp)
        max_profit = (long_put_K - short_put_K) - net_debit
        max_loss   = net_debit  # debit paid IS the max loss
        profit_target = net_debit * 1.00   # +100% of debit
        stop_loss     = -net_debit * 0.50  # -50% of debit
        be_upper = long_put_K - net_debit  # breakeven where the spread ITM portion covers debit
        be_lower = None

        trade_label  = "Long put debit spread"
        delta_target = 0.30
        is_credit    = False

        prices = np.linspace(spot * 0.80, spot * 1.10, 400)
        pnl_exp = np.where(
            prices >= long_put_K, -net_debit * 100,
            np.where(prices >= short_put_K,
                     ((long_put_K - prices) - net_debit) * 100,
                     ((long_put_K - short_put_K) - net_debit) * 100)
        )

        leg_rows = [
            {"Leg": "Long put",          "Strike": f"${long_put_K:.0f}",
             "Mid": f"${lp:.2f}", "Action": "BUY",
             "$/Contract": f"-${lp*100:.2f}"},
            {"Leg": "Short put (wing)",  "Strike": f"${short_put_K:.0f}",
             "Mid": f"${sp:.2f}", "Action": "SELL",
             "$/Contract": f"+${sp*100:.2f}"},
            {"Leg": "NET DEBIT",         "Strike": "", "Mid": "", "Action": "",
             "$/Contract": f"-${net_debit*100:.2f}"},
        ]
        be_marks = [("BE", be_upper)]

    # ── Metric cards ───────────────────────────────────────────────────────
    def _mc(label: str, val: str, color: str = T.TEXT_PRIMARY) -> html.Div:
        return html.Div([
            html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                    "fontWeight": "600", "textTransform": "uppercase",
                                    "marginBottom": "4px"}),
            html.Div(val,   style={"color": color, "fontSize": "1.05rem",
                                    "fontWeight": "700"}),
        ], style={**T.STYLE_CARD, "flex": "1", "minWidth": "110px", "padding": "10px 12px"})

    nc100 = (net_credit if is_credit else net_debit) * 100
    ml100 = max_loss * 100
    pt100 = profit_target * 100
    metric_cards = [
        _mc("Net Credit" if is_credit else "Net Debit",
            f"+${nc100:.2f}" if is_credit else f"-${nc100:.2f}",
            T.SUCCESS if is_credit else T.WARNING),
        _mc("Max Loss",     f"-${ml100:.2f}", T.DANGER),
        _mc("50% Target" if is_credit else "100% Target",
            f"+${pt100:.2f}", T.SUCCESS),
    ]
    if be_upper is not None:
        metric_cards.append(_mc("Upper BE", f"${be_upper:.2f}"))
    if be_lower is not None:
        metric_cards.append(_mc("Lower BE", f"${be_lower:.2f}"))
    metric_cards.append(_mc("DTE", f"{dte}d"))
    metric_cards.append(_mc("Δ target", f"~{delta_target:.0%}"))
    metric_cards.append(_mc("IV proxy", f"{iv*100:.1f}%"))

    metrics = html.Div(metric_cards,
        style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "14px"})

    # ── Legs table ─────────────────────────────────────────────────────────
    legs_table = _mrt_grid_shared(
        data=leg_rows,
        aggrid_cols=[
            {"field": "Leg"},
            {"field": "Strike"},
            {"field": "Mid"},
            {"field": "Action"},
            {"field": "$/Contract"},
        ],
        height=240,
        enable_pagination=False,
    )

    # ── Payoff figure ──────────────────────────────────────────────────────
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prices, y=np.where(pnl_exp >= 0, pnl_exp, 0),
        fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prices, y=np.where(pnl_exp < 0, pnl_exp, 0),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=prices, y=pnl_exp,
        line=dict(color="#6366f1", width=2), name="P&L at expiry",
        hovertemplate="$%{x:.2f} → $%{y:.0f}<extra>At expiry</extra>"))

    fig.add_hline(y=profit_target * 100, line=dict(color="#10b981", width=1.5, dash="dash"),
        annotation_text=f"✅ target: +${profit_target*100:.0f}",
        annotation_position="top left", annotation_font_color="#10b981")
    fig.add_hline(y=stop_loss * 100, line=dict(color="#ef4444", width=1.5, dash="dash"),
        annotation_text=f"🛑 stop: ${stop_loss*100:.0f}",
        annotation_position="bottom left", annotation_font_color="#ef4444")
    fig.add_hline(y=0, line=dict(color="#374151", width=1))
    fig.add_vline(x=spot, line=dict(color="#f59e0b", width=1.5, dash="dash"),
        annotation_text=f"Spot ${spot:.0f}", annotation_font_color="#f59e0b")
    for label, x in be_marks:
        if x is not None:
            fig.add_vline(x=x, line=dict(color="#9ca3af", width=1, dash="dot"),
                annotation_text=f"{label} ${x:.0f}",
                annotation_font_color="#9ca3af")

    fig.update_layout(
        title=dict(text=f"{ticker} {trade_label}  |  {dte} DTE  |  IV proxy {iv*100:.1f}%",
                   font=dict(size=13)),
        xaxis_title="Underlying Price",
        yaxis_title="P&L per Contract ($)",
        height=360, margin=dict(l=0, r=0, t=50, b=0),
        paper_bgcolor=T.BG_BASE, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_SEC, size=12),
        xaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f"),
        yaxis=dict(gridcolor=T.BORDER, tickformat="$,.0f", zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.15),
        template="plotly_dark",
    )
    chart = dcc.Graph(figure=fig, config={"displayModeBar": False})

    return {"metrics": metrics, "legs_table": legs_table, "chart": chart}


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
    status = "Trade-Ready" if (r.get("all_pass") and r.get("_chain")) else (
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
        "_chain":      r.get("_chain"),          # real strikes dict or None
        "_chain_err":  r.get("_chain_err"),     # error string if chain fetch failed
        "_atm_iv_raw": r.get("ATM IV"),         # raw float for BS calc
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
    spy_w  = r.get("SPY Weight", 0)
    score  = r.get("score", round(spy_w * 100))   # fallback: SPY weight as score proxy
    status = "Trade-Ready" if spy_w >= 0.75 else ("Partial" if spy_w >= 0.35 else "Blocked")
    return {
        "Ticker":       r.get("Ticker", ""),
        "Price":        round(r.get("Price", 0), 2),
        "VIX":          round(r.get("VIX", 0), 2),
        "Regime":       r.get("Regime", "—"),
        "SPY Weight":   f"{spy_w*100:.0f}%",
        "Signal":       r.get("Signal", "—"),
        "ATR%":         f"{r.get('ATR%', 0)*100:.2f}%",
        "5d Return":    f"{r.get('5d Return', 0)*100:.1f}%",
        "Regime Label": r.get("Regime Label", "—"),
        "Score":        score,
        "Status":       status,
        "all_pass":     spy_w >= 0.75,
        "n_pass":       1 if spy_w > 0 else 0,
    }


def _display_row_bwb(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":       r.get("Ticker", ""),
        "Price":        round(r.get("Price", 0), 2),
        "ATM IV":       _fmt_pct(r.get("ATM IV")),
        "IVR":          _fmt_pct(r.get("IVR")),
        "VIX":          round(r.get("VIX", 0), 2),
        "ADX":          round(r.get("ADX", 0), 1),
        "Narrow Wing":  _fmt2(r.get("Narrow Wing")),
        "Wide Wing":    _fmt2(r.get("Wide Wing")),
        "Score":        round(r.get("score", 0), 1),
        "Status":       status,
        "all_pass":     r.get("all_pass", False),
        "n_pass":       r.get("n_pass", 0),
    }


def _display_row_cal(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":   r.get("Ticker", ""),
        "Price":    round(r.get("Price", 0), 2),
        "ATM IV":   _fmt_pct(r.get("ATM IV")),
        "HV20":     _fmt_pct(r.get("HV20")),
        "VRP":      _fmt_pct(r.get("VRP")),
        "IVR":      _fmt_pct(r.get("IVR")),
        "VIX":      round(r.get("VIX", 0), 2),
        "ADX":      round(r.get("ADX", 0), 1),
        "Score":    round(r.get("score", 0), 1),
        "Status":   status,
        "all_pass": r.get("all_pass", False),
        "n_pass":   r.get("n_pass", 0),
    }


def _display_row_earn(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    dte = r.get("Days to Earnings")
    return {
        "Ticker":           r.get("Ticker", ""),
        "Price":            round(r.get("Price", 0), 2),
        "ATM IV":           _fmt_pct(r.get("ATM IV")),
        "IVR":              _fmt_pct(r.get("IVR")),
        "Days to Earnings": str(dte) if dte is not None else "—",
        "Impl. Move":       _fmt_pct(r.get("Impl. Move")),
        "Straddle Credit":  _fmt_price(r.get("Straddle Credit")),
        "VIX":              round(r.get("VIX", 0), 2),
        "Score":            round(r.get("score", 0), 1),
        "Status":           status,
        "all_pass":         r.get("all_pass", False),
        "n_pass":           r.get("n_pass", 0),
    }


def _display_row_wheel(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":     r.get("Ticker", ""),
        "Price":      round(r.get("Price", 0), 2),
        "MA50":       _fmt2(r.get("MA50")),
        "ATM IV":     _fmt_pct(r.get("ATM IV")),
        "IVR":        _fmt_pct(r.get("IVR")),
        "VIX":        round(r.get("VIX", 0), 2),
        "ADX":        round(r.get("ADX", 0), 1),
        "Put Strike": _fmt2(r.get("Put Strike")),
        "~Premium":   _fmt_price(r.get("~Premium")),
        "Score":      round(r.get("score", 0), 1),
        "Status":     status,
        "all_pass":   r.get("all_pass", False),
        "n_pass":     r.get("n_pass", 0),
    }


def _display_row_bps(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    return {
        "Ticker":       r.get("Ticker", ""),
        "Price":        round(r.get("Price", 0), 2),
        "MA50":         _fmt2(r.get("MA50")),
        "ATM IV":       _fmt_pct(r.get("ATM IV")),
        "IVR":          _fmt_pct(r.get("IVR")),
        "Short Strike": _fmt2(r.get("Short Strike")),
        "Long Strike":  _fmt2(r.get("Long Strike")),
        "Width":        _fmt2(r.get("Width")),
        "~Credit":      _fmt_price(r.get("~Credit")),
        "Credit/Width": _fmt2(r.get("Credit/Width")),
        "Score":        round(r.get("score", 0), 1),
        "Status":       status,
        "all_pass":     r.get("all_pass", False),
        "n_pass":       r.get("n_pass", 0),
    }


def _display_row_put_steal(r: dict) -> dict:
    status = "Trade-Ready" if r.get("all_pass") else (
        "Partial" if r.get("n_pass", 0) > 0 else "Blocked"
    )
    chain = r.get("_chain") or {}
    # Use real Polygon strikes/credit if available, else fall back to BS estimates
    short_k  = chain.get("short_put_k",  r.get("Short Put"))
    long_k   = chain.get("long_put_k",   r.get("Long Put"))
    credit   = chain.get("net_credit",   r.get("~Credit"))
    max_loss = chain.get("max_loss",     None)
    exp      = chain.get("best_exp",     "")
    source   = "Polygon" if chain else "~BS est."
    return {
        "Ticker":    r.get("Ticker", ""),
        "Price":     round(r.get("Price", 0), 2),
        "NII":       f"{r.get('NII', 0):.3f}",
        "Strike X":  _fmt2(r.get("Strike X")),
        "Short Put": _fmt2(short_k),
        "Long Put":  _fmt2(long_k),
        "~Credit":   _fmt_price(credit),
        "Max Loss":  _fmt_price(-max_loss) if max_loss else "—",
        "Expiry":    exp,
        "IV Src":    source,
        "ATM IV":    _fmt_pct(r.get("ATM IV")),
        "IVR":       _fmt_pct(r.get("IVR")),
        "VIX":       round(r.get("VIX", 0), 1),
        "Score":     round(r.get("score", 0), 1),
        "Status":    status,
        "all_pass":  r.get("all_pass", False),
        "n_pass":    r.get("n_pass", 0),
        "_chain":    chain,
        "_chain_err": r.get("_chain_err", ""),
    }


def _display_row_hmm(r: dict) -> dict:
    status = r.get("Status", "—")
    return {
        "Ticker":   r.get("Ticker", ""),
        "Price":    round(r.get("Price", 0), 2),
        "VIX":      round(r.get("VIX", 0), 2),
        "IVR":      _fmt_pct(r.get("IVR")),
        "Regime":   r.get("Regime", "—"),
        "State":    r.get("State", "—"),
        "P(state)": _fmt2(r.get("P(state)")),
        "Trade":    r.get("Trade", "—"),
        "Signal":   r.get("Signal", "—"),
        "5d Ret":   f"{(r.get('5d Ret')  or 0)*100:+.1f}%",
        "20d Ret":  f"{(r.get('20d Ret') or 0)*100:+.1f}%",
        "Mode":     r.get("Mode", "—"),
        "Score":    round(r.get("score", 0), 1),
        "Status":   status,
        "all_pass": r.get("all_pass", False),
        "n_pass":   r.get("n_pass", 0),
    }


def _display_row_emp(r: dict) -> dict:
    return {
        "Ticker":      r.get("Ticker", ""),
        "Price":       round(r.get("Price", 0), 2),
        "VIX":         round(r.get("VIX", 0), 2),
        "ATM IV":      _fmt_pct(r.get("ATM IV")),
        "IVR":         _fmt_pct(r.get("IVR")),
        "OpEx Week":   r.get("OpEx Week", "—"),
        "DTE to OpEx": r.get("DTE to OpEx", "—"),
        "Structure":   r.get("Structure", "—"),
        "Score":       round(r.get("score", 0), 1),
        "Status":      r.get("Status", "—"),
        "all_pass":    r.get("all_pass", False),
        "n_pass":      r.get("n_pass", 0),
    }


def _display_row_ssd(r: dict) -> dict:
    return {
        "Ticker":     r.get("Ticker", ""),
        "Price":      round(r.get("Price", 0), 2),
        "VIX":        round(r.get("VIX", 0), 2),
        "IVR":        _fmt_pct(r.get("IVR")),
        "Vol Ratio":  f"{(r.get('Vol Ratio') or 0):.2f}×",
        "5d Ret":     f"{(r.get('5d Ret')  or 0)*100:+.1f}%",
        "20d Ret":    f"{(r.get('20d Ret') or 0)*100:+.1f}%",
        "P(squeeze)": _fmt2(r.get("P(squeeze)")),
        "Structure":  r.get("Structure", "—"),
        "Mode":       r.get("Mode", "—"),
        "Score":      round(r.get("score", 0), 1),
        "Status":     r.get("Status", "—"),
        "all_pass":   r.get("all_pass", False),
        "n_pass":     r.get("n_pass", 0),
    }


def _display_row_trp(r: dict) -> dict:
    return {
        "Ticker":       r.get("Ticker", ""),
        "Price":        round(r.get("Price", 0), 2),
        "VIX":          round(r.get("VIX", 0), 2),
        "ATM IV":       _fmt_pct(r.get("ATM IV")),
        "IVR":          _fmt_pct(r.get("IVR")),
        "Long Strike":  _fmt2(r.get("Long Strike")),
        "Short Strike": _fmt2(r.get("Short Strike")),
        "Width":        _fmt2(r.get("Width")),
        "DTE":          r.get("DTE", "—"),
        "~Debit":       _fmt_price(r.get("~Debit")),
        "Max Payout":   _fmt_price(r.get("Max Payout")),
        "Structure":    r.get("Structure", "—"),
        "Score":        round(r.get("score", 0), 1),
        "Status":       r.get("Status", "—"),
        "all_pass":     r.get("all_pass", False),
        "n_pass":       r.get("n_pass", 0),
    }


def _display_row_nsn(r: dict) -> dict:
    return {
        "Ticker":     r.get("Ticker", ""),
        "Price":      round(r.get("Price", 0), 2),
        "VIX":        round(r.get("VIX", 0), 2),
        "IVR":        _fmt_pct(r.get("IVR")),
        "1d Ret":     f"{(r.get('1d Ret')  or 0)*100:+.2f}%",
        "5d Ret":     f"{(r.get('5d Ret')  or 0)*100:+.1f}%",
        "z (proxy)":  _fmt2(r.get("z (proxy)")),
        "z thresh":   _fmt2(r.get("z thresh")),
        "Signal":     r.get("Signal", "—"),
        "Structure":  r.get("Structure", "—"),
        "Mode":       r.get("Mode", "—"),
        "Score":      round(r.get("score", 0), 1),
        "Status":     r.get("Status", "—"),
        "all_pass":   r.get("all_pass", False),
        "n_pass":     r.get("n_pass", 0),
    }


# ── Core scan logic ───────────────────────────────────────────────────────────

def _run_scan(slug: str, universe: str, custom: str | None, api_key: str,
              param_overrides: dict | None = None):
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
        _score_broken_wing_butterfly,
        _score_calendar_spread,
        _score_earnings_straddle,
        _score_wheel_strategy,
        _score_bull_put_spread,
        _score_put_steal,
        _score_hmm_regime,
        _score_expiry_max_pain,
        _score_short_squeeze_detector,
        _score_tail_risk_put_spread,
        _score_news_sentiment_nlp,
        _DEFAULT_PARAMS,
    )

    # Locked-universe strategies ignore the universe/custom inputs
    if slug in _SPY_ONLY_SLUGS:
        tickers = ["SPY"]
    elif slug in _SECTOR_ONLY_SLUGS:
        tickers = _SECTOR_ETFS_LIST
    else:
        tickers = _resolve_tickers(universe, custom)
    if not tickers:
        return [], html.P("No tickers in universe.", style={"color": T.WARNING}), html.Div()

    vix_series, price_dfs, iv_all = _fetch_data(tickers, api_key)
    params = {**_DEFAULT_PARAMS.get(slug, {}), **(param_overrides or {})}

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
                chain, chain_err = _fetch_ic_strikes(
                    ticker, api_key,
                    spot=r["Price"],
                    adx_ok=r.get("adx_ok", True),
                )
                r["_chain"]     = chain
                r["_chain_err"] = chain_err
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

    elif slug == "broken_wing_butterfly":
        for ticker in price_dfs:
            r = _score_broken_wing_butterfly(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "calendar_spread":
        for ticker in price_dfs:
            r = _score_calendar_spread(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "earnings_straddle":
        for ticker in price_dfs:
            r = _score_earnings_straddle(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
                days_to_earnings=None,   # live days-to-earnings not yet wired
            )
            if r:
                raw_rows.append(r)

    elif slug == "wheel_strategy":
        for ticker in price_dfs:
            r = _score_wheel_strategy(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "bull_put_spread":
        for ticker in price_dfs:
            r = _score_bull_put_spread(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "put_steal":
        for ticker in price_dfs:
            r = _score_put_steal(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                # Fetch real Polygon options chain for actual strikes & mids
                chain, chain_err = _fetch_ps_strikes(
                    ticker, api_key,
                    spot=r["Price"],
                    itm_pct=params.get("itm_pct", 0.05),
                    wing_pct=0.04,
                )
                r["_chain"]     = chain
                r["_chain_err"] = chain_err
                raw_rows.append(r)

    elif slug == "hmm_regime":
        for ticker in price_dfs:
            r = _score_hmm_regime(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "expiry_max_pain":
        for ticker in price_dfs:
            r = _score_expiry_max_pain(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "short_squeeze_detector":
        for ticker in price_dfs:
            r = _score_short_squeeze_detector(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "tail_risk_put_spread":
        for ticker in price_dfs:
            r = _score_tail_risk_put_spread(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    elif slug == "news_sentiment_nlp":
        for ticker in price_dfs:
            r = _score_news_sentiment_nlp(
                ticker,
                price_dfs[ticker],
                vix_series,
                iv_all.get(ticker, {}),
                params,
            )
            if r:
                raw_rows.append(r)

    # Format rows for AG Grid
    fmt_map = {
        "iron_condor_rules":    _display_row_ic,
        "iron_condor_ai":       _display_row_ic,
        "vix_spike_fade":       _display_row_vsf,
        "ivr_credit_spread":    _display_row_ivr,
        "vol_arbitrage":        _display_row_va,
        "gex_positioning":      _display_row_gex,
        "broken_wing_butterfly": _display_row_bwb,
        "calendar_spread":      _display_row_cal,
        "earnings_straddle":    _display_row_earn,
        "wheel_strategy":       _display_row_wheel,
        "bull_put_spread":      _display_row_bps,
        "put_steal":            _display_row_put_steal,
        # New strategies (2026-05-01)
        "hmm_regime":              _display_row_hmm,
        "expiry_max_pain":         _display_row_emp,
        "short_squeeze_detector":  _display_row_ssd,
        "tail_risk_put_spread":    _display_row_trp,
        "news_sentiment_nlp":      _display_row_nsn,
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
    params_spec  = _SCREENER_PARAMS.get(slug, [])
    param_ids    = [{"type": f"str-{slug}-param", "index": p["id"]} for p in params_spec]

    @callback(
        Output(grid_id,   "data"),    # MRT uses `data` (not AgGrid's `rowData`)
        Output(status_id, "children"),
        Output(vix_id,    "children"),
        Input(scan_id,    "n_clicks"),
        State(universe_id, "value"),
        State(custom_id,   "value"),
        *([State({"type": f"str-{slug}-param", "index": ALL}, "value")] if params_spec else []),
        prevent_initial_call=True,
    )
    def _scan(n_clicks, universe, custom, *args):
        param_vals = args[0] if args else []
        overrides  = {p["id"]: v for p, v in zip(params_spec, param_vals) if v is not None}
        api_key = get_polygon_api_key()
        if not api_key:
            msg = html.P(
                "No Polygon API key found. Set POLYGON_API_KEY env var.",
                style={"color": T.WARNING, "fontSize": "13px"},
            )
            return no_update, msg, no_update

        try:
            rows, status_div, vix_div = _run_scan(slug, universe or "ETF Core", custom, api_key,
                                                   param_overrides=overrides)
            return rows, status_div, vix_div
        except Exception as exc:
            logger.exception(f"Scan error for {slug}: {exc}")
            err = html.P(f"Scan error: {exc}", style={"color": T.DANGER, "fontSize": "13px"})
            return [], err, no_update

    _scan.__name__ = f"_scan_{slug}"

    # Filter toggle
    if params_spec:
        filter_tog = f"str-{slug}-filter-toggle"
        filter_col = f"str-{slug}-filter-collapse"
        reset_id   = f"str-{slug}-param-reset"

        @callback(
            Output(filter_col, "is_open"),
            Input(filter_tog,  "n_clicks"),
            State(filter_col,  "is_open"),
            prevent_initial_call=True,
        )
        def _toggle_filters(n, is_open):
            return not is_open
        _toggle_filters.__name__ = f"_toggle_filters_{slug}"

        @callback(
            Output({"type": f"str-{slug}-param", "index": ALL}, "value"),
            Input(reset_id, "n_clicks"),
            prevent_initial_call=True,
        )
        def _reset_params(_):
            return [p["default"] for p in params_spec]
        _reset_params.__name__ = f"_reset_params_{slug}"

    return _scan


# Register callbacks for all 6 strategies at module import time
for _slug in [s["value"] for s in _STRATEGIES]:
    _make_scan_callback(_slug)


# ── Backtest tab ──────────────────────────────────────────────────────────────

_STRATEGY_CLASSES_BT = {
    "iron_condor_rules":     ("strategies.iron_condor_rules",     "IronCondorRulesStrategy"),
    "iron_condor_ai":        ("strategies.iron_condor_ai",        "IronCondorAIStrategy"),
    "vix_spike_fade":        ("strategies.vix_spike_fade",        "VIXSpikeFadeStrategy"),
    "ivr_credit_spread":     ("strategies.ivr_credit_spread",     "IVRCreditSpreadStrategy"),
    "vol_arbitrage":         ("strategies.vol_arbitrage",         "VolArbitrageStrategy"),
    "gex_positioning":       ("strategies.gex_positioning",       "GexPositioningStrategy"),
    "dealer_gamma_regime":   ("strategies.dealer_gamma_regime",   "DealerGammaRegimeStrategy"),
    "broken_wing_butterfly": ("strategies.broken_wing_butterfly", "BrokenWingButterflyStrategy"),
    "calendar_spread":       ("strategies.calendar_spread",       "CalendarSpreadStrategy"),
    "earnings_straddle":     ("strategies.earnings_straddle",     "EarningsStraddleStrategy"),
    "wheel_strategy":        ("strategies.wheel_strategy",        "WheelStrategy"),
    "bull_put_spread":       ("strategies.bull_put_spread",       "BullPutSpreadStrategy"),
    # AI strategies (5 new)
    "vix_term_structure":    ("strategies.vix_term_structure",    "VIXTermStructureStrategy"),
    "earnings_vol_crush":    ("strategies.earnings_vol_crush",    "EarningsVolCrushStrategy"),
    "momentum_regime_spread":("strategies.momentum_regime_spread","MomentumRegimeSpreadStrategy"),
    "covered_call_ai":       ("strategies.covered_call_ai",       "CoveredCallAIStrategy"),
    "rs_credit_spread":      ("strategies.rs_credit_spread",      "RSCreditSpreadStrategy"),
    "put_steal":             ("strategies.put_steal",             "PutStealStrategy"),
    # Tier A (5 new)
    "hmm_regime":            ("strategies.hmm_regime",            "HMMRegimeStrategy"),
    "expiry_max_pain":       ("strategies.expiry_max_pain",       "ExpiryMaxPainStrategy"),
    "short_squeeze_detector":("strategies.short_squeeze_detector","ShortSqueezeDetectorStrategy"),
    "tail_risk_put_spread":  ("strategies.tail_risk_put_spread",  "TailRiskPutSpreadStrategy"),
    "news_sentiment_nlp":    ("strategies.news_sentiment_nlp",    "NewsSentimentNLPStrategy"),
    # Tier B (5 new)
    "fomc_event_straddle":   ("strategies.fomc_event_straddle",   "FOMCEventStraddleStrategy"),
    "earnings_pin_risk":     ("strategies.earnings_pin_risk",     "EarningsPinRiskStrategy"),
    "tail_risk_long_put":    ("strategies.tail_risk_long_put",    "TailRiskLongPutStrategy"),
    "calendar_spread_vix":   ("strategies.calendar_spread_vix",   "VIXCalendarSpreadStrategy"),
    "yield_curve_regime":    ("strategies.yield_curve_regime",    "YieldCurveRegimeStrategy"),
    "vol_calendar_spread":   ("strategies.vol_calendar_spread",   "VolCalendarSpreadStrategy"),
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


def _build_hmm_regime_panel(regime_df, extra: dict) -> dbc.Card | None:
    """HMM-specific results panel: posterior time series + state distribution + health flags."""
    if regime_df is None or regime_df.empty:
        return None
    if not all(c in regime_df.columns for c in ("p_state0", "p_state1", "p_state2")):
        return None

    df = regime_df.dropna(subset=["p_state0", "p_state1", "p_state2"]).copy()
    if df.empty:
        return None

    # ── Posterior stacked area ────────────────────────────────────────────────
    fig = make_subplots(rows=1, cols=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["p_state0"], mode="lines",
        name="P(state 0) bull", line=dict(color=T.SUCCESS, width=1.2),
        stackgroup="one", fillcolor="rgba(16,185,129,0.55)",
        hovertemplate="%{x|%Y-%m-%d}  P0=%{y:.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["p_state1"], mode="lines",
        name="P(state 1) chop", line=dict(color=T.WARNING, width=1.2),
        stackgroup="one", fillcolor="rgba(245,158,11,0.55)",
        hovertemplate="%{x|%Y-%m-%d}  P1=%{y:.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["p_state2"], mode="lines",
        name="P(state 2) crisis", line=dict(color=T.DANGER, width=1.2),
        stackgroup="one", fillcolor="rgba(239,68,68,0.55)",
        hovertemplate="%{x|%Y-%m-%d}  P2=%{y:.2f}<extra></extra>"))
    fig.add_hline(y=0.60, line_dash="dash", line_color=T.TEXT_MUTED, line_width=1,
                  annotation_text="Entry floor 0.60", annotation_position="top right",
                  annotation_font=dict(size=10, color=T.TEXT_MUTED))
    fig.update_layout(
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_PRIMARY, family="Inter, sans-serif", size=12),
        height=340, margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="center", x=0.5,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        hovermode="x unified", template="plotly_dark",
    )
    fig.update_xaxes(gridcolor=T.BORDER, showgrid=True)
    fig.update_yaxes(gridcolor=T.BORDER, range=[0, 1.05], tickformat=".0%")

    # ── State distribution summary ────────────────────────────────────────────
    state_counts = df["state"].value_counts(normalize=True).reindex([0, 1, 2], fill_value=0.0)
    feat = extra.get("feature_importance", {}) or {}
    mean_p0 = float(feat.get("mean_p_state0", state_counts.get(0, 0.0))) * 100
    mean_p1 = float(feat.get("mean_p_state1", state_counts.get(1, 0.0))) * 100
    mean_p2 = float(feat.get("mean_p_state2", state_counts.get(2, 0.0))) * 100

    def _stat_chip(label: str, value: str, color: str) -> html.Div:
        return html.Div([
            html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                   "fontWeight": "700", "textTransform": "uppercase",
                                   "letterSpacing": "0.05em", "marginBottom": "4px"}),
            html.Div(value, style={"color": color, "fontSize": "1.15rem",
                                   "fontWeight": "700", "fontFamily": "JetBrains Mono, monospace"}),
        ], style={**T.STYLE_CARD, "flex": "1", "minWidth": "110px",
                  "padding": "10px 14px", "marginRight": "8px"})

    # ── Health flags ──────────────────────────────────────────────────────────
    n_bars = len(df)
    n_entry = int((df[["p_state0", "p_state1", "p_state2"]].max(axis=1) >= 0.60).sum())
    pct_confident = 100.0 * n_entry / max(n_bars, 1)
    backend = extra.get("hmm_backend", "unknown")
    health_msg = "OK" if backend == "hmmlearn" else "GMM fallback (iid)"
    health_color = T.SUCCESS if backend == "hmmlearn" else T.WARNING

    stats_row = html.Div([
        _stat_chip("Bull state (avg)",  f"{mean_p0:.1f}%", T.SUCCESS),
        _stat_chip("Chop state (avg)",  f"{mean_p1:.1f}%", T.WARNING),
        _stat_chip("Crisis state (avg)", f"{mean_p2:.1f}%", T.DANGER),
        _stat_chip("Confident bars",   f"{pct_confident:.1f}%", T.ACCENT),
        _stat_chip("Backend",          health_msg, health_color),
    ], style={"display": "flex", "gap": "0", "flexWrap": "wrap", "marginBottom": "12px"})

    return dbc.Card(dbc.CardBody([
        html.Div("HMM Regime Posterior", style={
            "color": T.ACCENT, "fontSize": "11px", "fontWeight": "700",
            "textTransform": "uppercase", "letterSpacing": "0.08em",
            "marginBottom": "8px",
        }),
        html.Hr(style={"borderColor": T.BORDER, "margin": "0 0 10px"}),
        stats_row,
        dcc.Graph(figure=fig, config={"displayModeBar": False}),
        html.P(
            "Each band shows the probability that today belongs to that regime. "
            "Trades fire only when one band exceeds the 0.60 entry floor.",
            style={"color": T.TEXT_MUTED, "fontSize": "11px",
                   "margin": "8px 0 0", "fontStyle": "italic"},
        ),
    ]), style={**T.STYLE_CARD, "marginBottom": "16px"})


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

    # ── Equity curve + Capital Deployment ─────────────────────────────────────
    eq        = result.equity_curve
    cash_s    = result.extra.get("cash_curve",   _pd.Series(dtype=float))
    start_cap = float(eq.iloc[0]) if not eq.empty else 100_000

    has_breakdown = not cash_s.empty and not eq.empty

    if has_breakdown:
        # % of capital deployed = (equity - cash) / equity × 100
        deploy_pct = ((eq - cash_s) / eq * 100).clip(lower=0)
        fig_eq = make_subplots(
            rows=2, cols=1,
            row_heights=[0.72, 0.28],
            shared_xaxes=True,
            vertical_spacing=0.04,
            subplot_titles=("Equity (MTM)", "% Capital Deployed"),
        )
    else:
        fig_eq = make_subplots(rows=1, cols=1)

    # ── Row 1: equity + drawdown shading ──────────────────────────────────────
    roll_max = eq.cummax()
    fig_eq.add_trace(go.Scatter(
        x=list(eq.index), y=list(roll_max),
        line=dict(width=0), showlegend=False, hoverinfo="skip", name="peak",
    ), row=1, col=1)
    fig_eq.add_trace(go.Scatter(
        x=list(eq.index), y=list(eq),
        fill="tonexty", fillcolor="rgba(239,68,68,0.12)",
        line=dict(width=0), showlegend=False, hoverinfo="skip", name="dd_fill",
    ), row=1, col=1)
    fig_eq.add_trace(go.Scatter(
        x=list(eq.index), y=list(eq),
        line=dict(color=T.ACCENT, width=2),
        name="Equity",
        hovertemplate="%{x|%Y-%m-%d}  $%{y:,.0f}<extra>Equity (MTM)</extra>",
    ), row=1, col=1)
    fig_eq.add_hline(
        y=start_cap, row=1,
        line=dict(color=T.BORDER_BRT, width=1, dash="dot"),
        annotation_text=f"Start ${start_cap:,.0f}",
        annotation_position="bottom right",
        annotation_font_color=T.TEXT_MUTED,
        annotation_font_size=10,
    )

    # ── Row 2: % capital deployed (filled area) ────────────────────────────────
    if has_breakdown:
        fig_eq.add_trace(go.Scatter(
            x=list(deploy_pct.index), y=list(deploy_pct),
            fill="tozeroy",
            fillcolor="rgba(245,158,11,0.25)",
            line=dict(color="#f59e0b", width=1.5),
            name="Deployed %",
            hovertemplate="%{x|%Y-%m-%d}  %{y:.1f}%<extra>Deployed</extra>",
        ), row=2, col=1)
        fig_eq.add_hline(y=50, row=2,
            line=dict(color=T.BORDER_BRT, width=1, dash="dot"),
            annotation_text="50%", annotation_position="bottom right",
            annotation_font_color=T.TEXT_MUTED, annotation_font_size=10,
        )

    fig_eq.update_layout(
        paper_bgcolor=T.BG_CARD, plot_bgcolor=T.BG_CARD,
        font=dict(color=T.TEXT_PRIMARY, family="Inter, sans-serif", size=12),
        height=430, margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
        template="plotly_dark",
    )
    fig_eq.update_xaxes(gridcolor=T.BORDER, showgrid=True)
    fig_eq.update_yaxes(gridcolor=T.BORDER, showgrid=True)
    fig_eq.update_yaxes(tickformat="$,.0f", row=1, col=1)
    fig_eq.update_yaxes(tickformat=".0f", ticksuffix="%", range=[0, 105], row=2, col=1)
    # Style subplot titles
    for ann in fig_eq.layout.annotations:
        ann.font.color = T.TEXT_MUTED
        ann.font.size  = 11

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
        # Column config: field → (headerName, width, cellStyle)
        _COL_CONFIG = {
            "entry_date":      ("Entry",          105, None),
            "exit_date":       ("Exit",           105, None),
            "pnl":             ("P&L",            100, {"function": "params.value >= 0 ? {'color':'#10b981','fontWeight':'600'} : {'color':'#ef4444','fontWeight':'600'}"}),
            "pnl_pct":         ("P&L %",           90, {"function": "params.value >= 0 ? {'color':'#10b981'} : {'color':'#ef4444'}"}),
            "dte_held":        ("DTE Held",         90, None),
            "hold_days":       ("Days Held",        95, None),
            "exit_reason":     ("Exit Reason",     130, None),
            "contracts":       ("Contracts",       100, None),
            "credit":          ("Credit",           90, None),
            "call_short_k":    ("Call Short",      110, None),
            "call_long_k":     ("Call Long",       110, None),
            "put_short_k":     ("Put Short",       110, None),
            "put_long_k":      ("Put Long",        110, None),
            "margin_reserved": ("Margin Rsv",      115, None),
            "ticker":          ("Ticker",          100, None),
            "status":          ("Status",          100, None),
        }
        # Columns to skip (redundant or internal)
        _SKIP = {"winner", "free_capital"}

        # Build ordered display list: known preferred first, then any extras
        _preferred_order = ["entry_date", "exit_date", "pnl", "pnl_pct", "dte_held",
                            "hold_days", "exit_reason", "contracts", "credit",
                            "call_short_k", "call_long_k", "put_short_k", "put_long_k",
                            "margin_reserved", "ticker", "status"]
        cols_lower = {c.lower(): c for c in trades_df.columns}
        display_cols = []
        for key in _preferred_order:
            orig = cols_lower.get(key)
            if orig and orig not in _SKIP:
                display_cols.append(orig)
        for orig in trades_df.columns:
            if orig not in display_cols and orig not in _SKIP:
                display_cols.append(orig)

        col_defs = []
        for orig in display_cols:
            key = orig.lower()
            header, width, style = _COL_CONFIG.get(key, (orig.replace("_", " ").title(), 100, None))
            cd = {
                "field":       orig,
                "headerName":  header,
                "width":       width,
                "resizable":   True,
                "sortable":    True,
                "filter":      True,
            }
            if style:
                cd["cellStyle"] = style
            col_defs.append(cd)

        tbl_height = min(500, 80 + len(trades_df) * 38)
        # Convert AgGrid column defs to MRT format on the fly
        mrt_cols = [
            {"accessorKey": c["field"], "header": c.get("headerName", c["field"])}
            for c in col_defs
        ]
        trades_grid = _MRT(
            data=trades_df[display_cols].astype(str).to_dict("records"),
            columns=mrt_cols,
            mrtProps={
                "enableColumnFilters": True,
                "enableGlobalFilter":  True,
                "enableSorting":       True,
                "enableDensityToggle": True,
                "enableColumnOrdering":True,
                "enablePagination":    True,
                "layoutMode":          "grid",
                "initialState": {
                    "density": "xs",
                    "pagination": {"pageIndex": 0, "pageSize": 25},
                },
                "defaultColumn": {"minSize": 80, "maxSize": 400, "size": 130},
                "mantineTableProps": {
                    "highlightOnHover": True,
                    "withTableBorder":  False,
                    "withColumnBorders":False,
                    "horizontalSpacing":"md",
                    "verticalSpacing":  "xs",
                },
                "mantineTableContainerProps": {
                    "style": {"maxHeight": f"{tbl_height}px", "width": "100%"},
                },
                "mantinePaperProps": {
                    "shadow": "0", "withBorder": False,
                    "style": {"backgroundColor": "transparent", "width": "100%"},
                },
            },
            mantineProviderProps={
                "theme": {
                    "colorScheme": "dark",
                    "primaryColor": "indigo",
                    "fontFamily": "Inter, system-ui, sans-serif",
                },
            },
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

    # ── Strategy-specific panels ─────────────────────────────────────────────
    extra_panels = []
    if slug == "hmm_regime":
        regime_df = result.extra.get("regime_log") if hasattr(result, "extra") else None
        hmm_panel = _build_hmm_regime_panel(regime_df, result.extra or {})
        if hmm_panel is not None:
            extra_panels.append(hmm_panel)

    return html.Div([
        metric_row,
        equity_chart,
        *extra_panels,
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
            # Only strip trailing zeros from true decimals, not integers like 30 → "3"
            if v == int(v):
                return str(int(v))
            return str(round(float(v), 4)).rstrip("0").rstrip(".")

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
        capital    = float(capital or 10_000)

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

        auxiliary_data = {"vix": vix_df, "rate10y": rate_df, "ticker": ticker}

        # ── Per-strategy auxiliary-data loaders ───────────────────────────────
        # Loader logic lives in app/pages/backtest_loaders.py — one pure
        # function per data type, registered in LOADERS_BY_SLUG. Each loader
        # may return a blocking Alert if required data is missing.
        from app.pages.backtest_loaders import run_loaders_for
        _aux_extra, _block = run_loaders_for(
            slug, engine, ticker, fd, td, price_data=price_data,
        )
        auxiliary_data.update(_aux_extra)
        if _block is not None:
            return _block

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

    # Step 1: row clicked → open modal immediately + store row data
    # MRT bridge: row clicks come via the hidden input written by
    # assets/mrt_row_click.js. The payload is a JSON string with `rowIndex`.
    @callback(
        Output("str-ic-modal",       "is_open",  allow_duplicate=True),
        Output("str-ic-modal-title", "children", allow_duplicate=True),
        Output("str-ic-row-store",   "data",     allow_duplicate=True),
        Output("str-ic-paper-btn",   "disabled", allow_duplicate=True),
        Input(f"{grid_id}-clicked",  "value"),
        State(grid_id,  "data"),
        prevent_initial_call=True,
    )
    def _open_modal(click_payload, all_rows):
        import json as _json
        if not click_payload or not all_rows:
            return no_update, no_update, no_update, no_update
        try:
            payload = _json.loads(click_payload)
        except Exception:
            return no_update, no_update, no_update, no_update
        row_index = int(payload.get("rowIndex", -1))
        if row_index < 0 or row_index >= len(all_rows):
            return no_update, no_update, no_update, no_update
        row = all_rows[row_index]
        if not row:
            return no_update, no_update, no_update, no_update
        row = {**row, "_slug": slug}   # tag the strategy slug for paper trade
        ticker = row.get("Ticker", "")
        chain  = row.get("_chain")
        title  = (f"{ticker} Iron Condor  ·  {chain['best_exp']} ({chain['dte_used']} DTE)  ·  "
                  f"~{chain['target_delta']:.0%}-delta  ·  Net credit ${chain['net_credit']*100:.2f}"
                  if chain else ticker)
        # Disable Paper Trade immediately; Step 2 re-enables only when chain is valid
        return True, title, row, True

    _open_modal.__name__ = f"_open_modal_{slug}"
    return _open_modal


# Step 2: store change → build and populate modal body (runs after modal is open)
@callback(
    Output("str-ic-modal-body",  "children"),
    Output("str-ic-paper-btn",   "disabled"),
    Input("str-ic-row-store", "data"),
    prevent_initial_call=True,
)
def _build_modal_body(row):
    if not row:
        return no_update, no_update
    ticker = row.get("Ticker", "")
    chain  = row.get("_chain")

    if not chain:
        err_detail = row.get("_chain_err") or "Polygon returned no data for the 30–60 DTE window"
        return dbc.Alert(
            [html.Strong(f"{ticker}: "), err_detail],
            color="warning",
        ), True

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
        _mc("Net Credit",   f"${nc100:.2f}" if _has_prices else "— (no quotes)",
            T.SUCCESS if net_credit > 0 else (T.WARNING if not _has_prices else T.DANGER)),
        _mc("Max Loss",     f"-${ml100:.2f}" if _has_prices else "—", T.DANGER),
        _mc("50% Target",   f"${pt100:.2f}" if _has_prices else "—", T.SUCCESS),
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
        return f"+${val:.2f}" if val >= 0 else f"-${abs(val):.2f}"

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
         "$/Contract": (f"+${net_cash:.2f}" if net_cash >= 0 else f"-${abs(net_cash):.2f}")
                       if _has_prices else "—"},
    ]
    leg_table = _mrt_grid_shared(
        data=leg_rows,
        aggrid_cols=[
            {"field": "Leg"},
            {"field": "Strike"},
            {"field": "Mid"},
            {"field": "Action"},
            {"field": "$/Contract"},
        ],
        height=260,
        enable_pagination=False,
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
    ]), False


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

    # Block trade if net credit is negative or below minimum threshold
    net_credit = chain.get("net_credit")
    if net_credit is not None and float(net_credit) < 0.05:
        return html.Span(
            f"⚠ Net credit ${float(net_credit):.2f} is too low — trade blocked. "
            "Credits below $0.05/share are not worth the risk.",
            style={"color": T.WARNING},
        )

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


# ── Paper Trade callback for signal-modal strategies ──────────────────────────

_CREDIT_SLUGS = {
    "ivr_credit_spread", "bull_put_spread", "put_steal",
    "broken_wing_butterfly", "rs_credit_spread",
}
_MIN_CREDIT_PER_SHARE = 0.05   # block if net credit < $0.05/share


@callback(
    Output("str-sig-paper-feedback", "children"),
    Input("str-sig-paper-btn", "n_clicks"),
    State("str-sig-row-store", "data"),
    State("str-sig-contracts", "value"),
    prevent_initial_call=True,
)
def _paper_trade_sig(n_clicks, row, contracts):
    if not n_clicks or not row:
        return no_update
    ticker  = row.get("Ticker", "")
    slug    = row.get("_slug", "")
    label   = _SLUG_TO_LABEL.get(slug, slug)
    status  = row.get("Status", "")
    n       = int(contracts or 1)

    # Block credit strategies where net credit is too low / negative
    if slug in _CREDIT_SLUGS:
        chain = row.get("_chain") or {}
        raw = (chain.get("net_credit") or row.get("net_credit") or
               row.get("~Credit") or row.get("Credit"))
        if raw is not None:
            try:
                cred_f = float(str(raw).lstrip("$+") or 0)
                if cred_f < _MIN_CREDIT_PER_SHARE:
                    return html.Span(
                        f"⚠ Net credit ${cred_f:.2f}/share is too low — trade blocked "
                        f"(min ${_MIN_CREDIT_PER_SHARE:.2f}/share).",
                        style={"color": T.WARNING, "fontSize": "12px"},
                    )
            except Exception:
                pass

    try:
        from engine.positions import insert_generic_paper_trade
        from db.client import get_engine
        engine = get_engine()
        # Build a summary of the key trade parameters
        details = {k: v for k, v in row.items()
                   if k not in ("_slug", "all_pass", "n_pass", "_chain")
                   and v not in (None, "—", "")}

        # VSF: inject chain leg data so insert_generic_paper_trade gets real strikes/premiums
        if slug == "vix_spike_fade":
            vsf = row.get("_chain") or {}
            if vsf:
                details["Short Strike"]   = vsf.get("short_put_k")   # OTM put we SELL
                details["Long Strike"]    = vsf.get("long_put_k")    # ATM put we BUY
                details["~Credit"]        = vsf.get("short_put_mid") # premium collected
                details["~Long Premium"]  = vsf.get("long_put_mid")  # premium paid
                details["Expiry"]         = vsf.get("best_exp")
                details["DTE"]            = vsf.get("dte_used")
                details["Long Delta"]     = vsf.get("long_delta")
                details["Net Debit"]      = vsf.get("net_debit")

        # IVR Credit Spread: inject chain leg data (put or call spread)
        elif slug == "ivr_credit_spread":
            ivr_c = row.get("_chain") or {}
            if ivr_c:
                details["Short Strike"]  = ivr_c.get("short_k")     # leg we SELL
                details["Long Strike"]   = ivr_c.get("long_k")      # wing we BUY
                details["~Credit"]       = ivr_c.get("short_mid")   # premium collected
                details["~Long Premium"] = ivr_c.get("long_mid")    # premium paid
                details["Expiry"]        = ivr_c.get("best_exp")
                details["DTE"]           = ivr_c.get("dte_used")

        # HMM Regime: compute strikes from the state-specific structure.
        # State 0 (bull put) and State 2 (long put spread) → 2-leg PUT inserter.
        # State 1 (iron condor) → routes through the 4-leg IC inserter directly,
        # returning early to bypass insert_generic_paper_trade.
        elif slug == "hmm_regime":
            try:
                state_val = int(row.get("State", -1))
            except Exception:
                state_val = -1
            try:
                spot = float(row.get("Price") or 0.0)
                vix  = float(row.get("VIX") or 0.0)
                preview = _hmm_trade_preview(state_val, spot, vix, ticker)
            except Exception:
                preview = None
            if state_val not in (0, 1, 2) or preview is None:
                return html.Span(
                    "⚠ HMM paper trade unavailable — current state has no entry "
                    "(VIX too high, or no dominant regime).",
                    style={"color": T.WARNING, "fontSize": "12px"},
                )
            try:
                from datetime import date, timedelta
                dte_map = {0: 30, 1: 35, 2: 45}
                dte_used = dte_map[state_val]
                expiry   = (date.today() + timedelta(days=dte_used)).isoformat()
                leg_rows = preview["legs_table"].rowData

                def _strike(r):
                    return float(str(r["Strike"]).lstrip("$"))

                def _mid(r):
                    return float(str(r["Mid"]).lstrip("$"))

                if state_val == 1:
                    # ── Iron Condor (4 legs) — route through insert_open_ic_trade ──
                    # leg_rows order from _hmm_trade_preview:
                    #   Long call (wing) BUY  | Short call SELL
                    #   Short put SELL        | Long put (wing) BUY
                    rows_by_label = {r["Leg"]: r for r in leg_rows
                                     if not str(r.get("Leg", "")).startswith("NET")}
                    chain = {
                        "best_exp":         expiry,
                        "long_call_k":      _strike(rows_by_label["Long call (wing)"]),
                        "short_call_k":     _strike(rows_by_label["Short call"]),
                        "short_put_k":      _strike(rows_by_label["Short put"]),
                        "long_put_k":       _strike(rows_by_label["Long put (wing)"]),
                        "long_call_mid":    _mid(rows_by_label["Long call (wing)"]),
                        "short_call_mid":   _mid(rows_by_label["Short call"]),
                        "short_put_mid":    _mid(rows_by_label["Short put"]),
                        "long_put_mid":     _mid(rows_by_label["Long put (wing)"]),
                    }
                    from engine.positions import insert_open_ic_trade
                    from db.client import get_engine
                    err = insert_open_ic_trade(
                        engine=get_engine(),
                        account_id=1,
                        ticker=ticker,
                        chain=chain,
                        strategy_name=label,
                        contracts=n,
                    )
                    if err:
                        return html.Span(f"Error: {err}", style={"color": T.DANGER, "fontSize": "12px"})
                    return html.Span(
                        f"✓ {ticker} {label} (Iron Condor, state 1) saved ({n} contract(s))",
                        style={"color": T.SUCCESS, "fontSize": "12px"},
                    )

                # ── State 0 / State 2 → 2-leg PUT spreads via generic inserter ──
                short_row = next(r for r in leg_rows if r["Action"] == "SELL")
                long_row  = next(r for r in leg_rows if r["Action"] == "BUY")
                short_k, long_k = _strike(short_row), _strike(long_row)
                short_mid, long_mid = _mid(short_row), _mid(long_row)
                details["Short Strike"]   = short_k
                details["Long Strike"]    = long_k
                details["~Credit"]        = short_mid - long_mid   # +ve for state 0, -ve for state 2
                details["~Long Premium"]  = long_mid
                details["Expiry"]         = expiry
                details["DTE"]            = dte_used
            except Exception as _e:
                return html.Span(
                    f"⚠ HMM paper-trade injection failed: {_e}",
                    style={"color": T.DANGER, "fontSize": "12px"},
                )

        err = insert_generic_paper_trade(
            engine=engine,
            account_id=1,
            ticker=ticker,
            strategy_name=label,
            contracts=n,
            details=details,
        )
        if err:
            return html.Span(f"Error: {err}", style={"color": T.DANGER, "fontSize": "12px"})
        return html.Span(
            f"✓ {ticker} {label} saved ({n} contract(s))",
            style={"color": T.SUCCESS, "fontSize": "12px"},
        )
    except Exception as e:
        return html.Span(f"Error: {e}", style={"color": T.DANGER, "fontSize": "12px"})


# ── Signal detail modal for VSF / IVR / VA / GEX ─────────────────────────────

def _make_signal_callback(slug: str):
    grid_id = f"str-{slug}-grid"

    @callback(
        Output("str-sig-modal",       "is_open",  allow_duplicate=True),
        Output("str-sig-modal-title", "children", allow_duplicate=True),
        Output("str-sig-row-store",   "data",     allow_duplicate=True),
        Input(f"{grid_id}-clicked", "value"),
        State(grid_id,  "data"),
        prevent_initial_call=True,
    )
    def _open_sig_modal(click_payload, all_rows):
        import json as _json
        if not click_payload or not all_rows:
            return no_update, no_update, no_update
        try:
            payload = _json.loads(click_payload)
        except Exception:
            return no_update, no_update, no_update
        row_index = int(payload.get("rowIndex", -1))
        if row_index < 0 or row_index >= len(all_rows):
            return no_update, no_update, no_update
        row = all_rows[row_index]
        if not row:
            return no_update, no_update, no_update
        row    = {**row, "_slug": slug}
        ticker = row.get("Ticker", "")
        label  = _SLUG_TO_LABEL.get(slug, slug)
        score  = row.get("Score", "")
        title  = f"{ticker}  ·  {label}  ·  Score {score}"
        return True, title, row

    _open_sig_modal.__name__ = f"_open_sig_modal_{slug}"
    return _open_sig_modal


def _sig_chart(spots, pnl, spot_price, ticker, title, max_loss, max_profit, target,
               stop_level=None):
    """Reusable P&L-at-expiry chart for signal modals.
    stop_level: explicit stop P&L line (e.g. -2×credit). Defaults to max_loss if None."""
    if stop_level is None:
        stop_level = max_loss
    be_prices = []
    for i in range(1, len(spots)):
        if pnl[i-1] * pnl[i] <= 0:
            be_prices.append(float(spots[i]))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(spots), y=pnl,
        mode="lines", name="P&L at expiry",
        line={"color": "#818cf8", "width": 2},
        fill="tozeroy",
        fillcolor="rgba(129,140,248,0.08)",
    ))
    # Colour the loss zone red
    fig.add_trace(go.Scatter(
        x=list(spots), y=[min(p, 0) for p in pnl],
        mode="lines", name="Loss zone",
        line={"width": 0},
        fill="tozeroy",
        fillcolor="rgba(239,68,68,0.12)",
        showlegend=False,
    ))
    # Reference lines
    fig.add_hline(y=0,      line_dash="solid", line_color="rgba(255,255,255,0.15)", line_width=1)
    fig.add_hline(y=target, line_dash="dash",  line_color="#10b981", line_width=1.5,
                  annotation_text=f"50% target: {target:+.0f}",
                  annotation_font_color="#10b981", annotation_font_size=11)
    fig.add_hline(y=stop_level, line_dash="dash", line_color="#ef4444", line_width=1.5,
                  annotation_text=f"2× stop: {stop_level:+.0f}",
                  annotation_font_color="#ef4444", annotation_font_size=11)
    fig.add_vline(x=spot_price, line_dash="dash", line_color="#f59e0b", line_width=1.5,
                  annotation_text=f"Spot ${spot_price:.0f}",
                  annotation_font_color="#f59e0b", annotation_font_size=11)
    for be in be_prices:
        fig.add_vline(x=be, line_dash="dot", line_color="rgba(255,255,255,0.4)", line_width=1,
                      annotation_text=f"BE ${be:.0f}",
                      annotation_font_color="rgba(255,255,255,0.6)", annotation_font_size=10)
    fig.update_layout(
        title={"text": f"{ticker} {title}", "font": {"size": 13, "color": "#e2e8f0"}, "x": 0.01},
        paper_bgcolor="#1e293b", plot_bgcolor="#1e293b",
        font={"color": "#94a3b8"},
        margin={"l": 50, "r": 20, "t": 40, "b": 40},
        height=320,
        xaxis={"title": "Underlying Price", "gridcolor": "#334155", "tickprefix": "$"},
        yaxis={"title": "P&L per Contract ($)", "gridcolor": "#334155", "tickprefix": "$"},
        showlegend=False,
    )
    return dcc.Graph(figure=fig, config={"displayModeBar": False},
                     style={"marginTop": "14px"})


def _make_legs_table(rows: list[dict]):
    """Build a compact legs summary table for strategy modals."""
    return _mrt_grid_shared(
        data=rows,
        aggrid_cols=[
            {"field": "Leg"},
            {"field": "Strike"},
            {"field": "Action"},
            {"field": "~/Contract"},
        ],
        height=240,
        enable_pagination=False,
    )


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
    chart      = html.Div()   # default: no chart; overridden by strategies that have P&L graphs
    legs_table = html.Div()   # default: no legs table

    if slug == "vix_spike_fade":
        vix     = row.get("VIX", "—")
        vix20   = row.get("VIX 20d avg", "—")
        ratio   = row.get("VIX / 20d", "—")
        atm_iv  = row.get("ATM IV", "—")
        hv20    = row.get("HV20", "—")
        ivr     = row.get("IVR", "—")
        ma200   = row.get("MA200", "—")
        spot    = float(row.get("Price") or 0)

        # Fetch real ATM put from Polygon (~30 DTE, delta ≈ -0.50)
        vsf_chain = None
        vsf_err   = None
        try:
            from app import get_polygon_api_key
            from data.polygon_client import PolygonClient
            import datetime as _dt
            api_key = get_polygon_api_key()
            if api_key and spot > 0:
                client = PolygonClient(api_key=api_key)
                today  = _dt.date.today()
                exp_lo = (today + _dt.timedelta(days=21)).isoformat()
                exp_hi = (today + _dt.timedelta(days=45)).isoformat()
                chain  = client.get_options_chain(
                    ticker,
                    expiration_date_gte=exp_lo,
                    expiration_date_lte=exp_hi,
                    strike_price_gte=spot * 0.85,
                    strike_price_lte=spot * 1.02,
                )
                if chain is not None and not chain.empty:
                    puts = chain[chain["type"] == "put"].copy()
                    puts["delta_abs"] = puts["delta"].abs()
                    # ATM put: delta closest to -0.50
                    atm_put = puts.loc[(puts["delta_abs"] - 0.50).abs().idxmin()] if not puts.empty else None
                    # OTM wing: delta closest to -0.25, strike below ATM
                    if atm_put is not None:
                        atm_k   = float(atm_put["strike"])
                        otm_row = puts[puts["strike"] < atm_k].copy()
                        otm_put = otm_row.loc[(otm_row["delta_abs"] - 0.25).abs().idxmin()] if not otm_row.empty else None
                        atm_mid = round((float(atm_put["bid"]) + float(atm_put["ask"])) / 2, 2) \
                                  if (atm_put.get("bid") == atm_put.get("bid")) else None
                        otm_mid = round((float(otm_put["bid"]) + float(otm_put["ask"])) / 2, 2) \
                                  if (otm_put is not None and otm_put.get("bid") == otm_put.get("bid")) else None
                        net_debit = round((atm_mid or 0) - (otm_mid or 0), 2)
                        vsf_chain = {
                            "long_put_k":  atm_k,
                            "long_put_mid": atm_mid,
                            "short_put_k": float(otm_put["strike"]) if otm_put is not None else None,
                            "short_put_mid": otm_mid,
                            "net_debit":   net_debit,
                            "best_exp":    str(atm_put["expiration"]),
                            "dte_used":    int(atm_put["dte"]) if atm_put.get("dte") else 30,
                            "long_delta":  round(float(atm_put["delta"]), 2) if atm_put.get("delta") == atm_put.get("delta") else None,
                        }
        except Exception as _e:
            vsf_err = str(_e)

        is_ready = float(str(ratio).rstrip("%") or 0) > 1.2
        signal = ("Buy put spread — VIX elevated, fade the spike back toward mean"
                  if is_ready else "Monitor — VIX spike not sufficient")

        chain_info = html.Div()
        if vsf_chain:
            c = vsf_chain
            _lpm = f"${c['long_put_mid']:.2f}" if c.get("long_put_mid") else "—"
            _spm = f"${c['short_put_mid']:.2f}" if c.get("short_put_mid") else "—"
            _nd  = f"${c['net_debit']:.2f}" if c.get("net_debit") is not None else "—"
            _sk  = f"${c['short_put_k']:.0f}" if c.get("short_put_k") else "—"
            chain_info = html.Div([
                html.Div("PUT SPREAD", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                              "fontWeight": "700", "letterSpacing": "0.07em",
                                              "marginBottom": "6px"}),
                _mrt_grid_shared(
                    data=[
                        {"Leg": "Long put (ATM)",  "Strike": f"${c['long_put_k']:.0f}",
                         "Mid": _lpm, "Action": "BUY",
                         "$/Contract": f"-${c['long_put_mid']*100:.2f}" if c.get("long_put_mid") else "—"},
                        {"Leg": "Short put (wing)", "Strike": _sk,
                         "Mid": _spm, "Action": "SELL",
                         "$/Contract": f"+${c['short_put_mid']*100:.2f}" if c.get("short_put_mid") else "—"},
                        {"Leg": "NET DEBIT", "Strike": "", "Mid": "", "Action": "",
                         "$/Contract": f"-${c['net_debit']*100:.2f}" if c.get("net_debit") else "—"},
                    ],
                    aggrid_cols=[
                        {"field": "Leg"},
                        {"field": "Strike"},
                        {"field": "Mid"},
                        {"field": "Action"},
                        {"field": "$/Contract"},
                    ],
                    height=200,
                    enable_pagination=False,
                ),
                html.Div(f"Expiry: {c['best_exp']}  ({c['dte_used']} DTE)  ·  "
                         f"Long delta: {c['long_delta']}",
                         style={"color": T.TEXT_MUTED, "fontSize": "11px"}),
            ], style={"marginTop": "12px"})
        elif vsf_err:
            chain_info = html.P(f"Chain error: {vsf_err}",
                                style={"color": T.WARNING, "fontSize": "12px"})
        else:
            chain_info = html.P("No Polygon data — set POLYGON_API_KEY to see real strikes.",
                                style={"color": T.TEXT_MUTED, "fontSize": "12px"})

        # Attach chain to row store so paper trade can use it
        row["_chain"] = vsf_chain
        legs_table = chain_info   # wire into final layout

        # Payoff chart — bear put spread (long ATM put, short OTM put)
        if vsf_chain and spot > 0:
            c   = vsf_chain
            lk  = c.get("long_put_k")  or spot
            sk  = c.get("short_put_k") or spot * 0.97
            nd  = c.get("net_debit")   or 0
            sw  = lk - sk
            max_prof  =  (sw - nd) * 100   # profit if spot falls below OTM put
            max_loss  = -nd * 100          # lose debit if spot stays above ATM put
            spots_vsf = np.linspace(spot * 0.80, spot * 1.10, 300)
            def _vsf_pnl(s):
                long_p  =  max(0, lk - s)
                short_p = -max(0, sk - s)
                return (-nd + long_p + short_p) * 100
            pnl_vsf = [_vsf_pnl(s) for s in spots_vsf]
            chart = _sig_chart(spots_vsf, pnl_vsf, spot, ticker,
                               "VIX Spike Fade — Bear Put Spread",
                               max_loss, max_prof, max_prof * 0.5,
                               stop_level=max_loss * 0.5)

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
        spot     = float(row.get("Price") or 0)
        is_bull  = "Bull" in str(sp_type)
        signal   = f"{sp_type} — sell premium into elevated IV (IVR {ivr})"

        # Fetch real options chain from Polygon
        ivr_chain = None
        ivr_err   = None
        try:
            from app import get_polygon_api_key
            from data.polygon_client import PolygonClient
            import datetime as _dt
            api_key = get_polygon_api_key()
            if api_key and spot > 0:
                client  = PolygonClient(api_key=api_key)
                today_d = _dt.date.today()
                exp_lo  = (today_d + _dt.timedelta(days=21)).isoformat()
                exp_hi  = (today_d + _dt.timedelta(days=45)).isoformat()
                opt_type = "put" if is_bull else "call"
                chain = client.get_options_chain(
                    ticker,
                    expiration_date_gte=exp_lo,
                    expiration_date_lte=exp_hi,
                    strike_price_gte=spot * 0.85,
                    strike_price_lte=spot * 1.15,
                )
                if chain is not None and not chain.empty:
                    legs_df = chain[chain["type"] == opt_type].copy()
                    legs_df["delta_abs"] = legs_df["delta"].abs()
                    if not legs_df.empty:
                        # Short leg: delta ≈ 0.35 (ATM-ish)
                        short_leg = legs_df.loc[(legs_df["delta_abs"] - 0.35).abs().idxmin()]
                        short_k   = float(short_leg["strike"])
                        # Long leg (wing): OTM beyond short leg, delta ≈ 0.15
                        if is_bull:
                            wing_df = legs_df[legs_df["strike"] < short_k].copy()
                        else:
                            wing_df = legs_df[legs_df["strike"] > short_k].copy()
                        long_leg = wing_df.loc[(wing_df["delta_abs"] - 0.15).abs().idxmin()] if not wing_df.empty else None

                        def _mid(r):
                            try:
                                b, a = float(r["bid"]), float(r["ask"])
                                return round((b + a) / 2, 2)
                            except Exception:
                                return None

                        short_mid = _mid(short_leg)
                        long_mid  = _mid(long_leg) if long_leg is not None else None
                        long_k    = float(long_leg["strike"]) if long_leg is not None else None
                        net_credit = round((short_mid or 0) - (long_mid or 0), 2)
                        ivr_chain = {
                            "short_k":     short_k,
                            "short_mid":   short_mid,
                            "long_k":      long_k,
                            "long_mid":    long_mid,
                            "net_credit":  net_credit,
                            "opt_type":    opt_type,
                            "best_exp":    str(short_leg["expiration"]),
                            "dte_used":    int(short_leg["dte"]) if short_leg.get("dte") else 30,
                            "short_delta": round(float(short_leg["delta"]), 2) if short_leg.get("delta") == short_leg.get("delta") else None,
                        }
        except Exception as _e:
            ivr_err = str(_e)

        # Build legs table
        chain_info = html.Div()
        if ivr_chain:
            c = ivr_chain
            stype_label = "PUT" if is_bull else "CALL"
            _sm  = f"${c['short_mid']:.2f}"  if c.get("short_mid")  else "—"
            _lm  = f"${c['long_mid']:.2f}"   if c.get("long_mid")   else "—"
            _nc  = f"${c['net_credit']:.2f}"  if c.get("net_credit") is not None else "—"
            _sk  = f"${c['short_k']:.0f}"    if c.get("short_k")   else "—"
            _lk  = f"${c['long_k']:.0f}"     if c.get("long_k")    else "—"
            spread_w = abs((c.get("long_k") or 0) - (c.get("short_k") or 0))
            max_loss = round((spread_w - (c.get("net_credit") or 0)) * 100, 2)

            # Payoff chart
            xs = [round(spot * (1 + p / 100), 2) for p in range(-20, 21)]
            nc100 = (c.get("net_credit") or 0) * 100
            sk, lk = c.get("short_k") or spot, c.get("long_k") or spot
            ys = []
            for x in xs:
                if is_bull:  # bull put spread profits when price > short put strike
                    if x >= sk:
                        pnl = nc100
                    elif x <= lk:
                        pnl = -max_loss
                    else:
                        pnl = nc100 - (sk - x) * 100
                else:  # bear call spread profits when price < short call strike
                    if x <= sk:
                        pnl = nc100
                    elif x >= lk:
                        pnl = -max_loss
                    else:
                        pnl = nc100 - (x - sk) * 100
                ys.append(round(pnl, 2))

            chart = dcc.Graph(
                figure={
                    "data": [{"type": "scatter", "x": xs, "y": ys,
                               "mode": "lines", "name": "P&L",
                               "line": {"color": "#6366f1", "width": 2},
                               "fill": "tozeroy",
                               "fillcolor": "rgba(99,102,241,0.08)"}],
                    "layout": {
                        "paper_bgcolor": "transparent", "plot_bgcolor": "transparent",
                        "font": {"color": "#e5e7eb", "size": 11},
                        "height": 200, "margin": {"l": 50, "r": 20, "t": 20, "b": 40},
                        "xaxis": {"gridcolor": "#374151", "title": "Spot Price ($)"},
                        "yaxis": {"gridcolor": "#374151", "title": "P&L ($)",
                                  "zeroline": True, "zerolinecolor": "#6b7280"},
                        "shapes": [{"type": "line", "x0": spot, "x1": spot,
                                    "y0": min(ys)*1.15, "y1": max(ys)*1.15,
                                    "line": {"color": "#9ca3af", "dash": "dot", "width": 1}}],
                    },
                },
                config={"displayModeBar": False},
                style={"marginTop": "10px"},
            )

            chain_info = html.Div([
                html.Div(f"{stype_label} SPREAD", style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                                         "fontWeight": "700", "letterSpacing": "0.07em",
                                                         "marginBottom": "6px"}),
                _mrt_grid_shared(
                    data=[
                        {"Leg": f"Short {opt_type} (ATM)",  "Strike": _sk, "Mid": _sm, "Action": "SELL",
                         "$/Contract": f"+${(c['short_mid'] or 0)*100:.2f}" if c.get("short_mid") else "—"},
                        {"Leg": f"Long {opt_type} (wing)",  "Strike": _lk, "Mid": _lm, "Action": "BUY",
                         "$/Contract": f"-${(c['long_mid'] or 0)*100:.2f}" if c.get("long_mid") else "—"},
                        {"Leg": "NET CREDIT", "Strike": "", "Mid": "", "Action": "",
                         "$/Contract": f"+${(c['net_credit'] or 0)*100:.2f}" if c.get("net_credit") else "—"},
                    ],
                    aggrid_cols=[
                        {"field": "Leg"},
                        {"field": "Strike"},
                        {"field": "Mid"},
                        {"field": "Action"},
                        {"field": "$/Contract"},
                    ],
                    height=200,
                    enable_pagination=False,
                ),
                html.Div(
                    f"Expiry: {c['best_exp']}  ({c['dte_used']} DTE)  ·  "
                    f"Short delta: {c['short_delta']}  ·  Max loss: ${max_loss:.0f}/contract",
                    style={"color": T.TEXT_MUTED, "fontSize": "11px"},
                ),
            ], style={"marginTop": "12px"})

            # Inject into details for paper trade
            row["_chain"] = {
                "short_k":    c["short_k"],    "short_mid":  c["short_mid"],
                "long_k":     c["long_k"],     "long_mid":   c["long_mid"],
                "net_credit": c["net_credit"], "best_exp":   c["best_exp"],
                "dte_used":   c["dte_used"],   "opt_type":   opt_type,
            }
        elif ivr_err:
            chain_info = html.P(f"Chain error: {ivr_err}",
                                style={"color": T.WARNING, "fontSize": "12px"})
        else:
            chain_info = html.P("No Polygon data — set POLYGON_API_KEY to see real strikes.",
                                style={"color": T.TEXT_MUTED, "fontSize": "12px"})

        legs_table = chain_info   # wire into final layout

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

    elif slug == "broken_wing_butterfly":
        atm_iv   = row.get("ATM IV", "—")
        ivr      = row.get("IVR", "—")
        vix      = row.get("VIX", "—")
        adx      = row.get("ADX", "—")
        narrow_w = row.get("Narrow Wing", "—")
        wide_w   = row.get("Wide Wing", "—")
        price    = float(str(row.get("Price", 0)) or 0)
        try:
            nw = float(str(narrow_w) or 0)
            ww = float(str(wide_w)   or 0)
        except Exception:
            nw = ww = 0
        # Risk metrics (rough — no live chain)
        credit_rough = (0.20 + price * 0.015 * 0.1) if (price > 0 and nw > 0) else 0.0
        max_profit_rough = (nw + credit_rough) * 100 if nw > 0 else None
        max_loss_rough   = max((ww - nw - credit_rough), 0) * 100 if (ww > nw) else None
        signal  = ("Net-credit BWB entry — IVR low, range-bound. Pin at body for max profit."
                   if status == "Trade-Ready" else "Conditions not fully met — monitor")
        metrics = html.Div([
            _row(
                _mc("ATM IV",     str(atm_iv)),
                _mc("IVR",        str(ivr)),
                _mc("VIX",        str(vix)),
                _mc("ADX",        str(adx)),
                _mc("Narrow Wing",str(narrow_w)),
                _mc("Wide Wing",  str(wide_w)),
                _mc("Status",     status, status_color),
            ),
            _row(
                _mc("~Net Credit", f"+${credit_rough * 100:.0f} / contract" if credit_rough > 0 else "—", T.SUCCESS),
                _mc("Max Profit",  f"+${max_profit_rough:.0f} / contract"   if max_profit_rough else "—", T.SUCCESS),
                _mc("Max Loss",    f"-${max_loss_rough:.0f} / contract"     if max_loss_rough else "—",   T.DANGER),
                _mc("Wide Wing Stop", f"within $1 of ${price * 1.10:.0f}" if price > 0 else "—",         T.WARNING),
            ),
        ])
        # Legs table + P&L chart
        chart = html.Div()
        if price > 0 and nw > 0 and ww > 0:
            body_k   = round(price * 1.005 / nw) * nw
            long1_k  = body_k - nw
            short_k  = body_k
            long2_k  = body_k + ww
            credit   = credit_rough
            legs_table = _make_legs_table([
                {"Leg": "Long call (lower wing)", "Strike": f"${long1_k:.0f}", "Action": "BUY",  "~/Contract": f"-${credit * 30:.2f}"},
                {"Leg": "Short call × 2 (body)",  "Strike": f"${short_k:.0f}", "Action": "SELL", "~/Contract": f"+${credit * 80:.2f}"},
                {"Leg": "Long call (wide wing)",  "Strike": f"${long2_k:.0f}", "Action": "BUY",  "~/Contract": f"-${credit * 30:.2f}"},
                {"Leg": "NET CREDIT",             "Strike": "",               "Action": "",     "~/Contract": f"+${credit * 100:.2f}"},
            ])
            spots    = np.linspace(price * 0.75, price * 1.30, 300)
            def _bwb_pnl(s):
                c1 = max(0, s - long1_k)     # long call lower wing  (×1)
                c2 = -2 * max(0, s - short_k) # short calls at body   (×2)
                c3 = max(0, s - long2_k)      # long call wide wing   (×1) — caps loss above
                return (c1 + c2 + c3 + credit) * 100
            pnl = [_bwb_pnl(s) for s in spots]
            max_profit = max(pnl)
            chart = _sig_chart(spots, pnl, price, ticker, "Broken Wing Butterfly",
                               -(ww - nw - credit) * 100, max_profit, 0.75 * max_profit)

    elif slug == "calendar_spread":
        atm_iv = row.get("ATM IV", "—")
        hv20   = row.get("HV20", "—")
        vrp    = row.get("VRP", "—")
        ivr    = row.get("IVR", "—")
        vix    = row.get("VIX", "—")
        adx    = row.get("ADX", "—")
        price  = float(str(row.get("Price", 0)) or 0)
        try:
            iv_f_cal = float(str(atm_iv).rstrip("%")) / 100 if "%" in str(atm_iv) else float(str(atm_iv) or 0.25)
        except Exception:
            iv_f_cal = 0.25
        debit_rough = price * iv_f_cal * (25 / 252) ** 0.5 * 0.3 if price > 0 else 0.0
        signal = ("Sell front-month, buy back-month — VRP positive, range-bound."
                  if status == "Trade-Ready" else "Conditions not fully met — monitor")
        metrics = html.Div([
            _row(
                _mc("ATM IV", str(atm_iv)),
                _mc("HV20",   str(hv20)),
                _mc("VRP",    str(vrp),  T.SUCCESS if vrp not in ("—", None) else T.TEXT_MUTED),
                _mc("IVR",    str(ivr)),
                _mc("VIX",    str(vix)),
                _mc("ADX",    str(adx)),
                _mc("Status", status, status_color),
            ),
            _row(
                _mc("~Net Debit",  f"-${debit_rough * 0.4 * 100:.0f} / contract" if debit_rough > 0 else "—", T.WARNING),
                _mc("Max Loss",    f"-${debit_rough * 0.4 * 100:.0f} / contract" if debit_rough > 0 else "—", T.DANGER),
                _mc("Max Profit",  f"+${debit_rough * 0.7 * 100:.0f} / contract" if debit_rough > 0 else "—", T.SUCCESS),
                _mc("Risk Note",   "Defined — lose debit only", T.TEXT_MUTED),
            ),
        ])
        # Calendar spread P&L is IV-dependent; show a tent-shaped approximation
        price = float(str(row.get("Price", 0)) or 0)
        chart = html.Div()
        if price > 0:
            try:
                iv_f = float(str(atm_iv).rstrip("%")) / 100 if "%" in str(atm_iv) else float(str(atm_iv) or 0.25)
            except Exception:
                iv_f = 0.25
            debit      = price * iv_f * (25 / 252) ** 0.5 * 0.3   # rough debit
            legs_table = _make_legs_table([
                {"Leg": "Sell front-month ATM",  "Strike": f"${price:.0f}", "Action": "SELL", "~/Contract": f"+${debit * 0.6 * 100:.2f}"},
                {"Leg": "Buy back-month ATM",    "Strike": f"${price:.0f}", "Action": "BUY",  "~/Contract": f"-${debit * 1.0 * 100:.2f}"},
                {"Leg": "NET DEBIT",             "Strike": "",              "Action": "",     "~/Contract": f"-${debit * 0.4 * 100:.2f}"},
            ])
            spots   = np.linspace(price * 0.85, price * 1.15, 300)
            def _cal_pnl(s):
                dist = abs(s - price) / price
                return (debit * max(0, 1 - dist / (iv_f * 0.5)) - debit * 0.3) * 100
            pnl = [_cal_pnl(s) for s in spots]
            chart = _sig_chart(spots, pnl, price, ticker, "Calendar Spread",
                               -debit * 100, debit * 0.7 * 100, debit * 0.3 * 100)

    elif slug == "earnings_straddle":
        atm_iv  = row.get("ATM IV", "—")
        ivr     = row.get("IVR", "—")
        dte_e   = row.get("Days to Earnings", "—")
        impl_mv = row.get("Impl. Move", "—")
        credit  = row.get("Straddle Credit", "—")
        price   = float(str(row.get("Price", 0)) or 0)
        try:
            cred_f = float(str(credit).lstrip("$") or 0)
        except Exception:
            cred_f = price * 0.05 if price > 0 else 0.0
        # Wing protection: buy OTM call + put at implied-move distance (~10% or impl_mv)
        try:
            impl_mv_f = float(str(impl_mv).rstrip("%")) / 100 if "%" in str(impl_mv) else float(str(impl_mv) or 0.08)
        except Exception:
            impl_mv_f = 0.08
        wing_dist    = max(impl_mv_f * 1.5, 0.10) * price if price > 0 else 0.0
        wing_cost_ps = cred_f * 0.20   # rough: OTM wing ≈ 20% of ATM value each
        net_cred_ps  = cred_f - 2 * wing_cost_ps
        max_loss_ps  = max(wing_dist / 100 - net_cred_ps, 0) * 100 if wing_dist > 0 else 0.0
        credit_display = f"${cred_f * 100:.0f} / contract" if cred_f > 0 else "—"
        net_cred_display = f"+${net_cred_ps * 100:.0f} / contract" if net_cred_ps > 0 else "—"
        max_loss_display = f"-${max_loss_ps:.0f} / contract" if max_loss_ps > 0 else "—"
        signal  = (f"Short iron condor — sell ATM straddle + buy OTM wings. Earnings in {dte_e} days, IV crush expected."
                   if status == "Trade-Ready" else "Outside earnings window or IV too low — monitor")
        metrics = html.Div([
            _row(
                _mc("ATM IV",           str(atm_iv)),
                _mc("IVR",              str(ivr),          T.SUCCESS if status == "Trade-Ready" else T.TEXT_MUTED),
                _mc("Days to Earnings", str(dte_e)),
                _mc("Impl. Move",       str(impl_mv)),
                _mc("Straddle Credit",  credit_display),
                _mc("Status",           status, status_color),
            ),
            _row(
                _mc("Net Credit (w/ wings)", net_cred_display,  T.SUCCESS),
                _mc("Max Loss",              max_loss_display,  T.DANGER),
                _mc("Wing Distance",         f"±{wing_dist:.0f}" if wing_dist > 0 else "—", T.WARNING),
                _mc("Structure",             "Short Iron Condor — defined risk", T.TEXT_MUTED),
            ),
        ])
        chart = html.Div()
        if price > 0 and cred_f > 0:
            call_wing_k = price + wing_dist
            put_wing_k  = price - wing_dist
            legs_table = _make_legs_table([
                {"Leg": "Long OTM call (wing)",  "Strike": f"${call_wing_k:.0f}", "Action": "BUY",  "~/Contract": f"-${wing_cost_ps * 100:.2f}"},
                {"Leg": "Short ATM call",        "Strike": f"${price:.0f}",       "Action": "SELL", "~/Contract": f"+${cred_f * 50:.2f}"},
                {"Leg": "Short ATM put",         "Strike": f"${price:.0f}",       "Action": "SELL", "~/Contract": f"+${cred_f * 50:.2f}"},
                {"Leg": "Long OTM put (wing)",   "Strike": f"${put_wing_k:.0f}",  "Action": "BUY",  "~/Contract": f"-${wing_cost_ps * 100:.2f}"},
                {"Leg": "NET CREDIT",            "Strike": "",                    "Action": "",     "~/Contract": f"+${net_cred_ps * 100:.2f}"},
            ])
            spots = np.linspace(price * 0.70, price * 1.30, 300)
            def _strad_pnl(s):
                short_call = -max(0, s - price)
                short_put  = -max(0, price - s)
                long_call  =  max(0, s - call_wing_k)
                long_put   =  max(0, put_wing_k - s)
                return (net_cred_ps + short_call + short_put + long_call + long_put) * 100
            pnl = [_strad_pnl(s) for s in spots]
            chart = _sig_chart(spots, pnl, price, ticker, "Earnings Short Condor (IV Crush)",
                               min(pnl), net_cred_ps * 100, net_cred_ps * 0.5 * 100,
                               stop_level=-net_cred_ps * 2 * 100)

    elif slug == "wheel_strategy":
        ma50    = row.get("MA50", "—")
        atm_iv  = row.get("ATM IV", "—")
        ivr     = row.get("IVR", "—")
        put_k   = row.get("Put Strike", "—")
        premium = row.get("~Premium", "—")
        adx     = row.get("ADX", "—")
        price   = float(str(row.get("Price", 0)) or 0)
        try:
            _prem_ps = float(str(premium).lstrip("$") or 0)
            premium_display = f"${_prem_ps * 100:.0f} / contract"
        except Exception:
            premium_display = str(premium)
        signal  = (f"Sell protected put spread at {put_k} — IVR elevated, above MA50."
                   if status == "Trade-Ready" else "Conditions not fully met — monitor")
        try:
            pk_pre    = float(str(put_k)  or 0)
            prem_pre  = float(str(premium).lstrip("$") or 0)
            # Add a long OTM put wing ~5% below short strike to cap downside
            long_k_pre  = round(pk_pre * 0.95, 1)
            wing_cost_pre = round(prem_pre * 0.25, 2)   # estimate long put ≈ 25% of credit
            net_cred_pre  = round(prem_pre - wing_cost_pre, 2)
            spread_width  = round(pk_pre - long_k_pre, 1)
            wheel_max_loss = round((spread_width - net_cred_pre) * 100, 0)
            wheel_be       = round(pk_pre - net_cred_pre, 2)
        except Exception:
            pk_pre = prem_pre = long_k_pre = wing_cost_pre = 0.0
            net_cred_pre = None; wheel_max_loss = None; wheel_be = None
        net_credit_display = f"${net_cred_pre * 100:.0f} / contract" if net_cred_pre else "—"
        be_display         = f"${wheel_be:,.2f}"     if wheel_be      else "—"
        metrics = html.Div([
            _row(
                _mc("ATM IV",    str(atm_iv)),
                _mc("IVR",       str(ivr),     T.SUCCESS if status == "Trade-Ready" else T.TEXT_MUTED),
                _mc("MA50",      str(ma50)),
                _mc("Put Strike",str(put_k)),
                _mc("~Premium",  premium_display, T.SUCCESS),
                _mc("ADX",       str(adx)),
                _mc("Status",    status, status_color),
            ),
            _row(
                _mc("Net Credit", net_credit_display, T.SUCCESS),
                _mc("Breakeven",  be_display,          T.WARNING),
                _mc("Max Loss",   f"-${wheel_max_loss:,.0f} / contract" if wheel_max_loss else "—", T.DANGER),
                _mc("Long Put",   f"${long_k_pre:.0f} wing — caps downside" if long_k_pre else "—", T.WARNING),
            ),
        ])
        chart = html.Div()
        if price > 0:
            try:
                pk      = float(str(put_k) or price * 0.90)
                prem    = float(str(premium).lstrip("$") or price * 0.02)
                long_k  = round(pk * 0.95, 1)
                wing_cost = round(prem * 0.25, 2)
                net_cred  = round(prem - wing_cost, 2)
            except Exception:
                pk = price * 0.90; prem = price * 0.02
                long_k = pk * 0.95; wing_cost = prem * 0.25; net_cred = prem - wing_cost
            legs_table = _make_legs_table([
                {"Leg": "Short put (CSP)",  "Strike": f"${pk:.0f}",     "Action": "SELL", "~/Contract": f"+${prem * 100:.2f}"},
                {"Leg": "Long put (wing)",  "Strike": f"${long_k:.0f}", "Action": "BUY",  "~/Contract": f"-${wing_cost * 100:.2f}"},
                {"Leg": "NET CREDIT",       "Strike": "",               "Action": "",     "~/Contract": f"+${net_cred * 100:.2f}"},
            ])
            spots = np.linspace(price * 0.70, price * 1.15, 300)
            def _wheel_pnl(s):
                short_put = -max(0, pk - s)
                long_put  =  max(0, long_k - s)
                return (net_cred + short_put + long_put) * 100
            pnl = [_wheel_pnl(s) for s in spots]
            true_max_loss = -(pk - long_k - net_cred) * 100
            chart = _sig_chart(spots, pnl, price, ticker, "Wheel — Protected Put Spread",
                               true_max_loss, net_cred * 100, net_cred * 0.5 * 100,
                               stop_level=-net_cred * 2 * 100)

    elif slug == "bull_put_spread":
        ma50    = row.get("MA50", "—")
        atm_iv  = row.get("ATM IV", "—")
        ivr     = row.get("IVR", "—")
        short_k = row.get("Short Strike", "—")
        long_k  = row.get("Long Strike", "—")
        width   = row.get("Width", "—")
        credit  = row.get("~Credit", "—")
        cw_r    = row.get("Credit/Width", "—")
        price   = float(str(row.get("Price", 0)) or 0)
        try:
            _cred_ps = float(str(credit).lstrip("$") or 0)
            credit_display = f"${_cred_ps * 100:.0f} / contract"
        except Exception:
            credit_display = str(credit)
        signal  = (f"Sell put spread {short_k}/{long_k} — bullish, IVR elevated, price above MA50."
                   if status == "Trade-Ready" else "Conditions not fully met — monitor")
        try:
            sk_pre   = float(str(short_k) or 0)
            lk_pre   = float(str(long_k)  or 0)
            cred_pre = float(str(credit).lstrip("$") or 0)
            w_pre    = sk_pre - lk_pre
            bps_max_loss   = (w_pre - cred_pre) * 100
            bps_net_credit = cred_pre * 100
        except Exception:
            bps_max_loss = bps_net_credit = None
        metrics = html.Div([
            _row(
                _mc("ATM IV",      str(atm_iv)),
                _mc("IVR",         str(ivr),    T.SUCCESS if status == "Trade-Ready" else T.TEXT_MUTED),
                _mc("MA50",        str(ma50)),
                _mc("Short Strike",str(short_k)),
                _mc("Long Strike", str(long_k)),
                _mc("~Credit",     credit_display, T.SUCCESS),
                _mc("Credit/Width",str(cw_r)),
                _mc("Status",      status, status_color),
            ),
            _row(
                _mc("Net Credit", f"+${bps_net_credit:.0f} / contract" if bps_net_credit else "—", T.SUCCESS),
                _mc("Max Loss",   f"-${bps_max_loss:.0f} / contract"   if bps_max_loss   else "—", T.DANGER),
                _mc("Structure",  "Bull Put Spread — defined risk",  T.TEXT_MUTED),
            ),
        ])
        chart = html.Div()
        if price > 0:
            try:
                sk   = float(str(short_k) or price * 0.92)
                lk   = float(str(long_k)  or price * 0.87)
                cred = float(str(credit).lstrip("$") or 1.0)
                w    = sk - lk
            except Exception:
                sk = price * 0.92; lk = price * 0.87; cred = 1.0; w = sk - lk
            legs_table = _make_legs_table([
                {"Leg": "Short put (income)",    "Strike": f"${sk:.0f}", "Action": "SELL", "~/Contract": f"+${cred * 100:.2f}"},
                {"Leg": "Long put (protection)", "Strike": f"${lk:.0f}", "Action": "BUY",  "~/Contract": f"-${(w - cred) * 100:.2f}"},
                {"Leg": "NET CREDIT",            "Strike": "",           "Action": "",     "~/Contract": f"+${cred * 100:.2f}"},
            ])
            spots = np.linspace(price * 0.75, price * 1.15, 300)
            def _bps_pnl(s):
                short_put = -max(0, sk - s)
                long_put  =  max(0, lk - s)
                return (cred + short_put + long_put) * 100
            pnl = [_bps_pnl(s) for s in spots]
            chart = _sig_chart(spots, pnl, price, ticker, "Bull Put Spread",
                               -(w - cred) * 100, cred * 100, cred * 0.5 * 100,
                               stop_level=-cred * 2 * 100)

    elif slug == "put_steal":
        price    = float(str(row.get("Price", 0)) or 0)
        nii      = row.get("NII", "—")
        strike_x = row.get("Strike X", "—")
        atm_iv   = row.get("ATM IV", "—")
        ivr      = row.get("IVR", "—")
        vix_val  = row.get("VIX", "—")
        # Prefer real Polygon chain data
        chain    = row.get("_chain") or {}
        iv_src   = row.get("IV Src", "~BS est.")
        short_k  = chain.get("short_put_k")  or row.get("Short Put", "—")
        long_k   = chain.get("long_put_k")   or row.get("Long Put",  "—")
        exp_date = chain.get("best_exp",      row.get("Expiry", ""))
        dte_used = chain.get("dte_used",      21)
        short_mid = chain.get("short_put_mid", None)
        long_mid  = chain.get("long_put_mid",  None)
        net_cred  = chain.get("net_credit",    None)
        ml_chain  = chain.get("max_loss",      None)  # already positive dollars/share
        chain_err = row.get("_chain_err", "")
        try:
            nii_f  = float(str(nii))
            nii_color = T.SUCCESS if nii_f > 0.05 else T.WARNING if nii_f > 0 else T.DANGER
        except Exception:
            nii_f = 0.0; nii_color = T.TEXT_MUTED
        # Numeric strikes/credit — prefer chain floats, else parse display strings
        try:
            sk = float(short_k) if isinstance(short_k, (int, float)) else float(str(short_k).lstrip("$") or 0)
            lk = float(long_k)  if isinstance(long_k,  (int, float)) else float(str(long_k).lstrip("$")  or 0)
        except Exception:
            sk = lk = 0.0
        if net_cred is not None:
            cred_f = float(net_cred)
        else:
            try:
                cred_f = float(str(row.get("~Credit", "0")).lstrip("$") or 0)
            except Exception:
                cred_f = 0.0
        wing     = sk - lk
        max_prof = cred_f * 100
        max_loss_v = ml_chain * 100 if ml_chain is not None else (wing - cred_f) * 100 if wing > 0 else None
        src_badge = html.Span(
            f" [{iv_src}]",
            style={"color": T.SUCCESS if iv_src == "Polygon" else T.WARNING, "fontSize": "11px"},
        )
        exp_label = f"{exp_date}  ({dte_used}d)" if exp_date else "—"
        signal = (f"Sell bull put ${sk:.0f}/${lk:.0f} exp {exp_date} — NII={nii} (early exercise edge open)"
                  if status == "Trade-Ready" else "NII edge not wide enough — monitor")
        if chain_err:
            signal += f"  ⚠ chain: {chain_err}"
        metrics = html.Div([
            _row(
                _mc("NII",       str(nii),    nii_color),
                _mc("Strike X",  str(strike_x)),
                _mc("Expiry",    exp_label),
                _mc("ATM IV",    str(atm_iv)),
                _mc("IVR",       str(ivr)),
                _mc("VIX",       str(vix_val)),
                _mc("Status",    status, status_color),
            ),
            _row(
                _mc("Net Credit", f"+${max_prof:.0f} / contract" if max_prof else "—", T.SUCCESS),
                _mc("Max Loss",   f"-${max_loss_v:.0f} / contract" if max_loss_v else "—", T.DANGER),
                _mc("Data Src",   iv_src, T.SUCCESS if iv_src == "Polygon" else T.WARNING),
                _mc("Structure",  "Bull Put Spread — defined risk", T.TEXT_MUTED),
            ),
        ])
        chart = html.Div()
        if price > 0 and sk > 0 and lk > 0 and cred_f > 0:
            def _fmt_leg(v):
                if v is None: return "—"
                v100 = v * 100
                if v100 < 0.01:
                    return "~$0  (far OTM)"
                return f"${v100:.2f}"
            sp_mid = short_mid if short_mid is not None else cred_f + (long_mid or 0)
            lp_mid = long_mid  if long_mid  is not None else max(0, sp_mid - cred_f)
            legs_table = _make_legs_table([
                {"Leg": "Short put (income)",    "Strike": f"${sk:.2f}", "Action": "SELL", "~/Contract": f"+{_fmt_leg(sp_mid)}"},
                {"Leg": "Long put (protection)", "Strike": f"${lk:.2f}", "Action": "BUY",  "~/Contract": f"-{_fmt_leg(lp_mid)}"},
                {"Leg": "NET CREDIT",            "Strike": "",           "Action": "",     "~/Contract": f"+${cred_f * 100:.2f}"},
            ])
            spots = np.linspace(price * 0.75, price * 1.15, 300)
            def _ps_pnl(s):
                return (cred_f - max(0, sk - s) + max(0, lk - s)) * 100
            pnl = [_ps_pnl(s) for s in spots]
            ml_for_chart = max_loss_v if max_loss_v else (wing - cred_f) * 100
            chart = _sig_chart(spots, pnl, price, ticker, "Put Steal — Bull Put Spread",
                               -ml_for_chart, max_prof, max_prof * 0.5,
                               stop_level=-cred_f * 2 * 100)

    elif slug == "hmm_regime":
        state    = row.get("State", "—")
        p_state  = row.get("P(state)", "—")
        regime   = row.get("Regime", "—")
        trade    = row.get("Trade", "—")
        sig_val  = row.get("Signal", "—")
        mode     = row.get("Mode", "—")
        vix_val  = row.get("VIX", "—")
        ivr      = row.get("IVR", "—")
        ret5d    = row.get("5d Ret", "—")
        ret20d   = row.get("20d Ret", "—")
        rv20     = row.get("RV20", "—")
        spot_val = row.get("Price", 0)

        state_color = (T.SUCCESS if str(state) == "0" else
                       T.WARNING if str(state) == "1" else
                       T.DANGER  if str(state) == "2" else T.TEXT_MUTED)
        sig_color = (T.SUCCESS if str(sig_val).upper() == "SELL" else
                     T.ACCENT  if str(sig_val).upper() == "BUY"  else T.TEXT_MUTED)
        try:
            p_float = float(p_state)
        except Exception:
            p_float = 0.0
        conv_color = (T.SUCCESS if p_float >= 0.60 else
                      T.WARNING if p_float >= 0.50 else T.DANGER)

        # ── Regime status row (state classification context) ──────────────
        regime_status = html.Div([
            _row(
                _mc("State",     str(state),    state_color),
                _mc("Regime",    str(regime)),
                _mc("P(state)",  str(p_state),  conv_color),
                _mc("Signal",    str(sig_val),  sig_color),
                _mc("Mode",      str(mode),     T.WARNING if str(mode) == "heuristic" else T.SUCCESS),
                _mc("VIX",       str(vix_val)),
                _mc("IVR",       str(ivr)),
            ),
        ], style={"marginBottom": "14px"})

        # ── Try to build state-specific trade preview (payoff diagram) ────
        try:
            spot_f = float(spot_val) if spot_val not in ("—", None, "") else 0.0
            vix_f  = float(vix_val) if vix_val not in ("—", None, "") else 0.0
            state_i = int(state) if str(state).isdigit() else -1
            preview = _hmm_trade_preview(state_i, spot_f, vix_f, ticker)
        except Exception:
            preview = None

        if preview is not None:
            # Trade preview metrics + leg table + payoff diagram
            preview_metrics = preview["metrics"]
            legs_table = preview["legs_table"]
            chart      = preview["chart"]

            # Disclaimer banner about IV proxy mode
            disclaimer = html.Div([
                html.Span("ℹ️ ", style={"fontSize": "13px"}),
                html.Span(
                    "Strikes computed via BS delta inversion at IV proxy = VIX / 100. "
                    "Real fills will differ — verify against your broker chain before paper-trading."
                    if str(mode) == "heuristic" else
                    "Model mode active. Strikes computed via BS at IV proxy.",
                    style={"color": T.TEXT_MUTED, "fontSize": "11px", "fontStyle": "italic"},
                ),
            ], style={"marginBottom": "12px", "padding": "8px 12px",
                       "backgroundColor": "rgba(99,102,241,0.08)",
                       "border": f"1px solid {T.BORDER}",
                       "borderLeft": f"3px solid {T.ACCENT}",
                       "borderRadius": "4px"})

            # Combine regime status + disclaimer + trade metrics into the metrics slot
            metrics = html.Div([regime_status, disclaimer, preview_metrics])
        else:
            # Fall back to status-only view if spot/vix are degenerate
            metrics = html.Div([
                regime_status,
                html.P(f"Unable to render trade preview: spot={spot_val}, vix={vix_val}",
                       style={"color": T.WARNING, "fontSize": "12px"}),
            ])

        signal = f"{sig_val} — {trade}"

    else:  # gex_positioning
        regime  = row.get("Regime", "—")
        sig     = row.get("Signal", "—")
        weight  = row.get("SPY Weight", "—")
        atr     = row.get("ATR%", "—")
        ret5d   = row.get("5d Return", "—")
        label_r = row.get("Regime Label", "—")
        vix_val = row.get("VIX", "—")
        price   = float(str(row.get("Price", 0)) or 0)
        sig_color = (T.SUCCESS if str(sig).upper() == "LONG" else
                     T.DANGER  if str(sig).upper() == "SHORT" else T.TEXT_MUTED)
        signal  = str(label_r)
        # Parse current weight for highlight
        try:
            cur_weight_pct = float(str(weight).rstrip("%") or 0)
        except Exception:
            cur_weight_pct = 0.0
        # Position Value — SPY allocation on $100k example portfolio
        pos_val_display = f"${cur_weight_pct * 1000:.0f} / $100k portfolio" if cur_weight_pct > 0 else "—"
        cash_display    = f"${(100 - cur_weight_pct) * 1000:.0f} / $100k in cash" if cur_weight_pct > 0 else "—"
        metrics = html.Div([
            _row(
                _mc("Signal",     str(sig),    sig_color),
                _mc("Regime",     str(regime)),
                _mc("SPY Weight", str(weight), T.SUCCESS if cur_weight_pct >= 60 else
                                               T.WARNING if cur_weight_pct >= 35 else T.DANGER),
                _mc("VIX",        str(vix_val),
                    T.DANGER if float(str(vix_val) or 0) > 25 else
                    T.WARNING if float(str(vix_val) or 0) > 18 else T.SUCCESS),
                _mc("ATR%",       str(atr)),
                _mc("5d Return",  str(ret5d)),
                _mc("Status",     status, status_color),
            ),
            _row(
                _mc("Position Value", pos_val_display, T.SUCCESS if cur_weight_pct >= 60 else T.WARNING),
                _mc("Cash Reserve",   cash_display,    T.TEXT_MUTED),
                _mc("Risk Note",      "Equity + cash allocation — no options, no leverage", T.TEXT_MUTED),
            ),
        ])
        # Regime allocation ladder chart
        _regimes   = ["Deep Negative\n(VIX>30)", "Negative\n(VIX 22-30)",
                      "Neutral\n(VIX 18-22)", "Mild Positive\n(VIX 15-18)", "High Positive\n(VIX<15)"]
        _allocs    = [15, 35, 60, 80, 90]
        _colors    = ["#ef4444", "#f97316", "#f59e0b", "#84cc16", "#10b981"]
        _cur_regime_map = {
            "DeepNegative": 0, "Negative": 1, "Neutral": 2,
            "MildPositive": 3, "HighPositive": 4,
        }
        cur_idx = _cur_regime_map.get(str(regime), -1)
        bar_colors = [
            "#818cf8" if i == cur_idx else c
            for i, c in enumerate(_colors)
        ]
        gex_fig = go.Figure(go.Bar(
            x=_regimes,
            y=_allocs,
            marker_color=bar_colors,
            text=[f"{a}%" for a in _allocs],
            textposition="outside",
            textfont={"color": "#e2e8f0", "size": 12},
        ))
        if cur_idx >= 0:
            gex_fig.add_shape(
                type="rect",
                x0=cur_idx - 0.4, x1=cur_idx + 0.4,
                y0=0, y1=_allocs[cur_idx],
                fillcolor="rgba(129,140,248,0.15)",
                line={"color": "#818cf8", "width": 2},
            )
        gex_fig.add_hline(y=cur_weight_pct, line_dash="dash",
                          line_color="#f59e0b", line_width=1.5,
                          annotation_text=f"Current: {weight}",
                          annotation_font_color="#f59e0b", annotation_font_size=11)
        gex_fig.update_layout(
            title={"text": f"{ticker}  GEX Regime → SPY Allocation",
                   "font": {"size": 13, "color": "#e2e8f0"}, "x": 0.01},
            paper_bgcolor="#1e293b", plot_bgcolor="#1e293b",
            font={"color": "#94a3b8"},
            margin={"l": 40, "r": 20, "t": 40, "b": 60},
            height=300,
            yaxis={"title": "SPY Allocation %", "range": [0, 105],
                   "gridcolor": "rgba(255,255,255,0.06)", "ticksuffix": "%"},
            xaxis={"gridcolor": "rgba(255,255,255,0.06)"},
            showlegend=False,
        )
        chart = dcc.Graph(figure=gex_fig, config={"displayModeBar": False},
                          style={"marginTop": "12px"})

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
        legs_table,
        chart,
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


for _slug in (
    "vix_spike_fade", "ivr_credit_spread", "vol_arbitrage", "gex_positioning",
    "broken_wing_butterfly", "calendar_spread", "earnings_straddle",
    "wheel_strategy", "bull_put_spread", "put_steal", "hmm_regime",
):
    _make_signal_callback(_slug)


# ── HMM Live Signal compute callback ──────────────────────────────────────────

@callback(
    Output("str-hmm_regime-live-signal-output", "children"),
    Input("str-hmm_regime-live-compute-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _compute_hmm_live_signal(n_clicks):
    """Fetch the latest SPY + VIX bars, score the HMM heuristic, and render
    today's posterior + recommended trade. If a trained model pickle exists,
    use it for a full posterior; otherwise fall back to the VIX-bucket heuristic
    (same path as the strategy's `_heuristic_signal`)."""
    if not n_clicks:
        return no_update

    try:
        from app import get_polygon_api_key
        from engine.screener import _fetch_ohlcv, _score_hmm_regime
        from engine.iv_metrics import get_iv_metrics_batch

        api_key = get_polygon_api_key()
        if not api_key:
            return dbc.Alert(
                "No Polygon API key configured — set POLYGON_API_KEY in your env.",
                color="danger", style={"fontSize": "12px"},
            )

        # Fetch SPY OHLCV (60 bars is enough for rv20 + recent context)
        spy_df = _fetch_ohlcv("SPY", api_key, bars=60)
        if spy_df.empty:
            return dbc.Alert("Failed to fetch SPY data from Polygon.",
                              color="danger", style={"fontSize": "12px"})

        # Fetch VIX (DB-first, Polygon-fallback)
        vix_series = _get_vix_series(api_key)
        if vix_series is None or vix_series.empty:
            return dbc.Alert("No VIX data available (DB and Polygon both failed).",
                              color="danger", style={"fontSize": "12px"})

        # IV metrics (atm_iv, ivr)
        try:
            iv_metrics = get_iv_metrics_batch(["SPY"], spy_df.iloc[-1].name).get("SPY", {})
        except Exception:
            iv_metrics = {}

        # Score via heuristic — same code path the screener uses
        row = _score_hmm_regime("SPY", spy_df, vix_series, iv_metrics or {})
        if row is None:
            return dbc.Alert("Heuristic scoring returned no data — check data freshness.",
                              color="warning", style={"fontSize": "12px"})

        # Headline cards
        state    = row.get("State", "—")
        regime   = row.get("Regime", "—")
        p_state  = row.get("P(state)", 0.0)
        trade    = row.get("Trade", "—")
        signal   = row.get("Signal", "—")
        vix_now  = row.get("VIX", 0.0)
        ivr_now  = row.get("IVR") or 0.0
        spot     = row.get("Price", 0.0)

        state_color = (T.SUCCESS if str(state) == "0" else
                       T.WARNING if str(state) == "1" else
                       T.DANGER  if str(state) == "2" else T.TEXT_MUTED)
        conf_color = (T.SUCCESS if p_state >= 0.60 else
                      T.WARNING if p_state >= 0.50 else T.DANGER)

        def _chip(label, val, color=T.TEXT_PRIMARY):
            return html.Div([
                html.Div(label, style={"color": T.TEXT_MUTED, "fontSize": "10px",
                                        "fontWeight": "600", "textTransform": "uppercase",
                                        "marginBottom": "4px"}),
                html.Div(str(val), style={"color": color, "fontSize": "1.05rem",
                                            "fontWeight": "700"}),
            ], style={**T.STYLE_CARD, "flex": "1", "minWidth": "100px", "padding": "10px 12px"})

        # Entry-gate evaluation
        vix_ok  = vix_now <= 40.0
        conf_ok = p_state >= 0.60
        gates = [
            ("p_state >= 0.60",  conf_ok, f"{p_state:.2f}"),
            ("VIX <= 40",        vix_ok, f"{vix_now:.2f}"),
        ]
        gate_rows = []
        for name, ok, val in gates:
            ind = "✓" if ok else "✗"
            color = T.SUCCESS if ok else T.DANGER
            gate_rows.append(html.Div([
                html.Span(ind, style={"color": color, "fontWeight": "700",
                                       "marginRight": "8px",
                                       "fontFamily": "JetBrains Mono, monospace"}),
                html.Span(name, style={"color": T.TEXT_PRIMARY, "fontSize": "12px"}),
                html.Span(f"  →  {val}",
                          style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                  "fontFamily": "JetBrains Mono, monospace"}),
            ], style={"marginBottom": "4px"}))

        all_pass = vix_ok and conf_ok
        verdict_color = T.SUCCESS if all_pass else T.WARNING
        verdict_text  = ("✅ ENTRY READY — would open " + str(trade)) if all_pass \
            else "⏸ HOLD — at least one gate failed"

        mode_text = row.get("Mode", "heuristic")
        status = row.get("Status", "")

        return html.Div([
            # Headline cards
            html.Div([
                _chip("State",     str(state),                    state_color),
                _chip("Regime",    regime),
                _chip("P(state)",  f"{p_state:.2f}",              conf_color),
                _chip("Trade",     trade,                         T.ACCENT),
                _chip("Signal",    signal,                        T.SUCCESS if signal == "SELL"
                                                                  else T.ACCENT),
                _chip("Mode",      mode_text,                     T.WARNING if mode_text == "heuristic"
                                                                  else T.SUCCESS),
            ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "12px"}),
            html.Div([
                _chip("Spot",   f"${spot:.2f}"),
                _chip("VIX",    f"{vix_now:.2f}"),
                _chip("IVR",    f"{(ivr_now or 0)*100:.1f}%" if ivr_now < 1 else f"{ivr_now:.1f}"),
            ], style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginBottom": "12px"}),

            # Entry gate evaluation
            html.Div([
                html.Div("Entry gate check", style={
                    "color": T.TEXT_MUTED, "fontSize": "11px", "fontWeight": "700",
                    "textTransform": "uppercase", "letterSpacing": "0.06em",
                    "marginBottom": "8px"}),
                *gate_rows,
            ], style={**T.STYLE_CARD, "padding": "10px 14px", "marginBottom": "12px"}),

            # Verdict
            html.Div([
                html.Span(verdict_text, style={
                    "color": verdict_color, "fontSize": "13px", "fontWeight": "700"}),
            ], style={"marginBottom": "8px"}),

            html.P(status, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                    "fontStyle": "italic", "margin": "0"}),
        ])

    except Exception as e:
        logger.exception("hmm_regime compute live signal failed")
        return dbc.Alert(
            f"Compute failed: {e}",
            color="danger", style={"fontSize": "12px"},
        )
