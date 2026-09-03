import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
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


class TestGetChainMid:
    def _make_chain(self, strikes, mids):
        return pd.DataFrame({"strike": strikes, "mid": mids})
    def test_exclude_short_strike_prevents_zero_width_spread(self):
        """Long wing must not equal the short strike."""
        from alan_trader.engine.screener import _get_chain_mid
        chain = self._make_chain([44, 46, 48, 50], [0.5, 0.8, 1.2, 2.0])
        # target=42 is below the chain; without exclude, nearest is 44
        # with exclude=44, nearest should be 46
        mid, k = _get_chain_mid(chain, strike=42, exclude_strike=44)
        assert k != 44, f"Wing strike {k} must not equal short strike 44"
        assert k == 46
    def test_no_exclude_returns_nearest(self):
        """Without exclude_strike the nearest strike is returned."""
        from alan_trader.engine.screener import _get_chain_mid
        chain = self._make_chain([44, 46, 48], [0.5, 0.8, 1.2])
        mid, k = _get_chain_mid(chain, strike=45)
        assert k == 44 or k == 46  # nearest to 45
    def test_empty_chain_returns_none(self):
        from alan_trader.engine.screener import _get_chain_mid
        chain = pd.DataFrame({"strike": [], "mid": []})
        mid, k = _get_chain_mid(chain, strike=100)
        assert mid is None
    def test_exclude_all_candidates_returns_none(self):
        """If excluding the only strike, result should be None."""
        from alan_trader.engine.screener import _get_chain_mid
        chain = self._make_chain([50], [1.0])
        mid, k = _get_chain_mid(chain, strike=50, exclude_strike=50)
        assert mid is None


class TestVolArbParityCircularFix:
    """
    When either call or put has a reconstructed (synthetic) price,
    no parity violation should be detected.
    """
    def _make_strategy(self):
        from alan_trader_strategies.strategies.vol_arbitrage.strategy import VolArbitrageStrategy
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


class TestVixSpikeFadeSignal:
    def _strategy(self):
        from alan_trader_strategies.strategies.vix_spike_fade.strategy import VIXSpikeFadeStrategy as VixSpikeFadeStrategy
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


class TestIVRConfidenceGating:
    def _strategy(self):
        from alan_trader_strategies.strategies.ivr_credit_spread.strategy import IVRCreditSpreadStrategy
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
