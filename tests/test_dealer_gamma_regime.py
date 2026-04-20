"""
tests/test_dealer_gamma_regime.py
Unit tests for the Dealer Gamma Regime strategy + GEX engine.

Run: python -m pytest tests/test_dealer_gamma_regime.py -v
"""
import math
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Chain fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_chain(spot: float, flip_offset_pct: float, strikes_pct=None,
                add_wall_at=None, wall_size=50_000, dte=30, iv=0.20):
    """
    Build a synthetic option chain where net dealer GEX flips sign at
    spot * (1 + flip_offset_pct). Used to test that find_flip_level
    recovers the intended flip point.

    flip_offset_pct > 0 → spot below flip (negative GEX regime)
    flip_offset_pct < 0 → spot above flip (positive GEX regime)
    """
    if strikes_pct is None:
        strikes_pct = np.arange(-0.15, 0.151, 0.01)

    rows = []
    flip_k = spot * (1 + flip_offset_pct)
    for pct in strikes_pct:
        K = round(spot * (1 + pct), 2)
        # Both call + put at each strike
        for opt_type in ("call", "put"):
            # Gamma peaks at-the-money; we approximate with a narrow gaussian
            g = math.exp(-((K - spot) ** 2) / (2 * (spot * 0.05) ** 2)) / 40.0
            # OI weighted so sign flips at flip_k:
            # below flip_k → put OI dominates; above → call OI dominates
            if opt_type == "call":
                oi = 5000 if K >= flip_k else 500
            else:
                oi = 500  if K >= flip_k else 5000
            rows.append({
                "strike":       K,
                "option_type":  opt_type,
                "gamma":        g,
                "open_interest":oi,
                "iv":           iv,
                "dte":          dte,
            })

    if add_wall_at is not None:
        for opt_type in ("call", "put"):
            rows.append({
                "strike":       add_wall_at,
                "option_type":  opt_type,
                "gamma":        0.08,
                "open_interest":wall_size,
                "iv":           iv,
                "dte":          dte,
            })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# GEX Engine tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGEXEngine:

    def test_bs_gamma_positive_ATM(self):
        from analytics.gex_engine import bs_gamma
        g = bs_gamma(S=100, K=100, T=30/365, iv=0.20)
        assert g > 0
        assert g < 1.0

    def test_bs_gamma_zero_edge_cases(self):
        from analytics.gex_engine import bs_gamma
        assert bs_gamma(100, 100, 0, 0.2) == 0.0
        assert bs_gamma(100, 100, 0.1, 0) == 0.0

    def test_compute_rejects_empty(self):
        from analytics.gex_engine import compute_dealer_gex
        with pytest.raises(ValueError):
            compute_dealer_gex(pd.DataFrame(), 100.0)

    def test_compute_rejects_bad_spot(self):
        from analytics.gex_engine import compute_dealer_gex
        chain = _make_chain(100, 0.0)
        with pytest.raises(ValueError):
            compute_dealer_gex(chain, -1.0)

    def test_missing_required_column(self):
        from analytics.gex_engine import compute_dealer_gex
        # strike is a hard requirement (gamma/IV are interchangeable)
        chain = _make_chain(100, 0.0).drop(columns=["strike"])
        with pytest.raises(ValueError, match="strike"):
            compute_dealer_gex(chain, 100.0)

    def test_gamma_backfilled_from_iv(self):
        """If gamma column is missing but IV is present, GEX still computes."""
        from analytics.gex_engine import compute_dealer_gex
        chain = _make_chain(100, 0.02).drop(columns=["gamma"])
        snap = compute_dealer_gex(chain, 100.0)
        assert snap.net_gex != 0.0

    def test_oi_falls_back_to_volume(self):
        """If OI is absent but Volume is present, GEX uses Volume as proxy."""
        from analytics.gex_engine import compute_dealer_gex
        chain = _make_chain(100, 0.02)
        chain = chain.rename(columns={"open_interest": "Volume"})
        snap = compute_dealer_gex(chain, 100.0)
        assert snap.net_gex != 0.0
        assert any("Volume" in w for w in snap.warnings)

    def test_returns_required_fields(self):
        from analytics.gex_engine import compute_dealer_gex
        chain = _make_chain(100, 0.0)
        snap  = compute_dealer_gex(chain, 100.0)
        assert snap.spot == 100.0
        assert snap.flip_level > 0
        assert isinstance(snap.net_gex, float)
        assert isinstance(snap.gex_by_strike, pd.Series)
        assert snap.sign_convention == "index_retail_call_long"

    def test_flip_level_above_spot_when_negative_regime(self):
        """Flip at +2% above spot → dist_to_flip_pct negative (spot below flip)."""
        from analytics.gex_engine import compute_dealer_gex
        chain = _make_chain(spot=100.0, flip_offset_pct=0.02)
        snap  = compute_dealer_gex(chain, 100.0)
        assert snap.flip_level > snap.spot
        assert snap.dist_to_flip_pct < 0

    def test_flip_level_below_spot_when_positive_regime(self):
        """Flip at -2% below spot → dist_to_flip_pct positive (spot above flip)."""
        from analytics.gex_engine import compute_dealer_gex
        chain = _make_chain(spot=100.0, flip_offset_pct=-0.02)
        snap  = compute_dealer_gex(chain, 100.0)
        assert snap.flip_level < snap.spot
        assert snap.dist_to_flip_pct > 0

    def test_sign_convention_inversion(self):
        """Inverting sign convention should flip the sign of net_gex."""
        from analytics.gex_engine import compute_dealer_gex
        chain = _make_chain(spot=100.0, flip_offset_pct=0.02)
        a = compute_dealer_gex(chain, 100.0, sign_convention="index_retail_call_long")
        b = compute_dealer_gex(chain, 100.0, sign_convention="retail_put_long")
        assert np.sign(a.net_gex) == -np.sign(b.net_gex)
        assert a.net_gex == pytest.approx(-b.net_gex)

    def test_invalid_sign_convention(self):
        from analytics.gex_engine import compute_dealer_gex
        chain = _make_chain(100, 0.0)
        with pytest.raises(ValueError, match="sign_convention"):
            compute_dealer_gex(chain, 100.0, sign_convention="bogus")

    def test_detect_wall_above_spot(self):
        from analytics.gex_engine import compute_dealer_gex
        chain = _make_chain(spot=100.0, flip_offset_pct=-0.02,
                            add_wall_at=108.0, wall_size=50_000)
        snap  = compute_dealer_gex(chain, 100.0)
        # Wall should be detected above spot
        assert snap.call_wall is not None
        assert snap.call_wall == pytest.approx(108.0)

    def test_wall_ignored_too_close_to_spot(self):
        from analytics.gex_engine import compute_dealer_gex
        chain = _make_chain(spot=100.0, flip_offset_pct=-0.02,
                            add_wall_at=100.2, wall_size=50_000)
        snap  = compute_dealer_gex(chain, 100.0, wall_min_dist_pct=0.01)
        # 100.2 is only 0.2% from spot, below min_dist_pct threshold
        # The massive wall gamma may still register via dominant sum at nearby strike
        # but specifically the wall at 100.2 should be filtered
        if snap.call_wall is not None:
            assert snap.call_wall >= 100 * 1.01

    def test_0dte_split(self):
        from analytics.gex_engine import compute_dealer_gex
        chain_a = _make_chain(100, 0.0, dte=30)
        chain_b = _make_chain(100, 0.0, dte=1)
        chain   = pd.concat([chain_a, chain_b], ignore_index=True)
        snap    = compute_dealer_gex(chain, 100.0)
        assert abs(snap.net_gex_0dte) > 0
        assert abs(snap.net_gex_multiday) > 0

    def test_classify_regime(self):
        from analytics.gex_engine import compute_dealer_gex, classify_regime
        # Positive regime — flip well below spot
        chain_pos = _make_chain(spot=100.0, flip_offset_pct=-0.05)
        snap_pos  = compute_dealer_gex(chain_pos, 100.0)
        assert classify_regime(snap_pos, near_flip_pct=0.005) == "positive"

        # Negative regime — flip well above spot
        chain_neg = _make_chain(spot=100.0, flip_offset_pct=0.05)
        snap_neg  = compute_dealer_gex(chain_neg, 100.0)
        assert classify_regime(snap_neg, near_flip_pct=0.005) == "negative"

    def test_expected_move(self):
        from analytics.gex_engine import expected_move_pct
        em = expected_move_pct(iv_atm=0.20, dte=30)
        assert em == pytest.approx(0.20 * math.sqrt(30 / 365), rel=1e-6)
        assert expected_move_pct(0.0, 30) > 0    # fallback
        assert expected_move_pct(0.20, 0) > 0    # fallback


# ─────────────────────────────────────────────────────────────────────────────
# Strategy tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDealerGammaRegime:

    def setup_method(self):
        from strategies.dealer_gamma_regime import DealerGammaRegimeStrategy
        self.cls = DealerGammaRegimeStrategy

    def test_instantiates(self):
        s = self.cls()
        assert s is not None
        assert s.name == "dealer_gamma_regime"
        assert s.status.value == "active"

    def test_get_params_returns_dict(self):
        s = self.cls()
        p = s.get_params()
        assert isinstance(p, dict)
        assert "base_risk_pct" in p
        assert "near_flip_pct" in p

    def test_ui_params_well_formed(self):
        s = self.cls()
        ui = s.get_backtest_ui_params()
        assert len(ui) > 0
        for item in ui:
            assert "key" in item and "label" in item and "type" in item and "default" in item

    # ── Live signal ───────────────────────────────────────────────────────

    def test_signal_hold_when_missing_inputs(self):
        s = self.cls()
        r = s.generate_signal({})
        assert r.signal == "HOLD"
        assert r.position_size_pct == 0.0

    def test_signal_hold_when_vix_too_high(self):
        s = self.cls(vix_ceiling=30)
        chain = _make_chain(100, 0.02)
        r = s.generate_signal({"option_chain": chain, "spot": 100.0, "vix": 45.0})
        assert r.signal == "HOLD"
        assert "vix" in r.metadata.get("reason", "").lower()

    def test_signal_negative_regime_buys_straddle(self):
        """Spot below flip → regime negative → BUY long_straddle."""
        s = self.cls(min_abs_gex=0)
        chain = _make_chain(spot=100.0, flip_offset_pct=0.05)
        r = s.generate_signal({"option_chain": chain, "spot": 100.0, "vix": 18.0})
        assert r.signal == "BUY"
        assert r.metadata["trade_type"] == "long_straddle"
        assert r.metadata["regime"] == "negative"

    def test_signal_positive_regime_sells_condor(self):
        """Spot above flip → regime positive → SELL iron_condor."""
        s = self.cls(min_abs_gex=0)
        chain = _make_chain(spot=100.0, flip_offset_pct=-0.05)
        r = s.generate_signal({"option_chain": chain, "spot": 100.0, "vix": 18.0})
        assert r.signal == "SELL"
        assert r.metadata["trade_type"] == "iron_condor"
        assert r.metadata["regime"] == "positive"

    def test_near_flip_is_long_straddle(self):
        s = self.cls(min_abs_gex=0, near_flip_pct=5.0)  # very wide near-flip band
        chain = _make_chain(spot=100.0, flip_offset_pct=0.001)
        r = s.generate_signal({"option_chain": chain, "spot": 100.0, "vix": 18.0})
        assert r.metadata["regime"] == "near_flip"
        assert r.metadata["trade_type"] == "long_straddle"

    # ── Sizing ────────────────────────────────────────────────────────────

    def test_sizing_scales_with_flip_proximity(self):
        s = self.cls(base_risk_pct=0.5, max_risk_pct=2.0)
        far_size = s._size_for_distance(0.05)   # 5% from flip
        mid_size = s._size_for_distance(0.01)   # 1%
        near_size = s._size_for_distance(0.001) # 0.1%
        assert far_size == pytest.approx(0.005)
        assert mid_size > far_size
        assert near_size > mid_size
        assert near_size <= 0.02 + 1e-9

    def test_sizing_never_exceeds_max(self):
        s = self.cls(base_risk_pct=0.5, max_risk_pct=2.0)
        assert s._size_for_distance(0.0) <= 0.02 + 1e-9

    def test_sizing_floor_at_base(self):
        s = self.cls(base_risk_pct=0.75, max_risk_pct=1.5)
        assert s._size_for_distance(0.10) == pytest.approx(0.0075)

    # ── Delta strike finder ──────────────────────────────────────────────

    def test_find_delta_strike_call_otm(self):
        k = self.cls._find_delta_strike(spot=100, T=30/365, iv=0.20,
                                         target_delta=0.15, opt_type="call")
        assert k > 100   # 15-delta call should be OTM

    def test_find_delta_strike_put_otm(self):
        k = self.cls._find_delta_strike(spot=100, T=30/365, iv=0.20,
                                         target_delta=0.15, opt_type="put")
        assert k < 100   # 15-delta put should be OTM

    def test_find_delta_strike_atm_at_50(self):
        kc = self.cls._find_delta_strike(spot=100, T=30/365, iv=0.20,
                                         target_delta=0.50, opt_type="call")
        assert abs(kc - 100) < 3   # 50-delta ≈ ATM

    # ── Registry integration ─────────────────────────────────────────────

    def test_registered_in_registry(self):
        from strategies.registry import STRATEGY_METADATA, get_strategy
        assert "dealer_gamma_regime" in STRATEGY_METADATA
        meta = STRATEGY_METADATA["dealer_gamma_regime"]
        assert meta["status"] == "active"
        assert meta["type"] == "rule"
        s = get_strategy("dealer_gamma_regime")
        assert s.__class__.__name__ == "DealerGammaRegimeStrategy"

    # ── Backtest guards ──────────────────────────────────────────────────

    def test_backtest_errors_without_options(self):
        s = self.cls()
        px = pd.DataFrame(
            {"open": [100]*30, "high": [101]*30, "low": [99]*30, "close": [100]*30,
             "volume": [1_000_000]*30},
            index=pd.date_range("2024-01-01", periods=30, freq="B"),
        )
        with pytest.raises(ValueError, match="option_snapshots"):
            s.backtest(px, auxiliary_data={})


# ─────────────────────────────────────────────────────────────────────────────
# Sign convention mechanics — codified mechanic from the quant spec
# ─────────────────────────────────────────────────────────────────────────────

class TestGEXMechanic:
    """Asserts the strategy actually trades the dealer-gamma mechanic."""

    def test_negative_gex_trades_long_gamma(self):
        """Negative GEX → trends amplify → strategy must BUY a debit straddle."""
        from strategies.dealer_gamma_regime import DealerGammaRegimeStrategy
        s = DealerGammaRegimeStrategy(min_abs_gex=0)
        chain = _make_chain(spot=100.0, flip_offset_pct=0.04)  # flip above spot
        r = s.generate_signal({"option_chain": chain, "spot": 100.0, "vix": 18.0})
        assert r.signal == "BUY", "Must go long gamma in negative GEX regime"
        assert r.metadata["trade_type"] == "long_straddle"

    def test_positive_gex_trades_short_gamma(self):
        """Positive GEX → mean-reversion/pin → strategy must SELL a condor."""
        from strategies.dealer_gamma_regime import DealerGammaRegimeStrategy
        s = DealerGammaRegimeStrategy(min_abs_gex=0)
        chain = _make_chain(spot=100.0, flip_offset_pct=-0.04)  # flip below spot
        r = s.generate_signal({"option_chain": chain, "spot": 100.0, "vix": 18.0})
        assert r.signal == "SELL", "Must go short gamma in positive GEX regime"
        assert r.metadata["trade_type"] == "iron_condor"

    def test_position_size_bounded(self):
        """Size never exceeds max_risk_pct."""
        from strategies.dealer_gamma_regime import DealerGammaRegimeStrategy
        s = DealerGammaRegimeStrategy(base_risk_pct=1.0, max_risk_pct=3.0, min_abs_gex=0)
        chain = _make_chain(spot=100.0, flip_offset_pct=0.04)
        r = s.generate_signal({"option_chain": chain, "spot": 100.0, "vix": 18.0})
        assert r.position_size_pct <= 0.03 + 1e-9
        assert r.position_size_pct > 0
