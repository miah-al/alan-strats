"""
engine/env.py — the checkout's ``.env`` and the credentials it carries, headless.

Every process of the platform (the service, the paper runner, scripts, the Dash app while it
exists) reads its keys from ``<checkout>/.env`` into ``os.environ`` with ``setdefault``
semantics: a variable already set in the environment wins. No python-dotenv needed.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

#: The checkout (the directory holding engine/, db/, api/ …) and its .env file.
CHECKOUT: Path = Path(__file__).resolve().parent.parent
ENV_FILE: Path = CHECKOUT / ".env"

_PLACEHOLDER = "YOUR_POLYGON_API_KEY"


def load_env(path: Optional[Path] = None) -> bool:
    """Load ``KEY=VALUE`` lines from ``path`` (default ``<checkout>/.env``) into os.environ
    without overriding anything already set. Returns whether the file existed."""
    p = Path(path) if path is not None else ENV_FILE
    if not p.exists():
        return False
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    return True


def get_polygon_api_key(user_input: str = "") -> str:
    """Polygon API key: explicit input → .env / environment → config.py → empty."""
    if user_input and user_input.strip() and user_input != _PLACEHOLDER:
        return user_input.strip()
    env = os.environ.get("POLYGON_API_KEY", "")
    if env and env != _PLACEHOLDER:
        return env
    try:
        from config import POLYGON_API_KEY
        if POLYGON_API_KEY and POLYGON_API_KEY != _PLACEHOLDER:
            return POLYGON_API_KEY
    except Exception:
        pass
    return ""


def tastytrade_credentials() -> Optional[tuple[str, str]]:
    """(TT_SECRET, TT_REFRESH) — the OAuth provider secret and refresh token — or None."""
    secret, refresh = os.environ.get("TT_SECRET", ""), os.environ.get("TT_REFRESH", "")
    return (secret, refresh) if secret and refresh else None
