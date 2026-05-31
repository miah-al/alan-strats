"""
dash_app/pages/models - Models workbench (package).

Split from the original monolithic models.py:
  pricing.py   - numerical/figure/UI helpers (pure logic)
  layout.py    - tab builders + layout()
  callbacks.py - all @callback handlers + slider-readout registration

Public surface unchanged: `from dash_app.pages.models import layout`.
Importing the package imports callbacks for its registration side-effect.
"""
from dash_app.pages.models.layout import layout      # noqa: F401  (public API)
from dash_app.pages.models import callbacks          # noqa: F401  (registers callbacks)

__all__ = ["layout"]
