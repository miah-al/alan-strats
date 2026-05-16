"""
tests/test_yield_curve_regime.py
Unit tests for the Yield Curve Regime AI strategy.
Run: python -m pytest tests/test_yield_curve_regime.py -v
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures — synthetic SPY + macro generator (no DB / network)
# ──────────────────────────────────────────────────────────────────────────────

def _make_synth_price(n_bars: int = 730, seed: int = 7) -> pd.DataFrame:
    """Mildly trending SPY-like series with realistic vol."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-02", periods=n_bars)
    drift = 0.0005
    vol   = 0.011
    rets  = rng.normal(drift, vol, size=n_bars)
    close = 250.0 * np.cumprod(1 + rets)
    high  = close * (1 + np.abs(rng.normal(0, 0.003, n_bars)))
    low   = close * (1 - np.abs(rng.normal(0, 0.003, n_bars)))
    open_ = close * (1 + rng.normal(0, 0.001, n_bars))
    vol_  = rng.integers(50_000_000, 80_000_000, n_bars)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol_},
        index=dates,
    )


def _make_synth_macro(idx: pd.DatetimeIndex, seed: int = 11,
                       inversion: bool = False) -> pd.DataFrame:
    """
    Synthetic FRED-style macro frame: rate_2y, rate_10y, rate_3m, rate_5y.
    inversion=True: 2y > 10y (curve inverted).
    """
    rng = np.random.default_rng(seed)
    n = len(idx)
    base_10y = 0.025 + np.cumsum(rng.normal(0, 0.0001, n))
    if inversion:
        base_2y = base_10y + 0.005 + rng.normal(0, 0.0005, n)  # inverted
    else:
        base_2y = base_10y - 0.005 + rng.normal(0, 0.0005, n)  # normal
    base_3m = base_2y - 0.002 + rng.normal(0, 0.0003, n)
    base_5y = (base_2y + base_10y) / 2.0 + rng.normal(0, 0.0002, n)
    return pd.DataFrame({
        "rate_2y":  base_2y,
        "rate_10y": base_10y,
        "rate_3m":  base_3m,
        "rate_5y":  base_5y,
    }, index=idx)


def _make_synth_vix(idx: pd.DatetimeIndex, seed: int = 13,
                     base: float = 17.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(idx)
    vix = base + rng.normal(0, 1.5, n).cumsum() * 0.05
    vix = np.clip(vix, 9.0, 60.0)
    return pd.DataFrame({"close": vix}, index=idx)


# ──────────────────────────────────────────────────────────────────────────────
# Basic instantiation / metadata
# ──────────────────────────────────────────────────────────────────────────────

class TestStrategyMetadata:

    def setup_method(self):
        from strategies.yield_curve_regime import YieldCurveRegimeStrategy
        self.cls = YieldCurveRegimeStrategy

    def test_instantiates(self):
        s = self.cls()
        assert s is not None
        assert s.name == "yield_curve_regime"
        assert s.display_name == "Yield Curve Regime"
        assert s.is_trainable() is True
        assert s.asset_class == "equities_options"
        assert s.typical_holding_days == 21
        assert abs(s.target_sharpe - 1.2) < 1e-9

    def test_get_params(self):
        s = self.cls(regime_confidence=0.62, dte_target=35)
        p = s.get_params()
        assert p["regime_confidence"] == pytest.approx(0.62)
        assert p["dte_target"] == 35
        assert "warmup_bars" in p
        assert "retrain_every" in p
        assert p["max_concurrent"] == 2
        assert p["vix_max"] == pytest.approx(35.0)

    def test_ui_params(self):
        s = self.cls()
        ui = s.get_backtest_ui_params()
        assert isinstance(ui, list)
        assert 7 <= len(ui) <= 8
        keys = {p["key"] for p in ui}
        # Ensure key controls exist
        for required in ("regime_confidence", "vix_max", "dte_target",
                         "wing_width_pct", "profit_target_pct", "position_size_pct"):
            assert required in keys
        for p in ui:
            assert "key" in p and "type" in p and "default" in p

    def test_feature_count(self):
        assert len(self.cls.FEATURE_COLS) == 8
        assert "yield_2y10y_spread" in self.cls.FEATURE_COLS
        assert "vix_level"          in self.cls.FEATURE_COLS
        assert {"yield_2y10y_spread", "vix_level"} == self.cls._CRITICAL_FEATURES


# ──────────────────────────────────────────────────────────────────────────────
# Live-signal behaviour
# ──────────────────────────────────────────────────────────────────────────────

class TestSignal:

    def setup_method(self):
        from strategies.yield_curve_regime import YieldCurveRegimeStrategy
        self.s = YieldCurveRegimeStrategy()

    def test_signal_hold_when_no_model(self):
        """No trained model → HOLD, regardless of features."""
        feat = pd.DataFrame({c: [0.0] for c in self.s.FEATURE_COLS})
        feat["vix_level"] = 18.0
        feat["yield_2y10y_spread"] = 0.005
        out = self.s.generate_signal({"vix": 18.0, "features_df": feat})
        assert out.signal == "HOLD"
        assert out.confidence == 0.0

    def test_signal_hold_when_no_macro_data(self):
        """features_df missing entirely → HOLD."""
        out = self.s.generate_signal({"vix": 18.0})
        assert out.signal == "HOLD"
        assert "no model" in out.metadata["reason"]

    def test_signal_hold_when_vix_too_high(self):
        """Even with a model loaded, VIX above ceiling → HOLD."""
        # Train a tiny model so _model is not None
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        rng = np.random.default_rng(0)
        X = rng.normal(size=(60, 8))
        y = rng.integers(low=-1, high=2, size=60)  # -1, 0, 1
        pipe = Pipeline([("s", StandardScaler()),
                         ("c", GradientBoostingClassifier(n_estimators=20, max_depth=2,
                                                            random_state=0))])
        pipe.fit(X, y)
        self.s._model   = pipe
        self.s._classes = list(pipe.named_steps["c"].classes_)

        feat = pd.DataFrame({c: [0.0] for c in self.s.FEATURE_COLS})
        feat["vix_level"] = 50.0
        out = self.s.generate_signal({"vix": 50.0, "features_df": feat})
        assert out.signal == "HOLD"
        assert "vix" in out.metadata["reason"].lower()

    def test_signal_routes_correctly_per_state(self):
        """A model that always predicts BULL → bull_put_spread; always BEAR → bear_put_spread."""
        from sklearn.dummy import DummyClassifier

        # Bull-only stub model
        bull_model = DummyClassifier(strategy="constant", constant=1)
        bull_model.fit(np.zeros((10, 8)), [1] * 10)
        # Inject prob=1 for class 1
        self.s._model   = bull_model
        self.s._classes = [1]
        feat = pd.DataFrame({c: [0.0] for c in self.s.FEATURE_COLS})
        feat["vix_level"]          = 18.0
        feat["yield_2y10y_spread"] = 0.005
        out_bull = self.s.generate_signal({"vix": 18.0, "features_df": feat})
        assert out_bull.signal == "SELL"  # credit = sell premium
        assert out_bull.metadata["structure"] == "bull_put_spread"
        assert out_bull.metadata["predicted_regime"] == 1

        # Bear-only stub model
        bear_model = DummyClassifier(strategy="constant", constant=-1)
        bear_model.fit(np.zeros((10, 8)), [-1] * 10)
        self.s._model   = bear_model
        self.s._classes = [-1]
        out_bear = self.s.generate_signal({"vix": 18.0, "features_df": feat})
        assert out_bear.signal == "BUY"  # debit = buy premium
        assert out_bear.metadata["structure"] == "bear_put_spread"
        assert out_bear.metadata["predicted_regime"] == -1

        # Chop-only stub model
        chop_model = DummyClassifier(strategy="constant", constant=0)
        chop_model.fit(np.zeros((10, 8)), [0] * 10)
        self.s._model   = chop_model
        self.s._classes = [0]
        out_chop = self.s.generate_signal({"vix": 18.0, "features_df": feat})
        assert out_chop.signal == "SELL"
        assert out_chop.metadata["structure"] == "iron_condor"


# ──────────────────────────────────────────────────────────────────────────────
# Label construction — controlled forward returns
# ──────────────────────────────────────────────────────────────────────────────

class TestLabelConstruction:

    def test_label_construction(self):
        """Build a synthetic series with controlled forward 60d behaviour and verify label classes."""
        from strategies.yield_curve_regime import _build_regime_labels, _LABEL_BULL, _LABEL_BEAR, _LABEL_CHOP

        n = 200
        idx = pd.bdate_range("2020-01-02", periods=n)
        # Construct a stairs of three segments: rising (bull), flat (chop), crashing (bear)
        segment = n // 3
        # Bull: smooth ~10% rise over 60 days, low vol
        seg1 = np.linspace(100.0, 112.0, segment)
        # Chop: tight band around 112
        seg2 = 112.0 + np.sin(np.linspace(0, 6 * np.pi, segment)) * 0.5
        # Bear: -8% drop
        seg3 = np.linspace(112.0, 102.0, n - 2 * segment)
        prices = pd.Series(np.concatenate([seg1, seg2, seg3]), index=idx)

        labels = _build_regime_labels(prices, n_forward=60)

        # Last 60 must be NaN (no look-ahead)
        assert labels.iloc[-60:].isna().all()

        # Pick representative anchor points well inside their segments
        bull_anchor = labels.iloc[10]
        # The chop anchor must be deep enough into seg2 that fwd_60 lies inside seg2
        chop_anchor_idx = segment + 5
        chop_anchor = labels.iloc[chop_anchor_idx]

        assert bull_anchor == float(_LABEL_BULL), \
            f"Expected BULL at start of segment 1, got {bull_anchor}"
        # Chop has tight band → small fwd return → label = chop (0)
        assert chop_anchor == float(_LABEL_CHOP), \
            f"Expected CHOP in segment 2, got {chop_anchor}"

    def test_label_classes_are_valid(self):
        from strategies.yield_curve_regime import _build_regime_labels
        rng = np.random.default_rng(42)
        n = 400
        idx = pd.bdate_range("2020-01-02", periods=n)
        prices = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.012, n)), index=idx)
        labels = _build_regime_labels(prices, n_forward=60)
        valid = labels.dropna()
        assert valid.isin([-1.0, 0.0, 1.0]).all()
        # last 60 NaN
        assert labels.iloc[-60:].isna().all()


# ──────────────────────────────────────────────────────────────────────────────
# Walk-forward: no look-ahead
# ──────────────────────────────────────────────────────────────────────────────

class TestNoLookahead:

    def test_no_lookahead(self):
        """
        Verify that at each retraining bar i, the training slice cannot include
        labels whose forward 60-day window extends past bar i.
        """
        from strategies.yield_curve_regime import _build_regime_labels, _FORWARD_DAYS

        n = 300
        idx = pd.bdate_range("2020-01-02", periods=n)
        rng = np.random.default_rng(1)
        prices = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.011, n)), index=idx)
        labels = _build_regime_labels(prices, n_forward=_FORWARD_DAYS)

        # The strategy uses train_cutoff = max(0, i - _FORWARD_DAYS).
        # At bar i, training labels considered are labels.iloc[:train_cutoff].
        # All such labels must have been computable using prices up to bar i (not later).
        for i in [100, 150, 200, 250]:
            train_cutoff = max(0, i - _FORWARD_DAYS)
            train_lbls = labels.iloc[:train_cutoff].dropna()
            # The most recent included label has index <= train_cutoff - 1.
            # That label uses prices up to (train_cutoff - 1) + _FORWARD_DAYS = i - 1.
            # → strictly earlier than bar i. No leakage.
            if len(train_lbls) == 0:
                continue
            last_used_idx = train_lbls.index[-1]
            # locate position of last_used_idx
            pos = idx.get_loc(last_used_idx)
            assert pos + _FORWARD_DAYS < i, \
                f"Label at pos {pos} would use prices up through {pos + _FORWARD_DAYS}, " \
                f"violating no-lookahead at bar {i}"


# ──────────────────────────────────────────────────────────────────────────────
# Backtest behaviour
# ──────────────────────────────────────────────────────────────────────────────

class TestBacktest:

    def test_backtest_errors_without_macro(self):
        """auxiliary_data without 'macro' key (or with empty macro) → ValueError."""
        from strategies.yield_curve_regime import YieldCurveRegimeStrategy
        s = YieldCurveRegimeStrategy()
        price = _make_synth_price(n_bars=300)
        with pytest.raises(ValueError, match=r"macro"):
            s.backtest(price, auxiliary_data={})

        with pytest.raises(ValueError, match=r"macro"):
            s.backtest(price, auxiliary_data={"macro": pd.DataFrame()})

    def test_backtest_errors_when_macro_missing_columns(self):
        from strategies.yield_curve_regime import YieldCurveRegimeStrategy
        s = YieldCurveRegimeStrategy()
        price = _make_synth_price(n_bars=300)
        bad_macro = pd.DataFrame({"rate_10y": [0.025]}, index=[price.index[0]])
        with pytest.raises(ValueError, match=r"missing required"):
            s.backtest(price, auxiliary_data={"macro": bad_macro})

    def test_backtest_runs_on_synthetic(self):
        """
        730 bars (≈3y) of synthetic SPY + macro: warmup 252, retrain every 60.
        After warmup the model should fire — but we only require that the run
        completes, equity is finite, and the result schema is correct.
        """
        from strategies.yield_curve_regime import YieldCurveRegimeStrategy

        price = _make_synth_price(n_bars=730, seed=5)
        macro = _make_synth_macro(price.index, seed=9)
        vix   = _make_synth_vix(price.index, seed=2, base=18.0)

        s = YieldCurveRegimeStrategy(
            regime_confidence=0.40,   # loosen for synthetic data
            warmup_bars=252,
            retrain_every=60,
            max_concurrent=2,
        )
        result = s.backtest(
            price_data=price,
            auxiliary_data={"macro": macro, "vix": vix, "ticker": "SPY_TEST"},
            starting_capital=100_000,
        )

        # Schema
        assert result.equity_curve is not None
        assert len(result.equity_curve) == len(price)
        assert np.isfinite(result.equity_curve.iloc[-1])
        assert isinstance(result.metrics, dict)
        assert isinstance(result.trades, pd.DataFrame)
        assert "regime_series" in result.extra
        assert "signal_ledger" in result.extra
        # Equity must remain positive (defined-risk caps drawdown)
        assert (result.equity_curve > 0).all()

    def test_max_concurrent_enforced(self):
        """Confirm the strategy never holds more than max_concurrent open spreads."""
        from strategies.yield_curve_regime import YieldCurveRegimeStrategy

        price = _make_synth_price(n_bars=730, seed=8)
        macro = _make_synth_macro(price.index, seed=14)
        vix   = _make_synth_vix(price.index, seed=4, base=15.0)

        max_conc = 2
        s = YieldCurveRegimeStrategy(
            regime_confidence=0.35,   # lower bar to encourage entries
            warmup_bars=252,
            retrain_every=40,
            max_concurrent=max_conc,
            dte_target=30,
        )
        result = s.backtest(
            price_data=price,
            auxiliary_data={"macro": macro, "vix": vix},
            starting_capital=200_000,
        )

        # n_open recorded each bar in regime_series
        regime_df = result.extra["regime_series"]
        if not regime_df.empty and "n_open" in regime_df.columns:
            assert int(regime_df["n_open"].max()) <= max_conc, \
                f"max_concurrent breached: max open {regime_df['n_open'].max()} > {max_conc}"
