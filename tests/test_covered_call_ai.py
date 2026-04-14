"""
tests/test_covered_call_ai.py
Unit tests for the Covered Call Optimizer AI strategy.
Run: python -m pytest tests/test_covered_call_ai.py -v
"""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cc_pnl(entry_px, exit_px, strike, premium):
    """P&L of covered call writer at expiry."""
    if exit_px <= strike:
        return premium + (exit_px - entry_px)   # keep premium + appreciation
    else:
        return premium + (strike - entry_px)    # capped at strike


def _hold_pnl(entry_px, exit_px):
    return exit_px - entry_px


class TestCoveredCallAI:

    def setup_method(self):
        from strategies.covered_call_ai import CoveredCallAIStrategy
        self.cls = CoveredCallAIStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_feature_count(self):
        s = self.cls()
        assert len(s.FEATURE_COLS) >= 8

    def test_cc_wins_flat_market(self):
        """Covered call outperforms holding when stock is flat or slightly up."""
        entry, strike, premium = 100, 105, 1.50
        exit_flat = 103  # stock went up 3%, call not exercised
        cc  = _cc_pnl(entry, exit_flat, strike, premium)
        hold = _hold_pnl(entry, exit_flat)
        assert cc > hold  # premium tips the balance

    def test_cc_loses_strong_rally(self):
        """Covered call caps gain in strong rally — holding wins."""
        entry, strike, premium = 100, 105, 1.50
        exit_rally = 115  # stock rallied 15%
        cc   = _cc_pnl(entry, exit_rally, strike, premium)
        hold = _hold_pnl(entry, exit_rally)
        assert cc < hold  # capped at strike

    def test_cc_wins_declining_market(self):
        """Premium partially offsets stock decline."""
        entry, strike, premium = 100, 105, 1.50
        exit_decline = 94  # stock fell 6%
        cc   = _cc_pnl(entry, exit_decline, strike, premium)
        hold = _hold_pnl(entry, exit_decline)
        assert cc > hold  # premium reduces loss

    def test_cc_max_gain_is_capped(self):
        """Covered call max gain is (strike - entry) + premium."""
        entry, strike, premium = 100, 105, 1.50
        max_gain = (strike - entry) + premium  # 5 + 1.50 = 6.50
        # Stock rallies to 130 — gain capped at 6.50
        pnl_huge = _cc_pnl(entry, 130, strike, premium)
        assert pnl_huge == pytest.approx(max_gain)

    def test_aggressive_vs_conservative_delta(self):
        """Aggressive delta is higher than conservative delta."""
        s = self.cls()
        assert s.aggressive_delta > s.conservative_delta

    def test_generate_signal_high_ivr_low_momentum(self):
        """High IVR + low momentum → BUY (write aggressive call)."""
        s = self.cls()
        result = s.generate_signal({"ivr": 0.65, "ret_20d": 0.01, "vix": 22.0})
        assert result.signal == "BUY"
        assert result.metadata["delta"] == s.aggressive_delta

    def test_generate_signal_low_ivr_skip(self):
        """Low IVR → HOLD (premium not worth capping upside)."""
        s = self.cls()
        result = s.generate_signal({"ivr": 0.15, "ret_20d": 0.02, "vix": 14.0})
        assert result.signal == "HOLD"

    def test_generate_signal_strong_momentum_conservative(self):
        """Strong uptrend + IVR OK → BUY with conservative delta."""
        s = self.cls()
        result = s.generate_signal({"ivr": 0.50, "ret_20d": 0.10, "vix": 16.0})
        assert result.signal == "BUY"
        assert result.metadata["delta"] == s.conservative_delta

    def test_get_params_roundtrip(self):
        s = self.cls(min_ivr=0.35, dte_target=30)
        p = s.get_params()
        assert p["min_ivr"] == 0.35
        assert p["dte_target"] == 30

    def test_ui_params_structure(self):
        s = self.cls()
        params = s.get_backtest_ui_params()
        assert len(params) >= 4
        for p in params:
            assert "key" in p and "type" in p


class TestCCLabelConstruction:

    def setup_method(self):
        from strategies.covered_call_ai import CoveredCallAIStrategy
        self.cls = CoveredCallAIStrategy

    def test_label_cc_wins_flat_scenario(self):
        """CC label = 1 when selling a call outperforms holding."""
        entry_px   = 100.0
        strike     = 105.0
        premium    = 1.50
        exit_flat  = 103.0
        cc_pnl     = _cc_pnl(entry_px, exit_flat, strike, premium)
        hold_pnl_  = _hold_pnl(entry_px, exit_flat)
        label = 1 if cc_pnl >= hold_pnl_ * 0.90 else 0
        assert label == 1

    def test_label_cc_loses_strong_rally(self):
        """CC label = 0 when strong rally makes holding better."""
        entry_px   = 100.0
        strike     = 105.0
        premium    = 1.50
        exit_rally = 120.0
        cc_pnl     = _cc_pnl(entry_px, exit_rally, strike, premium)
        hold_pnl_  = _hold_pnl(entry_px, exit_rally)
        label = 1 if cc_pnl >= hold_pnl_ * 0.90 else 0
        assert label == 0

    def test_earnings_window_proxy(self):
        """If last big gap < 10 days ago, skip writing covered call."""
        s = self.cls()
        days_since = 5  # 5 days since last large move — likely within earnings window
        assert days_since < s.min_days_since_earn  # should skip
