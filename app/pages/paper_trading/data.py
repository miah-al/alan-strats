"""
app/pages/paper_trading/data.py — moved to ``paper/views.py``.

The paper account's data and pricing logic is headless and shared with the service, so it lives
in ``paper.views``. This name is kept for the Paper Trading page while the Dash app exists: it
IS that module (one module object under two names), so the page, its callbacks and anything that
patches a setting here all see the same state.
"""
import sys

from paper import views as _views

sys.modules[__name__] = _views
