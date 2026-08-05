"""
app/pages/scope — the Scope page: strategy scope + review reports.

Package layout mirrors the other pages: `content` (data), `layout`
(presentation), `callbacks` (behaviour). The callbacks import below is a
registration side effect and must not be removed — Dash registers `@callback`
at import time, so dropping it leaves the page inert.
"""
from app.pages.scope.layout import layout          # noqa: F401  (public API)
from app.pages.scope import callbacks              # noqa: F401  (registers callbacks)

__all__ = ["layout"]
