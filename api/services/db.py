"""
api/services/db.py — the shared AlanStrats connection, read-only.

Every statement the service sends is screened by the guard ``api.bootstrap``
installs (a write raises ``ReadOnlyViolation`` before it reaches the server).
"""
from __future__ import annotations

from typing import Optional


class DatabaseUnavailable(RuntimeError):
    """The database cannot be reached; routers answer 503 with the real reason."""


def engine():
    from db.client import get_engine
    return get_engine()


def server_and_database() -> tuple[str, str]:
    from db import client
    return client._DEFAULT_SERVER, client._DEFAULT_DB


def ping() -> tuple[bool, Optional[str]]:
    try:
        with engine().connect() as c:
            c.exec_driver_sql("SELECT 1")
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc).splitlines()[0][:300] if str(exc) else ''}"


def require_db():
    ok, err = ping()
    if not ok:
        raise DatabaseUnavailable(f"database unavailable: {err}")
    return engine()


def query(sql: str, params: Optional[dict] = None) -> list[tuple]:
    from sqlalchemy import text
    with require_db().connect() as c:
        return [tuple(r) for r in c.execute(text(sql), params or {}).fetchall()]
