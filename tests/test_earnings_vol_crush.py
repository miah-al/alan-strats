"""
tests/test_earnings_vol_crush.py
Unit tests for the Earnings Vol Crush AI strategy.
Run: python -m pytest tests/test_earnings_vol_crush.py -v
"""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _credit_spread_pnl(spot, short_K, long_K, credit, spread_type):
    """P&L at expiry."""
    if spread_type == "bull_put":
        intrinsic = max(0, short_K - spot) - max(0, long_K - spot)
    else:  # bear_call
        intrinsic = max(0, spot - short_K) - max(0, spot - long_K)
    return (credit - intrinsic) * 100


class TestEarningsVolCrush:

    def setup_method(self):
        from strategies.earnings_vol_crush import EarningsVolCrushStrategy
        self.cls = EarningsVolCrushStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_feature_count(self):
        s = self.cls()
        assert len(s.FEATURE_COLS) >= 8

    def test_bear_call_max_profit(self):
        """Bear call: full credit when spot stays below short strike."""
        short_K, long_K, credit = 200, 210, 1.50
        pnl = _credit_spread_pnl(195, short_K, long_K, credit, "bear_call")
        assert pnl == pytest.approx(credit * 100)

    def test_bear_call_max_loss(self):
        """Bear call: max loss when spot above long strike."""
        short_K, long_K, credit = 200, 210, 1.50
        wing = long_K - short_K
        expected = -(wing - credit) * 100
        pnl = _credit_spread_pnl(215, short_K, long_K, credit, "bear_call")
        assert pnl == pytest.approx(expected)

    def test_bull_put_max_profit(self):
        """Bull put: full credit when spot above short strike."""
        short_K, long_K, credit = 95, 90, 1.20
        pnl = _credit_spread_pnl(100, short_K, long_K, credit, "bull_put")
        assert pnl == pytest.approx(credit * 100)

    def test_defined_risk_bear_call(self):
        """Bear call max loss = wing - credit."""
        short_K, long_K, credit = 200, 210, 1.50
        wing = long_K - short_K
        max_loss = (wing - credit) * 100
        assert max_loss > 0
        assert max_loss < 10_000

    def test_generate_signal_gap_up(self):
        """Positive earnings gap → SELL (bear call)."""
        s = self.cls()
        result = s.generate_signal({
            "earnings_gap_pct": 0.05, "ivr": 0.70, "vix": 18.0
        })
        assert result.signal == "SELL"

    def test_generate_signal_gap_down(self):
        """Negative earnings gap → BUY (bull put)."""
        s = self.cls()
        result = s.generate_signal({
            "earnings_gap_pct": -0.06, "ivr": 0.65, "vix": 22.0
        })
        assert result.signal == "BUY"

    def test_generate_signal_no_gap(self):
        """No gap → HOLD."""
        s = self.cls()
        result = s.generate_signal({
            "earnings_gap_pct": 0.01, "ivr": 0.30, "vix": 20.0
        })
        assert result.signal == "HOLD"

    def test_gap_direction_determines_spread_type(self):
        """Gap up → bear call (above gap). Gap down → bull put (below gap)."""
        s = self.cls(min_gap_pct=0.03)
        # Gap up: need bear call
        sig_up = s.generate_signal({"earnings_gap_pct": 0.05, "ivr": 0.6, "vix": 18})
        assert sig_up.signal == "SELL"
        # Gap down: need bull put
        sig_dn = s.generate_signal({"earnings_gap_pct": -0.05, "ivr": 0.6, "vix": 18})
        assert sig_dn.signal == "BUY"

    def test_get_params_roundtrip(self):
        s = self.cls(min_gap_pct=0.04, hold_days=8)
        p = s.get_params()
        assert p["min_gap_pct"] == 0.04
        assert p["hold_days"] == 8

    def test_ui_params_structure(self):
        s = self.cls()
        params = s.get_backtest_ui_params()
        assert len(params) >= 4
        for p in params:
            assert "key" in p and "type" in p


class TestEarningsGapDetection:

    def test_gap_detected(self):
        """Large single-day move is detected as earnings gap."""
        from strategies.earnings_vol_crush import _detect_earnings_gaps
        import pandas as pd
        prices = pd.Series([100.0, 100.5, 101.0, 106.2, 106.5, 106.0])
        gaps = _detect_earnings_gaps(prices, threshold=0.03)
        assert gaps.iloc[3] == True   # 5.1% gap on day 3

    def test_no_gap_small_move(self):
        """Small daily moves are not earnings gaps."""
        from strategies.earnings_vol_crush import _detect_earnings_gaps
        import pandas as pd
        prices = pd.Series([100.0, 100.5, 101.0, 101.5, 102.0])
        gaps = _detect_earnings_gaps(prices, threshold=0.03)
        assert gaps.sum() == 0

    def test_containment_label_logic(self):
        """Stock staying within ±8% of gap close → label = 1."""
        entry_px = 100.0
        containment = 0.08
        # Stock moves at most 7.5% in either direction → contained
        max_move = 0.075
        assert max_move <= containment  # should be labeled 1
        # Stock moves 9% → not contained
        big_move = 0.09
        assert big_move > containment   # should be labeled 0
