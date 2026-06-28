"""
app/pages/strategies/layout.py — page layout + per-strategy tab builders (pure view, no @callback).
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app.grid_helpers import (
    clickable_mrt_grid as _mrt_clickable,
)
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc

from app import theme as T, get_polygon_api_key
from app.ui import components as C
from app.pages.strategies.registry import (
    _STRATEGIES_RULES, _STRATEGIES_AI, _SPY_ONLY_SLUGS, _SECTOR_ETFS_LIST, _SECTOR_ONLY_SLUGS, _UNIVERSE_OPTIONS, _STATUS_COLORS, get_strategy_status, get_strategy_score, get_score_color, _SCREENER_PARAMS,
)
from app.pages.strategies.columns import (
    _COLS_BY_SLUG, _IC_COLS,
)
from app.pages.strategies.format import (
    _load_guide,
)
from app.pages.strategies.backtest_view import _get_ui_params_for_slug

logger = logging.getLogger(__name__)

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


# _SCREENER_PARAMS moved to registry.py (pure config, shared with scan.py)


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


def _performance_stub(slug: str) -> html.Div:
    return C.card(C.empty_state("Performance analytics coming soon.", icon="📊"))


def _simulator_stub(slug: str) -> html.Div:
    return C.card(C.empty_state("Simulator tab — coming in Phase 7.", icon="🎛"))


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
    status_card = C.card([
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
    ], style={"borderLeft": f"3px solid {status_color}"})

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

        sanity_card = C.section("Model sanity checks", [
            _check_row("rv20 mean(state 2) > 2× mean(state 0)",
                       f"{rv_means[0]:.3f} / {rv_means[1]:.3f} / {rv_means[2]:.3f}  (ratio {rv_ratio:.2f}×)",
                       rv_ok),
            _check_row("Transition matrix diagonal > 0.85 (regime persistence)",
                       diag_text, diag_ok),
        ])

    # ── State reference cards ────────────────────────────────────────────────
    state_cards = []
    for label, desc, trade, struct, color in _HMM_STATE_REF:
        state_cards.append(dbc.Col(C.card([
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
        ], style={"borderTop": f"3px solid {color}", "height": "100%", "marginBottom": "0"}), md=4))

    state_ref_row = dbc.Row(state_cards, style={"marginBottom": "16px"})

    # ── Entry checklist (static reference) ───────────────────────────────────
    gate_rows = [html.Div([
        html.Span("□  ", style={"color": T.TEXT_MUTED, "fontFamily": "JetBrains Mono, monospace"}),
        html.Span(gate, style={"color": T.TEXT_PRIMARY, "fontSize": "12px",
                                "fontFamily": "JetBrains Mono, monospace"}),
        html.Span(f"   — {note}", style={"color": T.TEXT_MUTED, "fontSize": "11px"}),
    ], style={"marginBottom": "5px"}) for gate, note in _HMM_ENTRY_GATES]

    gates_card = C.section("Entry checklist (all must pass to open a trade)", gate_rows)

    # ── Compute today's signal — placeholder (callback to be wired) ──────────
    compute_card = C.section("Today's signal", [
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
    ])

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

_SAVED_MODELS_DIR = Path(__file__).parent.parent.parent.parent / "saved_models"
_SAMPLE_DATA_PATH = Path(__file__).parent.parent.parent.parent / "data" / "sample_ic_training_data.csv"


def _find_ic_ai_model() -> "Path | None":
    """Locate a trained IC-AI model on disk. Models are saved per-ticker as
    iron_condor_ai_{ticker}.pkl — there is no un-suffixed file. Prefer SPY, then
    the default fallback, then any trained ticker."""
    for name in ("iron_condor_ai_spy.pkl", "iron_condor_ai_default.pkl"):
        p = _SAVED_MODELS_DIR / name
        if p.exists():
            return p
    hits = sorted(_SAVED_MODELS_DIR.glob("iron_condor_ai_*.pkl"))
    return hits[0] if hits else None


def _model_tab(slug: str) -> html.Div:
    if slug != "iron_condor_ai":
        return html.Div()

    # ── Model status ──────────────────────────────────────────────────────────
    _model_path   = _find_ic_ai_model()
    model_trained = _model_path is not None
    status_color  = T.SUCCESS if model_trained else T.WARNING
    status_text   = f"Trained model found: {_model_path.name}" if model_trained \
                    else "No saved model — run a backtest to train the GBM classifier"

    status_card = C.card([
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
    ], style={"borderLeft": f"3px solid {status_color}"})

    # ── Feature importance chart (from model or placeholder) ──────────────────
    # Names MUST be the model's actual training columns (FEATURE_COLS, 14) and in
    # that order — feature_importances_ is positional, so using the old 17-item
    # reference list would mislabel every bar.
    from strategies.iron_condor_ai import IronCondorAIStrategy
    feat_names = list(IronCondorAIStrategy.FEATURE_COLS)

    importances = None
    if model_trained:
        try:
            import pickle
            with open(_model_path, "rb") as f:
                saved = pickle.load(f)
            # Pipeline(StandardScaler, GBC) → pull the classifier; also support
            # a raw model or a {"clf": model} dict wrapper.
            if hasattr(saved, "named_steps"):
                clf = saved.named_steps.get("clf")
            elif isinstance(saved, dict):
                clf = saved.get("clf")
            else:
                clf = saved
            imp = getattr(clf, "feature_importances_", None)
            if imp is not None and len(imp) == len(feat_names):
                importances = list(imp)
        except Exception:
            importances = None

    # Placeholder importances (aligned to FEATURE_COLS order) when no usable model
    if importances is None:
        importances = [
            0.16,  # ivr
            0.14,  # adx
            0.06,  # put_call_skew
            0.06,  # iv_term_slope
            0.10,  # vrp
            0.06,  # atr_pct
            0.05,  # ret_5d
            0.05,  # ret_20d
            0.06,  # dist_from_ma50
            0.08,  # vix_level
            0.05,  # vix_5d_change
            0.05,  # vix_ma_ratio
            0.04,  # yield_curve_2y10y
            0.04,  # days_to_month_end
        ]
        importance_note = " (illustrative — run backtest to see trained importances)"
    else:
        importance_note = " (from trained model)"

    # Sort by importance descending (guard the unpack against an empty pairing)
    paired = sorted(zip(feat_names, importances), key=lambda x: x[1], reverse=True)
    sorted_names, sorted_imps = (zip(*paired) if paired else ((), ()))
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

    importance_card = C.section("Feature Importances", [
        dcc.Graph(figure=fig_imp, config={"displayModeBar": False}),
    ])

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

    hyperparam_card = C.section("GBM Hyperparameters & Strategy Parameters", [hyp_table])

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

    feat_card = C.section("Feature Engineering — Model Input Features", [
        html.P([
            "All features are derived from ", html.Strong("price, VIX, and macro data"),
            " — no options chain required. VIX serves as the IV proxy. "
            "Features are constructed without lookahead: only data available at bar ", html.Em("t"),
            " is used to generate predictions for bar ", html.Em("t+1"), ".",
        ], style={"color": T.TEXT_SEC, "fontSize": "13px", "lineHeight": "1.6",
                  "marginBottom": "14px"}),
        feat_table,
    ])

    # ── Label construction note ───────────────────────────────────────────────
    label_card = C.section("Label Construction", [
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
    ])

    # ── Sample data section ───────────────────────────────────────────────────
    sample_exists = _SAMPLE_DATA_PATH.exists()
    sample_card = C.section("Sample Training Data", [
        html.Div(id="str-ic-ai-sample-data-body"),
        dcc.Store(id="str-ic-ai-sample-exists", data=sample_exists),
    ])

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



# ── Test tab ─────────────────────────────────────────────────────────────────

_TEST_SUITES = {
    "trend_following":       [{"id": "trend", "label": "Trend / Momentum Tests",     "module": "test_trend_following"}],
    "ts_momentum":           [{"id": "trend", "label": "Trend / Momentum Tests",     "module": "test_trend_following"}],
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



# ── Signal & Alert tab (validated trend / momentum strategies) ────────────────

_SIGNAL_ALERT_SLUGS = {"trend_following", "ts_momentum"}


def _signal_alert_tab(slug: str) -> html.Div:
    return html.Div([
        html.Div("Current Signal & WhatsApp Alert", style={
            "fontSize": "15px", "fontWeight": "700", "color": T.TEXT_PRIMARY,
            "marginBottom": "6px"}),
        html.P("Check today's BUY/HOLD verdict for SPY and (optionally) text it to "
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

    # Signal & Alert tab — validated trend / momentum strategies
    if slug in _SIGNAL_ALERT_SLUGS:
        tabs.append(dbc.Tab(
            _signal_alert_tab(slug),
            label="Signal & Alert",
            tab_id=f"str-{slug}-inner-alert",
            tab_style=tab_style,
            active_tab_style={**tab_act_style, "borderTop": f"2px solid {T.ACCENT}"},
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
            C.page_header(
                "Strategies",
                "Select strategies to screen opportunities, run backtests, and read guides.",
            ),

            # ── Strategy selector (AI vs Rules-Based) ────────────────────────
            C.card([
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
            ]),

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
