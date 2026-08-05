"""
Risk and performance metrics.
Single source of truth — used by BacktestEngine, strategies, portfolio manager, and dashboard.
All functions are stateless and accept pandas Series.
"""

from typing import Optional
import numpy as np
import pandas as pd
from scipy import stats


TRADING_DAYS = 252


# ─────────────────────────────────────────────────────────────────────────────
# Core metrics
# ─────────────────────────────────────────────────────────────────────────────

def deployed_mask(returns: pd.Series) -> pd.Series:
    """
    Boolean mask of days on which capital was actually at risk.

    Backtest equity curves do not credit interest on idle cash, so a day with
    exactly zero P&L is a day the strategy was flat (or held an unmarked
    position). Either way the risk-free hurdle must not be charged against it —
    see `excess_returns`.
    """
    return returns != 0.0


def excess_returns(
    returns: pd.Series,
    risk_free_daily: float = 0.0,
    active: Optional[pd.Series] = None,
) -> pd.Series:
    """
    Returns in excess of the risk-free rate, charging the hurdle **only on days
    capital was deployed**.

    A backtest equity curve holds idle cash at 0%, whereas a real account earns
    the risk-free rate on it. Subtracting `risk_free_daily` from every calendar
    day therefore invents a drag that the strategy never actually suffered: a
    strategy flat 95% of the time accrues ~-rf on those days and reports a
    hugely negative Sharpe that reflects the accounting, not its risk. Treating
    an idle day as earning the risk-free rate makes its excess return zero,
    which is both the economically correct statement and the one that keeps
    intermittent and always-invested strategies comparable.

    Days the strategy *is* deployed are charged the hurdle as normal.
    """
    if active is None:
        active = deployed_mask(returns)
    return (returns - risk_free_daily).where(active, 0.0)


def sharpe_ratio(
    returns: pd.Series,
    risk_free_daily: float = 0.0,
    active: Optional[pd.Series] = None,
) -> float:
    """
    Annualized Sharpe ratio, measured on deployed capital.

    The risk-free hurdle is applied only to days the strategy held risk; idle
    days contribute zero excess return rather than a spurious -rf. Idle days
    are still counted in the sample, so being out of the market genuinely
    dilutes the ratio — it just no longer manufactures a loss.
    """
    if returns.empty:
        return 0.0
    excess = excess_returns(returns, risk_free_daily, active)
    std = excess.std()
    if std < 1e-10:
        return 0.0
    return float((excess.mean() / std) * np.sqrt(TRADING_DAYS))


def sortino_ratio(
    returns: pd.Series,
    risk_free_daily: float = 0.0,
    active: Optional[pd.Series] = None,
) -> float:
    """Annualized Sortino ratio (uses downside deviation). See `sharpe_ratio`."""
    if returns.empty:
        return 0.0
    excess = excess_returns(returns, risk_free_daily, active)
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return float((excess.mean() / downside.std()) * np.sqrt(TRADING_DAYS))


def exposure_pct(returns: pd.Series) -> float:
    """
    Share of days (0–100) on which capital was deployed.

    Companion to Sharpe: a 1.5 Sharpe at 8% exposure and a 1.5 Sharpe at 100%
    exposure are very different propositions.
    """
    if returns.empty:
        return 0.0
    return float(deployed_mask(returns).mean() * 100)


def calmar_ratio(equity_curve: pd.Series) -> float:
    """Annualized return / |max drawdown|. Higher = better."""
    ann_ret = annualized_return(equity_curve)
    mdd = abs(max_drawdown(equity_curve))
    if mdd == 0:
        return float("inf") if ann_ret > 0 else 0.0
    return float(ann_ret / mdd)


def max_drawdown(equity_curve: pd.Series) -> float:
    """Maximum peak-to-trough loss as a fraction (negative). e.g. -0.15 = -15%"""
    if equity_curve.empty:
        return 0.0
    roll_max = equity_curve.cummax()
    dd = (equity_curve - roll_max) / roll_max
    return float(dd.min())


def elapsed_years(equity_curve: pd.Series) -> float:
    """
    Calendar years spanned by an equity curve.

    Prefer the real elapsed time from a DatetimeIndex over `len / 252`. Row
    count only equals elapsed time for a dense daily curve; strategies that
    append a point per trade (or only on days their data exists) produce a
    sparse curve, and counting rows then radically understates the period. That
    understatement is not cosmetic — it inflates CAGR: a 13.95% gain over two
    real years across 47 sparse rows annualizes to 101% instead of 6.8%.
    """
    idx = getattr(equity_curve, "index", None)
    if isinstance(idx, pd.DatetimeIndex) and len(idx) >= 2:
        days = (idx.max() - idx.min()).days
        if days > 0:
            return days / 365.25
    return len(equity_curve) / TRADING_DAYS


def annualized_return(equity_curve: pd.Series) -> float:
    """CAGR from equity curve, annualized over real elapsed time."""
    if len(equity_curve) < 2 or equity_curve.iloc[0] == 0:
        return 0.0
    years = elapsed_years(equity_curve)
    if years <= 0:
        return 0.0
    total = equity_curve.iloc[-1] / equity_curve.iloc[0]
    if total <= 0:
        return -1.0
    return float(total ** (1 / years) - 1)


def total_return(equity_curve: pd.Series) -> float:
    """Total return as fraction. e.g. 0.15 = 15%"""
    if equity_curve.empty or equity_curve.iloc[0] == 0:
        return 0.0
    return float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1)


# ─────────────────────────────────────────────────────────────────────────────
# Market-relative metrics
# ─────────────────────────────────────────────────────────────────────────────

def alpha_beta(
    returns: pd.Series,
    benchmark_returns: pd.Series,
) -> tuple[float, float]:
    """
    OLS: returns = alpha + beta * benchmark.
    Returns (alpha_annualized, beta).
    """
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 5:
        return 0.0, 1.0
    y = aligned.iloc[:, 0].values
    x = aligned.iloc[:, 1].values
    slope, intercept, *_ = stats.linregress(x, y)
    alpha_ann = float(intercept * TRADING_DAYS)
    return alpha_ann, float(slope)


def information_ratio(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """IR = (mean active return) / tracking error."""
    active = returns - benchmark_returns
    te = active.std()
    if te == 0:
        return 0.0
    return float((active.mean() / te) * np.sqrt(TRADING_DAYS))


# ─────────────────────────────────────────────────────────────────────────────
# Tail risk
# ─────────────────────────────────────────────────────────────────────────────

def value_at_risk(returns: pd.Series, confidence: float = 0.95) -> float:
    """
    Historical VaR at given confidence.
    Returns a negative number representing potential loss.
    e.g. -0.02 = could lose 2% in a bad day.
    """
    if returns.empty:
        return 0.0
    return float(np.percentile(returns, (1 - confidence) * 100))


def conditional_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """CVaR / Expected Shortfall: mean of the worst (1-confidence) returns."""
    var = value_at_risk(returns, confidence)
    tail = returns[returns <= var]
    if tail.empty:
        return var
    return float(tail.mean())


# ─────────────────────────────────────────────────────────────────────────────
# Trade-level stats
# ─────────────────────────────────────────────────────────────────────────────

def trade_stats(trades_df: pd.DataFrame) -> dict:
    """Given a trades DataFrame with a 'pnl' column, return win/loss stats."""
    if trades_df.empty or "pnl" not in trades_df.columns:
        return {"win_rate_pct": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "profit_factor": 0.0, "num_trades": 0}
    wins   = trades_df[trades_df["pnl"] > 0]["pnl"]
    losses = trades_df[trades_df["pnl"] < 0]["pnl"]
    win_rate = len(wins) / len(trades_df) * 100 if len(trades_df) else 0.0
    avg_win  = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    pf = abs(wins.sum() / losses.sum()) if len(losses) > 0 and losses.sum() != 0 else float("inf")
    return {
        "win_rate_pct": round(win_rate, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(pf, 3),
        "num_trades": len(trades_df),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Rolling metrics
# ─────────────────────────────────────────────────────────────────────────────

def rolling_sharpe(returns: pd.Series, window: int = 60) -> pd.Series:
    rm = returns.rolling(window).mean()
    rs = returns.rolling(window).std()
    result = (rm / rs.replace(0, np.nan)) * np.sqrt(TRADING_DAYS)
    return result.rename(f"sharpe_{window}d")


def rolling_sortino(returns: pd.Series, window: int = 60) -> pd.Series:
    def _sortino(r):
        r = r[~np.isnan(r)]
        if len(r) < 2:
            return np.nan
        d = r[r < 0]
        if len(d) == 0 or d.std() == 0:
            return np.nan
        return (r.mean() / d.std()) * np.sqrt(TRADING_DAYS)
    return returns.rolling(window, min_periods=2).apply(_sortino, raw=True).rename(f"sortino_{window}d")


def rolling_max_drawdown(equity_curve: pd.Series, window: int = 60) -> pd.Series:
    def _mdd(eq):
        eq = eq[~np.isnan(eq)]
        if len(eq) < 2:
            return np.nan
        rm = np.maximum.accumulate(eq)
        dd = (eq - rm) / np.where(rm == 0, np.nan, rm)
        return np.nanmin(dd)
    return equity_curve.rolling(window, min_periods=2).apply(_mdd, raw=True).rename(f"mdd_{window}d")


# ─────────────────────────────────────────────────────────────────────────────
# Composite
# ─────────────────────────────────────────────────────────────────────────────

def compute_all_metrics(
    equity_curve: pd.Series,
    trades_df: Optional[pd.DataFrame] = None,
    benchmark_returns: Optional[pd.Series] = None,
    risk_free_annual: float = 0.05,
) -> dict:
    """
    Compute the full suite of metrics from an equity curve.
    Returns a flat dict suitable for dashboard metric cards.
    """
    returns = equity_curve.pct_change().dropna()
    rf_daily = risk_free_annual / TRADING_DAYS
    active = deployed_mask(returns)

    alpha, beta = (0.0, 1.0)
    ir = 0.0
    if benchmark_returns is not None and not benchmark_returns.empty:
        alpha, beta = alpha_beta(returns, benchmark_returns)
        ir = information_ratio(returns, benchmark_returns)

    result = {
        "total_return_pct":      round(total_return(equity_curve) * 100, 2),
        "annualized_return_pct": round(annualized_return(equity_curve) * 100, 2),
        "sharpe":                round(sharpe_ratio(returns, rf_daily, active), 3),
        "sortino":               round(sortino_ratio(returns, rf_daily, active), 3),
        "calmar":                round(calmar_ratio(equity_curve), 3),
        "exposure_pct":          round(exposure_pct(returns), 2),
        "max_drawdown_pct":      round(max_drawdown(equity_curve) * 100, 2),
        "var_95_pct":            round(value_at_risk(returns, 0.95) * 100, 3),
        "cvar_95_pct":           round(conditional_var(returns, 0.95) * 100, 3),
        "alpha_ann_pct":         round(alpha * 100, 3),
        "beta":                  round(beta, 3),
        "information_ratio":     round(ir, 3),
        "final_equity":          round(float(equity_curve.iloc[-1]), 2),
    }

    if trades_df is not None:
        result.update(trade_stats(trades_df))

    return result
