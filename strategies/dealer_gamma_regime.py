"""
Dealer Gamma Regime (DGR) — options strategy that actually trades the GEX mechanic.

MECHANIC
--------
Negative dealer GEX (spot < flip): dealers hedge WITH the move → trends amplify.
    → Edge is LONG GAMMA. Buy debit structures that pay off on large moves.
Positive dealer GEX (spot > flip): dealers hedge AGAINST the move → mean-reverting, pinning.
    → Edge is SHORT GAMMA. Sell iron condors anchored on largest-gamma strikes.
Near-flip (spot within near_flip_pct of flip): regime inflection.
    → Long straddle to catch the breakout either way.

Unlike the VIX-ladder gex_positioning strategy, this one:
  • computes actual dealer GEX from the options chain (not a VIX proxy),
  • sizes by distance-to-flip (not by VIX band),
  • uses 3 distinct options structures keyed to regime,
  • anchors short legs on detected put/call walls.

SIZING
------
Base risk = `base_risk_pct` of capital per trade.
Scaled up to `max_risk_pct` when |dist_to_flip| is small (regime signal is strong).
Blocked when |net_gex| too small (noise) or VIX > vix_ceiling (dislocated).
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)
from alan_trader.risk.metrics import compute_all_metrics
from alan_trader.analytics.gex_engine import (
    compute_dealer_gex,
    classify_regime,
    expected_move_pct,
    GEXSnapshot,
)

logger = logging.getLogger(__name__)

_RISK_FREE = 0.045


class DealerGammaRegimeStrategy(BaseStrategy):
    name                 = "dealer_gamma_regime"
    display_name         = "Dealer Gamma Regime"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Trades the actual dealer gamma mechanic using three regime-specific options "
        "structures. Negative GEX → long straddle (dealers amplify moves). Positive GEX "
        "→ iron condor anchored on call wall (dealers pin). Near-flip → long straddle "
        "(regime inflection). GEX computed from options chain; sized by distance-to-flip."
    )
    asset_class          = "equities_options"
    typical_holding_days = 18
    target_sharpe        = 1.5

    def __init__(
        self,
        # Regime detection
        near_flip_pct:      float = 0.25,   # % distance counted as near-flip zone
        min_abs_gex:        float = 5e7,    # skip if |net_gex| below this (noise)
        vix_ceiling:        float = 35.0,   # skip entries above this VIX
        sign_convention:    str   = "index_retail_call_long",
        # Structure params
        dte_entry_long:     int   = 30,     # straddle / debit legs
        dte_entry_condor:   int   = 35,
        short_leg_delta:    float = 0.15,   # condor short-leg target delta
        wing_em_width:      float = 2.0,    # wings at ± wing_em_width × expected move from body
        # Risk / sizing
        base_risk_pct:      float = 0.75,   # % capital per trade at far-from-flip
        max_risk_pct:       float = 1.50,   # % capital per trade at near-flip
        max_concurrent:     int   = 1,
        # Exits
        condor_profit_tgt:  float = 0.50,   # close at 50% max profit
        condor_stop_mult:   float = 2.0,    # close at 2× credit loss
        condor_dte_exit:    int   = 21,
        straddle_tp_mult:   float = 0.60,   # close at +60% profit
        straddle_stop_pct:  float = 0.50,   # close at -50% debit
        straddle_dte_exit:  int   = 7,
        # Costs
        slippage_per_leg:   float = 0.05,
        commission_per_leg: float = 0.65,
    ):
        self.near_flip_pct      = near_flip_pct / 100.0
        self.min_abs_gex        = min_abs_gex
        self.vix_ceiling        = vix_ceiling
        self.sign_convention    = sign_convention
        self.dte_entry_long     = dte_entry_long
        self.dte_entry_condor   = dte_entry_condor
        self.short_leg_delta    = short_leg_delta
        self.wing_em_width      = wing_em_width
        self.base_risk_pct      = base_risk_pct / 100.0
        self.max_risk_pct       = max_risk_pct / 100.0
        self.max_concurrent     = max_concurrent
        self.condor_profit_tgt  = condor_profit_tgt
        self.condor_stop_mult   = condor_stop_mult
        self.condor_dte_exit    = condor_dte_exit
        self.straddle_tp_mult   = straddle_tp_mult
        self.straddle_stop_pct  = straddle_stop_pct
        self.straddle_dte_exit  = straddle_dte_exit
        self.slippage_per_leg   = slippage_per_leg
        self.commission_per_leg = commission_per_leg

    # ═══════════════════════════════════════════════════════════════════════
    # Params
    # ═══════════════════════════════════════════════════════════════════════

    def get_params(self) -> dict:
        return {
            "near_flip_pct":     self.near_flip_pct * 100,
            "min_abs_gex":       self.min_abs_gex,
            "vix_ceiling":       self.vix_ceiling,
            "sign_convention":   self.sign_convention,
            "dte_entry_long":    self.dte_entry_long,
            "dte_entry_condor":  self.dte_entry_condor,
            "short_leg_delta":   self.short_leg_delta,
            "wing_em_width":     self.wing_em_width,
            "base_risk_pct":     self.base_risk_pct * 100,
            "max_risk_pct":      self.max_risk_pct * 100,
            "condor_profit_tgt": self.condor_profit_tgt,
            "condor_stop_mult":  self.condor_stop_mult,
            "condor_dte_exit":   self.condor_dte_exit,
            "straddle_tp_mult":  self.straddle_tp_mult,
            "straddle_stop_pct": self.straddle_stop_pct,
            "straddle_dte_exit": self.straddle_dte_exit,
        }

    def get_backtest_ui_params(self) -> list[dict]:
        return [
            {"key": "near_flip_pct",    "label": "Near-flip zone (% dist)", "type": "float", "default": 0.25, "min": 0.05, "max": 1.0, "step": 0.05, "col": 0, "row": 0},
            {"key": "base_risk_pct",    "label": "Base risk (% capital)",    "type": "float", "default": 0.75, "min": 0.25, "max": 3.0, "step": 0.25, "col": 1, "row": 0},
            {"key": "max_risk_pct",     "label": "Max risk (% capital)",     "type": "float", "default": 1.5,  "min": 0.5,  "max": 5.0, "step": 0.25, "col": 2, "row": 0},
            {"key": "dte_entry_long",   "label": "Straddle DTE",             "type": "int",   "default": 30,   "min": 14,   "max": 60,  "col": 0, "row": 1},
            {"key": "dte_entry_condor", "label": "Condor DTE",               "type": "int",   "default": 35,   "min": 21,   "max": 60,  "col": 1, "row": 1},
            {"key": "short_leg_delta",  "label": "Condor short Δ",           "type": "float", "default": 0.15, "min": 0.08, "max": 0.30, "step": 0.01, "col": 2, "row": 1},
            {"key": "vix_ceiling",      "label": "VIX entry ceiling",        "type": "int",   "default": 35,   "min": 20,   "max": 60,  "col": 0, "row": 2},
            {"key": "wing_em_width",    "label": "Condor wing width (× EM)", "type": "float", "default": 2.0,  "min": 1.0,  "max": 4.0, "step": 0.25, "col": 1, "row": 2},
        ]

    # ═══════════════════════════════════════════════════════════════════════
    # Live signal
    # ═══════════════════════════════════════════════════════════════════════

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Required snapshot keys:
            option_chain : DataFrame (required)
            spot         : float (required)
        Optional:
            vix          : float
        """
        chain = market_snapshot.get("option_chain")
        spot  = market_snapshot.get("spot")
        vix   = float(market_snapshot.get("vix", 20.0))

        if chain is None or (isinstance(chain, pd.DataFrame) and chain.empty) or spot is None:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "missing chain or spot"})

        try:
            gex = compute_dealer_gex(chain, float(spot), sign_convention=self.sign_convention)
        except ValueError as e:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"gex compute failed: {e}"})

        if vix > self.vix_ceiling:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"vix {vix:.1f} > ceiling {self.vix_ceiling}",
                                          "gex_snapshot": _snap_to_dict(gex)})
        if abs(gex.net_gex) < self.min_abs_gex:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "|net_gex| below noise floor",
                                          "gex_snapshot": _snap_to_dict(gex)})

        regime   = classify_regime(gex, self.near_flip_pct)
        size_pct = self._size_for_distance(abs(gex.dist_to_flip_pct))

        if regime == "negative":
            signal, trade_type = "BUY",  "long_straddle"
        elif regime == "positive":
            signal, trade_type = "SELL", "iron_condor"
        else:
            signal, trade_type = "BUY",  "long_straddle"   # near-flip → long gamma

        return SignalResult(
            strategy_name     = self.name,
            signal            = signal,
            confidence        = min(1.0, abs(gex.dist_to_flip_pct) / max(self.near_flip_pct, 1e-6) * 0.5 + 0.5),
            position_size_pct = size_pct,
            metadata={
                "regime":        regime,
                "trade_type":    trade_type,
                "gex_snapshot":  _snap_to_dict(gex),
                "vix":           vix,
            },
        )

    # ═══════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════

    def _size_for_distance(self, abs_dist: float) -> float:
        """Linearly interpolate base_risk → max_risk as distance shrinks toward flip."""
        if abs_dist >= 0.02:
            return self.base_risk_pct
        t = max(0.0, 1.0 - abs_dist / 0.02)
        return self.base_risk_pct + t * (self.max_risk_pct - self.base_risk_pct)

    @staticmethod
    def _find_delta_strike(spot: float, T: float, iv: float, target_delta: float,
                           opt_type: str) -> float:
        """Invert BS for a target-delta strike."""
        from scipy.optimize import brentq
        from scipy.stats import norm as _norm
        if T <= 0 or iv <= 0:
            return spot
        def obj(K):
            if K <= 0:
                return 1.0
            d1 = (math.log(spot / K) + (_RISK_FREE + 0.5 * iv * iv) * T) / (iv * math.sqrt(T))
            d  = float(_norm.cdf(d1)) if opt_type == "call" else float(_norm.cdf(d1) - 1.0)
            return abs(d) - target_delta
        try:
            return float(brentq(obj, spot * 0.5, spot * 1.5, xtol=0.01, maxiter=50))
        except Exception:
            move = iv * math.sqrt(T) * spot
            return spot + move if opt_type == "call" else spot - move

    # ═══════════════════════════════════════════════════════════════════════
    # Backtest
    # ═══════════════════════════════════════════════════════════════════════

    def backtest(
        self,
        price_data:       pd.DataFrame,
        auxiliary_data:   dict,
        starting_capital: float = 100_000.0,
        ticker:           str   = "SPY",
        progress_callback = None,
        **kwargs,
    ) -> BacktestResult:
        from alan_trader.backtest.engine import bs_price as _bs_price

        opts = auxiliary_data.get("option_snapshots")
        if opts is None or (isinstance(opts, pd.DataFrame) and opts.empty):
            raise ValueError(
                "dealer_gamma_regime: option_snapshots is required but missing. "
                "Sync options data for this ticker before running the backtest."
            )

        vix_df = auxiliary_data.get("vix")
        price_data = price_data.sort_index()

        # Snapshot date column
        date_col = None
        for c in ("SnapshotDate", "snapshot_date", "date", "Date"):
            if c in opts.columns:
                date_col = c
                break
        if date_col is None:
            raise ValueError("option_snapshots must have a date column (SnapshotDate/date/etc.)")

        opts = opts.copy()
        opts[date_col] = pd.to_datetime(opts[date_col])

        if vix_df is not None and not isinstance(vix_df.index, pd.DatetimeIndex):
            try:
                vix_df = vix_df.set_index(pd.to_datetime(vix_df.index))
            except Exception:
                vix_df = None

        snap_dates  = sorted(opts[date_col].dt.normalize().unique())
        price_dates = set(pd.to_datetime(price_data.index).normalize())
        snap_dates  = [d for d in snap_dates if d in price_dates]

        if len(snap_dates) < 20:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": f"Insufficient snapshots: {len(snap_dates)} (need ≥ 20)"},
            )

        capital    = float(starting_capital)
        equity_pts = []
        trade_rows: list[dict] = []
        open_trade: Optional[dict] = None
        regime_log: list[dict] = []
        _slip = self.slippage_per_leg
        _comm = self.commission_per_leg

        total = len(snap_dates)
        for i, snap_dt in enumerate(snap_dates):
            ts = pd.Timestamp(snap_dt)
            if ts not in price_data.index:
                continue
            spot = float(price_data.loc[ts, "close"])
            if spot <= 0:
                continue

            chain_today = opts[opts[date_col].dt.normalize() == ts]
            if chain_today.empty:
                equity_pts.append({"date": ts, "equity": capital + self._mtm(open_trade, spot, ts, _bs_price)})
                continue

            # VIX
            vix_val = 20.0
            if vix_df is not None:
                try:
                    vs = vix_df.loc[:ts, "close"].dropna()
                    if not vs.empty:
                        vix_val = float(vs.iloc[-1])
                except Exception:
                    pass

            # Compute GEX
            try:
                gex = compute_dealer_gex(chain_today, spot, sign_convention=self.sign_convention)
            except ValueError as e:
                logger.debug(f"GEX failed {ts}: {e}")
                equity_pts.append({"date": ts, "equity": capital + self._mtm(open_trade, spot, ts, _bs_price)})
                continue

            regime = classify_regime(gex, self.near_flip_pct)
            regime_log.append({"date": ts, "regime": regime, "net_gex": gex.net_gex,
                               "dist_to_flip_pct": gex.dist_to_flip_pct,
                               "flip_level": gex.flip_level})

            # ── Manage open trade (exit checks) ──────────────────────────
            if open_trade is not None:
                days_held = (ts - open_trade["entry_date"]).days
                dte_rem   = max(0, open_trade["entry_dte"] - days_held)
                iv        = self._atm_iv_from_chain(chain_today, spot) or open_trade["entry_iv"]
                T         = max(dte_rem, 1) / 365.0
                closed, exit_reason, net_pnl = False, "time", 0.0

                if open_trade["type"] == "long_straddle":
                    cv = _bs_price(spot, open_trade["call_k"], T, _RISK_FREE, iv, "call")
                    pv = _bs_price(spot, open_trade["put_k"],  T, _RISK_FREE, iv, "put")
                    curr = (cv + pv) * 100 * open_trade["contracts"]
                    cost = open_trade["cost"]
                    pnl  = curr - cost
                    tp   = pnl >= self.straddle_tp_mult * cost
                    sl   = pnl <= -self.straddle_stop_pct * cost
                    if tp or sl or dte_rem <= self.straddle_dte_exit:
                        exit_reason = "profit" if tp else ("loss" if sl else "time")
                        net_pnl = pnl - _comm * open_trade["contracts"] * 2
                        capital += net_pnl
                        closed = True

                elif open_trade["type"] == "iron_condor":
                    bc = _bs_price(spot, open_trade["body_call_k"], T, _RISK_FREE, iv, "call")
                    bp = _bs_price(spot, open_trade["body_put_k"],  T, _RISK_FREE, iv, "put")
                    wc = _bs_price(spot, open_trade["wing_call_k"], T, _RISK_FREE, iv, "call")
                    wp = _bs_price(spot, open_trade["wing_put_k"],  T, _RISK_FREE, iv, "put")
                    # Cost to close: buy body back, sell wings back
                    close_cost_per = (bc + _slip + bp + _slip - wc + _slip - wp + _slip) * 100
                    close_cost = close_cost_per * open_trade["contracts"]
                    credit = open_trade["credit"]
                    pnl    = credit - close_cost
                    tp     = pnl >= self.condor_profit_tgt * credit
                    sl     = pnl <= -self.condor_stop_mult * credit
                    if tp or sl or dte_rem <= self.condor_dte_exit:
                        exit_reason = "profit" if tp else ("loss" if sl else "time")
                        net_pnl = pnl - _comm * open_trade["contracts"] * 4
                        capital += net_pnl
                        # release margin
                        capital += open_trade["margin"]
                        closed = True

                if closed:
                    trade_rows.append({
                        "ticker":      ticker,
                        "entry_date":  open_trade["entry_date"],
                        "exit_date":   ts,
                        "trade_type":  open_trade["type"],
                        "regime":      open_trade["regime"],
                        "contracts":   open_trade["contracts"],
                        "cost":        round(open_trade["cost"], 2),
                        "pnl":         round(net_pnl, 2),
                        "exit_reason": exit_reason,
                    })
                    open_trade = None

            # ── Entry ────────────────────────────────────────────────────
            can_enter = (
                open_trade is None
                and vix_val <= self.vix_ceiling
                and abs(gex.net_gex) >= self.min_abs_gex
            )

            if can_enter:
                iv = self._atm_iv_from_chain(chain_today, spot) or 0.20
                size_pct = self._size_for_distance(abs(gex.dist_to_flip_pct))
                risk_budget = capital * size_pct

                if regime in ("negative", "near_flip"):
                    open_trade = self._open_straddle(
                        spot=spot, iv=iv, ts=ts, risk_budget=risk_budget,
                        bs_price=_bs_price, regime=regime,
                    )
                elif regime == "positive":
                    open_trade = self._open_condor(
                        spot=spot, iv=iv, ts=ts, risk_budget=risk_budget,
                        bs_price=_bs_price, regime=regime,
                        call_wall=gex.call_wall, put_wall=gex.put_wall,
                    )
                if open_trade is not None:
                    capital -= open_trade["cash_out"]

            # MTM
            equity_pts.append({"date": ts, "equity": capital + self._mtm(open_trade, spot, ts, _bs_price)})

            if progress_callback and i % 20 == 0:
                progress_callback(i / max(1, total), f"Simulating {i}/{total}…")

        # Close any open trade
        if open_trade is not None:
            trade_rows.append({
                "ticker":      ticker,
                "entry_date":  open_trade["entry_date"],
                "exit_date":   pd.Timestamp(snap_dates[-1]),
                "trade_type":  open_trade["type"],
                "regime":      open_trade["regime"],
                "contracts":   open_trade["contracts"],
                "cost":        round(open_trade["cost"], 2),
                "pnl":         0.0,
                "exit_reason": "end_of_data",
            })

        if not equity_pts:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": "No equity points produced"},
            )

        eq_df   = pd.DataFrame(equity_pts).set_index("date")["equity"].sort_index()
        eq_df   = eq_df[~eq_df.index.duplicated(keep="last")]
        returns = eq_df.pct_change().dropna()
        bench   = price_data["close"].pct_change().reindex(returns.index).dropna()

        trades_df = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame(
            columns=["ticker","entry_date","exit_date","trade_type","regime",
                     "contracts","cost","pnl","exit_reason"])
        metrics = compute_all_metrics(eq_df, trades_df if not trades_df.empty else None, bench)

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = eq_df,
            daily_returns = returns,
            trades        = trades_df,
            metrics       = metrics,
            params        = self.get_params(),
            extra         = {"regime_log": pd.DataFrame(regime_log), "ticker": ticker},
        )

    # ── Entry builders ────────────────────────────────────────────────────

    def _open_straddle(self, spot, iv, ts, risk_budget, bs_price, regime) -> Optional[dict]:
        T = self.dte_entry_long / 365.0
        call_k = self._find_delta_strike(spot, T, iv, 0.50, "call")
        put_k  = self._find_delta_strike(spot, T, iv, 0.50, "put")
        cv = bs_price(spot, call_k, T, _RISK_FREE, iv, "call") + self.slippage_per_leg
        pv = bs_price(spot, put_k,  T, _RISK_FREE, iv, "put")  + self.slippage_per_leg
        cost_per = (cv + pv) * 100
        if cost_per <= 0:
            return None
        contracts = max(1, int(risk_budget / cost_per))
        total_cost = cost_per * contracts + self.commission_per_leg * contracts * 2
        return {
            "type":       "long_straddle",
            "regime":     regime,
            "entry_date": ts,
            "entry_dte":  self.dte_entry_long,
            "entry_iv":   iv,
            "call_k":     call_k,
            "put_k":      put_k,
            "contracts":  contracts,
            "cost":       total_cost,
            "cash_out":   total_cost,
            "margin":     0.0,
            "credit":     0.0,
        }

    def _open_condor(self, spot, iv, ts, risk_budget, bs_price, regime,
                     call_wall, put_wall) -> Optional[dict]:
        dte = self.dte_entry_condor
        T   = dte / 365.0

        # Anchor body near call wall if one exists above spot, else use target delta.
        sc_k = self._find_delta_strike(spot, T, iv, self.short_leg_delta,     "call")
        sp_k = self._find_delta_strike(spot, T, iv, self.short_leg_delta,     "put")
        if call_wall is not None and call_wall > spot:
            sc_k = min(sc_k, call_wall)           # don't go BEYOND the wall
        if put_wall is not None and put_wall < spot:
            sp_k = max(sp_k, put_wall)

        em_pct = expected_move_pct(iv, dte)
        wing_w = max(1.0, self.wing_em_width * em_pct * spot)
        wc_k = sc_k + wing_w
        wp_k = sp_k - wing_w

        sc_v = bs_price(spot, sc_k, T, _RISK_FREE, iv, "call") - self.slippage_per_leg
        sp_v = bs_price(spot, sp_k, T, _RISK_FREE, iv, "put")  - self.slippage_per_leg
        wc_v = bs_price(spot, wc_k, T, _RISK_FREE, iv, "call") + self.slippage_per_leg
        wp_v = bs_price(spot, wp_k, T, _RISK_FREE, iv, "put")  + self.slippage_per_leg
        credit_per = max(0.01, (sc_v + sp_v - wc_v - wp_v) * 100)

        # Max loss = max(call wing, put wing) × 100 − credit
        width = max(wc_k - sc_k, sp_k - wp_k) * 100
        max_loss_per = max(1.0, width - credit_per)
        contracts = max(1, int(risk_budget / max_loss_per))
        margin    = max_loss_per * contracts
        if margin <= 0:
            return None
        credit_total = credit_per * contracts
        return {
            "type":        "iron_condor",
            "regime":      regime,
            "entry_date":  ts,
            "entry_dte":   dte,
            "entry_iv":    iv,
            "body_call_k": sc_k,
            "body_put_k":  sp_k,
            "wing_call_k": wc_k,
            "wing_put_k":  wp_k,
            "contracts":   contracts,
            "cost":        margin,
            "credit":      credit_total,
            "margin":      margin,
            "cash_out":    margin - credit_total,
        }

    # ── MTM ──────────────────────────────────────────────────────────────

    def _mtm(self, trade, spot, ts, bs_price) -> float:
        if trade is None:
            return 0.0
        days_held = (ts - trade["entry_date"]).days
        dte_rem   = max(1, trade["entry_dte"] - days_held)
        T         = dte_rem / 365.0
        iv        = trade["entry_iv"]
        if trade["type"] == "long_straddle":
            cv = bs_price(spot, trade["call_k"], T, _RISK_FREE, iv, "call")
            pv = bs_price(spot, trade["put_k"],  T, _RISK_FREE, iv, "put")
            return max(0.0, (cv + pv) * 100 * trade["contracts"])
        # iron condor
        bc = bs_price(spot, trade["body_call_k"], T, _RISK_FREE, iv, "call")
        bp = bs_price(spot, trade["body_put_k"],  T, _RISK_FREE, iv, "put")
        wc = bs_price(spot, trade["wing_call_k"], T, _RISK_FREE, iv, "call")
        wp = bs_price(spot, trade["wing_put_k"],  T, _RISK_FREE, iv, "put")
        close_cost = (bc + bp - wc - wp) * 100 * trade["contracts"]
        # equity value = margin posted + (credit received - cost to close)
        return max(0.0, trade["margin"] + trade["credit"] - close_cost - trade["margin"])

    # ── ATM IV lookup ────────────────────────────────────────────────────

    @staticmethod
    def _atm_iv_from_chain(chain: pd.DataFrame, spot: float) -> Optional[float]:
        """Grab IV of the strike closest to spot. Returns None if unavailable."""
        iv_col = None
        for c in ("iv", "IV", "implied_volatility", "ImpliedVolatility"):
            if c in chain.columns:
                iv_col = c
                break
        strike_col = None
        for c in ("strike", "Strike", "StrikePrice", "strike_price"):
            if c in chain.columns:
                strike_col = c
                break
        if iv_col is None or strike_col is None or chain.empty:
            return None
        tmp = chain.copy()
        tmp[strike_col] = pd.to_numeric(tmp[strike_col], errors="coerce")
        tmp[iv_col]     = pd.to_numeric(tmp[iv_col],     errors="coerce")
        tmp = tmp.dropna(subset=[strike_col, iv_col])
        tmp = tmp[(tmp[iv_col] > 0.01) & (tmp[iv_col] < 3.0)]
        if tmp.empty:
            return None
        idx = (tmp[strike_col] - spot).abs().idxmin()
        return float(tmp.loc[idx, iv_col])


def _snap_to_dict(snap: GEXSnapshot) -> dict:
    """Serialize GEXSnapshot for metadata payload (drops the full Series)."""
    return {
        "spot":             snap.spot,
        "net_gex":          snap.net_gex,
        "call_gex":         snap.call_gex,
        "put_gex":          snap.put_gex,
        "flip_level":       snap.flip_level,
        "dist_to_flip_pct": snap.dist_to_flip_pct,
        "call_wall":        snap.call_wall,
        "put_wall":         snap.put_wall,
        "net_gex_0dte":     snap.net_gex_0dte,
        "net_gex_multiday": snap.net_gex_multiday,
        "sign_convention":  snap.sign_convention,
        "warnings":         snap.warnings,
    }
