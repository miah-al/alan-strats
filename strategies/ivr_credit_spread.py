"""
IVR Credit Spread Strategy.

Harvests the Variance Risk Premium (VRP) by selling defined-risk vertical spreads
on SPY/QQQ when IV Rank is elevated (≥ 50%).  Implied volatility exceeds realised
volatility roughly 70% of the time, creating a persistent edge for credit-spread
sellers.

Entry rules:
  • IVR ≥ ivr_min  AND  price above 50-day MA  → sell Bull Put Spread  (bullish)
  • IVR ≥ ivr_min  AND  price below 50-day MA  → sell Bear Call Spread (bearish)

Trade parameters:
  • DTE at entry  : 30-45 days (default target 45)
  • Short strike  : 16-delta approximation via BS inversion
  • Spread width  : spread_width_pct × spot price  (default 5%)
  • Position size : floor(capital × position_size_pct / (spread_width × 100)) contracts

Exit conditions (checked daily, first trigger wins):
  1. 50% of credit received (profit target)
  2. 21 DTE remaining
  3. 2× credit received as loss (stop loss)
  4. End of data

IVR = (VIX − VIX_52w_low) / (VIX_52w_high − VIX_52w_low)
"""

import math
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)
from alan_trader.backtest.engine import bs_price
from alan_trader.risk.metrics import compute_all_metrics


# ── Constants ─────────────────────────────────────────────────────────────────

_RISK_FREE_RATE = 0.045   # proxy for 3-month T-Bill
_MIN_IVR_WINDOW = 30      # minimum bars needed to compute a valid IVR


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bs_delta(S: float, K: float, T: float, r: float, sigma: float,
              option_type: str) -> float:
    """Black-Scholes delta for a European option."""
    if T <= 0 or sigma <= 0 or S <= 0:
        if option_type == "call":
            return 1.0 if S > K else 0.0
        else:
            return -1.0 if S < K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    if option_type == "call":
        return float(norm.cdf(d1))
    else:
        return float(norm.cdf(d1) - 1.0)


def _find_strike_for_delta(S: float, T: float, r: float, sigma: float,
                           target_delta: float, option_type: str) -> float:
    """
    Binary-search for the strike K such that |delta(K)| ≈ target_delta.
    target_delta is positive (e.g. 0.16 for a 16-delta option).
    """
    if T <= 0 or sigma <= 0:
        return S  # fallback to ATM

    sign = 1.0 if option_type == "call" else -1.0

    def objective(K):
        d = _bs_delta(S, K, T, r, sigma, option_type)
        return abs(d) - target_delta

    lo, hi = S * 0.50, S * 1.50
    try:
        K = brentq(objective, lo, hi, xtol=0.01, maxiter=50)
    except (ValueError, RuntimeError):
        # fallback: use 1-sigma move as rough strike
        K = S * np.exp(sign * sigma * np.sqrt(T))
    return float(K)


def _compute_ivr(vix: pd.Series, window: int = 252) -> pd.Series:
    """
    Rolling IV Rank: (current − 52w_low) / (52w_high − 52w_low).
    Returns NaN when the window is not yet full.
    """
    roll_low  = vix.rolling(window, min_periods=_MIN_IVR_WINDOW).min()
    roll_high = vix.rolling(window, min_periods=_MIN_IVR_WINDOW).max()
    rng = roll_high - roll_low
    ivr = (vix - roll_low) / rng.replace(0, np.nan)
    return ivr.clip(0.0, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy class
# ─────────────────────────────────────────────────────────────────────────────

class IVRCreditSpreadStrategy(BaseStrategy):
    """
    IVR-triggered credit spread strategy.

    Sells Bull Put Spreads (bullish) or Bear Call Spreads (bearish) on
    SPY/QQQ whenever IV Rank is elevated, harvesting the variance risk premium
    with fully defined risk.
    """

    name                 = "ivr_credit_spread"
    display_name         = "IVR Credit Spread"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Sells defined-risk vertical spreads on any liquid optionable ticker when IV rank ≥ 50%. "
        "Bull put spread in uptrend, bear call spread in downtrend. "
        "Harvests the variance risk premium systematically. Ticker is a parameter."
    )
    asset_class          = "equities_options"
    typical_holding_days = 21
    target_sharpe        = 1.2

    def __init__(
        self,
        ivr_min:             float = 0.50,   # minimum IV rank to enter
        dte_target:          int   = 45,     # target DTE at entry
        dte_exit:            int   = 21,     # close regardless at this DTE
        delta_short:         float = 0.16,   # short-strike delta
        spread_width_pct:    float = 0.05,   # spread width as % of spot
        profit_target_pct:   float = 0.50,   # close at 50% of max credit
        stop_loss_mult:      float = 2.0,    # stop at 2× credit received
        position_size_pct:   float = 0.03,   # capital fraction per trade
        commission_per_leg:  float = 0.65,   # $ per contract per leg
    ):
        self.ivr_min            = ivr_min
        self.dte_target         = dte_target
        self.dte_exit           = dte_exit
        self.delta_short        = delta_short
        self.spread_width_pct   = spread_width_pct
        self.profit_target_pct  = profit_target_pct
        self.stop_loss_mult     = stop_loss_mult
        self.position_size_pct  = position_size_pct
        self.commission_per_leg = commission_per_leg

    # ── Params / UI ──────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        return {
            "ivr_min":            self.ivr_min,
            "dte_target":         self.dte_target,
            "dte_exit":           self.dte_exit,
            "delta_short":        self.delta_short,
            "spread_width_pct":   self.spread_width_pct,
            "profit_target_pct":  self.profit_target_pct,
            "stop_loss_mult":     self.stop_loss_mult,
            "position_size_pct":  self.position_size_pct,
            "commission_per_leg": self.commission_per_leg,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {
                "key":     "ivr_min",
                "label":   "Min IV Rank",
                "type":    "slider",
                "min":     0.30, "max": 0.80, "default": 0.50, "step": 0.05,
                "col":     0, "row": 0,
                "help":    "Minimum IV Rank (0-1) required to enter a new spread",
            },
            {
                "key":     "dte_target",
                "label":   "Target DTE at entry",
                "type":    "slider",
                "min":     21,   "max": 60,   "default": 45,   "step": 1,
                "col":     1,    "row": 0,
                "help":    "Target days-to-expiry when opening a new spread",
            },
            {
                "key":     "profit_target_pct",
                "label":   "Profit target (%)",
                "type":    "slider",
                "min":     0.30, "max": 0.70, "default": 0.50, "step": 0.05,
                "col":     2,    "row": 0,
                "help":    "Close spread when P&L reaches this fraction of max credit received",
            },
        ]

    # ── Live signal ──────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Use VIX as IV proxy and 50-day price MA for trend to emit a live signal.
        market_snapshot expected keys:
          price          — current spot price of the ticker (preferred)
          vix            — current VIX level
          features_df    — (optional) recent feature rows
        Legacy key spy_price is still accepted for backward compatibility.
        """
        vix   = market_snapshot.get("vix", 20.0)
        spot  = market_snapshot.get("price") or market_snapshot.get("spy_price")

        # Compute IVR from features_df if available (rolling window context)
        features_df = market_snapshot.get("features_df")
        ivr: float  = 0.0
        ma50: float | None = None

        if features_df is not None and not features_df.empty and "vix" in features_df.columns:
            vix_series = features_df["vix"].dropna()
            if len(vix_series) >= _MIN_IVR_WINDOW:
                vix_low  = vix_series.rolling(252, min_periods=_MIN_IVR_WINDOW).min().iloc[-1]
                vix_high = vix_series.rolling(252, min_periods=_MIN_IVR_WINDOW).max().iloc[-1]
                rng = vix_high - vix_low
                ivr = float((vix - vix_low) / rng) if rng > 0 else 0.0
                ivr = float(np.clip(ivr, 0.0, 1.0))

            if "close" in features_df.columns and len(features_df) >= 50:
                ma50 = float(features_df["close"].iloc[-50:].mean())
        else:
            # Rough heuristic: VIX > 20 → IVR ≈ 0.5
            ivr = float(np.clip((vix - 12.0) / (40.0 - 12.0), 0.0, 1.0))

        if ivr < self.ivr_min:
            return SignalResult(
                strategy_name=self.name,
                signal="HOLD",
                confidence=round(ivr, 3),
                position_size_pct=0.0,
                metadata={"ivr": round(ivr, 3), "reason": "IVR below threshold"},
            )

        # Direction from trend
        above_ma    = (spot is not None and ma50 is not None and spot > ma50)
        spread_type = "bull_put" if above_ma else "bear_call"
        signal      = "BUY" if above_ma else "SELL"

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=round(ivr, 3),
            position_size_pct=self.position_size_pct,
            metadata={
                "ivr":         round(ivr, 3),
                "vix":         vix,
                "spread_type": spread_type,
                "above_50ma":  above_ma,
            },
        )

    # ── Backtest ─────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:       pd.DataFrame,
        auxiliary_data:   dict,
        starting_capital: float = 100_000,
        ivr_min:          float | None = None,
        dte_target:       int   | None = None,
        profit_target_pct: float | None = None,
        **kwargs,
    ) -> BacktestResult:
        """
        Walk-forward simulation.  No look-ahead bias.

        auxiliary_data must contain:
          "vix"  : DataFrame with DatetimeIndex and a "close" column (VIX levels)
        """
        # ── Resolve params (UI overrides take precedence) ─────────────────
        ivr_min_eff  = ivr_min           if ivr_min           is not None else self.ivr_min
        dte_tgt_eff  = dte_target        if dte_target        is not None else self.dte_target
        pt_eff       = profit_target_pct if profit_target_pct is not None else self.profit_target_pct

        dte_exit_eff = self.dte_exit
        sl_mult      = self.stop_loss_mult
        sw_pct       = self.spread_width_pct
        d_short      = self.delta_short
        pos_sz_pct   = self.position_size_pct
        comm         = self.commission_per_leg
        r            = _RISK_FREE_RATE

        # ── Align data ────────────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)

        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if vix_df is None or (isinstance(vix_df, pd.DataFrame) and vix_df.empty):
            raise ValueError(
                "No VIX data found. Go to Data Manager → Macro Bars and sync VIX first."
            )

        vix_df = vix_df.copy()
        vix_df.index = pd.to_datetime(vix_df.index)
        vix = vix_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False).fillna(20.0)

        close  = price_data["close"]
        iv_proxy = vix / 100.0   # convert VIX points → decimal IV proxy

        # ── Derived series ────────────────────────────────────────────────
        ivr_series = _compute_ivr(vix, window=252)
        ma50       = close.rolling(50, min_periods=20).mean()

        all_dates  = list(price_data.index)
        n_dates    = len(all_dates)

        # ── Simulation state ──────────────────────────────────────────────
        capital    = float(starting_capital)
        equity_list: list[float]  = []
        pnl_at_exit: dict         = {}    # date → cumulative pnl additions
        open_trades: list[dict]   = []
        closed_trades: list[dict] = []

        for i, dt in enumerate(all_dates):
            spot    = float(close.iloc[i])
            ivr_val = float(ivr_series.iloc[i]) if not np.isnan(ivr_series.iloc[i]) else 0.0
            iv_val  = float(iv_proxy.iloc[i])
            ma_val  = float(ma50.iloc[i]) if not np.isnan(ma50.iloc[i]) else spot

            # ── 1. Check exit conditions on open trades ───────────────────
            still_open: list[dict] = []
            for trade in open_trades:
                dte_remaining = (trade["expiry_idx"] - i)

                # Current spread value (cost to close = current liability)
                T_now = max(dte_remaining / 252.0, 0.0)
                cur_iv = iv_val
                if trade["spread_type"] == "bull_put":
                    cur_val = (
                        bs_price(spot, trade["short_K"], T_now, r, cur_iv, "put")
                        - bs_price(spot, trade["long_K"],  T_now, r, cur_iv, "put")
                    )
                else:  # bear_call
                    cur_val = (
                        bs_price(spot, trade["short_K"], T_now, r, cur_iv, "call")
                        - bs_price(spot, trade["long_K"],  T_now, r, cur_iv, "call")
                    )

                # P&L = credit received − current cost to close (per spread)
                pnl_per_spread = trade["credit"] - cur_val
                pnl_total = pnl_per_spread * trade["contracts"] * 100

                # Commission to close (2 legs)
                close_comm = 2 * comm * trade["contracts"]

                exit_reason: str | None = None
                if pnl_per_spread >= pt_eff * trade["credit"]:
                    exit_reason = "profit_target"
                elif dte_remaining <= dte_exit_eff:
                    exit_reason = "dte_exit"
                elif cur_val >= sl_mult * trade["credit"]:
                    exit_reason = "stop_loss"
                elif i == n_dates - 1:
                    exit_reason = "end_of_data"

                if exit_reason:
                    net_pnl = round(pnl_total - close_comm, 2)
                    capital += net_pnl
                    closed_trades.append({
                        "entry_date":  trade["entry_date"].date(),
                        "exit_date":   dt.date(),
                        "spread_type": trade["spread_type"],
                        "short_K":     round(trade["short_K"], 2),
                        "long_K":      round(trade["long_K"],  2),
                        "credit":      round(trade["credit"],  4),
                        "contracts":   trade["contracts"],
                        "entry_cost":  round(trade["entry_capital"], 2),
                        "exit_value":  round(capital, 2),
                        "pnl":         net_pnl,
                        "exit_reason": exit_reason,
                        "dte_held":    trade["dte_entry"] - dte_remaining,
                    })
                    # Record pnl addition for equity curve construction
                    pnl_at_exit[dt] = pnl_at_exit.get(dt, 0.0) + net_pnl
                else:
                    still_open.append(trade)

            open_trades = still_open

            # ── 2. Entry check ────────────────────────────────────────────
            # Only enter if IVR ≥ threshold and we have valid IV / MA.
            # Require at least 50 bars of history so the 50-day MA is meaningful
            # and IVR has some history (ivr_series uses min_periods=30).
            can_enter = (
                i >= 50
                and ivr_val >= ivr_min_eff
                and not np.isnan(ivr_series.iloc[i])   # IVR must be a real value
                and iv_val > 0
                and spot > 0
                # Avoid entering too close to end of data
                and (n_dates - i) > dte_tgt_eff
            )

            if can_enter:
                above_ma    = spot > ma_val
                spread_type = "bull_put" if above_ma else "bear_call"
                T_entry     = dte_tgt_eff / 252.0

                # Strike selection: short strike at target delta, long strike spread_width below/above
                spread_width = spot * sw_pct

                if spread_type == "bull_put":
                    short_K = _find_strike_for_delta(spot, T_entry, r, iv_val, d_short, "put")
                    long_K  = short_K - spread_width    # long put below short put
                else:
                    short_K = _find_strike_for_delta(spot, T_entry, r, iv_val, d_short, "call")
                    long_K  = short_K + spread_width    # long call above short call

                long_K  = max(long_K,  0.01)
                short_K = max(short_K, 0.01)

                # Credit = short premium − long premium (net credit received)
                if spread_type == "bull_put":
                    short_prem = bs_price(spot, short_K, T_entry, r, iv_val, "put")
                    long_prem  = bs_price(spot, long_K,  T_entry, r, iv_val, "put")
                else:
                    short_prem = bs_price(spot, short_K, T_entry, r, iv_val, "call")
                    long_prem  = bs_price(spot, long_K,  T_entry, r, iv_val, "call")

                credit = short_prem - long_prem

                # Skip degenerate entries
                if credit <= 0.01 or spread_width < 0.50:
                    equity_list.append(capital)
                    continue

                # Size position: max loss = spread_width × 100 per contract
                max_loss_per_contract = spread_width * 100
                contracts = max(1, math.floor(
                    capital * pos_sz_pct / max_loss_per_contract
                ))

                # Entry commission (2 legs)
                entry_comm = 2 * comm * contracts
                capital   -= entry_comm

                expiry_idx = min(i + dte_tgt_eff, n_dates - 1)
                open_trades.append({
                    "entry_date":    dt,
                    "expiry_idx":    expiry_idx,
                    "dte_entry":     dte_tgt_eff,
                    "spread_type":   spread_type,
                    "short_K":       short_K,
                    "long_K":        long_K,
                    "credit":        credit,
                    "contracts":     contracts,
                    "entry_capital": capital,
                    "iv_entry":      iv_val,
                    "ivr_entry":     ivr_val,
                })

            # Mark-to-market: include unrealised P&L of all open trades
            mtm = 0.0
            for ot in open_trades:
                dte_rem = ot["expiry_idx"] - i
                T_mtm = max(dte_rem / 252.0, 0.0)
                if ot["spread_type"] == "bull_put":
                    ot_val = (
                        bs_price(spot, ot["short_K"], T_mtm, r, iv_val, "put")
                        - bs_price(spot, ot["long_K"],  T_mtm, r, iv_val, "put")
                    )
                else:  # bear_call
                    ot_val = (
                        bs_price(spot, ot["short_K"], T_mtm, r, iv_val, "call")
                        - bs_price(spot, ot["long_K"],  T_mtm, r, iv_val, "call")
                    )
                # Unrealised P&L = credit received − current cost to close
                mtm += (ot["credit"] - ot_val) * ot["contracts"] * 100
            equity_list.append(capital + mtm)

        # ── Build equity curve and daily returns ──────────────────────────
        equity = pd.Series(equity_list, index=price_data.index, dtype=float)
        daily_ret = equity.pct_change().dropna()
        bh_ret    = close.pct_change().reindex(equity.index).dropna()

        trades_df = (
            pd.DataFrame(closed_trades)
            if closed_trades
            else pd.DataFrame(columns=[
                "entry_date", "exit_date", "spread_type", "short_K", "long_K",
                "credit", "contracts", "entry_cost", "exit_value",
                "pnl", "exit_reason", "dte_held",
            ])
        )

        metrics = compute_all_metrics(
            equity_curve=equity,
            trades_df=trades_df,
            benchmark_returns=bh_ret,
        )

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params={
                **self.get_params(),
                "ivr_min":           ivr_min_eff,
                "dte_target":        dte_tgt_eff,
                "profit_target_pct": pt_eff,
            },
            extra={
                "ivr_series":        ivr_series,
                "vix":               vix,
                "ma50":              ma50,
                "benchmark_ret":     bh_ret,
                "open_trades_at_end": len(open_trades),
            },
        )

    # ── Empty result helper ───────────────────────────────────────────────────

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
