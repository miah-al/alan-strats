"""
tests/test_fomc_event_straddle.py
Unit tests for the FOMC Event Straddle strategy.

Run: python -m pytest tests/test_fomc_event_straddle.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_price_data(start="2023-01-02", periods=365, start_price=400.0,
                     mu=0.0003, sigma=0.012, seed=42):
    """Synthetic geometric-brownian SPY-like daily bars."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=periods)
    rets = rng.normal(mu, sigma, size=len(dates))
    px = start_price * np.exp(np.cumsum(rets))
    high = px * (1 + np.abs(rng.normal(0, 0.004, len(dates))))
    low  = px * (1 - np.abs(rng.normal(0, 0.004, len(dates))))
    return pd.DataFrame({
        "open":   px,
        "high":   high,
        "low":    low,
        "close":  px,
        "volume": rng.integers(50_000_000, 100_000_000, len(dates)),
    }, index=dates)


def _make_vix(price_df, base_vix=18.0, seed=7):
    """Synthetic VIX series aligned to price_df, mean-reverting around base_vix."""
    rng = np.random.default_rng(seed)
    n = len(price_df)
    vix = np.zeros(n)
    vix[0] = base_vix
    for i in range(1, n):
        # OU-like
        vix[i] = max(10.0, vix[i-1] + 0.10 * (base_vix - vix[i-1]) + rng.normal(0, 0.6))
    return pd.DataFrame({"close": vix}, index=price_df.index)


def _synthetic_fomc_dates(start="2023-02-01", n=10, weeks_between=6):
    """Synthetic FOMC dates ~every 6 weeks for testing."""
    start = pd.Timestamp(start)
    return pd.DatetimeIndex([start + pd.Timedelta(weeks=weeks_between * i) for i in range(n)])


# ─────────────────────────────────────────────────────────────────────────────
# Strategy tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFOMCEventStraddle:

    def setup_method(self):
        from strategies.fomc_event_straddle import FOMCEventStraddleStrategy
        self.cls = FOMCEventStraddleStrategy

    # ── Basic structural tests ───────────────────────────────────────────

    def test_instantiates(self):
        s = self.cls()
        assert s is not None
        assert s.name == "fomc_event_straddle"
        assert s.display_name == "FOMC Event Straddle"
        assert s.status.value == "active"
        assert s.strategy_type.value == "rule"
        assert s.asset_class == "equities_options"

    def test_get_params_returns_dict(self):
        s = self.cls()
        p = s.get_params()
        assert isinstance(p, dict)
        for k in ("dte_target", "days_before_fomc", "vix_max", "ivr_max",
                  "max_debit_pct_spot", "profit_target_pct", "stop_loss_pct",
                  "position_size_pct", "max_concurrent"):
            assert k in p, f"missing param: {k}"

    def test_ui_params_well_formed(self):
        s = self.cls()
        ui = s.get_backtest_ui_params()
        assert isinstance(ui, list)
        assert len(ui) >= 6
        for item in ui:
            assert "key" in item and "label" in item and "type" in item
            assert "default" in item

    # ── Calendar / window helpers ────────────────────────────────────────

    def test_default_calendar_has_known_dates(self):
        from strategies.fomc_event_straddle import default_fomc_calendar
        cal = default_fomc_calendar()
        assert isinstance(cal, pd.DatetimeIndex)
        # 2024-03-20 was a real FOMC announcement date
        assert pd.Timestamp("2024-03-20") in cal
        # Sanity: 2024 should have 8 dates
        in_2024 = cal[(cal.year == 2024)]
        assert len(in_2024) == 8

    def test_default_calendar_is_sorted(self):
        from strategies.fomc_event_straddle import default_fomc_calendar
        cal = default_fomc_calendar()
        assert list(cal) == sorted(cal)

    def test_is_fomc_window_correct(self):
        from strategies.fomc_event_straddle import is_fomc_window
        fomc = [pd.Timestamp("2024-03-20")]
        # T-2 inside window (days_before=2)
        assert is_fomc_window(pd.Timestamp("2024-03-18"), fomc, days_before=2) == True
        # Day-of inside window
        assert is_fomc_window(pd.Timestamp("2024-03-20"), fomc, days_before=2) == True
        # T+1 inside window (days_after=1)
        assert is_fomc_window(pd.Timestamp("2024-03-21"), fomc, days_before=2, days_after=1) == True
        # T-5 outside
        assert is_fomc_window(pd.Timestamp("2024-03-15"), fomc, days_before=2, days_after=1) == False
        # T+3 outside
        assert is_fomc_window(pd.Timestamp("2024-03-23"), fomc, days_before=2, days_after=1) == False

    def test_next_fomc_date(self):
        from strategies.fomc_event_straddle import next_fomc_date
        fomc = [pd.Timestamp("2024-03-20"), pd.Timestamp("2024-05-01")]
        nxt = next_fomc_date(pd.Timestamp("2024-03-15"), fomc)
        assert nxt == pd.Timestamp("2024-03-20")
        nxt2 = next_fomc_date(pd.Timestamp("2024-03-21"), fomc)
        assert nxt2 == pd.Timestamp("2024-05-01")
        # No future date
        none_ = next_fomc_date(pd.Timestamp("2025-01-01"), fomc)
        assert none_ is None

    # ── Live signal ──────────────────────────────────────────────────────

    def test_signal_hold_outside_fomc_window(self):
        s = self.cls()
        # Use a real FOMC date and pick a day far away
        snap = {
            "spot": 500.0, "vix": 18.0, "current_date": pd.Timestamp("2024-04-15"),
            "fomc_dates": [pd.Timestamp("2024-03-20")],
        }
        r = s.generate_signal(snap)
        assert r.signal == "HOLD"
        assert "outside" in r.metadata.get("reason", "").lower() or \
               "fomc" in r.metadata.get("reason", "").lower()

    def test_signal_hold_when_vix_too_high(self):
        s = self.cls(vix_max=28.0)
        snap = {
            "spot": 500.0, "vix": 35.0, "current_date": pd.Timestamp("2024-03-18"),
            "ivr": 0.4,
            "fomc_dates": [pd.Timestamp("2024-03-20")],
        }
        r = s.generate_signal(snap)
        assert r.signal == "HOLD"
        assert "vix" in r.metadata.get("reason", "").lower()

    def test_signal_hold_when_ivr_too_high(self):
        s = self.cls(ivr_max=0.7)
        snap = {
            "spot": 500.0, "vix": 22.0, "current_date": pd.Timestamp("2024-03-18"),
            "ivr": 0.85,
            "fomc_dates": [pd.Timestamp("2024-03-20")],
        }
        r = s.generate_signal(snap)
        assert r.signal == "HOLD"
        assert "ivr" in r.metadata.get("reason", "").lower()

    def test_signal_buy_when_in_window_and_gates_pass(self):
        s = self.cls(vix_max=28.0, ivr_max=0.7, max_debit_pct_spot=0.05)
        snap = {
            "spot": 500.0, "vix": 18.0, "current_date": pd.Timestamp("2024-03-18"),
            "ivr": 0.3,
            "fomc_dates": [pd.Timestamp("2024-03-20")],
        }
        r = s.generate_signal(snap)
        assert r.signal == "BUY"
        assert r.metadata["structure"] == "long_straddle"
        assert "fomc_date" in r.metadata
        assert pd.Timestamp(r.metadata["fomc_date"]).date() == pd.Timestamp("2024-03-20").date()
        assert r.position_size_pct > 0

    def test_signal_hold_when_missing_inputs(self):
        s = self.cls()
        r = s.generate_signal({})
        assert r.signal == "HOLD"
        assert r.position_size_pct == 0.0

    # ── Backtest ─────────────────────────────────────────────────────────

    def test_backtest_runs_on_synthetic(self):
        s = self.cls(
            vix_max=40.0, ivr_max=1.0, max_debit_pct_spot=0.10,
            position_size_pct=0.02, max_concurrent=1,
        )
        px  = _make_price_data(periods=365)
        vix = _make_vix(px, base_vix=18.0)
        # Synthetic FOMC dates every 6 weeks within the price window
        fomc = _synthetic_fomc_dates(start=px.index[20], n=8, weeks_between=6)

        result = s.backtest(
            price_data       = px,
            auxiliary_data   = {"vix": vix, "fomc_dates": fomc},
            starting_capital = 100_000.0,
        )
        assert result.strategy_name == "fomc_event_straddle"
        assert isinstance(result.equity_curve, pd.Series)
        assert len(result.equity_curve) > 0
        assert isinstance(result.trades, pd.DataFrame)
        # With permissive gates we should have multiple trades
        assert len(result.trades) >= 3, (
            f"Expected >= 3 trades on FOMC weeks but got {len(result.trades)}"
        )
        # Trades should reference FOMC dates
        if not result.trades.empty:
            assert "fomc_date" in result.trades.columns
            assert "structure" in result.trades.columns
            assert (result.trades["structure"] == "long_straddle").all()
            # Defined-risk: max loss bounded by debit_paid
            assert (result.trades["pnl"] >= -result.trades["debit_paid"] * 1.05).all(), \
                "Loss exceeded debit (defined-risk violation)"

    def test_backtest_errors_without_vix(self):
        s = self.cls()
        px = _make_price_data(periods=60)
        with pytest.raises(ValueError, match="VIX"):
            s.backtest(price_data=px, auxiliary_data={})

    def test_max_concurrent_enforced(self):
        s = self.cls(
            vix_max=40.0, ivr_max=1.0, max_debit_pct_spot=0.10,
            position_size_pct=0.02, max_concurrent=1,
            days_before_fomc=2, days_after_fomc=20,   # very long hold to force overlap
            stop_loss_pct=0.99, profit_target_pct=0.99,
        )
        px  = _make_price_data(periods=200)
        vix = _make_vix(px, base_vix=18.0)
        # FOMC every 2 weeks → entries would overlap if not gated
        fomc = _synthetic_fomc_dates(start=px.index[20], n=6, weeks_between=2)
        result = s.backtest(
            price_data       = px,
            auxiliary_data   = {"vix": vix, "fomc_dates": fomc},
            starting_capital = 100_000.0,
        )
        # Inspect entry log: at most 1 open position at any time. We test by
        # checking no two trades have overlapping entry/exit windows when
        # max_concurrent=1.
        trades = result.trades
        if len(trades) >= 2:
            ents = pd.to_datetime(trades["entry_date"]).sort_values().reset_index(drop=True)
            exts = pd.to_datetime(trades["exit_date"]).sort_values().reset_index(drop=True)
            for i in range(len(ents) - 1):
                # Next trade entry must be after previous exit (or the strategy
                # would have had 2 concurrent positions)
                assert ents.iloc[i+1] >= exts.iloc[i], (
                    f"Concurrent positions detected: entry {ents.iloc[i+1]} "
                    f"before exit {exts.iloc[i]}"
                )

    def test_backtest_no_lookahead(self):
        """Sanity: changing future bars should not change past equity."""
        s = self.cls(vix_max=40.0, ivr_max=1.0, max_debit_pct_spot=0.10)
        px_a = _make_price_data(periods=200, seed=11)
        vix_a = _make_vix(px_a, base_vix=18.0)
        fomc = _synthetic_fomc_dates(start=px_a.index[20], n=4, weeks_between=6)

        # Run on full data
        full = s.backtest(price_data=px_a, auxiliary_data={"vix": vix_a, "fomc_dates": fomc})
        # Run on truncated data
        trunc_idx = 100
        truncated = s.backtest(
            price_data=px_a.iloc[:trunc_idx],
            auxiliary_data={"vix": vix_a.iloc[:trunc_idx], "fomc_dates": fomc},
        )
        # Equity at index 50 should match between the two runs (no lookahead)
        common = full.equity_curve.index[:50]
        for d in common:
            if d in truncated.equity_curve.index:
                assert abs(full.equity_curve.loc[d] - truncated.equity_curve.loc[d]) < 1e-2, \
                    f"Lookahead detected at {d}"

    def test_defined_risk_loss_bounded(self):
        """Long straddle is debit-paid → loss can never exceed debit."""
        s = self.cls(
            vix_max=40.0, ivr_max=1.0, max_debit_pct_spot=0.10,
            position_size_pct=0.02,
        )
        px  = _make_price_data(periods=200, seed=99)
        vix = _make_vix(px, base_vix=22.0, seed=12)
        fomc = _synthetic_fomc_dates(start=px.index[20], n=5, weeks_between=6)
        result = s.backtest(price_data=px, auxiliary_data={"vix": vix, "fomc_dates": fomc})
        if not result.trades.empty:
            for _, row in result.trades.iterrows():
                # PnL floor = -debit_paid (plus small slippage/comm allowance)
                assert row["pnl"] >= -row["debit_paid"] * 1.05, (
                    f"Loss {row['pnl']} exceeded debit {row['debit_paid']}"
                )
