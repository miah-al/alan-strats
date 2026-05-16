"""
Tail Risk Long Put — Rules-Based Portfolio Insurance (Naked Long Put Variant).

THESIS
------
The Tail Risk Long Put is the gold-standard, full-payout systematic tail-hedge
program: a *naked* long out-of-the-money put on SPY/SPX, mechanically purchased
on a monthly cadence and rolled before the theta cliff. Unlike the put-spread
variant (see ``tail_risk_put_spread``), this strategy carries no short leg —
the payout is **uncapped** in deep crashes. The trade-off is a higher annual
premium drag (typically 1.0–1.3% of NAV per Israelov & Nielsen 2015) for
unbounded crash convexity.

LITERATURE
----------
* Bhansali, V. (2008). *Tail Risk Hedging*. McGraw-Hill. Foundational text on
  systematic OTM put programs as portfolio insurance; argues that the discipline
  of mechanical purchase decoupled from sentiment is the strategy's core edge.
* Israelov, R. & Nielsen, L. (2015). "Still Not Cheap: Portfolio Protection in
  Calm Markets." *Journal of Portfolio Management*. The empirical study of
  long-put hedging on SPX establishing the 1.0–1.3% annual premium drag and
  documenting that the edge appears only when the behavioural drawdown-recovery
  effects on the *underlying portfolio* are accounted for.
* Cole, C. (2013). "Volatility at World's End: Two Decades of Movement in
  Markets." Artemis Capital. Quantifies the structural overpricing of OTM SPX
  puts (the variance-risk-premium that systematic put buyers structurally pay)
  and motivates the 15–20% OTM zone as the cost-efficient sweet spot.
* Calvet, L., Campbell, J. & Sodini, P. (2009). "Fight or Flight? Portfolio
  Rebalancing by Individual Investors." *QJE*. Documents persistent under-
  allocation to risk assets in the 12–36 months after an unhedged catastrophic
  drawdown — the second-order cost the long-put hedge exists to prevent.
* Barber, B. & Odean (2011). "The Behavior of Individual Investors." Documents
  retail underperformance from panic-selling at troughs.

CORE EDGE — WHY NAKED LONG PUT INSTEAD OF A SPREAD
---------------------------------------------------
The standalone EV of the long-put hedge is *negative* by design (the variance
risk premium). The standalone EV of the *portfolio including the hedge* is
positive for the majority of investors because the hedge:

  1. Eliminates the catastrophic-drawdown trigger for panic selling.
  2. Delivers convex, *uncapped* payoff in 30–50% crashes — exactly when
     the equity portfolio needs the most rescue capital.
  3. Allows the holder to maintain (or even grow) equity allocation through
     the crash window, capturing the subsequent recovery.

The naked long put (this strategy) keeps the convex tail wide-open, in
exchange for ~50–100% higher annual premium drag than the bear-put-spread
variant. For investors with the budget, naked long puts are the correct
expression of tail-hedging because the payout is unbounded in the tails that
matter most (1973, 2008-trough, 1929-style events).

STRUCTURE
---------
  Buy 1 SPY put @ ``long_otm_pct`` OTM   (15–20% OTM, the *protection* leg)
  No short leg — the payout is unbounded as SPY falls below the strike.
  DTE 60–90 at entry (default 75)
  Net debit: 0.15–0.30% of SPY notional per contract (varies with VIX)

  Worked example at SPY $477, VIX 17.3:
     long_K = 477 × (1 − 0.15) ≈ $405.45
     debit ≈ $1.80–$2.10 per contract  (0.40% of SPY notional)
     payout in -25% crash to SPY $358 = ($405 − $358) × 100 = $4,700/contract.

ROLLING PROTOCOL
----------------
* Mechanical purchase every ``purchase_cadence_days`` (default 30, monthly
  per the existing guide article — fresher protection than the spread variant
  because there is no short leg to fund the cost).
* Roll a position when EITHER:
    1. DTE drops to ``roll_at_dte`` (default 30) — avoid deep theta zone, OR
    2. Long-leg delta < ``roll_at_long_delta`` (default −0.30) — long put is
       deep ITM, harvest the gain and reset protection at a fresh strike.
* Cadence is fixed regardless of VIX level. The discipline IS the strategy.

ANNUAL COST CAP (HARD CONSTRAINT)
---------------------------------
Cumulative debit paid in any rolling 365-day window must not exceed
``annual_cost_cap_pct`` × starting_capital (default 1.5%, looser than the
spread variant's 1.0% — this is real tail insurance, not budget version).
If a scheduled purchase would breach the cap, contract count is scaled down
(and the trade skipped entirely if the residual budget cannot fund a single
contract).

ENTRY GATES
-----------
* VIX ≤ ``vix_max_at_entry`` (default 35). Above this level the program
  pauses for the cycle — historically the *worst* time to buy fresh insurance.
* Per-purchase debit ≤ ``position_size_pct`` × current capital (default 0.5%).
* Concurrent open puts ≤ ``max_concurrent`` (default 3 — allows staggered
  monthly rolls).

EARLY HARVEST RULE
------------------
If the put's mark-to-market gain ≥ ``profit_take_pct`` × debit (default 100% =
debit doubled), close the put immediately and re-enter at the next standard
strike / DTE pair. This locks in the gain and *resets protection* at a fresh
cost basis — exactly the harvest discipline described in the guide article.

IV PROXY (DOCUMENTED ASSUMPTION)
--------------------------------
Without per-strike skew data, this backtest uses VIX/100 as the ATM-IV proxy
and applies a ``put_iv_skew_mult`` (default 1.20) to that proxy when pricing
the long put. This reflects the empirically-observed SPX put skew: 15–20% OTM
puts trade at roughly 110–130% of ATM IV (Cole 2013, Israelov & Nielsen 2015).

PERFORMANCE EXPECTATIONS
------------------------
Expected behaviour by regime (per Israelov & Nielsen 2015, Bhansali 2008):
  Calm year (e.g. 2017, 2021)         : equity drifts down ≈ 1.0–1.3% (premium drag).
  Modest correction (e.g. H1 2018)    : approximately flat to slightly negative.
  Bear market (2008, 2022)            : meaningful gains, *uncapped* (unlike spread).
  Extreme crash (2020 March, 2008-Q4) : large convex gains — this is the payoff.
Target Sharpe: 0.4 (low Sharpe is correct — this is insurance with negative EV
when measured stand-alone; the value is portfolio-level drawdown reduction).
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

from alan_trader.strategies.base import (
    BaseStrategy,
    BacktestResult,
    SignalResult,
    StrategyStatus,
    StrategyType,
)
from alan_trader.backtest.engine import bs_price
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
_RISK_FREE_RATE       = 0.045    # 3-month T-Bill proxy
_MIN_HISTORY_BARS     = 30       # warm-up before first purchase
_DEFAULT_VIX_FALLBACK = 18.0


# ── Helpers ────────────────────────────────────────────────────────────────────

def _put_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes put delta. Returns value in [-1, 0]."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return -1.0 if S < K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1) - 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy class
# ─────────────────────────────────────────────────────────────────────────────

class TailRiskLongPutStrategy(BaseStrategy):
    """
    Systematic Tail Risk Long Put — naked OTM long put on SPY rolled on a
    monthly cadence as portfolio insurance. The full, uncapped-payout variant
    of the put-spread tail hedge — higher cost, unbounded crash convexity.

    See module docstring for the full quant thesis.
    """

    name                 = "tail_risk_long_put"
    display_name         = "Tail Risk Long Put"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Systematic naked long put on SPY (15–18% OTM, 60–90 DTE). Mechanical "
        "monthly rolling, hard 1.5% annual cost cap, early harvest on 100%+ gains. "
        "Uncapped-payout tail hedge — higher premium drag than the put-spread "
        "variant in exchange for unbounded crash convexity. Negative-EV insurance "
        "(Bhansali 2008; Israelov & Nielsen 2015)."
    )
    asset_class          = "equities_options"
    typical_holding_days = 75
    target_sharpe        = 0.4    # uncapped insurance, lower Sharpe than the spread variant

    def __init__(
        self,
        long_otm_pct:           float = 0.15,    # 15% OTM long put (per guide)
        dte_target:             int   = 75,      # 60–90 DTE bucket midpoint
        roll_at_dte:            int   = 30,      # roll when DTE drops to here
        roll_at_long_delta:     float = -0.30,   # roll if long leg is deep ITM
        vix_max_at_entry:       float = 35.0,    # skip if VIX dislocated
        annual_cost_cap_pct:    float = 0.015,   # 1.5% of starting capital / year (loose)
        position_size_pct:      float = 0.005,   # max debit per purchase = 0.5% capital
        profit_take_pct:        float = 1.00,    # close at 100% gain on debit
        purchase_cadence_days:  int   = 30,      # monthly buy (per guide)
        slippage_per_leg:       float = 0.05,    # $/share per leg slippage
        commission_per_leg:     float = 0.65,    # $/contract per leg
        max_concurrent:         int   = 3,       # allow staggered monthly rolls
        put_iv_skew_mult:       float = 1.20,    # IV multiplier for OTM long put
    ):
        if not (0.0 < long_otm_pct < 1.0):
            raise ValueError(
                f"long_otm_pct must be in (0, 1); got {long_otm_pct}"
            )
        if dte_target <= roll_at_dte:
            raise ValueError(
                f"dte_target ({dte_target}) must exceed roll_at_dte ({roll_at_dte})"
            )
        self.long_otm_pct          = float(long_otm_pct)
        self.dte_target            = int(dte_target)
        self.roll_at_dte           = int(roll_at_dte)
        self.roll_at_long_delta    = float(roll_at_long_delta)
        self.vix_max_at_entry      = float(vix_max_at_entry)
        self.annual_cost_cap_pct   = float(annual_cost_cap_pct)
        self.position_size_pct     = float(position_size_pct)
        self.profit_take_pct       = float(profit_take_pct)
        self.purchase_cadence_days = int(purchase_cadence_days)
        self.slippage_per_leg      = float(slippage_per_leg)
        self.commission_per_leg    = float(commission_per_leg)
        self.max_concurrent        = int(max_concurrent)
        self.put_iv_skew_mult      = float(put_iv_skew_mult)

    # ── Parameter dictionaries ────────────────────────────────────────────

    def get_params(self) -> dict:
        return {
            "long_otm_pct":          self.long_otm_pct,
            "dte_target":            self.dte_target,
            "roll_at_dte":           self.roll_at_dte,
            "roll_at_long_delta":    self.roll_at_long_delta,
            "vix_max_at_entry":      self.vix_max_at_entry,
            "annual_cost_cap_pct":   self.annual_cost_cap_pct,
            "position_size_pct":     self.position_size_pct,
            "profit_take_pct":       self.profit_take_pct,
            "purchase_cadence_days": self.purchase_cadence_days,
            "slippage_per_leg":      self.slippage_per_leg,
            "commission_per_leg":    self.commission_per_leg,
            "max_concurrent":        self.max_concurrent,
            "put_iv_skew_mult":      self.put_iv_skew_mult,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "long_otm_pct",         "label": "Long put OTM%",        "type": "slider",
             "min": 0.08, "max": 0.25, "default": 0.15, "step": 0.01,
             "col": 0, "row": 0,
             "help": "Distance below spot for the long put. 15–18% is the optimal zone — "
                     "calibrated to the historical distribution of bear markets."},
            {"key": "dte_target",           "label": "Target DTE",           "type": "slider",
             "min": 45, "max": 120, "default": 75, "step": 5,
             "col": 1, "row": 0,
             "help": "Days to expiry at entry. 60–90 DTE is the sweet spot — long enough "
                     "to avoid the theta cliff, short enough to keep premium reasonable."},
            {"key": "purchase_cadence_days", "label": "Purchase cadence (days)", "type": "slider",
             "min": 20, "max": 90, "default": 30, "step": 5,
             "col": 2, "row": 0,
             "help": "How often to mechanically buy a fresh put. 30 days = monthly. The guide "
                     "recommends monthly cadence for naked-long programs."},
            {"key": "roll_at_dte",          "label": "Roll trigger DTE",     "type": "slider",
             "min": 14, "max": 45, "default": 30, "step": 1,
             "col": 0, "row": 1,
             "help": "Close & re-enter when DTE drops to here. Avoids the final-month theta cliff."},
            {"key": "annual_cost_cap_pct",  "label": "Annual cost cap (%)",  "type": "slider",
             "min": 0.005, "max": 0.030, "default": 0.015, "step": 0.001,
             "col": 1, "row": 1,
             "help": "Hard cap on total debits paid in any 365-day window, as a fraction of "
                     "starting capital. 1.0–1.5% is the empirical zone (Israelov & Nielsen 2015)."},
            {"key": "position_size_pct",    "label": "Per-purchase max debit (% capital)", "type": "slider",
             "min": 0.001, "max": 0.015, "default": 0.005, "step": 0.0005,
             "col": 2, "row": 1,
             "help": "Maximum debit allowed per single purchase, as a fraction of current capital."},
            {"key": "profit_take_pct",      "label": "Harvest at gain (× debit)", "type": "slider",
             "min": 0.50, "max": 3.00, "default": 1.00, "step": 0.25,
             "col": 0, "row": 2,
             "help": "Close & reset when the put mark exceeds debit by this multiple "
                     "(e.g. 1.0 = 100% gain). Locks in the gain and resets protection."},
            {"key": "vix_max_at_entry",     "label": "VIX gate (max at entry)", "type": "slider",
             "min": 20.0, "max": 50.0, "default": 35.0, "step": 1.0,
             "col": 1, "row": 2,
             "help": "Skip new purchases when VIX exceeds this level — buying after fear is "
                     "the worst time to enter (the 'barn door' problem)."},
            {"key": "max_concurrent",       "label": "Max concurrent puts", "type": "slider",
             "min": 1, "max": 6, "default": 3, "step": 1,
             "col": 2, "row": 2,
             "help": "Maximum overlapping put positions (allows staggered monthly rolls)."},
        ]

    # ── Live signal ───────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Live signal — emits BUY when calendar/budget gates pass, otherwise HOLD.

        Required snapshot keys:
            spot or price          : float (SPY price)
        Optional:
            vix                    : float
            days_since_last_buy    : int   (calendar trigger; default = cadence + 1)
            annual_cost_so_far_pct : float (pct of capital spent on hedge YTD)
            n_open                 : int   (concurrent open puts)
            capital                : float (live capital — for budget check)
        """
        spot = market_snapshot.get("spot")
        if spot is None:
            spot = market_snapshot.get("price")
        if spot is None or spot <= 0:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "missing/invalid spot price"})

        spot = float(spot)
        vix  = float(market_snapshot.get("vix", _DEFAULT_VIX_FALLBACK))
        days_since_last_buy = int(market_snapshot.get("days_since_last_buy",
                                                       self.purchase_cadence_days + 1))
        annual_cost_so_far_pct = float(market_snapshot.get("annual_cost_so_far_pct", 0.0))
        n_open  = int(market_snapshot.get("n_open", 0))
        capital = float(market_snapshot.get("capital",
                                              market_snapshot.get("portfolio_value", 100_000.0)))

        # ── Gate 1: VIX dislocation ──────────────────────────────────────
        if vix > self.vix_max_at_entry:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"VIX {vix:.1f} > {self.vix_max_at_entry} "
                                                    f"(skip dislocated regime)",
                                          "vix": vix})
        # ── Gate 2: cadence ───────────────────────────────────────────────
        if days_since_last_buy < self.purchase_cadence_days:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"calendar not yet due "
                                                    f"({days_since_last_buy}/{self.purchase_cadence_days} days)",
                                          "days_since_last_buy": days_since_last_buy})
        # ── Gate 3: annual cost cap ──────────────────────────────────────
        if annual_cost_so_far_pct >= self.annual_cost_cap_pct:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"annual cost cap reached "
                                                    f"({annual_cost_so_far_pct*100:.2f}% ≥ "
                                                    f"{self.annual_cost_cap_pct*100:.2f}%)"})
        # ── Gate 4: concurrency ──────────────────────────────────────────
        if n_open >= self.max_concurrent:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"max_concurrent reached "
                                                    f"({n_open}/{self.max_concurrent})"})

        # ── BUY signal — compute structure ───────────────────────────────
        long_K = round(spot * (1.0 - self.long_otm_pct), 2)

        atm_iv     = max(0.05, vix / 100.0)
        iv_long    = atm_iv * self.put_iv_skew_mult
        T          = self.dte_target / 365.0
        debit_per  = bs_price(spot, long_K, T, _RISK_FREE_RATE, iv_long, "put")
        debit_pct  = (debit_per * 100) / max(capital, 1.0)

        return SignalResult(
            strategy_name     = self.name,
            signal            = "BUY",
            confidence        = 0.5,    # mechanical purchase — confidence is constant by design
            position_size_pct = self.position_size_pct,
            metadata = {
                "long_strike":            long_K,
                "dte":                    self.dte_target,
                "debit_per_contract":     round(debit_per, 4),
                "debit_pct":              round(debit_pct, 5),
                "annual_cost_so_far_pct": round(annual_cost_so_far_pct, 5),
                "vix":                    vix,
                "iv_long":                round(iv_long, 4),
                "structure":              "naked_long_put",
            },
        )

    # ── Backtest ──────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:         pd.DataFrame,
        auxiliary_data:     dict,
        starting_capital:   float = 100_000.0,
        long_otm_pct:           Optional[float] = None,
        dte_target:             Optional[int]   = None,
        roll_at_dte:            Optional[int]   = None,
        roll_at_long_delta:     Optional[float] = None,
        vix_max_at_entry:       Optional[float] = None,
        annual_cost_cap_pct:    Optional[float] = None,
        position_size_pct:      Optional[float] = None,
        profit_take_pct:        Optional[float] = None,
        purchase_cadence_days:  Optional[int]   = None,
        max_concurrent:         Optional[int]   = None,
        **kwargs,
    ) -> BacktestResult:
        """
        Walk-forward Tail Risk Long Put simulation. No look-ahead.

        Walk forward bar-by-bar:
          1. Mark-to-market every open put using current spot, current VIX,
             current DTE — strictly current-bar data, no peeking ahead.
          2. Check exit triggers per put: harvest (profit_take), roll-DTE,
             roll-on-deep-ITM-delta, end-of-data.
          3. On each bar evaluate the calendar: if cadence is due AND VIX gate
             passes AND annual-cost-cap budget allows, open a new put sized
             to fit the residual budget.
        """

        # ── Resolve parameters ────────────────────────────────────────────
        long_otm  = self.long_otm_pct          if long_otm_pct           is None else float(long_otm_pct)
        dte_tgt   = self.dte_target            if dte_target             is None else int(dte_target)
        roll_dte  = self.roll_at_dte           if roll_at_dte            is None else int(roll_at_dte)
        roll_dlt  = self.roll_at_long_delta    if roll_at_long_delta     is None else float(roll_at_long_delta)
        vix_cap   = self.vix_max_at_entry      if vix_max_at_entry       is None else float(vix_max_at_entry)
        cost_cap  = self.annual_cost_cap_pct   if annual_cost_cap_pct    is None else float(annual_cost_cap_pct)
        pos_sz    = self.position_size_pct     if position_size_pct      is None else float(position_size_pct)
        ptake     = self.profit_take_pct       if profit_take_pct        is None else float(profit_take_pct)
        cadence   = self.purchase_cadence_days if purchase_cadence_days  is None else int(purchase_cadence_days)
        max_conc  = self.max_concurrent        if max_concurrent         is None else int(max_concurrent)

        comm = self.commission_per_leg
        slip = self.slippage_per_leg
        r    = _RISK_FREE_RATE

        if not (0.0 < long_otm < 1.0):
            raise ValueError(f"long_otm_pct must be in (0,1); got {long_otm}")
        if dte_tgt <= roll_dte:
            raise ValueError(f"dte_target ({dte_tgt}) must exceed roll_at_dte ({roll_dte})")

        # ── Validate inputs ───────────────────────────────────────────────
        if price_data is None or price_data.empty:
            raise ValueError("price_data is empty.")

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_data = price_data.sort_index()

        vix_df = auxiliary_data.get("vix") if auxiliary_data else None
        if vix_df is None or (isinstance(vix_df, pd.DataFrame) and vix_df.empty):
            raise ValueError(
                "tail_risk_long_put: VIX data is required. "
                "Pass auxiliary_data={'vix': <DataFrame>} with a 'close' column."
            )
        vix_df = vix_df.copy()
        vix_df.index = pd.to_datetime(vix_df.index)
        vix_close_col = "close" if "close" in vix_df.columns else vix_df.columns[0]
        vix = vix_df[vix_close_col].reindex(price_data.index).ffill().fillna(_DEFAULT_VIX_FALLBACK)

        close = price_data["close"]
        all_dates = list(price_data.index)
        n         = len(all_dates)

        # ── Simulation state ──────────────────────────────────────────────
        capital               = float(starting_capital)
        equity_curve          = []
        cash_curve            = []
        position_value_curve  = []
        open_trades:    list[dict] = []
        closed_trades:  list[dict] = []
        purchase_log:   list[dict] = []
        roll_log:       list[dict] = []
        harvest_log:    list[dict] = []
        regime_series:  list[dict] = []
        # rolling-window log of all debits paid: (date, dollars_spent)
        debits_paid_log: list[tuple] = []
        last_buy_idx = -10**9    # never bought yet

        for i, dt in enumerate(all_dates):
            spot     = float(close.iloc[i])
            vix_val  = float(vix.iloc[i])
            atm_iv   = max(0.05, vix_val / 100.0)
            iv_long  = atm_iv * self.put_iv_skew_mult

            # ── 1. Manage open puts (MTM + exit triggers) ─────────────────
            still_open: list[dict] = []
            unrealized = 0.0
            for trade in open_trades:
                dte_rem = trade["expiry_idx"] - i
                T_now   = max(dte_rem / 365.0, 1.0/365.0)

                cur_value = bs_price(
                    spot, trade["long_K"], T_now, r, iv_long, "put",
                )                                              # per share
                cur_value_total = cur_value * 100 * trade["contracts"]
                pnl_per         = cur_value - trade["debit_per_share"]
                long_dlt        = _put_delta(spot, trade["long_K"], T_now, r, iv_long)

                exit_reason = None
                if pnl_per >= ptake * trade["debit_per_share"] and trade["debit_per_share"] > 0:
                    exit_reason = "harvest_profit"
                elif dte_rem <= roll_dte:
                    exit_reason = "roll_at_dte"
                elif long_dlt < roll_dlt:
                    # long put gone deep ITM (delta strongly negative) → harvest
                    exit_reason = "roll_long_deep_itm"
                elif i == n - 1:
                    exit_reason = "end_of_data"

                if exit_reason is not None:
                    close_comm  = comm * trade["contracts"]               # 1 leg
                    close_slip  = slip * 100 * trade["contracts"]         # 1 leg × $/share × 100
                    proceeds    = cur_value_total - close_slip - close_comm
                    realised    = proceeds - trade["debit_total_paid"]
                    capital    += proceeds
                    closed_trades.append({
                        "entry_date":  trade["entry_date"].date(),
                        "exit_date":   dt.date(),
                        "long_K":      round(trade["long_K"], 2),
                        "debit":       round(trade["debit_per_share"], 4),
                        "contracts":   trade["contracts"],
                        "debit_total": round(trade["debit_total_paid"], 2),
                        "proceeds":    round(proceeds, 2),
                        "pnl":         round(realised, 2),
                        "exit_reason": exit_reason,
                        "dte_held":    dte_tgt - dte_rem,
                        "winner":      realised > 0,
                    })
                    if exit_reason == "harvest_profit":
                        harvest_log.append({
                            "date":      dt.date(),
                            "long_K":    round(trade["long_K"], 2),
                            "debit":     round(trade["debit_per_share"], 4),
                            "proceeds":  round(proceeds, 2),
                            "pnl":       round(realised, 2),
                        })
                    elif exit_reason in ("roll_at_dte", "roll_long_deep_itm"):
                        roll_log.append({
                            "date":      dt.date(),
                            "reason":    exit_reason,
                            "long_K":    round(trade["long_K"], 2),
                            "pnl":       round(realised, 2),
                        })
                else:
                    still_open.append(trade)
                    unrealized += cur_value_total - trade["debit_total_paid"]

            open_trades = still_open

            # ── 2. Mark-to-market equity snapshot ─────────────────────────
            mtm_equity = capital + unrealized
            equity_curve.append(mtm_equity)
            cash_curve.append(capital)
            position_value_curve.append(unrealized)

            # ── 3. Calendar / entry decision ──────────────────────────────
            # Compute rolling-365d cost spent.
            cutoff = dt - pd.Timedelta(days=365)
            _kept: list[tuple] = []
            spent_365d = 0.0
            for (d, dollars) in debits_paid_log:
                if d > cutoff:
                    _kept.append((d, dollars))
                    spent_365d += dollars
            debits_paid_log = _kept
            spent_365d_pct = spent_365d / max(starting_capital, 1.0)

            cadence_due    = (i - last_buy_idx) >= cadence
            enough_history = i >= _MIN_HISTORY_BARS
            enough_room    = (n - 1 - i) > roll_dte    # need at least roll-trigger horizon
            below_concur   = len(open_trades) < max_conc
            vix_ok         = vix_val <= vix_cap
            budget_ok      = spent_365d_pct < cost_cap
            spot_ok        = spot > 0

            regime = "ENTER" if (cadence_due and enough_history and enough_room
                                  and below_concur and vix_ok and budget_ok
                                  and spot_ok) else "SKIP"
            regime_series.append({
                "date":            dt.date(),
                "spot":            round(spot, 2),
                "vix":             round(vix_val, 2),
                "n_open":          len(open_trades),
                "spent_365d_pct":  round(spent_365d_pct, 5),
                "cadence_due":     cadence_due,
                "regime":          regime,
            })

            if regime != "ENTER":
                continue

            # ── 4. Build the put position ─────────────────────────────────
            long_K  = round(spot * (1.0 - long_otm), 2)
            T_entry = dte_tgt / 365.0
            debit_per_share = bs_price(spot, long_K, T_entry, r, iv_long, "put")
            if debit_per_share <= 0.01:
                continue

            # Apply entry slippage (bid-ask, 1 leg)
            entry_slip_per_share = slip
            debit_with_slip = debit_per_share + entry_slip_per_share
            debit_per_contract = debit_with_slip * 100

            # ── 5. Size respecting (a) per-purchase cap, (b) annual cap ──
            # (a) per-purchase cap
            max_debit_purchase = pos_sz * capital
            # (b) annual cap residual
            residual_budget = max(0.0, cost_cap * starting_capital - spent_365d)

            allowed_dollars = min(max_debit_purchase, residual_budget)
            if allowed_dollars <= debit_per_contract * 0.99:
                # Even one contract would overshoot → skip
                continue

            contracts = int(allowed_dollars // debit_per_contract)
            if contracts < 1:
                continue

            # Enforce concurrency one more time
            if len(open_trades) + 1 > max_conc:
                continue

            entry_comm     = comm * contracts                     # 1 leg
            total_outflow  = debit_per_contract * contracts + entry_comm
            if total_outflow > capital:
                continue

            capital -= total_outflow
            expiry_idx = min(i + dte_tgt, n - 1)

            trade_record = {
                "entry_date":          dt,
                "expiry_idx":          expiry_idx,
                "long_K":              long_K,
                "debit_per_share":     debit_with_slip,
                "debit_total_paid":    debit_per_contract * contracts + entry_comm,
                "contracts":           contracts,
                "vix_at_entry":        vix_val,
            }
            open_trades.append(trade_record)
            debits_paid_log.append((dt, debit_per_contract * contracts))
            last_buy_idx = i
            purchase_log.append({
                "date":              dt.date(),
                "spot":              round(spot, 2),
                "long_K":            long_K,
                "debit":             round(debit_with_slip, 4),
                "contracts":         contracts,
                "cost":              round(debit_per_contract * contracts, 2),
                "vix":               round(vix_val, 2),
                "spent_365d_after":  round(spent_365d + debit_per_contract * contracts, 2),
            })

        # ── End-of-data: liquidate handled inside loop via "end_of_data"
        # ── Build outputs ─────────────────────────────────────────────────
        idx = pd.DatetimeIndex(all_dates)
        eq_s     = pd.Series(equity_curve,         index=idx, dtype=float)
        cash_s   = pd.Series(cash_curve,           index=idx, dtype=float)
        posval_s = pd.Series(position_value_curve, index=idx, dtype=float)
        daily_returns = eq_s.pct_change().dropna()

        trades_df    = pd.DataFrame(closed_trades) if closed_trades else pd.DataFrame()
        purchase_df  = pd.DataFrame(purchase_log)  if purchase_log  else pd.DataFrame()
        roll_df      = pd.DataFrame(roll_log)      if roll_log      else pd.DataFrame()
        harvest_df   = pd.DataFrame(harvest_log)   if harvest_log   else pd.DataFrame()
        regime_df    = pd.DataFrame(regime_series) if regime_series else pd.DataFrame()

        metrics = compute_all_metrics(eq_s, trades_df if not trades_df.empty else None)

        # Compute realised annual cost
        total_debit_paid = sum(p["cost"] for p in purchase_log)
        if len(all_dates) >= 2:
            years = max(1e-9, (all_dates[-1] - all_dates[0]).days / 365.25)
        else:
            years = 1.0
        annual_cost_pct_actual = (total_debit_paid / starting_capital) / years

        if not trades_df.empty:
            n_trades = len(trades_df)
            n_winners = int(trades_df["winner"].sum())
            logger.info(
                f"TailRiskLongPut: {n_trades} closed puts, "
                f"{n_winners} winners ({100*n_winners/max(n_trades,1):.1f}%), "
                f"final equity ${eq_s.iloc[-1]:,.0f}, "
                f"annual cost actual {annual_cost_pct_actual*100:.2f}%."
            )
        else:
            logger.warning(
                "TailRiskLongPut: 0 closed puts — check VIX availability and date range."
            )

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = eq_s,
            daily_returns = daily_returns,
            trades        = trades_df,
            metrics       = metrics,
            params        = self.get_params(),
            extra = {
                "purchase_log":           purchase_df,
                "roll_log":               roll_df,
                "harvest_log":            harvest_df,
                "regime_series":          regime_df,
                "cash_curve":             cash_s,
                "position_value_curve":   posval_s,
                "annual_cost_pct_actual": round(annual_cost_pct_actual, 5),
                "total_debit_paid":       round(total_debit_paid, 2),
                "n_open_at_end":          len(open_trades),
            },
        )
