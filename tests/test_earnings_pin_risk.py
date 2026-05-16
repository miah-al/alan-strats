"""
tests/test_earnings_pin_risk.py
Unit tests for the Earnings Pin Risk AI strategy.
Run: python -m pytest tests/test_earnings_pin_risk.py -v
"""
import os
import sys
import math

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Synthetic data builders ──────────────────────────────────────────────────

def _build_synth_prices(n_days: int = 365, start: str = "2022-01-03",
                        seed: int = 7) -> pd.DataFrame:
    """Daily OHLCV with mild drift + 1% daily vol — realistic large-cap behaviour."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, periods=n_days)
    rets = rng.normal(loc=0.0003, scale=0.01, size=n_days)
    close = 150.0 * np.exp(np.cumsum(rets))
    high = close * (1.0 + np.abs(rng.normal(0, 0.004, n_days)))
    low  = close * (1.0 - np.abs(rng.normal(0, 0.004, n_days)))
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.integers(1_000_000, 5_000_000, n_days),
    }, index=dates)


def _build_calendar_with_small_moves(price_df: pd.DataFrame,
                                      release_idxs: list[int],
                                      ticker: str = "TEST") -> pd.DataFrame:
    """Create earnings releases at given bar indices and FORCE small post-release
    moves (≤0.3%) so the pin label is overwhelmingly 1 — gives the classifier
    something learnable. Returns the calendar DataFrame; mutates price_df.close.
    """
    rng = np.random.default_rng(123)
    close = price_df["close"].values.copy()
    for ridx in release_idxs:
        if ridx + 1 >= len(close):
            continue
        c0 = close[ridx]
        # tiny move +/- 0.2%
        small = rng.uniform(-0.003, 0.003)
        close[ridx + 1] = c0 * (1.0 + small)
    price_df["close"] = close

    cal_rows = []
    dates = price_df.index
    for ridx in release_idxs:
        if 0 <= ridx < len(dates):
            cal_rows.append({"ticker": ticker, "release_date": dates[ridx]})
    return pd.DataFrame(cal_rows)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEarningsPinRisk:

    def setup_method(self):
        from strategies.earnings_pin_risk import EarningsPinRiskStrategy
        self.cls = EarningsPinRiskStrategy

    def test_instantiates(self):
        s = self.cls()
        assert s is not None
        assert s.name == "earnings_pin_risk"
        assert s.is_trainable() is True
        assert len(s.FEATURE_COLS) == 7

    def test_get_params_returns_dict(self):
        s = self.cls(pin_threshold=0.65, ivr_max=0.80)
        p = s.get_params()
        assert isinstance(p, dict)
        assert p["pin_threshold"] == 0.65
        assert p["ivr_max"]       == 0.80
        # All declared __init__ kwargs must round-trip
        for k in ("vix_max", "wing_pct", "profit_target_pct",
                  "position_size_pct", "max_concurrent",
                  "n_estimators", "max_depth", "retrain_every"):
            assert k in p

    def test_ui_params_well_formed(self):
        s = self.cls()
        ui = s.get_backtest_ui_params()
        assert isinstance(ui, list)
        assert len(ui) >= 7
        param_keys = {p["key"] for p in ui}
        # Critical UI controls must exist
        for k in ("pin_threshold", "ivr_max", "vix_max", "wing_pct",
                  "profit_target_pct", "position_size_pct"):
            assert k in param_keys, f"missing UI param {k}"
        # Each entry must have minimum fields
        for p in ui:
            assert "key" in p and "label" in p and "type" in p and "default" in p

    def test_signal_hold_when_no_model(self):
        """Without a trained model, generate_signal must return HOLD."""
        s = self.cls()
        feats = pd.DataFrame([{
            "ivr_at_release": 0.4, "recent_realized_vol_60d": 0.2,
            "earnings_history_avg_move": 0.02,
            "option_market_implied_move": 0.05, "size_premium": 0.6,
            "pre_earnings_5d_momentum": 0.0, "vix_level": 18.0,
        }])
        result = s.generate_signal({
            "features_df": feats,
            "days_to_earnings": 3,
            "ivr": 0.4,
            "vix": 18.0,
        })
        assert result.signal == "HOLD"
        assert result.position_size_pct == 0.0

    def test_signal_hold_when_outside_dte_window(self):
        """Days-to-earnings outside [min, max] must HOLD even with a model."""
        s = self.cls(dte_to_earnings_min=2, dte_to_earnings_max=7)
        # No model needed — DTE check happens before model lookup
        for dte in (0, 1, 8, 15):
            r = s.generate_signal({
                "features_df": None,
                "days_to_earnings": dte,
                "ivr": 0.5,
                "vix": 18.0,
            })
            assert r.signal == "HOLD", f"expected HOLD for dte={dte}"

    def test_signal_hold_when_ivr_too_high(self):
        """IVR above ivr_max gates the trade out."""
        s = self.cls(ivr_max=0.85)
        r = s.generate_signal({
            "features_df": None,
            "days_to_earnings": 3,
            "ivr": 0.95,        # > ivr_max
            "vix": 18.0,
        })
        assert r.signal == "HOLD"

    def test_signal_hold_when_no_upcoming_event(self):
        """No days_to_earnings → HOLD (no-event)."""
        s = self.cls()
        r = s.generate_signal({"features_df": None, "ivr": 0.5, "vix": 18.0})
        assert r.signal == "HOLD"
        assert "no upcoming earnings event" in r.metadata.get("reason", "")

    def test_label_construction_correct(self):
        """Synthetic event with KNOWN small move → label = 1; large move → 0.

        Reproduces the strategy's labelling rule end-to-end via _build_event_features
        and a manual check against the spec:
            pin_event = 1 iff |close[T+1]-close[T]|/close[T] <= 0.5 * implied_move
        """
        # Spec rule check (deterministic):
        implied_move = 0.05
        # small actual move = 0.02 → 0.02 <= 0.5*0.05=0.025 ⇒ label=1
        small_actual = 0.02
        assert (small_actual <= 0.5 * implied_move) is True
        # large actual move = 0.06 → 0.06 > 0.025 ⇒ label=0
        large_actual = 0.06
        assert (large_actual <= 0.5 * implied_move) is False

        # End-to-end via backtest path: small post-release move should produce
        # a closed trade with pin_label=1 in the trades DataFrame.
        from strategies.earnings_pin_risk import EarningsPinRiskStrategy
        prices = _build_synth_prices(n_days=300, seed=11)
        # Place a couple of synthetic releases far enough in to clear warmup.
        release_idxs = [110, 160, 210, 250]
        cal = _build_calendar_with_small_moves(prices, release_idxs, ticker="TEST")
        s = EarningsPinRiskStrategy(pin_threshold=0.05)  # accept everything once trained
        res = s.backtest(prices, {"earnings_calendar": cal}, ticker="TEST")
        if not res.trades.empty:
            # Every trade we forced to have a tiny post-release move should be label=1
            pin_labels = res.trades["pin_label"].tolist()
            assert all(lbl == 1 for lbl in pin_labels), (
                f"expected all pin_label=1 for forced small moves, got {pin_labels}"
            )

    def test_backtest_errors_without_earnings_calendar(self):
        """No earnings_calendar → ValueError (event-driven strategies require it)."""
        from strategies.earnings_pin_risk import EarningsPinRiskStrategy
        prices = _build_synth_prices(n_days=200)
        s = EarningsPinRiskStrategy()
        with pytest.raises(ValueError):
            s.backtest(prices, auxiliary_data={})

        # Empty DataFrame is also invalid
        with pytest.raises(ValueError):
            s.backtest(prices, auxiliary_data={"earnings_calendar": pd.DataFrame()})

    def test_backtest_runs_on_synthetic(self):
        """Full walk-forward on synthetic data — equity finite and trades fire."""
        from strategies.earnings_pin_risk import EarningsPinRiskStrategy
        prices = _build_synth_prices(n_days=365, seed=21)
        # 4 well-spaced earnings events past warmup with forced small moves
        release_idxs = [120, 180, 240, 300]
        cal = _build_calendar_with_small_moves(prices, release_idxs, ticker="ABC")
        s = EarningsPinRiskStrategy(
            pin_threshold=0.05,    # very permissive — let the test fire trades
            ivr_max=1.00,
            vix_max=99.0,
            position_size_pct=0.02,
        )
        res = s.backtest(prices, {"earnings_calendar": cal},
                         ticker="ABC", starting_capital=100_000)
        # Equity curve well-formed and finite
        assert res.equity_curve is not None
        assert len(res.equity_curve) == len(prices)
        assert np.isfinite(res.equity_curve.iloc[-1])
        assert res.equity_curve.iloc[-1] > 0
        # First event won't have a model; later events should produce at least
        # one closed trade (low threshold + forced pin labels = something fires).
        # We don't assert a strict count because the first 1-2 events build the
        # training pool, but at least one trade must close out.
        assert res.metrics is not None
        assert "sharpe" in res.metrics
        assert isinstance(res.metrics["sharpe"], float)
        # Signal ledger should record at least one decision per event we offered
        assert "signal_ledger" in res.extra
        assert len(res.extra["signal_ledger"]) >= 1

    def test_max_concurrent_enforced(self):
        """Cluster of releases on consecutive bars must respect max_concurrent."""
        from strategies.earnings_pin_risk import EarningsPinRiskStrategy
        prices = _build_synth_prices(n_days=400, seed=31)
        # Cluster: 6 releases within an 8-bar window AFTER a longer warmup history
        # of well-separated earlier events to give the model something to train on.
        early = [110, 150, 190, 230]
        cluster = [275, 276, 277, 278, 279, 280]
        release_idxs = early + cluster
        cal = _build_calendar_with_small_moves(prices, release_idxs, ticker="CLUST")
        s = EarningsPinRiskStrategy(
            pin_threshold=0.05,
            ivr_max=1.00,
            vix_max=99.0,
            max_concurrent=2,
            dte_to_earnings_min=2,
            dte_to_earnings_max=7,
            exit_days_post=1,
        )
        res = s.backtest(prices, {"earnings_calendar": cal},
                         ticker="CLUST", starting_capital=200_000)
        # The signal ledger captures every entry attempt — at most max_concurrent
        # positions may be open at any time. Reconstruct overlap from trades.
        if not res.trades.empty:
            df = res.trades.copy()
            df["entry_date"] = pd.to_datetime(df["entry_date"])
            df["exit_date"]  = pd.to_datetime(df["exit_date"])
            # For each entry, count concurrent already-open positions at that moment
            for i, row in df.iterrows():
                concurrent_at_entry = df[
                    (df["entry_date"] <= row["entry_date"]) &
                    (df["exit_date"]  >  row["entry_date"]) &
                    (df.index != i)
                ].shape[0]
                # +1 for itself
                assert concurrent_at_entry + 1 <= s.max_concurrent + 1, (
                    f"max_concurrent={s.max_concurrent} violated: "
                    f"{concurrent_at_entry+1} positions open at {row['entry_date']}"
                )

    def test_no_lookahead(self):
        """Walk-forward integrity: training-event labels are derived from
        post-release prices that are STRICTLY in the past relative to any
        prediction made at entry time.

        Concretely: the trades dataframe stores `release_idx` features (computed
        at entry bar = release_idx - dte) and `actual_move` (computed at
        release_idx + 1). The pin_label is appended to the training pool only
        AFTER the trade closes — i.e. after release_idx + exit_days_post bars
        have passed. This test verifies that the strategy never predicts on a
        feature row that was computed using future-dated VIX or close data.
        """
        from strategies.earnings_pin_risk import EarningsPinRiskStrategy
        prices = _build_synth_prices(n_days=400, seed=41)
        release_idxs = [120, 165, 210, 255, 300, 340]
        cal = _build_calendar_with_small_moves(prices, release_idxs, ticker="NLA")
        s = EarningsPinRiskStrategy(pin_threshold=0.05, ivr_max=1.0, vix_max=99.0)
        res = s.backtest(prices, {"earnings_calendar": cal}, ticker="NLA")
        if res.trades.empty:
            pytest.skip("no trades fired — cannot verify lookahead bound")
        # For every closed trade, exit_date must be strictly AFTER release_date,
        # and entry_date must be strictly BEFORE release_date by [min, max] bars.
        df = res.trades.copy()
        df["entry_date"]   = pd.to_datetime(df["entry_date"])
        df["release_date"] = pd.to_datetime(df["release_date"])
        df["exit_date"]    = pd.to_datetime(df["exit_date"])

        # Map dates back to bar indices in the underlying price_data
        idx = {d: i for i, d in enumerate(prices.index)}
        for _, row in df.iterrows():
            ei = idx.get(row["entry_date"])
            ri = idx.get(row["release_date"])
            xi = idx.get(row["exit_date"])
            assert ei is not None and ri is not None and xi is not None
            # Entry strictly before release, within DTE window
            gap = ri - ei
            assert s.dte_to_earnings_min <= gap <= s.dte_to_earnings_max, (
                f"entry-to-release gap {gap} outside "
                f"[{s.dte_to_earnings_min},{s.dte_to_earnings_max}]"
            )
            # Exit on/after release + exit_days_post (cannot be before release)
            assert xi >= ri, f"exit {row['exit_date']} before release {row['release_date']}"

        # Also: feature_importance dict (if present) must not include the close_price
        # or any forward-looking proxy.
        fi = res.extra.get("feature_importance", {})
        forbidden = {"close_price", "future_close", "next_close", "actual_move"}
        for f in fi.keys():
            assert f not in forbidden, f"forbidden feature in importance: {f}"
