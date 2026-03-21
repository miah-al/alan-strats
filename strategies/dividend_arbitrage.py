"""
Dividend Arbitrage Strategy.

Logic:
  - Enter N days before ex-dividend date
  - Buy SPY shares, hedge downside with short-dated ATM put (priced via Black-Scholes)
  - Receive dividend on ex-date (price gaps down ~dividend amount)
  - Exit on ex-date + hold_days_post
  - Net P&L = (exit - entry) * shares + dividend - put_premium + put_exit_value - commissions
"""

import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult, StrategyStatus, StrategyType,
)
from alan_trader.backtest.engine import bs_price
from alan_trader.risk.metrics import compute_all_metrics


class DividendArbitrageStrategy(BaseStrategy):
    name                 = "dividend_arb"
    display_name         = "Dividend Arbitrage"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = ("Buy before ex-dividend date, capture dividend, "
                            "hedge equity risk with short-dated put.")
    asset_class          = "equities_options"
    typical_holding_days = 4
    target_sharpe        = 0.9

    def __init__(
        self,
        entry_days_before_exdiv: int = 3,
        hold_days_post_exdiv: int = 1,
        hedge_with_put: bool = True,
        put_dte: int = 7,
        position_size_pct: float = 0.10,
        min_div_yield_annual: float = 0.008,
        commission_per_share: float = 0.005,
        option_commission: float = 0.65,
        slippage_pct: float = 0.0005,
    ):
        self.entry_days      = entry_days_before_exdiv
        self.hold_post       = hold_days_post_exdiv
        self.hedge           = hedge_with_put
        self.put_dte         = put_dte
        self.pos_size_pct    = position_size_pct
        self.min_yield       = min_div_yield_annual
        self.comm_share      = commission_per_share
        self.comm_opt        = option_commission
        self.slippage        = slippage_pct

    # ─────────────────────────────────────────────────────────────────────
    # Signal
    # ─────────────────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        days_to_ex  = market_snapshot.get("days_to_next_exdiv", 999)
        div_yield   = market_snapshot.get("next_dividend_yield", 0.0)
        put_cost_pct = market_snapshot.get("estimated_put_cost_pct", 0.002)
        net_yield   = div_yield - (put_cost_pct if self.hedge else 0)

        if days_to_ex <= self.entry_days and div_yield >= self.min_yield / 4 and net_yield > 0:
            confidence = min(1.0, net_yield / 0.003)
            return SignalResult(
                strategy_name=self.name,
                signal="BUY",
                confidence=confidence,
                position_size_pct=self.pos_size_pct,
                metadata={
                    "days_to_exdiv":     days_to_ex,
                    "dividend_yield":    div_yield,
                    "net_yield":         net_yield,
                    "put_cost_est":      put_cost_pct,
                },
            )
        return SignalResult(self.name, "HOLD", 0.0, 0.0,
                            metadata={"days_to_exdiv": days_to_ex})

    # ─────────────────────────────────────────────────────────────────────
    # Backtest
    # ─────────────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data: pd.DataFrame,
        auxiliary_data: dict,
        starting_capital: float = 100_000,
        **kwargs,
    ) -> BacktestResult:
        dividends = auxiliary_data.get("dividends", pd.DataFrame())
        vix_df    = auxiliary_data.get("vix",    pd.DataFrame())

        if dividends.empty:
            return self._empty_result(starting_capital)

        # Align price dates
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_dates = set(price_data.index)

        # Build VIX lookup (for IV estimate)
        if not vix_df.empty:
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)
            vix_lookup = vix_df["close"]
        else:
            vix_lookup = pd.Series(dtype=float)

        capital     = float(starting_capital)
        equity_list = []
        trades_list = []
        all_dates   = sorted(price_data.index)

        for _, div_row in dividends.iterrows():
            ex_date = pd.Timestamp(div_row["ex_date"])
            div_per_share = float(div_row["div_per_share"])

            # Find entry date (N trading days before ex_date)
            sorted_dates = [d for d in all_dates if d < ex_date]
            if len(sorted_dates) < self.entry_days:
                continue
            entry_date = sorted_dates[-self.entry_days]

            # Find exit date
            post_dates = [d for d in all_dates if d >= ex_date]
            if len(post_dates) <= self.hold_post:
                continue
            exit_date = post_dates[self.hold_post]

            # Prices
            entry_price = float(price_data.loc[entry_date, "close"])
            exit_price  = float(price_data.loc[exit_date, "close"])

            # IV from VIX
            iv = float(vix_lookup.get(entry_date, 18.0)) / 100

            # Position size
            budget    = capital * self.pos_size_pct
            n_shares  = max(1, int(budget / entry_price))

            # Put hedge (1 ATM put per 100 shares = n_contracts)
            n_contracts = max(1, n_shares // 100)
            T_entry   = self.put_dte / 252
            T_exit    = max(0, (self.put_dte - (exit_date - entry_date).days)) / 252

            put_premium  = bs_price(entry_price, entry_price, T_entry, 0.045, iv, "put")
            put_exit_val = bs_price(exit_price,  entry_price, T_exit,  0.045, iv, "put") if self.hedge else 0.0

            # P&L components
            equity_pnl   = (exit_price - entry_price) * n_shares
            div_income   = div_per_share * n_shares
            put_cost     = put_premium   * n_contracts * 100 * (1 + self.slippage) if self.hedge else 0
            put_proceeds = put_exit_val  * n_contracts * 100 * (1 - self.slippage) if self.hedge else 0
            commissions  = (n_shares * self.comm_share * 2          # round-trip stock
                            + n_contracts * self.comm_opt * 2)       # round-trip options

            net_pnl = equity_pnl + div_income - put_cost + put_proceeds - commissions
            capital += net_pnl

            trades_list.append({
                "entry_date":    entry_date.date(),
                "exit_date":     exit_date.date(),
                "spread_type":   "dividend_arb",
                "long_strike":   entry_price,
                "short_strike":  entry_price,   # put strike = entry (ATM)
                "entry_cost":    entry_price,
                "exit_value":    exit_price,
                "contracts":     n_contracts,
                "pnl":           round(net_pnl, 2),
                "exit_reason":   "exdiv_hold",
                "div_income":    round(div_income, 2),
                "put_cost":      round(put_cost, 2),
                "equity_pnl":    round(equity_pnl, 2),
            })

        # Build daily equity curve (cash earning 0 when not in trade)
        if not trades_list:
            return self._empty_result(starting_capital)

        trades_df = pd.DataFrame(trades_list)
        # Reconstruct daily equity by distributing P&L at exit dates
        eq = pd.Series(starting_capital, index=all_dates, dtype=float)
        running = starting_capital
        for _, tr in trades_df.iterrows():
            exit_ts = pd.Timestamp(tr["exit_date"])
            mask    = eq.index >= exit_ts
            eq[mask] += tr["pnl"]

        equity = eq.copy()
        equity.index = pd.to_datetime(equity.index)
        daily_ret = equity.pct_change().dropna()

        vix_ret = None
        if not vix_df.empty:
            spy_ret = price_data["close"].pct_change().dropna()
            spy_ret.index = pd.to_datetime(spy_ret.index)
            vix_ret = spy_ret.reindex(equity.index).dropna()

        metrics = compute_all_metrics(
            equity_curve=equity,
            trades_df=trades_df,
            benchmark_returns=vix_ret,
        )

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
        )

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "hold_days", "label": "Days before ex-div", "type": "slider", "min": 1, "max": 10, "default": 3, "step": 1, "col": 0},
        ]

    def get_params(self) -> dict:
        return {
            "entry_days_before_exdiv": self.entry_days,
            "hold_days_post_exdiv":    self.hold_post,
            "hedge_with_put":          self.hedge,
            "put_dte":                 self.put_dte,
            "position_size_pct":       self.pos_size_pct,
            "min_div_yield_annual":    self.min_yield,
        }

    def _empty_result(self, capital: float) -> BacktestResult:
        eq = pd.Series([capital], dtype=float)
        return BacktestResult(
            strategy_name=self.name,
            equity_curve=eq,
            daily_returns=pd.Series(dtype=float),
            trades=pd.DataFrame(),
            metrics={},
            params=self.get_params(),
        )
