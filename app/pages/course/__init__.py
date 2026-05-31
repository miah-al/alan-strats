"""
app/pages/course/ — Quant Course page (package).

Split from the original 458-line course.py into focused modules:
  content.py     — chapter discovery + markdown transforms (pure logic)
  layout.py      — the view (sidebar nav + reading pane), uses app.ui
  callbacks.py   — the 4 Dash callbacks (registered on import)
  print_view.py  — print-ready HTML + Flask routes (/course/print, /guide-figure)

Public surface is unchanged: `from app.pages.course import layout`.
Importing this package registers the callbacks AND the Flask print routes, so the
app's existing `import app.pages.course` (in app.py) keeps everything wired.
"""
from app.pages.course.layout import layout          # noqa: F401  (public API)
from app.pages.course import callbacks              # noqa: F401  (registers callbacks)
from app.pages.course import print_view             # noqa: F401  (registers Flask routes)

__all__ = ["layout"]
