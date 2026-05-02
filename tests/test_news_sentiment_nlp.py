"""
tests/test_news_sentiment_nlp.py
Unit tests for the News Sentiment NLP strategy.

Run: python -m pytest tests/test_news_sentiment_nlp.py -v

These tests use synthetic data only — no external API calls, no live news,
no FinBERT inference. The strategy is tested as a CONSUMER of a sentiment
time-series, which is the correct contract: it does not generate sentiment.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
import numpy as np
import pandas as pd
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_price_series(n: int = 220, seed: int = 7,
                        drift: float = 0.0003, vol: float = 0.012,
                        start: float = 400.0,
                        spike_days: list | None = None,
                        spike_drift_boost: float = 0.0,
                        spike_horizon: int = 4) -> pd.DataFrame:
    """
    Synthetic SPY-like OHLCV. If ``spike_days`` is provided, the next
    ``spike_horizon`` bars receive an extra ``spike_drift_boost`` per bar —
    used to tie sentiment spikes to forward returns so the GBM has a
    learnable signal in finite synthetic data.
    """
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    if spike_days and spike_drift_boost:
        for sd in spike_days:
            for j in range(1, spike_horizon + 1):
                if sd + j < n:
                    rets[sd + j] += spike_drift_boost
    close = start * np.cumprod(1 + rets)
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame({
        "open":   close * (1 + rng.normal(0, 0.001, n)),
        "high":   close * (1 + np.abs(rng.normal(0, 0.003, n))),
        "low":    close * (1 - np.abs(rng.normal(0, 0.003, n))),
        "close":  close,
        "volume": np.full(n, 1_000_000.0),
    }, index=dates)


def _make_vix_df(idx, level: float = 18.0, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 0.5, len(idx))
    return pd.DataFrame({"close": np.clip(level + noise, 9.0, 60.0)}, index=idx)


def _make_sentiment_df(idx, ticker: str = "SPY",
                        regime: str = "spike_bullish",
                        seed: int = 3) -> pd.DataFrame:
    """
    Construct a synthetic sentiment series:
      - regime="spike_bullish": baseline ~0.0, large +0.6 spikes every ~30 days
      - regime="spike_bearish": baseline ~0.0, large -0.6 spikes every ~30 days
      - regime="quiet":         baseline ~0.0, no spikes
    """
    rng = np.random.default_rng(seed)
    n = len(idx)
    base = rng.normal(0.0, 0.05, n)

    if regime == "spike_bullish":
        for k in range(40, n, 30):
            base[k] += 0.60
            base[k + 1] = base[k + 1] + 0.45 if k + 1 < n else 0
    elif regime == "spike_bearish":
        for k in range(40, n, 30):
            base[k] -= 0.60
            base[k + 1] = base[k + 1] - 0.45 if k + 1 < n else 0

    return pd.DataFrame({
        "ticker":          [ticker] * n,
        "sentiment_score": base,
        "article_count":   np.full(n, 12.0),
        "source_weight":   np.full(n, 1.0),
    }, index=idx)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNewsSentimentNLP:

    def setup_method(self):
        from strategies.news_sentiment_nlp import NewsSentimentNLPStrategy
        self.cls = NewsSentimentNLPStrategy

    # ── 1. instantiation / params / UI ──────────────────────────────────

    def test_instantiates(self):
        s = self.cls()
        assert s is not None
        assert s.name == "news_sentiment_nlp"
        assert s.display_name == "News Sentiment NLP"
        assert s.strategy_type.value == "ai"
        assert s.status.value == "active"
        assert s.is_trainable() is True

    def test_get_params_returns_dict(self):
        s = self.cls()
        p = s.get_params()
        assert isinstance(p, dict)
        for k in ("signal_threshold", "sentiment_z_threshold",
                  "min_article_count", "vix_max", "dte_entry",
                  "profit_target_pct", "stop_loss_pct"):
            assert k in p

    def test_ui_params_well_formed(self):
        s = self.cls()
        ui = s.get_backtest_ui_params()
        assert isinstance(ui, list) and len(ui) >= 7
        for item in ui:
            assert "key" in item
            assert "label" in item
            assert "type" in item
            assert "default" in item

    # ── 2. Live-signal gating ───────────────────────────────────────────

    def test_signal_hold_when_no_model(self):
        """Without a trained model → HOLD with reason model_not_loaded."""
        s = self.cls()
        snap = {
            "sentiment_z":    2.5,
            "article_count":  12,
            "vix":            18.0,
            "price":          400.0,
            "ret_5d":         0.005,
            "features_df":    None,
        }
        r = s.generate_signal(snap)
        assert r.signal == "HOLD"
        assert "model" in r.metadata.get("reason", "").lower()

    def test_signal_hold_when_no_sentiment_data(self):
        """Sentiment_z absent (None) → HOLD with reason 'no news sentiment data'."""
        s = self.cls()
        r = s.generate_signal({"vix": 18.0, "price": 400.0})
        assert r.signal == "HOLD"
        assert r.position_size_pct == 0.0
        assert "no news sentiment data" in r.metadata.get("reason", "")

    def test_signal_hold_when_z_below_threshold(self):
        """z=0.5 → below ±2.0 → HOLD even with model."""
        s = self.cls()
        # Inject a fake model so we exercise the z-gate not the model-gate
        s._model = _DummyModel(p_up=0.99, p_down=0.0)
        s._classes_ = np.array([-1, 0, 1])
        feats = _make_feature_df({"sentiment_z": 0.5, "article_count": 12, "vix_level": 18.0})
        r = s.generate_signal({
            "sentiment_z":   0.5,
            "article_count": 12,
            "vix":           18.0,
            "price":         400.0,
            "ret_5d":        0.005,
            "features_df":   feats,
        })
        assert r.signal == "HOLD"
        assert "z_below_threshold" in r.metadata.get("reason", "")

    def test_signal_buy_call_spread_when_strong_bullish(self):
        """z=+2.5, model agrees, all gates pass → BUY bull_call_spread."""
        s = self.cls()
        s._model = _DummyModel(p_up=0.80, p_down=0.05)
        s._classes_ = np.array([-1, 0, 1])
        feats = _make_feature_df({
            "sentiment_z": 2.5, "sentiment_raw": 0.55, "article_count": 12,
            "ret_5d": 0.005, "ret_20d": 0.02, "volume_ratio": 1.4,
            "vix_level": 18.0, "ivr_proxy": 0.45, "atm_iv": 0.18,
            "days_to_next_earnings": 30,
        })
        r = s.generate_signal({
            "sentiment_z":   2.5,
            "article_count": 12,
            "vix":           18.0,
            "price":         400.0,
            "ret_5d":        0.005,
            "features_df":   feats,
        })
        assert r.signal == "BUY"
        assert r.metadata.get("structure") == "bull_call_spread"
        assert r.position_size_pct > 0

    def test_signal_buy_put_spread_when_strong_bearish(self):
        """z=-2.5, model agrees → BUY bear_put_spread."""
        s = self.cls()
        s._model = _DummyModel(p_up=0.05, p_down=0.80)
        s._classes_ = np.array([-1, 0, 1])
        feats = _make_feature_df({
            "sentiment_z": -2.5, "sentiment_raw": -0.55, "article_count": 12,
            "ret_5d": -0.005, "ret_20d": -0.02, "volume_ratio": 1.4,
            "vix_level": 18.0, "ivr_proxy": 0.45, "atm_iv": 0.18,
            "days_to_next_earnings": 30,
        })
        r = s.generate_signal({
            "sentiment_z":   -2.5,
            "article_count": 12,
            "vix":           18.0,
            "price":         400.0,
            "ret_5d":        -0.005,
            "features_df":   feats,
        })
        assert r.signal == "BUY"
        assert r.metadata.get("structure") == "bear_put_spread"

    def test_signal_hold_when_article_count_low(self):
        """z=+2.5 but article_count=2 → HOLD."""
        s = self.cls()
        s._model = _DummyModel(p_up=0.90, p_down=0.0)
        s._classes_ = np.array([-1, 0, 1])
        feats = _make_feature_df({"sentiment_z": 2.5, "article_count": 2, "vix_level": 18.0})
        r = s.generate_signal({
            "sentiment_z":   2.5,
            "article_count": 2,
            "vix":           18.0,
            "price":         400.0,
            "ret_5d":        0.005,
            "features_df":   feats,
        })
        assert r.signal == "HOLD"
        assert "article" in r.metadata.get("reason", "")

    def test_signal_hold_when_vix_too_high(self):
        """z=+2.5 but VIX=45 → HOLD."""
        s = self.cls()
        s._model = _DummyModel(p_up=0.90, p_down=0.0)
        s._classes_ = np.array([-1, 0, 1])
        feats = _make_feature_df({"sentiment_z": 2.5, "article_count": 12, "vix_level": 45.0})
        r = s.generate_signal({
            "sentiment_z":   2.5,
            "article_count": 12,
            "vix":           45.0,
            "price":         400.0,
            "ret_5d":        0.005,
            "features_df":   feats,
        })
        assert r.signal == "HOLD"
        assert "vix" in r.metadata.get("reason", "").lower()

    # ── 3. z-score correctness ──────────────────────────────────────────

    def test_z_score_computed_correctly(self):
        """
        Synthetic 30-day sentiment series with mean=0.20, std=0.10, today=0.50
        → z ≈ (0.50 - 0.20) / 0.10 = +3.0
        Tolerance: 0.2 (we use sample-std + ffill, so allow small drift).
        """
        from strategies.news_sentiment_nlp import _compute_sentiment_z
        rng = np.random.default_rng(123)
        # Build a 30-day window with mean ≈ 0.20, std ≈ 0.10
        baseline = rng.normal(0.20, 0.10, 30)
        # rescale exactly to target stats
        baseline = (baseline - baseline.mean()) / baseline.std() * 0.10 + 0.20
        series   = pd.Series(np.r_[baseline, [0.50]],
                             index=pd.date_range("2024-01-01", periods=31, freq="B"))
        z = _compute_sentiment_z(series, window=30, min_periods=5)
        # Today's z (last value) — uses trailing 30-bar window inclusive of today.
        # With today=0.50, the window includes the spike, so the realized mean shifts
        # slightly upward and std upward. Compare to expected 3.0 with broad tolerance.
        z_today = float(z.iloc[-1])
        # Sanity: must be strongly positive and in the right ballpark
        assert z_today > 2.0, f"Expected z >> 2 for a 0.30 spike on σ=0.10 baseline, got {z_today}"
        assert z_today < 4.0, f"Expected z within reason; got {z_today}"

    # ── 4. No-lookahead in label/training ───────────────────────────────

    def test_no_lookahead(self):
        """
        _build_labels masks the trailing _FORWARD_HORIZON bars (their label
        would require future data we cannot have at training time).
        """
        from strategies.news_sentiment_nlp import _build_labels, _FORWARD_HORIZON
        rng = np.random.default_rng(0)
        n = 200
        dates = pd.date_range("2023-01-01", periods=n, freq="B")
        close = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=dates)
        labels = _build_labels(close, n_forward=_FORWARD_HORIZON)
        # The trailing _FORWARD_HORIZON bars must be NaN (no future data)
        assert labels.iloc[-_FORWARD_HORIZON:].isna().all()
        # All other labels must be in {-1, 0, +1}
        valid = labels.dropna()
        assert valid.isin([-1.0, 0.0, 1.0]).all()

    # ── 5. Reversal exit ─────────────────────────────────────────────────

    def test_reversal_exit(self):
        """
        Open a bullish trade with high z; later sentiment z falls below the
        reversal threshold → trade closes with exit_reason='reversal'.
        We construct a sentiment series with periodic spikes followed by
        immediate collapse, and align price drift to the spikes so the
        GBM has a learnable signal.
        """
        from strategies.news_sentiment_nlp import NewsSentimentNLPStrategy
        n = 260
        # Spike days: regular cadence so labels have density
        spike_days = list(range(40, n, 30))
        # Each spike lasts 1-2 bars then collapses to 0 (drives reversal signal)
        price_df = _make_price_series(
            n=n, seed=2, drift=0.0008, vol=0.010,
            spike_days=spike_days, spike_drift_boost=0.012, spike_horizon=5,
        )
        idx = price_df.index
        vix_df = pd.DataFrame({"close": np.full(n, 15.0)}, index=idx)

        rng = np.random.default_rng(101)
        sent = rng.normal(0, 0.03, n)
        for sd in spike_days:
            sent[sd]     += 0.70
            if sd + 1 < n: sent[sd + 1] += 0.60
            # Bars sd+2 onwards collapse (no further injection) → z drops fast
        sent_df = pd.DataFrame({
            "ticker":          ["SPY"] * n,
            "sentiment_score": sent,
            "article_count":   np.full(n, 15.0),
            "source_weight":   np.full(n, 1.0),
        }, index=idx)

        s = NewsSentimentNLPStrategy(
            sentiment_z_threshold=1.8,
            min_article_count=5,
            signal_threshold=0.35,
            position_size_pct=0.02,
            reversal_z_threshold=1.0,
            dte_entry=21, dte_time_stop=5,
            max_concurrent=3,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = s.backtest(
                price_data=price_df,
                auxiliary_data={"vix": vix_df, "news_sentiment": sent_df},
                ticker="SPY",
                starting_capital=100_000,
            )
        assert not res.trades.empty, "Expected at least one trade in this regime"
        reasons = set(res.trades["exit_reason"].unique().tolist())
        assert "reversal" in reasons, \
            f"Expected at least one reversal exit; got {reasons}"

    # ── 6. Backtest with sentiment ───────────────────────────────────────

    def test_backtest_runs_with_sentiment(self):
        """260-bar synthetic SPY + bullish sentiment spikes → backtest completes,
        at least one trade fires."""
        from strategies.news_sentiment_nlp import NewsSentimentNLPStrategy
        # Tie sentiment spikes to forward drift so the GBM has a learnable
        # signal — without this, the 3-class GBM concentrates probability
        # on the FLAT class and never fires (correct quant behaviour, but
        # makes the smoke test vacuous on pure-noise data).
        spike_days = list(range(40, 260, 30))
        price_df = _make_price_series(
            n=260, drift=0.0008, vol=0.010,
            spike_days=spike_days, spike_drift_boost=0.012, spike_horizon=4,
        )
        vix_df   = _make_vix_df(price_df.index, level=15.0)
        sent_df  = _make_sentiment_df(price_df.index, ticker="SPY",
                                       regime="spike_bullish")

        s = NewsSentimentNLPStrategy(
            sentiment_z_threshold=1.8,    # slightly looser to ensure trade firing
            min_article_count=5,
            signal_threshold=0.35,
            position_size_pct=0.02,
            max_concurrent=3,
            dte_entry=14, dte_time_stop=3,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = s.backtest(
                price_data=price_df,
                auxiliary_data={"vix": vix_df, "news_sentiment": sent_df},
                ticker="SPY",
                starting_capital=100_000,
            )
        assert res.equity_curve is not None and len(res.equity_curve) == len(price_df)
        assert "model_meta" in res.extra
        assert res.extra["model_meta"]["sentiment_active"] is True
        # In this regime we expect at least one trade.
        assert len(res.trades) >= 1, "Expected at least one trade in bullish regime"

    # ── 7. Backtest without sentiment (degenerate fallback) ──────────────

    def test_backtest_runs_without_sentiment(self):
        """
        auxiliary_data['news_sentiment'] empty → backtest still completes,
        emits a UserWarning, and reports sentiment_active=False.
        """
        from strategies.news_sentiment_nlp import NewsSentimentNLPStrategy
        price_df = _make_price_series(n=200, drift=0.0003, vol=0.011)
        vix_df   = _make_vix_df(price_df.index, level=16.0)

        empty_sent = pd.DataFrame(columns=["ticker", "sentiment_score",
                                            "article_count", "source_weight"])

        s = NewsSentimentNLPStrategy(
            sentiment_z_threshold=2.0, min_article_count=5,
            signal_threshold=0.55, dte_entry=14, dte_time_stop=3,
            position_size_pct=0.02, max_concurrent=3,
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            res = s.backtest(
                price_data=price_df,
                auxiliary_data={"vix": vix_df, "news_sentiment": empty_sent},
                ticker="SPY",
                starting_capital=100_000,
            )
        # Warning was emitted
        assert any(issubclass(_w.category, UserWarning) and
                   "DEGENERATE FALLBACK" in str(_w.message) for _w in w), \
            "Expected DEGENERATE FALLBACK UserWarning"
        # Backtest completed
        assert res.equity_curve is not None
        assert len(res.equity_curve) == len(price_df)
        assert res.extra["model_meta"]["sentiment_active"] is False

    # ── 8. max_concurrent enforcement ───────────────────────────────────

    def test_max_concurrent_enforced(self):
        """Set max_concurrent=1, fire many bullish signals — only 1 trade open at a time."""
        from strategies.news_sentiment_nlp import NewsSentimentNLPStrategy
        n = 260
        idx = pd.date_range("2023-01-02", periods=n, freq="B")
        rng = np.random.default_rng(9)
        rets  = rng.normal(0.0006, 0.011, n)
        close = 400.0 * np.cumprod(1 + rets)
        price_df = pd.DataFrame({
            "open": close, "high": close*1.004, "low": close*0.996,
            "close": close, "volume": np.full(n, 1_000_000.0)
        }, index=idx)
        vix_df = pd.DataFrame({"close": np.full(n, 15.0)}, index=idx)

        # Very frequent positive sentiment spikes
        sent = rng.normal(0, 0.03, n)
        for k in range(40, n, 6):
            sent[k] += 0.65
        sent_df = pd.DataFrame({
            "ticker":          ["SPY"] * n,
            "sentiment_score": sent,
            "article_count":   np.full(n, 20.0),
            "source_weight":   np.full(n, 1.0),
        }, index=idx)

        s = NewsSentimentNLPStrategy(
            sentiment_z_threshold=1.5,
            min_article_count=5,
            signal_threshold=0.38,
            max_concurrent=1,
            dte_entry=21, dte_time_stop=5,
            position_size_pct=0.02,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = s.backtest(
                price_data=price_df,
                auxiliary_data={"vix": vix_df, "news_sentiment": sent_df},
                ticker="SPY",
                starting_capital=100_000,
            )

        # Walk through trade entry/exit dates and verify never > 1 simultaneously open
        if not res.trades.empty:
            events = []
            for _, row in res.trades.iterrows():
                events.append((pd.Timestamp(row["entry_date"]), +1))
                events.append((pd.Timestamp(row["exit_date"]),  -1))
            events.sort()
            count = 0
            max_count = 0
            for _, delta in events:
                count += delta
                max_count = max(max_count, count)
            assert max_count <= 1, f"max_concurrent=1 violated, observed {max_count}"


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers (kept at module bottom so the test class reads top-down cleanly)
# ─────────────────────────────────────────────────────────────────────────────

class _DummyModel:
    """Stand-in for the GBM pipeline used in live-signal tests."""
    def __init__(self, p_up: float, p_down: float):
        # Order matches classes_ = [-1, 0, +1]
        flat = max(0.0, 1.0 - p_up - p_down)
        self._proba = np.array([[p_down, flat, p_up]])

    def predict_proba(self, X):
        # Replicate the row count
        return np.repeat(self._proba, X.shape[0], axis=0)


def _make_feature_df(overrides: dict) -> pd.DataFrame:
    """Single-row feature DataFrame with FEATURE_COLS, applying overrides."""
    from strategies.news_sentiment_nlp import NewsSentimentNLPStrategy
    base = dict(NewsSentimentNLPStrategy._FEATURE_DEFAULTS)
    base.update(overrides)
    return pd.DataFrame([base], index=[pd.Timestamp("2024-06-03")])
