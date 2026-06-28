"""
12-Month Momentum (SPY) — own the index when its trailing 12-month return is
positive, cash when negative.

One of two strategies in this repo with an edge validated on 20 years of REAL
daily prices through 2008/2020/2022:

  12-month Momentum: 10.8% CAGR (matches buy-hold) at 0.63 Sharpe and -34% max DD
  vs -55%. Decided monthly; ~1-2 round trips/year.

"Time-series (absolute) momentum" — documented across decades and asset classes.
Shared timing machinery lives in timing_base.py; this file holds only the
momentum rule + Strategy class.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult, StrategyType, StrategyStatus,
)
from alan_trader.strategies.timing_base import (
    load_close, equity_from_position, episodes_to_trades, close_from_inputs,
)
from alan_trader.risk.metrics import compute_all_metrics


def tsmom_position(close: pd.Series, lookback_months: int = 12) -> pd.Series:
    """1.0 when the trailing N-month return is positive, else 0.0 (cash). Decided
    at each month-end, applied the following month (no look-ahead)."""
    m_end = close.resample("ME").last()
    mom   = m_end.pct_change(lookback_months)
    sig   = (mom > 0).shift(1, fill_value=False).astype(float)
    return sig.reindex(close.index, method="ffill").fillna(0.0)


def current_tsmom_signal(close: pd.Series, lookback_months: int = 12) -> dict:
    """Today's IN/OUT verdict for the momentum strategy."""
    if close.empty or len(close) < lookback_months * 21 + 1:
        return {"signal": "UNKNOWN", "detail": "insufficient history"}
    m_end = close.resample("ME").last()
    ret = float(m_end.pct_change(lookback_months).iloc[-1])
    long_ = ret > 0
    return {
        "signal":           "BUY" if long_ else "HOLD",
        "state":            "IN (long)" if long_ else "OUT (cash)",
        "price":            round(float(close.iloc[-1]), 2),
        "ret_lookback_pct": round(ret * 100.0, 2),
        "asof":             close.index[-1].date().isoformat(),
        "rule":             f"{lookback_months}-month return sign",
    }


class TSMomentumStrategy(BaseStrategy):
    name          = "ts_momentum"
    display_name  = "12-Month Momentum (SPY)"
    strategy_type = StrategyType.RULE_BASED
    status        = StrategyStatus.ACTIVE
    description   = (
        "Own the index when its trailing 12-month return is positive; otherwise "
        "hold cash. Validated on 20y of real prices: 10.8% CAGR (matches buy-hold) "
        "at 0.63 Sharpe and only -34% max drawdown vs -55%. Decided monthly."
    )
    asset_class          = "equities"
    typical_holding_days = 180

    def __init__(self, lookback_months: int = 12, cash_yield: float = 0.04,
                 ticker: str = "SPY"):
        self.lookback_months = lookback_months
        self.cash_yield      = cash_yield
        self.ticker          = ticker

    def get_params(self) -> dict:
        return {"lookback_months": self.lookback_months,
                "cash_yield": self.cash_yield, "ticker": self.ticker}

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "lookback_months", "label": "Lookback (months)", "type": "slider",
             "min": 3, "max": 12, "default": 12, "step": 1, "col": 0, "row": 0,
             "help": "Momentum window. 12 months is the canonical choice."},
            {"key": "cash_yield", "label": "Cash yield (annual)", "type": "slider",
             "min": 0.0, "max": 0.06, "default": 0.04, "step": 0.01, "col": 1, "row": 0},
        ]

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        close = market_snapshot.get("close")
        if close is None or (hasattr(close, "empty") and close.empty):
            close = load_close(market_snapshot.get("ticker", self.ticker))
        sig = current_tsmom_signal(close, self.lookback_months)
        is_buy = sig.get("signal") == "BUY"
        return SignalResult(self.name, sig.get("signal", "HOLD"),
                            confidence=1.0 if is_buy else 0.0,
                            position_size_pct=1.0 if is_buy else 0.0,
                            metadata=sig)

    def backtest(self, price_data: pd.DataFrame, auxiliary_data: dict,
                 starting_capital: float = 10_000, lookback_months: Optional[int] = None,
                 cash_yield: Optional[float] = None, **kwargs) -> BacktestResult:
        lb = lookback_months if lookback_months is not None else self.lookback_months
        cy = cash_yield if cash_yield is not None else self.cash_yield
        ticker = (auxiliary_data or {}).get("ticker", self.ticker)
        close = close_from_inputs(price_data, ticker)
        if close.empty:
            raise ValueError(f"No price data for {ticker}.")
        pos = tsmom_position(close, lb)
        eq  = equity_from_position(close, pos, cy, starting_capital)
        trades = episodes_to_trades(close, pos)
        metrics = compute_all_metrics(eq, trades if not trades.empty else None)
        bh = starting_capital * (1 + close.pct_change().fillna(0)).cumprod()
        return BacktestResult(self.name, eq, eq.pct_change().dropna(), trades, metrics,
                              params={"lookback_months": lb, "cash_yield": cy, "ticker": ticker},
                              extra={"benchmark_equity": bh,
                                     "current": current_tsmom_signal(close, lb)})
