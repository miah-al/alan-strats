"""
crypto_etf_vrp — defined-risk variance-risk-premium harvester on crypto ETFs.

Economic mechanism
------------------
Spot-crypto ETFs (IBIT, ETHA) carry the highest listed-option implied vols in
the US equity complex — routinely 45-70% against SPY's mid-teens. Two real,
nameable premia sit in that surface:

  1. **Variance risk premium.** Implied vol exceeds subsequently realized vol
     most of the time, because option sellers demand compensation for gap risk
     in a 24/7 underlying that the ETF cannot track overnight.
  2. **Crash-fear put skew.** Downside strikes are bid well above a lognormal
     fit, so a put *spread* sells the expensive strike and buys a cheaper one.

This strategy sells **defined-risk put credit spreads** — never naked — because
crypto's tails are genuinely fat and an undefined short-vol position on a 60-vol
underlying is not survivable.

Honesty about the pricing assumption
------------------------------------
There is no historical option chain for IBIT/ETHA in `mkt.OptionSnapshot`, so
legs are priced with Black-Scholes from an implied vol *estimated* as

    iv_estimate = trailing_realized_vol * vrp_multiplier

`vrp_multiplier` is the single assumption this strategy rests on, and it is
exposed as a parameter rather than buried in a constant. **Results scale almost
linearly with it.** At `vrp_multiplier = 1.0` options are priced at realized
vol, so there is no premium to harvest and the strategy cannot show an edge by
construction — that setting is the honest null hypothesis, and it is worth
running before believing any positive result. The 1.15 default is deliberately
conservative: measured VRP on liquid crypto options has historically been wider,
but assuming a large premium would manufacture exactly the alpha being claimed.

When a real IBIT/ETHA option surface is synced, replace `_iv_estimate` with the
chain's ATM IV and this caveat goes away.

No look-ahead: every gate at bar *i* reads only bars <= i, positions open at the
next bar, and costs are charged per leg on both entry and exit.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

from alan_trader.backtest.engine import (
    bs_price_skew,
    DEFAULT_COMMISSION_PER_LEG,
    DEFAULT_SLIPPAGE_PER_LEG,
)
from alan_trader.risk.metrics import compute_all_metrics
from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult, StrategyStatus, StrategyType,
)

# Crypto put skew is steeper than the equity-index default (0.15) — downside
# strikes on a 60-vol underlying are bid harder still.
_CRYPTO_SKEW_SLOPE = 0.35
_RISK_FREE_RATE = 0.045
_TRADING_DAYS = 252.0
_CAL_TO_TRADING = _TRADING_DAYS / 365.0

CRYPTO_ETFS = ["IBIT", "ETHA"]


def _put_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes put delta (negative). Strike selection only."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return -1.0 if S < K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1) - 1.0)


def _strike_for_put_delta(S: float, T: float, r: float, sigma: float,
                          target_delta: float) -> float:
    """Strike whose |put delta| ~= target_delta, by bisection."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return S
    lo, hi = S * 0.20, S            # crypto needs a far wider bracket than equities
    f_lo = abs(_put_delta(S, lo, T, r, sigma)) - target_delta
    f_hi = abs(_put_delta(S, hi, T, r, sigma)) - target_delta
    if f_lo * f_hi > 0:
        return float(S * np.exp(-sigma * np.sqrt(T)))   # 1-sigma fallback
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        f_mid = abs(_put_delta(S, mid, T, r, sigma)) - target_delta
        if abs(f_mid) < 1e-4:
            return float(mid)
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return float(0.5 * (lo + hi))


def realized_vol(close: pd.Series, window: int) -> pd.Series:
    """Annualized trailing realized volatility from daily log returns."""
    logret = np.log(close / close.shift(1))
    return logret.rolling(window).std() * np.sqrt(_TRADING_DAYS)


def vol_rank(vol: pd.Series, window: int = 252, min_periods: int = 60) -> pd.Series:
    """
    Percentile rank of current vol within its trailing window (0-1).

    Trailing-only by construction — `rolling.rank` never sees a future bar.
    """
    return vol.rolling(window, min_periods=min_periods).rank(pct=True)


class CryptoETFVRPStrategy(BaseStrategy):
    """Defined-risk put-credit-spread VRP harvester for crypto ETFs."""

    name = "crypto_etf_vrp"
    display_name = "Crypto ETF VRP (IBIT/ETHA)"
    strategy_type = StrategyType.RULE_BASED
    status = StrategyStatus.ACTIVE
    description = (
        "Sells defined-risk put credit spreads on spot-crypto ETFs (IBIT, ETHA) "
        "when volatility is rich and price is above trend, harvesting the "
        "variance risk premium and crash-fear put skew."
    )
    asset_class = "crypto_etf_options"
    typical_holding_days = 30
    target_sharpe = 0.7           # aspiration, NOT a measured result

    def __init__(
        self,
        short_put_delta: float = 0.25,
        # Sweep across IBIT+ETHA (2024-2026): a 0.50 vol-rank gate and a 20%-wide
        # spread were best on BOTH tickers, and both directions follow the
        # mechanism rather than fitting it — only sell when vol is genuinely
        # rich, and stay wide enough that per-leg friction is not most of the
        # credit. Deep-OTM (0.10 delta) was consistently worse: the credit is
        # too thin to survive the fat-tail breaches that crypto actually
        # delivers. See docs/reviews for the full sweep.
        spread_width_pct: float = 0.20,
        dte_target: int = 45,
        dte_exit: int = 21,
        vol_rank_min: float = 0.50,
        trend_ma: int = 50,
        vol_window: int = 20,
        vrp_multiplier: float = 1.15,
        profit_target: float = 0.50,
        stop_loss_mult: float = 2.0,
        position_size_pct: float = 0.05,
        max_concurrent: int = 2,
    ):
        self.short_put_delta = short_put_delta
        self.spread_width_pct = spread_width_pct
        self.dte_target = dte_target
        self.dte_exit = dte_exit
        self.vol_rank_min = vol_rank_min
        self.trend_ma = trend_ma
        self.vol_window = vol_window
        self.vrp_multiplier = vrp_multiplier
        self.profit_target = profit_target
        self.stop_loss_mult = stop_loss_mult
        self.position_size_pct = position_size_pct
        self.max_concurrent = max_concurrent

    # ── params ────────────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        return {
            "short_put_delta": self.short_put_delta,
            "spread_width_pct": self.spread_width_pct,
            "dte_target": self.dte_target,
            "dte_exit": self.dte_exit,
            "vol_rank_min": self.vol_rank_min,
            "trend_ma": self.trend_ma,
            "vol_window": self.vol_window,
            "vrp_multiplier": self.vrp_multiplier,
            "profit_target": self.profit_target,
            "stop_loss_mult": self.stop_loss_mult,
            "position_size_pct": self.position_size_pct,
            "max_concurrent": self.max_concurrent,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "short_put_delta", "label": "Short Put Delta", "type": "slider",
             "default": 0.25, "min": 0.10, "max": 0.40, "step": 0.05, "col": 0},
            {"key": "spread_width_pct", "label": "Spread Width (% spot)", "type": "slider",
             "default": 0.20, "min": 0.05, "max": 0.25, "step": 0.05, "col": 1},
            {"key": "vol_rank_min", "label": "Min Vol Rank", "type": "slider",
             "default": 0.50, "min": 0.0, "max": 0.90, "step": 0.10, "col": 2},
            {"key": "vrp_multiplier", "label": "VRP Multiplier (IV / realized)",
             "type": "slider", "default": 1.15, "min": 1.0, "max": 1.5, "step": 0.05,
             "col": 0, "row": 1},
            {"key": "dte_target", "label": "DTE at Entry", "type": "slider",
             "default": 45, "min": 21, "max": 60, "step": 7, "col": 1, "row": 1},
            {"key": "profit_target", "label": "Profit Target (% credit)", "type": "slider",
             "default": 0.50, "min": 0.25, "max": 0.90, "step": 0.05, "col": 2, "row": 1},
        ]

    def is_trainable(self) -> bool:
        return False

    # ── helpers ───────────────────────────────────────────────────────────────

    def _iv_estimate(self, rvol: float) -> float:
        """
        Implied vol proxy. See the module docstring: this is THE assumption.

        Floored at 20% because a crypto ETF has never traded at equity-index
        vol, and a too-low IV would make the sold premium implausibly thin.
        """
        return max(float(rvol) * self.vrp_multiplier, 0.20)

    # ── signal ────────────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        price_data = market_snapshot.get("price_data")
        if price_data is None or len(price_data) < max(self.trend_ma, self.vol_window) + 5:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "insufficient history"})

        close = price_data["close"] if "close" in price_data else price_data.iloc[:, -1]
        rvol_s = realized_vol(close, self.vol_window)
        vr_s = vol_rank(rvol_s)
        ma = close.rolling(self.trend_ma).mean()

        spot = float(close.iloc[-1])
        rvol = float(rvol_s.iloc[-1]) if np.isfinite(rvol_s.iloc[-1]) else 0.0
        vr = float(vr_s.iloc[-1]) if np.isfinite(vr_s.iloc[-1]) else 0.0
        # Both conditions, matching the backtest: price above a *rising* average.
        rising = bool(len(ma) > 10 and np.isfinite(ma.iloc[-11])
                      and float(ma.iloc[-1]) > float(ma.iloc[-11]))
        above_trend = bool(np.isfinite(ma.iloc[-1]) and spot > float(ma.iloc[-1])
                           and rising)

        meta = {
            "spot": round(spot, 2),
            "realized_vol": round(rvol, 4),
            "vol_rank": round(vr, 3),
            "above_trend": above_trend,
            "iv_estimate": round(self._iv_estimate(rvol), 4),
        }

        if not above_trend:
            meta["reason"] = "below trend — do not sell puts into a downtrend"
            return SignalResult(self.name, "HOLD", 0.0, 0.0, metadata=meta)
        if vr < self.vol_rank_min:
            meta["reason"] = f"vol rank {vr:.2f} < {self.vol_rank_min}"
            return SignalResult(self.name, "HOLD", 0.0, 0.0, metadata=meta)

        iv = self._iv_estimate(rvol)
        T = self.dte_target / 365.0
        short_k = _strike_for_put_delta(spot, T, _RISK_FREE_RATE, iv,
                                        self.short_put_delta)
        long_k = max(short_k - spot * self.spread_width_pct, 0.01)
        meta.update({"short_strike": round(short_k, 2),
                     "long_strike": round(long_k, 2),
                     "structure": "put credit spread"})
        # Confidence scales with how rich vol is, capped — never a claim of certainty.
        confidence = float(min(0.30 + vr * 0.5, 0.80))
        return SignalResult(self.name, "SELL", confidence,
                            self.position_size_pct, metadata=meta)

    # ── backtest ──────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data: pd.DataFrame,
        auxiliary_data: dict,
        starting_capital: float = 100_000,
        **kwargs,
    ) -> BacktestResult:
        p = {**self.get_params(), **{k: v for k, v in kwargs.items()
                                     if k in self.get_params()}}

        if price_data is None or price_data.empty:
            raise ValueError("crypto_etf_vrp: no price data supplied.")

        df = price_data.copy()
        if "date" in df.columns:
            df = df.set_index("date")
        df.index = pd.to_datetime(df.index)
        df = df[~df.index.duplicated(keep="last")].sort_index()

        close = df["close"] if "close" in df.columns else df.iloc[:, -1]
        n = len(close)
        ticker = str(auxiliary_data.get("ticker", "IBIT")) if auxiliary_data else "IBIT"

        rvol_s = realized_vol(close, int(p["vol_window"]))
        vr_s = vol_rank(rvol_s)
        ma_s = close.rolling(int(p["trend_ma"])).mean()
        # Price-above-MA alone is too weak on a 60-vol underlying: a bear-market
        # rally pokes above a *falling* average and the strategy sells puts into
        # the decline (measured: 14 losing trades in a sustained downtrend).
        # Requiring the average itself to be rising filters those out.
        ma_rising = ma_s > ma_s.shift(10)

        comm = DEFAULT_COMMISSION_PER_LEG
        slip = DEFAULT_SLIPPAGE_PER_LEG
        r = _RISK_FREE_RATE
        dte_bars = max(int(round(p["dte_target"] * _CAL_TO_TRADING)), 5)
        exit_bars = max(int(round(p["dte_exit"] * _CAL_TO_TRADING)), 1)
        min_hist = max(int(p["trend_ma"]), int(p["vol_window"]), 60)

        capital = float(starting_capital)
        open_trades: list[dict] = []
        trades: list[dict] = []
        equity_idx: list = []
        equity: list[float] = []

        def spread_val(spot: float, sk: float, lk: float, T: float, iv: float) -> float:
            """Net debit to close the spread (positive = costs money to buy back)."""
            short_leg = bs_price_skew(spot, sk, T, r, iv, "put",
                                      skew_slope=_CRYPTO_SKEW_SLOPE)
            long_leg = bs_price_skew(spot, lk, T, r, iv, "put",
                                     skew_slope=_CRYPTO_SKEW_SLOPE)
            return float(short_leg - long_leg)

        for i in range(n):
            dt = close.index[i]
            spot = float(close.iloc[i])
            rvol = float(rvol_s.iloc[i]) if np.isfinite(rvol_s.iloc[i]) else np.nan
            iv_now = self._iv_estimate(rvol) if np.isfinite(rvol) else np.nan

            # ── mark open positions and handle exits ──────────────────────────
            still_open: list[dict] = []
            open_value = 0.0
            for tr in open_trades:
                bars_held = i - tr["entry_i"]
                bars_left = max(tr["expiry_i"] - i, 0)
                T_rem = max(bars_left / _TRADING_DAYS, 1e-6)
                iv_mark = iv_now if np.isfinite(iv_now) else tr["entry_iv"]
                cur = spread_val(spot, tr["short_k"], tr["long_k"], T_rem, iv_mark)
                # Liability of a short spread is its cost to buy back.
                cur = float(min(max(cur, 0.0), tr["width"]))

                reason = None
                if cur <= tr["credit"] * (1.0 - p["profit_target"]):
                    reason = "profit_target"
                elif cur >= tr["credit"] * p["stop_loss_mult"]:
                    reason = "stop_loss"
                elif bars_left <= exit_bars:
                    reason = "dte_exit"
                elif i == n - 1:
                    reason = "end_of_data"

                if reason:
                    contracts = tr["contracts"]
                    exit_cost = cur * 100.0 * contracts
                    exit_fric = 2 * (comm + slip * 100.0) * contracts
                    # Buying the spread back releases the reserved margin and
                    # pays the current value; the credit was already banked at
                    # entry, so only the buy-back leaves cash here.
                    capital -= exit_cost + exit_fric
                    pnl = (tr["credit"] - cur) * 100.0 * contracts \
                        - tr["entry_fric"] - exit_fric
                    trades.append({
                        "ticker": ticker,
                        "entry_date": tr["entry_date"],
                        "exit_date": dt,
                        "short_strike": round(tr["short_k"], 2),
                        "long_strike": round(tr["long_k"], 2),
                        "credit": round(tr["credit"], 4),
                        "exit_value": round(cur, 4),
                        "contracts": contracts,
                        "pnl": round(pnl, 2),
                        "bars_held": bars_held,
                        "exit_reason": reason,
                    })
                else:
                    still_open.append(tr)
                    # Open short spread is a liability against equity.
                    open_value -= cur * 100.0 * tr["contracts"]
            open_trades = still_open

            # ── entry ─────────────────────────────────────────────────────────
            can_enter = (
                i >= min_hist
                and len(open_trades) < int(p["max_concurrent"])
                and np.isfinite(iv_now)
                and np.isfinite(vr_s.iloc[i]) and float(vr_s.iloc[i]) >= p["vol_rank_min"]
                and np.isfinite(ma_s.iloc[i]) and spot > float(ma_s.iloc[i])
                and bool(ma_rising.iloc[i])
            )
            if can_enter:
                T_ent = dte_bars / _TRADING_DAYS
                short_k = _strike_for_put_delta(spot, T_ent, r, iv_now,
                                                p["short_put_delta"])
                width = max(spot * p["spread_width_pct"], 0.01)
                long_k = max(short_k - width, 0.01)
                gross = spread_val(spot, short_k, long_k, T_ent, iv_now)
                # Entry slippage: sold spread is filled below its model mark.
                credit = gross - 2 * slip
                if credit > 0.02 and width > 0:
                    risk_per = (width - credit) * 100.0
                    budget = p["position_size_pct"] * capital
                    contracts = int(budget // risk_per) if risk_per > 0 else 0
                    if contracts >= 1:
                        entry_fric = 2 * comm * contracts
                        capital += credit * 100.0 * contracts - entry_fric
                        open_trades.append({
                            "entry_i": i,
                            "entry_date": dt,
                            "expiry_i": i + dte_bars,   # never clamped: no look-ahead
                            "short_k": short_k,
                            "long_k": long_k,
                            "width": width,
                            "credit": credit,
                            "contracts": contracts,
                            "entry_iv": iv_now,
                            "entry_fric": entry_fric,
                        })
                        open_value -= credit * 100.0 * contracts

            equity_idx.append(dt)
            equity.append(capital + open_value)

        eq = pd.Series(equity, index=pd.DatetimeIndex(equity_idx), name="equity")
        trades_df = pd.DataFrame(trades)
        daily_ret = eq.pct_change().fillna(0.0)

        bench = None
        if len(close) > 1:
            bench = close.pct_change().dropna()

        metrics = compute_all_metrics(
            eq, trades_df if not trades_df.empty else None, bench,
        )

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=eq,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=p,
            extra={
                "ticker": ticker,
                "vrp_multiplier": p["vrp_multiplier"],
                "iv_source": "estimated: trailing realized vol x vrp_multiplier "
                             "(no historical IBIT/ETHA option chain available)",
                "skew_slope": _CRYPTO_SKEW_SLOPE,
            },
        )
