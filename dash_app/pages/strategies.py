"""
dash_app/pages/strategies.py — Full Strategies page.

Phase 1: Shell — strategy selector, outer per-strategy tabs, inner sub-tabs.
Phase 2: Screener tab wired for all 6 strategies via engine/screener.py +
         engine/iv_metrics.py + db/client.py.
Phase 2 (Guide): Markdown articles from dashboard/tabs/guide_articles/{slug}.md.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from scipy.stats import norm as _scipy_norm

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update

from dash_app import theme as T, get_polygon_api_key

_DD = {**T.STYLE_DROPDOWN}  # shorthand for dropdown style

logger = logging.getLogger(__name__)

# ── Strategy registry ─────────────────────────────────────────────────────────

_STRATEGIES = [
    {"label": "Iron Condor (Rules)", "value": "iron_condor_rules"},
    {"label": "Iron Condor (AI)",    "value": "iron_condor_ai"},
    {"label": "VIX Spike Fade",      "value": "vix_spike_fade"},
    {"label": "IVR Credit Spread",   "value": "ivr_credit_spread"},
    {"label": "Vol Arbitrage",       "value": "vol_arbitrage"},
    {"label": "GEX Positioning",     "value": "gex_positioning"},
]

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

_GUIDE_DIR = Path(__file__).parent.parent.parent / "dashboard" / "tabs" / "guide_articles"


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
    _col("Ticker",  width=110, pinned="left"),
    _col("Price",   flex=1, min_width=75,  numeric=True),
    _col("ATM IV",  flex=1, min_width=75,  numeric=True),
    _col("IVR",     flex=1, min_width=65,  numeric=True),
    _col("HV20",    flex=1, min_width=70,  numeric=True),
    _col("VRP",     flex=1, min_width=65,  numeric=True),
    _col("IV/HV",   flex=1, min_width=70,  numeric=True),
    _col("VIX",     flex=1, min_width=60,  numeric=True),
    _col("ADX",     flex=1, min_width=60,  numeric=True),
    _col("ATR%",    flex=1, min_width=65,  numeric=True),
    _col("Score",   flex=1, min_width=65,  numeric=True, sort="desc"),
    _col("Status",  width=130),
    {"field": "Chart", "flex": 1, "minWidth": 90, "sortable": False, "filter": False,
     "cellStyle": {"textAlign": "center", "cursor": "pointer"},
     "valueGetter": {"function": "'📊 View'"},
     "cellClass": "ic-chart-btn"},
    {"field": "_chain",      "hide": True},
    {"field": "_atm_iv_raw", "hide": True},
]

_VSF_COLS = [
    _col("Ticker",      width=90,  pinned="left"),
    _col("Price",       width=90,  numeric=True),
    _col("VIX",         width=70,  numeric=True),
    _col("VIX 20d avg", width=100, numeric=True),
    _col("VIX / 20d",   width=90,  numeric=True),
    _col("ATM IV",      width=85,  numeric=True),
    _col("HV20",        width=80,  numeric=True),
    _col("IVR",         width=75,  numeric=True),
    _col("ATR%",        width=75,  numeric=True),
    _col("MA200",       width=80,  numeric=True),
    _col("Score",       width=75,  numeric=True, sort="desc"),
    _col("Status",      flex=1,    min_width=100),
]

_IVR_COLS = [
    _col("Ticker",      width=90,  pinned="left"),
    _col("Price",       width=90,  numeric=True),
    _col("ATM IV",      width=85,  numeric=True),
    _col("IVR",         width=75,  numeric=True),
    _col("VRP",         width=75,  numeric=True),
    _col("HV20",        width=80,  numeric=True),
    _col("IV/HV",       width=75,  numeric=True),
    _col("VIX",         width=70,  numeric=True),
    _col("ADX",         width=70,  numeric=True),
    _col("ATR%",        width=75,  numeric=True),
    _col("Trend",       width=85),
    _col("Spread Type", flex=1,    min_width=120),
    _col("Score",       width=75,  numeric=True, sort="desc"),
    _col("Status",      width=80),
]

_VA_COLS = [
    _col("Ticker",  width=90,  pinned="left"),
    _col("Price",   width=90,  numeric=True),
    _col("ATM IV",  width=85,  numeric=True),
    _col("HV20",    width=80,  numeric=True),
    _col("IV/HV",   width=80,  numeric=True),
    _col("VRP",     width=75,  numeric=True),
    _col("IVR",     width=75,  numeric=True),
    _col("VIX",     width=70,  numeric=True),
    _col("ATR%",    width=75,  numeric=True),
    _col("Score",   width=75,  numeric=True, sort="desc"),
    _col("Status",  flex=1,    min_width=100),
]

_GEX_COLS = [
    _col("Ticker",       width=90,  pinned="left"),
    _col("Price",        width=90,  numeric=True),
    _col("VIX",          width=70,  numeric=True),
    _col("Regime",       width=110),
    _col("SPY Weight",   width=100, numeric=True),
    _col("Signal",       width=75),
    _col("ATR%",         width=75,  numeric=True),
    _col("5d Return",    width=90,  numeric=True),
    _col("Regime Label", flex=1,    min_width=200),
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
                    columnSize="sizeToFit",
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
                style={"color": T.TEXT_PRIMARY, "fontSize": "14px", "lineHeight": "1.7"},
            ),
        ], style={"maxHeight": "600px", "overflowY": "auto", "padding": "4px 0"}),
    ], style={
        "backgroundColor": T.BG_CARD,
        "border": f"1px solid {T.BORDER}",
        "borderRadius": "10px",
        "padding": "24px",
    })


def _backtest_stub(slug: str) -> html.Div:
    return dbc.Card(
        dbc.CardBody(html.P(
            "Backtest tab — coming in Phase 3.",
            style={"color": T.TEXT_MUTED, "fontSize": "14px"},
        )),
        style=T.STYLE_CARD,
    )


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


# ── Inner tabs per strategy ───────────────────────────────────────────────────

def _inner_tabs(slug: str) -> dbc.Tabs:
    tab_style = {"fontSize": "13px", "padding": "6px 14px"}
    return dbc.Tabs(
        [
            dbc.Tab(
                _screener_layout(slug),
                label="Screener",
                tab_id=f"str-{slug}-inner-screener",
                tab_style=tab_style,
            ),
            dbc.Tab(
                _backtest_stub(slug),
                label="Backtest",
                tab_id=f"str-{slug}-inner-backtest",
                tab_style=tab_style,
            ),
            dbc.Tab(
                _performance_stub(slug),
                label="Performance",
                tab_id=f"str-{slug}-inner-performance",
                tab_style=tab_style,
            ),
            dbc.Tab(
                _guide_layout(slug),
                label="Guide",
                tab_id=f"str-{slug}-inner-guide",
                tab_style=tab_style,
            ),
            dbc.Tab(
                _simulator_stub(slug),
                label="Simulator",
                tab_id=f"str-{slug}-inner-simulator",
                tab_style=tab_style,
                disabled=True,
            ),
        ],
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

            # ── Strategy selector ─────────────────────────────────────────────
            dbc.Card(dbc.CardBody([
                html.Label("Select Strategies", style={
                    "color": T.TEXT_SEC, "fontSize": "12px",
                    "fontWeight": "600", "marginBottom": "8px",
                    "display": "block",
                }),
                dbc.Checklist(
                    id="str-strategy-select",
                    options=_STRATEGIES,
                    value=["iron_condor_rules"],
                    inline=True,
                    inputStyle={"marginRight": "4px", "accentColor": T.ACCENT},
                    labelStyle={
                        "color": T.TEXT_PRIMARY, "fontSize": "13px",
                        "marginRight": "20px", "cursor": "pointer",
                    },
                ),
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


# ── Callback: update outer tabs when strategy selection changes ───────────────

@callback(
    Output("str-outer-tabs-container", "children"),
    Output("str-strategy-tabs-store",  "data"),
    Input("str-strategy-select",       "value"),
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

    wing_w             = round(spot * wing_pct, 0)
    long_call_mid, long_call_k = _get_chain_mid(calls, short_call_k + wing_w)
    long_put_mid,  long_put_k  = _get_chain_mid(puts,  short_put_k  - wing_w)

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
        "ATR%":        f"{r.get('ATR%', 0):.2f}%",
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
        "ATR%":        f"{r.get('ATR%', 0):.2f}%",
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
        "ATR%":        f"{r.get('ATR%', 0):.2f}%",
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
        "ATR%":     f"{r.get('ATR%', 0):.2f}%",
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
                  f"~{chain['target_delta']:.0%}-delta  ·  Net credit ${chain['net_credit']:.2f}/shr"
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

    metrics = html.Div([
        _mc("Net Credit/shr", f"${net_credit:.2f}",
            T.SUCCESS if net_credit > 0 else T.DANGER),
        _mc("Max Loss/shr",   f"${max_loss:.2f}",  T.DANGER),
        _mc("50% Target",     f"${profit_target:.2f}", T.SUCCESS),
        _mc("Upper BE",       f"${be_upper:.2f}"),
        _mc("Lower BE",       f"${be_lower:.2f}"),
        _mc("Expiry",         f"{chain['best_exp']} ({chain['dte_used']} DTE)"),
        _mc("Delta target",   f"~{chain['target_delta']:.0%}"),
    ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap", "marginBottom": "16px"})

    def _cash(mid, action):
        val = mid * 100 * (1 if action == "SELL" else -1)
        return f"+${val:.0f}" if val >= 0 else f"-${abs(val):.0f}"

    net_cash = net_credit * 100
    leg_rows = [
        {"Leg": "Long call (wing)", "Strike": f"${chain['long_call_k']:.0f}",
         "Mid": f"${chain['long_call_mid']:.2f}", "Action": "BUY",
         "$/Contract": _cash(chain['long_call_mid'], "BUY")},
        {"Leg": "Short call",       "Strike": f"${chain['short_call_k']:.0f}",
         "Mid": f"${chain['short_call_mid']:.2f}", "Action": "SELL",
         "$/Contract": _cash(chain['short_call_mid'], "SELL")},
        {"Leg": "Short put",        "Strike": f"${chain['short_put_k']:.0f}",
         "Mid": f"${chain['short_put_mid']:.2f}", "Action": "SELL",
         "$/Contract": _cash(chain['short_put_mid'], "SELL")},
        {"Leg": "Long put (wing)",  "Strike": f"${chain['long_put_k']:.0f}",
         "Mid": f"${chain['long_put_mid']:.2f}", "Action": "BUY",
         "$/Contract": _cash(chain['long_put_mid'], "BUY")},
        {"Leg": "NET CREDIT", "Strike": "", "Mid": "", "Action": "",
         "$/Contract": f"+${net_cash:.0f}" if net_cash >= 0 else f"-${abs(net_cash):.0f}"},
    ]
    leg_table = dag.AgGrid(
        columnDefs=[
            {"field": "Leg",        "flex": 1, "minWidth": 160,
             "cellStyle": {"function": "params.data.Leg === 'NET CREDIT' ? {'fontWeight':'700','borderTop':'1px solid #374151'} : {}"}},
            {"field": "Strike",     "width": 85,
             "cellStyle": {"function": "params.data.Leg === 'NET CREDIT' ? {'borderTop':'1px solid #374151'} : {}"}},
            {"field": "Mid",        "width": 80,
             "cellStyle": {"function": "params.data.Leg === 'NET CREDIT' ? {'borderTop':'1px solid #374151'} : {}"}},
            {"field": "Action",     "width": 80,
             "cellStyle": {"function": "params.data.Leg === 'NET CREDIT' ? {'borderTop':'1px solid #374151'} : {}"}},
            {"field": "$/Contract", "width": 110,
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
