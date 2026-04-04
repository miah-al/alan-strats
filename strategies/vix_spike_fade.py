"""
VIX Spike Fade Strategy — Bull Call Spread on Mean-Reverting Fear Spikes.

THESIS
------
VIX spikes driven by sentiment / liquidity shocks (flash crashes, geo-political
scares, month-end rebalancing panic) mean-revert sharply within 5–15 trading
days. The strategy identifies spikes that are *not* regime breaks (the trading
instrument still above its 200-day MA) and buys a low-cost bull call spread at
peak panic to capture the snap-back.

The strategy is GENERIC — it trades whatever ticker is supplied as price_data.
SPY / QQQ / IWM are the most natural fits (liquid broad-market ETFs that track
VIX), but any highly-liquid optionable equity works.

TRADE STRUCTURE: Bull Call Spread on the supplied ticker
  - Long  call at ATM  (spot price rounded to nearest $1 strike)
  - Short call at ATM + spread_width  (OTM cap leg)
  - DTE at entry: ~dte_entry days (default 21)
  - Max loss  = debit paid × 100 × contracts  (defined risk)
  - Max gain  = (spread_width - debit) × 100 × contracts

ENTRY CONDITIONS (all must be true on the same day):
  1. vix > spike_threshold            (e.g. VIX > 25)
  2. vix > vix_20d_avg * spike_ratio  (e.g. VIX > 130% of 20-day average)
  3. close > ma_200d * 0.95           (within 5% of 200-day MA — not a regime break)
  4. No open position
  5. min_days_between_trades elapsed since last exit

EXIT CONDITIONS (first to trigger):
  A. VIX drops below revert_threshold  → close
  B. Current spread value > entry_debit × (1 + profit_target_pct)  → close
  C. Days held >= max_hold_days  → time stop

POSITION SIZING:
  contracts = max(1, floor(capital × position_size_pct / (debit × 100)))
  Total risk = debit × 100 × contracts + 2 × commission_per_leg × contracts

PARAMETERS
----------
  spike_threshold       — absolute VIX level to classify as spike   (default 25.0)
  spike_ratio           — VIX / 20d_avg ratio trigger               (default 1.3)
  revert_threshold      — exit when VIX drops below this            (default 22.0)
  spread_width          — OTM call strike distance in $             (default 5.0)
  dte_entry             — target DTE at entry                       (default 21)
  max_hold_days         — time stop in calendar days                (default 15)
  profit_target_pct     — close at this multiple of entry debit     (default 0.50)
  position_size_pct     — capital fraction per trade                (default 0.02)
  commission_per_leg    — per-contract per-leg commission           (default 0.65)
  min_days_between_trades — cooldown after each exit                (default 10)
"""

import math
import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)
from alan_trader.risk.metrics import compute_all_metrics
from alan_trader.backtest.engine import bs_price


_RISK_FREE_RATE = 0.045   # 4.5% annual, used for B-S pricing throughout


class VIXSpikeFadeStrategy(BaseStrategy):
    """Buy bull call spreads on any broad-market ticker during VIX panic spikes; exit on mean-reversion."""

    name                 = "vix_spike_fade"
    display_name         = "VIX Spike Fade"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Buys bull call spreads on a broad-market ticker (e.g. SPY, QQQ, IWM) during VIX "
        "panic spikes (VIX > 25 and 30%+ above 20-day avg). Captures mean-reversion of "
        "fear-driven volatility within 5-15 days. Ticker is a parameter — no hardcoding."
    )
    asset_class          = "equities_options"
    typical_holding_days = 10
    target_sharpe        = 1.8

    def __init__(
        self,
        spike_threshold: float = 25.0,
        spike_ratio: float = 1.3,
        revert_threshold: float = 22.0,
        spread_width: float = 5.0,
        dte_entry: int = 21,
        max_hold_days: int = 15,
        profit_target_pct: float = 0.50,
        position_size_pct: float = 0.02,
        commission_per_leg: float = 0.65,
        min_days_between_trades: int = 10,
    ):
        self.spike_threshold          = spike_threshold
        self.spike_ratio              = spike_ratio
        self.revert_threshold         = revert_threshold
        self.spread_width             = spread_width
        self.dte_entry                = dte_entry
        self.max_hold_days            = max_hold_days
        self.profit_target_pct        = profit_target_pct
        self.position_size_pct        = position_size_pct
        self.commission_per_leg       = commission_per_leg
        self.min_days_between_trades  = min_days_between_trades

    # ── Helpers ────────────────────────────────────────────────────────────

    def _empty_result(self, capital: float) -> BacktestResult:
        eq = pd.Series([capital], dtype=float)
        return BacktestResult(
            strategy_name=self.name,
            equity_curve=eq,
            daily_returns=pd.Series(dtype=float),
            trades=pd.DataFrame(
                columns=[
                    "entry_date", "exit_date", "entry_price", "atm_strike",
                    "otm_strike", "entry_debit", "exit_value", "contracts",
                    "pnl", "exit_reason", "vix_entry", "vix_exit",
                ]
            ),
            metrics={},
            params=self.get_params(),
        )

    @staticmethod
    def _spread_value(spot: float, k_long: float, k_short: float,
                      t_years: float, iv: float) -> float:
        """Current B-S value of long call spread (long k_long, short k_short)."""
        if t_years <= 0.0:
            # At expiry: intrinsic value
            return max(0.0, min(spot - k_long, k_short - k_long))
        long_val  = bs_price(spot, k_long,  t_years, _RISK_FREE_RATE, iv, "call")
        short_val = bs_price(spot, k_short, t_years, _RISK_FREE_RATE, iv, "call")
        return max(0.0, long_val - short_val)

    # ── Signal (live) ──────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Check VIX spike conditions from a live market snapshot.
        market_snapshot expected keys:
          price          — current spot price of the trading instrument
          vix            — current VIX level
          vix_20d_avg    — (optional) 20-day rolling average of VIX
          ma_200d        — (optional) 200-day MA of price; defaults to price
          benchmark_price — alias accepted but 'price' takes precedence
        Legacy key spy_price is still accepted for backward compatibility.
        """
        vix         = float(market_snapshot.get("vix", 0.0))
        # Accept 'price' (preferred), then legacy 'spy_price', then 0
        spot        = float(
            market_snapshot.get("price")
            or market_snapshot.get("spy_price")
            or 0.0
        )
        _vix_20d_raw = market_snapshot.get("vix_20d_avg")
        # If vix_20d_avg is absent, defaulting to current vix makes vix > vix*1.3
        # always False (silent failure). Use None and relax to threshold-only check.
        vix_20d_avg = float(_vix_20d_raw) if _vix_20d_raw is not None else None
        # Explicit key-presence check: 0.0 is a valid sentinel for "not enough history"
        # Cannot use `or` here because 0.0 is falsy and would be skipped.
        if "ma_200d" in market_snapshot and market_snapshot["ma_200d"] is not None:
            ma_200d = float(market_snapshot["ma_200d"])
        elif "spy_200d_ma" in market_snapshot and market_snapshot["spy_200d_ma"] is not None:
            ma_200d = float(market_snapshot["spy_200d_ma"])
        else:
            ma_200d = float(spot)

        if vix_20d_avg is not None:
            spike_cond = (vix > self.spike_threshold and
                          vix > vix_20d_avg * self.spike_ratio)
        else:
            # No 20d avg — only require absolute VIX threshold
            spike_cond = vix > self.spike_threshold
        # ma_200d == 0.0 means not enough data — skip the check (don't auto-pass)
        regime_ok   = (ma_200d > 0.0 and spot >= ma_200d * 0.95)

        if spike_cond and regime_ok and spot > 0:
            # Quick debit estimate for confidence / sizing
            t_years  = self.dte_entry / 365.0
            iv       = vix / 100.0
            k_long   = round(spot)           # nearest dollar ATM
            k_short  = k_long + self.spread_width
            debit    = self._spread_value(spot, k_long, k_short, t_years, iv)
            signal   = "BUY"
            conf     = min(0.95, (vix - self.spike_threshold) / self.spike_threshold + 0.5)
            meta     = {
                "vix": vix,
                "vix_20d_avg": vix_20d_avg,
                "k_long": k_long,
                "k_short": k_short,
                "estimated_debit": round(debit, 4),
                "reason": "VIX spike detected — not a regime break" + (
                    "" if vix_20d_avg is not None else " (no 20d avg in snapshot, ratio check skipped)"
                ),
            }
        else:
            signal  = "HOLD"
            conf    = 0.0
            meta    = {
                "vix": vix,
                "spike_cond": spike_cond,
                "regime_ok": regime_ok,
                "reason": "conditions not met",
            }

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=conf,
            position_size_pct=self.position_size_pct if signal == "BUY" else 0.0,
            metadata=meta,
        )

    # ── Backtest ───────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data: pd.DataFrame,
        auxiliary_data: dict,
        starting_capital: float = 100_000,
        # UI-overridable params
        spike_threshold: float | None = None,
        revert_threshold: float | None = None,
        spread_width: float | None = None,
        spike_ratio: float | None = None,
        max_hold_days: int | None = None,
        profit_target_pct: float | None = None,
        **kwargs,
    ) -> BacktestResult:

        # ── Resolve params (UI sliders can override constructor) ──────────
        spk_thr   = spike_threshold   if spike_threshold   is not None else self.spike_threshold
        rev_thr   = revert_threshold  if revert_threshold  is not None else self.revert_threshold
        sw        = spread_width      if spread_width       is not None else self.spread_width
        s_ratio   = spike_ratio       if spike_ratio        is not None else self.spike_ratio
        max_hold  = max_hold_days     if max_hold_days      is not None else self.max_hold_days
        pt_pct    = profit_target_pct if profit_target_pct  is not None else self.profit_target_pct

        # ── Prepare price data ────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)

        if price_data.empty or len(price_data) < 210:
            return self._empty_result(starting_capital)

        close = price_data["close"].astype(float)

        # ── VIX data ──────────────────────────────────────────────────────
        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if isinstance(vix_df, pd.DataFrame) and not vix_df.empty:
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)
            vix = vix_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False).fillna(20.0)
        else:
            raise ValueError(
                "No VIX data found. Go to Data Manager → Macro Bars and sync VIX first."
            )

        # ── Derived indicators ────────────────────────────────────────────
        vix_20d_avg = vix.rolling(20, min_periods=10).mean()
        ma_200d     = close.rolling(200, min_periods=100).mean()

        # ── Simulation state ──────────────────────────────────────────────
        capital          = float(starting_capital)
        equity_list      = []     # one entry per trading day
        trades_list      = []

        # Open trade state (None when flat)
        open_trade       = None   # dict when a trade is open
        days_since_exit  = self.min_days_between_trades  # start ready to trade

        all_dates = list(price_data.index)
        N         = len(all_dates)

        for i, dt in enumerate(all_dates):
            spot     = float(close.iloc[i])
            vix_val  = float(vix.iloc[i])
            vix_avg  = float(vix_20d_avg.iloc[i]) if not np.isnan(vix_20d_avg.iloc[i]) else vix_val
            ma200    = float(ma_200d.iloc[i])      if not np.isnan(ma_200d.iloc[i])      else spot

            # ── Manage open trade ─────────────────────────────────────────
            if open_trade is not None:
                days_held = (dt - open_trade["entry_date"]).days
                t_rem     = max(0.0, (open_trade["expiry_date"] - dt).days / 365.0)
                iv_cur    = vix_val / 100.0

                cur_val = self._spread_value(
                    spot,
                    open_trade["k_long"],
                    open_trade["k_short"],
                    t_rem,
                    iv_cur,
                )

                # Exit conditions
                exit_reason = None
                if vix_val < rev_thr:
                    exit_reason = "vix_reversion"
                elif cur_val >= open_trade["entry_debit"] * (1.0 + pt_pct):
                    exit_reason = "profit_target"
                elif days_held >= max_hold:
                    exit_reason = "time_stop"

                if exit_reason:
                    contracts = open_trade["contracts"]
                    gross_pnl = (cur_val - open_trade["entry_debit"]) * 100.0 * contracts
                    commissions = 2.0 * self.commission_per_leg * contracts  # exit legs
                    net_pnl   = gross_pnl - commissions
                    capital   += net_pnl

                    trades_list.append({
                        "entry_date":   open_trade["entry_date"].date(),
                        "exit_date":    dt.date(),
                        "entry_price":  round(open_trade["entry_price"], 2),
                        "atm_strike":   open_trade["k_long"],
                        "otm_strike":   open_trade["k_short"],
                        "entry_debit":  round(open_trade["entry_debit"], 4),
                        "exit_value":   round(cur_val, 4),
                        "contracts":    contracts,
                        "pnl":          round(net_pnl, 2),
                        "exit_reason":  exit_reason,
                        "vix_entry":    round(open_trade["vix_entry"], 2),
                        "vix_exit":     round(vix_val, 2),
                    })

                    open_trade      = None
                    days_since_exit = 0

            # ── Check for new entry ───────────────────────────────────────
            if open_trade is None:
                days_since_exit += 1

                spike_cond  = (vix_val > spk_thr and vix_val > vix_avg * s_ratio)
                regime_ok   = (spot >= ma200 * 0.95)
                cooldown_ok = (days_since_exit >= self.min_days_between_trades)
                # Need at least 200 days of history for MA to be meaningful
                has_history = (i >= 200)

                if spike_cond and regime_ok and cooldown_ok and has_history:
                    # Price the spread
                    t_entry = self.dte_entry / 365.0
                    iv_now  = vix_val / 100.0
                    k_long  = float(round(spot))       # ATM — nearest $1
                    k_short = k_long + sw

                    entry_debit = self._spread_value(spot, k_long, k_short, t_entry, iv_now)

                    if entry_debit > 0.01:   # sanity: spread must have positive cost
                        max_loss    = entry_debit * 100.0   # per contract
                        contracts   = max(1, math.floor(
                            capital * self.position_size_pct / max_loss
                        ))
                        # Deduct cost from capital
                        entry_cost  = entry_debit * 100.0 * contracts
                        entry_comm  = 2.0 * self.commission_per_leg * contracts  # entry legs
                        capital    -= (entry_cost + entry_comm)

                        import datetime
                        expiry_date = dt + pd.Timedelta(days=self.dte_entry)

                        open_trade = {
                            "entry_date":  dt,
                            "expiry_date": expiry_date,
                            "entry_price": spot,
                            "k_long":      k_long,
                            "k_short":     k_short,
                            "entry_debit": entry_debit,
                            "contracts":   contracts,
                            "vix_entry":   vix_val,
                        }
                        days_since_exit = 0

            # Mark-to-market: add current value of any open debit spread
            if open_trade is not None:
                t_rem_mtm = max(0.0, (open_trade["expiry_date"] - dt).days / 365.0)
                mtm_val   = self._spread_value(
                    spot,
                    open_trade["k_long"],
                    open_trade["k_short"],
                    t_rem_mtm,
                    vix_val / 100.0,
                )
                equity_list.append(capital + mtm_val * open_trade["contracts"] * 100.0)
            else:
                equity_list.append(capital)

        # ── Close any trade still open at end of period ───────────────────
        if open_trade is not None:
            last_dt    = all_dates[-1]
            last_spot  = float(close.iloc[-1])
            last_vix   = float(vix.iloc[-1])
            t_rem      = max(0.0, (open_trade["expiry_date"] - last_dt).days / 365.0)
            cur_val    = self._spread_value(
                last_spot,
                open_trade["k_long"],
                open_trade["k_short"],
                t_rem,
                last_vix / 100.0,
            )
            contracts   = open_trade["contracts"]
            gross_pnl   = (cur_val - open_trade["entry_debit"]) * 100.0 * contracts
            commissions = 2.0 * self.commission_per_leg * contracts
            net_pnl     = gross_pnl - commissions
            capital    += net_pnl
            equity_list[-1] = capital

            trades_list.append({
                "entry_date":   open_trade["entry_date"].date(),
                "exit_date":    last_dt.date(),
                "entry_price":  round(open_trade["entry_price"], 2),
                "atm_strike":   open_trade["k_long"],
                "otm_strike":   open_trade["k_short"],
                "entry_debit":  round(open_trade["entry_debit"], 4),
                "exit_value":   round(cur_val, 4),
                "contracts":    contracts,
                "pnl":          round(net_pnl, 2),
                "exit_reason":  "end_of_period",
                "vix_entry":    round(open_trade["vix_entry"], 2),
                "vix_exit":     round(last_vix, 2),
            })

        # ── Build outputs ─────────────────────────────────────────────────
        equity    = pd.Series(equity_list, index=price_data.index, dtype=float)
        daily_ret = equity.pct_change().dropna()
        bh_ret    = close.pct_change().reindex(equity.index).dropna()

        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(
            columns=[
                "entry_date", "exit_date", "entry_price", "atm_strike",
                "otm_strike", "entry_debit", "exit_value", "contracts",
                "pnl", "exit_reason", "vix_entry", "vix_exit",
            ]
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
            params=self.get_params(),
            extra={
                "vix":             vix,
                "vix_20d_avg":     vix_20d_avg,
                "ma_200d":         ma_200d,
                "benchmark_ret":   bh_ret,
            },
        )

    # ── UI params ──────────────────────────────────────────────────────────

    def get_backtest_ui_params(self) -> list:
        return [
            {
                "key": "spike_threshold",
                "label": "VIX spike threshold",
                "type": "slider", "min": 20, "max": 40, "default": 25, "step": 1,
                "col": 0, "row": 0,
                "help": "VIX must exceed this level to qualify as a spike",
            },
            {
                "key": "spike_ratio",
                "label": "VIX / 20-day avg ratio",
                "type": "slider", "min": 1.1, "max": 2.0, "default": 1.3, "step": 0.05,
                "col": 1, "row": 0,
                "help": "VIX must be this multiple above its 20-day rolling average",
            },
            {
                "key": "revert_threshold",
                "label": "VIX reversion target",
                "type": "slider", "min": 15, "max": 25, "default": 22, "step": 1,
                "col": 2, "row": 0,
                "help": "Close the spread when VIX drops back below this level",
            },
            {
                "key": "spread_width",
                "label": "Call spread width ($)",
                "type": "slider", "min": 2, "max": 10, "default": 5, "step": 1,
                "col": 0, "row": 1,
                "help": "Distance between long and short call strikes in dollars",
            },
            {
                "key": "max_hold_days",
                "label": "Max hold (days)",
                "type": "slider", "min": 5, "max": 21, "default": 15, "step": 1,
                "col": 1, "row": 1,
                "help": "Time stop — force-close after this many calendar days",
            },
            {
                "key": "profit_target_pct",
                "label": "Profit target (% of debit)",
                "type": "slider", "min": 0.25, "max": 1.0, "default": 0.50, "step": 0.05,
                "col": 2, "row": 1,
                "help": "Close early when spread value exceeds entry debit × (1 + this)",
            },
        ]

    def get_params(self) -> dict:
        return {
            "spike_threshold":         self.spike_threshold,
            "spike_ratio":             self.spike_ratio,
            "revert_threshold":        self.revert_threshold,
            "spread_width":            self.spread_width,
            "dte_entry":               self.dte_entry,
            "max_hold_days":           self.max_hold_days,
            "profit_target_pct":       self.profit_target_pct,
            "position_size_pct":       self.position_size_pct,
            "commission_per_leg":      self.commission_per_leg,
            "min_days_between_trades": self.min_days_between_trades,
        }
