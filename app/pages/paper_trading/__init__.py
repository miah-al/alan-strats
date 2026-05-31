"""
app/pages/paper_trading/ — Paper Trading page (package).

Split from the original ~2930-line paper_trading.py into focused modules:
  data.py      — pure data/pricing logic (no @callback)
  builders.py  — UI builders: figures, tables, modal bodies, column defs
  layout.py    — the view (header, metric row, tabs, modals, stores)
  callbacks.py — every Dash callback (registered on import)

Public surface is unchanged: `from app.pages.paper_trading import layout`.
Importing this package registers the callbacks via side effect, so the app's
existing `import app.pages.paper_trading` keeps everything wired.
"""
from app.pages.paper_trading.layout import layout        # noqa: F401  (public API)
from app.pages.paper_trading import callbacks            # noqa: F401  (registers callbacks)

__all__ = ["layout"]
