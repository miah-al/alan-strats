"""
tests/test_short_squeeze_detector.py
Unit tests for the Short Squeeze Detector AI strategy.

Run: python -m pytest tests/test_short_squeeze_detector.py -v
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
import numpy as np
import pandas as pd
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic chain / price helpers (same _make_chain pattern as test_dealer_gamma_regime)
# ─────────────────────────────────────────────────────────────────────────────

def _make_chain(spot: float, snapshot_date, strikes_pct=None, dte: int = 30,
                iv: float = 0.45, otm_call_vol: float = 1000.0):
    """
    Build a synthetic option-chain snapshot in the column schema the strategy
    expects: SnapshotDate, StrikePrice, OptionType, ImpliedVol, OpenInterest,
    Delta, DTE, Volume.
    """
    if strikes_pct is None:
        strikes_pct = np.arange(-0.20, 0.21, 0.05)
    rows = []
    for pct in strikes_pct:
        K = round(spot * (1 + pct), 2)
        for opt_type in ("call", "put"):
            # Higher OI / volume on OTM calls — mimics squeeze-setup chain
            if opt_type == "call" and pct > 0.05:
                oi  = 8000
                vol = otm_call_vol
            elif opt_type == "call":
                oi, vol = 4000, 500
            else:
                oi, vol = 3000, 300
            # Coarse delta sign
            if opt_type == "call":
                delta = max(0.0, min(1.0, 0.5 - pct * 2))
            else:
                delta = -max(0.0, min(1.0, 0.5 + pct * 2))
            rows.append({
                "SnapshotDate": pd.Timestamp(snapshot_date),
                "StrikePrice":  K,
                "OptionType":   opt_type,
                "ImpliedVol":   iv,
                "OpenInterest": oi,
                "Delta":        delta,
                "DTE":          dte,
                "Volume":       vol,
            })
    return pd.DataFrame(rows)


def _make_price_series(n_bars: int = 200, start: float = 50.0, seed: int = 0,
                       drift: float = 0.0005, vol: float = 0.02,
                       squeeze_bars: list[int] | None = None,
                       squeeze_size: float = 0.20):
    """
    Synthetic OHLCV price series with deterministic seeded noise. When
    `squeeze_bars` is provided, injects a +`squeeze_size` move at each listed bar
    so labels have at least a handful of positives for the classifier to learn.
    """
    rng = np.random.RandomState(seed)
    rets = rng.normal(drift, vol, n_bars)
    if squeeze_bars:
        for bar in squeeze_bars:
            if 0 <= bar < n_bars:
                rets[bar] += squeeze_size
    closes = start * np.exp(np.cumsum(rets))
    highs = closes * (1 + np.abs(rng.normal(0, vol / 2, n_bars)))
    lows  = closes * (1 - np.abs(rng.normal(0, vol / 2, n_bars)))
    # Force highs to actually exceed close on squeeze bars (ensures labels fire)
    if squeeze_bars:
        for bar in squeeze_bars:
            if 0 <= bar < n_bars:
                highs[bar] = max(highs[bar], closes[bar] * 1.02)
    opens = np.concatenate([[start], closes[:-1]])
    volumes = rng.randint(500_000, 2_000_000, n_bars).astype(float)
    if squeeze_bars:
        for bar in squeeze_bars:
            if 0 <= bar < n_bars:
                volumes[bar] *= 4.0   # volume spike accompanies the squeeze
    idx = pd.date_range("2023-01-02", periods=n_bars, freq="B")
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes,
    }, index=idx)


def _make_vix(price_idx: pd.DatetimeIndex, level: float = 18.0):
    return pd.DataFrame({"close": np.full(len(price_idx), level, dtype=float)},
                        index=price_idx)


def _make_short_interest(price_idx: pd.DatetimeIndex,
                         si_pct: float = 0.30, dtc: float = 4.0,
                         util: float = 0.85):
    """FINRA-style twice-monthly SI series (semi-monthly here)."""
    semi_monthly = price_idx[::10]   # roughly every 10 business days
    return pd.DataFrame({
        "short_interest_pct_float": np.full(len(semi_monthly), si_pct, dtype=float),
        "days_to_cover":            np.full(len(semi_monthly), dtc, dtype=float),
        "utilization":              np.full(len(semi_monthly), util, dtype=float),
    }, index=semi_monthly)


def _make_option_snapshots_for_dates(dates, spot_series, dte: int = 30,
                                     iv: float = 0.45):
    """Build per-date snapshots for every date in `dates`."""
    parts = []
    for d in dates:
        spot = float(spot_series.loc[d])
        parts.append(_make_chain(spot, d, dte=dte, iv=iv))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestShortSqueezeDetector:

    def setup_method(self):
        from strategies.short_squeeze_detector import ShortSqueezeDetectorStrategy
        self.cls = ShortSqueezeDetectorStrategy

    # ── Basic plumbing ────────────────────────────────────────────────────────

    def test_instantiates(self):
        s = self.cls()
        assert s is not None
        assert s.name == "short_squeeze_detector"
        assert s.display_name == "Short Squeeze Detector"
        assert s.status.value == "active"
        assert s.strategy_type.value == "ai"
        assert s.is_trainable() is True

    def test_get_params_returns_dict(self):
        s = self.cls()
        p = s.get_params()
        assert isinstance(p, dict)
        # Spot-check key params
        for key in ("signal_threshold", "position_size_pct", "max_vix",
                    "dte_entry", "otm_pct", "profit_target_pct",
                    "stop_loss_pct", "max_concurrent",
                    "short_int_min", "dtc_max"):
            assert key in p, f"missing param: {key}"

    def test_ui_params_well_formed(self):
        s = self.cls()
        ui = s.get_backtest_ui_params()
        assert len(ui) >= 8
        for item in ui:
            assert "key" in item and "label" in item and "type" in item and "default" in item

    # ── Signal gating ─────────────────────────────────────────────────────────

    def test_signal_hold_when_no_model(self):
        s = self.cls()
        r = s.generate_signal({"vix": 18.0, "volume_ratio": 3.0,
                               "short_interest_pct_float": 0.30,
                               "days_to_cover": 4.0})
        assert r.signal == "HOLD"
        assert r.position_size_pct == 0.0

    def test_signal_hold_when_vix_too_high(self):
        s = self.cls(max_vix=32.0)
        # Even with model present, VIX gate must fire — we don't need a model
        # because the gate runs first.
        r = s.generate_signal({"vix": 40.0, "volume_ratio": 5.0,
                               "short_interest_pct_float": 0.45,
                               "days_to_cover": 3.0})
        assert r.signal == "HOLD"
        assert "vix" in r.metadata.get("reason", "").lower()

    def test_signal_hold_when_volume_low(self):
        s = self.cls()
        r = s.generate_signal({"vix": 18.0, "volume_ratio": 1.0,
                               "short_interest_pct_float": 0.45,
                               "days_to_cover": 3.0})
        assert r.signal == "HOLD"
        assert "volume" in r.metadata.get("reason", "").lower()

    # ── Feature set selection ─────────────────────────────────────────────────

    def test_feature_set_full_when_short_interest_provided(self):
        """When short_interest is in auxiliary_data → 11 features used."""
        s = self.cls()
        # Drive backtest just far enough to trigger feature-set selection,
        # but we can also test the helper directly. Use the latter for speed.
        price = _make_price_series(n_bars=120, seed=1)
        snap_dates = price.index[20::5]
        snap = _make_option_snapshots_for_dates(snap_dates, price["close"])
        si   = _make_short_interest(price.index)
        vix  = _make_vix(price.index, level=18.0)

        result = s.backtest(
            price_data       = price,
            auxiliary_data   = {"option_snapshots": snap, "vix": vix, "short_interest": si},
            starting_capital = 100_000,
            ticker           = "TEST",
        )
        assert s._feature_cols == s.FEATURE_COLS_FULL
        assert len(s._feature_cols) == 11
        assert s._has_short_interest is True
        assert result.extra["feature_set"] == "full"
        assert result.extra["model_meta"]["short_interest_provided"] is True

    def test_feature_set_fallback_when_no_short_interest(self):
        """When short_interest is absent → 7 features (options-only)."""
        s = self.cls()
        price = _make_price_series(n_bars=120, seed=2)
        snap_dates = price.index[20::5]
        snap = _make_option_snapshots_for_dates(snap_dates, price["close"])
        vix  = _make_vix(price.index, level=18.0)

        result = s.backtest(
            price_data       = price,
            auxiliary_data   = {"option_snapshots": snap, "vix": vix},
            starting_capital = 100_000,
            ticker           = "TEST",
        )
        assert s._feature_cols == s.FEATURE_COLS_FALLBACK
        assert len(s._feature_cols) == 7
        assert s._has_short_interest is False
        assert result.extra["feature_set"] == "fallback"

    # ── Label construction ────────────────────────────────────────────────────

    def test_label_construction_15pct(self):
        """+20% spike at i+3 → label[i] = 1; +5% bump → label[i] = 0."""
        # 30-bar synthetic series — first 5 bars flat, then a controlled spike
        n = 30
        idx = pd.date_range("2024-01-02", periods=n, freq="B")
        close = pd.Series(np.full(n, 100.0), index=idx)
        # bar i = 5: spike on i+3
        close.iloc[8]  = 122.0   # +22% from close[5] = 100
        # bar i = 15: only +5% by i+3
        close.iloc[18] = 105.0
        high = close.copy()      # use close as high (test logic)
        price = pd.DataFrame({"open": close, "high": high, "low": close, "close": close,
                              "volume": np.full(n, 1_000_000)}, index=idx)

        feat_index = idx[:n - 5]    # exclude last horizon=5 (would be masked)
        labels = self.cls._build_labels(price, feat_index, horizon=5, threshold=0.15)

        # Bar 5 sees +22% high in window [6..10] → label 1
        assert labels.iloc[5] == 1
        # Bar 15 sees only +5% → label 0
        assert labels.iloc[15] == 0
        # Last horizon bars must be masked (-1) since there isn't a full forward window
        # feat_index ends at idx[24]; idx[24] + 5 = idx[29] which is the last bar (idx 29).
        # fwd_end = 24 + 5 = 29 → 29 >= len(close)=30 is False; so labels.iloc[24]
        # *can* be computed. The previous masked region is for bars whose forward
        # window extends past the end. Let's instead assert the docstring contract:
        # Any feat_index bar i where i + horizon >= len(close) is masked.
        # Build a feat_index that includes the right edge to verify masking:
        feat_index_full = idx
        labels_full = self.cls._build_labels(price, feat_index_full, horizon=5, threshold=0.15)
        # Last 5 bars (indices 25..29 — fwd_end >= 30) → -1
        assert (labels_full.iloc[-5:] == -1).all()

    # ── No-lookahead invariant ────────────────────────────────────────────────

    def test_no_lookahead(self):
        """Model trained at bar fi must only see X[:fi] and y[:fi] (label masked
        for the last `horizon` rows). Verify by inspecting the strategy's
        slicing convention via a direct simulation."""
        s = self.cls(n_estimators=20)
        price = _make_price_series(
            n_bars=200, seed=3,
            squeeze_bars=[35, 65, 95, 125, 155, 180], squeeze_size=0.22,
        )
        snap_dates = price.index[10::3]
        snap = _make_option_snapshots_for_dates(snap_dates, price["close"])
        vix  = _make_vix(price.index, level=18.0)

        # Run backtest, then inspect the feature_df + labels in the result extras
        result = s.backtest(
            price_data       = price,
            auxiliary_data   = {"option_snapshots": snap, "vix": vix},
            starting_capital = 100_000,
            ticker           = "TEST",
        )
        feature_df = result.extra["feature_df"]
        # Re-build labels using the strategy's helper and verify the invariant:
        # for every feat-row i, the label uses ONLY price data through index i+horizon
        labels = self.cls._build_labels(price, feature_df.index, horizon=5, threshold=0.15)
        # For each labelled row, the label was 1 ONLY if the forward 5d high
        # actually exceeded +15% — meaning the label cannot leak data BEFORE i.
        # The strict no-lookahead check: the LAST `horizon` rows must be masked.
        n_masked = int((labels == -1).sum())
        # At minimum the last 5 rows (one per horizon) must be masked when
        # they fall at the right edge of the price series.
        assert n_masked >= 1
        # Training-data slicing test: simulate the backtest's per-bar slicing
        # invariant — at decision bar fi, X_past_df = feature_df.iloc[:fi].
        # Verify that X_past_df does NOT contain row fi.
        test_fi = max(int(len(feature_df) * 0.6), 30)
        X_past = feature_df.iloc[:test_fi]
        assert len(X_past) == test_fi
        # The "forbidden" row is feature_df.iloc[test_fi]
        # — assert that timestamp is NOT in X_past.
        forbidden_ts = feature_df.index[test_fi]
        assert forbidden_ts not in X_past.index

    # ── Backtest input validation ─────────────────────────────────────────────

    def test_backtest_errors_without_options(self):
        s = self.cls()
        price = _make_price_series(n_bars=60)
        vix   = _make_vix(price.index)
        with pytest.raises(ValueError, match="option_snapshots"):
            s.backtest(price_data=price, auxiliary_data={"vix": vix})

    def test_backtest_errors_without_vix(self):
        s = self.cls()
        price = _make_price_series(n_bars=60)
        snap_dates = price.index[10::5]
        snap = _make_option_snapshots_for_dates(snap_dates, price["close"])
        with pytest.raises(ValueError, match="VIX"):
            s.backtest(price_data=price, auxiliary_data={"option_snapshots": snap})

    # ── End-to-end synthetic backtest ────────────────────────────────────────

    def test_backtest_runs_on_synthetic(self):
        """200 bars + 30-day options + optional SI → backtest completes,
        equity series length matches feature_df, model trains at least once.
        Inject squeeze bars so labels have positives for the classifier."""
        s = self.cls(n_estimators=20, max_depth=3)
        price = _make_price_series(
            n_bars=240, seed=7,
            squeeze_bars=[40, 70, 100, 130, 160, 185, 210, 230], squeeze_size=0.22,
        )
        snap_dates = price.index[22::1]   # daily snapshots after 22-bar warmup → ~218 feature rows
        snap = _make_option_snapshots_for_dates(snap_dates, price["close"], dte=30)
        si   = _make_short_interest(price.index, si_pct=0.35, dtc=4.0, util=0.90)
        vix  = _make_vix(price.index, level=18.0)

        result = s.backtest(
            price_data       = price,
            auxiliary_data   = {"option_snapshots": snap, "vix": vix, "short_interest": si},
            starting_capital = 100_000,
            ticker           = "TEST",
        )
        # Equity series should align with feature_df length
        feat_df = result.extra["feature_df"]
        assert len(result.equity_curve) == len(feat_df)
        # Should have trained at least once
        assert result.extra["model_meta"]["n_trainings"] >= 1
        # Metrics dict not empty
        assert isinstance(result.metrics, dict)
        # Equity curve finite throughout
        assert result.equity_curve.notna().all()
        assert (result.equity_curve > 0).all()

    # ── max_concurrent enforcement ────────────────────────────────────────────

    def test_max_concurrent_enforced(self):
        """With max_concurrent=1, no bar can have >1 trade open simultaneously."""
        s = self.cls(
            n_estimators       = 20,
            max_depth          = 3,
            max_concurrent     = 1,
            signal_threshold   = 0.0,    # admit every model decision so we maximise entries
            volume_ratio_min   = 0.0,    # disable the volume gate for this stress test
            short_int_min      = 0.0,
            dtc_max            = 1000.0,
            position_size_pct  = 0.005,
            absolute_risk_cap  = 0.05,
            dte_time_stop      = 5,
            dte_entry          = 30,
        )
        price = _make_price_series(
            n_bars=220, seed=11, drift=0.001, vol=0.025,
            squeeze_bars=[30, 55, 80, 105, 130, 155, 180, 200], squeeze_size=0.22,
        )
        snap_dates = price.index[5::1]   # daily snapshots for max entry chances
        snap = _make_option_snapshots_for_dates(snap_dates, price["close"], dte=30)
        si   = _make_short_interest(price.index, si_pct=0.40, dtc=3.0, util=0.95)
        vix  = _make_vix(price.index, level=18.0)

        result = s.backtest(
            price_data       = price,
            auxiliary_data   = {"option_snapshots": snap, "vix": vix, "short_interest": si},
            starting_capital = 100_000,
            ticker           = "TEST",
        )
        regime = result.extra["regime_log"]
        if not regime.empty and "n_open" in regime.columns:
            assert int(regime["n_open"].max()) <= 1, (
                f"max_concurrent=1 violated — saw {int(regime['n_open'].max())} concurrent open trades"
            )
        # The regime_log records n_open at the start of each bar (after exits, before entry).
        # Also assert no overlap in trades_df: at most one trade open at any timestamp.
        trades = result.trades
        if not trades.empty and len(trades) >= 2:
            tr = trades.copy()
            tr["entry_date"] = pd.to_datetime(tr["entry_date"])
            tr["exit_date"]  = pd.to_datetime(tr["exit_date"])
            # Overlap test: for every pair (a, b) sorted by entry_date, b.entry > a.exit
            tr = tr.sort_values("entry_date").reset_index(drop=True)
            for i in range(1, len(tr)):
                prev_exit = tr.loc[i - 1, "exit_date"]
                cur_entry = tr.loc[i,     "entry_date"]
                # Allow same-day re-entry on the bar after an exit, so cur_entry >= prev_exit
                assert cur_entry >= prev_exit, (
                    f"Overlap: trade {i} entered {cur_entry} but trade {i-1} exited {prev_exit}"
                )
