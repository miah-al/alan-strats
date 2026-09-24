"""Shared test isolation.

The paper provider keeps a day-long count of broker requests in a file shared by every process, so that
a paper session, a streamer and any ad-hoc script cannot each spend the whole daily budget. Tests must
never touch the real one: they would read the live runner's count and fail against their own small caps,
and every request they made would come out of the live session's budget.
"""
import os

import pytest

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


@pytest.fixture(autouse=True)
def _isolated_broker_budget(tmp_path, monkeypatch):
    try:
        import paper.providers as providers
    except Exception:
        yield
        return
    monkeypatch.setattr(providers, "BUDGET_STATE_DIR", str(tmp_path / "budget"))
    yield
