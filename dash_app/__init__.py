# dash_app — Parallel Dash frontend for alan_trader.

import os


def _load_env():
    """Load .env from alan_trader/ root into os.environ (same logic as dashboard/app.py)."""
    _here = os.path.dirname(os.path.abspath(__file__))  # alan_trader/dash_app/
    env_path = os.path.abspath(os.path.join(_here, "..", ".env"))  # alan_trader/.env
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()  # runs at import time, just like Streamlit's _load_env()


def get_polygon_api_key(user_input: str = "") -> str:
    """Return Polygon API key: user input → .env / env var → config.py → empty."""
    if user_input and user_input.strip() and user_input != "YOUR_POLYGON_API_KEY":
        return user_input.strip()
    env = os.environ.get("POLYGON_API_KEY", "")
    if env and env != "YOUR_POLYGON_API_KEY":
        return env
    try:
        from config import POLYGON_API_KEY
        if POLYGON_API_KEY and POLYGON_API_KEY != "YOUR_POLYGON_API_KEY":
            return POLYGON_API_KEY
    except Exception:
        pass
    return ""
