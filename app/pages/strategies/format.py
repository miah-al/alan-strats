"""
app/pages/strategies/format.py

Pure formatting helpers used by the screener and signal-modal renderers.
No DB calls, no callbacks — only string-formatting and html.Div builders.
The numeric helpers live in app.ui.strategy_widgets (shared with plugins) and
are re-exported here under their historical names.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from app import theme as T
from app.ui.strategy_widgets import num as _num, fmt_pct as _fmt_pct, fmt2 as _fmt2, fmt_price as _fmt_price  # noqa: F401

_TONE_COLOR = {"success": T.SUCCESS, "warning": T.WARNING, "danger": T.DANGER,
               "muted": T.TEXT_SEC, "default": T.TEXT_PRIMARY}


# ── VIX banner ────────────────────────────────────────────────────────────────

def _vix_banner(vix_series, slug: str) -> html.Div:
    """4-pill VIX context banner for screener top. The status line comes from
    the strategy's UI hook when it has one."""
    from engine.screener import _vix_ivr, _vix_20d_avg
    from alan_trader.strategy_api.registry import get_ui
    if vix_series is None or len(vix_series) == 0:
        return html.Div()

    current_vix = float(vix_series.iloc[-1])
    vix_20d_avg = _vix_20d_avg(vix_series)
    current_ivr = _vix_ivr(vix_series)
    n_pts       = len(vix_series)

    vix_color = (T.DANGER if current_vix > 35 else
                 T.WARNING if current_vix > 25 else T.SUCCESS)

    status_text  = f"VIX 20d avg: {vix_20d_avg:.1f}"
    status_color = T.TEXT_SEC
    try:
        custom = get_ui(slug).vix_banner_status(current_vix, vix_20d_avg)
    except Exception:
        custom = None
    if custom:
        status_text, tone = custom
        status_color = _TONE_COLOR.get(tone, tone)

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
    from app.guides import load_guide
    return load_guide(slug)
