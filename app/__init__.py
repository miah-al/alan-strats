# app — Parallel Dash frontend for alan_trader.
#
# The .env reader and the Polygon key lookup live in engine/env.py (headless, shared with the
# service and the paper runner); these names stay for the Dash pages until the app is removed.

try:
    from engine.env import get_polygon_api_key, load_env as _load_env_file
except ImportError:                      # imported as alan_trader.app without the checkout on sys.path
    from alan_trader.engine.env import get_polygon_api_key, load_env as _load_env_file


def _load_env():
    """Load .env from the checkout root into os.environ (existing variables win)."""
    _load_env_file()


_load_env()  # runs at import time, just like Streamlit's _load_env()

__all__ = ["get_polygon_api_key", "_load_env"]
