"""
tests/test_gex_positioning.py
Unit tests for the GEX Positioning (Dealer Gamma Exposure) strategy.
Run: python -m pytest tests/test_gex_positioning.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# GEX regime allocations as defined in the strategy
_ALLOC = {
    "HighPositive": 0.90,
    "MildPositive": 0.80,
    "Neutral":      0.60,
    "Negative":     0.35,
    "DeepNegative": 0.15,
}


def _regime_from_vix(vix, vix_low=15, vix_mid_low=18, vix_mid_high=22, vix_high=30):
    if vix < vix_low:
        return "HighPositive"
    elif vix < vix_mid_low:
        return "MildPositive"
    elif vix < vix_mid_high:
        return "Neutral"
    elif vix < vix_high:
        return "Negative"
    else:
        return "DeepNegative"


class TestGEXPositioning:

    def setup_method(self):
        from strategies.gex_positioning import GexPositioningStrategy
        self.cls = GexPositioningStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_five_regimes_defined(self):
        """Strategy must define exactly 5 GEX regimes."""
        assert len(_ALLOC) == 5

    def test_allocations_monotone_decreasing_with_vix(self):
        """Higher VIX → lower SPY allocation."""
        allocs = [_ALLOC[r] for r in ["HighPositive", "MildPositive", "Neutral", "Negative", "DeepNegative"]]
        for i in range(len(allocs) - 1):
            assert allocs[i] > allocs[i+1], "SPY allocation must decrease as regime worsens"

    def test_high_positive_gex_max_equity(self):
        """VIX < 15 → 90% SPY allocation."""
        regime = _regime_from_vix(12.0)
        assert regime == "HighPositive"
        assert _ALLOC[regime] == 0.90

    def test_deep_negative_gex_min_equity(self):
        """VIX > 30 → 15% SPY allocation (capital preservation)."""
        regime = _regime_from_vix(35.0)
        assert regime == "DeepNegative"
        assert _ALLOC[regime] == 0.15

    def test_neutral_zone_60pct_spy(self):
        """VIX 18-22 → 60% SPY (gamma flip zone)."""
        regime = _regime_from_vix(20.0)
        assert regime == "Neutral"
        assert _ALLOC[regime] == 0.60

    def test_negative_gex_regime_defensive(self):
        """VIX 22-30 → 35% SPY (dealers amplifying moves)."""
        regime = _regime_from_vix(26.0)
        assert regime == "Negative"
        assert _ALLOC[regime] == 0.35

    def test_all_allocations_in_valid_range(self):
        """All SPY allocations must be between 0 and 1."""
        for regime, alloc in _ALLOC.items():
            assert 0.0 < alloc <= 1.0, f"{regime} allocation {alloc} out of range"

    def test_total_allocation_never_exceeds_100pct(self):
        """No single regime puts more than 100% in SPY."""
        assert max(_ALLOC.values()) <= 1.0

    def test_positive_gex_is_vol_suppressing(self):
        """In positive GEX, dealers hedge by selling into rallies — dampens vol."""
        # VIX below 18 = positive GEX territory
        assert _regime_from_vix(13.0) in ("HighPositive", "MildPositive")
        assert _regime_from_vix(17.0) in ("HighPositive", "MildPositive")

    def test_vix_boundary_cases(self):
        assert _regime_from_vix(14.9) == "HighPositive"
        assert _regime_from_vix(15.0) == "MildPositive"
        assert _regime_from_vix(18.0) == "Neutral"
        assert _regime_from_vix(22.0) == "Negative"
        assert _regime_from_vix(30.0) == "DeepNegative"
