"""
tests/test_ivr_credit_spread.py
Unit + integration tests for the IVR Credit Spread strategy.

Covers:
  • Parameter / formula sanity (unit).
  • Synthetic walk-forward run on a controlled high-IVR regime (integration).
  • Transaction costs (commission + slippage) charged on entry AND exit.
  • Skew pricing actually applied (short OTM leg richer than flat-IV).
  • LOOK-AHEAD LEAK-FREEDOM: truncating the data must not change any trade that
    opens and closes (for a real reason) before the truncation boundary.

Run: python -m pytest tests/test_ivr_credit_spread.py -v
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

# Make both the repo root (so `strategies`, `backtest`, `risk` import) and its
# parent (so `import alan_trader...` works inside the strategy) importable.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_PARENT = os.path.dirname(_ROOT)
for _p in (_ROOT, _PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── P&L helpers (closed-form at expiry, for the unit tests) ─────────────────────

def _bs_put_spread_pnl(s, short_k, long_k, credit):
    """Bull put spread P&L at expiry ($ per contract)."""
    short_val = max(0, short_k - s)
    long_val = max(0, long_k - s)
    return (credit - short_val + long_val) * 100


def _bs_call_spread_pnl(s, short_k, long_k, credit):
    """Bear call spread P&L at expiry ($ per contract)."""
    short_val = max(0, s - short_k)
    long_val = max(0, s - long_k)
    return (credit - short_val + long_val) * 100


# ── Synthetic data builder (deterministic, high-IVR so the strategy fires) ──────

def _synthetic_data(n: int = 500, seed: int = 1):
    """Deterministic price + VIX frames whose VIX oscillates enough that IVR
    repeatedly clears 0.50, so the strategy actually opens trades."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-01", periods=n)
    close = 400.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    px = pd.DataFrame(
        {
            "close": close,
            "open": close,
            "high": close * 1.005,
            "low": close * 0.995,
            "volume": 1e6,
        },
        index=idx,
    )
    # VIX with a clear cycle 12..36 so the 52-week range is wide and IVR crosses 0.5.
    vix = 24.0 + 12.0 * np.sin(np.linspace(0, 8, n)) + np.abs(rng.normal(0, 1.0, n))
    vix_df = pd.DataFrame({"close": vix}, index=idx)
    return px, vix_df, idx


class TestIVRCreditSpread:

    def setup_method(self):
        from strategies.ivr_credit_spread import IVRCreditSpreadStrategy
        self.cls = IVRCreditSpreadStrategy

    # ── Basic params / formulas ────────────────────────────────────────────────

    def test_instantiates(self):
        assert self.cls() is not None

    def test_default_ivr_min(self):
        assert self.cls().ivr_min == 0.50

    def test_default_dte_exit(self):
        assert self.cls().dte_exit == 21

    def test_ivr_rank_formula(self):
        vix, vix_low, vix_high = 28.0, 12.0, 40.0
        ivr = (vix - vix_low) / (vix_high - vix_low)
        assert pytest.approx(ivr, abs=0.01) == 0.571

    def test_bull_put_selected_above_ma50(self):
        price, ma50 = 480.0, 460.0
        assert ("bull_put" if price > ma50 else "bear_call") == "bull_put"

    def test_bear_call_selected_below_ma50(self):
        price, ma50 = 440.0, 460.0
        assert ("bull_put" if price > ma50 else "bear_call") == "bear_call"

    def test_bull_put_max_profit_above_short_strike(self):
        credit = 1.50
        assert _bs_put_spread_pnl(110, 100, 95, credit) == pytest.approx(credit * 100)

    def test_bull_put_max_loss_below_long_strike(self):
        short_k, long_k, credit = 100, 95, 1.50
        expected = -(short_k - long_k - credit) * 100
        assert _bs_put_spread_pnl(80, short_k, long_k, credit) == pytest.approx(expected)

    def test_bear_call_max_profit_below_short_strike(self):
        credit = 1.20
        assert _bs_call_spread_pnl(90, 100, 105, credit) == pytest.approx(credit * 100)

    def test_50pct_profit_target(self):
        assert (1.50 * 0.50 * 100) == pytest.approx(75.0)

    def test_2x_stop_loss(self):
        assert (-1.50 * 2.0 * 100) == pytest.approx(-300.0)

    def test_ivr_clamped_to_0_1(self):
        vix_low, vix_high = 12.0, 40.0
        for vix in [5.0, 12.0, 20.0, 40.0, 50.0]:
            ivr = (vix - vix_low) / (vix_high - vix_low)
            assert 0.0 <= max(0.0, min(1.0, ivr)) <= 1.0

    # ── IVR series is leak-free (trailing rolling window only) ──────────────────

    def test_ivr_series_uses_only_past_data(self):
        """compute_ivr at bar i must not change when future bars are appended."""
        from strategies.ivr_credit_spread import _compute_ivr
        _, vix_df, _ = _synthetic_data(n=400, seed=7)
        vix = vix_df["close"]
        full = _compute_ivr(vix)
        trunc = _compute_ivr(vix.iloc[:301])
        diff = (full.iloc[:301] - trunc).abs().max()
        assert diff == 0.0 or np.isnan(diff), f"IVR leaked future data (max diff {diff})"

    def test_ivr_warmup_is_nan(self):
        """Below the 126-bar floor IVR must be NaN, not a fabricated rank."""
        from strategies.ivr_credit_spread import _compute_ivr, _MIN_VALID_IVR_BARS
        _, vix_df, _ = _synthetic_data(n=400, seed=8)
        ivr = _compute_ivr(vix_df["close"])
        assert ivr.iloc[: _MIN_VALID_IVR_BARS - 1].isna().all()
        assert ivr.iloc[_MIN_VALID_IVR_BARS:].notna().any()

    # ── Synthetic walk-forward run ──────────────────────────────────────────────

    def test_synthetic_run_executes_and_trades(self):
        px, vix_df, _ = _synthetic_data()
        r = self.cls().backtest(px, {"vix": vix_df, "ticker": "SPY"},
                                starting_capital=100_000)
        assert r is not None
        assert len(r.equity_curve) == len(px)
        assert len(r.trades) > 0, "high-IVR synthetic regime should open trades"
        # Equity must be finite and start at capital.
        assert np.isfinite(r.equity_curve.iloc[-1])
        assert r.equity_curve.iloc[0] == pytest.approx(100_000, rel=1e-3)
        # Every trade has both spread types' fields populated sanely.
        for _, t in r.trades.iterrows():
            assert t["spread_type"] in ("bull_put", "bear_call")
            assert t["contracts"] >= 1
            assert t["credit"] > 0
            assert t["exit_reason"] in (
                "profit_target", "dte_exit", "stop_loss", "end_of_data"
            )

    def test_missing_vix_raises(self):
        px, _, _ = _synthetic_data()
        with pytest.raises(ValueError):
            self.cls().backtest(px, {}, starting_capital=100_000)

    def test_short_history_no_trades(self):
        """Below the IVR warmup there can be no entries, but no crash."""
        idx = pd.bdate_range("2022-01-01", periods=80)
        px = pd.DataFrame({"close": 400 + np.arange(80) * 0.1}, index=idx)
        vix = pd.DataFrame({"close": np.full(80, 30.0)}, index=idx)
        r = self.cls().backtest(px, {"vix": vix}, starting_capital=100_000)
        assert len(r.trades) == 0
        assert r.equity_curve.iloc[-1] == pytest.approx(100_000)

    # ── Transaction costs: charged on entry AND exit ────────────────────────────

    def test_costs_reduce_pnl(self):
        """Identical trades cost money: zero-cost equity ≥ with-cost equity, and
        the difference equals the modeled friction (not zero)."""
        px, vix_df, _ = _synthetic_data(seed=3)
        aux = {"vix": vix_df, "ticker": "SPY"}
        free = self.cls(commission_per_leg=0.0, slippage_per_leg=0.0)
        paid = self.cls()  # engine-default commission + slippage
        rf = free.backtest(px, aux, starting_capital=100_000)
        rp = paid.backtest(px, aux, starting_capital=100_000)
        # Same set of entry decisions (costs don't gate entries here).
        assert len(rf.trades) == len(rp.trades) > 0
        # Costs strictly hurt.
        assert rp.equity_curve.iloc[-1] < rf.equity_curve.iloc[-1]

    def test_exit_friction_present_per_trade(self):
        """Each trade's net P&L must reflect BOTH entry and exit friction.
        Compare to a zero-cost run on the same trades: the per-trade gap must be
        > 0 and ≈ the round-trip friction (entry + exit commission + slippage)."""
        from backtest.engine import (
            DEFAULT_COMMISSION_PER_LEG as C,
            DEFAULT_SLIPPAGE_PER_LEG as SL,
        )
        px, vix_df, _ = _synthetic_data(seed=5)
        aux = {"vix": vix_df, "ticker": "SPY"}
        rf = self.cls(commission_per_leg=0.0, slippage_per_leg=0.0).backtest(
            px, aux, starting_capital=100_000)
        rp = self.cls().backtest(px, aux, starting_capital=100_000)

        # Strikes are cost-independent (delta inversion ignores costs), so pair
        # trades on the exact short strike + entry date.
        fmap = {(t.entry_date, round(t.short_K, 2)): t
                for t in rf.trades.itertuples()}
        checked = 0
        for t in rp.trades.itertuples():
            key = (t.entry_date, round(t.short_K, 2))
            if key not in fmap:
                continue
            f = fmap[key]
            # Only compare when the trade closed the same way in both runs;
            # entry slippage can occasionally flip a borderline exit reason.
            if f.exit_reason != t.exit_reason or f.exit_date != t.exit_date:
                continue
            gap = f.pnl - t.pnl  # free P&L minus paid P&L, recorded in the pnl field

            # The recorded `pnl` field = (credit − cost_to_close)×contracts×100 −
            # exit_close_cost. It does NOT include the entry commission (that is a
            # separate capital deduction). So the friction visible in `pnl` is:
            #   entry slippage folded into credit : 2×SL ×contracts×100
            #   exit close_cost                   : 2×(C + SL×100) ×contracts
            per_contract = (2 * SL * 100) + 2 * (C + SL * 100)
            expected = t.contracts * per_contract
            assert gap == pytest.approx(expected, rel=0.001, abs=0.05), (
                f"trade {key}: friction {gap:.2f} != expected {expected:.2f}"
            )
            checked += 1
        assert checked > 0, "no overlapping trades to verify friction on"

    # ── Skew pricing is actually applied ────────────────────────────────────────

    def test_skew_makes_otm_put_richer(self):
        """bs_price_skew must lift the IV (and price) of an OTM put above the
        flat-IV bs_price — proving the strategy prices with the equity-index
        downside skew, not flat VIX."""
        from backtest.engine import bs_price, bs_price_skew
        from strategies.ivr_credit_spread import _SKEW_SLOPE, _RISK_FREE_RATE
        S, iv, T, r = 500.0, 0.25, 45 / 365.0, _RISK_FREE_RATE
        K_otm = 462.0  # ~7.5% OTM put strike
        flat = bs_price(S, K_otm, T, r, iv, "put")
        skewed = bs_price_skew(S, K_otm, T, r, iv, "put", skew_slope=_SKEW_SLOPE)
        assert skewed > flat, "downside skew must richen the OTM short put"

    # ── Look-ahead leak-freedom (the core hardening guarantee) ──────────────────

    def test_no_lookahead_truncation_invariance(self):
        """Trades that open AND close (for a real reason) before the truncation
        boundary must be byte-identical whether or not future data exists.

        This is the decisive leak test: it catches any dependence of an entry or
        exit on n_dates / total sample length (the two bugs fixed in this file:
        the entry guard and the expiry-bar clamp)."""
        px, vix_df, idx = _synthetic_data(n=500, seed=1)
        aux_full = {"vix": vix_df, "ticker": "SPY"}
        cut = 450
        aux_cut = {"vix": vix_df.iloc[:cut], "ticker": "SPY"}

        full = self.cls().backtest(px, aux_full, starting_capital=100_000)
        trunc = self.cls().backtest(px.iloc[:cut], aux_cut, starting_capital=100_000)

        # Only compare trades that exited for a REAL reason (not end_of_data) and
        # with a 10-bar buffer before the cut, so boundary force-closes don't
        # contaminate the comparison.
        buf_date = idx[cut - 11].date()

        def real(df):
            d = df[(df["exit_date"] < buf_date) &
                   (df["exit_reason"] != "end_of_data")].copy()
            return d.sort_values(["entry_date", "short_K"]).reset_index(drop=True)

        fc, tc = real(full.trades), real(trunc.trades)
        assert len(fc) > 0, "synthetic run must produce comparable trades"
        assert len(fc) == len(tc), (
            f"trade count depends on future data: {len(fc)} vs {len(tc)} "
            "(look-ahead leak)"
        )
        for i in range(len(fc)):
            a, b = fc.iloc[i], tc.iloc[i]
            assert a["entry_date"] == b["entry_date"]
            assert a["exit_date"] == b["exit_date"]
            assert a["exit_reason"] == b["exit_reason"]
            assert a["pnl"] == pytest.approx(b["pnl"], abs=1e-6)
            assert a["short_K"] == pytest.approx(b["short_K"], abs=1e-6)
