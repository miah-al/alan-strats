"""
api/config.py — where the service keeps its state and which other checkouts' state it may read.

  service_state_dir()     this checkout's ``paper_state/`` — the directory ``paper.runner`` and the
                          platform's broker ``RequestBudget`` write for processes started from this
                          checkout (the service itself and the runners it manages)
  external_state_dirs()   other checkouts' ``paper_state/`` directories, READ ONLY: a paper runner
                          started elsewhere (the user's own terminal, the main checkout) publishes
                          its sessions, heartbeats and its broker request count there. The service
                          reads them so its broker budget counts the runner's calls and its runner
                          view shows those sessions; it never writes there.

``ALAN_TRADER_EXTERNAL_STATE_DIRS`` (``os.pathsep``-separated) overrides the default, which is the
main checkout's ``paper_state`` when this checkout is a linked git worktree (read from the
``.git`` pointer file; git itself is not run).
"""
from __future__ import annotations

import os
from pathlib import Path

from api.bootstrap import WORKING_COPY


def service_state_dir() -> Path:
    return WORKING_COPY / "paper_state"


def main_checkout() -> Path | None:
    """The main working tree when WORKING_COPY is a linked worktree (``.git`` is a file)."""
    git = WORKING_COPY / ".git"
    if not git.is_file():
        return None
    try:
        line = git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = Path(line.split(":", 1)[1].strip())
    # <main>/.git/worktrees/<name>
    if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        main = gitdir.parent.parent.parent
        return main if main.resolve() != WORKING_COPY.resolve() else None
    return None


def external_state_dirs() -> list[Path]:
    env = os.environ.get("ALAN_TRADER_EXTERNAL_STATE_DIRS")
    if env is not None:
        return [Path(p) for p in env.split(os.pathsep) if p.strip()]
    main = main_checkout()
    if main is not None and (main / "paper_state").is_dir():
        return [main / "paper_state"]
    return []


def paper_account_id() -> int:
    """The paper account the service trades and reads (the runner's ``Paper Account``)."""
    try:
        return int(os.environ.get("ALAN_TRADER_PAPER_ACCOUNT_ID", "") or 0) or _default_account()
    except ValueError:
        return _default_account()


def _default_account() -> int:
    from paper import views
    return int(views._ACCOUNT_ID)
