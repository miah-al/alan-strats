"""
VIX Calendar Spread Strategy.

THESIS
------
The VIX futures term structure is in contango approximately 80% of trading
days — front-month contracts trade below back-month contracts because the
market embeds a "fear premium" for distant unknown shocks while near-dated
volatility is more readily anchored to realised vol (Whaley 2009; Cheng
2018). This persistent contango is the well-documented "negative roll yield"
that drags down long VIX-futures and VIX-ETN holders (Eraker & Wu 2017).

VIX OPTIONS price off the corresponding VIX FUTURE for each expiry — not off
spot VIX. As a result, in normal contango the front-month VIX call's
underlying (M1 future) sits structurally below the back-month VIX call's
underlying (M2 future), so the front-month call's "moneyness" is
systematically worse and its premium decays faster as expiry approaches and
M1 → spot. A LONG-BACK / SHORT-FRONT VIX CALL CALENDAR captures this
asymmetry: the short front-month leg melts in contango while the back-month
leg retains time + vega value.

The trade has a defined-risk debit structure. Maximum loss is the net debit
× 100 × contracts: it is realised only if both legs go fully worthless, which
in practice requires a sharp VIX collapse far below the chosen strike (rare
once VIX is already calm). The position has POSITIVE VEGA on the back leg
and NEGATIVE GAMMA on the front leg — this is favourable in moderate vol
expansion (long vega gains more than short gamma loses on a slow drift
higher) but UNFAVOURABLE in a violent vol spike where the short front-month
gamma dominates. Hence the hard "VIX > 35" panic-close override: the short
leg blows up faster than the long leg can vega-rally, and what looked like
a defined-risk debit becomes a marked-to-market drawdown approaching the
full debit before expiry.

LITERATURE
----------
- Whaley (2009), "Understanding the VIX," J. of Portfolio Management 35(3):
  VIX construction, futures vs. spot, term structure dynamics.
- Eraker & Wu (2017), "Explaining the negative returns to VIX futures and
  ETNs," J. of Financial Economics 125(1): contango drag is the dominant
  source of long-VIX-futures losses.
- Cheng (2018), "The VIX Premium," Review of Financial Studies 32(1):
  documents the term-structure premium in VIX futures and its persistence
  through different vol regimes.
- Fernandez-Perez, Frijns & Tourani-Rad (2017): analogous calendar-spread
  mechanics in the contango/backwardation continuum.

PRICING
-------
VIX options are EUROPEAN-style (cash-settled at the special opening
quotation of VIX on settlement Wednesday). Black-Scholes is therefore the
correct closed-form price for both legs.  We price each leg with the SAME
underlying (current VIX-spot) as a tractable, lookahead-free proxy for the
respective futures levels — when no M1/M2 panel is supplied, the term-
structure ratio is approximated heuristically from realised contango.
This is documented as a heuristic; if VIX futures M1/M2 are supplied via
``auxiliary_data["vix_term"]``, the *futures-level* term ratio is used at
entry but the *spot* VIX is still used to price the options (mirroring the
"VIX-anchored" simplification commonly used in academic backtests when full
futures-strip data is unavailable).

GATING (entry, all required)
----------------------------
1. Term-structure ratio M2/M1 >= ``term_ratio_min`` (default 1.05) — the
   trade only makes sense in contango; backwardation inverts the edge.
2. Spot VIX <= ``vix_max_entry`` (default 22) — once VIX is already
   elevated, both legs are expensive and the entry cost erodes the edge.
3. VIX 5-day pct-change <= 25% — skip if vol is accelerating up;
   calendars hate trending vol.

EXITS (first trigger wins)
--------------------------
- Profit target: +30% of debit
- Stop loss:     -50% of debit
- Time exit:     front-month DTE <= 5 (close before pin / settlement risk)
- VIX-spike override: spot VIX > 35 ⇒ close immediately, regardless of P&L
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy,
    BacktestResult,
    SignalResult,
    StrategyStatus,
    StrategyType,
)
from alan_trader.backtest.engine import (
    bs_price_skew,
    DEFAULT_SLIPPAGE_PER_LEG,
    DEFAULT_COMMISSION_PER_LEG,
)
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)

_RISK_FREE_RATE = 0.045


# ─── Helpers ────────────────────────────────────────────────────────────────

def _heuristic_term_ratio(vix: pd.Series, lookback: int = 20) -> pd.Series:
    """
    Heuristic M2/M1 ratio when real VIX futures aren't available.

    Rationale: when VIX-spot is below its rolling mean (calm regime), futures
    contango tends to be wider (M2/M1 ~ 1.05–1.15). When VIX-spot is above
    its rolling mean (stress regime), the curve flattens or inverts
    (backwardation, M2/M1 < 1.0). We model:

        ratio_t = 1 + clip( (mean_t - vix_t) / mean_t , -0.10, 0.15 )

    bounded so the heuristic NEVER exceeds the realistic [-10%, +15%] band
    for VIX futures contango/backwardation. This is intentionally
    conservative — no synthetic alpha is created.
    """
    mean = vix.rolling(lookback, min_periods=max(5, lookback // 2)).mean()
    raw  = (mean - vix) / mean.replace(0, np.nan)
    return (1.0 + raw.clip(-0.10, 0.15)).fillna(1.0)


# ─── Strategy class ─────────────────────────────────────────────────────────

class VIXCalendarSpreadStrategy(BaseStrategy):
    """
    Long-back / short-front VIX-call CALENDAR spread.

    Captures VIX futures contango (M2 > M1) as expressed in the relative
    pricing of back-month vs. front-month VIX call options, with a hard
    panic-close override for vol spikes.

    Entry rules (all must pass):
      1. term ratio (M2/M1) >= ``term_ratio_min``
      2. spot VIX <= ``vix_max_entry``
      3. VIX 5-day pct change <= 0.25 (no upward acceleration)

    Trade structure (DEFINED RISK / DEBIT):
      LONG  back-month VIX call  (DTE ~ ``dte_back_target``)
      SHORT front-month VIX call (DTE ~ ``dte_front_target``)
      Same strike, set ``strike_otm_pct`` above current spot VIX.

    Max loss = debit × 100 × contracts (when both legs collapse to zero).

    Exits (first trigger wins):
      profit  +30% of debit
      stop    -50% of debit
      time    front-month DTE <= 5
      panic   spot VIX > 35 (immediate close, intra-bar)
    """

    name                 = "calendar_spread_vix"
    display_name         = "Calendar Spread (VIX)"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Long back-month / short front-month VIX call calendar. Captures the "
        "structural VIX futures contango (Eraker-Wu 2017, Cheng 2018) via the "
        "term-structure premium embedded in VIX call IV. Hard panic-close on "
        "VIX > 35. Defined-risk debit; max loss = debit × 100 × contracts."
    )
    asset_class          = "volatility"
    typical_holding_days = 18
    target_sharpe        = 1.2

    def __init__(
        self,
        dte_back_target:    int   = 75,
        dte_front_target:   int   = 21,
        strike_otm_pct:     float = 0.10,
        term_ratio_min:     float = 1.05,
        vix_max_entry:      float = 22.0,
        vix_spike_close:    float = 35.0,
        vix_5d_max_change:  float = 0.25,
        profit_target_pct:  float = 0.30,
        stop_loss_pct:      float = 0.50,
        dte_close_at:       int   = 5,
        position_size_pct:  float = 0.02,
        max_concurrent:     int   = 2,
        slippage_per_leg:   float = DEFAULT_SLIPPAGE_PER_LEG,
        commission_per_leg: float = DEFAULT_COMMISSION_PER_LEG,
    ):
        self.dte_back_target    = dte_back_target
        self.dte_front_target   = dte_front_target
        self.strike_otm_pct     = strike_otm_pct
        self.term_ratio_min     = term_ratio_min
        self.vix_max_entry      = vix_max_entry
        self.vix_spike_close    = vix_spike_close
        self.vix_5d_max_change  = vix_5d_max_change
        self.profit_target_pct  = profit_target_pct
        self.stop_loss_pct      = stop_loss_pct
        self.dte_close_at       = dte_close_at
        self.position_size_pct  = position_size_pct
        self.max_concurrent     = max_concurrent
        self.slippage_per_leg   = slippage_per_leg
        self.commission_per_leg = commission_per_leg

    # ── Params ───────────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        return {
            "dte_back_target":    self.dte_back_target,
            "dte_front_target":   self.dte_front_target,
            "strike_otm_pct":     self.strike_otm_pct,
            "term_ratio_min":     self.term_ratio_min,
            "vix_max_entry":      self.vix_max_entry,
            "vix_spike_close":    self.vix_spike_close,
            "vix_5d_max_change":  self.vix_5d_max_change,
            "profit_target_pct":  self.profit_target_pct,
            "stop_loss_pct":      self.stop_loss_pct,
            "dte_close_at":       self.dte_close_at,
            "position_size_pct":  self.position_size_pct,
            "max_concurrent":     self.max_concurrent,
            "slippage_per_leg":   self.slippage_per_leg,
            "commission_per_leg": self.commission_per_leg,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "term_ratio_min", "label": "Min M2/M1 contango",
             "type": "slider", "min": 1.00, "max": 1.20, "default": 1.05, "step": 0.01,
             "col": 0, "row": 0,
             "help": "Skip entries when VIX futures term structure isn't sufficiently in contango"},
            {"key": "vix_max_entry", "label": "Max VIX at entry",
             "type": "slider", "min": 14.0, "max": 35.0, "default": 22.0, "step": 1.0,
             "col": 1, "row": 0,
             "help": "Above this VIX, both legs are too expensive — entry cost erodes the edge"},
            {"key": "vix_spike_close", "label": "Panic-close VIX",
             "type": "slider", "min": 25.0, "max": 60.0, "default": 35.0, "step": 1.0,
             "col": 2, "row": 0,
             "help": "Hard immediate-close override when spot VIX exceeds this level"},
            {"key": "dte_back_target", "label": "Back-month DTE",
             "type": "slider", "min": 45, "max": 120, "default": 75, "step": 5,
             "col": 0, "row": 1, "help": "Target days-to-expiry of the long-back VIX call"},
            {"key": "dte_front_target", "label": "Front-month DTE",
             "type": "slider", "min": 10, "max": 35, "default": 21, "step": 1,
             "col": 1, "row": 1, "help": "Target days-to-expiry of the short-front VIX call"},
            {"key": "strike_otm_pct", "label": "Strike OTM (% of VIX)",
             "type": "slider", "min": 0.00, "max": 0.30, "default": 0.10, "step": 0.01,
             "col": 2, "row": 1, "help": "Common strike, set this fraction above spot VIX"},
            {"key": "profit_target_pct", "label": "Profit target (% of debit)",
             "type": "slider", "min": 0.10, "max": 0.75, "default": 0.30, "step": 0.05,
             "col": 0, "row": 2, "help": "Close at this fraction of the debit paid"},
            {"key": "stop_loss_pct", "label": "Stop loss (% of debit)",
             "type": "slider", "min": 0.20, "max": 0.90, "default": 0.50, "step": 0.05,
             "col": 1, "row": 2, "help": "Close at this fraction of the debit lost"},
            {"key": "max_concurrent", "label": "Max concurrent",
             "type": "slider", "min": 1, "max": 5, "default": 2, "step": 1,
             "col": 2, "row": 2, "help": "Maximum simultaneous open VIX calendars"},
        ]

    # ── Live signal ──────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Live entry gate. ``market_snapshot`` should contain:
          vix              : current spot VIX
          term_ratio       : current M2/M1 VIX futures ratio (preferred)
          vix_5d_change    : trailing 5-day pct change of VIX (optional)
        """
        vix          = float(market_snapshot.get("vix", 20.0))
        term_ratio   = float(market_snapshot.get("term_ratio", 1.0))
        vix_5d_chg   = float(market_snapshot.get("vix_5d_change", 0.0))

        # Hard panic close has priority — even live signal flags it
        if vix > self.vix_spike_close:
            return SignalResult(
                self.name, "HOLD", 0.0, 0.0,
                metadata={"reason": f"VIX {vix:.1f} > spike threshold {self.vix_spike_close}",
                          "regime": "panic"},
            )

        reasons = []
        if term_ratio < self.term_ratio_min:
            reasons.append(f"term ratio {term_ratio:.3f} < {self.term_ratio_min}")
        if vix > self.vix_max_entry:
            reasons.append(f"VIX {vix:.1f} > {self.vix_max_entry}")
        if vix_5d_chg > self.vix_5d_max_change:
            reasons.append(f"VIX 5d chg {vix_5d_chg:+.2%} > {self.vix_5d_max_change:.0%}")

        if reasons:
            return SignalResult(
                self.name, "HOLD", 0.0, 0.0,
                metadata={"reason": "; ".join(reasons), "vix": vix,
                          "term_ratio": term_ratio},
            )

        # Confidence scales with contango depth and VIX calmness
        contango_score = float(np.clip((term_ratio - self.term_ratio_min) / 0.10, 0.0, 1.0))
        calm_score     = float(np.clip(1.0 - (vix - 12) / (self.vix_max_entry - 12), 0.0, 1.0))
        confidence     = float(np.clip(0.40 + 0.35 * contango_score + 0.25 * calm_score,
                                       0.30, 0.90))

        strike = round(vix * (1.0 + self.strike_otm_pct), 2)
        return SignalResult(
            strategy_name=self.name,
            signal="BUY",
            confidence=confidence,
            position_size_pct=self.position_size_pct,
            metadata={
                "structure":         "vix_call_calendar",
                "leg_long":          {"side": "BUY",  "type": "call",
                                      "strike": strike, "dte": self.dte_back_target},
                "leg_short":         {"side": "SELL", "type": "call",
                                      "strike": strike, "dte": self.dte_front_target},
                "vix":               vix,
                "term_ratio":        term_ratio,
                "vix_5d_change":     vix_5d_chg,
                "european_settled":  True,
            },
        )

    # ── Backtest ─────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:       pd.DataFrame,           # VIX-spot OHLC, date-indexed
        auxiliary_data:   dict,                   # may include "vix_term": M1/M2 futures
        starting_capital: float = 100_000,
        **kwargs,
    ) -> BacktestResult:
        """
        Bar-by-bar walk-forward simulation.

        ``price_data``      : VIX SPOT OHLC. Required. Must have a "close" column.
        ``auxiliary_data``  : dict.
            "vix_term"  – DataFrame indexed by date with columns "m1_close",
                          "m2_close" giving VIX-futures front and 2nd-month
                          settlement prices. PREFERRED — used to compute the
                          true M2/M1 term ratio at entry.

                          If absent, a heuristic ratio (see
                          ``_heuristic_term_ratio``) is used and a WARNING is
                          logged. The heuristic is bounded to realistic
                          contango/backwardation magnitudes; it is *not* a
                          source of synthetic alpha.

        Per-bar mechanics (no lookahead):
          1. MTM all open calendars at today's spot/IV; check exits.
          2. Hard panic close if VIX_today > vix_spike_close — fires
             IMMEDIATELY before further exit checks (and before any new entry).
          3. Profit-target / stop-loss / time-exit checks (first wins).
          4. Entry gate using TODAY's snapshot only:
                term_ratio_today >= term_ratio_min
                vix_today        <= vix_max_entry
                |vix 5d pct chg| <= vix_5d_max_change
          5. Open spread: BS-price both legs at today's spot VIX with their
             respective times-to-expiry; debit = back - front (must be > 0).
        """

        # ── Validate primary data ──────────────────────────────────────────
        if price_data is None or len(price_data) == 0 or "close" not in price_data.columns:
            raise ValueError(
                "VIX Calendar Spread requires VIX-spot price_data with a 'close' "
                "column. Sync VIX in Data Manager → Macro Bars."
            )

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_data = price_data.sort_index()
        vix = price_data["close"].astype(float)

        # ── Term-structure source ──────────────────────────────────────────
        vix_term = auxiliary_data.get("vix_term") if auxiliary_data else None
        used_heuristic = False
        if (
            vix_term is None
            or not isinstance(vix_term, pd.DataFrame)
            or vix_term.empty
            or not {"m1_close", "m2_close"}.issubset(vix_term.columns)
        ):
            logger.warning(
                "VIXCalendarSpread: no vix_term futures panel supplied; "
                "falling back to bounded heuristic term ratio derived from "
                "VIX-spot relative to its 20d mean. Results approximate."
            )
            term_ratio_s = _heuristic_term_ratio(vix, lookback=20)
            used_heuristic = True
        else:
            vt = vix_term.copy()
            vt.index = pd.to_datetime(vt.index)
            m1 = vt["m1_close"].astype(float).reindex(vix.index).ffill()
            m2 = vt["m2_close"].astype(float).reindex(vix.index).ffill()
            term_ratio_s = (m2 / m1.replace(0, np.nan)).fillna(1.0)

        vix_5d_chg = vix.pct_change(5).fillna(0.0)

        # ── Sim state ──────────────────────────────────────────────────────
        capital        = float(starting_capital)
        equity_curve   = []
        open_trades:   list[dict] = []
        closed_trades: list[dict] = []
        signal_log:    list[dict] = []

        all_dates = list(price_data.index)
        n         = len(all_dates)
        r         = _RISK_FREE_RATE
        comm      = self.commission_per_leg
        slip      = self.slippage_per_leg

        for i, dt in enumerate(all_dates):
            spot       = float(vix.iloc[i])
            iv_proxy   = max(spot / 100.0, 0.05)   # VIX itself is the IV-of-SPX proxy
            ratio_now  = float(term_ratio_s.iloc[i])
            chg5_now   = float(vix_5d_chg.iloc[i])

            # ── 1. MTM and exits ───────────────────────────────────────────
            still_open: list[dict] = []
            unrealized_pnl = 0.0
            panic = spot > self.vix_spike_close

            for trade in open_trades:
                dte_back  = max(trade["expiry_back_idx"]  - i, 0)
                dte_front = max(trade["expiry_front_idx"] - i, 0)
                T_back  = max(dte_back  / 252.0, 1e-6)
                T_front = max(dte_front / 252.0, 1e-6)

                back_val  = bs_price_skew(spot, trade["strike"], T_back,  r, iv_proxy, "call")
                front_val = bs_price_skew(spot, trade["strike"], T_front, r, iv_proxy, "call")
                cur_value = back_val - front_val   # net spread value (long back, short front)
                pnl_per   = cur_value - trade["debit"]
                pnl_tot   = pnl_per * trade["contracts"] * 100

                exit_reason = None
                if panic:
                    exit_reason = "vix_spike"
                elif pnl_per >= self.profit_target_pct * trade["debit"]:
                    exit_reason = "profit_target"
                elif pnl_per <= -self.stop_loss_pct * trade["debit"]:
                    exit_reason = "stop_loss"
                elif dte_front <= self.dte_close_at:
                    exit_reason = "dte_front_close"
                elif i == n - 1:
                    exit_reason = "end_of_data"

                if exit_reason:
                    close_comm = 2 * comm * trade["contracts"]
                    close_slip = 2 * slip * trade["contracts"] * 100
                    net_pnl    = round(pnl_tot - close_comm - close_slip, 2)
                    capital   += net_pnl
                    closed_trades.append({
                        "entry_date":  trade["entry_date"].date(),
                        "exit_date":   dt.date(),
                        "strike":      round(trade["strike"], 2),
                        "debit":       round(trade["debit"], 4),
                        "contracts":   trade["contracts"],
                        "pnl":         net_pnl,
                        "exit_reason": exit_reason,
                        "vix_at_exit": round(spot, 2),
                        "winner":      net_pnl > 0,
                    })
                else:
                    still_open.append(trade)
                    unrealized_pnl += pnl_per * trade["contracts"] * 100

            open_trades = still_open
            mtm_equity  = capital + unrealized_pnl
            equity_curve.append(mtm_equity)

            # ── 2. Entry gate ──────────────────────────────────────────────
            if panic:
                continue                                # never open during a spike
            if len(open_trades) >= self.max_concurrent:
                continue
            if (n - i) <= self.dte_back_target:
                continue                                # not enough forward bars
            if spot <= 0 or np.isnan(ratio_now) or np.isnan(chg5_now):
                continue

            gates_pass = (
                ratio_now    >= self.term_ratio_min
                and spot     <= self.vix_max_entry
                and chg5_now <= self.vix_5d_max_change
            )

            signal_log.append({
                "date":       dt.date(),
                "vix":        round(spot, 2),
                "term_ratio": round(ratio_now, 4),
                "vix_5d":     round(chg5_now, 4),
                "regime":     "ENTER" if gates_pass else "SKIP",
            })

            if not gates_pass:
                continue

            # ── 3. Open spread ────────────────────────────────────────────
            strike  = spot * (1.0 + self.strike_otm_pct)
            T_back  = self.dte_back_target  / 252.0
            T_front = self.dte_front_target / 252.0

            back_px  = bs_price_skew(spot, strike, T_back,  r, iv_proxy, "call")
            front_px = bs_price_skew(spot, strike, T_front, r, iv_proxy, "call")
            debit    = back_px - front_px
            if debit <= 0.05:
                continue                                # no edge / pricing noise

            # Sizing: debit × 100 × contracts ≤ position_size_pct × capital
            max_dollars = max(capital * self.position_size_pct, 0.0)
            denom       = (debit + 2 * slip) * 100      # debit incl. entry slippage
            contracts   = max(int(max_dollars // denom), 1) if denom > 0 else 1

            entry_comm = 2 * comm * contracts
            entry_slip = 2 * slip * contracts * 100
            entry_cost = debit * contracts * 100 + entry_comm + entry_slip
            if entry_cost > capital:
                continue                                # insufficient cash for debit

            capital -= entry_cost
            open_trades.append({
                "entry_date":      dt,
                "expiry_back_idx": min(i + self.dte_back_target,  n - 1),
                "expiry_front_idx": min(i + self.dte_front_target, n - 1),
                "strike":          strike,
                "debit":           debit,
                "contracts":       contracts,
                "vix_at_entry":    spot,
                "ratio_at_entry":  ratio_now,
            })

        # ── Build output ───────────────────────────────────────────────────
        eq            = pd.Series(equity_curve, index=all_dates, dtype=float)
        daily_returns = eq.pct_change().dropna()
        trades_df     = pd.DataFrame(closed_trades) if closed_trades else pd.DataFrame()
        signal_df     = pd.DataFrame(signal_log)    if signal_log    else pd.DataFrame()
        metrics       = compute_all_metrics(eq, trades_df if not trades_df.empty else None)

        if not trades_df.empty:
            n_t = len(trades_df)
            n_w = int(trades_df["winner"].sum())
            logger.info(
                f"VIXCalendarSpread: {n_t} trades, {n_w}/{n_t} winners "
                f"({100 * n_w / max(n_t, 1):.1f}%), final capital ${capital:,.0f}"
            )
        else:
            logger.warning("VIXCalendarSpread: 0 trades — check term-ratio / VIX filters")

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=eq,
            daily_returns=daily_returns,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
            extra={
                "signal_log":     signal_df,
                "n_open_at_end":  len(open_trades),
                "term_ratio":     term_ratio_s,
                "used_heuristic": used_heuristic,
            },
        )
