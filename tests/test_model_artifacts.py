"""
Persisted ML artifacts must load, and a bad artifact must never look like a
trading signal.

`saved_models/*.pkl` were pickled under scikit-learn 1.8; under 1.9 the
gradient-boosting loss class moved and 12 of them raised
`ModuleNotFoundError: No module named '_loss'`. `load_model()` let that escape,
`engine/screener.py` catches broadly, and the result was
`score = 0.0, all_pass = False` — a broken model rendered as "no setup today"
for every non-SPY ticker. These tests guard both halves: the artifacts load, and
the failure mode degrades honestly if one ever doesn't.
"""

import pickle
from pathlib import Path

import pytest

from alan_trader.strategies.iron_condor_ai import IronCondorAIStrategy
from alan_trader.strategies.covered_call_ai import CoveredCallAIStrategy


SAVED = Path(__file__).resolve().parents[1] / "saved_models"

# Tickers the AI iron-condor screener scores on the ETF Core universe, plus the
# "default" fallback it drops to when a ticker has no model of its own.
IC_TICKERS = ["spy", "qqq", "iwm", "tlt", "gld", "eem",
              "xlk", "xlf", "xle", "xlv", "default"]


def _pickles():
    return sorted(SAVED.glob("*.pkl"))


def test_saved_models_directory_exists():
    assert SAVED.is_dir(), f"missing {SAVED}"
    assert _pickles(), "no model artifacts found"


@pytest.mark.parametrize("path", _pickles(), ids=lambda p: p.name)
def test_every_persisted_artifact_unpickles(path):
    """A stale artifact is a silent screener failure — see the module docstring."""
    with path.open("rb") as fh:
        obj = pickle.load(fh)
    assert obj is not None


# ── the failure mode must be honest ───────────────────────────────────────────

def test_load_model_returns_false_for_a_missing_ticker():
    assert IronCondorAIStrategy().load_model("definitely_not_a_ticker") is False


def test_load_model_returns_false_and_does_not_raise_on_a_corrupt_artifact(tmp_path,
                                                                          monkeypatch):
    """
    The regression that mattered: a corrupt pickle must degrade to the
    heuristic, not propagate an exception that a broad `except` upstream turns
    into a zero score.
    """
    import alan_trader.strategies.iron_condor_ai as mod

    monkeypatch.setattr(mod, "_SAVED_MODELS_DIR", tmp_path)
    (tmp_path / "iron_condor_ai_broken.pkl").write_bytes(b"not a pickle at all")

    strategy = mod.IronCondorAIStrategy()
    assert strategy.load_model("broken") is False      # must not raise
    assert strategy._model is None


def test_covered_call_load_model_is_equally_defensive(tmp_path, monkeypatch):
    import alan_trader.strategies.covered_call_ai as mod

    monkeypatch.setattr(mod, "_SAVED_MODELS_DIR", tmp_path)
    (tmp_path / "covered_call_ai_BROKEN.pkl").write_bytes(b"\x80\x04garbage")

    strategy = mod.CoveredCallAIStrategy()
    assert strategy.load_model("BROKEN") is False
    assert strategy._model is None


# ── the artifacts the screener actually reaches for ───────────────────────────

@pytest.mark.parametrize("ticker", IC_TICKERS)
def test_iron_condor_ai_model_loads_for_every_screened_ticker(ticker):
    strategy = IronCondorAIStrategy()
    assert strategy.load_model(ticker) is True, (
        f"iron_condor_ai has no loadable model for {ticker!r}; the screener "
        f"would score it 0.0 and present it as 'no setup'"
    )
    assert strategy._model is not None


@pytest.mark.parametrize("ticker", IC_TICKERS)
def test_loaded_model_can_actually_predict(ticker):
    """Loading is not enough — a model that cannot predict is still broken."""
    strategy = IronCondorAIStrategy()
    assert strategy.load_model(ticker)
    model = strategy._model
    assert hasattr(model, "predict_proba")

    n_features = getattr(model, "n_features_in_", None)
    if n_features:
        import numpy as np

        probs = model.predict_proba(np.zeros((1, int(n_features))))
        assert probs.shape[0] == 1
        assert 0.0 <= float(probs[0][-1]) <= 1.0


def test_covered_call_ai_model_loads():
    strategy = CoveredCallAIStrategy()
    assert strategy.load_model("SPY") is True
    assert strategy._model is not None
