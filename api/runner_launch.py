"""
python -m api.runner_launch <paper_runner arguments> — how the service starts a paper runner.

The runner script puts this checkout and its parent on sys.path, which in a worktree is not where
the strategy plugin lives. This launcher first runs the service's own bootstrap — the plugin loaded
by file path, no foreign ``alan_trader`` on the path, bytecode kept out of the plugin checkout — and
then hands the arguments to ``scripts.paper_runner.main`` unchanged.
"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    from api.bootstrap import BootstrapError, bootstrap
    try:
        bootstrap()
    except BootstrapError as exc:
        print(f"paper runner: {exc}", file=sys.stderr)
        return 2
    from scripts.paper_runner import main as run
    return int(run(argv if argv is not None else sys.argv[1:]) or 0)


if __name__ == "__main__":
    sys.exit(main())
