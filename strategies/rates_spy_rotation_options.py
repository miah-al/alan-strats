"""
Rates / SPY Rotation — Long Options Variant.

Same four-regime detection as rates_spy_rotation, but executes using
long calls and long puts only (no short selling, no margin required).

Uses REAL option chain data from mkt.OptionSnapshot.
If SPY or TLT option chain data is not available, backtest raises ValueError
with instructions on how to sync the data — no synthetic pricing is used.

Regime → instrument map:
  Growth    : Buy SPY call (equities up)
  Risk-On   : Buy SPY call + Buy TLT call (both rise)
  Fear      : Buy SPY put + Buy TLT call (stocks fall, bonds rally)
  Inflation : Buy SPY put + Buy TLT put (both fall as rates rise)
  Transition: No new positions; existing positions stay open
"""

import numpy as np
import pandas as pd
from datetime import date as dt_date

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult,
    StrategyStatus, StrategyType,
)
from alan_trader.risk.metrics import compute_all_metrics


# ── Regime → option direction ──────────────────────────────────────────────────
_REGIME_OPTS: dict[str, tuple[str | None, str | None]] = {
    "Growth":     ("call", None),
    "Risk-On":    ("call", "call"),
    "Fear":       ("put",  "call"),
    "Inflation":  ("put",  "put"),
    "Transition": (None,   None),
}

_KEEP_ON_TRANSITION: frozenset[str] = frozenset({"Growth", "Risk-On", "Fear", "Inflation"})


# ── Real chain lookup helpers ──────────────────────────────────────────────────

def _build_chain_idx(chain_df: pd.DataFrame) -> dict:
    """Build {(snapshot_date, expiration_date): sub-DataFrame} index."""
    idx: dict[tuple, pd.DataFrame] = {}
    if chain_df is None or chain_df.empty:
        return idx
    for (snap, exp), grp in chain_df.groupby(["snapshot_date", "expiration_date"]):
        idx[(snap, exp)] = grp.reset_index(drop=True)
    return idx


def _find_best_expiry(chain_idx: dict, snap_date: dt_date,
                      target_dte: int, tolerance: int = 21) -> dt_date | None:
    """Find expiry closest to target_dte available on snap_date."""
    available = [exp for (s, e) in chain_idx if s == snap_date]
    if not available:
        return None
    best = min(available, key=lambda e: abs((e - snap_date).days - target_dte))
    if abs((best - snap_date).days - target_dte) > tolerance:
        return None
    return best


def _lookup_mid(chain_idx: dict, snap_date: dt_date,
                expiry: dt_date, strike: float, flag: str) -> float | None:
    """Return real mid price for a specific (snap_date, expiry, strike, flag).
    Falls back to nearest available snapshot date before snap_date."""
    ct = "C" if flag == "call" else "P"

    for s in sorted(
        (s for (s, e) in chain_idx if e == expiry and s <= snap_date),
        reverse=True,
    ):
        chain_slice = chain_idx.get((s, expiry))
        if chain_slice is None or chain_slice.empty:
            continue
        ct_rows = chain_slice[chain_slice["contract_type"] == ct]
        if ct_rows.empty:
            continue
        # nearest available strike
        strikes = ct_rows["strike"].values
        nearest = float(strikes[np.argmin(np.abs(strikes - strike))])
        if abs(nearest - strike) > strike * 0.05:  # >5% away → not useful
            continue
        row = ct_rows[np.isclose(ct_rows["strike"], nearest, atol=0.01)]
        if row.empty:
            continue
        mid = row.iloc[0]["mid"]
        if pd.notna(mid) and float(mid) > 0:
            return float(mid)
        break
    return None


def _find_nearest_strike(chain_idx: dict, snap_date: dt_date,
                          expiry: dt_date, target_strike: float,
                          flag: str) -> float | None:
    """Find the nearest available strike in the chain for target_strike."""
    ct = "C" if flag == "call" else "P"
    chain_slice = chain_idx.get((snap_date, expiry))
    if chain_slice is None or chain_slice.empty:
        return None
    ct_rows = chain_slice[chain_slice["contract_type"] == ct]
    if ct_rows.empty:
        return None
    strikes = ct_rows["strike"].values
    nearest = float(strikes[np.argmin(np.abs(strikes - target_strike))])
    return nearest


class RatesSpyRotationOptionsStrategy(BaseStrategy):
    name                 = "rates_spy_rotation_options"
    display_name         = "TLT / SPY Rotation (Options)"
    strategy_type        = StrategyType.RULE_BASED
    status               = StrategyStatus.ACTIVE
    description          = (
        "Same regime detection as TLT/SPY Rotation but uses long calls/puts only. "
        "No short selling — retail-friendly. Each regime opens a defined-risk option "
        "position (premium = max loss). Uses real option chain data (mkt.OptionSnapshot)."
    )
    asset_class          = "equities_options"
    typical_holding_days = 30
    target_sharpe        = 0.7

    def __init__(
        self,
        yield_threshold: float  = 0.001,
        return_threshold: float = 0.02,
        confirm_days: int       = 3,
        option_dte: int         = 60,
        roll_dte: int           = 21,
        otm_pct: float          = 0.01,
        budget_pct: float       = 0.02,
        take_profit: float      = 1.5,
        stop_loss: float        = 0.40,
        slippage_pct: float     = 0.001,
    ):
        self.yield_threshold  = yield_threshold
        self.return_threshold = return_threshold
        self.confirm_days     = confirm_days
        self.option_dte       = option_dte
        self.roll_dte         = roll_dte
        self.otm_pct          = otm_pct
        self.budget_pct       = budget_pct
        self.take_profit      = take_profit
        self.stop_loss        = stop_loss
        self.slippage         = slippage_pct

    # ── Signal (live) ──────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        regime = market_snapshot.get("regime", "Transition")
        spy_opt, tlt_opt = _REGIME_OPTS.get(regime, (None, None))
        if spy_opt == "call":
            signal = "BUY"
        elif spy_opt == "put":
            signal = "SELL"
        else:
            signal = "HOLD"
        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=0.65,
            position_size_pct=self.budget_pct,
            metadata={"regime": regime, "spy_option": spy_opt, "tlt_option": tlt_opt},
        )

    # ── Backtest ───────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data: pd.DataFrame,
        auxiliary_data: dict,
        starting_capital: float = 100_000,
        yield_threshold: float | None = None,
        return_threshold: float | None = None,
        confirm_days: int | None = None,
        option_dte: int | None = None,
        otm_pct: float | None = None,
        budget_pct: float | None = None,
        take_profit: float | None = None,
        stop_loss: float | None = None,
        **kwargs,
    ) -> BacktestResult:

        # Convert slider units
        yield_thr = yield_threshold
        if yield_thr is not None and yield_thr >= 1:
            yield_thr /= 10_000
        else:
            yield_thr = yield_thr if yield_thr is not None else self.yield_threshold

        return_thr = return_threshold
        if return_thr is not None and return_thr >= 1:
            return_thr /= 100
        else:
            return_thr = return_thr if return_thr is not None else self.return_threshold

        conf_days = confirm_days if confirm_days is not None else self.confirm_days
        dte       = option_dte  if option_dte  is not None else self.option_dte
        otm       = (otm_pct / 100) if otm_pct is not None else self.otm_pct
        budget    = (budget_pct / 100) if (budget_pct is not None and budget_pct >= 1) else (budget_pct if budget_pct is not None else self.budget_pct)
        tp_mult   = take_profit if take_profit is not None else self.take_profit
        sl_mult   = stop_loss   if stop_loss   is not None else self.stop_loss

        # ── Validate real option chain data ──────────────────────────────────
        spy_opts_df = auxiliary_data.get("spy_options", pd.DataFrame())
        tlt_opts_df = auxiliary_data.get("tlt_options", pd.DataFrame())

        if spy_opts_df is None or (isinstance(spy_opts_df, pd.DataFrame) and spy_opts_df.empty):
            raise ValueError(
                "No SPY option chain data found.\n\n"
                "Go to Data Manager → Options Chain Coverage → select SPY → "
                "Sync Historical Options to download option chain snapshots."
            )
        if tlt_opts_df is None or (isinstance(tlt_opts_df, pd.DataFrame) and tlt_opts_df.empty):
            raise ValueError(
                "No TLT option chain data found.\n\n"
                "Go to Data Manager → Options Chain Coverage → select TLT → "
                "Sync Historical Options to download option chain snapshots."
            )

        # ── Align price data ──────────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)

        rate10y_df = auxiliary_data.get("rate10y", pd.DataFrame())
        tlt_df     = auxiliary_data.get("tlt",     pd.DataFrame())
        vix_df     = auxiliary_data.get("vix",     pd.DataFrame())

        if rate10y_df.empty:
            raise ValueError("No 10Y rate data. Sync Macro Bars in Data Manager first.")
        if tlt_df is None or (isinstance(tlt_df, pd.DataFrame) and tlt_df.empty):
            raise ValueError("No TLT price data. Go to Data Manager → Sync TLT price bars.")

        rate10y_df = rate10y_df.copy()
        rate10y_df.index = pd.to_datetime(rate10y_df.index)
        rate10y = rate10y_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False)

        tlt_df = tlt_df.copy()
        tlt_df.index = pd.to_datetime(tlt_df.index)
        tlt_close = tlt_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False)

        if not vix_df.empty:
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)
            vix = vix_df["close"].reindex(price_data.index).ffill().infer_objects(copy=False).fillna(20.0)
        else:
            vix = pd.Series(20.0, index=price_data.index)

        spy_close = price_data["close"]

        # ── Build real option chain indexes ───────────────────────────────────
        spy_chain_idx = _build_chain_idx(spy_opts_df)
        tlt_chain_idx = _build_chain_idx(tlt_opts_df)

        # ── Regime classification ─────────────────────────────────────────────
        rate_change_20d = rate10y - rate10y.shift(20)
        spy_return_20d  = spy_close.pct_change(20)

        def _classify(rc, sr) -> str:
            if np.isnan(rc) or np.isnan(sr):
                return "Transition"
            if rc > yield_thr and sr > return_thr:
                return "Growth"
            elif rc > yield_thr and sr < -return_thr:
                return "Inflation"
            elif rc < -yield_thr and sr < -return_thr:
                return "Fear"
            elif rc < -yield_thr and sr > return_thr:
                return "Risk-On"
            return "Transition"

        raw_regime = pd.Series(
            [_classify(rc, sr)
             for rc, sr in zip(rate_change_20d.values, spy_return_20d.values)],
            index=price_data.index,
        )

        confirmed = raw_regime.copy()
        streak = 1
        for i in range(1, len(raw_regime)):
            if raw_regime.iloc[i] == raw_regime.iloc[i - 1]:
                streak += 1
            else:
                streak = 1
            if streak < conf_days:
                confirmed.iloc[i] = confirmed.iloc[i - 1]
        regime_series = confirmed

        # ── Portfolio simulation ──────────────────────────────────────────────
        capital        = float(starting_capital)
        equity_list    = []
        trades_list    = []
        all_dates      = list(price_data.index)
        current_regime = "Transition"
        active_positions: list[dict] = []

        def _open_positions(snap_date: dt_date, regime: str,
                             spy_s: float, tlt_s: float, cap: float) -> list[dict]:
            spy_opt, tlt_opt = _REGIME_OPTS.get(regime, (None, None))
            crisis_boost = 1.25 if regime in ("Fear", "Inflation") else 1.0
            legs_budget  = cap * budget * crisis_boost

            legs = []
            if spy_opt:
                legs.append(("SPY", spy_opt, spy_s, spy_chain_idx))
            if tlt_opt and tlt_s is not None:
                legs.append(("TLT", tlt_opt, tlt_s, tlt_chain_idx))

            if not legs:
                return []

            per_leg_budget = legs_budget / len(legs)
            positions = []

            for asset, flag, spot, chain_idx in legs:
                # Find expiry
                expiry = _find_best_expiry(chain_idx, snap_date, dte, tolerance=21)
                if expiry is None:
                    continue  # no chain data for this date

                # Target strike
                target_strike = round(spot * (1 - otm) if flag == "put" else spot * (1 + otm))
                actual_strike = _find_nearest_strike(chain_idx, snap_date, expiry,
                                                      target_strike, flag)
                if actual_strike is None:
                    continue

                # Real mid price
                entry_mid = _lookup_mid(chain_idx, snap_date, expiry, actual_strike, flag)
                if entry_mid is None or entry_mid <= 0:
                    continue

                entry_with_slip = entry_mid * (1 + self.slippage)
                contracts = int(per_leg_budget / (entry_with_slip * 100))
                if contracts <= 0:
                    continue

                total_cost = contracts * 100 * entry_with_slip
                positions.append({
                    "asset":       asset,
                    "flag":        flag,
                    "strike":      actual_strike,
                    "expiry":      expiry,
                    "entry_mid":   entry_mid,
                    "entry_price": entry_with_slip,
                    "contracts":   contracts,
                    "total_cost":  total_cost,
                    "entry_date":  snap_date,
                    "chain_idx":   chain_idx,
                })
            return positions

        def _close_position(pos: dict, snap_date: dt_date, reason: str,
                             exit_mid: float | None) -> float:
            """Returns proceeds (not pnl). Logs trade."""
            if exit_mid is None:
                # Use intrinsic value as fallback at expiry
                exit_mid = 0.0
            proceeds = exit_mid * pos["contracts"] * 100 * (1 - self.slippage)
            pnl = proceeds - pos["total_cost"]
            trades_list.append({
                "entry_date":  pos["entry_date"],
                "exit_date":   snap_date,
                "spread_type": f"{pos['asset']} {pos['flag']} {current_regime}",
                "long_strike": pos["strike"],
                "short_strike": pos["strike"],
                "entry_cost":  round(pos["entry_mid"], 4),
                "exit_value":  round(exit_mid, 4),
                "contracts":   pos["contracts"],
                "pnl":         round(pnl, 2),
                "exit_reason": reason,
            })
            return proceeds

        for i, dt in enumerate(all_dates):
            regime    = regime_series.iloc[i]
            snap_date = dt.date()
            spy_s     = float(spy_close.iloc[i]) if not np.isnan(spy_close.iloc[i]) else None
            tlt_s     = float(tlt_close.iloc[i]) if not np.isnan(tlt_close.iloc[i]) else None

            if spy_s is None:
                equity_list.append(capital)
                continue

            # ── Value / manage existing positions ────────────────────────────
            still_active = []
            for pos in active_positions:
                chain_idx_pos = pos["chain_idx"]
                days_left = (pos["expiry"] - snap_date).days

                if days_left <= 0:
                    # Expiry — intrinsic value only
                    asset_price = spy_s if pos["asset"] == "SPY" else (tlt_s or spy_s)
                    intrinsic = max(0.0,
                        (asset_price - pos["strike"]) if pos["flag"] == "call"
                        else (pos["strike"] - asset_price))
                    capital += _close_position(pos, snap_date, "expiry", intrinsic)

                elif days_left <= self.roll_dte:
                    # Roll — close current, open new with fresh DTE
                    close_mid = _lookup_mid(chain_idx_pos, snap_date,
                                            pos["expiry"], pos["strike"], pos["flag"])
                    close_proceeds = (close_mid or 0.0) * pos["contracts"] * 100 * (1 - self.slippage)
                    pnl_partial = close_proceeds - pos["total_cost"]
                    trades_list.append({
                        "entry_date":  pos["entry_date"],
                        "exit_date":   snap_date,
                        "spread_type": f"{pos['asset']} {pos['flag']} ROLL",
                        "long_strike": pos["strike"],
                        "short_strike": pos["strike"],
                        "entry_cost":  round(pos["entry_mid"], 4),
                        "exit_value":  round(close_mid or 0, 4),
                        "contracts":   pos["contracts"],
                        "pnl":         round(pnl_partial, 2),
                        "exit_reason": "roll",
                    })
                    capital += close_proceeds  # cost already deducted at open

                    # Reopen with fresh expiry
                    asset_price = spy_s if pos["asset"] == "SPY" else (tlt_s or spy_s)
                    new_expiry = _find_best_expiry(chain_idx_pos, snap_date, dte, tolerance=21)
                    if new_expiry is not None:
                        actual_strike = _find_nearest_strike(
                            chain_idx_pos, snap_date, new_expiry, pos["strike"], pos["flag"])
                        new_mid = (_lookup_mid(chain_idx_pos, snap_date, new_expiry,
                                               actual_strike or pos["strike"], pos["flag"])
                                   if actual_strike else None)
                        if new_mid and new_mid > 0:
                            new_with_slip = new_mid * (1 + self.slippage)
                            reopen_cost = pos["contracts"] * 100 * new_with_slip
                            capital -= reopen_cost
                            pos["expiry"]      = new_expiry
                            pos["strike"]      = actual_strike or pos["strike"]
                            pos["entry_mid"]   = new_mid
                            pos["entry_price"] = new_with_slip
                            pos["total_cost"]  = reopen_cost
                            pos["entry_date"]  = snap_date
                            still_active.append(pos)
                    # if can't reopen, position just closed above

                else:
                    # Check take-profit / stop-loss using real chain price
                    current_mid = _lookup_mid(chain_idx_pos, snap_date,
                                              pos["expiry"], pos["strike"], pos["flag"])
                    if current_mid is not None:
                        hit_tp = current_mid >= pos["entry_mid"] * tp_mult
                        hit_sl = current_mid <= pos["entry_mid"] * sl_mult
                        if hit_tp or hit_sl:
                            reason = "take_profit" if hit_tp else "stop_loss"
                            capital += _close_position(pos, snap_date, reason, current_mid)
                            continue
                    still_active.append(pos)

            active_positions = still_active

            # ── Regime change ─────────────────────────────────────────────────
            if regime != current_regime:
                entering_transition = (
                    regime == "Transition" and current_regime in _KEEP_ON_TRANSITION
                )
                if not entering_transition:
                    # Close all open positions
                    for pos in active_positions:
                        chain_idx_pos = pos["chain_idx"]
                        close_mid = _lookup_mid(
                            chain_idx_pos, snap_date,
                            pos["expiry"], pos["strike"], pos["flag"]
                        )
                        capital += _close_position(
                            pos, snap_date, f"regime→{regime}", close_mid
                        )
                    active_positions = []

                current_regime = regime

                # Open new positions (not in Transition, need TLT price for TLT legs)
                if regime != "Transition" and tlt_s is not None:
                    new_positions = _open_positions(snap_date, regime, spy_s, tlt_s, capital)
                    for pos in new_positions:
                        capital -= pos["total_cost"]
                        active_positions.append(pos)

            # ── End-of-day MTM ────────────────────────────────────────────────
            mtm = 0.0
            for p in active_positions:
                mid = _lookup_mid(p["chain_idx"], snap_date, p["expiry"], p["strike"], p["flag"])
                if mid is not None:
                    mtm += mid * p["contracts"] * 100
            equity_list.append(capital + mtm)

        # ── Close remaining positions at end ──────────────────────────────────
        last_dt = all_dates[-1].date()
        for pos in active_positions:
            close_mid = _lookup_mid(
                pos["chain_idx"], last_dt, pos["expiry"], pos["strike"], pos["flag"]
            )
            capital += _close_position(pos, last_dt, "end_of_period", close_mid)
        if equity_list:
            equity_list[-1] = capital

        equity    = pd.Series(equity_list, index=price_data.index, dtype=float)
        daily_ret = equity.pct_change().dropna()
        spy_bh    = price_data["close"].pct_change().reindex(equity.index).dropna()

        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(
            columns=["entry_date", "exit_date", "spread_type", "long_strike",
                     "short_strike", "entry_cost", "exit_value",
                     "contracts", "pnl", "exit_reason"]
        )

        metrics = compute_all_metrics(
            equity_curve=equity,
            trades_df=trades_df,
            benchmark_returns=spy_bh,
        )

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
            extra={
                "regime_series": regime_series,
                "rate10y":       rate10y,
                "vix":           vix,
                "spy_prices":    spy_close,
                "tlt_prices":    tlt_close,
            },
        )

    # ── UI params ──────────────────────────────────────────────────────────────

    def get_backtest_ui_params(self) -> list:
        return [
            {
                "key": "yield_threshold", "label": "Yield threshold (bps)",
                "type": "slider", "min": 5, "max": 30, "default": 10, "step": 5,
                "col": 0, "row": 0,
                "help": "20-day yield change in bps to classify rising/falling regime",
            },
            {
                "key": "return_threshold", "label": "Return threshold (%)",
                "type": "slider", "min": 1, "max": 5, "default": 2, "step": 1,
                "col": 1, "row": 0,
                "help": "20-day SPY return % to classify bullish/bearish",
            },
            {
                "key": "confirm_days", "label": "Confirmation days",
                "type": "slider", "min": 1, "max": 10, "default": 3, "step": 1,
                "col": 2, "row": 0,
                "help": "Consecutive days in same regime before opening positions",
            },
            {
                "key": "option_dte", "label": "Option DTE",
                "type": "slider", "min": 21, "max": 90, "default": 60, "step": 7,
                "col": 0, "row": 1,
                "help": "Days to expiry when opening new options",
            },
            {
                "key": "otm_pct", "label": "OTM % (×100)",
                "type": "slider", "min": 1, "max": 8, "default": 1, "step": 1,
                "col": 1, "row": 1,
                "help": "How far out-of-the-money to buy (e.g. 3 = 3% OTM)",
            },
            {
                "key": "budget_pct", "label": "Premium budget (%)",
                "type": "slider", "min": 1, "max": 5, "default": 2, "step": 1,
                "col": 2, "row": 1,
                "help": "% of portfolio to spend on option premium per regime trade",
            },
            {
                "key": "take_profit", "label": "Take profit (×cost)",
                "type": "slider", "min": 1.2, "max": 3.0, "default": 1.5, "step": 0.1,
                "col": 0, "row": 2,
                "help": "Close when option value reaches this multiple of entry price",
            },
            {
                "key": "stop_loss", "label": "Stop loss (×cost)",
                "type": "slider", "min": 0.1, "max": 0.8, "default": 0.4, "step": 0.1,
                "col": 1, "row": 2,
                "help": "Close when option value falls to this fraction of entry price",
            },
        ]

    def get_params(self) -> dict:
        return {
            "yield_threshold":  self.yield_threshold,
            "return_threshold": self.return_threshold,
            "confirm_days":     self.confirm_days,
            "option_dte":       self.option_dte,
            "roll_dte":         self.roll_dte,
            "otm_pct":          self.otm_pct,
            "take_profit":      self.take_profit,
            "stop_loss":        self.stop_loss,
            "budget_pct":       self.budget_pct,
            "slippage_pct":     self.slippage,
        }
