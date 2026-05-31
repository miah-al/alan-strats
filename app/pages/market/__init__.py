"""
app/pages/market/ - Market Data page (package).

Split from the original ~3000-line market.py into focused modules:
  data.py      - pure data/logic (Polygon, FRED, yfinance, screener, formatters,
                 render helpers). No @callback.
  guides.py    - static illustrative guide builders (pure synthetic, no API).
  layout.py    - the layout() view (uses the shared design system).
  callbacks.py - every @callback (registered on import).

Public surface is unchanged: `from app.pages.market import layout`.
Importing this package registers the callbacks via the callbacks import side
effect, so the app's existing `import app.pages.market` keeps everything
wired. Do not remove the callbacks import.
"""
from app.pages.market.layout import layout        # noqa: F401  (public API)
from app.pages.market import callbacks            # noqa: F401  (registers callbacks)

__all__ = ["layout"]
