"""
app/pages/strategies/layout.py — page layout + per-strategy tab builders (pure view, no @callback).

Every per-strategy decision (columns, filter params, locked universe, extra
tabs, test suites) is read from the strategy's UI hook
(`strategy_api.registry.get_ui`). This module names no strategy.
"""
from __future__ import annotations

import logging
from datetime import date

from app.grid_helpers import (
    clickable_mrt_grid as _mrt_clickable,
)
import dash_bootstrap_components as dbc
from dash import html, dcc

from app import theme as T, get_polygon_api_key
from app.ui import components as C
from app.ui.strategy_widgets import GENERIC_COLS
from alan_trader.strategy_api.registry import get_ui
from app.pages.strategies.registry import (
    _STRATEGIES_RULES, _STRATEGIES_AI, _UNIVERSE_OPTIONS, _STATUS_COLORS,
    get_strategy_status, get_strategy_score, get_score_color,
)
from app.pages.strategies.format import (
    _load_guide,
)
from app.pages.strategies.backtest_view import _get_ui_params_for_slug

logger = logging.getLogger(__name__)


def _checklist_options_with_status(strategies: list[dict]) -> list[dict]:
    """Convert a list of `{"label","value"}` entries to selector options where
    each label carries a coloured dot reflecting the strategy's review status
    (ready/reviewed/reviewing/avoid).

    `search` keeps the dropdown's type-ahead working: react-select filters on
    label text, and these labels are components, so the plain name is supplied
    separately.
    """
    out = []
    for s in strategies:
        slug = s["value"]
        status = get_strategy_status(slug)
        dot_color = _STATUS_COLORS[status]["dot"]
        out.append({
            "label": html.Span([
                html.Span("●", style={"color": dot_color, "marginRight": "7px",
                                       "fontSize": "11px",
                                       "verticalAlign": "middle"}),
                html.Span(s["label"], style={"verticalAlign": "middle"}),
            ], title=f"Status: {_STATUS_COLORS[status]['label']}"),
            "value": slug,
            "search": f"{s['label']} {slug}",
        })
    return out


def _status_legend() -> html.Div:
    """Status colour key, compact enough to sit in the page header."""
    return html.Div(
        [html.Span([
            html.Span("●", style={"color": meta["dot"], "marginRight": "4px",
                                  "fontSize": "10px"}),
            html.Span(meta["label"], style={"color": T.TEXT_MUTED,
                                            "fontSize": "10px"}),
        ], style={"marginLeft": "12px", "whiteSpace": "nowrap"},
            title=f"Review status: {meta['label']}")
         for meta in _STATUS_COLORS.values()],
        style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"},
    )


def _api_key_pill() -> html.Div:
    """Polygon key state as a pill — it was a full-width line of its own."""
    ok = bool(get_polygon_api_key())
    colour = T.SUCCESS if ok else T.WARNING
    return html.Div([
        html.Span("●", style={"color": colour, "marginRight": "5px",
                              "fontSize": "9px"}),
        html.Span("Polygon key" if ok else "No Polygon key",
                  style={"color": T.TEXT_MUTED, "fontSize": "10px"}),
    ], title=("Polygon API key loaded" if ok else
              "Set POLYGON_API_KEY before scanning"),
        style={"display": "flex", "alignItems": "center", "marginLeft": "18px",
               "whiteSpace": "nowrap"})


def _selector_group(title: str, icon: str, accent: str, element_id: str,
                    strategies: list[dict], placeholder: str) -> html.Div:
    """One labelled group of toggle pills.

    This is a `dbc.Checklist` — the control the callbacks were always written
    against, so `value` stays a list of slugs — restyled into pills entirely in
    CSS (`.strat-chips` in z_polish.css). Keeping a real checkbox input means
    keyboard and screen-reader behaviour are unchanged; only the painting
    differs.
    """
    return html.Div([
        html.Div([
            html.Span(icon, style={"marginRight": "6px", "fontSize": "11px"}),
            html.Span(title, style={
                "fontSize": "10px", "fontWeight": "700",
                "letterSpacing": "0.08em", "textTransform": "uppercase",
                "color": accent,
            }),
            html.Span(f"· {len(strategies)}", style={
                "marginLeft": "6px", "fontSize": "10px",
                "color": T.TEXT_MUTED, "fontWeight": "500",
            }),
        ], style={"display": "flex", "alignItems": "center",
                  "marginBottom": "6px"}),
        dbc.Checklist(
            id=element_id,
            options=_checklist_options_with_status(strategies),
            value=[],
            # Block items (not inline) so CSS columns can pack them densely.
            inline=False,
            className="strat-list",
        ),
    ], style={"flex": "1 1 340px", "minWidth": "280px"})


def _default_ticker(slug: str) -> str:
    """The ticker a strategy's tabs start with: meta['default_ticker'], else SPY."""
    try:
        return str(get_ui(slug).meta.get("default_ticker") or "SPY").upper()
    except Exception:
        return "SPY"


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
    ui = get_ui(slug)
    universe_id   = f"str-{slug}-universe"
    custom_id     = f"str-{slug}-custom"
    scan_id       = f"str-{slug}-scan-btn"
    grid_id       = f"str-{slug}-grid"
    status_id     = f"str-{slug}-status"
    vix_banner_id = f"str-{slug}-vix-banner"
    loading_id    = f"str-{slug}-loading"
    cols          = ui.columns or GENERIC_COLS

    params_spec  = list(ui.screener_params or [])
    filter_tog   = f"str-{slug}-filter-toggle"
    filter_col   = f"str-{slug}-filter-collapse"

    locked_tickers = list(ui.locked_tickers or [])
    locked       = bool(locked_tickers)
    locked_label = ui.locked_label or (f"{len(locked_tickers)} fixed tickers" if locked else "")
    locked_value = ",".join(locked_tickers) if locked else None

    try:
        info_banner = ui.info_banner()
    except Exception:
        logger.exception(f"{slug}: info_banner failed")
        info_banner = None

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
        # f"{grid_id}-clicked" hidden Dash input).
        dcc.Loading(
            html.Div(
                _mrt_clickable(
                    grid_id=grid_id,
                    col_defs=cols,
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

    Reflects the plugin's hardening review (edge realism + implementation
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
    return C.card([
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
    ], pad="lg")


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

    controls = C.card([
        html.Div([
            html.Div([_lbl("Ticker"),
                dbc.Input(id=f"str-{slug}-bt-ticker", value=_default_ticker(slug), placeholder="e.g. SPY",
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
            html.Div([_lbl(" "),
                dbc.Button("Run Backtest", id=f"str-{slug}-bt-run", color="primary",
                           style={"fontWeight": "600", "fontSize": "13px",
                                  "height": "34px", "padding": "0 20px",
                                  "whiteSpace": "nowrap"})]),
        ], style={"display": "flex", "gap": "10px", "alignItems": "flex-end",
                  "padding": "2px 0"}),
    ])

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

        slider_cards = [C.section("Strategy Parameters", slider_children)]

    # ── Results area ──────────────────────────────────────────────────────────
    results_area = dcc.Loading(
        html.Div(id=f"str-{slug}-bt-results"),
        type="circle",
        color=T.ACCENT,
    )

    return html.Div([controls] + slider_cards + [results_area], style={"padding": "4px 0"})


def _performance_tab(slug: str) -> html.Div:
    """Real analytics — see performance.py."""
    from app.pages.strategies.performance import performance_tab
    return performance_tab(slug)


def _simulator_stub(slug: str) -> html.Div:
    return C.card(C.empty_state("Simulator tab — coming in Phase 7.", icon="🎛"))


# ── Test tab ─────────────────────────────────────────────────────────────────

_TEST_MARK_OPTIONS = [
    {"label": "All tests",    "value": "all"},
    {"label": "Unit only",    "value": "not db and not polygon"},
    {"label": "DB tests",     "value": "db"},
    {"label": "Polygon live", "value": "polygon"},
]


def _test_tab(slug: str) -> html.Div:
    suites = list(get_ui(slug).test_suites or [])
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
                    placeholder="No suites declared" if not suites else None,
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
                           color="primary", size="sm", disabled=not suites,
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
            ]) if suites else html.Div(
                "This strategy's plugin declares no test suites for the Test tab.",
                style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
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


# ── Signal & Alert tab (strategies that publish a live signal) ────────────────

def _signal_alert_tab(slug: str) -> html.Div:
    return html.Div([
        html.Div("Current Signal & WhatsApp Alert", style={
            "fontSize": "15px", "fontWeight": "700", "color": T.TEXT_PRIMARY,
            "marginBottom": "6px"}),
        html.P(f"Check today's verdict for {_default_ticker(slug)} and (optionally) text it to "
               "your phone. Manual — fires only when you click.",
               style={"color": T.TEXT_MUTED, "fontSize": "12px", "marginBottom": "12px"}),
        html.Div([
            dbc.Button("📲 Check & text me this signal", id=f"str-{slug}-alert-btn",
                       color="primary", size="sm", n_clicks=0,
                       style={"marginRight": "10px"}),
            dbc.Button("Check only (no text)", id=f"str-{slug}-alert-check",
                       color="secondary", size="sm", outline=True, n_clicks=0),
        ], style={"marginBottom": "14px"}),
        dcc.Loading(html.Div(id=f"str-{slug}-alert-status"), type="dot"),
        html.Div(id=f"str-{slug}-alert-config", style={
            "color": T.TEXT_MUTED, "fontSize": "11px", "marginTop": "14px"}),
    ], style={"padding": "16px 4px"})


# ── Inner tabs per strategy ───────────────────────────────────────────────────

def _inner_tabs(slug: str) -> dbc.Tabs:
    ui = get_ui(slug)
    tab_style     = {"fontSize": "13px", "padding": "6px 14px"}
    tab_act_style = {**tab_style, "borderTop": f"2px solid {T.ACCENT}"}
    tabs = []
    if ui.meta.get("has_screener", True):
        tabs.append(dbc.Tab(
            _screener_layout(slug),
            label="Screener",
            tab_id=f"str-{slug}-inner-screener",
            tab_style=tab_style,
            active_tab_style=tab_act_style,
        ))
    tabs += [
        dbc.Tab(
            _backtest_tab(slug),
            label="Backtest",
            tab_id=f"str-{slug}-inner-backtest",
            tab_style=tab_style,
            active_tab_style=tab_act_style,
        ),
        dbc.Tab(
            _performance_tab(slug),
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

    # Strategy-provided tabs (model inspection, live signal panels, ...)
    try:
        extra = ui.extra_tabs() or []
    except Exception:
        logger.exception(f"{slug}: extra_tabs failed")
        extra = []
    for spec in extra:
        tabs.append(dbc.Tab(
            spec.content,
            label=spec.label,
            tab_id=f"str-{slug}-inner-{spec.tab_id}",
            tab_style=tab_style,
            active_tab_style={**tab_act_style,
                              "borderTop": f"2px solid {spec.accent or T.ACCENT}"},
        ))

    # Signal & Alert tab — strategies that publish a live signal
    if ui.has_signal_alert:
        tabs.append(dbc.Tab(
            _signal_alert_tab(slug),
            label="Signal & Alert",
            tab_id=f"str-{slug}-inner-alert",
            tab_style=tab_style,
            active_tab_style={**tab_act_style, "borderTop": f"2px solid {T.ACCENT}"},
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

def _no_plugins_notice() -> html.Div:
    return C.card([
        html.Div("No strategy packages installed.", style={
            "color": T.TEXT_PRIMARY, "fontSize": "14px", "fontWeight": "600",
            "marginBottom": "6px"}),
        html.Div([
            "This platform ships no strategies. Install a strategy plugin "
            "(a package exposing a ", html.Code("StrategyPlugin"),
            " through the ", html.Code("alan_trader.strategies"),
            " entry point, or listed in ", html.Code("ALAN_TRADER_STRATEGY_PACKAGES"),
            ") and restart the app.",
        ], style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
    ], pad="lg")


def layout() -> html.Div:
    groups = []
    if _STRATEGIES_RULES:
        groups.append(_selector_group("Rules-Based", "⚙", T.ACCENT,
                                      "str-strategy-select-rules", _STRATEGIES_RULES,
                                      "Search rules-based strategies…"))
    if _STRATEGIES_AI:
        groups.append(_selector_group("AI-Powered", "🤖", "#a78bfa",
                                      "str-strategy-select-ai", _STRATEGIES_AI,
                                      "Search AI strategies…"))

    if groups:
        # The selection callback lists BOTH checklists as Inputs; when only one
        # category is installed (e.g. an allow-list of rules-only strategies) the
        # other must still exist or Dash refuses to fire the callback at all.
        hidden = []
        if not _STRATEGIES_RULES:
            hidden.append(dbc.Checklist(id="str-strategy-select-rules", options=[], value=[],
                                        style={"display": "none"}))
        if not _STRATEGIES_AI:
            hidden.append(dbc.Checklist(id="str-strategy-select-ai", options=[], value=[],
                                        style={"display": "none"}))
        selector = C.card([
            html.Div(groups, style={"display": "flex", "alignItems": "flex-start",
                                    "flexWrap": "wrap", "gap": "18px"}),
            *hidden,
            # Hidden combined store consumed by update_outer_tabs
            dcc.Store(id="str-strategy-select"),
        ], pad="sm")
    else:
        selector = html.Div([
            _no_plugins_notice(),
            # The selection callbacks reference these ids even with nothing to select.
            dbc.Checklist(id="str-strategy-select-rules", options=[], value=[],
                          style={"display": "none"}),
            dbc.Checklist(id="str-strategy-select-ai", options=[], value=[],
                          style={"display": "none"}),
            dcc.Store(id="str-strategy-select"),
        ])

    return html.Div(
        [
            C.page_header(
                "Strategies",
                "Screen, backtest, and read the playbook for each strategy.",
                actions=[_status_legend(), _api_key_pill()],
            ),

            # ── Strategy selector ─────────────────────────────────────────────
            selector,

            # ── Signal detail modal (one modal serves every strategy) ─────────
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
                                  min=1, max=100, step=1,
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
                    "Select at least one strategy above." if groups
                    else "Install a strategy package to get started.",
                    style={"color": T.TEXT_MUTED, "fontSize": "14px"},
                )
            ]),
        ],
        style=T.STYLE_PAGE,
    )
