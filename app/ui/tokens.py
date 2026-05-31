"""
app/ui/tokens.py — the single design-system source of truth.

Today every page hardcodes its own colours, spacings, font sizes and Plotly
layouts inline. That is exactly why the app looks inconsistent. This module
centralises ALL design decisions so the whole app can be re-skinned in one place.

It re-exports the existing palette from theme.py (so nothing drifts) and adds the
missing scales a polished UI needs: spacing, radius, shadow, type, and a single
canonical Plotly dark layout.

Import convention:
    from app.ui import tokens as D     # "D" for design
    D.SPACE_4, D.COLOR.accent, D.plotly_layout(height=320)
"""
from __future__ import annotations

# Re-export the canonical palette from the existing theme so there is ONE source.
from app import theme as _T


# ── Colour (mirrors theme.py; namespaced for ergonomics) ─────────────────────
class COLOR:
    bg          = _T.BG_BASE        # #0a0e1a  page background
    card        = _T.BG_CARD        # #111827  card surface
    elevated    = _T.BG_ELEVATED    # #161d2e  inputs / dropdowns / raised
    sidebar     = _T.SIDEBAR_BG     # #0c1120

    accent      = _T.ACCENT         # #6366f1  indigo
    accent_dim  = _T.ACCENT_DIM     # rgba(99,102,241,.15)
    accent_soft = "rgba(99,102,241,0.10)"

    success     = _T.SUCCESS        # #10b981
    danger      = _T.DANGER         # #ef4444
    warning     = _T.WARNING        # #f59e0b
    info        = "#06b6d4"
    purple      = "#8b5cf6"

    text        = _T.TEXT_PRIMARY   # #f9fafb
    text_sec    = _T.TEXT_SEC       # #9ca3af
    text_muted  = _T.TEXT_MUTED     # #6b7280

    border      = _T.BORDER         # #1f2937
    border_brt  = _T.BORDER_BRT     # #374151


# ── Spacing scale (4px base — use these, never raw px) ────────────────────────
SPACE_1  = "4px"
SPACE_2  = "8px"
SPACE_3  = "12px"
SPACE_4  = "16px"
SPACE_5  = "20px"
SPACE_6  = "24px"
SPACE_8  = "32px"
SPACE_10 = "40px"

# ── Radius ────────────────────────────────────────────────────────────────────
RADIUS_SM = "6px"
RADIUS_MD = "10px"
RADIUS_LG = "14px"
RADIUS_PILL = "999px"

# ── Shadow ────────────────────────────────────────────────────────────────────
SHADOW_SM = "0 1px 2px rgba(0,0,0,.30)"
SHADOW_MD = "0 4px 14px rgba(0,0,0,.40)"
SHADOW_LG = "0 12px 34px rgba(0,0,0,.55)"

# ── Typography ────────────────────────────────────────────────────────────────
FONT_SANS = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
FONT_MONO = "'JetBrains Mono', 'Fira Code', ui-monospace, 'Courier New', monospace"

TEXT_XS  = "11px"
TEXT_SM  = "12px"
TEXT_MD  = "13px"
TEXT_LG  = "15px"
TEXT_XL  = "18px"
TEXT_2XL = "24px"

WEIGHT_NORMAL = "500"
WEIGHT_MED    = "600"
WEIGHT_BOLD   = "700"
WEIGHT_HEAVY  = "800"

# ── Layout constants (mirror app shell) ──────────────────────────────────────
SIDEBAR_WIDTH = _T.SIDEBAR_WIDTH    # 220px
AGGRID_THEME  = _T.AGGRID_THEME     # ag-theme-quartz-dark
PAGE_PAD      = "24px 32px"


# ── Canonical surface styles (replace the per-page STYLE_CARD copies) ─────────
CARD = {
    "backgroundColor": COLOR.card,
    "border":          f"1px solid {COLOR.border}",
    "borderRadius":    "14px",
    "padding":         "22px",
}

CARD_FLUSH = {**CARD, "padding": "0", "overflow": "hidden"}

PAGE = {
    "backgroundColor": COLOR.bg,
    "minHeight":       "100vh",
    "color":           COLOR.text,
    "fontFamily":      FONT_SANS,
    "padding":         PAGE_PAD,
}


# ── Canonical Plotly dark layout ─────────────────────────────────────────────
# Every chart in the app should start from this so they all match. Pass overrides
# as kwargs; they shallow-merge over the defaults.
def plotly_layout(height: int = 320, **overrides) -> dict:
    base = dict(
        template="plotly_dark",
        paper_bgcolor=COLOR.card,
        plot_bgcolor=COLOR.card,
        font=dict(color=COLOR.text_sec, size=11, family=FONT_SANS),
        height=height,
        margin=dict(l=12, r=12, t=30, b=12),
        xaxis=dict(gridcolor=COLOR.border, zerolinecolor=COLOR.border_brt),
        yaxis=dict(gridcolor=COLOR.border, zerolinecolor=COLOR.border_brt),
        legend=dict(orientation="h", x=0, y=1.08, font=dict(size=11),
                    bgcolor="rgba(0,0,0,0)"),
    )
    base.update(overrides)
    return base


# Standard Plotly config — no modebar clutter, responsive.
PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}
