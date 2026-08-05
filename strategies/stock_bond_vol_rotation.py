"""
Stock-Bond Vol Rotation  (stock_bond_vol_rotation)  — SPY ⇄ TLT.

THESIS
------
Two ideas combined:

  1.  Variance-risk premium exists on both SPY and TLT, but its richness rotates.
      Sell defined-risk premium on whichever asset currently offers the richer
      *forecast* premium (real ATM IV − GBM-forecast realized vol), not on a
      fixed leg.

  2.  The stock-bond CORRELATION regime governs the risk of the short-vol book.
      When SPY and TLT are negatively correlated (the classic "bonds hedge
      stocks" regime) a vol shock in one leg is cushioned by the other, so a
      short-premium book is safer and can size up.  When the correlation flips
      POSITIVE (the 2022 inflation regime — both sell off together) there is no
      hedge; the book de-risks (smaller size, higher premium bar).

The rotation picks the asset; the correlation regime sets the size and the
premium hurdle.  Both legs are priced off their own real, skew-adjusted IV.

This is NOT rates_spy_rotation (a long-only rate-regime allocation): this trades
the *relative variance-risk premium* between equities and bonds and is gated by
their realized correlation.

DATA (all real; no proxies)
---------------------------
  price_data                  : SPY OHLCV (date-indexed)
  auxiliary_data["tlt"]       : TLT OHLCV DataFrame
  auxiliary_data["atm_iv_spy"]: real SPY ATM IV Series            ← required
  auxiliary_data["atm_iv_tlt"]: real TLT ATM IV Series            ← required
  auxiliary_data["vix"]       : VIX Series                        (risk feature/gate)
  auxiliary_data["rate10y"]   : 10y yield Series                  (feature)

Inherits all option pricing, the RV regressor, the walk-forward purge and the
data-hygiene IV gate from VRPPremiumStrategy — only the asset-selection and
correlation sizing are new here.
"""

from __future__ import annotations

import logging
import math
import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BacktestResult, SignalResult, StrategyStatus, StrategyType,
)
from alan_trader.strategies.vrp_premium import VRPPremiumStrategy
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)
_ANN = math.sqrt(252.0)


class StockBondVolRotationStrategy(VRPPremiumStrategy):
    """Sell defined-risk premium on whichever of SPY/TLT has the richer forecast
    variance-risk premium, sized by the live SPY-TLT correlation regime."""

    name                 = "stock_bond_vol_rotation"
    display_name         = "Stock-Bond Vol Rotation"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "Rotates defined-risk premium selling between SPY and TLT toward the asset "
        "with the richer forecast variance-risk premium (real ATM IV minus GBM-"
        "forecast realized vol), sized by the stock-bond correlation regime: larger "
        "when SPY/TLT are negatively correlated (each hedges the other), de-risked "
        "when the correlation flips positive (2022-style, no hedge). Both legs "
        "priced off their own real skew-adjusted IV. Edge bounded by IV data quality."
    )
    asset_class          = "multi_asset_options"
    typical_holding_days = 10
    target_sharpe        = 0.9

    def __init__(self, corr_window: int = 60, corr_neg_size_mult: float = 1.0,
                 corr_pos_size_mult: float = 0.4, **kwargs):
        super().__init__(**kwargs)
        self.corr_window        = int(corr_window)
        self.corr_neg_size_mult = float(corr_neg_size_mult)
        self.corr_pos_size_mult = float(corr_pos_size_mult)

    def get_params(self) -> dict:
        p = super().get_params()
        p.update({"corr_window": self.corr_window,
                  "corr_neg_size_mult": self.corr_neg_size_mult,
                  "corr_pos_size_mult": self.corr_pos_size_mult})
        return p

    def get_backtest_ui_params(self) -> list[dict]:
        base = super().get_backtest_ui_params()
        base.append({"key": "corr_window", "label": "Correlation window (days)",
                     "type": "int", "default": 60, "min": 20, "max": 120,
                     "col": 2, "row": 2})
        return base

    # ── helpers ───────────────────────────────────────────────────────────────

    def _corr_size_mult(self, corr: float) -> float:
        """Negative correlation (hedge intact) → full size; positive (no hedge)
        → de-risked. Linear blend across [-0.3, +0.3]."""
        if np.isnan(corr):
            return self.corr_pos_size_mult
        lo, hi = -0.3, 0.3
        t = float(np.clip((corr - lo) / (hi - lo), 0.0, 1.0))   # 0 at corr=-0.3, 1 at +0.3
        return self.corr_neg_size_mult + t * (self.corr_pos_size_mult - self.corr_neg_size_mult)

    def _prep_asset(self, px: pd.DataFrame, iv: pd.Series, vix, rate10y):
        """Feature matrix + labels for one asset (reuses VRP machinery)."""
        feat = self._build_features(px, iv, vix, rate10y)
        labels = self._build_labels(px)
        return feat, labels

    # ── backtest ──────────────────────────────────────────────────────────────

    def backtest(self, price_data, auxiliary_data, starting_capital=100_000.0,
                 ticker="SPY_TLT", progress_callback=None, **kwargs) -> BacktestResult:
        from alan_trader.strategies.vrp_premium import _as_series

        spy = price_data.sort_index()
        spy.index = pd.to_datetime(spy.index)
        tlt = auxiliary_data.get("tlt")
        iv_spy = _as_series(auxiliary_data.get("atm_iv_spy"), prefer=("atm_iv", "iv", "value"))
        iv_tlt = _as_series(auxiliary_data.get("atm_iv_tlt"), prefer=("atm_iv", "iv", "value"))
        if (tlt is None or (hasattr(tlt, "empty") and tlt.empty)
                or iv_spy is None or iv_spy.dropna().empty
                or iv_tlt is None or iv_tlt.dropna().empty):
            raise ValueError(
                "stock_bond_vol_rotation requires auxiliary_data['tlt'], "
                "['atm_iv_spy'] and ['atm_iv_tlt'] (all real). No proxy substituted.")
        tlt = tlt.sort_index(); tlt.index = pd.to_datetime(tlt.index)
        iv_spy.index = pd.to_datetime(iv_spy.index)
        iv_tlt.index = pd.to_datetime(iv_tlt.index)

        vix = _as_series(auxiliary_data.get("vix"), prefer=("close", "Close", "c"))
        if vix is not None and not vix.empty:
            vix.index = pd.to_datetime(vix.index)
        else:
            vix = None
        rate10y = _as_series(auxiliary_data.get("rate10y"),
                             prefer=("rate_10y", "Rate10Y", "close", "value"))
        if rate10y is not None and not rate10y.empty:
            rate10y.index = pd.to_datetime(rate10y.index)
        else:
            rate10y = None

        # Common trading calendar: dates where BOTH assets have price + real IV.
        common = (spy.index.intersection(tlt.index)
                  .intersection(iv_spy.dropna().index)
                  .intersection(iv_tlt.dropna().index))
        if len(common) < self.warmup_bars + 30:
            return BacktestResult(
                self.name, pd.Series(dtype=float), pd.Series(dtype=float),
                pd.DataFrame(),
                {"error": f"Only {len(common)} dates with both assets' real IV "
                          f"(need ≥ {self.warmup_bars + 30})"})
        common = common.sort_values()

        assets = {
            "SPY": dict(px=spy, **dict(zip(("feat", "labels"),
                       self._prep_asset(spy, iv_spy, vix, rate10y))), iv=iv_spy,
                       model=None),
            "TLT": dict(px=tlt, **dict(zip(("feat", "labels"),
                       self._prep_asset(tlt, iv_tlt, vix, rate10y))), iv=iv_tlt,
                       model=None),
        }

        # rolling SPY-TLT correlation on the common calendar
        spy_ret = spy["close"].reindex(common).pct_change()
        tlt_ret = tlt["close"].reindex(common).pct_change()
        corr = spy_ret.rolling(self.corr_window, min_periods=self.corr_window // 2).corr(tlt_ret)

        from sklearn.ensemble import GradientBoostingRegressor  # noqa: F401 (via _get_regressor)

        capital = float(starting_capital)
        idx = list(common)
        equity_pts = [{"date": idx[self.warmup_bars - 1], "equity": capital}]
        trade_rows: list[dict] = []
        open_trades: list[dict] = []

        def price_condor_close(ot, spot):
            days_held = max(0, (pd.Timestamp(ot["_dt_now"]) - pd.Timestamp(ot["entry_date"])).days)
            dte_rem = max(1, ot["entry_dte"] - days_held)
            T = dte_rem / 252.0
            return self._condor_close_cost(spot, ot["sc"], ot["wc"], ot["sp"], ot["wp"],
                                           ot["iv"], T) * 100 * ot["contracts"]

        for k in range(self.warmup_bars, len(idx)):
            dt = idx[k]
            since = k - self.warmup_bars

            # retrain each asset model (purged) on its own history up to dt
            if since % self.retrain_every == 0:
                for a in assets.values():
                    f = a["feat"].loc[a["feat"].index <= dt]
                    pos = f.index.get_indexer([dt], method="ffill")[0]
                    purge_end = max(0, pos - self.horizon)
                    Xtr = a["feat"][self.FEATURE_COLS].iloc[:purge_end]
                    ytr = a["labels"].reindex(Xtr.index)
                    m = ytr.notna() & Xtr.notna().all(axis=1)
                    if m.sum() >= 40:
                        a["model"] = self._get_regressor()
                        a["model"].fit(Xtr[m].values, ytr[m].values)

            # ── manage exits ───────────────────────────────────────────────────
            still = []
            for ot in open_trades:
                a = assets[ot["asset"]]
                if dt not in a["px"].index:
                    still.append(ot); continue
                spot = float(a["px"].loc[dt, "close"])
                ot["_dt_now"] = dt
                days_held = max(0, (pd.Timestamp(dt) - pd.Timestamp(ot["entry_date"])).days)
                dte_rem = max(0, ot["entry_dte"] - days_held)
                close_cost = price_condor_close(ot, spot)
                pnl = ot["credit_total"] - close_cost
                profit_hit = pnl >= self.profit_target_pct * ot["credit_total"]
                loss_hit = pnl <= -self.stop_loss_mult * ot["credit_total"]
                expire = dte_rem <= self.dte_exit
                if profit_hit or loss_hit or expire:
                    net = pnl - self.commission_per_leg * 4 * ot["contracts"]
                    capital += net
                    trade_rows.append({
                        "ticker": ot["asset"], "entry_date": ot["entry_date"], "exit_date": dt,
                        "trade_type": "iron_condor", "asset": ot["asset"],
                        "entry_dte": ot["entry_dte"], "contracts": ot["contracts"],
                        "credit": round(ot["credit_total"], 2), "vrp_hat": round(ot["vrp_hat"], 4),
                        "corr": round(ot["corr"], 3), "pnl": round(net, 2),
                        "exit_reason": "profit" if profit_hit else ("loss" if loss_hit else "expire")})
                else:
                    still.append(ot)
            open_trades = still

            # ── choose asset with richer forecast VRP & enter ──────────────────
            if len(open_trades) < self.max_concurrent:
                cand = []
                for name, a in assets.items():
                    if a["model"] is None or dt not in a["feat"].index:
                        continue
                    row = a["feat"].loc[dt]
                    X = row[self.FEATURE_COLS].values.astype(float)
                    if np.isnan(X).any():
                        continue
                    rv_hat = max(0.0, float(a["model"].predict(X.reshape(1, -1))[0]))
                    iv_now = float(row["iv_now"])
                    vrp_hat = iv_now - rv_hat
                    iv_med = float(row["iv_med20"]) if not np.isnan(row.get("iv_med20", np.nan)) else iv_now
                    iv_sane = (iv_now < self.iv_abs_cap) and (iv_med <= 0 or iv_now <= self.iv_spike_mult * iv_med)
                    vix_now = float(row["vix_level"]) if not np.isnan(row["vix_level"]) else 0.0
                    vix_ok = (vix_now == 0.0) or (vix_now <= self.vix_max)
                    if vrp_hat >= self.vrp_min and iv_now > 0.01 and iv_sane and vix_ok:
                        cand.append((vrp_hat, name, a, iv_now))
                if cand:
                    cand.sort(reverse=True)  # richest forecast premium first
                    vrp_hat, name, a, iv_now = cand[0]
                    spot = float(a["px"].loc[dt, "close"])
                    c_now = float(corr.loc[dt]) if dt in corr.index else np.nan
                    size_mult = self._corr_size_mult(c_now)
                    T = self.dte_entry / 252.0
                    sc, wc, sp, wp = self._condor_legs(spot, iv_now, T)
                    credit_ps = self._condor_credit(spot, sc, wc, sp, wp, iv_now, T)
                    if credit_ps > 0.01:
                        wing_w = max(wc - sc, sp - wp)
                        max_loss_ps = max(wing_w - credit_ps, 0.01)
                        alloc = capital * self.position_size_pct * size_mult
                        contracts = max(1, int(alloc / (max_loss_ps * 100)))
                        entry_comm = self.commission_per_leg * 4 * contracts
                        credit_total = credit_ps * 100 * contracts - entry_comm
                        if credit_total > 0:
                            capital += credit_total
                            open_trades.append({
                                "asset": name, "entry_date": dt, "entry_dte": self.dte_entry,
                                "sc": sc, "wc": wc, "sp": sp, "wp": wp, "iv": iv_now,
                                "contracts": contracts, "credit_total": credit_total,
                                "vrp_hat": vrp_hat, "corr": c_now if not np.isnan(c_now) else 0.0,
                                "_dt_now": dt})

            # MTM
            mtm = 0.0
            for ot in open_trades:
                a = assets[ot["asset"]]
                if dt in a["px"].index:
                    ot["_dt_now"] = dt
                    mtm += ot["credit_total"] - price_condor_close(ot, float(a["px"].loc[dt, "close"]))
            equity_pts.append({"date": dt, "equity": capital + mtm})

        # close survivors
        last = idx[-1]
        for ot in open_trades:
            a = assets[ot["asset"]]
            spot = float(a["px"].loc[last, "close"]) if last in a["px"].index else float(a["px"]["close"].iloc[-1])
            ot["_dt_now"] = last
            net = ot["credit_total"] - price_condor_close(ot, spot) - self.commission_per_leg * 4 * ot["contracts"]
            capital += net
            trade_rows.append({
                "ticker": ot["asset"], "entry_date": ot["entry_date"], "exit_date": last,
                "trade_type": "iron_condor", "asset": ot["asset"], "entry_dte": ot["entry_dte"],
                "contracts": ot["contracts"], "credit": round(ot["credit_total"], 2),
                "vrp_hat": round(ot["vrp_hat"], 4), "corr": round(ot["corr"], 3),
                "pnl": round(net, 2), "exit_reason": "end_of_data"})

        eq = pd.DataFrame(equity_pts).set_index("date")["equity"].sort_index()
        eq = eq[~eq.index.duplicated(keep="last")]
        returns = eq.pct_change().dropna()
        bench = spy["close"].pct_change().reindex(returns.index).dropna()
        trades_df = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame(
            columns=["ticker", "entry_date", "exit_date", "pnl", "contracts", "credit", "exit_reason"])
        metrics = compute_all_metrics(eq, trades_df if not trades_df.empty else None, bench)
        split = {}
        if not trades_df.empty:
            split = trades_df.groupby("asset")["pnl"].agg(["count", "sum"]).to_dict("index")
        self._model_meta = {"ticker": ticker, "n_trades": len(trade_rows), "by_asset": split}
        return BacktestResult(
            strategy_name=self.name, equity_curve=eq, daily_returns=returns,
            trades=trades_df, metrics=metrics, params=self.get_params(),
            extra={"model_meta": self._model_meta})

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        # Live signal delegates to the VRP logic on whichever asset's features are
        # supplied; full rotation is a backtest/portfolio-level concern.
        return super().generate_signal(market_snapshot)
