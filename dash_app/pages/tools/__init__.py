"""
dash_app/pages/tools/ -- Tools & Data Management hub (package).

Split from the original 2701-line tools.py into focused modules:
  data.py      -- pure data/logic helpers (no callbacks)
  tabs.py      -- per-tab layout builders + _get_tab_builder dispatch
  layout.py    -- the top-level layout() (dbc.Tabs shell + tools-tab-content div)
  callbacks.py -- all Dash callbacks, registered on import (tab routing + the
                  dynamically-registered per-symbol sync callbacks)

Public surface is unchanged: `from dash_app.pages.tools import layout`.
Importing this package registers the callbacks via the callbacks import below.
"""
from dash_app.pages.tools.layout import layout      # noqa: F401  (public API)
from dash_app.pages.tools import callbacks          # noqa: F401  (registers callbacks)

__all__ = ["layout"]
