"""
Volatility Arbitrage — Put-Call Parity Violation + IV Skew Strategy.

Put-call parity (European options, continuous dividends):
    C - P = S * e^(-q*T) - K * e^(-r*T)

When the observed (C - P) deviates from the theoretical value by more than
transaction costs + threshold, two trades exist:

  CONVERSION  (calls overpriced, C - P > parity + threshold):
    Buy stock + Buy put + Sell call at same K, T
    → P&L = K*e^(-rT) - (S + P - C) - costs  [positive when calls are rich]

  REVERSAL    (puts overpriced, C - P < parity - threshold):
    Short stock + Sell put + Buy call at same K, T
    → P&L = (S + P - C) - K*e^(-rT) - costs  [positive when puts are rich]

Secondary signal: IV skew arb — when put IV significantly exceeds call IV at
the same delta (typical in retail-heavy names like HOOD, GME, COIN), enter a
risk-reversal: sell the expensive side (put), buy the cheap side (call), delta-
hedge with stock. This captures the skew premium mean-reversion.

HOOD-specific insights:
  - IV typically 60–100% vs SPY 15–20% → wider violations in dollar terms
  - Persistent put skew 8–20 vol pts → skew_arb is primary signal for HOOD
  - P/C OI ratio 1.5–2.5 → retail put buying creates structural mispricing
  - Hard-to-borrow at times → reversals (short stock leg) may have stock-loan cost
  - Best DTE window: 14–45 days (liquid, enough time value, not too much gamma risk)
  - IV rank > 50 → elevated enough to trade; IV rank > 80 → max sizing

Parameters:
  min_violation_pct    — min parity violation as % of S before entering  (default 0.003)
  max_violation_pct    — max violation to accept (above = data error)    (default 0.05)
  iv_skew_threshold    — put-call IV difference (vol pts) to trade skew  (default 0.08)
  iv_rank_min          — min IV rank (0–1) to enter any trade            (default 0.3)
  dte_min / dte_max    — DTE window for chain scanning                   (default 14–45)
  dividend_yield       — continuous div yield of underlying              (default 0.013)
  position_size_pct    — capital % per trade                             (default 0.08)
  hold_days            — max hold before closing                         (default 3)
"""

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
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
# Helpers
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


def _bs_delta(S: float, K: float, T: float, r: float, iv: float, option_type: str) -> float:
    """Black-Scholes delta. Falls back to ±0.5 on bad inputs."""
    try:
        if T <= 0 or iv <= 0 or S <= 0 or K <= 0:
            return 0.5 if option_type == "call" else -0.5
        d1 = (np.log(S / K) + (r + 0.5 * iv ** 2) * T) / (iv * T ** 0.5)
        from scipy.stats import norm as _norm
        return float(_norm.cdf(d1)) if option_type == "call" else float(_norm.cdf(d1) - 1)
    except Exception:
        return 0.5 if option_type == "call" else -0.5


def _iv_rank(current_iv: float, iv_history: pd.Series) -> float:
    """
    Standard IV Rank = (current - 52wk_min) / (52wk_max - 52wk_min).
    Returns 0.5 (neutral) when history is too short to be meaningful.
    """
    if iv_history.empty or current_iv != current_iv or len(iv_history) < 10:
        return 0.5   # insufficient history — treat as neutral, don't block trading
    lo = float(iv_history.min())
    hi = float(iv_history.max())
    if hi <= lo:
        return 0.5
    return float(max(0.0, min(1.0, (current_iv - lo) / (hi - lo))))


@dataclass
class ParityViolation:
    """A detected put-call parity or IV skew violation."""
    date: object
    strike: float
    expiry_days: int
    call_price: float
    put_price: float
    spot: float
    observed_diff: float        # actual C - P
    theoretical_diff: float     # S*e^(-qT) - K*e^(-rT)
    violation: float            # observed - theoretical (+ = calls rich)
    trade_type: str             # "conversion" | "reversal" | "skew_arb"
    iv_call: Optional[float]
    iv_put: Optional[float]
    iv_skew: Optional[float]    # iv_put - iv_call (positive = put expensive)
    signal_strength: float = 0.0  # normalised 0–1
    call_delta: Optional[float] = None   # BS delta of call leg
    put_delta:  Optional[float] = None   # BS delta of put leg (negative)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy
# ─────────────────────────────────────────────────────────────────────────────

class VolArbitrageStrategy(BaseStrategy):
    name                 = "vol_arbitrage"
    display_name         = "Vol Arbitrage"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Detects put-call parity violations and IV skew mispricing across the "
        "options chain. Executes conversions (calls overpriced), reversals "
        "(puts overpriced), or risk-reversals (persistent put-skew). "
        "Works best on retail-heavy names (HOOD, COIN, GME) where structural "
        "put buying creates persistent skew premium. DTE-filtered, IV-rank gated."
    )
    asset_class          = "equities_options"
    typical_holding_days = 3
    target_sharpe        = 1.4

    def __init__(
        self,
        min_violation_pct:       float = 0.003,
        max_violation_pct:       float = 0.05,
        iv_skew_threshold:       float = 0.08,
        iv_rank_min:             float = 0.30,
        dte_min:                 int   = 14,
        dte_max:                 int   = 45,
        dividend_yield:          float = 0.013,
        position_size_pct:       float = 0.08,
        hold_days:               int   = 3,
        commission_per_contract: float = 0.65,
        slippage_pct:            float = 0.001,
        delta_hedge:             bool  = True,
    ):
        self.min_viol     = min_violation_pct
        self.max_viol     = max_violation_pct
        self.skew_thresh  = iv_skew_threshold
        self.iv_rank_min  = iv_rank_min
        self.dte_min      = dte_min
        self.dte_max      = dte_max
        self.div_yield    = dividend_yield
        self.pos_size_pct = position_size_pct
        self.hold_days    = hold_days
        self.commission   = commission_per_contract
        self.slippage     = slippage_pct
        self.delta_hedge  = delta_hedge

    # ── Live signal ──────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        chain = market_snapshot.get("options_chain")
        S     = market_snapshot.get("spy_price") or market_snapshot.get("price", 500.0)
        r     = market_snapshot.get("rate_10y", 0.045)
        vix_hist = market_snapshot.get("vix_history", pd.Series(dtype=float))
        cur_iv   = market_snapshot.get("vix", 0.20)

        if chain is None or (hasattr(chain, "empty") and chain.empty):
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "no options chain"})

        ivr = _iv_rank(cur_iv, vix_hist)
        if ivr < self.iv_rank_min:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"IV rank {ivr:.2f} below min {self.iv_rank_min}"})

        violations = self._scan_chain(chain, S, r)
        if not violations:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "no violations found"})

        best = violations[0]
        signal = "SELL" if best.trade_type == "conversion" else "BUY"
        confidence = min(1.0, best.signal_strength)

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=confidence,
            position_size_pct=self.pos_size_pct * (1 + ivr),  # scale up with IV rank
            metadata={
                "trade_type":    best.trade_type,
                "strike":        best.strike,
                "dte":           best.expiry_days,
                "violation_pct": round(best.violation / S * 100, 3) if best.trade_type != "skew_arb" else 0,
                "iv_skew":       best.iv_skew,
                "iv_rank":       round(ivr, 2),
                "n_violations":  len(violations),
            },
        )

    # ── Backtest ─────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:       pd.DataFrame,
        auxiliary_data:   dict,
        starting_capital: float = 100_000,
        hold_days:        int   | None = None,
        min_violation_pct:float | None = None,
        iv_skew_threshold:float | None = None,
        iv_rank_min:      float | None = None,
        dte_min:          int   | None = None,
        dte_max:          int   | None = None,
        skip_parity_arb:  bool  = False,
        delta_hedge:      bool | None = None,
        **kwargs,
    ) -> BacktestResult:

        h_days   = hold_days          if hold_days          is not None else self.hold_days
        min_viol = min_violation_pct  if min_violation_pct  is not None else self.min_viol
        skew_thr = iv_skew_threshold  if iv_skew_threshold  is not None else self.skew_thresh
        ivr_min  = iv_rank_min        if iv_rank_min        is not None else self.iv_rank_min
        dte_lo   = dte_min            if dte_min            is not None else self.dte_min
        dte_hi   = dte_max            if dte_max            is not None else self.dte_max
        self._skip_parity_arb = skip_parity_arb
        self._use_delta_hedge = delta_hedge if delta_hedge is not None else self.delta_hedge

        price_data = price_data.copy()
        _idx = pd.to_datetime(price_data.index)
        if _idx.tz is not None:
            _idx = _idx.tz_convert("UTC").tz_localize(None)
        price_data.index = _idx

        vix_df       = auxiliary_data.get("vix",              pd.DataFrame())
        rate_df      = auxiliary_data.get("rate10y",          pd.DataFrame())
        chains       = auxiliary_data.get("options_chains")
        data_quality = auxiliary_data.get("option_data_quality", "unknown")

        if not vix_df.empty:
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)

        if not rate_df.empty:
            rate_df = rate_df.copy()
            rate_df.index = pd.to_datetime(rate_df.index)

        if chains is None:
            raise ValueError(
                "No option chain data found. "
                "Go to Data Manager → Sync Options for this ticker first."
            )

        # Build rolling VIX series (used only as fallback if chain IV unavailable)
        vix_series = (
            vix_df["close"].reindex(price_data.index).ffill().fillna(20.0)
            if not vix_df.empty else
            pd.Series(20.0, index=price_data.index)
        )

        # Build rolling ATM IV history from the chains themselves (more accurate than VIX
        # for stock-specific options — HOOD IV 60-100% has nothing to do with VIX 12-25%)
        _chain_iv_by_date: dict = {}   # Timestamp → median ATM IV (decimal) for that day

        capital     = float(starting_capital)
        trades      = []
        equity_pts  = []
        open_trades = []

        for today in sorted(price_data.index):
            today_date = today.date() if hasattr(today, "date") else today

            # Close expired holds
            still_open = []
            for tr in open_trades:
                days_held = (pd.Timestamp(today) - pd.Timestamp(tr["entry_date"])).days
                if days_held >= h_days:
                    S_exit            = float(price_data.loc[today, "close"])
                    returned, cl_extra = self._close_trade(tr, S_exit,
                                                           chains=chains, close_date=today_date)
                    pnl       = returned - tr["cost"]
                    capital  += returned
                    exit_val  = round(returned / max(tr["contracts"] * 100, 1), 4)
                    trades.append({**tr, **cl_extra, "exit_date": today_date,
                                   "exit_value": exit_val,
                                   "pnl": round(pnl, 2), "exit_reason": "hold_expired"})
                else:
                    still_open.append(tr)
            open_trades = still_open

            if today_date in chains and len(open_trades) == 0:
                chain = chains[today_date]
                S   = float(price_data.loc[today, "close"])
                r   = (float(rate_df["close"].asof(today)) / 100
                       if not rate_df.empty else 0.045)

                # Use chain's own ATM IV for IV rank (not VIX — VIX ≠ stock IV)
                # ATM = strikes within 10% of spot; take median IV across calls+puts
                _atm = chain[chain["iv"].notna() & (chain["iv"] > 0) &
                             (chain["strike"].between(S * 0.90, S * 1.10))]
                if not _atm.empty:
                    cur_iv = float(_atm["iv"].median())
                    _chain_iv_by_date[today] = cur_iv
                else:
                    cur_iv = float(vix_series.asof(today)) / 100 if hasattr(vix_series, "asof") else 0.20

                # Rolling IV rank: compare today's ATM IV against past 252 chain readings
                _past_ivs = pd.Series({k: v for k, v in _chain_iv_by_date.items() if k <= today})
                iv_hist_window = _past_ivs.tail(252)
                ivr = _iv_rank(cur_iv, iv_hist_window)

                if ivr >= ivr_min:
                    # Override strategy params for this scan
                    self._tmp_min_viol  = min_viol
                    self._tmp_skew_thr  = skew_thr
                    self._tmp_dte_min   = dte_lo
                    self._tmp_dte_max   = dte_hi
                    violations = self._scan_chain(chain, S, r)
                    del self._tmp_min_viol, self._tmp_skew_thr
                    del self._tmp_dte_min,  self._tmp_dte_max

                    for v in violations[:1]:
                        tr = self._open_trade(v, S, capital, today_date)
                        if tr:
                            capital -= tr["cost"]
                            open_trades.append(tr)

            equity_pts.append({"date": today, "equity": capital})

        # Close remaining
        if open_trades and len(price_data) > 0:
            last_price  = float(price_data["close"].iloc[-1])
            last_date   = price_data.index[-1]
            last_date   = last_date.date() if hasattr(last_date, "date") else last_date
            for tr in open_trades:
                returned, cl_extra = self._close_trade(tr, last_price,
                                                       chains=chains, close_date=last_date)
                pnl       = returned - tr["cost"]
                capital  += returned
                exit_val  = round(returned / max(tr["contracts"] * 100, 1), 4)
                trades.append({**tr, **cl_extra, "exit_date": price_data.index[-1].date(),
                               "exit_value": exit_val,
                               "pnl": round(pnl, 2), "exit_reason": "end_of_data"})
            # Record final equity after all positions are closed
            equity_pts.append({"date": price_data.index[-1], "equity": capital})

        if not equity_pts:
            return self._empty_result(starting_capital)

        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        equity    = pd.Series(
            [e["equity"] for e in equity_pts],
            index=pd.to_datetime([e["date"] for e in equity_pts]),
            name="equity",
        )
        daily_ret = equity.pct_change().dropna()
        spy_ret   = price_data["close"].pct_change().dropna()
        spy_ret.index = pd.to_datetime(spy_ret.index)

        metrics = compute_all_metrics(
            equity_curve=equity,
            trades_df=trades_df if not trades_df.empty else None,
            benchmark_returns=spy_ret.reindex(equity.index).dropna(),
        )

        # Trade type breakdown for performance tab
        type_breakdown = pd.DataFrame()
        if not trades_df.empty and "spread_type" in trades_df.columns:
            type_breakdown = (
                trades_df.groupby("spread_type")["pnl"]
                .agg(total_pnl="sum", trades="count",
                     win_rate=lambda x: 100 * (x > 0).sum() / len(x),
                     avg_pnl="mean")
                .reset_index()
                .rename(columns={"spread_type": "Trade Type"})
            )

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
            extra={
                "spy_returns":           spy_ret,
                "type_breakdown":        type_breakdown,
                "vix_series":            vix_series,
                "data_quality":          data_quality,
                "chain_iv_series":       pd.Series(_chain_iv_by_date, name="atm_iv"),
                "n_chain_dates":         len(chains),
                "n_price_dates":         len(price_data),
                "n_chain_matches":       sum(1 for d in price_data.index
                                             if (d.date() if hasattr(d, "date") else d) in chains),
                "candidate_assessment":  auxiliary_data.get("candidate_assessment"),
            },
        )

    # ── Walk-forward ──────────────────────────────────────────────────────────

    def walk_forward(
        self,
        price_data:       pd.DataFrame,
        auxiliary_data:   dict,
        test_months:      int   = 2,
        starting_capital: float = 100_000,
        **backtest_kwargs,
    ) -> dict:
        """
        Roll a fixed-param backtest across non-overlapping test windows.
        Returns a dict with:
            windows  : list of per-window metric dicts (+ date bounds + trades)
            summary  : dict of aggregate stats (consistency, avg sharpe, etc.)
            equity   : pd.Series — concatenated equity across all test windows
        Since vol arb has no trainable model, walk-forward tests parameter
        stability across different market regimes rather than re-fitting.
        """
        import datetime as _dt
        from alan_trader.risk.metrics import compute_all_metrics

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        chains = auxiliary_data.get("options_chains", {})

        # Build sorted list of dates with chain data
        chain_dates = sorted(chains.keys())
        if not chain_dates:
            return {"windows": [], "summary": {}, "equity": pd.Series(dtype=float)}

        # Split into test windows by calendar month boundaries
        first_date = chain_dates[0]
        last_date  = chain_dates[-1]
        if isinstance(first_date, _dt.date) and not isinstance(first_date, _dt.datetime):
            first_date = pd.Timestamp(first_date)
            last_date  = pd.Timestamp(last_date)

        # Generate window start/end dates
        window_starts = []
        cur = first_date.to_period("M").to_timestamp()
        while cur <= last_date:
            window_starts.append(cur)
            # advance by test_months
            yr   = cur.year + (cur.month - 1 + test_months) // 12
            mo   = (cur.month - 1 + test_months) % 12 + 1
            cur  = pd.Timestamp(yr, mo, 1)

        windows     = []
        all_equity  = []

        for ws in window_starts:
            we = ws + pd.DateOffset(months=test_months) - pd.DateOffset(days=1)

            # Slice price data
            pd_slice = price_data.loc[
                (price_data.index >= ws) & (price_data.index <= we)
            ]
            if len(pd_slice) < 5:
                continue

            # Slice chains
            ch_slice = {
                d: v for d, v in chains.items()
                if pd.Timestamp(d) >= ws and pd.Timestamp(d) <= we
            }
            if not ch_slice:
                continue

            # Slice auxiliary series (vix, rate10y) — keep full history for context
            aux_slice = {k: v for k, v in auxiliary_data.items()
                         if k != "options_chains"}
            aux_slice["options_chains"]       = ch_slice
            aux_slice["option_data_quality"]  = auxiliary_data.get("option_data_quality", "unknown")

            try:
                res = self.backtest(
                    pd_slice, aux_slice,
                    starting_capital=starting_capital,
                    **backtest_kwargs,
                )
                m = res.metrics
                n_trades = m.get("num_trades", 0)
                window_record = {
                    "period":       f"{ws.strftime('%b %Y')} – {we.strftime('%b %Y')}",
                    "start":        ws.date(),
                    "end":          we.date(),
                    "trades":       n_trades,
                    "win_rate":     m.get("win_rate_pct", 0.0),
                    "total_return": m.get("total_return_pct", 0.0),
                    "sharpe":       m.get("sharpe", 0.0),
                    "max_dd":       m.get("max_drawdown_pct", 0.0),
                    "profit_factor": m.get("profit_factor", 0.0),
                    "result":       res,
                }
                windows.append(window_record)
                if not res.equity_curve.empty:
                    all_equity.append(res.equity_curve)
            except Exception:
                pass  # skip empty windows silently

        if not windows:
            return {"windows": [], "summary": {}, "equity": pd.Series(dtype=float)}

        # Concatenated equity (each window starts where previous ended —
        # rescale so the curve is continuous)
        combined_equity = pd.Series(dtype=float)
        if all_equity:
            offset = 0.0
            pieces  = []
            for eq in all_equity:
                if pieces:
                    offset = pieces[-1].iloc[-1] - float(eq.iloc[0])
                pieces.append(eq + offset)
            combined_equity = pd.concat(pieces).sort_index()
            combined_equity = combined_equity[~combined_equity.index.duplicated(keep="last")]

        # Aggregate stats
        profitable_windows = sum(1 for w in windows if w["total_return"] > 0)
        sharpes = [w["sharpe"] for w in windows if w["trades"] > 0]
        returns = [w["total_return"] for w in windows]
        summary = {
            "n_windows":            len(windows),
            "profitable_windows":   profitable_windows,
            "consistency_pct":      round(profitable_windows / len(windows) * 100, 1),
            "avg_return_pct":       round(float(pd.Series(returns).mean()), 2),
            "avg_sharpe":           round(float(pd.Series(sharpes).mean()), 3) if sharpes else 0.0,
            "worst_window_return":  round(min(returns), 2),
            "best_window_return":   round(max(returns), 2),
        }
        return {"windows": windows, "summary": summary, "equity": combined_equity}

    # ── UI params ─────────────────────────────────────────────────────────────

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "hold_days",          "label": "Max hold days",
             "type": "slider",  "min": 1,   "max": 10,   "default": 2,    "step": 1,
             "col": 0, "row": 0, "help": "Close position after this many days if not expired"},
            {"key": "min_violation_pct",  "label": "Min parity violation (fraction of S)",
             "type": "slider",  "min": 0.001, "max": 0.020, "default": 0.003, "step": 0.001,
             "col": 1, "row": 0, "help": "Minimum violation as fraction of spot (0.003 = 0.3% for SPY, 0.005 for HOOD)"},
            {"key": "iv_skew_threshold",  "label": "IV skew threshold (fraction, e.g. 0.05 = 5pts)",
             "type": "slider",  "min": 0.02, "max": 0.20, "default": 0.05, "step": 0.01,
             "col": 2, "row": 0, "help": "Put minus call IV threshold to trigger skew arb (0.05 = 5 vol pts)"},
            {"key": "iv_rank_min",        "label": "Min IV Rank to enter (0–1)",
             "type": "slider",  "min": 0.0, "max": 0.80, "default": 0.0,  "step": 0.05,
             "col": 0, "row": 1, "help": "Only trade when IV rank (0=lowest, 1=highest) exceeds this value"},
            {"key": "dte_min",            "label": "DTE minimum",
             "type": "slider",  "min": 5,   "max": 30,   "default": 7,    "step": 1,
             "col": 1, "row": 1, "help": "Skip contracts with fewer DTE (too much gamma risk)"},
            {"key": "dte_max",            "label": "DTE maximum",
             "type": "slider",  "min": 20,  "max": 90,   "default": 60,   "step": 5,
             "col": 2, "row": 1, "help": "Skip contracts with more DTE (too little premium decay)"},
            {"key": "delta_hedge",        "label": "Delta hedge (short stock)",
             "type": "checkbox", "default": True,
             "col": 0, "row": 2, "help": "Short stock equal to net delta of the risk reversal. Isolates pure IV skew P&L from directional moves. No theta cost."},
        ]

    def get_params(self) -> dict:
        return {
            "min_violation_pct":  self.min_viol,
            "max_violation_pct":  self.max_viol,
            "iv_skew_threshold":  self.skew_thresh,
            "iv_rank_min":        self.iv_rank_min,
            "dte_min":            self.dte_min,
            "dte_max":            self.dte_max,
            "dividend_yield":     self.div_yield,
            "position_size_pct":  self.pos_size_pct,
            "hold_days":          self.hold_days,
            "slippage_pct":       self.slippage,
            "delta_hedge":        self.delta_hedge,
        }

    # ── Core: scan chain ─────────────────────────────────────────────────────

    def _scan_chain(self, chain: pd.DataFrame, S: float, r: float) -> list:
        """
        Scan for:
          1. Put-call parity violations (conversion / reversal)
          2. IV skew arbitrage (persistent put premium vs calls)

        Returns violations sorted by signal_strength descending.
        """
        min_viol  = getattr(self, "_tmp_min_viol",  self.min_viol)
        skew_thr  = getattr(self, "_tmp_skew_thr",  self.skew_thresh)
        dte_lo    = getattr(self, "_tmp_dte_min",    self.dte_min)
        dte_hi    = getattr(self, "_tmp_dte_max",    self.dte_max)

        violations = []

        # Group by expiration so duplicate strikes across expirations never collide
        exp_col = "expiration" if "expiration" in chain.columns else "dte"
        groups  = chain.groupby(exp_col) if exp_col in chain.columns else [(None, chain)]

        for exp_key, exp_grp in groups:
            # DTE for this expiration slice
            if "dte" in exp_grp.columns:
                dte_vals = exp_grp["dte"].dropna()
                dte_val  = float(dte_vals.iloc[0]) if not dte_vals.empty else 30.0
            else:
                dte_val = 30.0

            if not (dte_lo <= dte_val <= dte_hi):
                continue

            T = dte_val / 252
            if T <= 0:
                continue

            calls = exp_grp[exp_grp["type"] == "call"].set_index("strike")
            puts  = exp_grp[exp_grp["type"] == "put"].set_index("strike")
            common = calls.index.intersection(puts.index)

            # Only scan near-ATM strikes (±20% of spot) — deep OTM options
            # have structurally high put skew from the volatility smile, not arb
            atm_common = [k for k in common if S * 0.80 <= k <= S * 1.20]
            if not atm_common:
                continue

            for K in atm_common:
                c_row = calls.loc[K]
                p_row = puts.loc[K]

                # Handle residual duplicates within same expiration — take best (highest OI)
                if isinstance(c_row, pd.DataFrame):
                    c_row = c_row.sort_values("open_interest", ascending=False).iloc[0] \
                            if "open_interest" in c_row.columns else c_row.iloc[0]
                if isinstance(p_row, pd.DataFrame):
                    p_row = p_row.sort_values("open_interest", ascending=False).iloc[0] \
                            if "open_interest" in p_row.columns else p_row.iloc[0]

                c_bid = c_row.get("bid", float("nan"))
                c_ask = c_row.get("ask", float("nan"))
                p_bid = p_row.get("bid", float("nan"))
                p_ask = p_row.get("ask", float("nan"))

                # Get stored IVs (used for skew arb and as fallback for price reconstruction)
                c_iv_stored = float(c_row.get("iv") or c_row.get("ImpliedVol") or float("nan"))
                p_iv_stored = float(p_row.get("iv") or p_row.get("ImpliedVol") or float("nan"))

                # Filter out extreme/illiquid IV (capped values like 20.0 = 2000% are noise)
                _MAX_IV = 3.0   # 300% — anything above is deep OTM / illiquid noise
                if (c_iv_stored == c_iv_stored and c_iv_stored > _MAX_IV) or \
                   (p_iv_stored == p_iv_stored and p_iv_stored > _MAX_IV):
                    continue

                # Track whether prices are real market quotes or BS-reconstructed
                c_reconstructed = (c_bid != c_bid or c_ask != c_ask or
                                   float(c_bid if c_bid == c_bid else 0) <= 0 or
                                   float(c_ask if c_ask == c_ask else 0) <= 0)
                p_reconstructed = (p_bid != p_bid or p_ask != p_ask or
                                   float(p_bid if p_bid == p_bid else 0) <= 0 or
                                   float(p_ask if p_ask == p_ask else 0) <= 0)
                both_reconstructed = c_reconstructed and p_reconstructed

                # Reconstruct bid/ask from IV+BS when prices are missing (historical DB data)
                def _bs_mid_spread(iv_val, opt_type):
                    if iv_val is None or iv_val != iv_val or float(iv_val) <= 0:
                        return float("nan"), float("nan")
                    try:
                        mid    = bs_price(S, K, T, r, float(iv_val), opt_type)
                        spread = max(0.01, mid * (0.04 if mid < 1 else 0.02))
                        return mid - spread / 2, mid + spread / 2
                    except Exception:
                        return float("nan"), float("nan")

                if c_reconstructed:
                    c_bid, c_ask = _bs_mid_spread(c_iv_stored, "call")
                if p_reconstructed:
                    p_bid, p_ask = _bs_mid_spread(p_iv_stored, "put")

                # Skip if still no valid quotes after reconstruction
                if any(v != v for v in [c_bid, c_ask, p_bid, p_ask]):
                    continue

                c_mid = (float(c_bid) + float(c_ask)) / 2
                p_mid = (float(p_bid) + float(p_ask)) / 2
                if c_mid <= 0 or p_mid <= 0:
                    continue

                # ── Parity violation (REAL quotes only) ───────────────────
                # When prices are BS-reconstructed from IVs, the apparent parity
                # violation is circular: violation = BS(put_iv) - BS(call_iv) - parity,
                # which is just the IV skew in dollar form — not a real market arb.
                # Only trade parity violations when we have real bid/ask market quotes.
                _force_skip_parity = getattr(self, "_skip_parity_arb", False)
                if not both_reconstructed and not _force_skip_parity:
                    observed    = c_mid - p_mid
                    theoretical = _parity_theoretical(S, K, T, r, self.div_yield)
                    violation   = observed - theoretical
                    viol_pct    = abs(violation) / S

                    if min_viol <= viol_pct <= self.max_viol:
                        # Use stored IVs directly when available; avoid circular re-solve
                        iv_c = c_iv_stored if c_iv_stored == c_iv_stored else _implied_vol(c_mid, S, K, T, r, "call")
                        iv_p = p_iv_stored if p_iv_stored == p_iv_stored else _implied_vol(p_mid, S, K, T, r, "put")
                        iv_skew = (iv_p - iv_c) if (iv_c and iv_p) else None
                        trade_type = "conversion" if violation > 0 else "reversal"
                        strength   = min(1.0, viol_pct / (min_viol * 3))
                        violations.append(ParityViolation(
                            date=None, strike=K, expiry_days=int(dte_val),
                            call_price=c_mid, put_price=p_mid, spot=S,
                            observed_diff=observed, theoretical_diff=theoretical,
                            violation=violation, trade_type=trade_type,
                            iv_call=iv_c, iv_put=iv_p, iv_skew=iv_skew,
                            signal_strength=strength,
                        ))
                else:
                    # Reconstructed prices: set these so skew_arb block below has values
                    viol_pct = 0.0

                # ── IV skew arb ───────────────────────────────────────────
                # Use stored IVs directly (avoids circular implied_vol re-solve on
                # BS-reconstructed prices, which just returns the original stored IV)
                # ── Delta (used for hedge sizing) ─────────────────────────
                # Use stored delta from chain; fall back to BS when absent
                _c_delta_raw = float(c_row.get("delta") or float("nan"))
                _p_delta_raw = float(p_row.get("delta") or float("nan"))
                _iv_c_for_d  = c_iv_stored if (c_iv_stored == c_iv_stored and c_iv_stored > 0) else 0.3
                _iv_p_for_d  = p_iv_stored if (p_iv_stored == p_iv_stored and p_iv_stored > 0) else 0.3
                c_delta = _c_delta_raw if (0 < _c_delta_raw <= 1.0) \
                          else _bs_delta(S, K, T, r, _iv_c_for_d, "call")
                p_delta = _p_delta_raw if (-1.0 <= _p_delta_raw < 0) \
                          else _bs_delta(S, K, T, r, _iv_p_for_d, "put")

                iv_c2 = c_iv_stored if c_iv_stored == c_iv_stored else None
                iv_p2 = p_iv_stored if p_iv_stored == p_iv_stored else None
                if iv_c2 and iv_p2:
                    skew = iv_p2 - iv_c2
                    if skew > skew_thr and viol_pct < min_viol:
                        strength = min(1.0, (skew - skew_thr) / skew_thr)
                        violations.append(ParityViolation(
                            date=None, strike=K, expiry_days=int(dte_val),
                            call_price=c_mid, put_price=p_mid, spot=S,
                            observed_diff=c_mid - p_mid,
                            theoretical_diff=_parity_theoretical(S, K, T, r, self.div_yield),
                            violation=0.0, trade_type="skew_arb",
                            iv_call=iv_c2, iv_put=iv_p2, iv_skew=skew,
                            signal_strength=strength,
                            call_delta=c_delta, put_delta=p_delta,
                        ))

        violations.sort(key=lambda v: v.signal_strength, reverse=True)
        return violations

    # ── Trade management ─────────────────────────────────────────────────────

    def _open_trade(self, v: ParityViolation, S: float,
                    capital: float, today) -> Optional[dict]:
        margin_per_contract = S * 100 * 0.20
        budget              = capital * self.pos_size_pct
        n_contracts         = max(1, int(budget / margin_per_contract))

        slippage_cost = S * self.slippage * n_contracts * 100
        commission    = self.commission * n_contracts * 3

        if v.trade_type == "skew_arb":
            # Risk-reversal: sell put, buy call, delta-hedge
            gross   = abs(v.iv_skew or 0) * S * 0.10 * n_contracts * 100
        else:
            gross   = abs(v.violation) * n_contracts * 100

        net_profit = gross - slippage_cost - commission
        if net_profit <= 0:
            return None

        cost = margin_per_contract * n_contracts

        iv_str = (f"Call IV={v.iv_call:.1%}  Put IV={v.iv_put:.1%}"
                  if v.iv_call and v.iv_put else "IV=N/A")
        if v.trade_type == "conversion":
            desc = (f"CONVERSION  K=${v.strike:.1f}  DTE={v.expiry_days}  "
                    f"Spot=${S:.2f}  {n_contracts}x  |  "
                    f"Legs: Buy stock @${S:.2f}  Buy put @${v.put_price:.3f}  Sell call @${v.call_price:.3f}  |  "
                    f"Total in=${cost:.2f}  |  "
                    f"Viol={v.violation:+.3f} ({abs(v.violation)/S*100:.2f}% S)  "
                    f"{iv_str}")
        elif v.trade_type == "reversal":
            desc = (f"REVERSAL  K=${v.strike:.1f}  DTE={v.expiry_days}  "
                    f"Spot=${S:.2f}  {n_contracts}x  |  "
                    f"Legs: Short stock @${S:.2f}  Sell put @${v.put_price:.3f}  Buy call @${v.call_price:.3f}  |  "
                    f"Total in=${cost:.2f}  |  "
                    f"Viol={v.violation:+.3f} ({abs(v.violation)/S*100:.2f}% S)  "
                    f"{iv_str}")
        else:
            skew_pts  = f"{(v.iv_skew or 0)*100:.1f}"
            net_debit = (v.call_price - v.put_price) * 100 * n_contracts
            # Delta hedge: net delta of risk reversal = call_delta + |put_delta|
            # Offset with long puts (negative delta) sized to neutralize
            use_hedge  = getattr(self, "_use_delta_hedge", self.delta_hedge)
            c_d        = v.call_delta if (v.call_delta and 0 < v.call_delta <= 1) else 0.5
            p_d        = abs(v.put_delta) if (v.put_delta and -1 <= v.put_delta < 0) else 0.5
            net_delta  = c_d + p_d          # both legs contribute positive delta
            # Number of long ATM puts needed: net_delta / 0.5 (ATM put delta ≈ -0.5)
            hedge_puts = round(net_delta * n_contracts / 0.5) if use_hedge else 0
            # Express hedge as equivalent short-stock shares (net_delta * n * 100)
            hedge_shares = round(net_delta * n_contracts * 100)
            hedge_str  = f"  +Short {hedge_shares} shares (Δ-hedge)" if hedge_shares > 0 else ""
            desc = (f"SKEW ARB{'[Δ-HEDGED]' if hedge_puts else ''}  K=${v.strike:.1f}  "
                    f"DTE={v.expiry_days}  Spot=${S:.2f}  {n_contracts}x  |  "
                    f"Sell put @${v.put_price:.3f}  Buy call @${v.call_price:.3f}"
                    f"{hedge_str}  |  "
                    f"Net debit=${net_debit:.2f}  |  "
                    f"PutIV-CallIV={skew_pts}vp  {iv_str}")

        # Plain-English rationale and exit expectation
        if v.trade_type == "skew_arb":
            skew_pct  = abs(v.iv_skew or 0) * 100
            use_hedge = getattr(self, "_use_delta_hedge", self.delta_hedge)
            hedge_note = (
                " Delta is neutralized via short stock — position profits from IV skew compression "
                "independent of stock direction."
            ) if use_hedge else (
                " No delta hedge — position has net long delta and benefits from stock rising."
            )
            comment = (
                f"Put IV is {skew_pct:.1f} vol pts above call IV at K=${v.strike:.0f} "
                f"({v.expiry_days}d to expiry). "
                f"Selling the overpriced put and buying the cheap call."
                f"{hedge_note} "
                f"Win if put premium mean-reverts (skew compresses) before expiry. "
                f"Lose if skew widens further."
            )
        elif v.trade_type == "conversion":
            comment = (
                f"Put-call parity broken by +${abs(v.violation):.3f} at K=${v.strike:.0f} "
                f"(call too expensive vs put). "
                f"Buy stock + buy put + sell call locks in the mispricing. "
                f"P&L is nearly locked at entry; exits when options expire or are closed."
            )
        else:  # reversal
            comment = (
                f"Put-call parity broken by -${abs(v.violation):.3f} at K=${v.strike:.0f} "
                f"(put too expensive vs call). "
                f"Short stock + sell put + buy call captures the mispricing. "
                f"P&L is nearly locked at entry; exits when position is closed or hold period expires."
            )

        return {
            "entry_date":        today,
            "spread_type":       f"vol_arb_{v.trade_type}",
            "description":       desc,
            "comment":           comment,
            "spot":              round(S, 2),
            "strike":            v.strike,
            "dte":               v.expiry_days,
            "long_strike":       v.strike,
            "short_strike":      v.strike,
            "entry_cost":        round(cost / (n_contracts * 100), 4),
            "exit_value":        0.0,
            "contracts":         n_contracts,
            "expected_pnl":      round(net_profit, 2),
            "violation":         round(v.violation, 4),
            "cost":              cost,
            "trade_type":        v.trade_type,
            "iv_call":           round(v.iv_call, 4) if v.iv_call else None,
            "iv_put":            round(v.iv_put, 4) if v.iv_put else None,
            "iv_skew":           round(v.iv_skew, 4) if v.iv_skew else None,
            "call_price_entry":  round(v.call_price, 4),
            "put_price_entry":   round(v.put_price, 4),
            "signal_strength":   round(v.signal_strength, 3),
            # Delta hedge fields (only set for skew_arb with hedging enabled)
            "hedge_puts":        hedge_puts if v.trade_type == "skew_arb" else 0,
            "hedge_entry_spot":  round(S, 4) if v.trade_type == "skew_arb" else None,
            "net_delta_entry":   round(net_delta, 3) if v.trade_type == "skew_arb" else None,
        }

    def _close_trade(self, tr: dict, S_exit: float,
                     chains: dict | None = None, close_date=None) -> tuple:
        """
        Close P&L using actual chain data (bid/ask mid) at exit date.

        Skew arb (risk-reversal: short put, long call):
          Exit P&L = (put_entry - put_exit) + (call_exit - call_entry) per share
                   = profit from short-put decay + profit from call appreciation
          Uses BS-priced mid from close chain.  Because spot moves and time pass even
          when IV is constant, the delta + theta P&L is fully captured by comparing
          the BS mids at entry vs exit.

        Parity arb (conversion / reversal):
          Same approach — look up both legs at exit, compare mids to entry mids.
          Falls back to 80% capture if no close chain available.
        """
        import datetime as _cdt

        n          = tr["contracts"]
        commission = self.commission * n * 3
        gross      = tr["expected_pnl"]

        # ── Find closest chain snapshot at or near close_date ─────────────────
        close_chain = None
        if chains is not None and close_date is not None:
            if close_date in chains:
                close_chain = chains[close_date]
            else:
                for delta in [1, -1, 2, -2, 3, -3]:
                    adj = (close_date + _cdt.timedelta(days=delta)
                           if isinstance(close_date, _cdt.date) else close_date)
                    if adj in chains:
                        close_chain = chains[adj]
                        break

        if close_chain is None:
            # No chain data available at close
            if tr.get("trade_type") != "skew_arb":
                return round(tr["cost"] + gross * 0.80, 2), {}
            return round(tr["cost"], 2), {}

        # ── Find same strike + similar DTE in close chain ─────────────────────
        K         = tr["strike"]
        entry_dte = tr.get("dte", 30)
        hold      = (close_date - tr["entry_date"]).days if (
            close_date is not None and tr.get("entry_date") is not None
        ) else 2
        target_dte = max(1, entry_dte - hold)

        cdf = close_chain[close_chain["dte"].between(target_dte - 10, target_dte + 10)] \
              if "dte" in close_chain.columns else close_chain

        calls_c = cdf[cdf["type"] == "call"]
        puts_c  = cdf[cdf["type"] == "put"]

        if calls_c.empty or puts_c.empty:
            if tr.get("trade_type") != "skew_arb":
                return round(tr["cost"] + gross * 0.80, 2), {}
            return round(tr["cost"], 2), {}

        # Nearest available strike
        c_near = calls_c.iloc[(calls_c["strike"] - K).abs().argsort().iloc[:1]]
        p_near = puts_c.iloc[(puts_c["strike"] - K).abs().argsort().iloc[:1]]

        # Exit mid prices
        def _mid(row):
            bid = row["bid"].iloc[0] if "bid" in row.columns else float("nan")
            ask = row["ask"].iloc[0] if "ask" in row.columns else float("nan")
            if bid == bid and ask == ask and float(bid) > 0 and float(ask) > 0:
                return (float(bid) + float(ask)) / 2
            return float("nan")

        c_mid_exit = _mid(c_near)
        p_mid_exit = _mid(p_near)

        if c_mid_exit != c_mid_exit or p_mid_exit != p_mid_exit:
            # Can't price exit legs → fall back
            if tr.get("trade_type") != "skew_arb":
                return round(tr["cost"] + gross * 0.80, 2), {}
            return round(tr["cost"], 2), {}

        call_entry = tr.get("call_price_entry", 0.0) or 0.0
        put_entry  = tr.get("put_price_entry",  0.0) or 0.0

        if tr.get("trade_type") == "skew_arb":
            # Short put, long call:
            #   Put P&L  = put_entry − put_exit   (sold at entry, bought back at exit)
            #   Call P&L = call_exit − call_entry (bought at entry, sold at exit)
            put_pnl  = (put_entry  - p_mid_exit) * 100 * n
            call_pnl = (c_mid_exit - call_entry) * 100 * n

            # Delta hedge: long ATM puts priced at exit using BS with exit spot
            # Hedge gain = ATM put value increases when stock falls (negative delta)
            hedge_pnl  = 0.0
            hedge_puts = tr.get("hedge_puts", 0) or 0
            if hedge_puts > 0:
                S_entry = tr.get("hedge_entry_spot") or 0.0
                net_d   = tr.get("net_delta_entry") or 1.0
                # Delta hedge modeled as short stock (standard approach — no theta drag).
                # Short stock = profit when price falls, loss when rises.
                # Equivalent to short net_delta * n_contracts * 100 shares.
                if S_entry > 0:
                    hedge_pnl = -(S_exit - S_entry) * net_d * n * 100

            skew_pnl = put_pnl + call_pnl - commission
            profit   = skew_pnl + hedge_pnl
            extra    = {
                "put_pnl":    round(put_pnl,    2),
                "call_pnl":   round(call_pnl,   2),
                "hedge_pnl":  round(hedge_pnl,  2),
                "commission": round(commission,  2),
            }

        elif tr.get("trade_type") == "conversion":
            # Long call, short put (+ long stock):
            #   Call P&L = call_exit − call_entry
            #   Put P&L  = put_entry − put_exit
            #   Stock P&L accounted in cost (not tracked separately)
            put_pnl  = (put_entry  - p_mid_exit) * 100 * n
            call_pnl = (c_mid_exit - call_entry) * 100 * n
            profit   = put_pnl + call_pnl - commission
            extra    = {}

        else:   # reversal
            # Short call, long put (+ short stock):
            #   Call P&L = call_entry − call_exit
            #   Put P&L  = put_exit − put_entry
            put_pnl  = (p_mid_exit - put_entry)  * 100 * n
            call_pnl = (call_entry - c_mid_exit) * 100 * n
            profit   = put_pnl + call_pnl - commission
            extra    = {}

        return round(tr["cost"] + profit, 2), extra

    # ── Candidate assessment ──────────────────────────────────────────────────

    def assess_candidate(
        self,
        chains: dict,           # date → DataFrame (same format as backtest input)
        price_data: pd.DataFrame,
        dte_min: int = 7,
        dte_max: int = 60,
    ) -> dict:
        """
        Score a ticker as a vol-arb candidate (0–100).

        Criteria:
          1. Average IV skew (put IV − call IV at ATM)   — higher is better
          2. Average ATM IV level                         — higher means more premium
          3. Dollar premium per 1-lot (ATM call value)   — too low = not worth trading
          4. Price trend over the period                  — flat/rising beats a crash
          5. Chain coverage (% of price days with chain) — data availability

        Returns a dict with score, verdict, per-criterion breakdown, and advice.
        """
        skews, atm_ivs, premiums = [], [], []

        for dt, chain in chains.items():
            # Match a price for this date
            ts = pd.Timestamp(str(dt))
            try:
                S = float(price_data["close"].asof(ts)) if hasattr(price_data["close"], "asof") \
                    else float(price_data.loc[ts, "close"])
            except Exception:
                continue
            if not S or S != S:
                continue

            sub = chain[chain["dte"].between(dte_min, dte_max)] if "dte" in chain.columns else chain
            calls = sub[sub["type"] == "call"]
            puts  = sub[sub["type"] == "put"]
            atm_range = (S * 0.90, S * 1.10)
            calls_atm = calls[calls["strike"].between(*atm_range)]
            puts_atm  = puts[puts["strike"].between(*atm_range)]

            if calls_atm.empty or puts_atm.empty:
                continue

            # Median ATM IVs
            c_iv = float(calls_atm["iv"].dropna().median()) if "iv" in calls_atm.columns else float("nan")
            p_iv = float(puts_atm["iv"].dropna().median())  if "iv" in puts_atm.columns  else float("nan")
            if c_iv != c_iv or p_iv != p_iv or c_iv <= 0 or p_iv <= 0:
                continue
            if c_iv > 3.0 or p_iv > 3.0:
                continue

            skew = p_iv - c_iv
            atm_iv = (c_iv + p_iv) / 2
            # Dollar value of an ATM call, 30-day proxy
            T_proxy = 30 / 252
            try:
                from alan_trader.backtest.engine import bs_price as _bsp
                prem = _bsp(S, S, T_proxy, 0.045, c_iv, "call") * 100
            except Exception:
                prem = S * c_iv * (T_proxy ** 0.5) * 100 * 0.4  # rough approx

            skews.append(skew)
            atm_ivs.append(atm_iv)
            premiums.append(prem)

        if not skews:
            return {
                "score": 0, "verdict": "No Data",
                "color": "gray",
                "reasons": ["No option chain data available for this ticker."],
                "metrics": {},
            }

        avg_skew   = float(np.mean(skews))        # decimal, e.g. 0.25 = 25 vol pts
        avg_iv     = float(np.mean(atm_ivs))
        avg_prem   = float(np.mean(premiums))
        pct_skew_pos = float((np.array(skews) > self.skew_thresh).mean())  # fraction of days with tradeable skew

        # Price trend over the period
        price_trend = float("nan")
        try:
            p_start = float(price_data["close"].iloc[0])
            p_end   = float(price_data["close"].iloc[-1])
            price_trend = (p_end - p_start) / p_start
        except Exception:
            pass

        # Chain coverage
        n_price = len(price_data)
        n_chain = len(chains)
        coverage = n_chain / max(n_price, 1)

        # ── Scoring (each criterion 0–25) ─────────────────────────────────────
        # 1. IV skew magnitude (0–25 pts): 5 vol pts = 5, 15 = 15, 25+ = 25
        skew_score = min(25, max(0, avg_skew * 100 * 1.0))          # 1pt per vol pt up to 25

        # 2. IV level (0–20 pts): 25% = 5, 50% = 10, 100% = 20
        iv_score = min(20, max(0, avg_iv * 100 * 0.2))              # 0.2pt per vol pt

        # 3. Dollar premium (0–20 pts): $50 = 10, $100 = 15, $200+ = 20
        prem_score = min(20, max(0, avg_prem / 10))

        # 4. Price trend (0–20 pts): flat/up is good, -10%+ hurts
        if price_trend != price_trend:
            trend_score = 10  # neutral
        else:
            if price_trend >= 0:
                trend_score = min(20, 10 + price_trend * 50)        # reward upward drift
            else:
                trend_score = max(0, 10 + price_trend * 80)         # penalise downtrend

        # 5. Consistent skew signal (0–15 pts): % of days skew is tradeable
        signal_score = min(15, pct_skew_pos * 15)

        total = skew_score + iv_score + prem_score + trend_score + signal_score
        total = round(min(100, max(0, total)))

        if   total >= 70: verdict, color = "Strong candidate",   "green"
        elif total >= 45: verdict, color = "Moderate candidate", "orange"
        elif total >= 25: verdict, color = "Weak candidate",     "red"
        else:             verdict, color = "Poor candidate",     "red"

        # ── Build plain-English reasons ────────────────────────────────────────
        reasons = []

        skew_pts = avg_skew * 100
        if skew_pts >= 15:
            reasons.append(f"✅ Strong IV skew: put IV averages **{skew_pts:.0f} vol pts** above call IV — structural put premium present.")
        elif skew_pts >= 5:
            reasons.append(f"🟡 Moderate IV skew: **{skew_pts:.0f} vol pts** put-call difference. Tradeable but not exceptional.")
        else:
            reasons.append(f"❌ Weak IV skew: only **{skew_pts:.1f} vol pts** difference — not enough edge for skew arb.")

        iv_pct = avg_iv * 100
        if iv_pct >= 50:
            reasons.append(f"✅ High IV: avg ATM IV **{iv_pct:.0f}%** — ample premium to capture.")
        elif iv_pct >= 25:
            reasons.append(f"🟡 Moderate IV: avg ATM IV **{iv_pct:.0f}%** — decent but not high-octane.")
        else:
            reasons.append(f"❌ Low IV: avg ATM IV **{iv_pct:.0f}%** — premium too thin for meaningful P&L.")

        if avg_prem >= 100:
            reasons.append(f"✅ Good dollar premium: ~**${avg_prem:.0f}** per 1-lot ATM call — worthwhile position sizes.")
        elif avg_prem >= 40:
            reasons.append(f"🟡 Modest dollar premium: ~**${avg_prem:.0f}** per 1-lot — need more contracts for meaningful P&L.")
        else:
            reasons.append(f"❌ Low dollar premium: ~**${avg_prem:.0f}** per 1-lot — stock price too low to generate real edge.")

        if price_trend == price_trend:
            trend_pct = price_trend * 100
            if trend_pct >= 5:
                reasons.append(f"✅ Uptrend: stock gained **{trend_pct:+.1f}%** over the period — synthetic long bias helps.")
            elif trend_pct >= -10:
                reasons.append(f"✅ Stable price: **{trend_pct:+.1f}%** drift — range-bound stocks are ideal for this strategy.")
            elif trend_pct >= -25:
                reasons.append(f"⚠️ Downtrend: stock fell **{trend_pct:.1f}%** — risk-reversal (long delta) fights the tape.")
            else:
                reasons.append(f"❌ Strong downtrend: stock fell **{trend_pct:.1f}%** — synthetic long loses badly in crashes.")

        if pct_skew_pos >= 0.70:
            reasons.append(f"✅ Consistent skew signal: **{pct_skew_pos*100:.0f}%** of chain days have tradeable skew (>{self.skew_thresh*100:.0f} vol pts).")
        elif pct_skew_pos >= 0.40:
            reasons.append(f"🟡 Intermittent skew: **{pct_skew_pos*100:.0f}%** of days with signal — fewer trade opportunities.")
        else:
            reasons.append(f"❌ Rare skew signal: only **{pct_skew_pos*100:.0f}%** of days qualify — strategy will rarely trigger.")

        return {
            "score":    total,
            "verdict":  verdict,
            "color":    color,
            "reasons":  reasons,
            "metrics": {
                "avg_iv_skew_pts":   round(skew_pts, 1),
                "avg_atm_iv_pct":    round(iv_pct, 1),
                "avg_dollar_prem":   round(avg_prem, 0),
                "price_trend_pct":   round(price_trend * 100, 1) if price_trend == price_trend else None,
                "pct_days_w_signal": round(pct_skew_pos * 100, 0),
                "chain_dates":       n_chain,
            },
        }

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


