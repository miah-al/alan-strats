"""
12-Month Momentum (SPY) — own the index when its trailing 12-month return is
positive, cash when negative.

A crash-drawdown overlay validated on 20 years of REAL daily prices through
2008/2020/2022. Measured with the same metric code for both legs (price-return
SPY, 4% cash yield when out):

  12-month Momentum: ~10.0% CAGR at ~0.38 Sharpe and -34% max DD, vs buy-hold's
  ~11.1% CAGR / ~0.38 Sharpe / -55% DD. So the ONLY reproducible benefit is a
  much shallower drawdown; it does NOT beat buy-hold on return or Sharpe.
  Decided monthly; ~1-2 round trips/year.

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
    """1.0 when the trailing N-month return is positive, else 0.0 (cash).

    The decision is made *at* each month-end close (using only data through that
    close) and held until the next month-end. To avoid look-ahead we never trade
    on the decision bar itself: the month-end verdict is forward-filled across the
    following days and then shifted one trading day, so the position on day *d* is
    a function of closes strictly before *d*. Forward-fill only — no bfill.
    """
    m_end = close.resample("ME").last()
    mom   = m_end.pct_change(lookback_months)
    raw   = (mom > 0).astype(float)                      # decided at each month-end close
    daily = raw.reindex(close.index, method="ffill")     # carry the month-end verdict forward
    return daily.shift(1).fillna(0.0)                    # apply next trading day → no look-ahead


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
        "hold cash. A crash-drawdown overlay: on 20y of real prices it cuts max "
        "drawdown from ~-55% to ~-34%, but at ~-1% CAGR and roughly equal Sharpe "
        "(~0.38) vs buy-hold — it does not beat buy-hold on return. Decided monthly."
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
