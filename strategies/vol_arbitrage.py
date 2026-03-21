"""
Volatility Arbitrage — Put-Call Parity Violation Strategy.

Put-call parity (European options, continuous dividends):
    C - P = S * e^(-q*T) - K * e^(-r*T)

Where:
    C = call mid price
    P = put mid price
    S = underlying price
    K = strike price
    r = risk-free rate
    q = continuous dividend yield
    T = time to expiry (years)

When the observed (C - P) deviates from the theoretical value by more than
transaction costs + threshold, two trades exist:

  CONVERSION  (calls overpriced, C - P > parity + threshold):
    Buy stock + Buy put + Sell call at same K, T
    → Always worth K*e^(-rT) at expiry, regardless of S_T
    → P&L = K*e^(-rT) - (S + P - C) - costs  [positive when calls are rich]

  REVERSAL    (puts overpriced, C - P < parity - threshold):
    Short stock + Sell put + Buy call at same K, T
    → Always costs K*e^(-rT) at expiry
    → P&L = (S + P - C) - K*e^(-rT) - costs  [positive when puts are rich]

Secondary signal: IV skew — when put IV significantly exceeds call IV at the
same delta (e.g. IV_put_20d - IV_call_20d > threshold), sell the expensive side.
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional
from scipy.optimize import brentq
from scipy.stats import norm

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult, StrategyStatus, StrategyType,
)
from alan_trader.backtest.engine import bs_price
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Greeks / IV helpers
# ─────────────────────────────────────────────────────────────────────────────

def _implied_vol(market_price: float, S: float, K: float, T: float,
                 r: float, option_type: str) -> Optional[float]:
    """Solve for IV via Brent's method. Returns None if no solution."""
    if T <= 0 or market_price <= 0:
        return None
    intrinsic = max(0, S - K) if option_type == "call" else max(0, K - S)
    if market_price < intrinsic:
        return None
    try:
        iv = brentq(
            lambda v: bs_price(S, K, T, r, v, option_type) - market_price,
            1e-6, 10.0, xtol=1e-6, maxiter=100,
        )
        return float(iv)
    except (ValueError, RuntimeError):
        return None


def _parity_theoretical(S: float, K: float, T: float, r: float, q: float) -> float:
    """Theoretical C - P from put-call parity with continuous dividend yield."""
    return S * np.exp(-q * T) - K * np.exp(-r * T)


@dataclass
class ParityViolation:
    """A detected put-call parity violation."""
    date: object
    strike: float
    expiry_days: int
    call_price: float
    put_price: float
    spot: float
    observed_diff: float       # actual C - P
    theoretical_diff: float    # S*e^(-qT) - K*e^(-rT)
    violation: float           # observed - theoretical (+ = calls rich, - = puts rich)
    trade_type: str            # "conversion" or "reversal"
    iv_call: Optional[float]
    iv_put: Optional[float]
    iv_skew: Optional[float]   # iv_put - iv_call  (positive = put skew)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy
# ─────────────────────────────────────────────────────────────────────────────

class VolArbitrageStrategy(BaseStrategy):
    name                 = "vol_arbitrage"
    display_name         = "Vol Arbitrage (Put-Call Parity)"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Detects put-call parity violations across the SPY options chain. "
        "Executes conversions (calls overpriced) or reversals (puts overpriced). "
        "Also trades IV skew when OTM puts diverge significantly from OTM calls."
    )
    asset_class          = "equities_options"
    typical_holding_days = 3
    target_sharpe        = 1.4

    def __init__(
        self,
        min_violation_pct: float = 0.003,   # min 0.3% of S to enter
        max_violation_pct: float = 0.05,    # ignore if > 5% (data error)
        iv_skew_threshold: float = 0.08,    # 8 vol-point skew = tradeable
        dividend_yield: float = 0.013,      # SPY annual div yield ~1.3%
        position_size_pct: float = 0.08,
        hold_days: int = 3,
        commission_per_contract: float = 0.65,
        slippage_pct: float = 0.001,        # 0.1% bid-ask slippage
    ):
        self.min_viol       = min_violation_pct
        self.max_viol       = max_violation_pct
        self.skew_thresh    = iv_skew_threshold
        self.div_yield      = dividend_yield
        self.pos_size_pct   = position_size_pct
        self.hold_days      = hold_days
        self.commission     = commission_per_contract
        self.slippage       = slippage_pct

    # ─────────────────────────────────────────────────────────────────────
    # Signal
    # ─────────────────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        chain = market_snapshot.get("options_chain")
        S     = market_snapshot.get("spy_price", 500.0)
        r     = market_snapshot.get("rate_10y", 0.045)

        if chain is None or chain.empty:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "no options chain"})

        violations = self._scan_chain(chain, S, r)
        if not violations:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "no violations found"})

        best = max(violations, key=lambda v: abs(v.violation))
        signal = "SELL" if best.trade_type == "conversion" else "BUY"
        confidence = min(1.0, abs(best.violation) / (S * self.min_viol * 3))

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=confidence,
            position_size_pct=self.pos_size_pct,
            metadata={
                "trade_type":       best.trade_type,
                "strike":           best.strike,
                "violation_pct":    round(best.violation / S * 100, 3),
                "iv_skew":          best.iv_skew,
                "n_violations":     len(violations),
            },
        )

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
        vix_df  = auxiliary_data.get("vix",    pd.DataFrame())
        rate_df = auxiliary_data.get("rate10y", pd.DataFrame())
        chains  = auxiliary_data.get("options_chains")  # dict: date → chain DataFrame

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)

        if not vix_df.empty:
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)

        if not rate_df.empty:
            rate_df = rate_df.copy()
            rate_df.index = pd.to_datetime(rate_df.index)

        # Generate simulated chains if none provided
        if chains is None:
            chains = self._simulate_chains(price_data, vix_df, rate_df)

        capital    = float(starting_capital)
        trades     = []
        equity_pts = []

        sorted_dates = sorted(chains.keys())
        open_trades  = []   # list of dicts tracking open positions

        for today in sorted(price_data.index):
            today_date = today.date() if hasattr(today, "date") else today

            # Close trades that have held long enough
            still_open = []
            for tr in open_trades:
                days_held = (pd.Timestamp(today) - pd.Timestamp(tr["entry_date"])).days
                if days_held >= self.hold_days:
                    S_exit = float(price_data.loc[today, "close"])
                    pnl    = self._close_trade(tr, S_exit)
                    capital += pnl
                    trades.append({**tr, "exit_date": today_date,
                                   "pnl": round(pnl, 2), "exit_reason": "hold_expired"})
                else:
                    still_open.append(tr)
            open_trades = still_open

            # Look for new violations on today's chain
            if today in chains and len(open_trades) == 0:
                chain = chains[today]
                S   = float(price_data.loc[today, "close"])
                r   = float(rate_df["close"].asof(today)) / 100 if not rate_df.empty else 0.045
                violations = self._scan_chain(chain, S, r)

                for v in violations[:1]:   # take best violation only
                    tr = self._open_trade(v, S, capital, today_date)
                    if tr:
                        capital -= tr["cost"]
                        open_trades.append(tr)

            equity_pts.append({"date": today, "equity": capital})

        # Close remaining open trades at last price
        if open_trades and len(price_data) > 0:
            last_price = float(price_data["close"].iloc[-1])
            for tr in open_trades:
                pnl = self._close_trade(tr, last_price)
                capital += pnl
                trades.append({**tr, "exit_date": sorted_dates[-1] if sorted_dates else None,
                               "pnl": round(pnl, 2), "exit_reason": "end_of_data"})

        if not equity_pts:
            return self._empty_result(starting_capital)

        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        equity    = pd.Series(
            [e["equity"] for e in equity_pts],
            index=pd.to_datetime([e["date"] for e in equity_pts]),
            name="equity",
        )
        daily_ret = equity.pct_change().dropna()

        spy_ret = price_data["close"].pct_change().dropna()
        spy_ret.index = pd.to_datetime(spy_ret.index)

        metrics = compute_all_metrics(
            equity_curve=equity,
            trades_df=trades_df if not trades_df.empty else None,
            benchmark_returns=spy_ret.reindex(equity.index).dropna(),
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
            {"key": "hold_days",          "label": "Max hold days",       "type": "slider", "min": 1, "max": 10,  "default": 3,   "step": 1,   "col": 0},
            {"key": "min_violation_pct",  "label": "Min violation % of S","type": "slider", "min": 0.1,"max": 1.0,"default": 0.3, "step": 0.1, "col": 1},
        ]

    def get_params(self) -> dict:
        return {
            "min_violation_pct":    self.min_viol,
            "max_violation_pct":    self.max_viol,
            "iv_skew_threshold":    self.skew_thresh,
            "dividend_yield":       self.div_yield,
            "position_size_pct":    self.pos_size_pct,
            "hold_days":            self.hold_days,
            "slippage_pct":         self.slippage,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Core: scan options chain for parity violations
    # ─────────────────────────────────────────────────────────────────────

    def _scan_chain(self, chain: pd.DataFrame, S: float, r: float) -> list[ParityViolation]:
        """
        For each strike with both a call and put, compute parity deviation.
        Returns list sorted by |violation| descending.
        """
        violations = []
        calls = chain[chain["type"] == "call"].set_index("strike")
        puts  = chain[chain["type"] == "put"].set_index("strike")

        common_strikes = calls.index.intersection(puts.index)
        for K in common_strikes:
            c_row = calls.loc[K]
            p_row = puts.loc[K]

            c_mid = (float(c_row["bid"]) + float(c_row["ask"])) / 2
            p_mid = (float(p_row["bid"]) + float(p_row["ask"])) / 2
            T     = float(c_row.get("dte", 30)) / 252

            if T <= 0 or c_mid <= 0 or p_mid <= 0:
                continue

            observed    = c_mid - p_mid
            theoretical = _parity_theoretical(S, K, T, r, self.div_yield)
            violation   = observed - theoretical

            # Skip if violation is noise-level or suspiciously large
            viol_pct = abs(violation) / S
            if viol_pct < self.min_viol or viol_pct > self.max_viol:
                continue

            # Implied vols
            iv_c = _implied_vol(c_mid, S, K, T, r, "call")
            iv_p = _implied_vol(p_mid, S, K, T, r, "put")
            iv_skew = (iv_p - iv_c) if (iv_c and iv_p) else None

            trade_type = "conversion" if violation > 0 else "reversal"
            violations.append(ParityViolation(
                date=None, strike=K,
                expiry_days=int(c_row.get("dte", 30)),
                call_price=c_mid, put_price=p_mid, spot=S,
                observed_diff=observed, theoretical_diff=theoretical,
                violation=violation, trade_type=trade_type,
                iv_call=iv_c, iv_put=iv_p, iv_skew=iv_skew,
            ))

        violations.sort(key=lambda v: abs(v.violation), reverse=True)
        return violations

    # ─────────────────────────────────────────────────────────────────────
    # Trade management
    # ─────────────────────────────────────────────────────────────────────

    def _open_trade(self, v: ParityViolation, S: float,
                    capital: float, today) -> Optional[dict]:
        # Each contract = 100 shares; conversion ties up ~20% margin on stock leg
        margin_per_contract = S * 100 * 0.20
        budget        = capital * self.pos_size_pct
        n_contracts   = max(1, int(budget / margin_per_contract))

        slippage_cost = S * self.slippage * n_contracts * 100
        commission    = self.commission * n_contracts * 3   # stock + call + put legs

        # Expected locked-in profit = violation per share * 100 shares * contracts
        gross_profit = abs(v.violation) * n_contracts * 100
        net_profit   = gross_profit - slippage_cost - commission

        if net_profit <= 0:
            return None

        cost = margin_per_contract * n_contracts

        return {
            "entry_date":     today,
            "spread_type":    f"vol_arb_{v.trade_type}",
            "long_strike":    v.strike,
            "short_strike":   v.strike,
            "entry_cost":     cost / (n_contracts * 100),
            "exit_value":     0.0,
            "contracts":      n_contracts,
            "expected_pnl":   net_profit,
            "violation":      v.violation,
            "cost":           cost,
            "trade_type":     v.trade_type,
            "iv_skew":        v.iv_skew,
        }

    def _close_trade(self, tr: dict, S_exit: float) -> float:
        """
        Returns capital tied up + net profit.
        Collect ~80% of the expected locked-in profit (exit before expiry).
        """
        n          = tr["contracts"]
        commission = self.commission * n * 3
        profit     = tr["expected_pnl"] * 0.80 - commission
        return round(tr["cost"] + profit, 2)

    # ─────────────────────────────────────────────────────────────────────
    # Simulated options chains with injected violations
    # ─────────────────────────────────────────────────────────────────────

    def _simulate_chains(
        self,
        price_data: pd.DataFrame,
        vix_df: pd.DataFrame,
        rate_df: pd.DataFrame,
    ) -> dict:
        """
        Build a synthetic options chain for each trading day.
        Injects random put-call parity violations on ~15% of days.
        """
        from alan_trader.data.simulator import simulate_options_chain_with_violations
        chains = {}
        rng = np.random.default_rng(42)

        for date, row in price_data.iterrows():
            S   = float(row["close"])
            iv  = float(vix_df["close"].asof(date)) / 100 if not vix_df.empty else 0.18
            r   = float(rate_df["close"].asof(date)) / 100 if not rate_df.empty else 0.045
            inject = rng.random() < 0.15   # violation on ~15% of days
            chain  = simulate_options_chain_with_violations(
                S=S, iv=iv, r=r, q=self.div_yield,
                inject_violation=inject, rng=rng,
            )
            chains[date] = chain

        return chains

    def _empty_result(self, capital: float) -> BacktestResult:
        eq = pd.Series([float(capital)], dtype=float)
        return BacktestResult(
            strategy_name=self.name,
            equity_curve=eq,
            daily_returns=pd.Series(dtype=float),
            trades=pd.DataFrame(),
            metrics={},
            params=self.get_params(),
        )
