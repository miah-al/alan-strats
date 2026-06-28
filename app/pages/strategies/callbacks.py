"""
app/pages/strategies/callbacks.py — layout-driving Dash callbacks (registered on import).
"""
from __future__ import annotations

import logging

from app.grid_helpers import (
    mrt_grid as _mrt_grid_shared,
)
import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, State, no_update, ctx

from app import theme as T
from app.ui import components as C
from app.pages.strategies.registry import (
    _STRATEGIES, _SLUG_TO_LABEL,
)
from app.pages.strategies.layout import (
    _SAMPLE_DATA_PATH, _TEST_SUITES, _SIGNAL_ALERT_SLUGS, _inner_tabs,
)

logger = logging.getLogger(__name__)

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

        stats_row = C.kpi_row([
            ("Rows", f"{n_rows:,}"),
            ("Features", f"{n_cols - 3}"),
            ("Positive Rate", pos_rate, "success"),
            ("Date Range", date_rng),
        ])

        # Preview last 10 rows
        preview = df.tail(10).round(4)
        col_defs = [{"field": c, "width": 80 if c == "date" else 70,
                     "minWidth": 60} for c in preview.columns]
        col_defs[0]["width"] = 100  # date column wider

        grid = _mrt_grid_shared(
            data=preview.to_dict("records"),
            col_defs=col_defs,
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

def _make_signal_alert_callback(slug: str):
    @callback(
        Output(f"str-{slug}-alert-status", "children"),
        Output(f"str-{slug}-alert-config", "children"),
        Input(f"str-{slug}-alert-btn",   "n_clicks"),
        Input(f"str-{slug}-alert-check", "n_clicks"),
        prevent_initial_call=True,
    )
    def _alert(n_send, n_check):
        trig = ctx.triggered_id
        if not trig:
            return no_update, no_update
        do_send = (trig == f"str-{slug}-alert-btn")
        try:
            from strategies.timing_base import load_close
            from strategies.trend_following import current_trend_signal
            from strategies.ts_momentum import current_tsmom_signal
            from engine.signal_alerts import format_signal_line, send_trade_alert
            from engine.notify import whatsapp_configured

            close = load_close("SPY")
            sig = (current_trend_signal(close) if slug == "trend_following"
                   else current_tsmom_signal(close))
            label = "200-Day Trend" if slug == "trend_following" else "12-Month Momentum"
            sig["label"] = label; sig["ticker"] = "SPY"

            color = T.SUCCESS if sig.get("signal") == "BUY" else T.WARNING
            body = [
                html.Div([
                    html.Span(f"{label} · SPY: ", style={"color": T.TEXT_MUTED, "fontSize": "13px"}),
                    html.Span(sig.get("signal", "?"), style={"color": color, "fontWeight": "700",
                                                             "fontSize": "16px"}),
                    html.Span(f"  {sig.get('state','')}", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
                ]),
                html.Div(format_signal_line(sig).split("\n", 1)[-1],
                         style={"color": T.TEXT_SEC, "fontSize": "12px", "whiteSpace": "pre-line",
                                "marginTop": "4px"}),
            ]

            cfg = ""
            if do_send:
                if not whatsapp_configured():
                    body.append(html.Div("⚠ WhatsApp not configured — set WHATSAPP_PHONE + "
                                         "CALLMEBOT_APIKEY in .env to enable texting.",
                                         style={"color": T.WARNING, "fontSize": "12px", "marginTop": "8px"}))
                else:
                    ok, detail = send_trade_alert(f"📊 {label} · SPY\n" + format_signal_line(sig))
                    body.append(html.Div(("✅ Text sent to your phone." if ok
                                          else f"❌ Send failed: {detail}"),
                                         style={"color": T.SUCCESS if ok else T.DANGER,
                                                "fontSize": "12px", "marginTop": "8px"}))
            from engine.notify import whatsapp_configured as _wc
            cfg = ("WhatsApp: configured ✓" if _wc() else
                   "WhatsApp: not configured (one-time CallMeBot setup needed)")
            return html.Div(body), cfg
        except Exception as e:
            return html.Div(f"Error: {e}", style={"color": T.DANGER, "fontSize": "12px"}), ""

    _alert.__name__ = f"_alert_{slug}"
    return _alert


for _slug in _SIGNAL_ALERT_SLUGS:
    _make_signal_alert_callback(_slug)

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
