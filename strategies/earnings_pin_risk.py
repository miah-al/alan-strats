"""
Earnings Pin Risk — AI Strategy.

THESIS
------
"Pin risk" in the earnings literature is the failure case of short-volatility
positions held into an earnings release: the stock either pins close to the
short strike (the trade works — IV crush + small move = full credit) or it
runs through one of the wings (the trade loses, capped by long wings). The
classical evidence:

  * Patell & Wolfson (1979, 1981) — first documented the systematic IV expansion
    into earnings releases and the abrupt crush in the days that follow. The
    crush is the durable component of the earnings vol-risk premium; the move
    that overwhelms it is what kills short-premium structures.
  * Dubinsky & Johannes (2006) "Earnings Announcements and Equity Options" —
    show the IV term structure around earnings (front-month IV jumps, back-month
    barely moves) and document that the *option-implied* move is a noisy estimator
    of the realised post-earnings move; on average it overstates by 15–25%, but
    has a long right tail.
  * Barth & So (2014) "Non-Diversifiable Volatility Risk and Risk Premiums" —
    formalise the earnings volatility-risk premium and show it is largest, in
    risk-adjusted terms, for liquid large-caps that *consistently* deliver small
    post-earnings moves.

CORE EDGE
The premium is real and capturable, but the failure case (the runaway move)
destroys headline returns. The edge is therefore in *event selection*, not in
the structure itself: predict which upcoming earnings will pin (small actual
move relative to the implied move) and only sell the short-straddle structure
on those events. A gradient-boosting classifier learns the conditional
probability of a "pin event" from a small set of pre-event features.

LABEL (computed at T+1 close, never used to train models that observe T-k):
    pin_event = 1 if |close[T+1] - close[T]| / close[T] <= 0.5 * implied_move
                                 ^ 50% of the option-implied move
    where T = earnings release date, implied_move = ATM straddle / spot at T-1.

FEATURES (7, all observable strictly before the release at T-dte):
    ivr_at_release            — IVR at entry (high IVR ⇒ market pricing big
                                 move ⇒ LOWER pin probability)
    recent_realized_vol_60d   — 60-day annualised realised vol
    earnings_history_avg_move — rolling 3-quarter mean |post-earnings return|
    option_market_implied_move — ATM straddle / spot
    size_premium              — market-cap percentile proxy (large caps pin more)
    pre_earnings_5d_momentum  — 5-day return going into the event
    vix_level                 — broad market vol regime

WALK-FORWARD
    * 90-bar warmup before any prediction.
    * Retrain whenever (i) 30 bars elapse OR (ii) a new earnings event lands
      in the training history — whichever comes first.
    * Training set is strictly historical earnings events for the ticker; the
      label for event T is computed using prices at T+1 only and therefore
      cannot leak into any prediction made at T-dte.

ENTRY GATING
    pin_probability >= 0.60        (model conviction)
    ivr_at_release  <= 0.85        (skip mega-rich straddles, model less reliable)
    vix_level       <= 30          (skip macro-stress regimes)
    days_to_earnings in [2, 7]     (entry window)
    concurrent open  <= 2          (cluster control)

STRUCTURE — Iron butterfly (defined risk):
    short ATM call + short ATM put  (the straddle being sold)
    long  call wing at +5% spot
    long  put  wing at -5% spot
    Exit T+1 close (one trading day after release) — the IV crush is exhausted
    after one full session; holding longer adds drift risk that the strategy
    is *not* compensated for.

DIFFERENTIATION FROM EXISTING EARNINGS STRATEGIES
    * earnings_iv_crush       — sells the same structure on EVERY qualifying
                                 event filtered only by implied/historical
                                 ratio. Has no model of which events will pin.
    * earnings_post_drift     — buys a directional bull call spread to capture
                                 PEAD; trades the move, not the pin.
    * earnings_pin_risk (this) — gates entries on a *learned* pin-probability
                                 classifier, then sells the iron butterfly only
                                 on high-conviction pin candidates.

DATA CONTRACT
    auxiliary_data["earnings_calendar"] : REQUIRED DataFrame with columns
        ticker, release_date  (release_date in tz-naive trading-day form).
    auxiliary_data["vix"]               : optional VIX close series (DataFrame
                                           with "close" column).
    A missing earnings_calendar raises ValueError — this is an event-driven
    strategy and fabricating event dates from price action would defeat the
    walk-forward guarantee.
"""

from __future__ import annotations

import logging
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
from alan_trader.backtest.engine import bs_price
from alan_trader.risk.metrics import compute_all_metrics

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
_RISK_FREE_RATE   = 0.045
_WARMUP_BARS      = 90
_RETRAIN_EVERY    = 30
_SAVED_MODELS_DIR = Path(__file__).parent.parent / "saved_models"


# ── Helpers ────────────────────────────────────────────────────────────────────

class _ConstantClassifier:
    """Fallback classifier when training history contains a single label class.

    Returns a constant probability vector in the standard sklearn shape so it
    can be wrapped in a Pipeline alongside a pass-through scaler. Picklable.
    """
    def __init__(self, label_value: int, n_features: int):
        self._p = float(label_value)
        self.feature_importances_ = np.zeros(n_features)

    def predict_proba(self, X):
        n_rows = len(X)
        return np.array([[1.0 - self._p, self._p]] * n_rows)


class _PassThroughScaler:
    """No-op scaler — needed because Pipeline wraps the classifier."""
    def fit(self, X, y=None): return self
    def transform(self, X): return X
    def fit_transform(self, X, y=None): return X


def _atm_straddle_implied_move(
    spot: float, T: float, r: float, iv: float
) -> float:
    """ATM straddle priced via Black-Scholes, returned as fraction of spot.

    ATM straddle ≈ 0.8 * sigma * sqrt(T) is a useful intuition; we price it
    via BS for accuracy at non-trivial T.
    """
    if spot <= 0 or T <= 0 or iv <= 0:
        return 0.0
    c = bs_price(spot, spot, T, r, iv, "call")
    p = bs_price(spot, spot, T, r, iv, "put")
    return float((c + p) / spot)


def _historical_avg_move(
    close: pd.Series, past_release_dates: list[pd.Timestamp], n_quarters: int = 3
) -> float:
    """Mean |close[T+1]/close[T] - 1| over the last n_quarters earnings events.

    Strictly historical — the caller must filter past_release_dates to events
    occurring strictly before the current bar.
    """
    if not past_release_dates:
        return 0.05  # neutral 5% prior
    rels = sorted(past_release_dates)[-n_quarters:]
    moves = []
    for ed in rels:
        try:
            idx = close.index.get_indexer([ed], method="bfill")[0]
        except Exception:
            continue
        if idx <= 0 or idx + 1 >= len(close):
            continue
        c0 = float(close.iloc[idx])
        c1 = float(close.iloc[idx + 1])
        if c0 > 0:
            moves.append(abs(c1 - c0) / c0)
    return float(np.mean(moves)) if moves else 0.05


def _build_event_features(
    close: pd.Series,
    vix: pd.Series,
    release_date: pd.Timestamp,
    feat_idx: int,
    past_release_dates: list[pd.Timestamp],
    iv_at_release: float,
    spot_at_release: float,
    days_to_earnings: int,
    size_proxy: float,
) -> dict:
    """Build the 7-feature snapshot for an event at feat_idx (entry bar).

    Strictly uses prices/vix available at feat_idx — never indexes forward.
    """
    # IVR over a 252-day window of VIX (proxy for ticker IVR — VIX moves drive
    # cross-sectional IV moves and is a reasonable proxy when ticker option
    # snapshots are unavailable).
    vix_slice = vix.iloc[max(0, feat_idx - 252):feat_idx + 1]
    if len(vix_slice) >= 30 and vix_slice.max() > vix_slice.min():
        ivr = float((vix_slice.iloc[-1] - vix_slice.min()) /
                    (vix_slice.max() - vix_slice.min()))
    else:
        ivr = 0.50
    ivr = float(np.clip(ivr, 0.0, 1.0))

    # 60d realised vol
    rets = close.iloc[max(0, feat_idx - 60):feat_idx + 1].pct_change().dropna()
    rv60 = float(rets.std() * np.sqrt(252)) if len(rets) > 5 else 0.20

    # 3-quarter rolling avg post-earnings move
    past = [d for d in past_release_dates if d < release_date]
    hist_move = _historical_avg_move(close, past, n_quarters=3)

    # Implied move from ATM straddle priced at the entry bar with dte = days_to_earnings
    T_release = max(days_to_earnings / 252.0, 1e-4)
    implied_move = _atm_straddle_implied_move(
        spot_at_release, T_release, _RISK_FREE_RATE, iv_at_release
    )

    # 5-day pre-earnings momentum
    if feat_idx >= 5:
        c0 = float(close.iloc[feat_idx - 5])
        c1 = float(close.iloc[feat_idx])
        mom5 = (c1 - c0) / c0 if c0 > 0 else 0.0
    else:
        mom5 = 0.0

    vix_val = float(vix.iloc[feat_idx]) if feat_idx < len(vix) else 20.0

    return {
        "ivr_at_release":            ivr,
        "recent_realized_vol_60d":   rv60,
        "earnings_history_avg_move": hist_move,
        "option_market_implied_move": implied_move,
        "size_premium":              float(size_proxy),
        "pre_earnings_5d_momentum":  float(mom5),
        "vix_level":                 vix_val,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Strategy class
# ─────────────────────────────────────────────────────────────────────────────

class EarningsPinRiskStrategy(BaseStrategy):
    """AI-gated short iron butterfly into earnings releases.

    Predicts P(pin) on each upcoming earnings event from 7 pre-event features
    using a GradientBoostingClassifier trained walk-forward on the ticker's
    own historical earnings events. Enters a defined-risk iron butterfly
    only when P(pin) >= pin_threshold and IVR / VIX gates pass. Closes one
    trading day after the release, capturing IV crush + small-move payoff.
    """

    name                 = "earnings_pin_risk"
    display_name         = "Earnings Pin Risk"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "AI-gated short iron butterfly into earnings releases. A gradient-boosting "
        "classifier predicts pin probability from 7 features (IVR, realised vol, "
        "rolling avg post-earnings move, implied move, size, pre-event momentum, "
        "VIX). Sells ATM straddle with ±5% wings only when P(pin) >= threshold; "
        "exits T+1. Patell-Wolfson (1979) IV crush + Barth-So (2014) vol risk "
        "premium, with a learned event-selection layer."
    )
    asset_class          = "equities_options"
    typical_holding_days = 3
    target_sharpe        = 1.5

    FEATURE_COLS = [
        "ivr_at_release",
        "recent_realized_vol_60d",
        "earnings_history_avg_move",
        "option_market_implied_move",
        "size_premium",
        "pre_earnings_5d_momentum",
        "vix_level",
    ]

    _FEATURE_DEFAULTS = {
        "ivr_at_release":            0.50,
        "recent_realized_vol_60d":   0.25,
        "earnings_history_avg_move": 0.05,
        "option_market_implied_move": 0.05,
        "size_premium":              0.50,
        "pre_earnings_5d_momentum":  0.00,
        "vix_level":                 20.0,
    }

    def __init__(
        self,
        pin_threshold:       float = 0.60,
        ivr_max:             float = 0.85,
        vix_max:             float = 30.0,
        dte_to_earnings_min: int   = 2,
        dte_to_earnings_max: int   = 7,
        exit_days_post:      int   = 1,
        wing_pct:            float = 0.05,
        profit_target_pct:   float = 0.50,
        stop_loss_mult:      float = 2.0,
        position_size_pct:   float = 0.02,
        max_concurrent:      int   = 2,
        n_estimators:        int   = 80,
        max_depth:           int   = 3,
        retrain_every:       int   = 30,
        commission_per_leg:  float = 0.65,
    ):
        self.pin_threshold       = pin_threshold
        self.ivr_max             = ivr_max
        self.vix_max             = vix_max
        self.dte_to_earnings_min = dte_to_earnings_min
        self.dte_to_earnings_max = dte_to_earnings_max
        self.exit_days_post      = exit_days_post
        self.wing_pct            = wing_pct
        self.profit_target_pct   = profit_target_pct
        self.stop_loss_mult      = stop_loss_mult
        self.position_size_pct   = position_size_pct
        self.max_concurrent      = max_concurrent
        self.n_estimators        = n_estimators
        self.max_depth           = max_depth
        self.retrain_every       = retrain_every
        self.commission_per_leg  = commission_per_leg
        self._model              = None  # trained GBM classifier

    # ── Params ─────────────────────────────────────────────────────────────

    def get_params(self) -> dict:
        return {
            "pin_threshold":       self.pin_threshold,
            "ivr_max":             self.ivr_max,
            "vix_max":             self.vix_max,
            "dte_to_earnings_min": self.dte_to_earnings_min,
            "dte_to_earnings_max": self.dte_to_earnings_max,
            "exit_days_post":      self.exit_days_post,
            "wing_pct":            self.wing_pct,
            "profit_target_pct":   self.profit_target_pct,
            "stop_loss_mult":      self.stop_loss_mult,
            "position_size_pct":   self.position_size_pct,
            "max_concurrent":      self.max_concurrent,
            "n_estimators":        self.n_estimators,
            "max_depth":           self.max_depth,
            "retrain_every":       self.retrain_every,
            "commission_per_leg":  self.commission_per_leg,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "pin_threshold",       "label": "Pin probability threshold",
             "type": "slider", "min": 0.50, "max": 0.85, "default": 0.60, "step": 0.05,
             "col": 0, "row": 0,
             "help": "Minimum model P(pin) to enter the iron butterfly."},
            {"key": "ivr_max",             "label": "Max IVR",
             "type": "slider", "min": 0.50, "max": 1.00, "default": 0.85, "step": 0.05,
             "col": 1, "row": 0,
             "help": "Skip when straddle is mega-expensive — model less reliable above this."},
            {"key": "vix_max",             "label": "Max VIX",
             "type": "slider", "min": 18.0, "max": 45.0, "default": 30.0, "step": 1.0,
             "col": 2, "row": 0,
             "help": "Skip macro-stress regimes."},
            {"key": "wing_pct",            "label": "Wing width (% of spot)",
             "type": "slider", "min": 0.03, "max": 0.10, "default": 0.05, "step": 0.005,
             "col": 0, "row": 1,
             "help": "Long wings ±wing_pct from ATM. Wider = more credit, more risk."},
            {"key": "profit_target_pct",   "label": "Profit target (% of credit)",
             "type": "slider", "min": 0.25, "max": 0.85, "default": 0.50, "step": 0.05,
             "col": 1, "row": 1},
            {"key": "position_size_pct",   "label": "Position size (% capital)",
             "type": "slider", "min": 0.01, "max": 0.05, "default": 0.02, "step": 0.005,
             "col": 2, "row": 1,
             "help": "Capital risked per event."},
            {"key": "max_concurrent",      "label": "Max concurrent positions",
             "type": "slider", "min": 1, "max": 5, "default": 2, "step": 1,
             "col": 0, "row": 2,
             "help": "Earnings cluster control."},
            {"key": "n_estimators",        "label": "GBM trees",
             "type": "slider", "min": 30, "max": 200, "default": 80, "step": 10,
             "col": 1, "row": 2},
        ]

    # ── Persistence ────────────────────────────────────────────────────────

    def save_model(self, ticker: str = "default") -> str:
        _SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        path = _SAVED_MODELS_DIR / f"earnings_pin_risk_{ticker.lower()}.pkl"
        with open(path, "wb") as f:
            pickle.dump(self._model, f)
        logger.info(f"earnings_pin_risk: model saved to {path}")
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _SAVED_MODELS_DIR / f"earnings_pin_risk_{ticker.lower()}.pkl"
        if path.exists():
            with open(path, "rb") as f:
                self._model = pickle.load(f)
            logger.info(f"earnings_pin_risk: model loaded from {path}")
            return True
        return False

    def is_trainable(self) -> bool:
        return True

    # ── Live signal ────────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """Live signal.

        Expects market_snapshot keys:
          features_df       : DataFrame with last row containing FEATURE_COLS
          days_to_earnings  : int (days until next earnings release)
          ivr               : float
          vix               : float
        Returns HOLD if model not loaded, outside DTE window, or gate fails.
        """
        days_to_earnings = market_snapshot.get("days_to_earnings")
        ivr              = float(market_snapshot.get("ivr", 0.50))
        vix              = float(market_snapshot.get("vix", 20.0))
        features_df      = market_snapshot.get("features_df")

        if days_to_earnings is None:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": "no upcoming earnings event"},
            )

        if not (self.dte_to_earnings_min <= int(days_to_earnings) <= self.dte_to_earnings_max):
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": f"days_to_earnings={days_to_earnings} outside [{self.dte_to_earnings_min},{self.dte_to_earnings_max}]"},
            )

        if ivr > self.ivr_max:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": f"ivr {ivr:.2f} > max {self.ivr_max:.2f}"},
            )

        if vix > self.vix_max:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": f"vix {vix:.1f} > max {self.vix_max:.1f}"},
            )

        if self._model is None or features_df is None or features_df.empty:
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": "no trained model — call backtest() or load_model() first"},
            )

        try:
            row = features_df[self.FEATURE_COLS].iloc[-1:].copy()
            for col, default in self._FEATURE_DEFAULTS.items():
                row[col] = row[col].fillna(default)
            prob = float(self._model.predict_proba(row.values)[0][1])
        except Exception as e:
            logger.warning(f"earnings_pin_risk live signal failed: {e}")
            return SignalResult(
                strategy_name=self.name, signal="HOLD",
                confidence=0.0, position_size_pct=0.0,
                metadata={"reason": f"inference error: {e}"},
            )

        signal = "SELL" if prob >= self.pin_threshold else "HOLD"
        return SignalResult(
            strategy_name=self.name,
            signal=signal,
            confidence=round(prob, 3),
            position_size_pct=self.position_size_pct if signal == "SELL" else 0.0,
            metadata={
                "pin_probability":  round(prob, 3),
                "ivr":              round(ivr, 3),
                "vix":              round(vix, 2),
                "days_to_earnings": int(days_to_earnings),
            },
        )

    # ── Backtest ───────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:        pd.DataFrame,
        auxiliary_data:    dict,
        ticker:            Optional[str] = None,
        starting_capital:  float = 100_000,
        pin_threshold:     Optional[float] = None,
        ivr_max:           Optional[float] = None,
        vix_max:           Optional[float] = None,
        wing_pct:          Optional[float] = None,
        profit_target_pct: Optional[float] = None,
        position_size_pct: Optional[float] = None,
        max_concurrent:    Optional[int]   = None,
        n_estimators:      Optional[int]   = None,
        **kwargs,
    ) -> BacktestResult:
        """Walk-forward earnings-pin backtest.

        Required:
            auxiliary_data["earnings_calendar"] : DataFrame with columns
                ticker, release_date.  If absent or empty → ValueError.
        """
        # ── Resolve params ────────────────────────────────────────────────
        thresh   = pin_threshold     if pin_threshold     is not None else self.pin_threshold
        ivr_lim  = ivr_max           if ivr_max           is not None else self.ivr_max
        vix_lim  = vix_max           if vix_max           is not None else self.vix_max
        ww       = wing_pct          if wing_pct          is not None else self.wing_pct
        pt       = profit_target_pct if profit_target_pct is not None else self.profit_target_pct
        pos_sz   = position_size_pct if position_size_pct is not None else self.position_size_pct
        max_conc = max_concurrent    if max_concurrent    is not None else self.max_concurrent
        n_est    = n_estimators      if n_estimators      is not None else self.n_estimators
        sl_mult  = self.stop_loss_mult
        comm     = self.commission_per_leg
        r        = _RISK_FREE_RATE

        # ── Earnings calendar — REQUIRED ──────────────────────────────────
        ec_raw = auxiliary_data.get("earnings_calendar")
        if ec_raw is None or (isinstance(ec_raw, pd.DataFrame) and ec_raw.empty):
            raise ValueError(
                "earnings_pin_risk requires auxiliary_data['earnings_calendar'] "
                "(DataFrame with columns: ticker, release_date). This is an "
                "event-driven strategy — fabricating event dates from price "
                "action would defeat the walk-forward guarantee."
            )
        if not isinstance(ec_raw, pd.DataFrame):
            raise ValueError("auxiliary_data['earnings_calendar'] must be a DataFrame.")
        ec = ec_raw.copy()
        # Normalise the date column
        date_col = None
        for c in ("release_date", "date", "earnings_date", "report_date"):
            if c in ec.columns:
                date_col = c
                break
        if date_col is None:
            raise ValueError(
                "earnings_calendar must contain a 'release_date' (or 'date') column."
            )
        ec[date_col] = pd.to_datetime(ec[date_col])

        # ── Align price data ──────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_data = price_data.sort_index()
        close = price_data["close"]
        all_dates = list(price_data.index)
        n = len(all_dates)
        date_to_idx = {d: i for i, d in enumerate(all_dates)}

        # ── VIX (optional) ────────────────────────────────────────────────
        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if isinstance(vix_df, pd.DataFrame) and not vix_df.empty:
            vix_df = vix_df.copy()
            vix_df.index = pd.to_datetime(vix_df.index)
            vix = (
                vix_df["close"]
                .reindex(price_data.index).ffill()
                .infer_objects(copy=False).fillna(20.0)
            )
        else:
            vix = pd.Series(20.0, index=price_data.index)

        # ── Filter calendar to this ticker (if column present) ────────────
        if ticker is not None and "ticker" in ec.columns:
            tkr_up = str(ticker).upper()
            ec = ec[ec["ticker"].astype(str).str.upper() == tkr_up]

        # Snap each release to the next available trading bar (the actual entry
        # decision is taken `dte` bars BEFORE this — see below).
        release_dates_all: list[pd.Timestamp] = []
        for _, row in ec.iterrows():
            rd = row[date_col]
            if rd in date_to_idx:
                release_dates_all.append(rd)
            else:
                # snap to next trading day
                future = [d for d in all_dates if d >= rd]
                if future:
                    release_dates_all.append(future[0])
        release_dates_all = sorted(set(release_dates_all))

        if not release_dates_all:
            logger.warning("earnings_pin_risk: no earnings releases overlap price_data window.")
            # Build empty result rather than crashing
            eq = pd.Series([starting_capital] * n, index=all_dates, dtype=float)
            return BacktestResult(
                strategy_name=self.name,
                equity_curve=eq,
                daily_returns=eq.pct_change().dropna(),
                trades=pd.DataFrame(),
                metrics=compute_all_metrics(eq, None),
                params=self.get_params(),
                extra={"reason": "no earnings events in window"},
            )

        # ── Build size proxy (rolling rank of close — proxies market cap percentile)
        # When the user passes mkt_cap data we'd use it; here we use price level rank
        # as a stable proxy that does not look ahead.
        size_proxy_series = close.rolling(252, min_periods=30).rank(pct=True).fillna(0.5)

        # ── Walk-forward simulation ───────────────────────────────────────
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
        except ImportError:
            raise ImportError("scikit-learn is required. pip install scikit-learn")

        capital         = float(starting_capital)
        reserved_margin = 0.0
        equity_curve    = []
        open_trades:   list[dict] = []
        closed_trades: list[dict] = []
        signal_ledger: list[dict] = []

        # Training pool of historical earnings events: (features_dict, label,
        # observable_at_bar_idx). The third element is the bar index at which
        # the label becomes observable (release_idx + 1) — predictions use ONLY
        # samples whose observable_at_bar_idx < current_bar (no look-ahead).
        training_pool:      list[tuple[dict, int, int]] = []
        last_train_event_n  = 0
        last_train_bar_idx  = -10**9
        model_pipeline      = None
        events_processed:   set = set()

        # Pre-compute, for each release, the entry bar candidate (we'll choose
        # within [dte_min, dte_max]). We pick the latest entry within the window
        # that is an actual trading day.
        release_entry_idx: dict[pd.Timestamp, int] = {}
        for rd in release_dates_all:
            ridx = date_to_idx.get(rd)
            if ridx is None:
                continue
            chosen = None
            # Prefer entry exactly dte_to_earnings_min bars before release (latest
            # legal entry — closest to event = strongest IV crush capture).
            for offset in range(self.dte_to_earnings_min, self.dte_to_earnings_max + 1):
                cand = ridx - offset
                if 0 <= cand < n:
                    chosen = cand
                    break
            if chosen is not None:
                release_entry_idx[rd] = chosen

        # ── Pre-build the labelled training pool from EVERY historical event.
        # For each release we compute (features at entry bar, pin label observed
        # at release+1, observable_at = release_idx + 1). When the walk-forward
        # loop reaches bar i, it filters to samples with observable_at < i —
        # so no future labels can leak into a prediction. This is what allows
        # the model to bootstrap before any trade has actually been executed.
        for rd in release_dates_all:
            ridx = date_to_idx.get(rd)
            entry_idx = release_entry_idx.get(rd)
            if ridx is None or entry_idx is None or ridx + 1 >= n:
                continue
            past_releases = [d for d in release_dates_all if d < rd]
            spot_e = float(close.iloc[entry_idx])
            iv_e   = float(vix.iloc[entry_idx]) / 100.0
            size_p = float(size_proxy_series.iloc[entry_idx]) if entry_idx < len(size_proxy_series) else 0.5
            feats = _build_event_features(
                close=close, vix=vix, release_date=rd,
                feat_idx=entry_idx, past_release_dates=past_releases,
                iv_at_release=iv_e, spot_at_release=spot_e,
                days_to_earnings=ridx - entry_idx, size_proxy=size_p,
            )
            implied_at_entry = feats["option_market_implied_move"]
            c0 = float(close.iloc[ridx])
            c1 = float(close.iloc[ridx + 1])
            actual_move = abs(c1 - c0) / c0 if c0 > 0 else 0.0
            label = 1 if actual_move <= 0.5 * implied_at_entry else 0
            observable_at = ridx + 1  # label becomes known at this bar
            training_pool.append((feats, label, observable_at))

        for i, dt in enumerate(all_dates):
            spot    = float(close.iloc[i])
            vix_val = float(vix.iloc[i])
            iv_val  = vix_val / 100.0

            # ── 1. Manage open trades ─────────────────────────────────────
            still_open: list[dict] = []
            unrealized = 0.0
            for trade in open_trades:
                exit_idx = trade["exit_idx"]
                T_now = max((trade["release_idx"] + self.exit_days_post + 1 - i) / 252.0, 1e-6)

                cs = bs_price(spot, trade["call_short_K"], T_now, r, iv_val, "call")
                cl = bs_price(spot, trade["call_long_K"],  T_now, r, iv_val, "call")
                ps = bs_price(spot, trade["put_short_K"],  T_now, r, iv_val, "put")
                pl = bs_price(spot, trade["put_long_K"],   T_now, r, iv_val, "put")

                cur_cost = max((cs - cl) + (ps - pl), 0.0)
                pnl_per  = trade["credit"] - cur_cost
                pnl_tot  = pnl_per * trade["contracts"] * 100
                close_comm = 4 * comm * trade["contracts"]

                exit_reason = None
                # Profit target — only allowed AFTER the release (the IV crush has happened)
                if i > trade["release_idx"] and pnl_per >= pt * trade["credit"]:
                    exit_reason = "profit_target"
                elif i >= exit_idx:
                    exit_reason = "scheduled_exit"
                elif i > trade["release_idx"] and cur_cost >= sl_mult * trade["credit"]:
                    exit_reason = "stop_loss"
                elif i == n - 1:
                    exit_reason = "end_of_data"

                if exit_reason:
                    net_pnl = round(pnl_tot - close_comm, 2)
                    reserved_margin -= trade["margin_reserved"]
                    capital         += net_pnl

                    # Recompute the realised post-earnings move for the trade record.
                    # (The training-pool label was pre-computed at backtest start
                    # using the same arithmetic — see training_pool build above —
                    # so the model already saw this event's label as soon as
                    # bar release_idx+1 elapsed; we don't double-count.)
                    if 0 <= trade["release_idx"] < n - 1:
                        c0 = float(close.iloc[trade["release_idx"]])
                        c1 = float(close.iloc[min(trade["release_idx"] + 1, n - 1)])
                        actual_move = abs(c1 - c0) / c0 if c0 > 0 else 0.0
                    else:
                        actual_move = 0.0
                    pin_label = 1 if actual_move <= 0.5 * trade["implied_move_at_entry"] else 0

                    closed_trades.append({
                        "entry_date":        trade["entry_date"].date(),
                        "release_date":      trade["release_date"].date(),
                        "exit_date":         dt.date(),
                        "spot_entry":        round(trade["spot_entry"], 2),
                        "spot_release":      round(c0 if 0 <= trade["release_idx"] < n else trade["spot_entry"], 2),
                        "spot_exit":         round(spot, 2),
                        "atm_strike":        round(trade["call_short_K"], 2),
                        "call_long_K":       round(trade["call_long_K"],  2),
                        "put_long_K":        round(trade["put_long_K"],   2),
                        "credit":            round(trade["credit"], 4),
                        "contracts":         trade["contracts"],
                        "margin_reserved":   round(trade["margin_reserved"], 2),
                        "pnl":               net_pnl,
                        "exit_reason":       exit_reason,
                        "winner":            net_pnl > 0,
                        "model_prob":        round(trade["model_prob"], 3),
                        "implied_move_at_entry": round(trade["implied_move_at_entry"], 4),
                        "actual_move":       round(actual_move, 4),
                        "pin_label":         pin_label,
                    })
                else:
                    still_open.append(trade)
                    unrealized += pnl_per * trade["contracts"] * 100

            open_trades = still_open
            equity_curve.append(capital + unrealized)

            # ── 2. Retrain model if due ───────────────────────────────────
            # Look-ahead safe filter: only use training samples whose label
            # was OBSERVABLE strictly before the current bar i.
            available_events = [(f, lbl) for (f, lbl, obs_at) in training_pool if obs_at < i]
            new_events_since_train = len(available_events) - last_train_event_n
            bars_since_train       = i - last_train_bar_idx
            ready_to_train = (
                i >= _WARMUP_BARS
                and len(available_events) >= 1
                and (new_events_since_train >= 1 or bars_since_train >= self.retrain_every)
            )
            if ready_to_train:
                X = np.array([[e[0][f] for f in self.FEATURE_COLS] for e in available_events])
                y = np.array([e[1] for e in available_events], dtype=int)
                if len(np.unique(y)) >= 2 and len(y) >= 4:
                    try:
                        model_pipeline = Pipeline([
                            ("scaler", StandardScaler()),
                            ("clf", GradientBoostingClassifier(
                                n_estimators=n_est,
                                max_depth=self.max_depth,
                                learning_rate=0.05,
                                min_samples_leaf=1,
                                subsample=0.85,
                                random_state=42,
                            )),
                        ])
                        model_pipeline.fit(X, y)
                        last_train_event_n = len(available_events)
                        last_train_bar_idx = i
                        logger.debug(
                            "earnings_pin_risk: retrained at bar %d "
                            "(%d events, %d positive)", i, len(y), int(y.sum())
                        )
                    except Exception as e:
                        logger.warning(f"earnings_pin_risk: retrain failed: {e}")
                elif len(np.unique(y)) == 1 and len(y) >= 1:
                    # Degenerate: only one class observed in history. Use a
                    # constant-output stub that returns the empirical class
                    # probability — keeps the strategy from blocking forever
                    # while still being honest about its lack of information.
                    # Bypass Pipeline (sklearn's is_fitted check rejects naive stubs).
                    model_pipeline = _ConstantClassifier(int(y[0]), len(self.FEATURE_COLS))
                    # Wrap with named_steps shim so the post-loop feature_importance
                    # extraction doesn't crash.
                    model_pipeline.named_steps = {"clf": model_pipeline}
                    last_train_event_n = len(available_events)
                    last_train_bar_idx = i
                    logger.debug(
                        "earnings_pin_risk: single-class history at bar %d, "
                        "using constant-probability stub (p=%.3f)", i, model_pipeline._p
                    )

            # ── 3. Entry check — is today an entry bar for some release? ──
            # Find any release whose entry bar equals i AND that we have not processed
            for rd, entry_idx in release_entry_idx.items():
                if entry_idx != i or rd in events_processed:
                    continue
                ridx = date_to_idx[rd]
                days_to_earnings = ridx - i
                if not (self.dte_to_earnings_min <= days_to_earnings <= self.dte_to_earnings_max):
                    continue
                if len(open_trades) >= max_conc:
                    continue
                if vix_val > vix_lim:
                    continue

                # Build features
                past_releases = [d for d in release_dates_all if d < rd]
                size_proxy = float(size_proxy_series.iloc[i]) if i < len(size_proxy_series) else 0.5
                feats = _build_event_features(
                    close=close,
                    vix=vix,
                    release_date=rd,
                    feat_idx=i,
                    past_release_dates=past_releases,
                    iv_at_release=iv_val,
                    spot_at_release=spot,
                    days_to_earnings=days_to_earnings,
                    size_proxy=size_proxy,
                )
                ivr_val = feats["ivr_at_release"]
                if ivr_val > ivr_lim:
                    events_processed.add(rd)
                    signal_ledger.append({
                        "release_date": rd.date(),
                        "entry_date":   dt.date(),
                        "decision":     "skip_ivr",
                        "ivr":          round(ivr_val, 3),
                        "model_prob":   None,
                    })
                    continue

                # Predict pin probability
                if model_pipeline is None:
                    events_processed.add(rd)
                    signal_ledger.append({
                        "release_date": rd.date(),
                        "entry_date":   dt.date(),
                        "decision":     "skip_no_model",
                        "model_prob":   None,
                    })
                    continue

                try:
                    X_row = np.array([[feats[f] for f in self.FEATURE_COLS]])
                    prob = float(model_pipeline.predict_proba(X_row)[0][1])
                except Exception:
                    prob = 0.0

                if prob < thresh:
                    events_processed.add(rd)
                    signal_ledger.append({
                        "release_date": rd.date(),
                        "entry_date":   dt.date(),
                        "decision":     "skip_low_prob",
                        "model_prob":   round(prob, 3),
                        "ivr":          round(ivr_val, 3),
                    })
                    continue

                # ── Construct the iron butterfly ─────────────────────────
                T_release = max(days_to_earnings / 252.0, 1e-4)
                # ATM strike rounded to nearest dollar
                if spot <= 500:
                    atm_K = round(spot)
                else:
                    atm_K = round(spot / 5) * 5
                wing_w = max(spot * ww, 1.0)
                call_short_K = atm_K
                put_short_K  = atm_K
                call_long_K  = atm_K + wing_w
                put_long_K   = atm_K - wing_w

                credit = (
                    bs_price(spot, call_short_K, T_release, r, iv_val, "call")
                    - bs_price(spot, call_long_K,  T_release, r, iv_val, "call")
                    + bs_price(spot, put_short_K,  T_release, r, iv_val, "put")
                    - bs_price(spot, put_long_K,   T_release, r, iv_val, "put")
                )
                if credit <= 0.05:
                    events_processed.add(rd)
                    signal_ledger.append({
                        "release_date": rd.date(),
                        "entry_date":   dt.date(),
                        "decision":     "skip_no_credit",
                        "model_prob":   round(prob, 3),
                    })
                    continue

                # Defined-risk: max loss per spread = wing_w - credit
                max_loss_per = wing_w - credit
                if max_loss_per <= 0:
                    events_processed.add(rd)
                    continue
                budget    = capital * pos_sz
                contracts = max(1, int(budget / (max_loss_per * 100)))
                contracts = min(contracts, 25)

                margin_needed = max_loss_per * contracts * 100
                open_comm     = 4 * comm * contracts
                exit_idx      = min(ridx + self.exit_days_post, n - 1)

                reserved_margin += margin_needed
                capital         -= open_comm
                events_processed.add(rd)

                implied_move = feats["option_market_implied_move"]
                open_trades.append({
                    "entry_date":            dt,
                    "release_date":          rd,
                    "release_idx":           ridx,
                    "exit_idx":              exit_idx,
                    "call_short_K":          call_short_K,
                    "call_long_K":           call_long_K,
                    "put_short_K":           put_short_K,
                    "put_long_K":            put_long_K,
                    "credit":                credit,
                    "wing_width":            wing_w,
                    "contracts":             contracts,
                    "margin_reserved":       margin_needed,
                    "spot_entry":            spot,
                    "model_prob":            prob,
                    "features":              feats,
                    "implied_move_at_entry": implied_move,
                })
                signal_ledger.append({
                    "release_date": rd.date(),
                    "entry_date":   dt.date(),
                    "decision":     "enter",
                    "spot":         round(spot, 2),
                    "atm_K":        round(atm_K, 2),
                    "credit":       round(credit, 4),
                    "contracts":    contracts,
                    "model_prob":   round(prob, 3),
                    "ivr":          round(ivr_val, 3),
                    "implied_move": round(implied_move, 4),
                })

        # ── Build outputs ────────────────────────────────────────────────
        eq        = pd.Series(equity_curve, index=all_dates, dtype=float)
        daily_ret = eq.pct_change().dropna()
        trades_df = pd.DataFrame(closed_trades) if closed_trades else pd.DataFrame()
        signal_df = pd.DataFrame(signal_ledger) if signal_ledger else pd.DataFrame()
        bh_ret    = close.pct_change().reindex(eq.index).dropna()

        metrics = compute_all_metrics(
            equity_curve=eq,
            trades_df=trades_df if not trades_df.empty else None,
            benchmark_returns=bh_ret,
        )

        # Persist trained model
        self._model = model_pipeline
        if model_pipeline is not None and ticker:
            try:
                self.save_model(ticker)
            except Exception as e:
                logger.warning(f"earnings_pin_risk: model save failed: {e}")

        if closed_trades:
            n_trades  = len(closed_trades)
            n_winners = sum(1 for t in closed_trades if t["winner"])
            logger.info(
                f"earnings_pin_risk: {n_trades} trades, "
                f"{n_winners}/{n_trades} winners ({100*n_winners/n_trades:.1f}%), "
                f"final ${capital:,.0f}"
            )
        else:
            logger.info("earnings_pin_risk: 0 trades (model warmup or all events filtered)")

        return BacktestResult(
            strategy_name = self.name,
            equity_curve  = eq,
            daily_returns = daily_ret,
            trades        = trades_df,
            metrics       = metrics,
            params        = self.get_params(),
            extra         = {
                "signal_ledger":  signal_df,
                "n_open_at_end":  len(open_trades),
                "n_train_events": len(training_pool),
                "feature_importance": (
                    dict(zip(self.FEATURE_COLS,
                             model_pipeline.named_steps["clf"].feature_importances_))
                    if model_pipeline is not None else {}
                ),
            },
        )
