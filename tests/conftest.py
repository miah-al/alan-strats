"""Shared test isolation.

The paper provider keeps a day-long count of broker requests in a file shared by every process, so that
a paper session, a streamer and any ad-hoc script cannot each spend the whole daily budget. Tests must
never touch the real one: they would read the live runner's count and fail against their own small caps,
and every request they made would come out of the live session's budget.

The same goes for the runner's diary (logs/paper/<strategy>_<date>.log): a test that runs the runner
script's main() attached it to the root logger, and every later test's warnings, simulated halts included,
landed in the live session's diary and from there in the committed day archive.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_broker_budget(tmp_path, monkeypatch):
    try:
        import paper.providers as providers
        monkeypatch.setattr(providers, "BUDGET_STATE_DIR", str(tmp_path / "budget"))
    except Exception:
        pass
    try:
        import scripts.paper_runner as runner_script
        monkeypatch.setattr(runner_script, "DIARY_DIR", tmp_path / "diary")
    except Exception:
        pass
    yield
