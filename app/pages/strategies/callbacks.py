"""
app/pages/strategies/callbacks.py — layout-driving Dash callbacks (registered on import).
"""
from __future__ import annotations

import logging

import dash_bootstrap_components as dbc
from dash import html, callback, Input, Output, State, no_update, ctx

from app import theme as T
from alan_trader.strategy_api import registry as R
from app.pages.strategies.registry import _STRATEGIES, _SLUG_TO_LABEL, slugs as _slugs
from app.pages.strategies.layout import _inner_tabs

logger = logging.getLogger(__name__)


# ── Test tab ──────────────────────────────────────────────────────────────────

def _make_test_callback(slug: str):
    ui = R.get_ui(slug)
    if not ui.test_suites:
        return None

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
        suites = R.get_ui(slug).test_suites
        suite  = next((s for s in suites if s["id"] == suite_id), None)
        if not suite:
            return "No test suite selected.", {"display": "block"}, html.P("No suite.")

        tests_dir = R.tests_dir_for(slug)
        root      = R.root_for(slug)
        if tests_dir is None:
            return ("The strategy's plugin declares no tests directory.",
                    {"display": "block"}, html.P("No tests directory."))
        test_file = os.path.join(str(tests_dir), f"{suite['module']}.py")
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
                cwd=str(root) if root else None,
            )
            output  = result.stdout + result.stderr
            elapsed = time.time() - t0
            passed  = output.count(" PASSED")
            failed  = output.count(" FAILED")
            errored = output.count(" ERROR")
            skipped = output.count(" SKIPPED")

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


for _slug in _slugs():
    _make_test_callback(_slug)


# ── Signal & Alert tab ────────────────────────────────────────────────────────

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
            from alan_trader.strategy_api.timing_base import load_close
            from engine.signal_alerts import format_signal_line, send_trade_alert
            from engine.notify import whatsapp_configured

            label = R.get_ui(slug).label
            ticker = str(R.get_ui(slug).meta.get("default_ticker") or "SPY").upper()
            close = load_close(ticker)
            sig = R.get_strategy(slug).current_signal(close)
            if not sig:
                return html.Div("This strategy publishes no live signal.",
                                style={"color": T.WARNING, "fontSize": "12px"}), ""
            sig = dict(sig)
            sig["label"] = label; sig["ticker"] = ticker

            _s = str(sig.get("signal", "")).upper()
            color = T.SUCCESS if _s in ("BUY", "OPEN", "TRADE") else T.DANGER if _s in ("SELL", "SKIP", "BLOCKED") else T.WARNING
            body = [
                html.Div([
                    html.Span(f"{label} · {ticker}: ", style={"color": T.TEXT_MUTED, "fontSize": "13px"}),
                    html.Span(sig.get("signal", "?"), style={"color": color, "fontWeight": "700",
                                                             "fontSize": "16px"}),
                    html.Span(f"  {sig.get('state','')}", style={"color": T.TEXT_MUTED, "fontSize": "12px"}),
                ]),
                html.Div(format_signal_line(sig).split("\n", 1)[-1],
                         style={"color": T.TEXT_SEC, "fontSize": "12px", "whiteSpace": "pre-line",
                                "marginTop": "4px"}),
            ]

            if do_send:
                if not whatsapp_configured():
                    body.append(html.Div("⚠ WhatsApp not configured — set WHATSAPP_PHONE + "
                                         "CALLMEBOT_APIKEY in .env to enable texting.",
                                         style={"color": T.WARNING, "fontSize": "12px", "marginTop": "8px"}))
                else:
                    ok, detail = send_trade_alert(f"📊 {label} · {ticker}\n" + format_signal_line(sig))
                    body.append(html.Div(("✅ Text sent to your phone." if ok
                                          else f"❌ Send failed: {detail}"),
                                         style={"color": T.SUCCESS if ok else T.DANGER,
                                                "fontSize": "12px", "marginTop": "8px"}))
            cfg = ("WhatsApp: configured ✓" if whatsapp_configured() else
                   "WhatsApp: not configured (one-time CallMeBot setup needed)")
            return html.Div(body), cfg
        except Exception as e:
            return html.Div(f"Error: {e}", style={"color": T.DANGER, "fontSize": "12px"}), ""

    _alert.__name__ = f"_alert_{slug}"
    return _alert


for _slug in _slugs():
    if R.get_ui(_slug).has_signal_alert:
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
