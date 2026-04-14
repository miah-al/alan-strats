"""
tests/test_put_steal.py
Unit tests for the Put Steal (Short Stock Interest Arbitrage) strategy.
Run: python -m pytest tests/test_put_steal.py -v
"""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.put_steal import _compute_nii, _build_labels, _build_features, _bs_price


class TestNII:

    def test_nii_positive_high_rate(self):
        """High interest rate, deep ITM put → NII should be positive (steal is on)."""
        S, X, T, r, sigma = 90.0, 100.0, 30 / 365.0, 0.05, 0.20
        nii = _compute_nii(S, X, T, r, sigma)
        assert nii > 0, f"Expected positive NII, got {nii:.4f}"

    def test_nii_negative_high_vol(self):
        """Very high vol → caput is large → NII should be negative (don't steal)."""
        S, X, T, r, sigma = 95.0, 100.0, 30 / 365.0, 0.01, 1.50
        nii = _compute_nii(S, X, T, r, sigma)
        assert nii < 0, f"Expected negative NII with high vol, got {nii:.4f}"

    def test_nii_zero_rate(self):
        """Zero interest rate → no interest income → NII always non-positive."""
        S, X, T, r, sigma = 90.0, 100.0, 30 / 365.0, 0.0, 0.20
        nii = _compute_nii(S, X, T, r, sigma)
        assert nii <= 0

    def test_nii_increases_with_rate(self):
        """NII should be monotonically increasing in the risk-free rate."""
        S, X, T, sigma = 88.0, 100.0, 21 / 365.0, 0.20
        nii_low  = _compute_nii(S, X, T, 0.01, sigma)
        nii_mid  = _compute_nii(S, X, T, 0.04, sigma)
        nii_high = _compute_nii(S, X, T, 0.08, sigma)
        assert nii_low < nii_mid < nii_high

    def test_nii_decreases_with_vol(self):
        """NII should be decreasing in vol (higher vol → larger caput)."""
        S, X, T, r = 88.0, 100.0, 21 / 365.0, 0.05
        nii_low_vol  = _compute_nii(S, X, T, r, 0.10)
        nii_high_vol = _compute_nii(S, X, T, r, 0.60)
        assert nii_low_vol > nii_high_vol

    def test_nii_zero_dte(self):
        """At expiry (T=0), NII is 0 — no time left to earn interest."""
        nii = _compute_nii(90.0, 100.0, 0.0, 0.05, 0.20)
        assert nii == 0.0


class TestBullPutSpreadPnL:

    def _spread_pnl(self, spot, short_K, long_K, credit):
        """P&L of a bull put credit spread at expiry."""
        intrinsic = max(0, short_K - spot) - max(0, long_K - spot)
        return (credit - intrinsic) * 100

    def test_full_profit_above_short_strike(self):
        """Bull put: full credit when spot stays above short strike."""
        credit = 1.50
        pnl = self._spread_pnl(520, 500, 485, credit)
        assert pnl == pytest.approx(credit * 100)

    def test_max_loss_below_long_strike(self):
        """Bull put: max loss = (wing - credit) × 100 when spot crashes through both strikes."""
        short_K, long_K, credit = 500, 485, 1.50
        expected = -(short_K - long_K - credit) * 100
        pnl = self._spread_pnl(460, short_K, long_K, credit)
        assert pnl == pytest.approx(expected)

    def test_defined_risk(self):
        """Max loss is finite and bounded by wing × 100."""
        short_K, long_K, credit = 500, 485, 1.50
        max_loss = (short_K - long_K - credit) * 100
        assert max_loss > 0
        assert max_loss < 10_000


class TestPutStealStrategy:

    def setup_method(self):
        from strategies.put_steal import PutStealStrategy
        self.cls = PutStealStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_warmup_bars(self):
        from strategies.put_steal import _WARMUP_BARS
        assert _WARMUP_BARS >= 60

    def test_retrain_interval(self):
        from strategies.put_steal import _RETRAIN_EVERY
        assert _RETRAIN_EVERY >= 10

    def test_feature_count(self):
        s = self.cls()
        assert len(s.FEATURE_COLS) >= 10

    def test_get_params_roundtrip(self):
        s = self.cls(nii_threshold=0.10, itm_pct=0.07)
        p = s.get_params()
        assert p["nii_threshold"] == pytest.approx(0.10)
        assert p["itm_pct"] == pytest.approx(0.07)

    def test_ui_params_structure(self):
        s = self.cls()
        params = s.get_backtest_ui_params()
        assert len(params) >= 5
        for p in params:
            assert "key" in p and "label" in p and "type" in p

    def test_generate_signal_sell(self):
        """Deep ITM put, high rate, low vol → SELL signal (steal is on).
        Use itm_pct=0.20 so the put is 20% ITM: the call at X is far OTM,
        making NII = X(1-e^{-rT}) - call(S,X,T) clearly positive.
        """
        s = self.cls(nii_threshold=0.01, itm_pct=0.20)
        result = s.generate_signal({
            "spot": 80.0,          # stock has dropped; put at X=96 is 20% ITM
            "risk_free_rate": 0.05,
            "iv_level": 0.20,
            "vix": 18.0,
        })
        assert result.signal == "SELL", (
            f"Expected SELL but got {result.signal}. "
            f"metadata: {result.metadata}"
        )
        assert result.confidence > 0.5

    def test_generate_signal_hold_high_vol(self):
        """High vol (IV > iv_max) → HOLD."""
        s = self.cls(iv_max=0.50)
        result = s.generate_signal({
            "spot": 90.0,
            "risk_free_rate": 0.05,
            "iv_level": 0.80,   # above iv_max
            "vix": 18.0,
        })
        assert result.signal == "HOLD"

    def test_generate_signal_hold_high_vix(self):
        """Panic VIX → HOLD."""
        s = self.cls(vix_max=40.0)
        result = s.generate_signal({
            "spot": 90.0,
            "risk_free_rate": 0.05,
            "iv_level": 0.25,
            "vix": 55.0,    # above vix_max
        })
        assert result.signal == "HOLD"


class TestLabelConstruction:

    def test_labels_binary(self):
        """Labels must be 0.0 or 1.0 only."""
        import pandas as pd
        n = 60
        dates = pd.date_range("2023-01-01", periods=n)
        close = pd.Series(100.0 + np.cumsum(np.random.normal(0, 1, n)), index=dates)
        labels = _build_labels(close, itm_pct=0.05, n_forward=21)
        valid = labels.dropna()
        assert len(valid) > 0
        assert valid.isin([0.0, 1.0]).all()

    def test_labels_tight_buffer_mostly_fail(self):
        """Small itm_pct (tiny buffer) on a declining stock → many label=0.
        short_strike = spot × (1 - 0.01). A stock falling 1.5%/day easily
        drops below 99% of today's price in 10 days → label=0 most of the time.
        """
        import pandas as pd
        np.random.seed(42)
        n = 100
        dates = pd.date_range("2023-01-01", periods=n)
        # Strong downtrend: ~1.5% daily decline
        returns = np.random.normal(-0.015, 0.005, n)
        close = pd.Series(100.0 * np.exp(np.cumsum(returns)), index=dates)
        labels = _build_labels(close, itm_pct=0.01, n_forward=10)
        valid = labels.dropna()
        assert len(valid) > 0
        # A declining stock easily breaks the 1% buffer → majority label=0
        assert valid.mean() < 0.5
