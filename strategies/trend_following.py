"""
200-Day Trend (SPY) — own the index above its moving average, cash below.

One of two strategies in this repo with an edge validated on 20 years of REAL
daily prices through 2008/2020/2022. The edge is RISK-ADJUSTED, not excess return:

  200-day Trend: ~9% CAGR, 0.64 Sharpe, -20% max DD (vs -55% buy-hold; -5.6% in 2008).

Single, un-optimised rule (the 200-day average) — the opposite of the curve-fit,
flat-vol options backtests elsewhere in this repo. Shared timing machinery lives
in timing_base.py; this file holds only the trend rule + Strategy class.

Signal convention: BUY = be long the underlying; HOLD = sit in cash.
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


def trend_position(close: pd.Series, ma_window: int = 200) -> pd.Series:
    """1.0 when close > its moving average (long), else 0.0 (cash). Shifted one
    day so today's position uses only data through yesterday's close."""
    ma = close.rolling(ma_window).mean()
    return (close > ma).shift(1, fill_value=False).astype(float)


def current_trend_signal(close: pd.Series, ma_window: int = 200) -> dict:
    """Today's IN/OUT verdict for the trend strategy."""
    if close.empty or len(close) < ma_window + 1:
        return {"signal": "UNKNOWN", "detail": "insufficient history"}
    ma = float(close.rolling(ma_window).mean().iloc[-1])
    px = float(close.iloc[-1])
    long_ = px > ma
    return {
        "signal":    "BUY" if long_ else "HOLD",   # BUY=long index, HOLD=cash
        "state":     "IN (long)" if long_ else "OUT (cash)",
        "price":     round(px, 2),
        "ma":        round(ma, 2),
        "pct_vs_ma": round((px / ma - 1.0) * 100.0, 2),
        "asof":      close.index[-1].date().isoformat(),
        "rule":      f"{ma_window}-day moving average",
    }


class TrendFollowingStrategy(BaseStrategy):
    name          = "trend_following"
    display_name  = "200-Day Trend (SPY)"
    strategy_type = StrategyType.RULE_BASED
    status        = StrategyStatus.ACTIVE
    description   = (
        "Own the index while it trades above its 200-day moving average; move to "
        "cash when it drops below. Validated on 20y of real prices: ~9% CAGR, "
        "0.64 Sharpe, -20% max drawdown (vs -55% buy-hold; only -5.6% in 2008). "
        "Checked monthly; ~1-3 round trips/year."
    )
    asset_class          = "equities"
    typical_holding_days = 120

    def __init__(self, ma_window: int = 200, cash_yield: float = 0.04,
                 ticker: str = "SPY"):
        self.ma_window  = ma_window
        self.cash_yield = cash_yield
        self.ticker     = ticker

    def get_params(self) -> dict:
        return {"ma_window": self.ma_window, "cash_yield": self.cash_yield,
                "ticker": self.ticker}

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "ma_window", "label": "MA window (days)", "type": "slider",
             "min": 50, "max": 300, "default": 200, "step": 10, "col": 0, "row": 0,
             "help": "Trend filter length. 200 is the canonical, un-optimised choice."},
            {"key": "cash_yield", "label": "Cash yield (annual)", "type": "slider",
             "min": 0.0, "max": 0.06, "default": 0.04, "step": 0.01, "col": 1, "row": 0,
             "help": "Yield earned while out of the market (T-bills)."},
        ]

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        close = market_snapshot.get("close")
        if close is None or (hasattr(close, "empty") and close.empty):
            close = load_close(market_snapshot.get("ticker", self.ticker))
        sig = current_trend_signal(close, self.ma_window)
        is_buy = sig.get("signal") == "BUY"
        return SignalResult(self.name, sig.get("signal", "HOLD"),
                            confidence=1.0 if is_buy else 0.0,
                            position_size_pct=1.0 if is_buy else 0.0,
                            metadata=sig)

    def backtest(self, price_data: pd.DataFrame, auxiliary_data: dict,
                 starting_capital: float = 10_000, ma_window: Optional[int] = None,
                 cash_yield: Optional[float] = None, **kwargs) -> BacktestResult:
        mw = ma_window if ma_window is not None else self.ma_window
        cy = cash_yield if cash_yield is not None else self.cash_yield
        ticker = (auxiliary_data or {}).get("ticker", self.ticker)
        close = close_from_inputs(price_data, ticker)
        if close.empty:
            raise ValueError(f"No price data for {ticker}.")
        pos = trend_position(close, mw)
        eq  = equity_from_position(close, pos, cy, starting_capital)
        trades = episodes_to_trades(close, pos)
        metrics = compute_all_metrics(eq, trades if not trades.empty else None)
        bh = starting_capital * (1 + close.pct_change().fillna(0)).cumprod()
        return BacktestResult(self.name, eq, eq.pct_change().dropna(), trades, metrics,
                              params={"ma_window": mw, "cash_yield": cy, "ticker": ticker},
                              extra={"benchmark_equity": bh,
                                     "current": current_trend_signal(close, mw)})
