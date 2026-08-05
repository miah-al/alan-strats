"""
Variance-Risk-Premium Premium Harvester  (vrp_premium)  — SPY & TLT.

THESIS
------
Implied volatility systematically exceeds the volatility that subsequently
realizes (the *variance risk premium*, VRP).  Selling options harvests that
premium — but the premium is small and the left tail (a vol explosion while
you are short) is what destroys short-vol books.  The edge therefore is NOT
"sell premium"; everyone knows IV > RV.  The edge is:

  1.  Forecasting realized vol better than the naive "RV = trailing RV", which
      sharpens the VRP estimate (sell only when the premium is genuinely rich
      relative to what vol is *about* to do), and
  2.  Standing aside when the model expects realized vol to overrun implied.

A gradient-boosting REGRESSOR predicts forward H-day realized vol from price /
IV / macro features.  The traded signal is the *explicit* premium

      VRP_hat  =  ATM_IV_now  −  forecast_RV_H

When VRP_hat is rich enough and risk gates pass, the strategy sells a
defined-risk iron condor at the tenor the real IV surface covers (short-dated,
~7-21 DTE here), priced with the equity-index skew.

This differs from iron_condor_ai (a price-*excursion classifier*): vrp_premium
forecasts vol and trades the IV−RV spread directly, and it prices off the REAL
reconstructed ATM IV supplied in auxiliary_data["atm_iv"] — not a VIX proxy.

DATA (all real; no proxies)
---------------------------
  price_data                : underlying OHLCV (SPY or TLT), date-indexed
  auxiliary_data["atm_iv"]  : real daily ATM implied vol Series (decimal)  ← required
  auxiliary_data["vix"]     : VIX close Series                  (risk gate, optional)
  auxiliary_data["news_sentiment"] : daily mean sentiment Series (gate, optional)
  auxiliary_data["rate10y"] : 10y yield Series                  (feature, optional)

Walk-forward: WARMUP bars, retrain every RETRAIN_EVERY bars, labels purged H
bars back so a training row never sees its own forward realized-vol window.
"""

from __future__ import annotations

import logging
import math
import pickle
from pathlib import Path
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
from alan_trader.risk.metrics import compute_all_metrics
from alan_trader.backtest.engine import (
    bs_price_skew,
    DEFAULT_SLIPPAGE_PER_LEG,
    DEFAULT_COMMISSION_PER_LEG,
)

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).parent.parent / "saved_models"
_MODEL_DIR.mkdir(exist_ok=True)

_RISK_FREE = 0.045
_ANN = math.sqrt(252.0)


def _ann_realized_vol(log_ret: pd.Series) -> float:
    """Annualised realised vol of a window of log returns."""
    if len(log_ret) < 2:
        return float("nan")
    return float(log_ret.std(ddof=0) * _ANN)


def _as_series(x, prefer=("close", "Close", "rate_10y", "c", "value")):
    """Coerce a Series / single-column DataFrame / mapping into a Series, picking
    a preferred column when several exist (the app passes VIX as a 'close'-column
    DataFrame and rates as a 'rate_10y'-column DataFrame). None if nothing usable."""
    if x is None:
        return None
    if isinstance(x, pd.Series):
        return x
    if isinstance(x, pd.DataFrame):
        if x.empty:
            return None
        for col in prefer:
            if col in x.columns:
                return x[col]
        num = x.select_dtypes("number")
        return num.iloc[:, 0] if num.shape[1] else None
    try:
        return pd.Series(x)
    except Exception:
        return None


class VRPPremiumStrategy(BaseStrategy):
    """
    Sell defined-risk iron condors when the forecast variance-risk premium
    (real ATM IV − GBM-forecast realized vol) is rich and risk gates pass.
    Works on any liquid underlying with a real IV series; tuned for SPY & TLT.
    """

    name                 = "vrp_premium"
    display_name         = "VRP Premium Harvester"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "Gradient-boosting regressor forecasts forward realized vol; trades the "
        "explicit variance-risk premium (real ATM IV minus forecast RV). Sells a "
        "defined-risk iron condor when the premium is rich and risk gates pass "
        "(VIX not spiking, sentiment not crashing). Prices off the real skew-"
        "adjusted IV surface. SPY & TLT."
    )
    asset_class          = "equities_options"
    typical_holding_days = 10
    target_sharpe        = 0.9

    # Features fed to the RV regressor (all known at decision time, no look-ahead)
    FEATURE_COLS = [
        "rv_5", "rv_10", "rv_20",
        "iv_now", "vrp_now", "iv_5d_chg",
        "ret_5", "ret_20", "downside_5",
        "atr_pct", "dist_ma20",
        "vix_level", "vix_5d_chg",
        "rate10y_5d_chg",
    ]

    def __init__(
        self,
        horizon:            int   = 10,     # forward RV window = condor tenor (trading days)
        vrp_min:            float = 0.02,   # require ≥2 vol-pts forecast premium to enter
        delta_short:        float = 0.16,   # short-leg delta (≈1σ wings)
        wing_width_pct:     float = 0.05,   # long wing this far beyond short strike
        profit_target_pct:  float = 0.50,   # close at 50% of credit captured
        stop_loss_mult:     float = 2.0,    # stop at 2× credit
        dte_entry:          int   = 10,
        dte_exit:           int   = 2,      # force-close at this DTE
        position_size_pct:  float = 2.0,    # % of capital risked (max loss) per trade
        vix_max:            float = 40.0,   # hard gate: no new shorts above this VIX
        sentiment_floor:    float = -0.55,  # hard gate: skip if daily sentiment below
        iv_spike_mult:      float = 2.5,    # data-hygiene: skip if iv_now > mult × trailing median IV
        iv_abs_cap:         float = 1.00,   # data-hygiene: skip absurd IV prints (>100% vol)
        max_concurrent:     int   = 3,
        # GBM regressor hyper-params
        n_estimators:       int   = 200,
        max_depth:          int   = 3,
        learning_rate:      float = 0.03,
        warmup_bars:        int   = 150,
        retrain_every:      int   = 20,
        slippage_per_leg:   float = DEFAULT_SLIPPAGE_PER_LEG,
        commission_per_leg: float = DEFAULT_COMMISSION_PER_LEG,
        skew_slope:         float = 0.15,
    ):
        self.horizon            = int(horizon)
        self.vrp_min            = float(vrp_min)
        self.delta_short        = float(delta_short)
        self.wing_width_pct     = float(wing_width_pct)
        self.profit_target_pct  = float(profit_target_pct)
        self.stop_loss_mult     = float(stop_loss_mult)
        self.dte_entry          = int(dte_entry)
        self.dte_exit           = int(dte_exit)
        self.position_size_pct  = float(position_size_pct) / 100.0
        self.vix_max            = float(vix_max)
        self.sentiment_floor    = float(sentiment_floor)
        self.iv_spike_mult      = float(iv_spike_mult)
        self.iv_abs_cap         = float(iv_abs_cap)
        self.max_concurrent     = int(max_concurrent)
        self.n_estimators       = int(n_estimators)
        self.max_depth          = int(max_depth)
        self.learning_rate      = float(learning_rate)
        self.warmup_bars        = int(warmup_bars)
        self.retrain_every      = int(retrain_every)
        self.slippage_per_leg   = float(slippage_per_leg)
        self.commission_per_leg = float(commission_per_leg)
        self.skew_slope         = float(skew_slope)
        self._model             = None
        self._model_meta: dict  = {}

    # ── public interface ──────────────────────────────────────────────────────

    def is_trainable(self) -> bool:
        return True

    def get_params(self) -> dict:
        return {
            "horizon":           self.horizon,
            "vrp_min":           self.vrp_min,
            "delta_short":       self.delta_short,
            "wing_width_pct":    self.wing_width_pct,
            "profit_target_pct": self.profit_target_pct,
            "stop_loss_mult":    self.stop_loss_mult,
            "dte_entry":         self.dte_entry,
            "position_size_pct": self.position_size_pct * 100,
            "vix_max":           self.vix_max,
            "n_estimators":      self.n_estimators,
            "max_depth":         self.max_depth,
        }

    def get_backtest_ui_params(self) -> list[dict]:
        return [
            {"key": "vrp_min",           "label": "Min forecast VRP (vol pts)", "type": "float", "default": 0.02, "min": 0.0,  "max": 0.10, "step": 0.005, "col": 0, "row": 0},
            {"key": "delta_short",       "label": "Short-leg delta",            "type": "float", "default": 0.16, "min": 0.08, "max": 0.30, "step": 0.01,  "col": 1, "row": 0},
            {"key": "dte_entry",         "label": "DTE at entry",               "type": "int",   "default": 10,   "min": 5,    "max": 21,   "col": 2, "row": 0},
            {"key": "profit_target_pct", "label": "Profit target (× credit)",   "type": "float", "default": 0.50, "min": 0.25, "max": 0.90, "step": 0.05,  "col": 0, "row": 1},
            {"key": "stop_loss_mult",    "label": "Stop (× credit)",            "type": "float", "default": 2.0,  "min": 1.0,  "max": 4.0,  "step": 0.5,   "col": 1, "row": 1},
            {"key": "position_size_pct", "label": "Risk per trade (%)",         "type": "int",   "default": 2,    "min": 1,    "max": 5,    "col": 2, "row": 1},
            {"key": "vix_max",           "label": "Max VIX to sell",            "type": "int",   "default": 40,   "min": 20,   "max": 60,   "col": 0, "row": 2},
            {"key": "n_estimators",      "label": "GBM trees",                  "type": "int",   "default": 200,  "min": 50,   "max": 500,  "col": 1, "row": 2},
        ]

    # ── feature / label construction ──────────────────────────────────────────

    def _build_features(
        self,
        price_data: pd.DataFrame,
        atm_iv:     pd.Series,
        vix:        Optional[pd.Series],
        rate10y:    Optional[pd.Series],
    ) -> pd.DataFrame:
        """Build the feature matrix aligned to price_data.index. Every column is
        computed from data available at (or before) each bar — no look-ahead."""
        close = price_data["close"].astype(float)
        logret = np.log(close / close.shift(1))

        rv_5  = logret.rolling(5).std(ddof=0)  * _ANN
        rv_10 = logret.rolling(10).std(ddof=0) * _ANN
        rv_20 = logret.rolling(20).std(ddof=0) * _ANN

        iv = atm_iv.reindex(close.index).ffill()
        iv_5d_chg = iv - iv.shift(5)
        vrp_now = iv - rv_20

        ret_5  = close.pct_change(5)
        ret_20 = close.pct_change(20)
        downside_5 = logret.clip(upper=0.0).rolling(5).sum()

        # ATR% (Wilder-style simple mean of true range, normalised by close)
        high, low = price_data["high"].astype(float), price_data["low"].astype(float)
        prev_c = close.shift(1)
        tr = pd.concat([(high - low), (high - prev_c).abs(), (low - prev_c).abs()], axis=1).max(axis=1)
        atr_pct = tr.rolling(14).mean() / close

        ma20 = close.rolling(20).mean()
        dist_ma20 = (close - ma20) / ma20

        # Trailing IV level for a data-hygiene gate: a reconstructed ATM-IV print
        # many times its own recent median is a bad inversion (illiquid weekly
        # priced off a stale close), not a real vol event. Trading such prints
        # manufactures a phantom premium, so entries guard iv_now against this.
        iv_med20 = iv.rolling(20, min_periods=5).median()

        if vix is not None and not vix.empty:
            vx = vix.reindex(close.index).ffill()
        else:
            vx = pd.Series(np.nan, index=close.index)
        vix_5d_chg = vx.pct_change(5)

        if rate10y is not None and not rate10y.empty:
            r10 = rate10y.reindex(close.index).ffill()
            rate10y_5d_chg = r10 - r10.shift(5)
        else:
            rate10y_5d_chg = pd.Series(0.0, index=close.index)

        feat = pd.DataFrame({
            "rv_5": rv_5, "rv_10": rv_10, "rv_20": rv_20,
            "iv_now": iv, "vrp_now": vrp_now, "iv_5d_chg": iv_5d_chg,
            "ret_5": ret_5, "ret_20": ret_20, "downside_5": downside_5,
            "atr_pct": atr_pct, "dist_ma20": dist_ma20,
            "vix_level": vx, "vix_5d_chg": vix_5d_chg,
            "rate10y_5d_chg": rate10y_5d_chg,
            "iv_med20": iv_med20,   # not a model feature — data-hygiene gate only
        }, index=close.index)
        return feat

    def _build_labels(self, price_data: pd.DataFrame) -> pd.Series:
        """Label = forward annualised realised vol over the next `horizon` days.
        The last `horizon` rows are NaN (their forward window is incomplete) and
        are purged from training so a row never trains on its own future."""
        close = price_data["close"].astype(float)
        logret = np.log(close / close.shift(1))
        n = len(close)
        out = np.full(n, np.nan)
        for i in range(n - self.horizon):
            fwd = logret.iloc[i + 1: i + 1 + self.horizon]
            out[i] = _ann_realized_vol(fwd)
        return pd.Series(out, index=close.index, name="fwd_rv")

    def _get_regressor(self):
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        return Pipeline([
            ("scale", StandardScaler()),
            ("gbm", GradientBoostingRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                learning_rate=self.learning_rate,
                subsample=0.8,
                random_state=42,
            )),
        ])

    # ── strike helpers ────────────────────────────────────────────────────────

    def _strike_for_delta(self, spot: float, T: float, iv: float,
                          target_delta: float, opt_type: str) -> float:
        """Strike whose (flat-IV) BS delta ≈ target_delta. Closed-form inverse."""
        if T <= 0 or iv <= 0:
            return spot
        from scipy.stats import norm
        # |delta| = N(d1) for calls, N(-d1)... solve d1 from target
        if opt_type == "call":
            d1 = norm.ppf(min(max(target_delta, 1e-4), 0.9999))
        else:
            d1 = -norm.ppf(min(max(target_delta, 1e-4), 0.9999))
        # d1 = (ln(S/K) + (r + iv²/2)T) / (iv√T)  →  K
        K = spot * math.exp(-(d1 * iv * math.sqrt(T) - (_RISK_FREE + 0.5 * iv * iv) * T))
        return float(K)

    def _price(self, S, K, T, iv, otype):
        return bs_price_skew(S, K, T, _RISK_FREE, iv, otype, skew_slope=self.skew_slope)

    def _condor_legs(self, spot: float, iv: float, T: float):
        """Return (sc_k, wc_k, sp_k, wp_k) strikes for the iron condor."""
        sc = self._strike_for_delta(spot, T, iv, self.delta_short, "call")
        sp = self._strike_for_delta(spot, T, iv, self.delta_short, "put")
        wc = sc * (1.0 + self.wing_width_pct)
        wp = sp * (1.0 - self.wing_width_pct)
        return sc, wc, sp, wp

    def _condor_credit(self, spot, sc, wc, sp, wp, iv, T) -> float:
        """Net credit per 1-lot (per share, ×100 later). Short legs collected,
        long wings paid; slippage worsens each leg."""
        slp = self.slippage_per_leg
        short_call = self._price(spot, sc, T, iv, "call") - slp
        short_put  = self._price(spot, sp, T, iv, "put")  - slp
        long_call  = self._price(spot, wc, T, iv, "call") + slp
        long_put   = self._price(spot, wp, T, iv, "put")  + slp
        return (short_call + short_put) - (long_call + long_put)

    def _condor_close_cost(self, spot, sc, wc, sp, wp, iv, T) -> float:
        """Cost per share to buy the condor back (buy shorts, sell wings)."""
        slp = self.slippage_per_leg
        short_call = self._price(spot, sc, T, iv, "call") + slp
        short_put  = self._price(spot, sp, T, iv, "put")  + slp
        long_call  = self._price(spot, wc, T, iv, "call") - slp
        long_put   = self._price(spot, wp, T, iv, "put")  - slp
        return (short_call + short_put) - (long_call + long_put)

    # ── save / load ───────────────────────────────────────────────────────────

    def save_model(self, ticker: str = "default") -> str:
        path = _MODEL_DIR / f"vrp_premium_{ticker.lower()}.pkl"
        with open(path, "wb") as f:
            pickle.dump({"model": self._model, "meta": self._model_meta}, f)
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _MODEL_DIR / f"vrp_premium_{ticker.lower()}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._model = data["model"]
        self._model_meta = data.get("meta", {})
        return True

    # ── live signal ───────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        feats = market_snapshot.get("features_df")
        if self._model is None or feats is None or len(feats) == 0:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "model or features unavailable"})
        row = feats.iloc[-1]
        X = np.array([[float(row.get(c, np.nan)) for c in self.FEATURE_COLS]], dtype=float)
        if np.isnan(X).any():
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "feature NaN"})
        rv_hat = max(0.0, float(self._model.predict(X)[0]))   # vol ≥ 0
        iv_now = float(row.get("iv_now", np.nan))
        vrp_hat = iv_now - rv_hat
        vix_now = float(row.get("vix_level", np.nan))
        gate_ok = (vrp_hat >= self.vrp_min and
                   (np.isnan(vix_now) or vix_now <= self.vix_max))
        signal = "SELL" if gate_ok else "HOLD"
        conf = float(np.clip(vrp_hat / max(self.vrp_min, 1e-6) - 1.0, 0.0, 1.0)) if gate_ok else 0.0
        return SignalResult(
            self.name, signal, conf,
            self.position_size_pct if signal == "SELL" else 0.0,
            metadata={"vrp_hat": round(vrp_hat, 4), "iv_now": round(iv_now, 4),
                      "rv_forecast": round(rv_hat, 4), "vix": round(vix_now, 2)},
        )

    # ── backtest ──────────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:       pd.DataFrame,
        auxiliary_data:   dict,
        starting_capital: float = 100_000.0,
        ticker:           str   = "UNKNOWN",
        progress_callback=None,
        **kwargs,
    ) -> BacktestResult:
        atm_iv = _as_series(auxiliary_data.get("atm_iv"), prefer=("atm_iv", "iv", "value"))
        if atm_iv is None or atm_iv.dropna().empty:
            raise ValueError(
                "vrp_premium: auxiliary_data['atm_iv'] (real implied-vol series) is "
                "required. No proxy is substituted."
            )
        atm_iv.index = pd.to_datetime(atm_iv.index)

        price_data = price_data.sort_index()
        price_data.index = pd.to_datetime(price_data.index)

        vix = _as_series(auxiliary_data.get("vix"), prefer=("close", "Close", "c"))
        if vix is not None and not vix.empty:
            vix.index = pd.to_datetime(vix.index)
        else:
            vix = None

        sent = _as_series(auxiliary_data.get("news_sentiment"),
                          prefer=("sentiment", "mean_sentiment", "avg_sentiment", "s", "value"))
        if sent is not None and not sent.empty:
            sent.index = pd.to_datetime(sent.index)
        else:
            sent = None

        rate10y = _as_series(auxiliary_data.get("rate10y"),
                             prefer=("rate_10y", "Rate10Y", "close", "value"))
        if rate10y is not None and not rate10y.empty:
            rate10y.index = pd.to_datetime(rate10y.index)
        else:
            rate10y = None

        # Restrict to the dates we actually have real IV for.
        iv_dates = atm_iv.dropna().index
        common = price_data.index.intersection(iv_dates)
        if len(common) < self.warmup_bars + 30:
            return BacktestResult(
                self.name, pd.Series(dtype=float), pd.Series(dtype=float),
                pd.DataFrame(),
                {"error": f"Only {len(common)} dates with real IV (need ≥ {self.warmup_bars + 30})"},
            )
        px = price_data.loc[price_data.index <= common.max()]

        feat = self._build_features(px, atm_iv, vix, rate10y)
        labels = self._build_labels(px)

        # Only trade on bars that have a real IV print and complete features.
        tradeable = feat.dropna(subset=self.FEATURE_COLS).index.intersection(common)
        feat_t = feat.loc[tradeable]
        if len(feat_t) < self.warmup_bars + 20:
            return BacktestResult(
                self.name, pd.Series(dtype=float), pd.Series(dtype=float),
                pd.DataFrame(),
                {"error": f"Only {len(feat_t)} complete feature rows (need ≥ {self.warmup_bars + 20})"},
            )

        close = px["close"].astype(float)
        sent_aligned = sent.reindex(feat_t.index).ffill() if sent is not None and not sent.empty else None

        capital = float(starting_capital)
        equity_pts = [{"date": feat_t.index[self.warmup_bars - 1], "equity": capital}]
        trade_rows: list[dict] = []
        open_trades: list[dict] = []
        idx = list(feat_t.index)

        def _mtm_open(dt, spot) -> float:
            val = 0.0
            for ot in open_trades:
                days_held = max(0, (pd.Timestamp(dt) - pd.Timestamp(ot["entry_date"])).days)
                dte_rem = max(1, ot["entry_dte"] - days_held)
                T = dte_rem / 252.0
                cost_to_close = self._condor_close_cost(
                    spot, ot["sc"], ot["wc"], ot["sp"], ot["wp"], ot["iv"], T) * 100 * ot["contracts"]
                # open trade equity contribution = credit already received − cost to close now
                val += ot["credit_total"] - cost_to_close
            return val

        for i in range(self.warmup_bars, len(idx)):
            dt = idx[i]
            spot = float(close.loc[dt])
            row = feat_t.iloc[i]
            since = i - self.warmup_bars

            # ── retrain ───────────────────────────────────────────────────────
            if since % self.retrain_every == 0:
                purge_end = max(0, i - self.horizon)
                Xtr = feat_t[self.FEATURE_COLS].iloc[:purge_end]
                ytr = labels.reindex(Xtr.index)
                mask = ytr.notna() & Xtr.notna().all(axis=1)
                if mask.sum() >= 40:
                    self._model = self._get_regressor()
                    self._model.fit(Xtr[mask].values, ytr[mask].values)

            # ── manage exits ──────────────────────────────────────────────────
            still_open = []
            for ot in open_trades:
                days_held = max(0, (pd.Timestamp(dt) - pd.Timestamp(ot["entry_date"])).days)
                dte_rem = max(0, ot["entry_dte"] - days_held)
                T = max(dte_rem, 1) / 252.0
                close_cost = self._condor_close_cost(
                    spot, ot["sc"], ot["wc"], ot["sp"], ot["wp"], ot["iv"], T) * 100 * ot["contracts"]
                pnl = ot["credit_total"] - close_cost            # before exit commission
                profit_hit = pnl >= self.profit_target_pct * ot["credit_total"]
                loss_hit = pnl <= -self.stop_loss_mult * ot["credit_total"]
                expire = dte_rem <= self.dte_exit
                if profit_hit or loss_hit or expire:
                    exit_comm = self.commission_per_leg * 4 * ot["contracts"]
                    net = pnl - exit_comm
                    capital += net
                    trade_rows.append({
                        "ticker": ticker, "entry_date": ot["entry_date"], "exit_date": dt,
                        "trade_type": "iron_condor", "entry_dte": ot["entry_dte"],
                        "contracts": ot["contracts"], "credit": round(ot["credit_total"], 2),
                        "vrp_hat": round(ot["vrp_hat"], 4), "iv": round(ot["iv"], 4),
                        "pnl": round(net, 2),
                        "exit_reason": "profit" if profit_hit else ("loss" if loss_hit else "expire"),
                    })
                else:
                    still_open.append(ot)
            open_trades = still_open

            # ── maybe enter ───────────────────────────────────────────────────
            if self._model is not None and len(open_trades) < self.max_concurrent:
                X = row[self.FEATURE_COLS].values.astype(float)
                if not np.isnan(X).any():
                    # Realized vol is non-negative; the GBM is unbounded and can
                    # extrapolate below 0, which would fabricate a huge VRP. Clip.
                    rv_hat = max(0.0, float(self._model.predict(X.reshape(1, -1))[0]))
                    iv_now = float(row["iv_now"])
                    vrp_hat = iv_now - rv_hat
                    vix_now = float(row["vix_level"]) if not np.isnan(row["vix_level"]) else 0.0
                    sent_now = float(sent_aligned.iloc[i]) if sent_aligned is not None and not np.isnan(sent_aligned.iloc[i]) else 0.0

                    vix_ok = (vix_now == 0.0) or (vix_now <= self.vix_max)
                    sent_ok = sent_now >= self.sentiment_floor
                    iv_med = float(row["iv_med20"]) if not np.isnan(row.get("iv_med20", np.nan)) else iv_now
                    iv_sane = (iv_now < self.iv_abs_cap) and (iv_med <= 0 or iv_now <= self.iv_spike_mult * iv_med)
                    if (vrp_hat >= self.vrp_min and iv_now > 0.01
                            and vix_ok and sent_ok and iv_sane):
                        T = self.dte_entry / 252.0
                        sc, wc, sp, wp = self._condor_legs(spot, iv_now, T)
                        credit_ps = self._condor_credit(spot, sc, wc, sp, wp, iv_now, T)
                        if credit_ps > 0.01:
                            # max loss per 1-lot = wider wing distance − credit (per share ×100)
                            wing_w = max(wc - sc, sp - wp)
                            max_loss_ps = max(wing_w - credit_ps, 0.01)
                            alloc = capital * self.position_size_pct
                            contracts = max(1, int(alloc / (max_loss_ps * 100)))
                            entry_comm = self.commission_per_leg * 4 * contracts
                            credit_total = credit_ps * 100 * contracts - entry_comm
                            if credit_total > 0:
                                capital += credit_total      # collect credit now
                                open_trades.append({
                                    "entry_date": dt, "entry_dte": self.dte_entry,
                                    "sc": sc, "wc": wc, "sp": sp, "wp": wp,
                                    "iv": iv_now, "contracts": contracts,
                                    "credit_total": credit_total, "vrp_hat": vrp_hat,
                                    "max_loss_ps": max_loss_ps,
                                })

            equity_pts.append({"date": dt, "equity": capital + _mtm_open(dt, spot)})

            if progress_callback and since % 40 == 0:
                progress_callback(min(0.95, since / max(1, len(idx) - self.warmup_bars)),
                                  f"VRP sim bar {since}…")

        # close survivors at last mark
        last_dt = idx[-1]
        last_spot = float(close.loc[last_dt])
        for ot in open_trades:
            days_held = max(0, (pd.Timestamp(last_dt) - pd.Timestamp(ot["entry_date"])).days)
            dte_rem = max(1, ot["entry_dte"] - days_held)
            T = dte_rem / 252.0
            close_cost = self._condor_close_cost(
                last_spot, ot["sc"], ot["wc"], ot["sp"], ot["wp"], ot["iv"], T) * 100 * ot["contracts"]
            net = ot["credit_total"] - close_cost - self.commission_per_leg * 4 * ot["contracts"]
            capital += net
            trade_rows.append({
                "ticker": ticker, "entry_date": ot["entry_date"], "exit_date": last_dt,
                "trade_type": "iron_condor", "entry_dte": ot["entry_dte"],
                "contracts": ot["contracts"], "credit": round(ot["credit_total"], 2),
                "vrp_hat": round(ot["vrp_hat"], 4), "iv": round(ot["iv"], 4),
                "pnl": round(net, 2), "exit_reason": "end_of_data",
            })

        eq = pd.DataFrame(equity_pts).set_index("date")["equity"].sort_index()
        eq = eq[~eq.index.duplicated(keep="last")]
        returns = eq.pct_change().dropna()
        bench = close.pct_change().reindex(returns.index).dropna() if len(close) >= 2 else None
        trades_df = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame(
            columns=["ticker", "entry_date", "exit_date", "pnl", "contracts", "credit", "exit_reason"])
        metrics = compute_all_metrics(eq, trades_df if not trades_df.empty else None, bench)

        self._model_meta = {"ticker": ticker, "n_trades": len(trade_rows),
                            "horizon": self.horizon}
        return BacktestResult(
            strategy_name=self.name, equity_curve=eq, daily_returns=returns,
            trades=trades_df, metrics=metrics, params=self.get_params(),
            extra={"model_meta": self._model_meta, "ticker": ticker},
        )
