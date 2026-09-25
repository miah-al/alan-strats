"""Shared test isolation.

The paper provider keeps a day-long count of broker requests in a file shared by every process, so that
a paper session, a streamer and any ad-hoc script cannot each spend the whole daily budget. Tests must
never touch the real one: they would read the live runner's count and fail against their own small caps,
and every request they made would come out of the live session's budget.
"""
import os
import sys
from pathlib import Path

import pytest

# The platform is ``alan_trader`` by file path, whatever this checkout's folder is called (api/bootstrap.py). Bind it
# before any test module imports ``alan_trader.*``: pytest puts the checkout's parent on sys.path, and beside the
# live checkout that name would otherwise resolve to the live code.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from api.bootstrap import register_platform_package  # noqa: E402

register_platform_package()

# The service's market-data hub starts no live provider under test (no DXLink stream, no polling):
# hub tests inject fakes. A developer who really wants live providers sets the variable explicitly.
os.environ.setdefault("ALAN_TRADER_PROVIDERS", "none")
# The runner's real paper account (AccountId 1): the service's DB guard refuses any ledger / app write
# for it while the suite runs. Service tests trade a throwaway account of their own and delete it.
os.environ.setdefault("ALAN_TRADER_PROTECTED_ACCOUNTS", "1")
# Backtest jobs run under test do not leave app.BacktestRun rows behind.
os.environ.setdefault("ALAN_TRADER_STORE_BACKTESTS", "0")
# ... and no live GEX is recorded into app.GexHistory.
os.environ.setdefault("ALAN_TRADER_GEX_RECORD", "0")
os.environ.setdefault("ALAN_TRADER_QUOTE_RECORD", "0")
# ... no nightly daily-bars sync, and no bar top-ups (a GET must not reach yfinance or write bars under test).
os.environ.setdefault("ALAN_TRADER_NIGHTLY_SYNC", "0")
os.environ.setdefault("ALAN_TRADER_BARS_TOPUP", "0")
# ... arms live in memory only and nothing is ever started on a schedule (a test must never launch a paper run).
os.environ.setdefault("ALAN_TRADER_ARMS", "memory")
os.environ.setdefault("ALAN_TRADER_ARM_SCHEDULER", "0")


@pytest.fixture(autouse=True)
def _isolated_broker_budget(tmp_path, monkeypatch):
    try:
        import paper.providers as providers
    except Exception:
        yield
        return
    monkeypatch.setattr(providers, "BUDGET_STATE_DIR", str(tmp_path / "budget"))
    yield
