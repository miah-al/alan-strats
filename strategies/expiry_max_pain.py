"""
OpEx Max Pain Pin — short-volatility iron butterfly anchored at the max-pain strike.

THESIS
------
The "max pain" strike is the spot price at expiration that minimises the aggregate
dollar payout to all option holders. When dealers are net long gamma against retail
short-dated short-call / short-put inventory (the typical regime for SPX/SPY into
monthly expiration), the gamma profile concentrates around the highest-OI strike.
Dealer delta-hedging then becomes a mechanical mean-reverter: dealers BUY underlying
when spot dips below the gamma centre and SELL when spot rises above it, dampening
volatility and pulling spot toward the high-OI strike.

The economic effect is small but persistent on monthly OpEx Fridays (third Friday).
We exploit it with a defined-risk SHORT iron butterfly centred on the max-pain
strike, sized so a wing breach is a bounded loss.

LITERATURE
----------
Stoll, H. R., & Whaley, R. E. (1990, 1991). "Stock Market Structure and Volatility."
    Review of Financial Studies. First systematic documentation of expiration-week
    pricing effects in equity index options.
Ni, S. X., Pearson, N. D., & Poteshman, A. M. (2005). "Stock price clustering on
    option expiration dates." Journal of Financial Economics 78(1): 49–87.
    Empirical evidence that prices cluster near high-OI strikes on monthly OpEx.
Hu, J. (2014). "Optionable Stocks and Mutual Fund Returns." Confirms the mechanism
    is dealer hedging rather than manipulation.

MAX-PAIN MATH
-------------
Aggregate payout to option holders if the underlying expires at price S_exp:

    payout(S_exp) = Σ_K [ call_OI(K) × max(0, S_exp − K) ]
                  + Σ_K [ put_OI(K)  × max(0, K − S_exp) ]

The max-pain strike is the value of S_exp ∈ {observed K} that minimises payout(·).
Because payouts are piecewise-linear in S_exp with breakpoints at strikes, the
minimum is always realised at some traded strike — no continuous search needed.
Use only the chain expiring on the OpEx Friday (no mixing of expiries).

EDGE FILTERS
------------
1. Distance from spot to max pain ≥ min_dist_pct (default 0.5%) — otherwise spot is
   already pinned and there is no convergence to capture.
2. Distance ≤ max_dist_pct (default 3.5%) — otherwise the move required exceeds the
   pin force.
3. Net dealer gamma must be positive (dealers vol-suppressive) — fall back to an
   OI-concentration heuristic if GEX cannot be computed.
4. VIX ≤ vix_ceiling (default 25) — high vol breaks the pin (dealers cannot hedge
   a runaway move).

STRUCTURE
---------
Short iron butterfly:
    +1 long call  at K_mp + W   (wing)
    −1 short call at K_mp        (body)
    −1 short put  at K_mp        (body)
    +1 long put   at K_mp − W   (wing)

W = wing_width_pct × spot. Max loss = W × 100 − net_credit per contract.
Position-size contracts so total max loss ≤ position_size_pct × capital.

EXIT RULES
----------
1. Hold to Friday OpEx close (let theta finish its work) — primary exit.
2. Profit target: close at +profit_target_pct of received credit.
3. Stop loss:    close at −stop_loss_mult × credit.
"""

from __future__ import annotations

import logging
import math
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
from alan_trader.backtest.engine import bs_price
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)

_RISK_FREE = 0.045


# ─────────────────────────────────────────────────────────────────────────────
# OpEx calendar helpers
# ─────────────────────────────────────────────────────────────────────────────

def third_friday(year: int, month: int) -> pd.Timestamp:
    """Date of the 3rd Friday of (year, month)."""
    first = pd.Timestamp(year=year, month=month, day=1)
    # weekday() — Monday=0, Friday=4
    offset_to_first_friday = (4 - first.weekday()) % 7
    first_friday_day = 1 + offset_to_first_friday
    return pd.Timestamp(year=year, month=month, day=first_friday_day + 14)


def is_opex_week(ts) -> bool:
    """True if the calendar week of ``ts`` contains the 3rd-Friday OpEx."""
    ts = pd.Timestamp(ts)
    tf = third_friday(ts.year, ts.month)
    monday_of_opex = tf - pd.Timedelta(days=tf.weekday())  # Monday of OpEx week
    friday_of_opex = monday_of_opex + pd.Timedelta(days=4)
    return monday_of_opex.normalize() <= ts.normalize() <= friday_of_opex.normalize()


def dist_to_opex_friday(ts) -> int:
    """Calendar days to the next 3rd-Friday OpEx (>=0). 0 means today is Friday OpEx."""
    ts = pd.Timestamp(ts).normalize()
    tf_this = third_friday(ts.year, ts.month).normalize()
    if ts <= tf_this:
        return int((tf_this - ts).days)
    # past this month's OpEx — roll to next month
    if ts.month == 12:
        nxt = third_friday(ts.year + 1, 1).normalize()
    else:
        nxt = third_friday(ts.year, ts.month + 1).normalize()
    return int((nxt - ts).days)


# ─────────────────────────────────────────────────────────────────────────────
# Max-pain math
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_chain_columns(chain: pd.DataFrame) -> dict:
    """Detect canonical column names, returning a dict of {role: col_name}."""
    pick = lambda names: next((c for c in names if c in chain.columns), None)
    cols = {
        "strike":  pick(("StrikePrice", "strike_price", "strike", "Strike")),
        "type":    pick(("OptionType",  "option_type",  "type",   "contract_type")),
        "oi":      pick(("OpenInterest","open_interest","oi")),
        "volume":  pick(("Volume",      "volume",       "vol")),
        "iv":      pick(("iv", "IV", "implied_volatility", "ImpliedVolatility")),
        "expiry":  pick(("expiry", "Expiry", "expiration_date", "ExpirationDate")),
        "dte":     pick(("dte", "DTE", "days_to_expiry")),
    }
    if cols["strike"] is None or cols["type"] is None:
        raise ValueError(
            f"expiry_max_pain: chain missing required columns 'strike' and/or "
            f"'option_type'. Columns present: {list(chain.columns)}"
        )
    return cols


def compute_max_pain(chain_df: pd.DataFrame, spot: float) -> float:
    """
    Compute the max-pain strike from a chain SNAPSHOT.

    For each candidate price P (we evaluate at every traded strike — the loss
    function is piecewise-linear with breakpoints at strikes, so the minimum
    is always at a strike), compute total payout to option holders:

        payout(P) = Σ call_OI(K) × max(0, P − K)
                  + Σ put_OI(K)  × max(0, K − P)

    Return argmin(payout). If chain has zero usable OI, return ``spot`` as a
    safe sentinel (the gating logic in ``generate_signal`` will reject this
    snapshot anyway).
    """
    if chain_df is None or chain_df.empty:
        return float(spot)

    cols = _normalize_chain_columns(chain_df)
    df = chain_df.copy()
    df[cols["strike"]] = pd.to_numeric(df[cols["strike"]], errors="coerce")
    df = df.dropna(subset=[cols["strike"]])
    df = df[df[cols["strike"]] > 0]

    # OI source: prefer open_interest, fall back to volume
    if cols["oi"] is not None:
        oi = pd.to_numeric(df[cols["oi"]], errors="coerce").fillna(0.0)
        if not (oi > 0).any() and cols["volume"] is not None:
            oi = pd.to_numeric(df[cols["volume"]], errors="coerce").fillna(0.0)
    elif cols["volume"] is not None:
        oi = pd.to_numeric(df[cols["volume"]], errors="coerce").fillna(0.0)
    else:
        return float(spot)

    if oi.sum() <= 0:
        return float(spot)

    is_call = df[cols["type"]].astype(str).str.lower().str.startswith("c").to_numpy()
    strikes = df[cols["strike"]].to_numpy(dtype=float)
    oi_arr  = oi.to_numpy(dtype=float)

    # Candidate prices: every traded strike
    candidates = np.unique(strikes)
    if candidates.size == 0:
        return float(spot)

    best_strike = float(candidates[0])
    best_payout = np.inf
    for P in candidates:
        # vectorised payouts
        call_payout = np.where(is_call, np.maximum(0.0, P - strikes) * oi_arr, 0.0).sum()
        put_payout  = np.where(~is_call, np.maximum(0.0, strikes - P) * oi_arr, 0.0).sum()
        total = float(call_payout + put_payout)
        if total < best_payout:
            best_payout = total
            best_strike = float(P)

    return best_strike


def _atm_iv_from_chain(chain: pd.DataFrame, spot: float) -> Optional[float]:
    """Return IV of the strike closest to spot, or None if unavailable."""
    cols = _normalize_chain_columns(chain)
    if cols["iv"] is None:
        return None
    tmp = chain.copy()
    tmp[cols["strike"]] = pd.to_numeric(tmp[cols["strike"]], errors="coerce")
    tmp[cols["iv"]]     = pd.to_numeric(tmp[cols["iv"]],     errors="coerce")
    tmp = tmp.dropna(subset=[cols["strike"], cols["iv"]])
    tmp = tmp[(tmp[cols["iv"]] > 0.01) & (tmp[cols["iv"]] < 3.0)]
    if tmp.empty:
        return None
    idx = (tmp[cols["strike"]] - spot).abs().idxmin()
    return float(tmp.loc[idx, cols["iv"]])


def _net_dealer_gamma_proxy(chain_df: pd.DataFrame, spot: float) -> Optional[float]:
    """
    Try to compute net dealer GEX via analytics.gex_engine. Return None on
    failure so callers can decide on a fallback.
    """
    try:
        from alan_trader.analytics.gex_engine import compute_dealer_gex
        snap = compute_dealer_gex(chain_df, float(spot))
        return float(snap.net_gex)
    except Exception as e:
        logger.debug(f"max_pain: GEX compute failed, falling back to OI heuristic: {e}")
        return None


def _oi_concentration_score(chain_df: pd.DataFrame, max_pain_k: float) -> float:
    """
    Fallback heuristic when GEX is unavailable: ratio of OI at the max-pain
    strike to median per-strike OI. Score >= 1.5 implies a real OI magnet.
    """
    cols = _normalize_chain_columns(chain_df)
    if cols["oi"] is None and cols["volume"] is None:
        return 0.0
    df = chain_df.copy()
    df[cols["strike"]] = pd.to_numeric(df[cols["strike"]], errors="coerce")
    src = cols["oi"] or cols["volume"]
    df[src] = pd.to_numeric(df[src], errors="coerce").fillna(0)
    by_k = df.groupby(cols["strike"])[src].sum()
    if by_k.empty:
        return 0.0
    med = float(by_k.median()) or 1.0
    closest = (by_k.index - max_pain_k).abs().idxmin()
    return float(by_k.loc[closest] / med)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy
# ─────────────────────────────────────────────────────────────────────────────

class ExpiryMaxPainStrategy(BaseStrategy):
    """
    Short iron butterfly anchored at the OpEx max-pain strike.

    Live-signal contract (``generate_signal``)
        market_snapshot keys:
            option_chain : DataFrame (required) — chain expiring on this OpEx Friday
            spot         : float (required)
            vix          : float (optional, default 20)
            current_date : Timestamp/str (optional, default today)

    Backtest contract
        price_data:     DataFrame indexed by date, with at least 'close'.
        auxiliary_data: dict with required key 'option_snapshots' (DataFrame of
                        chains stamped per snapshot date) and optional 'vix' df.
    """

    name                 = "expiry_max_pain"
    display_name         = "OpEx Max Pain Pin"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Defined-risk short iron butterfly anchored at the monthly-OpEx max-pain "
        "strike. Captures the well-documented dealer-hedging pin around the high-OI "
        "strike (Stoll & Whaley 1990; Ni, Pearson & Poteshman 2005). Entered Mon/Tue "
        "of OpEx week, held to Friday close. Gated on positive dealer gamma, VIX ≤ 25, "
        "and a 0.5–3.5%% spot-to-pin distance."
    )
    asset_class          = "equities_options"
    typical_holding_days = 4
    target_sharpe        = 1.3

    def __init__(
        self,
        min_dist_pct:        float = 0.005,   # spot must be ≥ this % from max pain
        max_dist_pct:        float = 0.035,   # and ≤ this %
        vix_ceiling:         float = 25.0,
        wing_width_pct:      float = 0.015,   # 1.5% wing each side of body
        entry_dte_min:       int   = 2,       # only enter when ≥ this many days to OpEx
        entry_dte_max:       int   = 5,
        profit_target_pct:   float = 0.50,    # close at +50% of received credit
        stop_loss_mult:      float = 2.0,     # stop at 2× credit loss
        position_size_pct:   float = 0.02,    # max 2% capital at risk per trade
        require_positive_gex: bool = True,
        slippage_per_leg:    float = 0.05,
        commission_per_leg:  float = 0.65,
    ):
        self.min_dist_pct        = float(min_dist_pct)
        self.max_dist_pct        = float(max_dist_pct)
        self.vix_ceiling         = float(vix_ceiling)
        self.wing_width_pct      = float(wing_width_pct)
        self.entry_dte_min       = int(entry_dte_min)
        self.entry_dte_max       = int(entry_dte_max)
        self.profit_target_pct   = float(profit_target_pct)
        self.stop_loss_mult      = float(stop_loss_mult)
        self.position_size_pct   = float(position_size_pct)
        self.require_positive_gex = bool(require_positive_gex)
        self.slippage_per_leg    = float(slippage_per_leg)
        self.commission_per_leg  = float(commission_per_leg)

    # ── Params / UI ─────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        return {
            "min_dist_pct":         self.min_dist_pct,
            "max_dist_pct":         self.max_dist_pct,
            "vix_ceiling":          self.vix_ceiling,
            "wing_width_pct":       self.wing_width_pct,
            "entry_dte_min":        self.entry_dte_min,
            "entry_dte_max":        self.entry_dte_max,
            "profit_target_pct":    self.profit_target_pct,
            "stop_loss_mult":       self.stop_loss_mult,
            "position_size_pct":    self.position_size_pct,
            "require_positive_gex": self.require_positive_gex,
            "slippage_per_leg":     self.slippage_per_leg,
            "commission_per_leg":   self.commission_per_leg,
        }

    def get_backtest_ui_params(self) -> list[dict]:
        return [
            {"key": "min_dist_pct",      "label": "Min spot–pin distance",
             "type": "slider", "default": 0.005, "min": 0.001, "max": 0.020, "step": 0.001,
             "col": 0, "row": 0,
             "help": "Spot must be at least this fraction away from max-pain strike. Below this, no convergence to capture."},
            {"key": "max_dist_pct",      "label": "Max spot–pin distance",
             "type": "slider", "default": 0.035, "min": 0.010, "max": 0.060, "step": 0.005,
             "col": 1, "row": 0,
             "help": "Spot must be no more than this fraction away. Beyond this, the move needed exceeds the pin force."},
            {"key": "vix_ceiling",       "label": "VIX ceiling",
             "type": "slider", "default": 25.0, "min": 14.0, "max": 40.0, "step": 1.0,
             "col": 2, "row": 0,
             "help": "Skip entries above this VIX — high vol breaks the pin."},
            {"key": "wing_width_pct",    "label": "Wing width (% spot)",
             "type": "slider", "default": 0.015, "min": 0.005, "max": 0.040, "step": 0.005,
             "col": 0, "row": 1,
             "help": "Each wing is this fraction of spot away from the body strike."},
            {"key": "profit_target_pct", "label": "Profit target (× credit)",
             "type": "slider", "default": 0.50, "min": 0.20, "max": 0.90, "step": 0.05,
             "col": 1, "row": 1,
             "help": "Close at +X × the received credit."},
            {"key": "stop_loss_mult",    "label": "Stop loss (× credit)",
             "type": "slider", "default": 2.0, "min": 1.0, "max": 4.0, "step": 0.5,
             "col": 2, "row": 1,
             "help": "Close on a loss of N × credit."},
            {"key": "position_size_pct", "label": "Position size (% capital)",
             "type": "slider", "default": 0.02, "min": 0.005, "max": 0.05, "step": 0.005,
             "col": 0, "row": 2,
             "help": "Total max-loss across the butterfly contracts ≤ this fraction of capital."},
            {"key": "entry_dte_max",     "label": "Max DTE at entry",
             "type": "slider", "default": 5, "min": 2, "max": 7, "step": 1,
             "col": 1, "row": 2,
             "help": "Only enter trades on bars ≤ this many days to OpEx Friday."},
        ]

    # ── Live signal ─────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        chain = market_snapshot.get("option_chain")
        spot  = market_snapshot.get("spot")
        vix   = market_snapshot.get("vix", 20.0)
        ts    = market_snapshot.get("current_date") or pd.Timestamp.today().normalize()
        ts    = pd.Timestamp(ts)

        if chain is None or (isinstance(chain, pd.DataFrame) and chain.empty) or spot is None:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "missing chain or spot"})

        if not is_opex_week(ts):
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "not in OpEx week"})

        dte = dist_to_opex_friday(ts)
        if dte < self.entry_dte_min or dte > self.entry_dte_max:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"dte {dte} outside [{self.entry_dte_min},{self.entry_dte_max}]"})

        try:
            vix_f = float(vix)
        except Exception:
            vix_f = 20.0
        if vix_f > self.vix_ceiling:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"vix {vix_f:.1f} > ceiling {self.vix_ceiling}"})

        spot_f = float(spot)
        try:
            mp = compute_max_pain(chain, spot_f)
        except ValueError as e:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"max-pain compute failed: {e}"})

        dist_pct = abs(spot_f - mp) / spot_f
        if dist_pct < self.min_dist_pct:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"spot too close to pin ({dist_pct:.4f} < {self.min_dist_pct})",
                                          "max_pain_strike": mp, "dist_pct": dist_pct})
        if dist_pct > self.max_dist_pct:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": f"spot too far from pin ({dist_pct:.4f} > {self.max_dist_pct})",
                                          "max_pain_strike": mp, "dist_pct": dist_pct})

        # Regime gate: prefer GEX, fall back to OI concentration
        regime = "unknown"
        gex_val = _net_dealer_gamma_proxy(chain, spot_f)
        if gex_val is not None:
            regime = "positive_gex" if gex_val > 0 else "negative_gex"
            if self.require_positive_gex and gex_val <= 0:
                return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                    metadata={"reason": "net dealer gamma not positive",
                                              "max_pain_strike": mp, "dist_pct": dist_pct,
                                              "regime": regime, "net_gex": gex_val})
        else:
            score = _oi_concentration_score(chain, mp)
            regime = f"oi_concentration={score:.2f}"
            if self.require_positive_gex and score < 1.5:
                return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                    metadata={"reason": "OI concentration too weak (no GEX, score < 1.5)",
                                              "max_pain_strike": mp, "dist_pct": dist_pct,
                                              "regime": regime})

        opex_friday = (third_friday(ts.year, ts.month) if ts <= third_friday(ts.year, ts.month)
                       else (third_friday(ts.year + 1, 1) if ts.month == 12
                             else third_friday(ts.year, ts.month + 1)))

        # SELL the butterfly (open the short-vol structure)
        return SignalResult(
            strategy_name     = self.name,
            signal            = "SELL",
            confidence        = float(min(1.0, dist_pct / max(self.max_dist_pct, 1e-6) + 0.4)),
            position_size_pct = self.position_size_pct,
            metadata={
                "max_pain_strike": float(mp),
                "dist_pct":        float(dist_pct),
                "opex_friday":     pd.Timestamp(opex_friday).strftime("%Y-%m-%d"),
                "regime":          regime,
                "structure":       "iron_butterfly_short",
                "dte":             int(dte),
                "vix":             float(vix_f),
            },
        )

    # ── Backtest ────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data: pd.DataFrame,
        auxiliary_data: dict,
        starting_capital: float = 100_000.0,
        ticker: str = "SPY",
        progress_callback=None,
        **kwargs,
    ) -> BacktestResult:
        opts = auxiliary_data.get("option_snapshots") if auxiliary_data else None
        if opts is None or (isinstance(opts, pd.DataFrame) and opts.empty):
            raise ValueError(
                "expiry_max_pain: option_snapshots is required but missing in "
                "auxiliary_data. Sync options data for this ticker before "
                "running the backtest."
            )

        # ── normalise inputs ────────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_data = price_data.sort_index()
        if "close" not in price_data.columns:
            raise ValueError("expiry_max_pain: price_data must have a 'close' column.")

        date_col = next((c for c in ("SnapshotDate", "snapshot_date", "date", "Date")
                         if c in opts.columns), None)
        if date_col is None:
            raise ValueError(
                "expiry_max_pain: option_snapshots must have a snapshot date column "
                "(SnapshotDate/snapshot_date/date/Date)."
            )
        opts = opts.copy()
        opts[date_col] = pd.to_datetime(opts[date_col])

        vix_df = auxiliary_data.get("vix")
        if vix_df is not None and not vix_df.empty:
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)
            if "close" in vix_df.columns:
                vix_series = vix_df["close"].reindex(price_data.index).ffill().fillna(20.0)
            else:
                vix_series = pd.Series(20.0, index=price_data.index)
        else:
            vix_series = pd.Series(20.0, index=price_data.index)

        # ── State ───────────────────────────────────────────────────────────
        capital     = float(starting_capital)
        equity_pts  = []
        trade_rows  = []
        max_pain_log = []
        regime_log   = []
        open_trade: Optional[dict] = None

        all_dates = list(price_data.index)
        n = len(all_dates)
        _slip = self.slippage_per_leg
        _comm = self.commission_per_leg
        r = _RISK_FREE

        for i, ts in enumerate(all_dates):
            spot = float(price_data.loc[ts, "close"])
            if spot <= 0:
                equity_pts.append({"date": ts, "equity": capital + self._mtm(open_trade, spot, ts)})
                continue
            vix_val = float(vix_series.loc[ts]) if ts in vix_series.index else 20.0

            # ── 1. Manage open trade ─────────────────────────────────────────
            if open_trade is not None:
                exit_now, exit_reason = False, None
                exp_ts = open_trade["expiry_ts"]

                # Time-based exit: at or after expiry Friday
                if ts.normalize() >= pd.Timestamp(exp_ts).normalize():
                    exit_now, exit_reason = True, "expiry_close"

                if not exit_now:
                    # MTM the structure to evaluate profit-target / stop-loss
                    cur_cost_ps   = self._butterfly_close_cost_per_share(spot, ts, open_trade, r)
                    pnl_per_share = open_trade["credit_per_share"] - cur_cost_ps
                    cred_ps       = open_trade["credit_per_share"]
                    if pnl_per_share >= self.profit_target_pct * cred_ps:
                        exit_now, exit_reason = True, "profit_target"
                    elif pnl_per_share <= -self.stop_loss_mult * cred_ps:
                        exit_now, exit_reason = True, "stop_loss"

                if exit_now:
                    cur_cost_ps   = self._butterfly_close_cost_per_share(spot, ts, open_trade, r)
                    pnl_per_share = open_trade["credit_per_share"] - cur_cost_ps
                    pnl_total     = pnl_per_share * 100.0 * open_trade["contracts"]
                    close_comm    = _comm * 4 * open_trade["contracts"]
                    capital += pnl_total - close_comm
                    capital += open_trade["margin"]   # release margin
                    trade_rows.append({
                        "ticker":          ticker,
                        "entry_date":      open_trade["entry_date"],
                        "exit_date":       ts,
                        "max_pain_strike": open_trade["max_pain_strike"],
                        "spot_at_entry":   open_trade["spot_at_entry"],
                        "spot_at_exit":    round(spot, 4),
                        "contracts":       open_trade["contracts"],
                        "credit":          round(open_trade["credit_total"], 2),
                        "pnl":             round(pnl_total - close_comm, 2),
                        "exit_reason":     exit_reason,
                        "winner":          (pnl_total - close_comm) > 0,
                    })
                    open_trade = None

            # ── 2. Entry ────────────────────────────────────────────────────
            if open_trade is None:
                can_enter, reason = self._entry_eligible(ts, vix_val)
                if can_enter:
                    chain_today = self._chain_for_opex(opts, ts, date_col)
                    if chain_today is not None and not chain_today.empty:
                        try:
                            trade = self._open_butterfly(
                                ts, spot, chain_today, capital, r,
                                regime_log_out=regime_log, max_pain_log_out=max_pain_log,
                            )
                        except Exception as e:
                            logger.debug(f"max_pain entry failed at {ts}: {e}")
                            trade = None
                        if trade is not None:
                            capital -= trade["cash_out"]
                            open_trade = trade
                else:
                    if reason and reason != "not_opex_week":
                        regime_log.append({"date": ts, "reason": reason})

            equity_pts.append({"date": ts, "equity": capital + self._mtm(open_trade, spot, ts)})
            if progress_callback and i % 20 == 0:
                progress_callback(i / max(1, n), f"max-pain {i}/{n}")

        # ── Close any leftover trade at end-of-data ─────────────────────────
        if open_trade is not None:
            ts = all_dates[-1]
            spot = float(price_data.loc[ts, "close"])
            cur_cost_ps   = self._butterfly_close_cost_per_share(spot, ts, open_trade, r)
            pnl_per_share = open_trade["credit_per_share"] - cur_cost_ps
            pnl_total     = pnl_per_share * 100.0 * open_trade["contracts"]
            close_comm    = _comm * 4 * open_trade["contracts"]
            capital += pnl_total - close_comm
            capital += open_trade["margin"]
            trade_rows.append({
                "ticker":          ticker,
                "entry_date":      open_trade["entry_date"],
                "exit_date":       ts,
                "max_pain_strike": open_trade["max_pain_strike"],
                "spot_at_entry":   open_trade["spot_at_entry"],
                "spot_at_exit":    round(spot, 4),
                "contracts":       open_trade["contracts"],
                "credit":          round(open_trade["credit_total"], 2),
                "pnl":             round(pnl_total - close_comm, 2),
                "exit_reason":     "end_of_data",
                "winner":          (pnl_total - close_comm) > 0,
            })
            open_trade = None

        # ── Build result ────────────────────────────────────────────────────
        if not equity_pts:
            return BacktestResult(
                strategy_name = self.name,
                equity_curve  = pd.Series(dtype=float),
                daily_returns = pd.Series(dtype=float),
                trades        = pd.DataFrame(),
                metrics       = {"error": "no equity points produced"},
                params        = self.get_params(),
                extra         = {"max_pain_log": pd.DataFrame(max_pain_log),
                                 "regime_log":   pd.DataFrame(regime_log),
                                 "ticker":       ticker},
            )

        eq_df = pd.DataFrame(equity_pts).set_index("date")["equity"].sort_index()
        eq_df = eq_df[~eq_df.index.duplicated(keep="last")]
        returns = eq_df.pct_change().dropna()
        bench = price_data["close"].pct_change().reindex(returns.index).dropna()

        trades_df = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame()
        metrics = compute_all_metrics(eq_df, trades_df if not trades_df.empty else None,
                                      bench if not bench.empty else None)

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = eq_df,
            daily_returns = returns,
            trades        = trades_df,
            metrics       = metrics,
            params        = self.get_params(),
            extra         = {
                "max_pain_log": pd.DataFrame(max_pain_log),
                "regime_log":   pd.DataFrame(regime_log),
                "ticker":       ticker,
            },
        )

    # ── Internals: entry helpers ────────────────────────────────────────────

    def _entry_eligible(self, ts: pd.Timestamp, vix_val: float) -> tuple[bool, str]:
        if not is_opex_week(ts):
            return False, "not_opex_week"
        dte = dist_to_opex_friday(ts)
        if dte < self.entry_dte_min or dte > self.entry_dte_max:
            return False, f"dte_{dte}_outside_window"
        if vix_val > self.vix_ceiling:
            return False, f"vix_{vix_val:.1f}_above_ceiling"
        return True, ""

    @staticmethod
    def _chain_for_opex(opts: pd.DataFrame, ts: pd.Timestamp, date_col: str) -> Optional[pd.DataFrame]:
        """
        Return the chain snapshot for ``ts``, restricted to options expiring on the
        next 3rd-Friday OpEx (no future leakage — we only filter by an expiry
        column that is already in the snapshot row).
        """
        same_day = opts[opts[date_col].dt.normalize() == ts.normalize()]
        if same_day.empty:
            return None
        # Identify expiry column
        exp_col = next((c for c in ("expiry", "Expiry", "expiration_date", "ExpirationDate")
                        if c in same_day.columns), None)
        if exp_col is None:
            # If no expiry column, treat the whole snapshot as the OpEx chain
            return same_day
        target = third_friday(ts.year, ts.month)
        if ts.normalize() > target.normalize():
            target = third_friday(ts.year + 1, 1) if ts.month == 12 \
                     else third_friday(ts.year, ts.month + 1)
        exp_ts = pd.to_datetime(same_day[exp_col], errors="coerce").dt.normalize()
        sub = same_day[exp_ts == target.normalize()]
        return sub if not sub.empty else same_day

    def _open_butterfly(
        self,
        ts: pd.Timestamp,
        spot: float,
        chain_today: pd.DataFrame,
        capital: float,
        r: float,
        regime_log_out: list,
        max_pain_log_out: list,
    ) -> Optional[dict]:
        try:
            mp = compute_max_pain(chain_today, spot)
        except ValueError:
            return None
        dist_pct = abs(spot - mp) / spot
        if dist_pct < self.min_dist_pct or dist_pct > self.max_dist_pct:
            regime_log_out.append({"date": ts, "reason": f"dist_pct_{dist_pct:.4f}_out_of_band"})
            max_pain_log_out.append({"date": ts, "spot": spot, "max_pain": mp,
                                     "dist_pct": dist_pct, "entered": False,
                                     "reason": "dist_band"})
            return None

        # Regime gate
        gex_val = _net_dealer_gamma_proxy(chain_today, spot)
        if gex_val is not None:
            regime = "positive_gex" if gex_val > 0 else "negative_gex"
            if self.require_positive_gex and gex_val <= 0:
                regime_log_out.append({"date": ts, "reason": "negative_gex"})
                max_pain_log_out.append({"date": ts, "spot": spot, "max_pain": mp,
                                         "dist_pct": dist_pct, "entered": False,
                                         "reason": "negative_gex", "net_gex": gex_val})
                return None
        else:
            score = _oi_concentration_score(chain_today, mp)
            regime = f"oi_concentration={score:.2f}"
            if self.require_positive_gex and score < 1.5:
                regime_log_out.append({"date": ts, "reason": f"oi_concentration_{score:.2f}_too_weak"})
                max_pain_log_out.append({"date": ts, "spot": spot, "max_pain": mp,
                                         "dist_pct": dist_pct, "entered": False,
                                         "reason": "oi_concentration_weak"})
                return None

        # ── Build butterfly ─────────────────────────────────────────────────
        # Anchor body at strike closest to max-pain (must exist in actual chain
        # for live execution, but here we use the computed mp as the anchor).
        body_k = mp
        wing   = max(self.wing_width_pct * spot, 0.5)  # avoid degenerate wing
        wing_call_k = body_k + wing
        wing_put_k  = body_k - wing

        # IV: ATM IV from chain, fallback to 0.20
        iv = _atm_iv_from_chain(chain_today, spot) or 0.20

        # OpEx Friday and DTE
        exp_target = third_friday(ts.year, ts.month)
        if ts.normalize() > exp_target.normalize():
            exp_target = third_friday(ts.year + 1, 1) if ts.month == 12 \
                         else third_friday(ts.year, ts.month + 1)
        dte_calendar = max(1, (exp_target.normalize() - ts.normalize()).days)
        T = dte_calendar / 365.0

        # Price legs (BS). Short call/put we receive premium minus slippage; long wings
        # we pay premium plus slippage.
        sc = bs_price(spot, body_k,      T, r, iv, "call") - self.slippage_per_leg
        sp = bs_price(spot, body_k,      T, r, iv, "put")  - self.slippage_per_leg
        wc = bs_price(spot, wing_call_k, T, r, iv, "call") + self.slippage_per_leg
        wp = bs_price(spot, wing_put_k,  T, r, iv, "put")  + self.slippage_per_leg

        credit_per_share = sc + sp - wc - wp
        # No-arbitrage cap: a short iron butterfly's credit cannot exceed the wing
        # width. BS-pricing each leg independently can produce credits above this
        # bound when the body strike is ITM (asymmetric chain priced with the same
        # IV). Cap the credit at (wing - 1¢) to keep max_loss strictly positive
        # and reflect the no-arb price the market would actually fill at.
        credit_cap_per_share = wing - 0.01
        if credit_per_share > credit_cap_per_share:
            credit_per_share = credit_cap_per_share
        if credit_per_share <= 0.05:
            max_pain_log_out.append({"date": ts, "spot": spot, "max_pain": mp,
                                     "dist_pct": dist_pct, "entered": False,
                                     "reason": "credit_too_thin"})
            return None

        # Defined max loss: wing − credit (per share × 100 = per contract)
        wing_width = wing  # symmetric
        max_loss_per_contract = max(1.0, (wing_width - credit_per_share) * 100)

        # Sizing: max-loss × contracts ≤ position_size_pct × capital
        risk_budget = max(1.0, self.position_size_pct * capital)
        contracts = max(0, int(risk_budget // max_loss_per_contract))
        if contracts <= 0:
            max_pain_log_out.append({"date": ts, "spot": spot, "max_pain": mp,
                                     "dist_pct": dist_pct, "entered": False,
                                     "reason": "size_zero"})
            return None

        margin       = max_loss_per_contract * contracts
        credit_total = credit_per_share * 100 * contracts
        open_comm    = self.commission_per_leg * 4 * contracts

        regime_log_out.append({"date": ts, "reason": f"entered_{regime}"})
        max_pain_log_out.append({"date": ts, "spot": spot, "max_pain": mp,
                                 "dist_pct": dist_pct, "entered": True,
                                 "regime": regime, "contracts": contracts,
                                 "credit_total": credit_total,
                                 "max_loss_total": margin,
                                 "expiry": pd.Timestamp(exp_target)})

        return {
            "type":            "iron_butterfly_short",
            "entry_date":      ts,
            "expiry_ts":       pd.Timestamp(exp_target),
            "entry_dte":       dte_calendar,
            "entry_iv":        float(iv),
            "max_pain_strike": float(mp),
            "spot_at_entry":   float(spot),
            "body_k":          float(body_k),
            "wing_call_k":     float(wing_call_k),
            "wing_put_k":      float(wing_put_k),
            "wing_width":      float(wing),
            "credit_per_share": float(credit_per_share),
            "credit_total":     float(credit_total),
            "contracts":       int(contracts),
            "margin":          float(margin),
            "regime":          regime,
            # Cash flow at open: post margin, receive credit, pay commission
            "cash_out":        float(margin - credit_total + open_comm),
        }

    # ── Internals: MTM / close cost ─────────────────────────────────────────

    def _butterfly_close_cost_per_share(
        self, spot: float, ts: pd.Timestamp, trade: dict, r: float,
    ) -> float:
        """Cost-to-close per SHARE (multiply by 100 for dollars per contract)."""
        days_held = max(0, (ts.normalize() - pd.Timestamp(trade["entry_date"]).normalize()).days)
        dte_rem   = max(0, trade["entry_dte"] - days_held)
        T = max(dte_rem, 0) / 365.0
        iv = trade["entry_iv"]

        sc = bs_price(spot, trade["body_k"],      T, r, iv, "call") + self.slippage_per_leg
        sp = bs_price(spot, trade["body_k"],      T, r, iv, "put")  + self.slippage_per_leg
        wc = bs_price(spot, trade["wing_call_k"], T, r, iv, "call") - self.slippage_per_leg
        wp = bs_price(spot, trade["wing_put_k"],  T, r, iv, "put")  - self.slippage_per_leg
        # To close: BUY back body, SELL wings → net cost = (sc + sp) − (wc + wp)
        cost_per_share = (sc + sp) - (wc + wp)
        # Bound cost-to-close by the no-arb max-loss frontier: cost cannot exceed
        # wing_width (otherwise BS-priced legs would imply an arbitrage opportunity
        # against the actual structure's payoff at expiration).
        cap_per_share = trade["wing_width"]
        return float(min(max(0.0, cost_per_share), cap_per_share))

    def _mtm(self, trade: Optional[dict], spot: float, ts: pd.Timestamp) -> float:
        """Equity attributable to an open trade (margin posted + unrealised P&L)."""
        if trade is None:
            return 0.0
        cur_cost_ps = self._butterfly_close_cost_per_share(spot, ts, trade, _RISK_FREE)
        pnl_per_share = trade["credit_per_share"] - cur_cost_ps
        unreal_dollars = pnl_per_share * 100.0 * trade["contracts"]
        return float(trade["margin"] + unreal_dollars)
