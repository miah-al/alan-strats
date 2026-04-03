"""
dash_app/theme.py
Color constants matching the Streamlit dark theme in dashboard/app.py.
"""

# ── Palette (mirrors CSS variables in dashboard/app.py) ──────────────────────
BG_BASE      = "#0a0e1a"
BG_CARD      = "#111827"
BG_ELEVATED  = "#161d2e"
ACCENT       = "#6366f1"
ACCENT_DIM   = "rgba(99,102,241,0.15)"
SUCCESS      = "#10b981"
DANGER       = "#ef4444"
WARNING      = "#f59e0b"
TEXT_PRIMARY = "#f9fafb"
TEXT_SEC     = "#9ca3af"
TEXT_MUTED   = "#6b7280"
BORDER       = "#1f2937"
BORDER_BRT   = "#374151"

# ── Sidebar ───────────────────────────────────────────────────────────────────
SIDEBAR_WIDTH = "220px"
SIDEBAR_BG    = "#0c1120"

# ── AG Grid theme ─────────────────────────────────────────────────────────────
AGGRID_THEME = "ag-theme-quartz-dark"

# ── Reusable inline style blocks ─────────────────────────────────────────────
STYLE_CARD = {
    "backgroundColor": BG_CARD,
    "border":          f"1px solid {BORDER}",
    "borderRadius":    "10px",
    "padding":         "16px",
}

STYLE_DROPDOWN = {
    "backgroundColor": BG_ELEVATED,
    "border":          f"1px solid {BORDER}",
    "color":           TEXT_PRIMARY,
    "fontSize":        "13px",
}

STYLE_PAGE = {
    "backgroundColor": BG_BASE,
    "minHeight":       "100vh",
    "color":           TEXT_PRIMARY,
    "fontFamily":      "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    "padding":         "24px 32px",
}
