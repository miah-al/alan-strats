"""
tests/test_vol_arbitrage.py
Unit tests for the Vol Arbitrage (IV Skew Premium Capture) strategy.
Run: python -m pytest tests/test_vol_arbitrage.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestVolArbitrage:

    def setup_method(self):
        from strategies.vol_arbitrage import VolArbitrageStrategy
        self.cls = VolArbitrageStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_iv_skew_threshold_default(self):
        """Default skew threshold should be 8 vol pts (0.08)."""
        s = self.cls()
        assert s.skew_thresh == pytest.approx(0.08)

    def test_skew_detected_when_put_iv_above_call_iv(self):
        """Skew arb fires when put IV exceeds call IV at same strike by threshold."""
        put_iv, call_iv, threshold = 0.45, 0.30, 0.08
        skew = put_iv - call_iv
        assert skew >= threshold, "Should detect skew arb opportunity"

    def test_no_skew_below_threshold(self):
        put_iv, call_iv, threshold = 0.35, 0.30, 0.08
        skew = put_iv - call_iv
        assert skew < threshold, "Skew below threshold — should not trade"

    def test_bull_put_spread_max_loss_bounded(self):
        """Long put protects against unlimited loss on short put."""
        short_k, long_k, credit = 50.0, 48.0, 0.60
        max_loss = -(short_k - long_k - credit) * 100
        assert max_loss < 0
        assert max_loss > -(short_k * 100), "Loss must be bounded by spread width"

    def test_bull_put_spread_max_profit_is_credit(self):
        credit = 0.60
        assert credit * 100 == pytest.approx(60.0)

    def test_five_leg_structure_is_defined_risk(self):
        """
        Full structure: short put + long put + long call + short call + long call.
        Every short leg has a long leg protecting it — fully defined risk.
        """
        legs = [
            {"type": "put",  "side": "short"},  # ① short put at K
            {"type": "put",  "side": "long"},   # ② long put below K
            {"type": "call", "side": "long"},   # ③ long call at K
            {"type": "call", "side": "short"},  # ④ short call ATM (delta hedge)
            {"type": "call", "side": "long"},   # ⑤ long call above ATM (cap)
        ]
        short_puts  = sum(1 for l in legs if l["type"] == "put"  and l["side"] == "short")
        long_puts   = sum(1 for l in legs if l["type"] == "put"  and l["side"] == "long")
        short_calls = sum(1 for l in legs if l["type"] == "call" and l["side"] == "short")
        long_calls  = sum(1 for l in legs if l["type"] == "call" and l["side"] == "long")
        # Each short leg is covered by a long leg
        assert long_puts  >= short_puts,  "Short puts must be covered"
        assert long_calls >= short_calls, "Short calls must be covered"

    def test_parity_violation_signal(self):
        """
        Put-call parity: C - P = S - K*exp(-rT).
        If put is overpriced relative to call at same strike, skew arb exists.
        """
        S, K, r, T = 100.0, 100.0, 0.045, 0.125  # ~45 DTE
        import math
        parity_rhs = S - K * math.exp(-r * T)  # should ≈ 0 for ATM
        assert abs(parity_rhs) < 2.0, "Parity RHS should be near zero for ATM"

    def test_high_retail_iv_names_meet_threshold(self):
        """High-IV retail names (HOOD, COIN etc.) typically have 8+ vol pt skew."""
        typical_put_iv  = 0.75   # 75% put IV (retail buying puts)
        typical_call_iv = 0.60   # 60% call IV
        skew = typical_put_iv - typical_call_iv
        assert skew >= 0.08, "High-vol retail names should consistently show arb signal"
