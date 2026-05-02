"""
tests/test_expiry_max_pain.py

Unit tests for the OpEx Max Pain Pin strategy.

Run: python -m pytest tests/test_expiry_max_pain.py -v
"""
from __future__ import annotations

import math
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic chain fixture
# ─────────────────────────────────────────────────────────────────────────────

def _make_chain(
    spot: float,
    max_pain_k: float,
    *,
    strikes_pct=None,
    iv: float = 0.20,
    dte: int = 4,
    expiry: pd.Timestamp | None = None,
    asym_put_oi_below: float = 1.0,   # multiplier on put OI for K < spot
    base_oi: int = 1_000,
    pin_oi: int = 30_000,
):
    """
    Build a synthetic chain whose max-pain strike == ``max_pain_k`` and where
    OI peaks at that strike. ``asym_put_oi_below`` skews put OI heavier below
    spot to drag max pain down (used by the asymmetry test).
    """
    if strikes_pct is None:
        strikes_pct = np.arange(-0.12, 0.121, 0.005)  # ±12% in 0.5% steps
    rows = []
    for pct in strikes_pct:
        K = round(spot * (1 + pct), 2)
        # Heavy concentration AT max_pain_k for both calls and puts
        is_pin = abs(K - max_pain_k) < 1e-6
        # Distance-decay around max_pain_k for OI
        decay = math.exp(-((K - max_pain_k) / (spot * 0.04)) ** 2)
        for opt_type in ("call", "put"):
            if is_pin:
                oi = pin_oi
            else:
                oi = max(int(base_oi * decay), 100)
                if opt_type == "put" and K < spot:
                    oi = int(oi * asym_put_oi_below)
            # Gamma proxy (gaussian centred on spot)
            gamma = math.exp(-((K - spot) / (spot * 0.05)) ** 2) / 40.0
            rows.append({
                "strike":        K,
                "option_type":   opt_type,
                "open_interest": oi,
                "gamma":         gamma,
                "iv":            iv,
                "dte":           dte,
                "expiry":        expiry if expiry is not None else
                                 (pd.Timestamp.today().normalize() + pd.Timedelta(days=dte)),
            })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestExpiryMaxPain:

    def setup_method(self):
        from alan_trader.strategies.expiry_max_pain import ExpiryMaxPainStrategy
        self.cls = ExpiryMaxPainStrategy

    # ── Basic class hygiene ──────────────────────────────────────────────────

    def test_instantiates(self):
        s = self.cls()
        assert s is not None
        assert s.name == "expiry_max_pain"
        assert s.display_name == "OpEx Max Pain Pin"
        assert s.status.value == "active"
        assert s.strategy_type.value == "rule"
        assert s.asset_class == "equities_options"

    def test_get_params_returns_dict(self):
        s = self.cls()
        p = s.get_params()
        assert isinstance(p, dict)
        for required in ("min_dist_pct", "max_dist_pct", "vix_ceiling",
                         "wing_width_pct", "position_size_pct"):
            assert required in p

    def test_ui_params_well_formed(self):
        s = self.cls()
        ui = s.get_backtest_ui_params()
        assert isinstance(ui, list) and 6 <= len(ui) <= 8
        for item in ui:
            for required in ("key", "label", "type", "default"):
                assert required in item, f"missing {required} in {item}"

    # ── compute_max_pain ────────────────────────────────────────────────────

    def test_compute_max_pain_picks_max_OI_strike(self):
        """Symmetric chain with peak OI at $100 → max pain ≈ $100."""
        from alan_trader.strategies.expiry_max_pain import compute_max_pain
        chain = _make_chain(spot=100.0, max_pain_k=100.0)
        mp = compute_max_pain(chain, 100.0)
        assert abs(mp - 100.0) <= 0.6   # tight tolerance — peak at the pin

    def test_compute_max_pain_handles_asymmetric_OI(self):
        """Heavier put OI below spot drags max pain DOWN relative to a symmetric chain."""
        from alan_trader.strategies.expiry_max_pain import compute_max_pain
        sym  = _make_chain(spot=100.0, max_pain_k=100.0)
        asym = _make_chain(spot=100.0, max_pain_k=99.0,
                           asym_put_oi_below=4.0, pin_oi=18_000)
        mp_sym  = compute_max_pain(sym,  100.0)
        mp_asym = compute_max_pain(asym, 100.0)
        assert mp_asym <= mp_sym
        assert mp_asym < 100.0

    # ── OpEx week / DTE helpers ─────────────────────────────────────────────

    def test_is_opex_week_true_for_third_friday_week(self):
        """March 11–15 2024: 3rd Friday is March 15."""
        from alan_trader.strategies.expiry_max_pain import is_opex_week
        for d in pd.date_range("2024-03-11", "2024-03-15", freq="D"):
            assert is_opex_week(d), f"{d.date()} should be in OpEx week"

    def test_is_opex_week_false_for_first_friday(self):
        """March 1 2024 is the 1st Friday — NOT OpEx week."""
        from alan_trader.strategies.expiry_max_pain import is_opex_week
        assert is_opex_week(pd.Timestamp("2024-03-01")) is False

    # ── Live signal gating ───────────────────────────────────────────────────

    def test_signal_hold_outside_opex_week(self):
        s = self.cls()
        chain = _make_chain(spot=100.0, max_pain_k=99.0)
        # Mid-cycle (first Tuesday of month, well before OpEx)
        r = s.generate_signal({
            "option_chain": chain, "spot": 100.0, "vix": 18.0,
            "current_date": pd.Timestamp("2024-03-05"),
        })
        assert r.signal == "HOLD"
        assert "opex" in r.metadata.get("reason", "").lower()

    def test_signal_hold_when_dist_too_small(self):
        s = self.cls(min_dist_pct=0.005, max_dist_pct=0.035, require_positive_gex=False)
        chain = _make_chain(spot=100.0, max_pain_k=100.0)
        r = s.generate_signal({
            "option_chain": chain, "spot": 100.0, "vix": 18.0,
            "current_date": pd.Timestamp("2024-03-12"),
        })
        assert r.signal == "HOLD"
        assert "close" in r.metadata.get("reason", "").lower() or \
               "pin"   in r.metadata.get("reason", "").lower()

    def test_signal_hold_when_dist_too_large(self):
        s = self.cls(min_dist_pct=0.005, max_dist_pct=0.035, require_positive_gex=False)
        chain = _make_chain(spot=100.0, max_pain_k=95.0)   # 5% gap
        r = s.generate_signal({
            "option_chain": chain, "spot": 100.0, "vix": 18.0,
            "current_date": pd.Timestamp("2024-03-12"),
        })
        assert r.signal == "HOLD"
        assert "far" in r.metadata.get("reason", "").lower() or \
               "pin" in r.metadata.get("reason", "").lower()

    def test_signal_sell_when_conditions_align(self):
        """Spot 1% above max pain, OpEx Tuesday, VIX 18 → SELL with metadata."""
        s = self.cls(require_positive_gex=False)
        chain = _make_chain(spot=100.0, max_pain_k=99.0)   # 1% gap
        r = s.generate_signal({
            "option_chain": chain, "spot": 100.0, "vix": 18.0,
            "current_date": pd.Timestamp("2024-03-12"),    # Tuesday of OpEx week (3rd Fri = 03-15)
        })
        assert r.signal == "SELL", f"expected SELL got {r.signal} reason={r.metadata.get('reason')}"
        assert "max_pain_strike" in r.metadata
        assert "dist_pct" in r.metadata
        assert "opex_friday" in r.metadata
        assert "regime" in r.metadata
        assert r.position_size_pct > 0

    def test_signal_hold_when_vix_high(self):
        s = self.cls(vix_ceiling=25.0, require_positive_gex=False)
        chain = _make_chain(spot=100.0, max_pain_k=99.0)
        r = s.generate_signal({
            "option_chain": chain, "spot": 100.0, "vix": 30.0,
            "current_date": pd.Timestamp("2024-03-12"),
        })
        assert r.signal == "HOLD"
        assert "vix" in r.metadata.get("reason", "").lower()

    # ── Backtest guards ─────────────────────────────────────────────────────

    def test_backtest_errors_without_options(self):
        s = self.cls()
        px = pd.DataFrame(
            {"open":  [100.0]*40, "high": [101.0]*40, "low": [99.0]*40,
             "close": [100.0]*40, "volume": [1_000_000]*40},
            index=pd.date_range("2024-01-01", periods=40, freq="B"),
        )
        with pytest.raises(ValueError, match="option_snapshots"):
            s.backtest(px, auxiliary_data={})

    # ── End-to-end synthetic backtest ───────────────────────────────────────

    def test_backtest_runs_on_synthetic(self):
        """
        ~3 months of synthetic SPY price data plus monthly OpEx chains where
        max pain sits ~1% from spot. Assert ≥ 2 trades fire and equity is finite.
        """
        from alan_trader.strategies.expiry_max_pain import (
            ExpiryMaxPainStrategy, third_friday,
        )

        # Daily price data, Jan–Mar 2024, gentle drift around 100
        all_days = pd.date_range("2024-01-02", "2024-03-29", freq="B")
        rng = np.random.default_rng(42)
        # Random-walk with low vol so the pin filter passes occasionally
        rets = rng.normal(0.0, 0.005, size=len(all_days))
        prices = 100.0 * np.exp(np.cumsum(rets))
        px = pd.DataFrame({
            "open":   prices,
            "high":   prices * 1.003,
            "low":    prices * 0.997,
            "close":  prices,
            "volume": 1_000_000,
        }, index=all_days)

        # Build per-day option snapshots ONLY for OpEx-week days,
        # with max_pain set to spot * 0.99 (1% below) on each of those days.
        snapshot_rows: list[pd.DataFrame] = []
        for ts in all_days:
            tf = third_friday(ts.year, ts.month)
            monday = tf - pd.Timedelta(days=tf.weekday())
            if not (monday.normalize() <= ts.normalize() <= tf.normalize()):
                continue
            spot = float(px.loc[ts, "close"])
            mp_k = round(spot * 0.99, 2)
            chain = _make_chain(spot=spot, max_pain_k=mp_k, dte=max(1, (tf - ts).days),
                                expiry=tf)
            chain["SnapshotDate"] = ts
            snapshot_rows.append(chain)

        opt_snaps = pd.concat(snapshot_rows, ignore_index=True)

        # VIX df — calm
        vix_df = pd.DataFrame({"close": [18.0] * len(all_days)}, index=all_days)

        strat = ExpiryMaxPainStrategy(require_positive_gex=False,
                                      min_dist_pct=0.003, max_dist_pct=0.040,
                                      position_size_pct=0.05)
        result = strat.backtest(
            price_data       = px,
            auxiliary_data   = {"option_snapshots": opt_snaps, "vix": vix_df},
            starting_capital = 100_000.0,
            ticker           = "SPY",
        )

        assert isinstance(result.trades, pd.DataFrame)
        assert len(result.trades) >= 2, f"expected ≥ 2 trades, got {len(result.trades)}"
        # Equity must be finite and non-empty
        assert not result.equity_curve.empty
        final_eq = float(result.equity_curve.iloc[-1])
        assert math.isfinite(final_eq)
        assert final_eq > 0
        # Sanity: trade rows have all required fields
        for col in ("entry_date", "exit_date", "max_pain_strike",
                    "contracts", "credit", "pnl", "exit_reason"):
            assert col in result.trades.columns, f"missing {col} in trades df"
