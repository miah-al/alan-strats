"""
dash_app/pages/strategies/format.py

Pure formatting helpers used by the screener and signal-modal renderers.
No DB calls, no callbacks — only string-formatting and html.Div builders.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from dash_app import theme as T

from dash_app.pages.strategies.registry import _GUIDE_DIR


# ── Numeric formatters ────────────────────────────────────────────────────────

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
