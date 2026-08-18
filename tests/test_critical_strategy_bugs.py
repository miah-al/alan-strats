"""
Regression tests for the four CRITICAL defects found in the 2026-08-01 edge
review. Each one produced plausible-looking output while being wrong, which is
why they survived: none of them crashed.
"""

import numpy as np
import pandas as pd
import pytest


# ── 1. vol_calendar_spread: cost floor became the sizing denominator ──────────

def test_degenerate_calendar_is_rejected_not_floored():
    """
    A calendar whose legs price to nearly the same value has no economics left.
    The old code clamped `cost` up to $0.01/share, and that floor then became
    the DENOMINATOR of the position sizer: $1.00 cost + $1.30 commission sized
    100_000 * 0.05 / 2.30 = 2,173 contracts on a $100k account.
    """
    from alan_trader.strategies import vol_calendar_spread as m

    assert m._MIN_NET_PER_SHARE > 0.01, (
        "the minimum tradeable premium must exceed the old $0.01 clamp"
    )
    assert m._MAX_CONTRACTS <= 100, "a contract ceiling must bound the sizer"

    # The pathological sizing the floor used to permit.
    capital, pos_pct, commission = 100_000.0, 0.05, 1.30
    floored_cost = 0.01 * 100
    old_contracts = int(capital * pos_pct / max(floored_cost + commission, 1))
    assert old_contracts > 2000, "sanity: this is the bug being guarded against"
    assert min(old_contracts, m._MAX_CONTRACTS) <= m._MAX_CONTRACTS


def test_calendar_cost_floor_is_gone_from_source():
    import inspect
    from alan_trader.strategies import vol_calendar_spread as m

    src = inspect.getsource(m)
    assert "max(0.01," not in src, (
        "a max(0.01, ...) premium clamp is back; it silently converts an "
        "unpriceable spread into a near-zero-cost one"
    )


# ── 2. short_squeeze_detector: option debit charged twice ────────────────────

def test_closing_a_long_call_returns_its_value_not_its_pnl():
    """
    Entry debits the full premium from cash. If the exit credits only the P&L,
    the principal is destroyed every round trip — a call that DOUBLES still
    books a net capital loss.
    """
    import inspect
    from alan_trader.strategies import short_squeeze_detector as m

    src = inspect.getsource(m.ShortSqueezeDetectorStrategy.backtest)
    assert "capital  += cur_prem * trade[\"contracts\"] * 100 - exit_cost" in src, (
        "exit must credit the option's market value, not net_pnl"
    )

    # The arithmetic the fix restores.
    premium, contracts, leg_cost = 5.00, 1, 5.65
    start = 100_000.0
    cash_after_entry = start - (premium * contracts * 100 + leg_cost)
    exit_prem = 10.00                                   # the call doubles
    wrong = cash_after_entry + ((exit_prem - premium) * contracts * 100 - leg_cost)
    right = cash_after_entry + (exit_prem * contracts * 100 - leg_cost)
    assert wrong < start, "the old formula lost money on a doubling call"
    assert right > start, "the corrected formula must profit"
    assert right - wrong == pytest.approx(premium * contracts * 100)


# ── 3. rs_credit_spread: entry and mark priced on different horizons ─────────

def test_entry_and_mark_share_one_time_base():
    """
    The spread was written at dte_target (21d) but marked at hold_days (10d),
    handing every trade an instant block of unearned theta. That artifact was
    the strategy's entire apparent frictionless edge.
    """
    import inspect
    from alan_trader.strategies import rs_credit_spread as m

    src = inspect.getsource(m.RSCreditSpreadStrategy.backtest)
    assert "max(0, h_days - trade[\"days_held\"])" not in src
    assert "max(0, h_days - ot[\"days_held\"])" not in src
    assert "dte_tgt - trade[\"days_held\"]" in src
    assert "dte_tgt - ot[\"days_held\"]" in src


# ── 4. earnings_pin_risk: degenerate classifier asserted certainty ───────────

def test_single_class_stub_is_never_certain():
    from alan_trader.strategies.earnings_pin_risk import _ConstantClassifier

    for n in (1, 4, 6, 20, 100):
        p = _ConstantClassifier(1, 8, n_samples=n).predict_proba(np.zeros((1, 8)))[0][1]
        assert 0.0 < p < 1.0, f"n={n} produced certainty: {p}"
        q = _ConstantClassifier(0, 8, n_samples=n).predict_proba(np.zeros((1, 8)))[0][1]
        assert 0.0 < q < 1.0, f"n={n} produced certainty: {q}"


def test_more_evidence_moves_the_estimate_toward_certainty():
    from alan_trader.strategies.earnings_pin_risk import _ConstantClassifier

    probs = [_ConstantClassifier(1, 8, n_samples=n).predict_proba(np.zeros((1, 8)))[0][1]
             for n in (1, 5, 25, 200)]
    assert probs == sorted(probs), "more single-class evidence must not lower P"
    assert probs[0] < 0.75, "one observation must not imply near-certainty"


def test_legacy_artifact_certainty_is_repaired_on_load():
    """Old pickles stored _p as exactly 1.0; __setstate__ must defuse that."""
    import pickle
    from alan_trader.strategies.earnings_pin_risk import _ConstantClassifier

    legacy = _ConstantClassifier(1, 8, n_samples=4)
    legacy.__dict__["_p"] = 1.0            # simulate the pre-fix artifact
    restored = pickle.loads(pickle.dumps(legacy))
    p = restored.predict_proba(np.zeros((1, 8)))[0][1]
    assert p < 1.0, "legacy certainty survived unpickling"
    assert getattr(restored, "_legacy_repaired", False) is True


def test_single_class_training_requires_real_evidence():
    from alan_trader.strategies import earnings_pin_risk as m

    assert m._MIN_SINGLE_CLASS_EVENTS >= 20, (
        "a single-class fit of a handful of events must not authorise trading"
    )


def test_stub_advertises_that_it_is_degenerate():
    from alan_trader.strategies.earnings_pin_risk import _ConstantClassifier

    assert _ConstantClassifier(1, 8, n_samples=10).degenerate is True


# ── 5. hmm_regime: a fixed confidence floor on a long-horizon forecast ───────

def test_confidence_floor_is_applied_to_the_spot_posterior():
    """
    `expected_posterior` projects the chain ~22 bars ahead. As the fitted
    transition matrix grows more diffuse, that projection converges toward the
    stationary distribution, whose maximum is ~1/3-0.5 for three states. A fixed
    0.60 floor on it is therefore guaranteed to stop passing as data
    accumulates — and it did: the strategy took its last entry 2025-07-17 and
    then sat out 348 days to the end of the sample.

    The floor belongs on the spot posterior ("how sure am I of the regime NOW");
    the forward posterior is still used for the argmax agreement check, which is
    scale-free.
    """
    import inspect
    from alan_trader.strategies import hmm_regime as m

    src = inspect.getsource(m.HMMRegimeStrategy.backtest)
    assert 'float(np.max(posterior)) >= p["regime_confidence_min"]' in src
    assert 'float(np.max(gating_post)) >= p["regime_confidence_min"]' not in src, (
        "the confidence floor is back on the forward posterior; it will decay "
        "below the floor and switch the strategy off permanently"
    )
    # The argmax stability check must survive — it is the point of the forward view.
    assert 'int(np.argmax(gating_post)) == int(np.argmax(posterior))' in src


def test_hmm_entry_does_not_depend_on_total_series_length():
    """
    `(n - i) > max(dte...)` refuses entries near the end of the sample, which
    makes a trade's existence depend on how much future data happens to exist —
    the same look-ahead already removed from iron_condor_rules.
    """
    import inspect
    from alan_trader.strategies import hmm_regime as m

    src = inspect.getsource(m.HMMRegimeStrategy.backtest)
    assert '(n - i) > max(p["dte_bull_put"]' not in src


# ── 6. iron_condor_rules: the concurrency cap was never enforced ─────────────

def test_max_concurrent_is_actually_enforced():
    """
    `max_conc` was resolved from the UI slider and never read. Measured peak
    concurrency was 21 simultaneous condors against a documented cap of 5 — the
    headline 4.33% CAGR was unbounded leverage, not skill (2.79% once capped).
    """
    import inspect
    from alan_trader.strategies import iron_condor_rules as m

    src = inspect.getsource(m.IronCondorRulesStrategy.backtest)
    assert "len(open_trades) < max_conc" in src, "the concurrency cap is dead again"


# ── 7. iron_condor_ai: look-ahead + production-model mutation ────────────────

def test_iron_condor_ai_has_no_series_length_lookahead():
    import inspect
    from alan_trader.strategies import iron_condor_ai as m

    src = inspect.getsource(m.IronCondorAIStrategy.backtest)
    assert "(n - i) > dte_tgt" not in src
    assert "min(i + dte_tgt, n - 1)" not in src, (
        "clamping expiry to the sample end makes marks depend on future data"
    )


def test_backtest_does_not_overwrite_the_live_model_artifact():
    """
    `backtest()` used to call save_model(), so any Backtest/Performance tab run
    silently replaced saved_models/iron_condor_ai_<ticker>.pkl — the artifact
    engine/screener.py scores live trades with. Persisting must be explicit.
    """
    import inspect
    from alan_trader.strategies import iron_condor_ai as m

    src = inspect.getsource(m.IronCondorAIStrategy.backtest)
    # Strip whole comment lines — the explanatory note in the source mentions
    # save_model by name, which a naive substring check would trip on.
    code = chr(10).join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "save_model" not in code, (
        "backtest() persists a model again; an exploratory run must not mutate "
        "production model state"
    )


# ── 8. Backtest and Performance tabs must agree ─────────────────────────────

def test_backtest_tab_uses_the_same_warmup_as_performance():
    """
    The warm-up fix reached rank_strategies.py and performance.py but not
    backtest_view.py, so the two tabs disagreed on identical inputs
    (ts_momentum 12.05% vs 15.20% CAGR; vix_term_structure flipped sign).
    """
    from alan_trader.app.pages.strategies import backtest_view as bv
    from alan_trader.app.pages.strategies import performance as perf

    assert bv._WARMUP_DAYS == perf.WARMUP_DAYS, (
        f"warm-up differs: backtest_view={bv._WARMUP_DAYS} vs "
        f"performance={perf.WARMUP_DAYS}"
    )
