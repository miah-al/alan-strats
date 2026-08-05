"""
Bull Put Spread Strategy.

A defined-risk bullish income trade that collects premium by selling an OTM
put while buying a further OTM put as protection. The spread profits when
the underlying stays above the short put strike through expiration.

Entry rules (all must pass):
  • IVR ≥ ivr_min (40% default) — elevated IV inflates premium collected
  • Price > 50-day MA — bullish bias confirmation
  • ADX ≤ adx_max (40 default) — avoid the most extreme momentum regimes
  • VIX ≤ vix_max (35 default) — not in panic regime
  • Credit ≥ 15% of spread width — realistic reward-to-risk floor (a
    30-delta/5%-wide spread collects ~15-22% under skew-adjusted BS)

Structure:
  • Sell OTM put at ~delta 0.30 (short strike, BS delta inversion)
  • Buy further OTM put `spread_width_pct × spot` below (long strike, protection)
  • Expiry: 21–45 DTE (target 30)

Exit (checked daily, first trigger wins):
  • 50% of max credit (profit target)
  • cost-to-close ≥ stop_loss_mult × credit (stop loss)
  • dte_exit DTE time exit to avoid gamma risk
  • end of data

Realism (mirrors ivr_credit_spread, the validated credit-spread engine):
  • Legs are priced with the engine's equity-index volatility SKEW
    (bs_price_skew) so the OTM short put carries higher IV than the flat
    VIX-implied ATM level — never a fabricated `vol × √T × Δ` proxy.
  • BOTH commission (DEFAULT_COMMISSION_PER_LEG, $/contract) and slippage
    (DEFAULT_SLIPPAGE_PER_LEG, BS-mark units) are charged per leg × contracts
    on ENTRY and on EXIT — the round trip is never free.
  • Calendar DTE is converted to trading-day bars (× 252/365) so the simulated
    hold matches the quoted expiry instead of running ~45% too long.
  • Walk-forward, single open position, MTM equity each bar — no look-ahead:
    every series read at bar i uses only data up to and including i.

Data: this strategy derives IV from the VIX proxy + reconstructs IVR/ADX from
the price/VIX series it is handed. It does NOT consume mkt.OptionSnapshot, so
it needs no backtest_loaders entry (run_loaders_for returns empty aux and the
harness still supplies auxiliary_data['vix']).
"""

import math
import numpy as np
import pandas as pd
from typing import Optional

from scipy.stats import norm

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)
from alan_trader.strategies.indicators import compute_ivr, compute_adx
from alan_trader.backtest.engine import (
    bs_price_skew,
    DEFAULT_SLIPPAGE_PER_LEG, DEFAULT_COMMISSION_PER_LEG, DEFAULT_SKEW_SLOPE,
)
from alan_trader.risk.metrics import compute_all_metrics


# ── Constants ─────────────────────────────────────────────────────────────────

_RISK_FREE_RATE        = 0.045   # proxy for 3-month T-Bill
_SKEW_SLOPE            = DEFAULT_SKEW_SLOPE   # equity-index downside skew
_TRADING_DAYS_PER_YEAR = 252.0
_CAL_TO_TRADING        = _TRADING_DAYS_PER_YEAR / 365.0   # ≈ 0.690


def _bs_put_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes put delta (negative). Used only for strike selection."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return -1.0 if S < K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1) - 1.0)


def _short_put_strike_for_delta(S: float, T: float, r: float, sigma: float,
                                target_delta: float) -> float:
    """Strike K such that |put delta(K)| ≈ target_delta, via bisection.

    target_delta is positive (e.g. 0.30 for a 30-delta put). Falls back to a
    1-sigma down move if the search fails. Closed-form would invert N(d1) but a
    short bisection keeps this dependency-light and is exact enough at $1 strikes.
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return S
    lo, hi = S * 0.50, S          # OTM put strike is below spot
    f_lo = abs(_bs_put_delta(S, lo, T, r, sigma)) - target_delta
    f_hi = abs(_bs_put_delta(S, hi, T, r, sigma)) - target_delta
    if f_lo * f_hi > 0:
        # No sign change in bracket → 1-sigma fallback.
        return float(S * np.exp(-sigma * np.sqrt(T)))
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        f_mid = abs(_bs_put_delta(S, mid, T, r, sigma)) - target_delta
        if abs(f_mid) < 1e-4:
            return float(mid)
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return float(0.5 * (lo + hi))


class BullPutSpreadStrategy(BaseStrategy):
    name          = "bull_put_spread"
    display_name  = "Bull Put Spread"
    strategy_type = StrategyType.RULE_BASED
    status        = StrategyStatus.ACTIVE
    description   = (
        "Sells OTM put spread to collect premium in bullish markets. "
        "IVR > 40%, price above 50-MA. Credit ≥ 15% of width. 50% buyback target."
    )
    asset_class          = "equities_options"
    typical_holding_days = 30
    target_sharpe        = 1.3

    _DEFAULTS = {
        "ivr_min":          0.40,
        # ADX measures trend STRENGTH, not direction. On daily SPY this
        # compute_adx runs hot (median ~31), and the IVR≥40% spikes that gate
        # entry coincide with strong moves, so adx_max=30 rejected EVERY
        # qualifying bull-put window (0 trades). 40 still excludes the top ~25%
        # most violent trends while admitting real entries.
        "adx_max":          40.0,
        "vix_max":          35.0,
        "short_put_delta":  0.30,   # short leg delta
        "spread_width_pct": 0.05,   # spread width as % of spot
        # Minimum net-credit-to-width. A 30-delta short put with a 5%-wide wing
        # collects ~15-22% of width under skew-adjusted BS (see the guide's
        # worked example: 12.5% acceptable, 17.5% better, 1/3 only at IVR 65%+).
        # The old 0.30 default was mathematically unreachable with these strikes
        # and silently produced ZERO trades; 0.15 is the realistic floor.
        "min_credit_ratio": 0.15,   # credit must be ≥ 15% of width
        "dte_target":       30,     # target DTE at entry (calendar days)
        "dte_exit":         21,     # close regardless at this DTE
        "profit_target":    0.50,   # close at 50% of max credit
        "stop_loss_mult":   2.0,    # stop when cost-to-close ≥ 2× credit
        "ma_period":        50,     # SMA period for trend filter
        "position_size_pct": 0.03,  # capital fraction risked per trade
        "commission_per_leg": DEFAULT_COMMISSION_PER_LEG,
        "slippage_per_leg":   DEFAULT_SLIPPAGE_PER_LEG,
    }

    def get_params(self) -> dict:
        return dict(self._DEFAULTS)

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "ivr_min",          "label": "IVR min",          "type": "slider",
             "min": 0.20, "max": 0.70, "step": 0.05, "default": 0.40},
            {"key": "adx_max",          "label": "ADX max",          "type": "slider",
             "min": 15,   "max": 55,   "step": 1,    "default": 40},
            {"key": "vix_max",          "label": "VIX max",          "type": "slider",
             "min": 20,   "max": 50,   "step": 1,    "default": 35},
            {"key": "short_put_delta",  "label": "Short put delta",  "type": "slider",
             "min": 0.15, "max": 0.45, "step": 0.05, "default": 0.30},
            {"key": "spread_width_pct", "label": "Spread width %",   "type": "slider",
             "min": 0.02, "max": 0.10, "step": 0.01, "default": 0.05},
            {"key": "profit_target",    "label": "Profit target",    "type": "slider",
             "min": 0.25, "max": 0.70, "step": 0.05, "default": 0.50},
        ]

    # ── Live signal ──────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        spot   = market_snapshot.get("price", 0)
        ivr    = market_snapshot.get("ivr", 0)
        adx    = market_snapshot.get("adx", 0)
        vix    = market_snapshot.get("vix", 20)
        ma50   = market_snapshot.get("ma50", 0)
        atm_iv = market_snapshot.get("atm_iv", 0)
        p      = self._DEFAULTS

        trend_ok = (spot > ma50) if ma50 else True
        ivr_ok   = ivr >= p["ivr_min"]
        adx_ok   = adx <= p["adx_max"]
        vix_ok   = vix <= p["vix_max"]

        if not (ivr_ok and adx_ok and vix_ok and trend_ok and spot > 0):
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                {"reason": "Entry conditions not met"})

        iv = atm_iv or (vix / 100.0) or 0.25
        T  = p["dte_target"] / 365.0
        width      = round(spot * p["spread_width_pct"], 0)
        short_k    = _short_put_strike_for_delta(spot, T, _RISK_FREE_RATE, iv,
                                                 p["short_put_delta"])
        long_k     = max(short_k - width, 0.01)
        short_prem = bs_price_skew(spot, short_k, T, _RISK_FREE_RATE, iv, "put",
                                   skew_slope=_SKEW_SLOPE)
        long_prem  = bs_price_skew(spot, long_k,  T, _RISK_FREE_RATE, iv, "put",
                                   skew_slope=_SKEW_SLOPE)
        credit_est = (short_prem - long_prem) - 2 * p["slippage_per_leg"]
        credit_ratio = credit_est / width if width > 0 else 0

        if credit_ratio < p["min_credit_ratio"]:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                {"reason": f"Credit/width ratio {credit_ratio:.2f} < {p['min_credit_ratio']}"})

        confidence = float(np.clip(
            ivr * 0.5 + (1.0 - adx / p["adx_max"]) * 0.3 + 0.2, 0.3, 0.90))

        return SignalResult(
            self.name, "SELL", confidence,
            position_size_pct=p["position_size_pct"],
            metadata={
                "structure":     "bull_put_spread",
                "short_strike":  round(short_k, 2),
                "long_strike":   round(long_k, 2),
                "width":         width,
                "credit_est":    round(credit_est, 2),
                "credit_ratio":  round(credit_ratio, 3),
                "dte_target":    p["dte_target"],
                "ivr":           ivr,
                "adx":           adx,
            },
        )

    # ── Pricing helper ───────────────────────────────────────────────────────

    def _spread_cost_to_close(self, spot: float, short_K: float, long_K: float,
                              bars_to_expiry: int, atm_iv: float) -> float:
        """Cost to buy back the bull put spread, priced with equity-index skew.

        `bars_to_expiry` is in *trading-day* bars; the calendar-year fraction
        remaining is bars / 252. Cost = short put value − long put value (both
        same option type). Clamped ≥ 0 (a spread can never be worth < $0).
        """
        T = max(bars_to_expiry, 0) / _TRADING_DAYS_PER_YEAR
        short_v = bs_price_skew(spot, short_K, T, _RISK_FREE_RATE, atm_iv, "put",
                                skew_slope=_SKEW_SLOPE)
        long_v  = bs_price_skew(spot, long_K,  T, _RISK_FREE_RATE, atm_iv, "put",
                                skew_slope=_SKEW_SLOPE)
        return max(short_v - long_v, 0.0)

    # ── Backtest ─────────────────────────────────────────────────────────────

    def backtest(self, price_data: pd.DataFrame, auxiliary_data: dict,
                 starting_capital: float = 100_000,
                 params: Optional[dict] = None, **kwargs) -> BacktestResult:
        p = {**self._DEFAULTS, **(params or {})}
        # UI / harness may pass individual overrides as kwargs.
        for k in p:
            if k in kwargs and kwargs[k] is not None:
                p[k] = kwargs[k]

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        close = price_data["close"].astype(float)
        high  = price_data.get("high", close).astype(float)
        low   = price_data.get("low",  close).astype(float)

        # VIX → IV proxy, aligned to the price index (no look-ahead: reindex+ffill
        # only carries PAST observations forward).
        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if isinstance(vix_df, pd.DataFrame) and not vix_df.empty:
            vdf = vix_df.copy()
            vdf.index = pd.to_datetime(vdf.index)
            vix = vdf["close"].reindex(close.index).ffill().infer_objects(copy=False).fillna(20.0)
        elif isinstance(vix_df, pd.Series) and not vix_df.empty:
            vix = vix_df.copy()
            vix.index = pd.to_datetime(vix.index)
            vix = vix.reindex(close.index).ffill().fillna(20.0)
        else:
            vix = pd.Series(20.0, index=close.index)
        iv_proxy = vix / 100.0

        # Derived series — all causal (rolling windows look BACK only).
        ivr_s = compute_ivr(vix, window=252)
        adx_s = compute_adx(high, low, close, warmup_fill=20.0)
        ma_s  = close.rolling(p["ma_period"], min_periods=20).mean()

        comm  = p["commission_per_leg"]
        slip  = p["slippage_per_leg"]
        r     = _RISK_FREE_RATE
        dte_bars      = max(1, int(round(p["dte_target"] * _CAL_TO_TRADING)))
        dte_exit_bars = max(0, int(round(p["dte_exit"]   * _CAL_TO_TRADING)))

        capital  = float(starting_capital)
        trades   = []
        equity   = []
        in_trade = False
        trade    = {}
        n        = len(close)

        for i in range(n):
            dt    = close.index[i]
            spot  = float(close.iloc[i])
            iv_v  = float(iv_proxy.iloc[i])
            ivr_v = float(ivr_s.iloc[i]) if not np.isnan(ivr_s.iloc[i]) else np.nan
            adx_v = float(adx_s.iloc[i]) if not np.isnan(adx_s.iloc[i]) else 20.0
            vix_v = float(vix.iloc[i])
            ma_v  = float(ma_s.iloc[i]) if not np.isnan(ma_s.iloc[i]) else spot

            # ── 1. Manage open trade ──────────────────────────────────────
            if in_trade:
                bars_left = trade["expiry_idx"] - i
                cur_cost  = self._spread_cost_to_close(
                    spot, trade["short_K"], trade["long_K"], bars_left, iv_v)
                pnl_per   = trade["credit"] - cur_cost          # per share
                pnl_total = pnl_per * trade["contracts"] * 100

                exit_reason = None
                if pnl_per >= p["profit_target"] * trade["credit"]:
                    exit_reason = "profit_target"
                elif bars_left <= dte_exit_bars:
                    exit_reason = "dte_exit"
                elif cur_cost >= p["stop_loss_mult"] * trade["credit"]:
                    exit_reason = "stop_loss"
                elif i == n - 1:
                    exit_reason = "end_of_data"

                if exit_reason:
                    # Round-trip exit friction: commission + slippage, 2 legs.
                    close_cost = 2 * (comm + slip * 100) * trade["contracts"]
                    net_pnl = round(pnl_total - close_cost, 2)
                    capital += net_pnl
                    trades.append({
                        "entry_date":  trade["entry_date"].date(),
                        "exit_date":   dt.date(),
                        "spread_type": "bull_put",
                        "short_K":     round(trade["short_K"], 2),
                        "long_K":      round(trade["long_K"], 2),
                        "credit":      round(trade["credit"], 4),
                        "contracts":   trade["contracts"],
                        "pnl":         net_pnl,
                        "exit_value":  round(capital, 2),
                        "exit_reason": exit_reason,
                        "dte_held":    i - trade["entry_idx"],
                    })
                    in_trade = False
                    trade = {}

            # ── 2. Entry check ────────────────────────────────────────────
            if not in_trade:
                can_enter = (
                    i >= p["ma_period"]
                    and not np.isnan(ivr_v)
                    and ivr_v >= p["ivr_min"]
                    and adx_v <= p["adx_max"]
                    and vix_v <= p["vix_max"]
                    and spot > ma_v          # bullish bias
                    and iv_v > 0 and spot > 0
                    and (n - i) > dte_bars   # room to hold to expiry
                )
                if can_enter:
                    T_entry = p["dte_target"] / 365.0
                    width   = round(spot * p["spread_width_pct"], 0)
                    if width < 0.50:
                        equity.append(capital)
                        continue
                    short_K = _short_put_strike_for_delta(
                        spot, T_entry, r, iv_v, p["short_put_delta"])
                    long_K  = max(short_K - width, 0.01)

                    short_prem = bs_price_skew(spot, short_K, T_entry, r, iv_v,
                                               "put", skew_slope=_SKEW_SLOPE)
                    long_prem  = bs_price_skew(spot, long_K,  T_entry, r, iv_v,
                                               "put", skew_slope=_SKEW_SLOPE)
                    # Entry slippage degrades the realized credit (2 legs).
                    credit = (short_prem - long_prem) - 2 * slip
                    credit_ratio = credit / width if width > 0 else 0.0

                    if credit > 0.01 and credit_ratio >= p["min_credit_ratio"]:
                        max_loss_per_contract = width * 100
                        contracts = max(1, math.floor(
                            capital * p["position_size_pct"] / max_loss_per_contract))
                        # Entry commission (2 legs); slippage already in credit.
                        capital -= 2 * comm * contracts
                        in_trade = True
                        trade = {
                            "entry_date": dt,
                            "entry_idx":  i,
                            "expiry_idx": min(i + dte_bars, n - 1),
                            "short_K":    short_K,
                            "long_K":     long_K,
                            "credit":     credit,
                            "contracts":  contracts,
                        }

            # ── 3. Mark-to-market equity ──────────────────────────────────
            mtm = 0.0
            if in_trade:
                cur = self._spread_cost_to_close(
                    spot, trade["short_K"], trade["long_K"],
                    trade["expiry_idx"] - i, iv_v)
                mtm = (trade["credit"] - cur) * trade["contracts"] * 100
            equity.append(capital + mtm)

        eq_series = pd.Series(equity, index=close.index, dtype=float, name="equity")
        daily_ret = eq_series.pct_change().dropna()
        bh_ret    = close.pct_change().reindex(eq_series.index).dropna()

        trades_df = (
            pd.DataFrame(trades) if trades
            else pd.DataFrame(columns=[
                "entry_date", "exit_date", "spread_type", "short_K", "long_K",
                "credit", "contracts", "pnl", "exit_value", "exit_reason",
                "dte_held"])
        )

        metrics = compute_all_metrics(
            equity_curve=eq_series, trades_df=trades_df, benchmark_returns=bh_ret)

        return BacktestResult(
            self.name, eq_series, daily_ret, trades_df, metrics,
            params=p,
            extra={"ivr_series": ivr_s, "adx_series": adx_s,
                   "vix": vix, "ma": ma_s, "benchmark_ret": bh_ret},
        )
