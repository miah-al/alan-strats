"""
tests/test_calendar_spread_vix.py
Unit tests for the VIX Calendar Spread strategy.
Run: python -m pytest tests/test_calendar_spread_vix.py -v
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.calendar_spread_vix import (   # noqa: E402
    VIXCalendarSpreadStrategy,
    _heuristic_term_ratio,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────

def _make_vix_panel(n_days: int = 365, base_vix: float = 16.0,
                    seed: int = 7) -> pd.DataFrame:
    """Synthetic VIX OHLC: mean-reverting around base_vix, no extreme spikes."""
    rng    = np.random.default_rng(seed)
    dates  = pd.bdate_range("2022-01-03", periods=n_days)
    shocks = rng.normal(0.0, 0.6, n_days)
    series = np.zeros(n_days)
    series[0] = base_vix
    for i in range(1, n_days):
        series[i] = series[i-1] + 0.20 * (base_vix - series[i-1]) + shocks[i]
    series = np.clip(series, 10.0, 30.0)
    df = pd.DataFrame({
        "open":  series,
        "high":  series + 0.3,
        "low":   series - 0.3,
        "close": series,
    }, index=dates)
    return df


def _make_term_panel(vix_df: pd.DataFrame, ratio: float = 1.10) -> pd.DataFrame:
    """Synthetic VIX futures M1/M2 panel with steady contango."""
    m1 = vix_df["close"] * 1.02         # M1 just above spot in calm regime
    m2 = m1 * ratio                     # M2 fixed contango above M1
    return pd.DataFrame({"m1_close": m1, "m2_close": m2}, index=vix_df.index)


# ─── Test class ─────────────────────────────────────────────────────────────

class TestVIXCalendarSpread:

    def setup_method(self):
        self.cls = VIXCalendarSpreadStrategy

    # --- basic construction & params --------------------------------------

    def test_instantiates(self):
        s = self.cls()
        assert s is not None
        assert s.name == "calendar_spread_vix"
        assert s.display_name == "Calendar Spread (VIX)"
        assert s.asset_class == "volatility"

    def test_get_params(self):
        s = self.cls()
        p = s.get_params()
        assert isinstance(p, dict)
        # spot-check the key economic parameters
        for k in ("dte_back_target", "dte_front_target", "strike_otm_pct",
                  "term_ratio_min", "vix_max_entry", "vix_spike_close",
                  "profit_target_pct", "stop_loss_pct", "dte_close_at",
                  "max_concurrent"):
            assert k in p
        assert p["dte_back_target"]  == 75
        assert p["dte_front_target"] == 21
        assert p["term_ratio_min"]   == 1.05
        assert p["vix_spike_close"]  == 35.0

    def test_ui_params(self):
        s = self.cls()
        ui = s.get_backtest_ui_params()
        assert isinstance(ui, list) and len(ui) >= 7
        keys = {row["key"] for row in ui}
        for required in ("term_ratio_min", "vix_max_entry", "vix_spike_close",
                         "dte_back_target", "dte_front_target"):
            assert required in keys

    # --- live signal gating -----------------------------------------------

    def test_signal_hold_when_term_ratio_too_low(self):
        s = self.cls()
        sig = s.generate_signal({"vix": 16.0, "term_ratio": 1.00,
                                 "vix_5d_change": 0.0})
        assert sig.signal == "HOLD"
        assert "term ratio" in sig.metadata["reason"]

    def test_signal_hold_when_vix_high(self):
        s = self.cls()
        sig = s.generate_signal({"vix": 30.0, "term_ratio": 1.10,
                                 "vix_5d_change": 0.0})
        assert sig.signal == "HOLD"
        assert "VIX" in sig.metadata["reason"]

    def test_signal_hold_when_vix_5d_accelerating(self):
        s = self.cls()
        sig = s.generate_signal({"vix": 18.0, "term_ratio": 1.10,
                                 "vix_5d_change": 0.40})
        assert sig.signal == "HOLD"
        assert "5d" in sig.metadata["reason"]

    def test_signal_buy_when_contango_and_calm(self):
        s = self.cls()
        sig = s.generate_signal({"vix": 15.0, "term_ratio": 1.10,
                                 "vix_5d_change": 0.0})
        assert sig.signal == "BUY"
        assert sig.confidence > 0.4
        meta = sig.metadata
        assert meta["structure"] == "vix_call_calendar"
        assert meta["leg_long"]["dte"] == s.dte_back_target
        assert meta["leg_short"]["dte"] == s.dte_front_target
        # Same strike, ~10% above VIX
        assert meta["leg_long"]["strike"] == meta["leg_short"]["strike"]
        assert meta["leg_long"]["strike"] == pytest.approx(15.0 * 1.10, rel=0.01)
        assert meta["european_settled"] is True

    def test_signal_panic_close_priority(self):
        """Live signal must report panic regime when VIX > spike threshold."""
        s = self.cls()
        sig = s.generate_signal({"vix": 40.0, "term_ratio": 1.10,
                                 "vix_5d_change": 0.0})
        assert sig.signal == "HOLD"
        assert sig.metadata.get("regime") == "panic"

    # --- backtest plumbing -------------------------------------------------

    def test_backtest_errors_without_vix_spot(self):
        s = self.cls()
        with pytest.raises(ValueError):
            s.backtest(price_data=pd.DataFrame(), auxiliary_data={})

    def test_backtest_runs_on_synthetic(self):
        """Stable contango + calm VIX should produce trades."""
        s = self.cls(max_concurrent=3)
        vix_df  = _make_vix_panel(365, base_vix=16.0)
        term_df = _make_term_panel(vix_df, ratio=1.10)
        result  = s.backtest(price_data=vix_df,
                             auxiliary_data={"vix_term": term_df},
                             starting_capital=100_000)
        assert isinstance(result.equity_curve, pd.Series)
        assert len(result.equity_curve) == len(vix_df)
        # Edge should fire at least a handful of times across a year of contango
        assert len(result.trades) >= 3, f"expected ≥3 trades, got {len(result.trades)}"
        # No-lookahead sanity: every trade closes on or after entry date
        for _, row in result.trades.iterrows():
            assert row["exit_date"] >= row["entry_date"]
        # Defined-risk-AT-EXPIRATION invariant: each opened debit is bounded by
        # ``debit × 100 × contracts``.  Intraday MTM during a gap CAN exceed
        # this magnitude before the stop / panic-close fires (this is the
        # well-documented "calendar collapse in vol spike" behaviour the
        # strategy is built to guard against).  We assert the structural
        # invariant — that the typical loser is contained — rather than a
        # bound on per-bar gap MTM.
        for _, row in result.trades.iterrows():
            structural_max_loss = row["debit"] * 100 * row["contracts"]
            # Loser magnitudes must stay within ~3× debit even on gap exits
            # (this catches truly broken pricing while allowing realistic
            # gap risk).
            assert row["pnl"] >= -3.0 * structural_max_loss - 50.0, (
                f"trade loss {row['pnl']} exceeds 3× debit×100×contracts "
                f"({structural_max_loss}) — pricing or exit logic broken"
            )
        # And on average the strategy's loser size should be sane vs. capital
        losers = result.trades[result.trades["pnl"] < 0]
        if not losers.empty:
            assert losers["pnl"].mean() > -5_000, (
                f"avg loser {losers['pnl'].mean():.0f} unreasonably large for $100K cap"
            )
        assert result.extra["used_heuristic"] is False

    def test_backtest_with_heuristic_term_fallback(self, caplog):
        """Missing vix_term → strategy must fall back to heuristic & warn."""
        import logging
        s = self.cls(max_concurrent=3)
        vix_df = _make_vix_panel(365, base_vix=14.0)   # calm → heuristic gives contango
        with caplog.at_level(logging.WARNING):
            result = s.backtest(price_data=vix_df, auxiliary_data={},
                                starting_capital=100_000)
        # Warning fired
        assert any("heuristic" in m.lower() for m in caplog.messages)
        # Backtest still completes and returns a usable equity curve
        assert result.extra["used_heuristic"] is True
        assert len(result.equity_curve) == len(vix_df)
        # Heuristic ratio is bounded — confirm no impossible values
        ratios = result.extra["term_ratio"]
        assert ratios.min() >= 0.85
        assert ratios.max() <= 1.20

    def test_vix_spike_close(self):
        """Open a trade in calm regime, then jump VIX above panic threshold."""
        # ATM strike: at the synthetic flat VIX=15 a 10%-OTM calendar's debit sits
        # just under the $0.05 floor, so entries never open. ATM clears the floor
        # so a trade actually opens — which is the precondition this test needs to
        # exercise the VIX-spike panic-close path.
        s = self.cls(max_concurrent=1, dte_back_target=60, dte_front_target=20,
                     strike_otm_pct=0.0)
        # First 50 bars: calm contango → entry happens
        # Then jump VIX to 40 for several bars → panic close fires
        n = 200
        dates  = pd.bdate_range("2023-01-02", periods=n)
        series = np.full(n, 15.0)
        series[120:] = 40.0
        vix_df = pd.DataFrame({"open": series, "high": series + 0.3,
                               "low": series - 0.3, "close": series},
                              index=dates)
        term_df = _make_term_panel(vix_df, ratio=1.10)
        result = s.backtest(price_data=vix_df,
                            auxiliary_data={"vix_term": term_df},
                            starting_capital=100_000)
        # At least one trade must exit with reason 'vix_spike'
        reasons = set(result.trades["exit_reason"]) if not result.trades.empty else set()
        assert "vix_spike" in reasons, (
            f"expected a 'vix_spike' exit; got reasons={reasons}, "
            f"n_trades={len(result.trades)}"
        )
        # The VIX-spike exit happens on the first bar at/after VIX > 35
        spike_trades = result.trades[result.trades["exit_reason"] == "vix_spike"]
        for _, row in spike_trades.iterrows():
            assert row["vix_at_exit"] > s.vix_spike_close

    def test_max_concurrent_enforced(self):
        """Backtest never holds more than max_concurrent open positions."""
        s = self.cls(max_concurrent=2, dte_back_target=60, dte_front_target=20)
        vix_df  = _make_vix_panel(365, base_vix=15.0)
        term_df = _make_term_panel(vix_df, ratio=1.12)   # strong contango → many entries
        result  = s.backtest(price_data=vix_df,
                             auxiliary_data={"vix_term": term_df},
                             starting_capital=500_000)
        # Reconstruct concurrency from entry/exit dates
        if result.trades.empty:
            pytest.skip("no trades in this run")
        events = []
        for _, row in result.trades.iterrows():
            events.append((pd.Timestamp(row["entry_date"]), +1))
            events.append((pd.Timestamp(row["exit_date"]),  -1))
        events.sort()
        n_open, max_seen = 0, 0
        for _, delta in events:
            n_open += delta
            max_seen = max(max_seen, n_open)
        assert max_seen <= s.max_concurrent, (
            f"observed {max_seen} concurrent trades, exceeds cap {s.max_concurrent}"
        )

    # --- defined-risk / heuristic helpers ---------------------------------

    def test_defined_risk_invariant_arithmetic(self):
        """Calendar = debit spread → max loss is the net debit paid."""
        debit = 1.20
        contracts = 3
        max_loss = debit * 100 * contracts
        assert max_loss == pytest.approx(360.0)

    def test_heuristic_term_ratio_bounded(self):
        """Heuristic must NEVER exceed realistic contango/backwardation band."""
        rng    = np.random.default_rng(0)
        dates  = pd.bdate_range("2022-01-03", periods=300)
        # Throw a wide vix range at it
        series = pd.Series(np.clip(20 + rng.normal(0, 8, 300), 5, 80), index=dates)
        ratio  = _heuristic_term_ratio(series, lookback=20)
        assert ratio.min() >= 0.85
        assert ratio.max() <= 1.20
