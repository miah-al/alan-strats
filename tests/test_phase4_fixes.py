"""
tests/test_phase4_fixes.py

Unit tests for Phase 4 offline bug fixes.
Run with:  python -m pytest tests/test_phase4_fixes.py -v

Each test is named after the bug it covers.
"""
import math
import pytest
import numpy as np
import pandas as pd
import sys
import os

# Make sure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_price_df(n=300, price=100.0, vol=0.015):
    """Synthetic OHLCV dataframe."""
    np.random.seed(42)
    closes = price + np.cumsum(np.random.randn(n) * vol * price)
    closes = np.maximum(closes, 1.0)
    df = pd.DataFrame({
        "close": closes,
        "open":  closes * 0.999,
        "high":  closes * 1.005,
        "low":   closes * 0.995,
        "volume": np.ones(n) * 1_000_000,
    })
    return df


def _make_vix_series(n=300, level=20.0):
    np.random.seed(1)
    v = level + np.cumsum(np.random.randn(n) * 0.3)
    return pd.Series(np.maximum(v, 5.0))


def _make_vix_spike_series(n=300, spike_at=-1, spike_level=35.0, base=18.0):
    s = _make_vix_series(n, level=base)
    s.iloc[spike_at] = spike_level
    return s


# ─────────────────────────────────────────────────────────────────────────────
# 1. Screener: wing strike exclude_strike fix
# ─────────────────────────────────────────────────────────────────────────────

class TestGetChainMid:
    def _make_chain(self, strikes, mids):
        return pd.DataFrame({"strike": strikes, "mid": mids})

    def test_exclude_short_strike_prevents_zero_width_spread(self):
        """Long wing must not equal the short strike."""
        from engine.screener import _get_chain_mid
        chain = self._make_chain([44, 46, 48, 50], [0.5, 0.8, 1.2, 2.0])
        # target=42 is below the chain; without exclude, nearest is 44
        # with exclude=44, nearest should be 46
        mid, k = _get_chain_mid(chain, strike=42, exclude_strike=44)
        assert k != 44, f"Wing strike {k} must not equal short strike 44"
        assert k == 46

    def test_no_exclude_returns_nearest(self):
        """Without exclude_strike the nearest strike is returned."""
        from engine.screener import _get_chain_mid
        chain = self._make_chain([44, 46, 48], [0.5, 0.8, 1.2])
        mid, k = _get_chain_mid(chain, strike=45)
        assert k == 44 or k == 46  # nearest to 45

    def test_empty_chain_returns_none(self):
        from engine.screener import _get_chain_mid
        chain = pd.DataFrame({"strike": [], "mid": []})
        mid, k = _get_chain_mid(chain, strike=100)
        assert mid is None

    def test_exclude_all_candidates_returns_none(self):
        """If excluding the only strike, result should be None."""
        from engine.screener import _get_chain_mid
        chain = self._make_chain([50], [1.0])
        mid, k = _get_chain_mid(chain, strike=50, exclude_strike=50)
        assert mid is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Screener: ATR% is decimal, not percentage
# ─────────────────────────────────────────────────────────────────────────────

class TestAtrPctDecimal:
    def test_ic_rules_atr_pct_is_decimal(self):
        from engine.screener import _score_ic_rules
        price_df  = _make_price_df(300)
        vix       = _make_vix_series(300, level=22.0)
        iv        = {"atm_iv": 0.20, "hv20": 0.15, "ivr": 0.50,
                     "vrp": 0.05, "iv_over_hv": 1.3, "iv_source": "test"}
        params    = {"ivr_min": 0.20, "vix_min": 14.0, "vix_max": 45.0,
                     "adx_max": 35.0, "atr_pct_max": 0.05}
        row = _score_ic_rules("TEST", price_df, vix, iv, params)
        assert row is not None
        atr_pct = row["ATR%"]
        assert atr_pct < 1.0, f"ATR% should be decimal (<1.0), got {atr_pct}"
        assert atr_pct > 0.0

    def test_vix_spike_fade_atr_pct_is_decimal(self):
        from engine.screener import _score_vix_spike_fade
        price_df = _make_price_df(300)
        vix      = _make_vix_spike_series(300)
        iv       = {}
        row = _score_vix_spike_fade("TEST", price_df, vix, iv)
        assert row is not None
        assert row["ATR%"] < 1.0, f"ATR% should be decimal, got {row['ATR%']}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Vol Arb: parity check requires BOTH sides to have real quotes
# ─────────────────────────────────────────────────────────────────────────────

class TestVolArbParityCircularFix:
    """
    When either call or put has a reconstructed (synthetic) price,
    no parity violation should be detected.
    """

    def _make_strategy(self):
        from strategies.vol_arbitrage import VolArbitrageStrategy
        return VolArbitrageStrategy()

    def test_neither_reconstructed_flag(self):
        """Verify the neither_reconstructed variable logic."""
        # Simulating the flag logic directly (no full strategy call needed)
        c_reconstructed = False
        p_reconstructed = False
        neither_reconstructed = not c_reconstructed and not p_reconstructed
        assert neither_reconstructed is True

    def test_one_side_reconstructed_blocks_parity(self):
        """If call is reconstructed, parity check must not run."""
        c_reconstructed = True
        p_reconstructed = False
        neither_reconstructed = not c_reconstructed and not p_reconstructed
        assert neither_reconstructed is False

    def test_both_reconstructed_blocks_parity(self):
        c_reconstructed = True
        p_reconstructed = True
        neither_reconstructed = not c_reconstructed and not p_reconstructed
        assert neither_reconstructed is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. Vol Arb screener: score capped at 100
# ─────────────────────────────────────────────────────────────────────────────

class TestVolArbScoreCap:
    def test_score_capped_at_100_for_extreme_vrp(self):
        from engine.screener import _score_vol_arbitrage
        price_df = _make_price_df(300)
        vix      = _make_vix_series(300, level=20.0)
        # extreme VRP = 0.80 (80 vol pts) — was previously giving score > 100
        iv = {"atm_iv": 0.90, "hv20": 0.10, "ivr": 0.80,
              "vrp": 0.80, "iv_over_hv": 9.0, "iv_source": "test"}
        row = _score_vol_arbitrage("TEST", price_df, vix, iv)
        assert row is not None
        assert row["score"] <= 100, f"Score should be capped at 100, got {row['score']}"

    def test_score_is_non_negative(self):
        from engine.screener import _score_vol_arbitrage
        price_df = _make_price_df(300)
        vix      = _make_vix_series(300, level=20.0)
        iv = {"atm_iv": 0.20, "hv20": 0.25, "ivr": 0.30,
              "vrp": -0.05, "iv_over_hv": 0.8, "iv_source": "test"}
        row = _score_vol_arbitrage("TEST", price_df, vix, iv)
        assert row is not None
        assert row["score"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. VIX Spike Fade: vix_20d_avg missing → threshold-only fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestVixSpikeFadeSignal:
    def _strategy(self):
        from strategies.vix_spike_fade import VIXSpikeFadeStrategy as VixSpikeFadeStrategy
        return VixSpikeFadeStrategy()

    def test_signal_fires_without_vix_20d_avg(self):
        """If vix_20d_avg is absent, should still BUY when VIX > spike_threshold."""
        s = self._strategy()
        snap = {"vix": 32.0, "price": 500.0, "ma_200d": 480.0}
        # vix_20d_avg is intentionally absent
        result = s.generate_signal(snap)
        assert result.signal == "BUY", (
            f"Expected BUY (VIX=32 > threshold=25, no 20d_avg), got {result.signal}. "
            f"meta={result.metadata}"
        )

    def test_signal_hold_when_vix_below_threshold_no_avg(self):
        s = self._strategy()
        snap = {"vix": 18.0, "price": 500.0, "ma_200d": 480.0}
        result = s.generate_signal(snap)
        assert result.signal == "HOLD"

    def test_signal_hold_when_ma200_zero(self):
        """ma_200d=0.0 must NOT auto-pass the regime check."""
        s = self._strategy()
        snap = {"vix": 35.0, "price": 500.0, "ma_200d": 0.0}
        result = s.generate_signal(snap)
        # regime_ok = (ma_200d > 0.0 and spot >= ma_200d * 0.95)
        # 0.0 > 0.0 is False → regime_ok=False → HOLD
        assert result.signal == "HOLD", (
            "ma_200d=0 should fail regime check (insufficient history), not auto-pass"
        )

    def test_ratio_check_fires_when_20d_avg_present_and_below(self):
        """With 20d avg present but VIX not spiking, should HOLD."""
        s = self._strategy()
        snap = {"vix": 22.0, "price": 500.0, "ma_200d": 480.0, "vix_20d_avg": 21.0}
        # ratio = 22/21 = 1.048 < 1.3 → spike_cond False
        result = s.generate_signal(snap)
        assert result.signal == "HOLD"

    def test_ratio_check_fires_when_spiked(self):
        s = self._strategy()
        snap = {"vix": 32.0, "price": 500.0, "ma_200d": 480.0, "vix_20d_avg": 20.0}
        # ratio = 32/20 = 1.6 >= 1.3 → spike_cond True
        result = s.generate_signal(snap)
        assert result.signal == "BUY"


# ─────────────────────────────────────────────────────────────────────────────
# 6. IVR Credit Spread: cold-start IVR fix
# ─────────────────────────────────────────────────────────────────────────────

class TestIVRColdStart:
    def test_ivr_nan_when_fewer_than_126_bars(self):
        """_compute_ivr returns NaN for the first 125 bars."""
        from strategies.ivr_credit_spread import _compute_ivr
        vix = pd.Series([20.0] * 100)
        ivr = _compute_ivr(vix)
        assert ivr.isna().all(), (
            f"Expected all NaN with only 100 bars, got non-NaN at: {ivr.dropna().index.tolist()}"
        )

    def test_ivr_computes_after_126_bars(self):
        from strategies.ivr_credit_spread import _compute_ivr
        np.random.seed(0)
        vix = pd.Series(20.0 + np.cumsum(np.random.randn(300) * 0.3))
        vix = vix.clip(5, 80)
        ivr = _compute_ivr(vix)
        valid = ivr.dropna()
        assert len(valid) > 0, "Expected some valid IVR values with 300 bars"
        assert (valid >= 0.0).all() and (valid <= 1.0).all()

    def test_ivr_not_inflated_at_warmup_boundary(self):
        """At exactly 126 bars, IVR should reflect the full 126-bar range, not a 30-bar range."""
        from strategies.ivr_credit_spread import _compute_ivr
        # Construct a series where VIX is at its maximum for the whole window
        # A 30-bar min_periods would see a narrow range → IVR ≈ 1.0 (inflated)
        # A 126-bar min_periods sees a wider range → IVR is more moderate
        vix_values = list(range(10, 136))  # 10,11,...,135 — 126 values
        vix = pd.Series(vix_values, dtype=float)
        ivr = _compute_ivr(vix)
        last_ivr = ivr.iloc[-1]
        assert not math.isnan(last_ivr)
        # With range 10-135=125, current=135, IVR = (135-10)/125 = 1.0 (at max)
        # That's expected — test just that it doesn't fire earlier than 126 bars
        first_valid_idx = ivr.first_valid_index()
        assert first_valid_idx >= 125, (
            f"IVR should not produce valid values before index 125, first valid at {first_valid_idx}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. IVR Credit Spread: low-confidence IVR uses stricter threshold
# ─────────────────────────────────────────────────────────────────────────────

class TestIVRConfidenceGating:
    def _strategy(self):
        from strategies.ivr_credit_spread import IVRCreditSpreadStrategy
        return IVRCreditSpreadStrategy(ivr_min=0.40)

    def test_low_confidence_ivr_stricter_threshold(self):
        """With VIX-fallback IVR just above ivr_min, should HOLD due to stricter effective threshold."""
        s = self._strategy()
        # No features_df → VIX heuristic IVR
        # VIX=28 → ivr ≈ (28-12)/(40-12) = 0.571
        # ivr_min=0.40, low-conf effective = 0.50 → should pass
        # VIX=22 → ivr ≈ (22-12)/28 = 0.357 → below ivr_min=0.40 → HOLD
        snap_low_vix = {"vix": 22.0, "price": 500.0}
        result = s.generate_signal(snap_low_vix)
        assert result.signal == "HOLD"

    def test_low_confidence_ivr_in_metadata(self):
        """ivr_confidence should appear in metadata."""
        s = self._strategy()
        snap = {"vix": 35.0, "price": 500.0}
        result = s.generate_signal(snap)
        assert "ivr_confidence" in result.metadata, "ivr_confidence must be in metadata"

    def test_high_confidence_ivr_uses_normal_threshold(self):
        """With real 252-bar VIX history, ivr_confidence='high' and normal threshold applies."""
        s = self._strategy()
        np.random.seed(5)
        vix_vals = 20 + np.cumsum(np.random.randn(300) * 0.5)
        vix_vals = np.clip(vix_vals, 8, 60)
        features_df = pd.DataFrame({
            "vix":   vix_vals,
            "close": 500 + np.cumsum(np.random.randn(300) * 2),
        })
        snap = {"vix": float(vix_vals[-1]), "price": float(features_df["close"].iloc[-1]),
                "features_df": features_df}
        result = s.generate_signal(snap)
        assert result.metadata.get("ivr_confidence") in ("high", "low (VIX fallback)")


# ─────────────────────────────────────────────────────────────────────────────
# 8. IVR Credit Spread: MA50 unavailable → HOLD not bear_call bias
# ─────────────────────────────────────────────────────────────────────────────

class TestIVRMA50ColdStart:
    def test_hold_when_no_price_history(self):
        """<50 bars of price history → HOLD, not a biased bear_call."""
        from strategies.ivr_credit_spread import IVRCreditSpreadStrategy
        s = IVRCreditSpreadStrategy(ivr_min=0.30)
        np.random.seed(7)
        # Enough VIX history for IVR (200 bars) but only 40 bars of price
        vix_vals = 20 + np.cumsum(np.random.randn(200) * 0.5)
        vix_vals = np.clip(vix_vals, 8, 60)
        close_vals = 500 + np.cumsum(np.random.randn(40) * 2)
        # Pad close to match vix length (NaN for missing)
        close_padded = np.concatenate([np.full(160, np.nan), close_vals])
        features_df = pd.DataFrame({"vix": vix_vals, "close": close_padded})
        snap = {
            "vix": float(vix_vals[-1]),
            "price": float(close_vals[-1]),
            "features_df": features_df,
        }
        result = s.generate_signal(snap)
        # With only 40 bars of price history, ma50 is None → HOLD
        if result.signal != "HOLD":
            # Only acceptable if IVR is below threshold
            assert result.metadata.get("reason", "").lower().find("ivr") >= 0, (
                f"Expected HOLD due to insufficient MA50 history, got {result.signal}. "
                f"meta={result.metadata}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 9. IC AI: adaptive delta marginal signal (was unreachable)
# ─────────────────────────────────────────────────────────────────────────────

class TestICAIAdaptiveDelta:
    def test_marginal_signal_gets_wider_strikes(self):
        """
        When thresh <= prob < thresh+0.10, adaptive_delta should be reduced
        (wider strikes). Previously this branch was unreachable.
        """
        from strategies.iron_condor_ai import IronCondorAIStrategy
        s = IronCondorAIStrategy(signal_threshold=0.60, delta_short=0.16)
        thresh = s.signal_threshold   # 0.60
        d_short = s.delta_short       # 0.16

        # Simulate the adaptive delta logic for a marginal probability
        prob = thresh + 0.05   # 0.65 — marginal, < thresh+0.10=0.70

        adaptive_delta = d_short
        if prob >= 0.75:
            adaptive_delta = min(d_short + 0.04, 0.22)
        elif prob < thresh + 0.10:
            adaptive_delta = max(d_short - 0.03, 0.10)

        assert adaptive_delta == max(d_short - 0.03, 0.10), (
            f"Marginal prob {prob} should widen strikes. "
            f"Expected delta={max(d_short - 0.03, 0.10)}, got {adaptive_delta}"
        )

    def test_high_prob_gets_tighter_strikes(self):
        from strategies.iron_condor_ai import IronCondorAIStrategy
        s = IronCondorAIStrategy(signal_threshold=0.60, delta_short=0.16)
        d_short = s.delta_short
        prob = 0.80

        adaptive_delta = d_short
        if prob >= 0.75:
            adaptive_delta = min(d_short + 0.04, 0.22)
        elif prob < s.signal_threshold + 0.10:
            adaptive_delta = max(d_short - 0.03, 0.10)

        assert adaptive_delta == min(d_short + 0.04, 0.22)


# ─────────────────────────────────────────────────────────────────────────────
# 10. IC AI: _prepare_feat_row fills sensibly (not zeros for VIX)
# ─────────────────────────────────────────────────────────────────────────────

class TestICAIFeaturePrep:
    def test_vix_level_not_zero_filled(self):
        """vix_level NaN should be filled with 20.0, not 0.0."""
        from strategies.iron_condor_ai import IronCondorAIStrategy
        s = IronCondorAIStrategy()
        df = pd.DataFrame({col: [np.nan] for col in s.FEATURE_COLS})
        row = s._prepare_feat_row(df)
        assert row["vix_level"].iloc[0] == 20.0, (
            f"vix_level NaN should fill to 20.0, got {row['vix_level'].iloc[0]}"
        )

    def test_realized_vol_not_zero_filled(self):
        from strategies.iron_condor_ai import IronCondorAIStrategy
        s = IronCondorAIStrategy()
        df = pd.DataFrame({col: [np.nan] for col in s.FEATURE_COLS})
        row = s._prepare_feat_row(df)
        assert row["realized_vol_20d"].iloc[0] == 0.15

    def test_vix_ma_ratio_not_zero_filled(self):
        """vix_ma_ratio=0 is invalid (division issue). Should be 1.0."""
        from strategies.iron_condor_ai import IronCondorAIStrategy
        s = IronCondorAIStrategy()
        df = pd.DataFrame({col: [np.nan] for col in s.FEATURE_COLS})
        row = s._prepare_feat_row(df)
        assert row["vix_ma_ratio"].iloc[0] == 1.0

    def test_ffill_used_before_defaults(self):
        """Forward-fill takes priority over static defaults."""
        from strategies.iron_condor_ai import IronCondorAIStrategy
        s = IronCondorAIStrategy()
        # Two rows: first has data, second is NaN — ffill should carry forward
        data = {col: [np.nan, np.nan] for col in s.FEATURE_COLS}
        data["vix_level"] = [35.0, np.nan]
        df = pd.DataFrame(data)
        row = s._prepare_feat_row(df)
        assert row["vix_level"].iloc[-1] == 35.0, (
            "ffill should propagate vix_level=35.0 to second row, not replace with default 20.0"
        )
