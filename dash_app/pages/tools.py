"""
dash_app/pages/tools.py — Tools page.

Tabs:
  1. Data Manager  — sync controls, coverage tables, training validation
  2. IV Metrics    — IVR chart, IV vs HV comparison, term structure
  3. Guide         — browse all strategy guide articles
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc, callback, Input, Output, State, no_update

from dash_app import theme as T, get_polygon_api_key

logger = logging.getLogger(__name__)

_GUIDE_DIR = Path(__file__).parent.parent.parent / "dashboard" / "tabs" / "guide_articles"

# ── Coverage symbols ──────────────────────────────────────────────────────────

_COVERAGE_SYMBOLS = ["HOOD", "SPY", "QQQ", "AAPL", "TSLA", "MARA", "TLT"]

# ── Tab style helper ──────────────────────────────────────────────────────────

_TAB_STYLE    = {"fontSize": "13px", "padding": "6px 14px"}
_TAB_ACT_STYLE = {**_TAB_STYLE, "borderTop": f"2px solid {T.ACCENT}"}


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
            size="sm",
            style={"fontSize": "12px", "minWidth": "220px"},
        ),
        html.Span(id=status_id, style={"fontSize": "12px", "marginLeft": "10px"}),
        html.Div(id=caption_id, style={"color": T.TEXT_MUTED, "fontSize": "11px",
                                       "marginLeft": "10px"}),
    ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px",
               "flexWrap": "wrap", "gap": "4px"})


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

        # ── Sync buttons ──────────────────────────────────────────────────────
        html.Div([
            # Left column — Polygon
            html.Div([
                _section_label("Polygon (API key required)"),
                _sync_row("Sync Price Bars",   "tools-dm-btn-price",    "tools-dm-st-price",    "tools-dm-cap-price"),
                _sync_row("Sync News",          "tools-dm-btn-news",     "tools-dm-st-news",     "tools-dm-cap-news"),
                _sync_row("Sync Options",       "tools-dm-btn-options",  "tools-dm-st-options",  "tools-dm-cap-options"),
                _sync_row("Sync Dividends",     "tools-dm-btn-divs",     "tools-dm-st-divs",     "tools-dm-cap-divs"),
                _sync_row("Sync Earnings",      "tools-dm-btn-earnings", "tools-dm-st-earnings", "tools-dm-cap-earnings"),
                html.Div(style={"height": "12px"}),
                _section_label("Alpha Vantage"),
                dbc.Input(
                    id="tools-dm-av-key",
                    placeholder="Alpha Vantage API key (free at alphavantage.co)",
                    type="password",
                    style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                           "border": f"1px solid {T.BORDER}", "fontSize": "12px",
                           "marginBottom": "8px"},
                    debounce=True,
                ),
                _sync_row("Sync EPS Estimates", "tools-dm-btn-eps",     "tools-dm-st-eps",      "tools-dm-cap-eps"),
            ], style={"flex": "1", "minWidth": "320px"}),

            # Right column — Free sources
            html.Div([
                _section_label("Free Sources (FRED / CBOE)"),
                _sync_row("Sync Treasury Yields — FRED", "tools-dm-btn-treasury", "tools-dm-st-treasury", "tools-dm-cap-treasury"),
                _sync_row("Sync VIX Bars — CBOE",        "tools-dm-btn-vix",      "tools-dm-st-vix",      "tools-dm-cap-vix"),
                _sync_row("Sync Macro — FRED",            "tools-dm-btn-macro",    "tools-dm-st-macro",    "tools-dm-cap-macro"),
                _sync_row("Sync CPI — FRED",              "tools-dm-btn-cpi",      "tools-dm-st-cpi",      "tools-dm-cap-cpi"),
                _sync_row("Sync FOMC Calendar",           "tools-dm-btn-fomc",     "tools-dm-st-fomc",     "tools-dm-cap-fomc"),
            ], style={"flex": "1", "minWidth": "320px"}),
        ], style={"display": "flex", "gap": "32px", "flexWrap": "wrap",
                  "marginBottom": "24px"}),

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

def _guide_options() -> list[dict]:
    """Build dropdown options from all .md files in guide_articles/."""
    options = []
    if _GUIDE_DIR.exists():
        for p in sorted(_GUIDE_DIR.glob("*.md")):
            slug = p.stem
            label = slug.replace("_", " ").title()
            options.append({"label": label, "value": slug})
    return options


def _guide_tab() -> html.Div:
    opts = _guide_options()
    default = opts[0]["value"] if opts else None
    return html.Div([
        html.Div([
            html.Label("Select Article", style={"color": T.TEXT_SEC, "fontSize": "12px",
                                                 "marginBottom": "4px", "display": "block"}),
            dbc.Select(
                id="tools-guide-select",
                options=opts,
                value=default,
                style={"backgroundColor": T.BG_ELEVATED, "color": T.TEXT_PRIMARY,
                       "border": f"1px solid {T.BORDER}", "fontSize": "13px",
                       "width": "360px"},
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
                dbc.Tab(_data_manager_tab(), label="Data Manager",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(_iv_metrics_tab(),   label="IV Metrics",
                        tab_style=_TAB_STYLE, active_tab_style=_TAB_ACT_STYLE),
                dbc.Tab(_guide_tab(),        label="Guide",
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
            _col("Ticker", width=90),
            _col("Price Bars", width=100, numeric=True),
            _col("Price From", width=110),
            _col("Price To",   width=110),
            _col("Opt Days",   width=100, numeric=True),
            _col("Opt From",   width=110),
            _col("Opt To",     width=110),
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
        _col("Ticker",  width=90),
        _col("ATM IV",  width=80),
        _col("IVR",     width=75),
        _col("HV20",    width=75),
        _col("VRP",     width=75),
        _col("IV/HV",   width=75),
        _col("DTE",     width=60),
        _col("Strike",  width=85),
        _col("Conf",    width=75),
        _col("Source",  flex=2, min_width=140),
        _col("Error",   flex=2, min_width=100),
    ]

    summary_grid = dag.AgGrid(
        rowData=rows,
        columnDefs=tbl_cols,
        defaultColDef={"resizable": True},
        className=T.AGGRID_THEME,
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
    return dcc.Markdown(
        content,
        style={"color": T.TEXT_PRIMARY, "fontSize": "14px", "lineHeight": "1.75"},
    )
