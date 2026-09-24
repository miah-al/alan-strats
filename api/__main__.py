"""
python -m api — run the service with uvicorn.

    ALAN_TRADER_API_HOST   bind address (default 127.0.0.1 — loopback only)
    ALAN_TRADER_API_PORT   port (default 8765)
    ALAN_TRADER_API_LOG    log level (default info)
"""
from __future__ import annotations

import logging
import os
import sys


def main() -> int:
    level = os.environ.get("ALAN_TRADER_API_LOG", "info").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    # The platform's libraries log a lot at DEBUG/INFO through these; keep them quiet.
    for noisy in ("urllib3", "yfinance", "peewee", "matplotlib", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    from api.bootstrap import BootstrapError
    try:
        from api.app import create_app
        app = create_app()
    except BootstrapError as exc:
        print(f"alan_trader service: {exc}", file=sys.stderr)
        return 2

    import uvicorn
    host = os.environ.get("ALAN_TRADER_API_HOST", "127.0.0.1")
    port = int(os.environ.get("ALAN_TRADER_API_PORT", "8765"))
    uvicorn.run(app, host=host, port=port, log_level=level.lower(), log_config=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
