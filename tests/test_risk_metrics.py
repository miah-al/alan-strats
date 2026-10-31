"""
Tests for risk.metrics — with emphasis on the risk-free-rate treatment.

The 2026-07-03 and 2026-07-11 audits both flagged that Sharpe was charging the
5% risk-free hurdle on every calendar day, including days a strategy held no
position. That made intermittent strategies report Sharpe of -58 / -159, which
is an accounting artifact rather than a statement about risk, and it made the
whole strategy ranking unusable on a risk-adjusted basis.
"""

import numpy as np
import pandas as pd
import pytest

from risk import metrics as rm


TRADING_DAYS = rm.TRADING_DAYS
RF = 0.05
RF_DAILY = RF / TRADING_DAYS


def _flat_then_trade(n_flat: int, trade_returns: list[float]) -> pd.Series:
    """Returns series: `n_flat` idle days, then a handful of real P&L days."""
    return pd.Series([0.0] * n_flat + list(trade_returns))


# ─────────────────────────────────────────────────────────────────────────────
# The bug that was fixed
# ─────────────────────────────────────────────────────────────────────────────

def test_idle_days_do_not_accrue_risk_free_drag():
    """A strategy that never trades has no risk and must not score as ruinous."""
    flat = pd.Series([0.0] * 500)
    assert rm.sharpe_ratio(flat, RF_DAILY) == 0.0


def test_intermittent_strategy_is_not_crushed_by_the_hurdle():
    """
    Two profitable trades over two years of sitting in cash. The old code
    charged -rf on ~500 idle days and returned a Sharpe near -159.
    """
    returns = _flat_then_trade(500, [0.01, 0.012])
    sharpe = rm.sharpe_ratio(returns, RF_DAILY)
    assert sharpe > 0, "profitable intermittent strategy must not score negative"
    assert sharpe < 10, "and must not be absurdly large either"


def test_hurdle_still_charged_on_deployed_days():
    """The risk-free rate is a real hurdle when capital is actually at risk."""
    returns = pd.Series(np.full(TRADING_DAYS, 0.0001) + np.tile([1e-5, -1e-5], TRADING_DAYS // 2))
    with_hurdle = rm.sharpe_ratio(returns, RF_DAILY)
    without = rm.sharpe_ratio(returns, 0.0)
    assert with_hurdle < without, "a fully-deployed strategy must still pay the hurdle"


def test_always_invested_strategy_is_unaffected_by_the_fix():
    """
    Every day is a deployed day, so the new masking is a no-op and the value
    matches the plain textbook computation.
    """
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.normal(0.0005, 0.01, TRADING_DAYS * 2))
    expected_excess = returns - RF_DAILY
    expected = (expected_excess.mean() / expected_excess.std()) * np.sqrt(TRADING_DAYS)
    assert rm.sharpe_ratio(returns, RF_DAILY) == pytest.approx(expected, rel=1e-9)


def test_idle_days_still_dilute_the_ratio():
    """
    Being out of the market shouldn't manufacture a loss, but it also shouldn't
    be free: the same trades spread over more idle days score lower.
    """
    trades = [0.01, -0.004, 0.008, 0.006]
    dense = rm.sharpe_ratio(_flat_then_trade(20, trades), RF_DAILY)
    sparse = rm.sharpe_ratio(_flat_then_trade(400, trades), RF_DAILY)
    assert dense > sparse > 0


def test_explicit_active_mask_overrides_the_zero_return_heuristic():
    """
    A held-but-unmarked position can post an exactly-zero day. Callers that
    know their true exposure can say so.
    """
    returns = pd.Series([0.0, 0.0, 0.01, -0.005] * 50)
    active = pd.Series([True] * len(returns))
    masked = rm.sharpe_ratio(returns, RF_DAILY, active)
    inferred = rm.sharpe_ratio(returns, RF_DAILY)
    assert masked != inferred
    assert masked == pytest.approx(
        ((returns - RF_DAILY).mean() / (returns - RF_DAILY).std()) * np.sqrt(TRADING_DAYS)
    )


def test_sortino_shares_the_deployed_capital_treatment():
    """Sortino had the identical bug — idle days counted as downside."""
    returns = _flat_then_trade(500, [0.01, 0.012])
    assert rm.sortino_ratio(returns, RF_DAILY) > 0


def test_sortino_idle_days_are_not_counted_as_downside():
    flat_with_one_win = _flat_then_trade(200, [0.02])
    excess = rm.excess_returns(flat_with_one_win, RF_DAILY)
    assert (excess < 0).sum() == 0


# ─────────────────────────────────────────────────────────────────────────────
# exposure_pct — the companion that makes Sharpe interpretable
# ─────────────────────────────────────────────────────────────────────────────

def test_exposure_pct_reports_share_of_deployed_days():
    assert rm.exposure_pct(_flat_then_trade(90, [0.01] * 10)) == pytest.approx(10.0)
    assert rm.exposure_pct(pd.Series([0.0] * 50)) == 0.0
    assert rm.exposure_pct(pd.Series([0.01] * 50)) == pytest.approx(100.0)


def test_exposure_pct_empty_series():
    assert rm.exposure_pct(pd.Series(dtype=float)) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# compute_all_metrics wiring
# ─────────────────────────────────────────────────────────────────────────────

def _equity_from_returns(returns: pd.Series, start: float = 100_000.0) -> pd.Series:
    """Rebuild an equity curve whose pct_change() reproduces `returns`."""
    idx = pd.bdate_range("2024-01-01", periods=len(returns) + 1)
    levels = [start] + (start * (1.0 + returns).cumprod()).tolist()
    return pd.Series(levels, index=idx)


def test_compute_all_metrics_exposes_exposure_and_sane_sharpe():
    returns = _flat_then_trade(500, [0.01, 0.012])
    result = rm.compute_all_metrics(_equity_from_returns(returns))
    assert "exposure_pct" in result
    assert 0 <= result["exposure_pct"] <= 100
    assert result["sharpe"] > 0
    assert np.isfinite(result["sharpe"])


def test_compute_all_metrics_keeps_its_existing_keys():
    """Downstream UI columns and PortfolioManager read these by name."""
    rng = np.random.default_rng(1)
    returns = pd.Series(rng.normal(0.0004, 0.009, 300))
    result = rm.compute_all_metrics(_equity_from_returns(returns))
    for key in (
        "total_return_pct", "annualized_return_pct", "sharpe", "sortino",
        "calmar", "max_drawdown_pct", "var_95_pct", "cvar_95_pct",
        "alpha_ann_pct", "beta", "information_ratio", "final_equity",
    ):
        assert key in result, f"missing metric key: {key}"


# ─────────────────────────────────────────────────────────────────────────────
# CAGR must annualize over real elapsed time, not row count
# ─────────────────────────────────────────────────────────────────────────────

def test_sparse_equity_curve_does_not_inflate_cagr():
    """
    A strategy that appends a point per trade (not per day) yields a sparse
    curve. Annualizing by row count treated a 2-year gain as if earned in ten
    weeks and reported 101% CAGR for vrp_premium's real 13.95% total return.
    """
    idx = pd.to_datetime(["2024-04-01", "2025-04-01", "2026-03-31"])
    equity = pd.Series([100_000.0, 106_000.0, 113_950.0], index=idx)

    cagr = rm.annualized_return(equity)
    assert 0.05 < cagr < 0.08, f"expected ~6.8%/yr over 2 real years, got {cagr:.1%}"


def test_dense_and_sparse_curves_agree_on_the_same_period():
    """Same start, end and value — sampling frequency must not change CAGR."""
    dense_idx = pd.bdate_range("2024-01-02", "2026-01-02")
    dense = pd.Series(
        np.linspace(100_000.0, 120_000.0, len(dense_idx)), index=dense_idx
    )
    sparse = dense.iloc[:: len(dense) // 12]
    sparse = pd.concat([sparse, dense.iloc[[-1]]])

    assert rm.annualized_return(sparse) == pytest.approx(
        rm.annualized_return(dense), abs=0.01
    )


def test_elapsed_years_uses_the_datetime_index():
    idx = pd.to_datetime(["2020-01-01", "2024-01-01"])
    assert rm.elapsed_years(pd.Series([1.0, 2.0], index=idx)) == pytest.approx(4.0, abs=0.02)


def test_elapsed_years_falls_back_to_row_count_without_dates():
    """A plain RangeIndex carries no time information — assume daily bars."""
    assert rm.elapsed_years(pd.Series(range(TRADING_DAYS))) == pytest.approx(1.0)


def test_annualized_return_survives_a_wiped_out_account():
    """A curve ending at or below zero must not raise or return a complex number."""
    idx = pd.to_datetime(["2024-01-01", "2026-01-01"])
    assert rm.annualized_return(pd.Series([100_000.0, 0.0], index=idx)) == -1.0
