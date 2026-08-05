"""
tests/test_bull_put_spread.py
Unit tests for the Bull Put Spread strategy.

Covers:
  • import-fix regression (the strategy module + its backtest path import cleanly;
    the old `from ivr_credit_spread import _compute_ivr, _compute_adx` raised
    ImportError because `_compute_adx` never existed there).
  • look-ahead leak-freedom (prefix-stability of the equity curve).
  • a synthetic walk-forward run producing sane, defined-risk economics.
  • structural payoff formulas.

Run: python -m pytest tests/test_bull_put_spread.py -v
"""
import importlib

import numpy as np
import pandas as pd
import pytest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The strategy modules use absolute `alan_trader.*` imports; ensure the parent
# of the package dir is importable too.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _bps_pnl(s, short_k, long_k, credit):
    """Bull put spread P&L at expiry, per contract ($)."""
    return (credit - max(0, short_k - s) + max(0, long_k - s)) * 100


# ── Synthetic data builder ──────────────────────────────────────────────────

def _synthetic(n=600, seed=7):
    """Mild-drift price + cyclic VIX so 252-window IVR sweeps the full [0,1]
    range and the strategy actually enters trades."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-01", periods=n)
    price = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.008, n)))
    close = pd.Series(price, index=idx)
    px = pd.DataFrame({"close": close, "high": close * 1.004, "low": close * 0.996})
    t = np.arange(n)
    vix = pd.Series(20 + 10 * np.sin(t / 40.0) + rng.normal(0, 0.4, n), index=idx).clip(11, 40)
    aux = {"vix": pd.DataFrame({"close": vix})}
    return px, aux


# ── Import-fix regression ───────────────────────────────────────────────────

class TestImportFixRegression:
    """The original bug: `backtest()` imported `_compute_adx` from
    `ivr_credit_spread`, which does not export it → ImportError at runtime.
    These tests fail loudly if that (or any sibling import) regresses."""

    def test_module_imports_clean(self):
        mod = importlib.import_module("strategies.bull_put_spread")
        assert hasattr(mod, "BullPutSpreadStrategy")

    def test_indicator_imports_resolve(self):
        # The canonical helpers the strategy now depends on must exist.
        from strategies.indicators import compute_ivr, compute_adx  # noqa: F401
        from backtest.engine import (  # noqa: F401
            bs_price_skew, DEFAULT_SLIPPAGE_PER_LEG,
            DEFAULT_COMMISSION_PER_LEG, DEFAULT_SKEW_SLOPE,
        )

    def test_ivr_credit_spread_does_not_export_compute_adx(self):
        """Pin the root cause: importing _compute_adx from ivr_credit_spread
        must STILL fail, so the strategy never silently re-acquires the bad
        dependency."""
        ivr = importlib.import_module("strategies.ivr_credit_spread")
        assert not hasattr(ivr, "_compute_adx"), (
            "ivr_credit_spread unexpectedly exports _compute_adx — the original "
            "broken import would resurface; route through strategies.indicators."
        )

    def test_backtest_runs_without_import_error(self):
        from strategies.bull_put_spread import BullPutSpreadStrategy
        px, aux = _synthetic()
        # If the broken import regressed, this line raises ImportError.
        result = BullPutSpreadStrategy().backtest(px, aux, starting_capital=100_000)
        assert result is not None


# ── Core strategy contract ──────────────────────────────────────────────────

class TestBullPutSpread:

    def setup_method(self):
        from strategies.bull_put_spread import BullPutSpreadStrategy
        self.cls = BullPutSpreadStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_has_default_params(self):
        p = self.cls().get_params()
        assert isinstance(p, dict) and "ivr_min" in p and "spread_width_pct" in p

    def test_credit_ratio_default_is_feasible(self):
        """The old 0.30 min_credit_ratio was unreachable under skew BS for a
        30-delta/5%-wide spread (max ~0.22) → guaranteed 0 trades. Guard that
        the default stays within the achievable band."""
        assert self.cls()._DEFAULTS["min_credit_ratio"] <= 0.22

    def test_max_loss_formula(self):
        short_k, long_k, credit = 92.0, 87.0, 1.20
        assert (short_k - long_k - credit) * 100 == pytest.approx(380.0)

    def test_max_profit_is_credit(self):
        assert 1.20 * 100 == pytest.approx(120.0)

    def test_breakeven(self):
        assert 92.0 - 1.20 == pytest.approx(90.80)

    def test_full_profit_above_short_strike(self):
        assert _bps_pnl(95, 92, 87, 1.2) == pytest.approx(120.0)
        assert _bps_pnl(92, 92, 87, 1.2) == pytest.approx(120.0)

    def test_max_loss_below_long_strike(self):
        expected = -(92 - 87 - 1.2) * 100
        assert _bps_pnl(80, 92, 87, 1.2) == pytest.approx(expected)
        assert _bps_pnl(70, 92, 87, 1.2) == pytest.approx(expected)

    def test_long_put_caps_loss(self):
        assert _bps_pnl(85, 92, 87, 1.2) == pytest.approx(_bps_pnl(80, 92, 87, 1.2))

    def test_signal_hold_when_conditions_unmet(self):
        # IVR below threshold → HOLD.
        sig = self.cls().generate_signal(
            {"price": 100, "ivr": 0.10, "adx": 20, "vix": 18, "ma50": 95, "atm_iv": 0.20})
        assert sig.signal == "HOLD"


# ── Synthetic walk-forward run ──────────────────────────────────────────────

class TestSyntheticBacktest:

    def setup_method(self):
        from strategies.bull_put_spread import BullPutSpreadStrategy
        self.S = BullPutSpreadStrategy()
        self.px, self.aux = _synthetic()
        self.r = self.S.backtest(self.px, self.aux, starting_capital=100_000)

    def test_produces_trades(self):
        assert len(self.r.trades) >= 5, "synthetic regime should generate entries"

    def test_equity_curve_aligned_and_clean(self):
        eq = self.r.equity_curve
        assert eq.index.equals(self.px.index)
        assert bool(eq.notna().all())

    def test_all_credits_positive(self):
        assert bool((self.r.trades["credit"] > 0).all())

    def test_defined_risk_respected(self):
        """No trade may lose more than its width × 100 × contracts (the wing
        caps the loss). Allow a tiny epsilon for exit friction rounding."""
        t = self.r.trades
        max_loss = (t["short_K"] - t["long_K"]) * 100 * t["contracts"]
        # net pnl + max_loss should be ≥ ~ -(round-trip friction). Use a small tol.
        breaches = int(((t["pnl"] + max_loss) < -5.0).sum())
        assert breaches == 0

    def test_exit_reasons_valid(self):
        valid = {"profit_target", "stop_loss", "dte_exit", "end_of_data"}
        assert set(self.r.trades["exit_reason"]).issubset(valid)

    def test_costs_are_charged(self):
        """Round-tripping a profit_target winner must net LESS than the gross
        50%-of-credit target, because entry+exit commission and slippage are
        deducted. Compare a winner's pnl to its gross theoretical target."""
        wins = self.r.trades[self.r.trades["exit_reason"] == "profit_target"]
        if wins.empty:
            pytest.skip("no profit-target exits in this synthetic draw")
        row = wins.iloc[0]
        gross_target = row["credit"] * 0.50 * row["contracts"] * 100
        assert row["pnl"] < gross_target  # frictions ate into the gross


# ── Look-ahead leak-freedom ─────────────────────────────────────────────────

class TestNoLookAhead:

    def setup_method(self):
        from strategies.bull_put_spread import BullPutSpreadStrategy
        self.S = BullPutSpreadStrategy()

    def test_prefix_stability(self):
        """The defining property of a leak-free walk-forward: running on a
        truncated prefix of the data yields a byte-identical equity curve over
        that prefix. Any use of future information would break this."""
        px, aux = _synthetic(n=600)
        cut = 400
        full = self.S.backtest(px, aux, starting_capital=100_000).equity_curve

        px_c = px.iloc[:cut]
        aux_c = {"vix": aux["vix"].iloc[:cut]}
        part = self.S.backtest(px_c, aux_c, starting_capital=100_000).equity_curve

        common = full.index[:cut]
        diff = np.abs((full.reindex(common) - part.reindex(common)).to_numpy())
        assert np.nanmax(diff) < 1e-6, "equity diverged on prefix → look-ahead leak"

    def test_appending_future_does_not_change_past(self):
        """Symmetric check: extending the series with extra future bars must not
        alter any equity value on the original window."""
        px_short, aux_short = _synthetic(n=450)
        px_long, aux_long = _synthetic(n=600)
        # _synthetic is deterministic per-n via seed; the first 450 bars of the
        # 600-bar draw differ, so instead append future bars to the SHORT draw.
        extra_idx = pd.bdate_range(px_short.index[-1] + pd.Timedelta(days=1), periods=80)
        last = float(px_short["close"].iloc[-1])
        ext_close = pd.Series(np.linspace(last, last * 1.05, 80), index=extra_idx)
        ext_px = pd.DataFrame({"close": ext_close, "high": ext_close * 1.004,
                               "low": ext_close * 0.996})
        ext_vix = pd.Series(np.linspace(18, 22, 80), index=extra_idx)

        px_ext = pd.concat([px_short, ext_px])
        vix_ext = pd.concat([aux_short["vix"]["close"], ext_vix])
        aux_ext = {"vix": pd.DataFrame({"close": vix_ext})}

        base = self.S.backtest(px_short, aux_short, starting_capital=100_000).equity_curve
        grown = self.S.backtest(px_ext, aux_ext, starting_capital=100_000).equity_curve

        common = base.index
        diff = np.abs((base.reindex(common) - grown.reindex(common)).to_numpy())
        assert np.nanmax(diff) < 1e-6, "appending future bars changed the past → leak"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
