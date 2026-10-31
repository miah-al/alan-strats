"""
api/services/watchlists.py — named symbol lists in ``app.Watchlist``.

Symbols are stored in the market-data hub's canonical spelling (``^VIX`` → ``VIX``, options as
compact OCC), in the order given, duplicates dropped. Reading never creates the table.
"""
from __future__ import annotations

import json
from typing import Optional

from api.marketdata import symbols as SYM
from api.services.db import require_db

MAX_SYMBOLS = 500
MAX_NAME = 100


class WatchlistError(ValueError):
    pass


class UnknownWatchlist(KeyError):
    pass


def _clean_name(name: str) -> str:
    n = str(name or "").strip()
    if not n:
        raise WatchlistError("a watchlist needs a name")
    if len(n) > MAX_NAME:
        raise WatchlistError(f"a watchlist name is at most {MAX_NAME} characters")
    return n


def normalize_symbols(symbols) -> list[str]:
    if not isinstance(symbols, list):
        raise WatchlistError("symbols: a list of symbols")
    out, bad = [], []
    for s in symbols:
        try:
            c = SYM.normalize(str(s))
        except ValueError:
            bad.append(str(s))
            continue
        if c not in out:
            out.append(c)
    if bad:
        raise WatchlistError(f"not symbols: {bad}")
    if len(out) > MAX_SYMBOLS:
        raise WatchlistError(f"at most {MAX_SYMBOLS} symbols per watchlist")
    return out


def list_all() -> list[dict]:
    from sqlalchemy import text
    from api.services import appdb
    if not appdb.exists("Watchlist"):
        return []
    with require_db().connect() as c:
        rows = c.execute(text("SELECT Name, SymbolsJson, CreatedAt, UpdatedAt FROM app.Watchlist ORDER BY Name")).fetchall()
    return [_row(r) for r in rows]


def _row(r) -> dict:
    from api.services.orders import _iso_utc
    return {"name": r[0], "symbols": json.loads(r[1] or "[]"), "created": _iso_utc(r[2]), "updated": _iso_utc(r[3])}


def get(name: str) -> Optional[dict]:
    from sqlalchemy import text
    from api.services import appdb
    if not appdb.exists("Watchlist"):
        return None
    with require_db().connect() as c:
        r = c.execute(text("SELECT Name, SymbolsJson, CreatedAt, UpdatedAt FROM app.Watchlist WHERE Name = :n"),
                      {"n": _clean_name(name)}).fetchone()
    return _row(r) if r is not None else None


def put(name: str, symbols) -> dict:
    from sqlalchemy import text
    from api.services import appdb
    n = _clean_name(name)
    syms = normalize_symbols(symbols)
    appdb.ensure("Watchlist")
    with require_db().begin() as c:
        upd = c.execute(text("UPDATE app.Watchlist SET SymbolsJson = :s, UpdatedAt = SYSUTCDATETIME() WHERE Name = :n"),
                        {"n": n, "s": json.dumps(syms)})
        if upd.rowcount == 0:
            c.execute(text("INSERT INTO app.Watchlist (Name, SymbolsJson) VALUES (:n, :s)"), {"n": n, "s": json.dumps(syms)})
    return get(n)


def delete(name: str) -> None:
    from sqlalchemy import text
    from api.services import appdb
    n = _clean_name(name)
    if not appdb.exists("Watchlist"):
        raise UnknownWatchlist(n)
    with require_db().begin() as c:
        if c.execute(text("DELETE FROM app.Watchlist WHERE Name = :n"), {"n": n}).rowcount == 0:
            raise UnknownWatchlist(n)
