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

def sharpe_ratio(returns: pd.Series, risk_free_daily: float = 0.0) -> float:
    """Annualized Sharpe ratio."""
    excess = returns - risk_free_daily
    if excess.std() == 0:
        return 0.0
    return float((excess.mean() / excess.std()) * np.sqrt(TRADING_DAYS))


def sortino_ratio(returns: pd.Series, risk_free_daily: float = 0.0) -> float:
    """Annualized Sortino ratio (uses downside deviation)."""
    excess = returns - risk_free_daily
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return float((excess.mean() / downside.std()) * np.sqrt(TRADING_DAYS))


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


def annualized_return(equity_curve: pd.Series) -> float:
    """CAGR from equity curve."""
    if len(equity_curve) < 2 or equity_curve.iloc[0] == 0:
        return 0.0
    years = len(equity_curve) / TRADING_DAYS
    total = equity_curve.iloc[-1] / equity_curve.iloc[0]
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
    pf = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
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

    alpha, beta = (0.0, 1.0)
    ir = 0.0
    if benchmark_returns is not None and not benchmark_returns.empty:
        alpha, beta = alpha_beta(returns, benchmark_returns)
        ir = information_ratio(returns, benchmark_returns)

    result = {
        "total_return_pct":      round(total_return(equity_curve) * 100, 2),
        "annualized_return_pct": round(annualized_return(equity_curve) * 100, 2),
        "sharpe":                round(sharpe_ratio(returns, rf_daily), 3),
        "sortino":               round(sortino_ratio(returns, rf_daily), 3),
        "calmar":                round(calmar_ratio(equity_curve), 3),
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
