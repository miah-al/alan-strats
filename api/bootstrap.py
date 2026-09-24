"""
api/bootstrap.py — make the platform importable for the service process, safely.

The platform imports itself two ways: ``db.*``, ``engine.*``, ``paper.*`` … relative to
this checkout, and ``alan_trader.*`` relative to its parent directory. Strategies come
from the ``alan_trader_strategies`` plugin package, which normally sits next to the
checkout and is imported by name.

A service checkout can live next to ANOTHER copy of ``alan_trader`` (a git worktree
beside the live original). Putting the directory that holds both on ``sys.path`` would
let ``import alan_trader`` resolve to the wrong copy, so the plugin is never imported
through its parent directory: it is loaded by file path and registered in
``sys.modules`` before the registry runs discovery. After that, ``alan_trader`` and
``engine`` are asserted to resolve inside this checkout — the process refuses to start
otherwise. The service never imports the Dash app (``app/``).

Everything here is idempotent; ``bootstrap()`` may be called any number of times.
``install_db_read_only_guard()`` makes every SQLAlchemy engine in the process refuse
any write outside the service's allow-list (the paper ledger, the market-data tables the sync
jobs fill, the service's own ``app`` schema) — the database is shared with the live system.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("alan_trader.api")

#: This checkout (the directory holding app/, db/, engine/, api/ …).
WORKING_COPY: Path = Path(__file__).resolve().parent.parent
#: Its parent — on sys.path so ``import alan_trader`` resolves to WORKING_COPY.
PARENT: Path = WORKING_COPY.parent

PLUGIN_PACKAGE = "alan_trader_strategies"
ENV_STRATEGIES_DIR = "ALAN_TRADER_STRATEGIES_DIR"

_STATE: dict = {"done": False}


class BootstrapError(RuntimeError):
    """The process would import the wrong code; refuse to run."""


def _inside(path: Optional[str], root: Path) -> bool:
    if not path:
        return False
    try:
        Path(path).resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _foreign_alan_trader_dirs() -> list[str]:
    """sys.path entries that would expose a DIFFERENT ``alan_trader`` package."""
    bad = []
    for p in sys.path:
        try:
            cand = Path(p or os.getcwd()) / "alan_trader"
            if cand.is_dir() and cand.resolve() != WORKING_COPY:
                bad.append(p)
        except OSError:
            continue
    return bad


def _fix_sys_path() -> None:
    for p in _foreign_alan_trader_dirs():
        logger.warning("removing %r from sys.path: it holds a different alan_trader checkout", p)
        while p in sys.path:
            sys.path.remove(p)
    for p in (str(PARENT), str(WORKING_COPY)):
        if p not in sys.path:
            sys.path.insert(0, p)


def strategies_dir_candidates() -> list[Path]:
    env = os.environ.get(ENV_STRATEGIES_DIR, "").strip()
    if env:
        return [Path(env)]
    return [WORKING_COPY.parent.parent / PLUGIN_PACKAGE, WORKING_COPY.parent / PLUGIN_PACKAGE]


def _load_plugin_by_path() -> Optional[Path]:
    """Load the strategies package from its directory without touching sys.path."""
    env = os.environ.get("ALAN_TRADER_STRATEGY_PACKAGES")
    if env is not None and env.strip().lower() == "none":
        return None
    existing = sys.modules.get(PLUGIN_PACKAGE)
    if existing is not None:
        return Path(existing.__file__).resolve().parent if getattr(existing, "__file__", None) else None
    for d in strategies_dir_candidates():
        init = d / "__init__.py"
        if not init.is_file():
            continue
        d = d.resolve()
        spec = importlib.util.spec_from_file_location(
            PLUGIN_PACKAGE, str(d / "__init__.py"), submodule_search_locations=[str(d)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[PLUGIN_PACKAGE] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception:
            sys.modules.pop(PLUGIN_PACKAGE, None)
            logger.exception("strategy plugin at %s failed to load; running strategy-free", d)
            return None
        logger.info("strategy plugin loaded from %s (%d strategies)", d,
                    len(getattr(mod, "STRATEGY_METADATA", {}) or {}))
        return d
    logger.warning("no %s directory found (tried %s); running strategy-free", PLUGIN_PACKAGE,
                   ", ".join(str(p) for p in strategies_dir_candidates()))
    return None


def _reload_registries() -> None:
    """A registry imported before the plugin was loaded has already run discovery."""
    for name in ("alan_trader.strategy_api.registry", "strategy_api.registry"):
        mod = sys.modules.get(name)
        if mod is not None:
            try:
                mod.reload()
            except Exception:
                logger.exception("registry reload failed for %s", name)


def _assert_paths(plugin_dir: Optional[Path]) -> None:
    import alan_trader  # noqa: F401
    import engine  # noqa: F401
    problems = []
    # the service imports nothing from the Dash app (app/); if something else in the process
    # already did, it must still be this checkout's
    names = ["alan_trader", "engine"] + [n for n in ("app",) if n in sys.modules]
    for name in names:
        mod = sys.modules[name]
        if not _inside(getattr(mod, "__file__", None), WORKING_COPY):
            problems.append(f"{name} resolves to {getattr(mod, '__file__', None)!r}, not inside {WORKING_COPY}")
    plug = sys.modules.get(PLUGIN_PACKAGE)
    if plug is not None and plugin_dir is not None and not _inside(getattr(plug, "__file__", None), plugin_dir):
        problems.append(f"{PLUGIN_PACKAGE} resolves to {plug.__file__!r}, not {plugin_dir}")
    if problems:
        raise BootstrapError("refusing to start: " + "; ".join(problems))


# ── database write guard (an allow-list) ──────────────────────────────────────
#
# The service is the single writer to AlanStrats, but only to what it owns: the paper ledger the
# Paper views and the runner use, the market-data tables db/sync.py fills, and its own ``app``
# schema (watchlists, alerts, orders). Every statement on every SQLAlchemy engine in the process
# is screened before it reaches the server: each write clause's target table must be on the list,
# and any write the screen cannot attribute to an allowed table (DROP, TRUNCATE, EXEC, SELECT INTO,
# DDL outside ``app`` …) is refused, as before.

#: the paper ledger (paper/ledger.py, engine/positions.py, db/portfolio_client.py's paper paths)
LEDGER_TABLES = frozenset({
    "portfolio.account", "portfolio.balance", "portfolio.position", "portfolio.leg", "portfolio.transaction",
    "portfolio.security", "portfolio.modelsignal", "portfolio.dailymark",
})
#: the market-data tables db/sync.py (and the db/client upserts it calls) write
MARKET_TABLES = frozenset({
    "mkt.ticker", "mkt.pricebar", "mkt.optionsnapshot", "mkt.vixbar", "mkt.macrobar", "mkt.news", "mkt.dividend",
    "mkt.earnings", "mkt.vixfuture", "mkt.fomccalendar", "mkt.treasurybar", "mkt.cpibar", "mkt.minutebar",
    "mkt.optionminutebar", "mkt.optionminutesession", "mkt.eventcalendar", "mkt.synclog",
})
APP_SCHEMA = "app"
DATABASE = "alanstrats"

_WRITE_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE|DENY|"
    r"BULK|RESTORE|BACKUP|DBCC|SP_EXECUTESQL|INTO)\b", re.I)
_SQL_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_SQL_STRING = re.compile(r"'(?:[^']|'')*'")
_IDENT = r'(?:\[[^\]]+\]|"[^"]+"|[A-Za-z_#@][\w$#@]*)'
_QNAME = rf"{_IDENT}(?:\s*\.\s*{_IDENT}){{0,2}}"
_CLAUSES = [
    ("INSERT", re.compile(rf"\bINSERT\s+(?:INTO\s+)?({_QNAME})", re.I)),
    ("UPDATE", re.compile(rf"\bUPDATE\s+({_QNAME})\s+SET\b", re.I)),
    ("DELETE", re.compile(rf"\bDELETE\s+(?:FROM\s+)?({_QNAME})", re.I)),
    ("MERGE", re.compile(rf"\bMERGE\s+(?:INTO\s+)?({_QNAME})", re.I)),
    ("CREATE SCHEMA", re.compile(rf"\bCREATE\s+SCHEMA\s+({_IDENT})", re.I)),
    ("CREATE TABLE", re.compile(rf"\bCREATE\s+TABLE\s+({_QNAME})", re.I)),
    ("CREATE INDEX", re.compile(rf"\bCREATE\s+(?:UNIQUE\s+)?(?:(?:NON)?CLUSTERED\s+)?INDEX\s+{_IDENT}\s+ON\s+({_QNAME})", re.I)),
    ("ALTER TABLE", re.compile(rf"\bALTER\s+TABLE\s+({_QNAME})", re.I)),
]


class ReadOnlyViolation(RuntimeError):
    """The service attempted a statement its write allow-list does not cover (the name is kept
    from the read-only days; routers answer 500 and log it)."""


WriteRefused = ReadOnlyViolation


def _table_name(raw: str) -> str:
    parts = [p.strip().strip("[]").strip('"').lower() for p in re.split(r"\s*\.\s*", raw.strip())]
    if len(parts) == 3:
        if parts[0] != DATABASE:
            return f"{parts[0]}.{parts[1]}.{parts[2]}"      # another database: never allowed
        parts = parts[1:]
    if len(parts) == 1:
        parts = ["dbo", parts[0]]
    return ".".join(parts)


def _allowed(kind: str, table: str) -> bool:
    if kind == "CREATE SCHEMA":
        return table.split(".")[-1] == APP_SCHEMA
    if table.startswith(APP_SCHEMA + "."):
        return True
    if kind in ("CREATE TABLE", "CREATE INDEX", "ALTER TABLE"):
        return False                                       # DDL only in the service's own schema
    return table in LEDGER_TABLES or table in MARKET_TABLES


def write_targets(statement: str) -> list[tuple[str, str]]:
    """[(clause, table)] a statement writes, or raises ReadOnlyViolation for a write the screen
    cannot attribute to a table (DROP, TRUNCATE, EXEC, SELECT … INTO, …)."""
    body = _SQL_STRING.sub("''", _SQL_COMMENT.sub(" ", str(statement)))
    spans, out = [], []
    for kind, rx in _CLAUSES:
        for m in rx.finditer(body):
            spans.append((m.start(), m.end()))
            out.append((kind, _table_name(m.group(1))))
    for m in _WRITE_SQL.finditer(body):
        if not any(a <= m.start() < b for a, b in spans):
            raise ReadOnlyViolation(
                f"refused a {m.group(1).upper()} statement the service's write allow-list does not cover: "
                f"{' '.join(str(statement).split())[:160]}")
    return out


def check_statement(statement: str) -> list[tuple[str, str]]:
    """The allow-list verdict on one statement: its write targets, or ReadOnlyViolation."""
    targets = write_targets(statement)
    for kind, table in targets:
        if not _allowed(kind, table):
            raise ReadOnlyViolation(
                f"refused a {kind} on {table}: not in the service's write allow-list "
                f"(paper ledger, market data, app.*): {' '.join(str(statement).split())[:160]}")
    return targets


def _protected_accounts() -> set[int]:
    """Accounts no statement of this process may write for (ALAN_TRADER_PROTECTED_ACCOUNTS — the
    test suite sets it to the real paper account)."""
    raw = os.environ.get("ALAN_TRADER_PROTECTED_ACCOUNTS", "")
    return {int(x) for x in re.findall(r"\d+", raw)}


def _account_params(context) -> set[int]:
    found: set[int] = set()
    for params in (getattr(context, "compiled_parameters", None) or []):
        for k, v in (params or {}).items():
            key = str(k).lower()
            if key in ("aid", "a") or "account" in key:
                try:
                    found.add(int(v))
                except (TypeError, ValueError):
                    pass
    return found


def _guard(conn, cursor, statement, parameters, context, executemany):
    targets = check_statement(statement)
    protected = _protected_accounts()
    if protected and any(t in LEDGER_TABLES or t.startswith(APP_SCHEMA + ".") for _, t in targets):
        hit = _account_params(context) & protected
        if hit:
            raise ReadOnlyViolation(f"refused a write for protected account {sorted(hit)} "
                                    f"(ALAN_TRADER_PROTECTED_ACCOUNTS): {' '.join(str(statement).split())[:120]}")


def write_allow_list() -> dict:
    return {"ledger": sorted(LEDGER_TABLES), "market_data": sorted(MARKET_TABLES), "schema": f"{APP_SCHEMA}.*",
            "protected_accounts": sorted(_protected_accounts())}


def install_db_read_only_guard() -> bool:
    """Screen every SQL statement on every SQLAlchemy engine in the process against the write
    allow-list (the historical name: it is the service's only DB guard)."""
    if _STATE.get("guard"):
        return True
    try:
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
    except Exception:  # pragma: no cover - sqlalchemy is a hard dependency
        return False
    event.listen(Engine, "before_cursor_execute", _guard)
    _STATE["guard"] = True
    return True


install_db_write_guard = install_db_read_only_guard


def uninstall_db_read_only_guard() -> None:
    """Remove the guard (tests that share a process with DB-writing tests)."""
    if not _STATE.get("guard"):
        return
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    event.remove(Engine, "before_cursor_execute", _guard)
    _STATE["guard"] = False


def db_guard_installed() -> bool:
    return bool(_STATE.get("guard"))


def bootstrap() -> dict:
    """Arrange sys.path, load .env, load the plugin by path and assert where everything
    resolves. Returns what it found. (The service's ``create_app`` also installs the
    DB write guard.)"""
    if _STATE["done"]:
        return _STATE["info"]
    _fix_sys_path()
    if sys.pycache_prefix is None:
        # Never write __pycache__ into the plugin checkout (it is imported read-only).
        sys.pycache_prefix = str(WORKING_COPY / ".pycache")
    from engine.env import load_env
    load_env()                      # <working copy>/.env into os.environ (existing variables win)
    plugin_dir = _load_plugin_by_path()
    _reload_registries()
    _assert_paths(plugin_dir)
    info = {"working_copy": str(WORKING_COPY), "strategies_dir": str(plugin_dir) if plugin_dir else None}
    _STATE.update(done=True, info=info)
    return info
