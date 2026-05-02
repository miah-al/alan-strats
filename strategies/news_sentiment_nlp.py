"""
News Sentiment NLP Strategy.

THESIS
------
Markets are information-processing engines whose efficiency is bounded by the
speed at which humans can read, interpret, and act on natural-language news.
A systematic NLP pipeline can score the directional sentiment of an earnings
release, analyst note or filing in seconds — long before the average analyst
or retail trader has finished reading. The persistent edge is not insight,
but speed and consistency: machines do not suffer the framing biases that
make humans confuse "record revenue that missed consensus" with bullish news.

LITERATURE
----------
- Tetlock (2007), "Giving Content to Investor Sentiment: The Role of Media in
  the Stock Market," Journal of Finance — first systematic evidence of
  media-sentiment alpha (negative-tone WSJ columns predict downward pressure
  on Dow returns over the next 1-2 days).
- Loughran & McDonald (2011), "When Is a Liability Not a Liability? Textual
  Analysis, Dictionaries, and 10-Ks," Journal of Finance — domain-specific
  positive/negative dictionaries that remain the standard for lexicon-tier
  sentiment in finance.
- Araci (2019), "FinBERT: Financial Sentiment Analysis with Pre-trained
  Language Models," arXiv:1908.10063 — fine-tuned BERT on Reuters/Bloomberg
  text, outperforming general BERT on financial sentiment by 15+ pp.
- Ke, Kelly & Xiu (2019), "Predicting Returns with Text Data," NBER w26186 —
  topic-model-based text scoring delivers Sharpe > 4 in-sample on US equities.

DATA CONTRACT — IMPORTANT
-------------------------
This strategy DOES NOT scrape news, run FinBERT or generate sentiment scores
of its own. Sentiment is an INPUT, supplied via auxiliary_data["news_sentiment"]
as a date-indexed DataFrame:

    columns: ['ticker', 'sentiment_score', 'article_count', 'source_weight']
    where:
      - sentiment_score  : weighted aggregate sentiment in [-1, +1]
                           (FinBERT positive_prob - negative_prob, or the
                            output of any compatible scoring pipeline)
      - article_count    : number of articles the score is based on
      - source_weight    : weighted-average source quality
                           (e.g. SEC filing 1.5, WSJ 1.0, blog 0.3)

If auxiliary_data["news_sentiment"] is missing or empty:
  - generate_signal() → HOLD with reason "no news sentiment data"
  - backtest()        → runs in DEGENERATE FALLBACK with sentiment fixed at 0
                        (the strategy collapses to a pure-momentum filter and
                         emits a UserWarning). We DO NOT FABRICATE sentiment.
                        A sentiment strategy without sentiment is honest about
                         being a no-signal degenerate case.

SIGNAL CONSTRUCTION (per the existing guide article)
----------------------------------------------------
    z = (current_sentiment - 30d_rolling_mean) / 30d_rolling_std

    z >= +sentiment_z_threshold (default +2.0) → strong bullish
    z <= -sentiment_z_threshold (default -2.0) → strong bearish
    |z| <  threshold                            → no signal

The z-score is filtered for low article_count (sparse coverage produces an
unreliable baseline) and high VIX (macro risk overwhelms idiosyncratic news).

WALK-FORWARD TRAINING
---------------------
  - Warmup: 90 bars
  - Retrain: every 20 bars
  - 3-class GBM (n_estimators=80, max_depth=4) predicts 3-day forward
    direction (UP / FLAT / DOWN) using sentiment + price + vol features.
  - Labels are masked for the trailing horizon at every retrain point so
    the model never sees a future-derived label (zero look-ahead).

FEATURE SET (10 features)
-------------------------
  Sentiment:    sentiment_z, sentiment_raw, article_count
  Momentum:     ret_5d, ret_20d
  Volume:       volume_ratio (today / 20d avg)
  Vol regime:   vix_level, ivr_proxy, atm_iv
  Calendar:     days_to_next_earnings (999 if no calendar provided)

LABELS (3-class)
----------------
  +1 (UP)   if 3-day forward return >=  +1.5%
  -1 (DOWN) if 3-day forward return <=  -1.5%
   0 (FLAT) otherwise

ENTRY GATES (all must be true)
------------------------------
  - |sentiment_z| >= sentiment_z_threshold
  - article_count >= min_article_count
  - vix_level <= vix_max
  - model probability of predicted class >= signal_threshold
  - price-confirmation:
       bullish entries: ret_5d > -0.02 (not actively falling)
       bearish entries: ret_5d < +0.02 (not actively rising)

TRADE STRUCTURES (defined-risk debit spreads only)
--------------------------------------------------
  Bullish (z >= +threshold AND model agrees):
    - Long  ATM  call  (~spot)
    - Short OTM call   (~spot * 1.05)
    - DTE: 21
  Bearish (z <= -threshold AND model agrees):
    - Long  ATM  put   (~spot)
    - Short OTM put    (~spot * 0.95)
    - DTE: 21
  Max loss is bounded to debit paid × 100 × contracts.

EXITS
-----
  - Profit target:   +60% of debit
  - Stop loss:       -50% of debit
  - Time stop:       close at 5 DTE remaining
  - Reversal stop:   if sentiment_z reverses through ±reversal_z_threshold
                     (default 1.0) while we are directional, close immediately

PRODUCTION WIRING (what real ops looks like)
--------------------------------------------
  In production this strategy is a thin trader on top of an upstream NLP
  pipeline. The pipeline is responsible for:
    1. Ingesting news from a real-time provider (Bloomberg, RavenPack,
       Benzinga, Refinitiv Real-Time News, NewsAPI.ai, …) plus SEC EDGAR.
    2. Running FinBERT (HuggingFace ProsusAI/finbert) or an LLM extractor on
       each article, optionally with Loughran-McDonald lexicon as a fast
       baseline. Output a per-article score in [-1, +1] plus a relevance
       score wrt each ticker.
    3. Aggregating to a per-ticker daily score using exp(-0.1 * age_hours)
       recency decay and source_weight (SEC=1.5, WSJ=1.0, blog=0.3, …).
    4. Persisting the daily aggregate to a table that this strategy reads
       via auxiliary_data["news_sentiment"]. The strategy itself stays
       NLP-agnostic — swap FinBERT for a finer model and the trader is
       unchanged. This is the correct separation of concerns.
"""

from __future__ import annotations

import logging
import pickle
import warnings
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
_RETRAIN_EVERY    = 20
_FORWARD_HORIZON  = 3       # forward days for label
_LABEL_UP_THRESH  =  0.015  # +1.5%
_LABEL_DN_THRESH  = -0.015  # -1.5%
_SAVED_MODELS_DIR = Path(__file__).parent.parent / "saved_models"

# Class labels for 3-class GBM
_CLASS_DOWN = -1
_CLASS_FLAT =  0
_CLASS_UP   = +1


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalise_sentiment_df(
    sent_df: Optional[pd.DataFrame],
    ticker: str,
    target_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    """
    Normalise the user-supplied sentiment DataFrame into a date-indexed
    table aligned to ``target_index`` with columns:
        sentiment_score, article_count, source_weight

    Accepts:
      - Date-indexed DataFrame with 'ticker' column → filter on ticker
      - Date-indexed DataFrame without ticker column → use as-is (single ticker)
      - MultiIndex (date, ticker) DataFrame → cross-section on ticker

    Missing days are forward-filled then back-filled with neutrals
    (sentiment 0.0, article_count 0, source_weight 0.0).

    If ``sent_df`` is None or empty, returns the neutral fallback frame
    with the same index as ``target_index``.
    """
    neutral = pd.DataFrame({
        "sentiment_score": np.zeros(len(target_index)),
        "article_count":   np.zeros(len(target_index), dtype=float),
        "source_weight":   np.zeros(len(target_index)),
    }, index=target_index)

    if sent_df is None or (isinstance(sent_df, pd.DataFrame) and sent_df.empty):
        return neutral

    df = sent_df.copy()

    # MultiIndex (date, ticker)
    if isinstance(df.index, pd.MultiIndex):
        try:
            df = df.xs(ticker, level=1, drop_level=True)
        except KeyError:
            return neutral
    elif "ticker" in df.columns:
        df = df[df["ticker"].astype(str).str.upper() == str(ticker).upper()].copy()
        df = df.drop(columns=["ticker"])

    if df.empty:
        return neutral

    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # Ensure all required columns are present
    for col, default in (("sentiment_score", 0.0), ("article_count", 0.0),
                          ("source_weight", 0.0)):
        if col not in df.columns:
            df[col] = default

    df = df[["sentiment_score", "article_count", "source_weight"]].astype(float)

    # Reindex onto the price-data calendar; gaps → ffill (news is sticky)
    aligned = df.reindex(target_index).ffill()
    aligned["sentiment_score"] = aligned["sentiment_score"].fillna(0.0)
    aligned["article_count"]   = aligned["article_count"].fillna(0.0)
    aligned["source_weight"]   = aligned["source_weight"].fillna(0.0)
    return aligned


def _compute_sentiment_z(
    sent_score: pd.Series,
    window: int = 30,
    min_periods: int = 5,
) -> pd.Series:
    """
    z = (current - 30d_rolling_mean) / 30d_rolling_std.

    Critically, we use rolling().shift(1)? No — by convention z compares
    *today's* sentiment to the trailing N-day window INCLUDING today, which
    is what the guide article specifies. Look-ahead is not a concern here
    because at inference time we only know past sentiment values up to and
    including today, which is exactly the window used.

    To avoid div-by-zero when the rolling std is exactly 0, we add a small
    epsilon and clip extreme values to ±10.
    """
    roll_mean = sent_score.rolling(window, min_periods=min_periods).mean()
    roll_std  = sent_score.rolling(window, min_periods=min_periods).std()
    z = (sent_score - roll_mean) / roll_std.replace(0, np.nan)
    return z.fillna(0.0).clip(-10.0, 10.0)


def _proxy_ivr(vix: pd.Series, window: int = 252) -> pd.Series:
    roll_low  = vix.rolling(window, min_periods=30).min()
    roll_high = vix.rolling(window, min_periods=30).max()
    rng = (roll_high - roll_low).replace(0, np.nan)
    return ((vix - roll_low) / rng).clip(0.0, 1.0).fillna(0.5)


def _build_feature_matrix(
    close:       pd.Series,
    volume:      pd.Series,
    vix:         pd.Series,
    sentiment:   pd.DataFrame,
    earnings_calendar: Optional[pd.Series],
) -> pd.DataFrame:
    """
    Build the 10-feature matrix aligned to ``close.index``.
    ``sentiment`` must be aligned to close.index already (see
    ``_normalise_sentiment_df``).
    ``earnings_calendar`` is an optional Series of earnings dates
    (datetime index of earnings dates → 1.0).
    """
    sent_score = sentiment["sentiment_score"].astype(float)
    art_count  = sentiment["article_count"].astype(float)

    sentiment_z   = _compute_sentiment_z(sent_score, window=30, min_periods=5)
    sentiment_raw = sent_score
    article_count = art_count

    ret_5d  = close.pct_change(5)
    ret_20d = close.pct_change(20)

    vol_ma20     = volume.rolling(20, min_periods=5).mean()
    volume_ratio = (volume / vol_ma20.replace(0, np.nan)).clip(0.0, 10.0)

    vix_level = vix
    ivr_proxy = _proxy_ivr(vix)
    atm_iv    = (vix / 100.0).clip(0.05, 1.50)

    # Days to next earnings (999 sentinel if no calendar provided)
    if earnings_calendar is not None and not earnings_calendar.empty:
        earnings_dates = pd.to_datetime(earnings_calendar.index).sort_values()
        days_to = []
        for dt in close.index:
            future = earnings_dates[earnings_dates >= pd.Timestamp(dt)]
            days_to.append(float((future[0] - pd.Timestamp(dt)).days)
                           if len(future) > 0 else 999.0)
        days_to_next_earnings = pd.Series(days_to, index=close.index)
    else:
        days_to_next_earnings = pd.Series(999.0, index=close.index)

    feat = pd.DataFrame({
        "sentiment_z":          sentiment_z,
        "sentiment_raw":        sentiment_raw,
        "article_count":        article_count,
        "ret_5d":               ret_5d,
        "ret_20d":              ret_20d,
        "volume_ratio":         volume_ratio,
        "vix_level":            vix_level,
        "ivr_proxy":            ivr_proxy,
        "atm_iv":               atm_iv,
        "days_to_next_earnings": days_to_next_earnings,
    })
    return feat.ffill().fillna(0.0)


def _build_labels(close: pd.Series, n_forward: int = _FORWARD_HORIZON) -> pd.Series:
    """
    3-class label using n_forward forward total return:
      +1 if ret >= +1.5%
      -1 if ret <= -1.5%
       0 otherwise
    Last n_forward bars masked NaN (their label uses future data we will
    not have at training time).
    """
    fwd = close.shift(-n_forward) / close - 1.0
    labels = pd.Series(_CLASS_FLAT, index=close.index, dtype=float)
    labels[fwd >= _LABEL_UP_THRESH] = _CLASS_UP
    labels[fwd <= _LABEL_DN_THRESH] = _CLASS_DOWN
    labels.iloc[-n_forward:] = np.nan
    labels[fwd.isna()] = np.nan
    return labels


def _debit_call_spread_value(S, long_K, short_K, T, r, iv):
    return bs_price(S, long_K, T, r, iv, "call") - bs_price(S, short_K, T, r, iv, "call")


def _debit_put_spread_value(S, long_K, short_K, T, r, iv):
    return bs_price(S, long_K, T, r, iv, "put") - bs_price(S, short_K, T, r, iv, "put")


# ─────────────────────────────────────────────────────────────────────────────
# Strategy class
# ─────────────────────────────────────────────────────────────────────────────

class NewsSentimentNLPStrategy(BaseStrategy):
    """
    News Sentiment NLP — defined-risk directional debit spreads on FinBERT-style
    sentiment z-scores.

    The strategy IS NOT an NLP model. It consumes a sentiment time-series (see
    module docstring DATA CONTRACT) and turns sharp z-score deviations into
    bull-call or bear-put debit spreads, gated by a walk-forward GBM that
    confirms the price direction implied by the news.
    """

    name                 = "news_sentiment_nlp"
    display_name         = "News Sentiment NLP"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = (
        "Defined-risk directional debit spreads driven by news-sentiment z-scores. "
        "Consumes a precomputed sentiment time-series (FinBERT or compatible) and "
        "uses a walk-forward 3-class GBM to confirm direction before entering. "
        "Bullish signals → bull call spread; bearish → bear put spread. Max loss "
        "bounded to debit paid. The strategy does not fabricate sentiment — "
        "without sentiment data it falls back to a degenerate no-signal mode "
        "with an explicit warning."
    )
    asset_class          = "equities_options"
    typical_holding_days = 4
    target_sharpe        = 1.4

    FEATURE_COLS = [
        "sentiment_z",
        "sentiment_raw",
        "article_count",
        "ret_5d",
        "ret_20d",
        "volume_ratio",
        "vix_level",
        "ivr_proxy",
        "atm_iv",
        "days_to_next_earnings",
    ]

    _FEATURE_DEFAULTS = {
        "sentiment_z":           0.0,
        "sentiment_raw":         0.0,
        "article_count":         0.0,
        "ret_5d":                0.0,
        "ret_20d":               0.0,
        "volume_ratio":          1.0,
        "vix_level":             20.0,
        "ivr_proxy":             0.5,
        "atm_iv":                0.20,
        "days_to_next_earnings": 999.0,
    }

    _CRITICAL_FEATURES = {"sentiment_z", "vix_level", "article_count"}

    def __init__(
        self,
        signal_threshold:     float = 0.55,
        sentiment_z_threshold: float = 2.0,
        min_article_count:    int   = 5,
        vix_max:              float = 35.0,
        dte_entry:            int   = 21,
        profit_target_pct:    float = 0.60,
        stop_loss_pct:        float = 0.50,
        dte_time_stop:        int   = 5,
        reversal_z_threshold: float = 1.0,
        position_size_pct:    float = 0.025,
        max_concurrent:       int   = 3,
        n_estimators:         int   = 80,
        max_depth:            int   = 4,
        retrain_every:        int   = _RETRAIN_EVERY,
        commission_per_leg:   float = 0.65,
    ):
        self.signal_threshold      = signal_threshold
        self.sentiment_z_threshold = sentiment_z_threshold
        self.min_article_count     = min_article_count
        self.vix_max               = vix_max
        self.dte_entry             = dte_entry
        self.profit_target_pct     = profit_target_pct
        self.stop_loss_pct         = stop_loss_pct
        self.dte_time_stop         = dte_time_stop
        self.reversal_z_threshold  = reversal_z_threshold
        self.position_size_pct     = position_size_pct
        self.max_concurrent        = max_concurrent
        self.n_estimators          = n_estimators
        self.max_depth             = max_depth
        self.retrain_every         = retrain_every
        self.commission_per_leg    = commission_per_leg
        self._model                = None  # walk-forward sklearn pipeline
        self._classes_             = None  # ordered class array from the fitted model

    # ── Public API ────────────────────────────────────────────────────────

    def is_trainable(self) -> bool:
        return True

    def get_params(self) -> dict:
        return {
            "signal_threshold":      self.signal_threshold,
            "sentiment_z_threshold": self.sentiment_z_threshold,
            "min_article_count":     self.min_article_count,
            "vix_max":               self.vix_max,
            "dte_entry":             self.dte_entry,
            "profit_target_pct":     self.profit_target_pct,
            "stop_loss_pct":         self.stop_loss_pct,
            "dte_time_stop":         self.dte_time_stop,
            "reversal_z_threshold":  self.reversal_z_threshold,
            "position_size_pct":     self.position_size_pct,
            "max_concurrent":        self.max_concurrent,
            "n_estimators":          self.n_estimators,
            "max_depth":             self.max_depth,
            "retrain_every":         self.retrain_every,
            "commission_per_leg":    self.commission_per_leg,
        }

    def get_backtest_ui_params(self) -> list:
        return [
            {"key": "sentiment_z_threshold", "label": "Sentiment z-score threshold",
             "type": "slider", "min": 1.0, "max": 3.5, "default": 2.0, "step": 0.1,
             "col": 0, "row": 0,
             "help": "|z| must exceed this to fire a signal (Tetlock 2007 / "
                     "guide default 2.0)"},
            {"key": "signal_threshold",      "label": "Model probability threshold",
             "type": "slider", "min": 0.45, "max": 0.80, "default": 0.55, "step": 0.05,
             "col": 1, "row": 0,
             "help": "GBM P(class) must exceed this to confirm the sentiment signal"},
            {"key": "min_article_count",     "label": "Min article count",
             "type": "slider", "min": 1, "max": 20, "default": 5, "step": 1,
             "col": 2, "row": 0,
             "help": "Sparse coverage → unreliable z-score (guide §When To Avoid)"},
            {"key": "vix_max",               "label": "VIX ceiling",
             "type": "slider", "min": 20.0, "max": 60.0, "default": 35.0, "step": 1.0,
             "col": 0, "row": 1,
             "help": "Macro risk overrides idiosyncratic news above this VIX level"},
            {"key": "dte_entry",             "label": "Entry DTE",
             "type": "slider", "min": 7, "max": 45, "default": 21, "step": 1,
             "col": 1, "row": 1,
             "help": "Target days-to-expiry for the debit spread"},
            {"key": "profit_target_pct",     "label": "Profit target (× debit)",
             "type": "slider", "min": 0.30, "max": 1.20, "default": 0.60, "step": 0.05,
             "col": 2, "row": 1},
            {"key": "stop_loss_pct",         "label": "Stop loss (× debit)",
             "type": "slider", "min": 0.20, "max": 0.80, "default": 0.50, "step": 0.05,
             "col": 0, "row": 2},
            {"key": "position_size_pct",     "label": "Position size (% capital)",
             "type": "slider", "min": 0.01, "max": 0.06, "default": 0.025, "step": 0.005,
             "col": 1, "row": 2},
        ]

    def save_model(self, ticker: str = "default") -> str:
        _SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        path = _SAVED_MODELS_DIR / f"news_sentiment_nlp_{ticker.lower()}.pkl"
        with open(path, "wb") as f:
            pickle.dump({"model": self._model, "classes": self._classes_}, f)
        logger.info(f"news_sentiment_nlp: model saved to {path}")
        return str(path)

    def load_model(self, ticker: str = "default") -> bool:
        path = _SAVED_MODELS_DIR / f"news_sentiment_nlp_{ticker.lower()}.pkl"
        if not path.exists():
            return False
        with open(path, "rb") as f:
            payload = pickle.load(f)
        if isinstance(payload, dict):
            self._model    = payload.get("model")
            self._classes_ = payload.get("classes")
        else:
            self._model    = payload
            self._classes_ = None
        return self._model is not None

    # ── Live signal ───────────────────────────────────────────────────────

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        """
        Live signal expects:
          - 'sentiment_z'   (float)
          - 'sentiment_raw' (float, optional)
          - 'article_count' (int)
          - 'vix'           (float)
          - 'price'         (float)
          - 'features_df'   (DataFrame with FEATURE_COLS, last row = today)

        Returns HOLD if any of:
          - sentiment data is absent (sentiment_z is None)
          - |z| < sentiment_z_threshold
          - article_count < min_article_count
          - vix > vix_max
          - model is None (must call backtest() or load_model() first)
          - model probability < signal_threshold
          - price-direction does not confirm sentiment direction
        """
        sentiment_z   = market_snapshot.get("sentiment_z")
        article_count = market_snapshot.get("article_count")
        vix           = market_snapshot.get("vix")
        spot          = market_snapshot.get("price") or market_snapshot.get("spot")
        features_df   = market_snapshot.get("features_df")
        ret_5d        = float(market_snapshot.get("ret_5d", 0.0))

        if sentiment_z is None or article_count is None:
            return SignalResult(
                self.name, "HOLD", 0.0, 0.0,
                metadata={"reason": "no news sentiment data"},
            )

        sentiment_z   = float(sentiment_z)
        article_count = float(article_count)
        vix           = float(vix) if vix is not None else 20.0

        # Gate 1: model must exist
        if self._model is None:
            return SignalResult(
                self.name, "HOLD", 0.0, 0.0,
                metadata={"reason": "model_not_loaded",
                          "sentiment_z": round(sentiment_z, 3)},
            )

        # Gate 2: |z| threshold
        if abs(sentiment_z) < self.sentiment_z_threshold:
            return SignalResult(
                self.name, "HOLD", 0.0, 0.0,
                metadata={"reason": "z_below_threshold",
                          "sentiment_z": round(sentiment_z, 3),
                          "threshold":   self.sentiment_z_threshold},
            )

        # Gate 3: sparse coverage
        if article_count < self.min_article_count:
            return SignalResult(
                self.name, "HOLD", 0.0, 0.0,
                metadata={"reason": "article_count_too_low",
                          "article_count": int(article_count),
                          "min_required":  self.min_article_count},
            )

        # Gate 4: macro risk
        if vix > self.vix_max:
            return SignalResult(
                self.name, "HOLD", 0.0, 0.0,
                metadata={"reason": "vix_too_high",
                          "vix": round(vix, 2),
                          "vix_max": self.vix_max},
            )

        # Gate 5: model confirmation
        if features_df is None or features_df.empty:
            return SignalResult(
                self.name, "HOLD", 0.0, 0.0,
                metadata={"reason": "features_unavailable"},
            )

        feat_row = self._prepare_feat_row(features_df.iloc[-1:])
        if feat_row[list(self._CRITICAL_FEATURES)].isna().any(axis=1).iloc[0]:
            return SignalResult(
                self.name, "HOLD", 0.0, 0.0,
                metadata={"reason": "critical_features_nan"},
            )

        proba   = self._model.predict_proba(feat_row.values)[0]
        classes = self._classes_ if self._classes_ is not None else \
                  getattr(self._model, "classes_", np.array([_CLASS_DOWN, _CLASS_FLAT, _CLASS_UP]))
        prob_map = {int(c): float(p) for c, p in zip(classes, proba)}
        p_up   = prob_map.get(_CLASS_UP,   0.0)
        p_down = prob_map.get(_CLASS_DOWN, 0.0)

        # Direction is dictated by sentiment; confirmation is from the model.
        if sentiment_z >= self.sentiment_z_threshold:
            # Bullish signal — model must agree
            if p_up < self.signal_threshold:
                return SignalResult(
                    self.name, "HOLD", round(p_up, 3), 0.0,
                    metadata={"reason": "model_disagrees_bullish",
                              "p_up": round(p_up, 3),
                              "sentiment_z": round(sentiment_z, 3)},
                )
            if ret_5d <= -0.02:
                return SignalResult(
                    self.name, "HOLD", round(p_up, 3), 0.0,
                    metadata={"reason": "price_not_confirming_bullish",
                              "ret_5d": round(ret_5d, 4)},
                )
            return SignalResult(
                self.name, "BUY", round(p_up, 3), self.position_size_pct,
                metadata={
                    "structure":   "bull_call_spread",
                    "sentiment_z": round(sentiment_z, 3),
                    "p_up":        round(p_up, 3),
                    "vix":         round(vix, 2),
                    "spot":        float(spot) if spot is not None else None,
                    "dte":         self.dte_entry,
                },
            )
        # else sentiment_z <= -threshold — bearish
        if p_down < self.signal_threshold:
            return SignalResult(
                self.name, "HOLD", round(p_down, 3), 0.0,
                metadata={"reason": "model_disagrees_bearish",
                          "p_down": round(p_down, 3),
                          "sentiment_z": round(sentiment_z, 3)},
            )
        if ret_5d >= 0.02:
            return SignalResult(
                self.name, "HOLD", round(p_down, 3), 0.0,
                metadata={"reason": "price_not_confirming_bearish",
                          "ret_5d": round(ret_5d, 4)},
            )
        return SignalResult(
            self.name, "BUY", round(p_down, 3), self.position_size_pct,
            metadata={
                "structure":   "bear_put_spread",
                "sentiment_z": round(sentiment_z, 3),
                "p_down":      round(p_down, 3),
                "vix":         round(vix, 2),
                "spot":        float(spot) if spot is not None else None,
                "dte":         self.dte_entry,
            },
        )

    # ── Internals ─────────────────────────────────────────────────────────

    @classmethod
    def _prepare_feat_row(cls, df_slice: pd.DataFrame) -> pd.DataFrame:
        row = df_slice.copy()
        for col in cls.FEATURE_COLS:
            if col not in row.columns:
                row[col] = cls._FEATURE_DEFAULTS[col]
        row = row[cls.FEATURE_COLS]
        row = row.ffill()
        for col, default in cls._FEATURE_DEFAULTS.items():
            row[col] = row[col].fillna(default)
        return row

    # ── Backtest ──────────────────────────────────────────────────────────

    def backtest(
        self,
        price_data:        pd.DataFrame,
        auxiliary_data:    dict,
        ticker:            str = "default",
        starting_capital:  float = 100_000,
        sentiment_z_threshold: Optional[float] = None,
        signal_threshold:      Optional[float] = None,
        min_article_count:     Optional[int]   = None,
        vix_max:               Optional[float] = None,
        dte_entry:             Optional[int]   = None,
        profit_target_pct:     Optional[float] = None,
        stop_loss_pct:         Optional[float] = None,
        position_size_pct:     Optional[float] = None,
        **kwargs,
    ) -> BacktestResult:
        """
        Walk-forward backtest. See module docstring for the full specification.

        Required ``auxiliary_data`` keys:
          - "vix" : DataFrame with 'close' column, date-indexed (REQUIRED)

        Optional ``auxiliary_data`` keys:
          - "news_sentiment"  : sentiment DataFrame (see DATA CONTRACT)
                                If absent or empty, runs in degenerate fallback
                                with sentiment fixed at 0 and emits UserWarning.
          - "earnings_calendar" : Series of earnings dates (datetime index)
        """
        try:
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
        except ImportError as e:
            raise ImportError("scikit-learn required: pip install scikit-learn") from e

        # ── Resolve params ───────────────────────────────────────────────
        z_thr   = sentiment_z_threshold if sentiment_z_threshold is not None else self.sentiment_z_threshold
        sig_thr = signal_threshold      if signal_threshold      is not None else self.signal_threshold
        min_ac  = min_article_count     if min_article_count     is not None else self.min_article_count
        v_max   = vix_max               if vix_max               is not None else self.vix_max
        dte_e   = dte_entry             if dte_entry             is not None else self.dte_entry
        pt_pct  = profit_target_pct     if profit_target_pct     is not None else self.profit_target_pct
        sl_pct  = stop_loss_pct         if stop_loss_pct         is not None else self.stop_loss_pct
        pos_pct = position_size_pct     if position_size_pct     is not None else self.position_size_pct
        rev_thr = self.reversal_z_threshold
        time_stop = self.dte_time_stop
        max_conc  = self.max_concurrent
        comm      = self.commission_per_leg
        r         = _RISK_FREE_RATE

        # ── Align core data ──────────────────────────────────────────────
        price_data = price_data.copy()
        price_data.index = pd.to_datetime(price_data.index)
        price_data = price_data.sort_index()
        close = price_data["close"]
        vol_s = price_data.get("volume", pd.Series(1.0, index=price_data.index))
        idx   = price_data.index

        vix_df = auxiliary_data.get("vix", pd.DataFrame())
        if vix_df is None or (isinstance(vix_df, pd.DataFrame) and vix_df.empty):
            raise ValueError(
                "news_sentiment_nlp: VIX data required in auxiliary_data['vix']."
            )
        vix_df = vix_df.copy()
        vix_df.index = pd.to_datetime(vix_df.index)
        vix = vix_df["close"].reindex(idx).ffill().fillna(20.0)

        # ── Sentiment ingestion (or degenerate fallback) ─────────────────
        sent_input = auxiliary_data.get("news_sentiment")
        sentiment_aligned = _normalise_sentiment_df(sent_input, ticker, idx)
        sentiment_active  = (sent_input is not None
                              and isinstance(sent_input, pd.DataFrame)
                              and not sent_input.empty)
        if not sentiment_active:
            warnings.warn(
                "news_sentiment_nlp: auxiliary_data['news_sentiment'] is missing or "
                "empty — running in DEGENERATE FALLBACK with sentiment=0. The "
                "strategy will not generate sentiment-driven signals. This is the "
                "honest no-signal posture; do NOT interpret backtest results as "
                "evidence of NLP alpha in this mode.",
                UserWarning, stacklevel=2,
            )
            logger.warning("news_sentiment_nlp: degenerate fallback (no sentiment "
                           "data) — expect zero or near-zero trades.")

        earnings_cal = auxiliary_data.get("earnings_calendar")

        # ── Feature matrix + labels ──────────────────────────────────────
        feat_df = _build_feature_matrix(
            close=close, volume=vol_s, vix=vix,
            sentiment=sentiment_aligned,
            earnings_calendar=earnings_cal,
        )
        labels = _build_labels(close, n_forward=_FORWARD_HORIZON)

        # ── Walk-forward simulation ──────────────────────────────────────
        capital         = float(starting_capital)
        equity_curve    = []
        cash_curve      = []
        unreal_curve    = []
        open_trades:   list[dict] = []
        closed_trades: list[dict] = []
        signal_log:    list[dict] = []
        sentiment_log: list[dict] = []
        regime_log:    list[dict] = []

        model_      = None
        classes_    = None
        last_train  = -10**9

        feature_importance: dict = {}

        for i, dt in enumerate(idx):
            spot     = float(close.iloc[i])
            vix_val  = float(vix.iloc[i])
            iv_val   = float(vix.iloc[i] / 100.0)
            sent_z   = float(feat_df["sentiment_z"].iloc[i])
            art_cnt  = float(feat_df["article_count"].iloc[i])
            ret_5d_v = float(feat_df["ret_5d"].iloc[i]) if not np.isnan(
                                feat_df["ret_5d"].iloc[i]) else 0.0

            sentiment_log.append({
                "date":          dt.date(),
                "sentiment_z":   round(sent_z, 4),
                "sentiment_raw": round(float(feat_df["sentiment_raw"].iloc[i]), 4),
                "article_count": int(art_cnt),
                "vix":           round(vix_val, 2),
                "spot":          round(spot, 2),
            })

            # ── 1. MTM open trades + manage exits ────────────────────────
            still_open: list[dict] = []
            unreal_pnl_dollars = 0.0
            for trade in open_trades:
                dte_rem = max(0, trade["expiry_idx"] - i)
                T_now   = max(dte_rem / 252.0, 1e-6)
                stype   = trade["spread_type"]
                if stype == "bull_call":
                    val_now = _debit_call_spread_value(
                        spot, trade["long_K"], trade["short_K"], T_now, r, iv_val,
                    )
                else:
                    val_now = _debit_put_spread_value(
                        spot, trade["long_K"], trade["short_K"], T_now, r, iv_val,
                    )
                debit_per = trade["debit_per_share"]
                pnl_per   = val_now - debit_per
                pnl_total = pnl_per * 100 * trade["contracts"]
                close_comm = 2 * comm * trade["contracts"]

                exit_reason = None
                if pnl_per >= pt_pct * debit_per:
                    exit_reason = "profit_target"
                elif pnl_per <= -sl_pct * debit_per:
                    exit_reason = "stop_loss"
                elif dte_rem <= time_stop:
                    exit_reason = "time_stop"
                elif i == len(idx) - 1:
                    exit_reason = "end_of_data"
                else:
                    # Reversal stop: if we're long bullish exposure but z has dropped
                    # back below +rev_thr (or vice-versa for bearish)
                    if stype == "bull_call" and sent_z <= rev_thr:
                        exit_reason = "reversal"
                    elif stype == "bear_put" and sent_z >= -rev_thr:
                        exit_reason = "reversal"

                if exit_reason:
                    net_pnl = round(pnl_total - close_comm, 2)
                    capital += net_pnl
                    closed_trades.append({
                        "entry_date":    trade["entry_date"].date(),
                        "exit_date":     dt.date(),
                        "spread_type":   stype,
                        "long_K":        round(trade["long_K"], 2),
                        "short_K":       round(trade["short_K"], 2),
                        "debit":         round(debit_per, 4),
                        "exit_value":    round(val_now, 4),
                        "contracts":     trade["contracts"],
                        "pnl":           net_pnl,
                        "exit_reason":   exit_reason,
                        "dte_held":      trade["dte_at_entry"] - dte_rem,
                        "winner":        net_pnl > 0,
                        "sentiment_z_entry": round(trade["sentiment_z_entry"], 3),
                        "model_prob":        round(trade["model_prob"], 3),
                    })
                else:
                    still_open.append(trade)
                    unreal_pnl_dollars += pnl_total

            open_trades = still_open
            mtm_equity  = capital + unreal_pnl_dollars
            equity_curve.append(mtm_equity)
            cash_curve.append(capital)
            unreal_curve.append(unreal_pnl_dollars)

            # ── 2. Retrain (walk-forward, no look-ahead) ─────────────────
            if i >= _WARMUP_BARS and (i - last_train) >= self.retrain_every:
                # Mask trailing horizon: labels.iloc[k] uses close.iloc[k+_FORWARD_HORIZON]
                # so we may only train on rows where k + _FORWARD_HORIZON <= i
                cutoff = max(0, i - _FORWARD_HORIZON)
                X_train_df = feat_df[self.FEATURE_COLS].iloc[:cutoff]
                y_train    = labels.iloc[:cutoff]
                valid = y_train.notna() & X_train_df.notna().all(axis=1)
                X_tr, y_tr = X_train_df[valid].values, y_train[valid].values

                if len(y_tr) >= 40:
                    n_classes_present = len(np.unique(y_tr))
                    if n_classes_present >= 2:
                        try:
                            pipe = Pipeline([
                                ("scaler", StandardScaler()),
                                ("clf", GradientBoostingClassifier(
                                    n_estimators=self.n_estimators,
                                    max_depth=self.max_depth,
                                    learning_rate=0.05,
                                    min_samples_leaf=10,
                                    subsample=0.85,
                                    random_state=42,
                                )),
                            ])
                            pipe.fit(X_tr, y_tr.astype(int))
                            model_     = pipe
                            classes_   = pipe.named_steps["clf"].classes_
                            last_train = i
                            logger.debug(
                                f"news_sentiment_nlp retrained at bar {i} "
                                f"({dt.date()}) on {len(y_tr)} samples, "
                                f"classes={list(classes_)}"
                            )
                        except Exception as e:
                            logger.warning(f"news_sentiment_nlp retrain failed at bar {i}: {e}")

            # ── 3. Entry decision ─────────────────────────────────────────
            enough_history = i >= _WARMUP_BARS
            future_room    = (len(idx) - i) > dte_e
            model_ready    = model_ is not None

            decision = {
                "date":         dt.date(),
                "sentiment_z":  round(sent_z, 4),
                "article_count": int(art_cnt),
                "vix":          round(vix_val, 2),
                "n_open":       len(open_trades),
                "regime":       "SKIP",
                "reason":       "",
            }

            if not enough_history:
                decision["reason"] = "warmup"
                regime_log.append(decision); continue
            if not future_room:
                decision["reason"] = "no_future_room"
                regime_log.append(decision); continue
            if not model_ready:
                decision["reason"] = "model_not_ready"
                regime_log.append(decision); continue
            if len(open_trades) >= max_conc:
                decision["reason"] = "max_concurrent"
                regime_log.append(decision); continue
            if abs(sent_z) < z_thr:
                decision["reason"] = "z_below_threshold"
                regime_log.append(decision); continue
            if art_cnt < min_ac:
                decision["reason"] = "article_count_low"
                regime_log.append(decision); continue
            if vix_val > v_max:
                decision["reason"] = "vix_too_high"
                regime_log.append(decision); continue

            # Critical-NaN guard
            feat_row_df = self._prepare_feat_row(feat_df.iloc[i:i+1])
            if feat_row_df[list(self._CRITICAL_FEATURES)].isna().any(axis=1).iloc[0]:
                decision["reason"] = "critical_nan"
                regime_log.append(decision); continue

            try:
                proba = model_.predict_proba(feat_row_df.values)[0]
            except Exception as e:
                logger.warning(f"news_sentiment_nlp predict failed: {e}")
                decision["reason"] = "predict_failed"
                regime_log.append(decision); continue

            prob_map = {int(c): float(p) for c, p in zip(classes_, proba)}
            p_up     = prob_map.get(_CLASS_UP,   0.0)
            p_down   = prob_map.get(_CLASS_DOWN, 0.0)

            bullish = sent_z >= z_thr
            bearish = sent_z <= -z_thr
            chosen_p = p_up if bullish else p_down

            if chosen_p < sig_thr:
                decision["reason"] = "model_disagrees"
                decision["p_up"]   = round(p_up, 3)
                decision["p_down"] = round(p_down, 3)
                regime_log.append(decision); continue

            if bullish and ret_5d_v <= -0.02:
                decision["reason"] = "price_not_confirming_bullish"
                regime_log.append(decision); continue
            if bearish and ret_5d_v >=  0.02:
                decision["reason"] = "price_not_confirming_bearish"
                regime_log.append(decision); continue

            # ── 4. Build the spread (BS-priced) ──────────────────────────
            T_entry = dte_e / 252.0
            wing_pct = 0.05  # ±5% OTM short strike per spec
            if bullish:
                long_K  = spot
                short_K = spot * (1.0 + wing_pct)
                debit_per = _debit_call_spread_value(spot, long_K, short_K, T_entry, r, iv_val)
                stype = "bull_call"
            else:
                long_K  = spot
                short_K = spot * (1.0 - wing_pct)
                debit_per = _debit_put_spread_value(spot, long_K, short_K, T_entry, r, iv_val)
                stype = "bear_put"

            if debit_per <= 0.05:
                decision["reason"] = "debit_too_small"
                regime_log.append(decision); continue

            max_loss_per_contract = debit_per * 100  # debit-spread max loss = debit
            risk_dollars = capital * pos_pct
            contracts    = max(1, int(risk_dollars / max_loss_per_contract))
            contracts    = min(contracts, 20)

            entry_cost = debit_per * 100 * contracts + 2 * comm * contracts
            if entry_cost > capital:
                decision["reason"] = "insufficient_capital"
                regime_log.append(decision); continue

            capital -= entry_cost
            expiry_idx = min(i + dte_e, len(idx) - 1)
            open_trades.append({
                "entry_date":         dt,
                "expiry_idx":         expiry_idx,
                "dte_at_entry":       dte_e,
                "spread_type":        stype,
                "long_K":             long_K,
                "short_K":            short_K,
                "debit_per_share":    debit_per,
                "contracts":          contracts,
                "sentiment_z_entry":  sent_z,
                "model_prob":         chosen_p,
                "vix_at_entry":       vix_val,
            })
            decision["regime"] = "ENTER"
            decision["reason"] = stype
            decision["p_up"]    = round(p_up, 3)
            decision["p_down"]  = round(p_down, 3)
            regime_log.append(decision)
            signal_log.append({
                "date":          dt.date(),
                "spread_type":   stype,
                "spot":          round(spot, 2),
                "long_K":        round(long_K, 2),
                "short_K":       round(short_K, 2),
                "debit":         round(debit_per, 4),
                "contracts":     contracts,
                "sentiment_z":   round(sent_z, 3),
                "model_prob":    round(chosen_p, 3),
                "vix":           round(vix_val, 2),
            })

        # ── Build output ─────────────────────────────────────────────────
        eq        = pd.Series(equity_curve, index=idx, dtype=float)
        cash_s    = pd.Series(cash_curve,   index=idx, dtype=float)
        unreal_s  = pd.Series(unreal_curve, index=idx, dtype=float)
        daily_ret = eq.pct_change().dropna()
        trades_df = pd.DataFrame(closed_trades) if closed_trades else pd.DataFrame(
            columns=["entry_date","exit_date","spread_type","long_K","short_K",
                     "debit","exit_value","contracts","pnl","exit_reason",
                     "dte_held","winner","sentiment_z_entry","model_prob"]
        )
        bench_ret = close.pct_change().reindex(idx).dropna()
        metrics   = compute_all_metrics(eq, trades_df if not trades_df.empty else None,
                                          benchmark_returns=bench_ret)

        if model_ is not None:
            try:
                clf_step = model_.named_steps["clf"]
                feature_importance = dict(zip(self.FEATURE_COLS,
                                              clf_step.feature_importances_.tolist()))
            except Exception:
                feature_importance = {}

        self._model    = model_
        self._classes_ = classes_

        if model_ is not None:
            try:
                self.save_model(ticker)
            except Exception as e:
                logger.warning(f"news_sentiment_nlp model save failed: {e}")

        if not trades_df.empty:
            n  = len(trades_df)
            nw = int(trades_df["winner"].sum())
            logger.info(
                f"NewsSentimentNLP[{ticker}]: {n} trades, {nw}/{n} winners "
                f"({100*nw/n:.1f}%), final ${capital:,.0f}, "
                f"sentiment_active={sentiment_active}"
            )
        else:
            logger.warning(
                f"NewsSentimentNLP[{ticker}]: 0 trades (sentiment_active={sentiment_active})"
            )

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=eq,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
            extra={
                "model_meta": {
                    "n_estimators":     self.n_estimators,
                    "max_depth":        self.max_depth,
                    "retrain_every":    self.retrain_every,
                    "warmup_bars":      _WARMUP_BARS,
                    "forward_horizon":  _FORWARD_HORIZON,
                    "classes":          [int(c) for c in classes_] if classes_ is not None else [],
                    "sentiment_active": sentiment_active,
                },
                "feature_importance": feature_importance,
                "sentiment_log":      pd.DataFrame(sentiment_log),
                "regime_log":         pd.DataFrame(regime_log),
                "signal_log":         pd.DataFrame(signal_log),
                "cash_curve":         cash_s,
                "unrealised_curve":   unreal_s,
                "n_open_at_end":      len(open_trades),
            },
        )
