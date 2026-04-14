"""
Cross-Sectional Relative Strength Credit Spread AI Strategy.

THESIS
------
When sector relative strength diverges to extremes, institutional rebalancing
(pension funds, ETF reconstitution, factor rotation) creates predictable mean-
reversion pressure. This strategy exploits extreme sector divergence by selling:
  - A bear call spread on the weakest sector ETF (betting the laggard won't
    surge further — continuation is already priced in, gravity pulls it back)
  - A bull put spread on the strongest sector ETF (betting the leader won't
    collapse — it has momentum support, short put captures elevated IV)

This is a dual-edge: (1) options premium from elevated IV in volatile sectors,
and (2) structural mean-reversion of extreme RS divergence.

The AI layer predicts whether extreme RS divergence will persist or revert,
and assigns confidence to each leg independently.

WALK-FORWARD TRAINING
---------------------
  - Warmup: 90 bars
  - Retrain every 15 bars
  - One model per direction (laggard revert, leader hold)

FEATURE SET (10 features)
--------------------------
  Sector RS:  rs_rank_10d (0-10 rank among 11 sectors), rs_zscore_60d
  Sector IV:  sector_ivr (IVR of this ETF), sector_iv_vs_spy_iv
  Correlation: sector_spy_corr_20d (higher = safer credit spread)
  SPY:        spy_adx_14 (avoid credit in trending SPY), spy_ret_5d
  VIX:        vix_level
  Calendar:   days_to_month_end

LABEL CONSTRUCTION
------------------
  For laggard (bear call): 1 if sector ETF stays below (spot + buffer) over 10 days
  For leader (bull put):   1 if sector ETF stays above (spot - buffer) over 10 days
  This is the credit spread survival condition.

SECTOR ETFs: XLK, XLE, XLF, XLV, XLI, XLY, XLP, XLU, XLRE, XLB, XLC
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
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
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)

_RISK_FREE_RATE   = 0.045
_WARMUP_BARS      = 90
_RETRAIN_EVERY    = 15
_SAVED_MODELS_DIR = Path(__file__).parent.parent / "saved_models"

SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLY", "XLP", "XLU", "XLRE", "XLB", "XLC"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _bs_price(S, K, T, r, sigma, option_type):
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(0.0, (S - K) if option_type == "call" else (K - S))
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def _spread_credit(S, short_K, long_K, T, r, iv, spread_type):
    if spread_type == "bull_put":
        return _bs_price(S, short_K, T, r, iv, "put") - _bs_price(S, long_K, T, r, iv, "put")
    return _bs_price(S, short_K, T, r, iv, "call") - _bs_price(S, long_K, T, r, iv, "call")


def _compute_adx(high, low, close, period=14):
    ph, pl, pc = high.shift(1), low.shift(1), close.shift(1)
    tr  = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    dmp = (high - ph).clip(lower=0.0).where((high - ph) > (pl - low), 0.0)
    dmm = (pl - low).clip(lower=0.0).where((pl - low) > (high - ph), 0.0)
    atr_s = tr.rolling(period, min_periods=period // 2).mean()
    dip   = 100 * dmp.rolling(period, min_periods=period // 2).mean() / atr_s.replace(0, np.nan)
    dim   = 100 * dmm.rolling(period, min_periods=period // 2).mean() / atr_s.replace(0, np.nan)
    dx    = 100 * (dip - dim).abs() / (dip + dim).replace(0, np.nan)
    return dx.rolling(period, min_periods=period // 2).mean().fillna(20.0)


def _build_sector_features(
    sector_close: pd.Series,
    spy_close:    pd.Series,
    spy_high:     pd.Series,
    spy_low:      pd.Series,
    all_sector_closes: dict,   # ticker → pd.Series
    vix:          pd.Series,
) -> pd.DataFrame:
    """Build feature matrix for a single sector ETF."""
    # 10d relative return vs all sectors
    sector_ret10 = sector_close.pct_change(10)
    all_rets10   = pd.DataFrame({t: s.pct_change(10) for t, s in all_sector_closes.items()})
    # RS rank (0-10, 10 = strongest)
    rs_rank = all_rets10.rank(axis=1, ascending=True).get(
        next(k for k, v in all_sector_closes.items() if v is sector_close),
        pd.Series(5.0, index=sector_close.index)
    )

    # RS z-score vs trailing 60d
    rs_zscore = (sector_ret10 - sector_ret10.rolling(60, min_periods=20).mean()) / \
                sector_ret10.rolling(60, min_periods=20).std().replace(0, np.nan)
    rs_zscore = rs_zscore.clip(-3, 3)

    # Sector IVR proxy (using sector realized vol vs 252d window)
    rv20       = sector_close.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)
    rv_hi252   = rv20.rolling(252, min_periods=60).max()
    rv_lo252   = rv20.rolling(252, min_periods=60).min()
    sector_ivr = ((rv20 - rv_lo252) / (rv_hi252 - rv_lo252).replace(0, np.nan)).clip(0, 1)

    # Sector IV vs SPY IV ratio
    spy_rv20       = spy_close.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)
    sector_iv_spy  = (rv20 / spy_rv20.replace(0, np.nan)).clip(0.5, 3.0)

    # Sector-SPY 20d correlation
    sector_spy_corr = sector_close.pct_change().rolling(20, min_periods=10).corr(
        spy_close.pct_change()
    ).clip(0, 1)

    # SPY ADX
    spy_adx = _compute_adx(spy_high, spy_low, spy_close)
    spy_ret5 = spy_close.pct_change(5)

    vix_ma20 = vix.rolling(20, min_periods=10).mean()
    vix_rat  = (vix / vix_ma20.replace(0, np.nan)).clip(0.5, 2.5)

    month_end = pd.Series(
        [(_d + pd.offsets.MonthEnd(0) - _d).days for _d in sector_close.index],
        index=sector_close.index, dtype=float
    )

    return pd.DataFrame({
        "rs_rank_10d":          rs_rank if isinstance(rs_rank, pd.Series) else pd.Series(5.0, index=sector_close.index),
        "rs_zscore_60d":        rs_zscore,
        "sector_ivr":           sector_ivr,
        "sector_iv_vs_spy":     sector_iv_spy,
        "sector_spy_corr_20d":  sector_spy_corr,
        "spy_adx_14":           spy_adx,
        "spy_ret_5d":           spy_ret5,
        "vix_level":            vix,
        "vix_ma_ratio":         vix_rat,
        "days_to_month_end":    month_end,
    }).ffill().bfill()


def _build_rs_labels(close: pd.Series, buffer_pct: float = 0.04,
                      hold_days: int = 10, direction: str = "laggard") -> pd.Series:
    """
    direction='laggard': credit call spread survives if close stays below spot*(1+buffer)
    direction='leader':  credit put spread survives if close stays above spot*(1-buffer)
    """
    labels = pd.Series(np.nan, index=close.index)
    for i in range(len(close) - hold_days):
        entry_px = float(close.iloc[i])
        if entry_px <= 0:
            continue
        fwd = close.iloc[i + 1: i + 1 + hold_days]
        if direction == "laggard":
            # Bear call: need to stay below entry + buffer
            labels.iloc[i] = 1.0 if fwd.max() <= entry_px * (1 + buffer_pct) else 0.0
        else:
            # Bull put: need to stay above entry - buffer
            labels.iloc[i] = 1.0 if fwd.min() >= entry_px * (1 - buffer_pct) else 0.0
    return labels


# ── Strategy class ─────────────────────────────────────────────────────────────

class RSCreditSpreadStrategy(BaseStrategy):
    """
    Cross-Sectional Relative Strength Credit Spread AI strategy.

    Each week, identifies the weakest and strongest sector ETFs by 10d RS rank.
    Sells a bear call spread on the laggard and a bull put spread on the leader.
    GBM models predict P(spread survives) independently for each leg.
    Only enters when confidence exceeds threshold AND SPY ADX < adx_max.
    Requires sector ETF OHLCV data in auxiliary_data['sectors'].
    """

    name                 = "rs_credit_spread"
    display_name         = "RS Credit Spread — AI"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "AI-powered cross-sectional RS mean-reversion. Sells bear call spread "
        "on weakest sector ETF + bull put spread on strongest. "
        "GBM predicts containment probability for each leg. Weekly rebalance."
    )
    asset_class          = "equities_options"
    typical_holding_days = 10
    target_sharpe        = 1.2

    FEATURE_COLS = [
        "rs_rank_10d", "rs_zscore_60d", "sector_ivr", "sector_iv_vs_spy",
        "sector_spy_corr_20d", "spy_adx_14", "spy_ret_5d",
        "vix_level", "vix_ma_ratio", "days_to_month_end",
    ]

    _FEATURE_DEFAULTS = {
        "rs_rank_10d":         5.0,
        "rs_zscore_60d":       0.0,
        "sector_ivr":          0.40,
        "sector_iv_vs_spy":    1.0,
        "sector_spy_corr_20d": 0.70,
        "spy_adx_14":          20.0,
        "spy_ret_5d":          0.0,
        "vix_level":           20.0,
        "vix_ma_ratio":        1.0,
        "days_to_month_end":   10.0,
    }

    def __init__(
        self,
        min_confidence:     float = 0.60,
        adx_max:            float = 30.0,   # skip if SPY is strongly trending
        min_rs_rank_spread: int   = 5,      # laggard must rank ≤ this, leader ≥ 11-this
        dte_target:         int   = 21,
        hold_days:          int   = 10,
        buffer_pct:         float = 0.04,   # short strike placed 4% beyond spot
        wing_width_pct:     float = 0.05,
        profit_target_pct:  float = 0.50,
        stop_loss_mult:     float = 2.0,
        position_size_pct:  float = 0.015,  # per leg
        vix_max:            float = 40.0,
        rebalance_days:     int   = 5,      # rebalance every N days
        n_estimators:       int   = 50,
        max_depth:          int   = 2,
        learning_rate:      float = 0.05,
    ):
        self.min_confidence    = min_confidence
        self.adx_max           = adx_max
        self.min_rs_rank_spread = min_rs_rank_spread
        self.dte_target        = dte_target
        self.hold_days         = hold_days
        self.buffer_pct        = buffer_pct
        self.wing_width_pct    = wing_width_pct
        self.profit_target_pct = profit_target_pct
        self.stop_loss_mult    = stop_loss_mult
        self.position_size_pct = position_size_pct
        self.vix_max           = vix_max
        self.rebalance_days    = rebalance_days
        self.n_estimators      = n_estimators
        self.max_depth         = max_depth
        self.learning_rate     = learning_rate
        self._model_lag        = None
        self._model_lead       = None

    def save_model(self, ticker: str = "SECTOR"):
        _SAVED_MODELS_DIR.mkdir(exist_ok=True)
        for tag, m in [("lag", self._model_lag), ("lead", self._model_lead)]:
            if m is not None:
                with open(_SAVED_MODELS_DIR / f"rs_credit_spread_{tag}.pkl", "wb") as f:
                    pickle.dump(m, f)

    def load_model(self, ticker: str = "SECTOR") -> bool:
        loaded = False
        for tag in ("lag", "lead"):
            path = _SAVED_MODELS_DIR / f"rs_credit_spread_{tag}.pkl"
            if path.exists():
                with open(path, "rb") as f:
                    m = pickle.load(f)
                if tag == "lag":
                    self._model_lag = m
                else:
                    self._model_lead = m
                loaded = True
        return loaded

    def is_trainable(self) -> bool:
        return True

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        rs_rank = float(market_snapshot.get("rs_rank_10d", 5.0))
        adx     = float(market_snapshot.get("spy_adx_14", 20.0))
        vix     = float(market_snapshot.get("vix", 20.0))

        if adx > self.adx_max or vix > self.vix_max:
            signal = "HOLD"
        elif rs_rank <= self.min_rs_rank_spread:
            signal = "SELL"  # laggard → bear call
        elif rs_rank >= (len(SECTOR_ETFS) - self.min_rs_rank_spread):
            signal = "BUY"   # leader → bull put
        else:
            signal = "HOLD"

        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=0.60 if signal != "HOLD" else 0.35,
            position_size_pct=self.position_size_pct if signal != "HOLD" else 0.0,
            metadata={"rs_rank": rs_rank, "adx": adx, "vix": vix},
        )

    def backtest(
        self,
        price_data:         pd.DataFrame,
        auxiliary_data:     dict,
        starting_capital:   float = 100_000,
        min_confidence:     float | None = None,
        adx_max:            float | None = None,
        dte_target:         int   | None = None,
        hold_days:          int   | None = None,
        buffer_pct:         float | None = None,
        wing_width_pct:     float | None = None,
        profit_target_pct:  float | None = None,
        **kwargs,
    ) -> BacktestResult:
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
        except ImportError as e:
            raise ImportError("scikit-learn required") from e

        conf_min  = min_confidence    if min_confidence    is not None else self.min_confidence
        adx_max_  = adx_max           if adx_max           is not None else self.adx_max
        dte_tgt   = dte_target        if dte_target        is not None else self.dte_target
        h_days    = hold_days         if hold_days         is not None else self.hold_days
        buf       = buffer_pct        if buffer_pct        is not None else self.buffer_pct
        wing      = wing_width_pct    if wing_width_pct    is not None else self.wing_width_pct
        pt_pct    = profit_target_pct if profit_target_pct is not None else self.profit_target_pct

        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        spy_close = price_data["close"]
        spy_high  = price_data.get("high",  spy_close)
        spy_low   = price_data.get("low",   spy_close)

        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if vix_df.empty:
            raise ValueError("No VIX data. Sync Macro Bars first.")
        vix_df.index = pd.to_datetime(vix_df.index)
        vix = vix_df["close"].reindex(spy_close.index).ffill().fillna(20.0)

        # Load sector data from auxiliary_data['sectors']
        sectors_data = auxiliary_data.get("sectors", {})
        if not sectors_data:
            # Fallback: use SPY with synthetic RS (all same → flat RS, no trades)
            logger.warning("No sector data in auxiliary_data['sectors']. Using SPY-only fallback.")
            sectors_data = {"SPY": spy_close}

        # Align all sector series to SPY index
        sector_closes = {}
        for ticker, df_or_s in sectors_data.items():
            if isinstance(df_or_s, pd.DataFrame):
                s = df_or_s["close"] if "close" in df_or_s.columns else df_or_s.iloc[:, 0]
            else:
                s = df_or_s
            s.index = pd.to_datetime(s.index)
            sector_closes[ticker] = s.reindex(spy_close.index).ffill().bfill()

        if len(sector_closes) < 3:
            # Not enough sectors for meaningful RS — run like a simple VIX strategy
            logger.warning("Fewer than 3 sector ETFs available. RS edge minimal.")

        # Build features for every sector ETF (used at inference time per trade)
        all_sector_feats: dict[str, pd.DataFrame] = {}
        for ticker, s_close in sector_closes.items():
            all_sector_feats[ticker] = _build_sector_features(
                s_close, spy_close, spy_high, spy_low, sector_closes, vix
            )

        # For training labels, combine all sectors' data (laggard and leader share the
        # same survival condition, just applied to different price series)
        main_ticker = list(sector_closes.keys())[0]
        main_close  = sector_closes[main_ticker]

        # Shared SPY-based feature set for training (ADX / VIX features are the same
        # across sectors; sector-specific RS features vary only at inference)
        feats_lag   = all_sector_feats[main_ticker]
        feats_lead  = feats_lag  # same SPY context for training; sector used at inference
        labels_lag  = _build_rs_labels(main_close, buf, h_days, "laggard")
        labels_lead = _build_rs_labels(main_close, buf, h_days, "leader")

        all_dates   = list(price_data.index)
        capital     = float(starting_capital)
        equity_list = []
        trades_list = []
        open_trades = []  # allow 2 open (one lag, one lead)
        model_lag   = None
        model_lead  = None
        last_train  = -999
        last_rebal  = -999

        def _train_model(X, y):
            valid = y.notna() & X.notna().all(axis=1)
            Xt, yt = X[valid], y[valid]
            if len(yt) < 20 or yt.nunique() < 2:
                return None
            pipe = Pipeline([
                ("scaler", StandardScaler()),
                ("clf", GradientBoostingClassifier(
                    n_estimators=self.n_estimators,
                    max_depth=self.max_depth,
                    learning_rate=self.learning_rate,
                    random_state=42,
                )),
            ])
            pipe.fit(Xt.values, yt.values)
            return pipe

        for i, dt in enumerate(all_dates):
            # Update open trades
            new_open = []
            for trade in open_trades:
                trade["days_held"] += 1
                spot    = float(sector_closes.get(trade["ticker"], spy_close).iloc[i])
                iv_now  = float(vix.iloc[i]) / 100.0
                days_rem = max(0, h_days - trade["days_held"])
                t_yr    = days_rem / 252.0
                credit_now = _spread_credit(spot, trade["short_strike"], trade["long_strike"],
                                             t_yr, _RISK_FREE_RATE, iv_now, trade["spread_type"])
                entry_v    = trade["entry_value"]
                pnl_now    = (entry_v - credit_now) * 100

                exit_reason = None
                if pnl_now >= entry_v * 100 * pt_pct:
                    exit_reason = "profit_target"
                elif pnl_now <= -entry_v * 100 * self.stop_loss_mult:
                    exit_reason = "stop_loss"
                elif trade["days_held"] >= h_days:
                    exit_reason = "hold_days"

                if exit_reason:
                    capital += pnl_now
                    trades_list.append({
                        "entry_date":  trade["entry_date"].date(),
                        "exit_date":   dt.date(),
                        "spread_type": trade["spread_type"],
                        "entry_cost":  round(entry_v * 100, 2),
                        "exit_value":  round(credit_now * 100, 2),
                        "pnl":         round(pnl_now, 2),
                        "exit_reason": exit_reason,
                    })
                else:
                    new_open.append(trade)
            open_trades = new_open

            equity_list.append(capital)

            if i < _WARMUP_BARS:
                continue

            # Retrain models — exclude last h_days bars (labels use future data)
            if i - last_train >= _RETRAIN_EVERY:
                cutoff = max(0, i - h_days)
                X_lag  = feats_lag.iloc[:cutoff][self.FEATURE_COLS]
                X_lead = feats_lead.iloc[:cutoff][self.FEATURE_COLS]
                model_lag  = _train_model(X_lag,  labels_lag.iloc[:cutoff])
                model_lead = _train_model(X_lead, labels_lead.iloc[:cutoff])
                last_train = i

            # Rebalance check
            if i - last_rebal < self.rebalance_days:
                continue

            vix_now = float(vix.iloc[i])
            if vix_now > self.vix_max:
                continue

            spy_adx_now = float(feats_lag["spy_adx_14"].iloc[i])
            if spy_adx_now > adx_max_:
                continue

            # Identify laggard and leader from RS ranks
            if len(sector_closes) < 3:
                continue

            rets_10d = {t: float(s.pct_change(10).iloc[i]) for t, s in sector_closes.items()
                        if len(s) > i and not np.isnan(s.pct_change(10).iloc[i])}
            if len(rets_10d) < 3:
                continue

            sorted_tickers = sorted(rets_10d, key=rets_10d.get)
            laggard = sorted_tickers[0]
            leader  = sorted_tickers[-1]

            for role, ticker, model_, stype in [
                ("lag",  laggard, model_lag,  "bear_call"),
                ("lead", leader,  model_lead, "bull_put"),
            ]:
                # Skip if already have a trade in this role
                if any(t.get("role") == role for t in open_trades):
                    continue

                if model_ is None:
                    continue

                # Use the sector-specific feature row for inference
                fdf = all_sector_feats.get(ticker, feats_lag)
                feat_row = fdf.iloc[[i]][self.FEATURE_COLS]
                for col, default in self._FEATURE_DEFAULTS.items():
                    if col in feat_row.columns:
                        feat_row[col] = feat_row[col].fillna(default)
                if feat_row.isna().any().any():
                    continue

                prob = float(model_.predict_proba(feat_row.values)[0][1])
                if prob < conf_min:
                    continue

                sec_close = sector_closes.get(ticker, spy_close)
                spot      = float(sec_close.iloc[i])
                iv_entry  = float(vix.iloc[i]) / 100.0
                t_yr      = dte_tgt / 252.0
                wing_w    = spot * wing
                max_cost  = capital * self.position_size_pct

                if stype == "bear_call":
                    short_K = round(spot * (1 + buf), 2)
                    long_K  = round(short_K + wing_w, 2)
                else:
                    short_K = round(spot * (1 - buf), 2)
                    long_K  = round(short_K - wing_w, 2)

                entry_v = _spread_credit(spot, short_K, long_K, t_yr,
                                          _RISK_FREE_RATE, iv_entry, stype)
                if entry_v <= 0:
                    continue

                open_trades.append({
                    "role": role, "ticker": ticker,
                    "entry_date": dt, "spread_type": stype,
                    "short_strike": short_K, "long_strike": long_K,
                    "entry_value": entry_v,
                    "days_held": 0, "prob": prob,
                })

            # Always update rebalance counter after the check (regardless of entries)
            last_rebal = i

        for trade in open_trades:
            trades_list.append({
                "entry_date":  trade["entry_date"].date(),
                "exit_date":   all_dates[-1].date(),
                "spread_type": trade["spread_type"],
                "entry_cost":  round(trade["entry_value"] * 100, 2),
                "exit_value":  0.0,
                "pnl":         0.0,
                "exit_reason": "end_of_data",
            })

        equity    = pd.Series(equity_list, index=price_data.index, dtype=float)
        daily_ret = equity.pct_change().dropna()
        bh_ret    = spy_close.pct_change().reindex(equity.index).dropna()
        trades_df = pd.DataFrame(trades_list) if trades_list else pd.DataFrame(
            columns=["entry_date", "exit_date", "spread_type",
                     "entry_cost", "exit_value", "pnl", "exit_reason"]
        )
        metrics = compute_all_metrics(
            equity_curve=equity, trades_df=trades_df, benchmark_returns=bh_ret
        )
        self._model_lag  = model_lag
        self._model_lead = model_lead
        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
            extra={"sector_etfs": list(sector_closes.keys())},
        )

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "min_confidence",   "label": "Min confidence (P contained)",
             "type": "slider", "min": 0.50, "max": 0.80, "default": 0.60, "step": 0.05,
             "col": 0, "row": 0,
             "help": "Minimum probability to open each spread leg"},
            {"key": "adx_max",          "label": "SPY ADX ceiling",
             "type": "slider", "min": 20, "max": 45, "default": 30, "step": 5,
             "col": 1, "row": 0,
             "help": "Skip if SPY is strongly trending — mean-reversion edge disappears"},
            {"key": "hold_days",        "label": "Hold days",
             "type": "slider", "min": 5, "max": 21, "default": 10, "step": 1,
             "col": 2, "row": 0,
             "help": "Maximum days to hold each spread leg"},
            {"key": "buffer_pct",       "label": "Strike buffer (% spot)",
             "type": "slider", "min": 0.02, "max": 0.07, "default": 0.04, "step": 0.01,
             "col": 0, "row": 1,
             "help": "Short strike placed this far beyond current sector ETF price"},
            {"key": "wing_width_pct",   "label": "Wing width (% spot)",
             "type": "slider", "min": 0.03, "max": 0.08, "default": 0.05, "step": 0.01,
             "col": 1, "row": 1,
             "help": "Width of each spread leg as % of spot"},
            {"key": "profit_target_pct", "label": "Profit target (% max credit)",
             "type": "slider", "min": 0.30, "max": 0.75, "default": 0.50, "step": 0.05,
             "col": 2, "row": 1,
             "help": "Close each leg at this fraction of maximum credit received"},
        ]

    def get_params(self) -> dict:
        return {
            "min_confidence":     self.min_confidence,
            "adx_max":            self.adx_max,
            "min_rs_rank_spread": self.min_rs_rank_spread,
            "dte_target":         self.dte_target,
            "hold_days":          self.hold_days,
            "buffer_pct":         self.buffer_pct,
            "wing_width_pct":     self.wing_width_pct,
            "profit_target_pct":  self.profit_target_pct,
            "stop_loss_mult":     self.stop_loss_mult,
            "position_size_pct":  self.position_size_pct,
            "vix_max":            self.vix_max,
            "rebalance_days":     self.rebalance_days,
            "n_estimators":       self.n_estimators,
            "max_depth":          self.max_depth,
            "learning_rate":      self.learning_rate,
        }
