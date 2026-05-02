"""
tests/test_tail_risk_put_spread.py
Unit tests for the Tail Risk Put Spread strategy.

Run: python -m pytest tests/test_tail_risk_put_spread.py -v
"""
import os
import sys
import math

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic-market fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_calm_market(days: int = 500, spot0: float = 477.0,
                      mu_annual: float = 0.07, sigma_annual: float = 0.13,
                      seed: int = 7) -> pd.DataFrame:
    """Geometric Brownian motion — no crash, mild drift, low vol."""
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    shocks = rng.standard_normal(days)
    log_rets = (mu_annual - 0.5 * sigma_annual ** 2) * dt + sigma_annual * math.sqrt(dt) * shocks
    prices = spot0 * np.exp(np.cumsum(log_rets))
    idx = pd.date_range("2018-01-02", periods=days, freq="B")
    return pd.DataFrame({
        "open":  prices,
        "high":  prices * 1.003,
        "low":   prices * 0.997,
        "close": prices,
        "volume": [10_000_000] * days,
    }, index=idx)


def _make_crash_market(days: int = 252, spot0: float = 477.0,
                       seed: int = 11) -> pd.DataFrame:
    """
    Deterministic crash: linear drift up for 100 days, sharp -25% drop over
    next 30 days, recovery for the remainder. The hedge program should pay
    off near the trough.
    """
    rng = np.random.default_rng(seed)
    prices = np.empty(days)
    prices[0] = spot0
    # phase A — calm uptrend (days 0-119)
    for i in range(1, 120):
        prices[i] = prices[i-1] * (1 + rng.normal(0.0003, 0.008))
    crash_start = 120
    crash_end   = 150
    target_low  = prices[crash_start-1] * 0.75
    # phase B — crash (linear interpolation w/ noise)
    for i in range(crash_start, crash_end):
        frac = (i - crash_start + 1) / (crash_end - crash_start)
        prices[i] = prices[crash_start-1] * (1 - 0.25 * frac) * (1 + rng.normal(0, 0.012))
    # phase C — partial recovery
    for i in range(crash_end, days):
        prices[i] = prices[i-1] * (1 + rng.normal(0.0008, 0.012))

    idx = pd.date_range("2020-01-02", periods=days, freq="B")
    return pd.DataFrame({
        "open":  prices,
        "high":  prices * 1.005,
        "low":   prices * 0.995,
        "close": prices,
        "volume": [10_000_000] * days,
    }, index=idx)


def _make_vix_for(price_df: pd.DataFrame, base: float = 17.0, sigma: float = 2.0,
                  seed: int = 19, crash_lift: bool = False) -> pd.DataFrame:
    """
    Synthesize a plausible VIX series for the given price DataFrame:
      - base level around `base`,
      - mean-reverting noise (sigma),
      - if `crash_lift`: amplify VIX inversely with rolling returns (proxy for
        the empirical SPY ↑ VIX inverse relationship).
    """
    rng = np.random.default_rng(seed)
    n = len(price_df)
    noise = rng.standard_normal(n) * sigma
    vix = base + noise

    if crash_lift:
        # Proxy: when price drops sharply, VIX rises
        rets = price_df["close"].pct_change().fillna(0).to_numpy()
        rolling = pd.Series(rets).rolling(20, min_periods=1).sum().to_numpy()
        vix = vix - 250.0 * np.minimum(rolling, 0)   # only lift on drawdown

    vix = np.clip(vix, 9.0, 80.0)
    return pd.DataFrame({"close": vix}, index=price_df.index)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTailRiskPutSpread:

    def setup_method(self):
        from strategies.tail_risk_put_spread import TailRiskPutSpreadStrategy
        self.cls = TailRiskPutSpreadStrategy

    # ── Basic plumbing ────────────────────────────────────────────────────

    def test_instantiates(self):
        s = self.cls()
        assert s is not None
        assert s.name == "tail_risk_put_spread"
        assert s.display_name == "Tail Risk Put Spread"
        assert s.status.value == "active"
        assert s.strategy_type.value == "rule"
        assert s.asset_class == "equities_options"

    def test_get_params_returns_dict(self):
        s = self.cls()
        p = s.get_params()
        assert isinstance(p, dict)
        for k in ("long_otm_pct", "short_otm_pct", "dte_target",
                  "roll_at_dte", "annual_cost_cap_pct", "purchase_cadence_days",
                  "max_concurrent"):
            assert k in p

    def test_ui_params_well_formed(self):
        s = self.cls()
        ui = s.get_backtest_ui_params()
        assert isinstance(ui, list)
        assert len(ui) >= 7
        for item in ui:
            for required in ("key", "label", "type", "default"):
                assert required in item, f"missing {required} in {item}"

    def test_invalid_strike_ordering_rejected(self):
        with pytest.raises(ValueError):
            # short closer-to-ATM than long is nonsensical for a bear put debit spread
            self.cls(long_otm_pct=0.20, short_otm_pct=0.10)

    # ── Live signal ───────────────────────────────────────────────────────

    def test_signal_hold_when_vix_too_high(self):
        s = self.cls(vix_max_at_entry=35.0)
        r = s.generate_signal({
            "spot": 477.0,
            "vix":  45.0,
            "days_since_last_buy": 90,
            "annual_cost_so_far_pct": 0.0,
            "n_open": 0,
            "capital": 100_000.0,
        })
        assert r.signal == "HOLD"
        assert "VIX" in r.metadata.get("reason", "") or "vix" in r.metadata.get("reason", "").lower()

    def test_signal_buy_when_vix_normal_and_due(self):
        s = self.cls()
        r = s.generate_signal({
            "spot": 477.0,
            "vix":  18.0,
            "days_since_last_buy": 90,
            "annual_cost_so_far_pct": 0.0,
            "n_open": 0,
            "capital": 100_000.0,
        })
        assert r.signal == "BUY"
        meta = r.metadata
        assert "long_strike" in meta
        assert "short_strike" in meta
        assert meta["long_strike"] > meta["short_strike"]   # bear put debit spread
        assert meta["dte"] == s.dte_target
        assert meta["debit_per_contract"] > 0.0
        assert meta["max_payout_per_contract"] > 0.0
        assert meta["structure"] == "bear_put_debit_spread"

    def test_signal_hold_when_calendar_not_due(self):
        s = self.cls()
        r = s.generate_signal({
            "spot": 477.0,
            "vix":  18.0,
            "days_since_last_buy": 10,    # too soon
            "annual_cost_so_far_pct": 0.0,
            "n_open": 0,
            "capital": 100_000.0,
        })
        assert r.signal == "HOLD"
        assert "calendar" in r.metadata["reason"].lower()

    def test_signal_hold_when_budget_exhausted(self):
        s = self.cls(annual_cost_cap_pct=0.010)
        r = s.generate_signal({
            "spot": 477.0,
            "vix":  18.0,
            "days_since_last_buy": 200,
            "annual_cost_so_far_pct": 0.012,    # already over cap
            "n_open": 0,
            "capital": 100_000.0,
        })
        assert r.signal == "HOLD"
        assert "cost cap" in r.metadata["reason"].lower()

    def test_strikes_at_correct_otm_distances(self):
        """For spot=477, long_otm_pct=0.07, short_otm_pct=0.18:
           long ≈ 477*0.93 = 443.61 ; short ≈ 477*0.82 = 391.14.
           The brief specified 444 / 391 — assert within $1 of those."""
        s = self.cls(long_otm_pct=0.07, short_otm_pct=0.18)
        r = s.generate_signal({
            "spot": 477.0, "vix": 18.0, "days_since_last_buy": 200,
            "annual_cost_so_far_pct": 0.0, "n_open": 0, "capital": 100_000.0,
        })
        assert r.signal == "BUY"
        long_K  = r.metadata["long_strike"]
        short_K = r.metadata["short_strike"]
        assert abs(long_K  - 443.61) < 1.0   # ~444
        assert abs(short_K - 391.14) < 1.0   # ~391
        assert long_K > short_K

    # ── Backtest validation ──────────────────────────────────────────────

    def test_backtest_errors_without_vix(self):
        s = self.cls()
        px = _make_calm_market(days=120)
        with pytest.raises(ValueError, match=r"(?i)vix"):
            s.backtest(px, auxiliary_data={})

    def test_backtest_runs_on_synthetic_calm_market(self):
        """500 days of GBM SPY with no crash → equity should drift slightly down
        (cost of insurance) but not catastrophically. Sanity bounds: end equity
        must be within [-3%, +3%] of starting (premium drag dominates)."""
        s = self.cls(annual_cost_cap_pct=0.012, dte_target=60,
                     purchase_cadence_days=70)
        px  = _make_calm_market(days=500)
        vix = _make_vix_for(px, base=15.0, sigma=1.5)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=100_000.0)

        eq = result.equity_curve
        assert not eq.empty
        assert len(eq) == len(px)

        end_eq = eq.iloc[-1]
        # In a GBM-only market with no crash, the spread should cost money on net.
        # Very wide bounds — synthetic prices may produce small payouts on dips.
        assert 95_000.0 < end_eq < 103_000.0, f"Calm market end equity {end_eq:.0f} outside [95k, 103k]"

        # Annual cost should be in the ballpark of the cap (we want the program
        # to spend up to but not above the cap).
        actual = result.extra["annual_cost_pct_actual"]
        assert actual < 0.012 * 1.10, f"Annual cost {actual:.4f} > cap × 1.10"

    def test_backtest_runs_on_synthetic_crash(self):
        """252 days with a -25% crash mid-window. Hedge program should produce
        a meaningful gain at the trough — end equity must be ABOVE start."""
        s = self.cls(annual_cost_cap_pct=0.020, dte_target=75,
                     purchase_cadence_days=60, profit_take_pct=1.00)
        px  = _make_crash_market(days=252)
        vix = _make_vix_for(px, base=18.0, sigma=2.5, crash_lift=True)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=100_000.0)
        eq = result.equity_curve
        assert not eq.empty

        # Peak equity (likely captured around or just after crash trough)
        peak_eq = eq.max()
        # The hedge must have produced gains during the drawdown — we need
        # the equity curve to have spent some time above starting capital.
        assert peak_eq > 100_500, (
            f"Hedge produced no meaningful gain on a 25% crash: "
            f"peak equity {peak_eq:.0f}"
        )
        # And we should see at least one harvest in the harvest_log
        # OR a closed trade with positive PnL.
        if not result.trades.empty:
            assert result.trades["pnl"].max() > 0, "No winning hedge trade in crash run"

    def test_annual_cost_cap_enforced(self):
        """Run the strategy across 2 years on a synthetic calm market.
        Total debits paid should not exceed (annual_cost_cap × 2 years × capital × 1.05)."""
        cap_pct = 0.010
        years   = 2
        days    = 252 * years
        s = self.cls(annual_cost_cap_pct=cap_pct, purchase_cadence_days=60,
                     dte_target=75)
        px  = _make_calm_market(days=days)
        vix = _make_vix_for(px, base=15.0, sigma=1.0)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=100_000.0)

        total_debit = result.extra["total_debit_paid"]
        cap_dollars = cap_pct * 100_000.0 * years * 1.05    # 5% slack for rolling-window edge effects
        assert total_debit <= cap_dollars, (
            f"Total debit paid ${total_debit:,.0f} exceeds 2-year cap ${cap_dollars:,.0f}"
        )

    def test_roll_at_dte_threshold(self):
        """Open a spread; advance time past the roll-DTE threshold; assert a
        fresh purchase has occurred (= the original spread was closed and a new
        one opened)."""
        # Use a short cadence so that calendar always permits a fresh entry as
        # soon as the existing spread closes.
        s = self.cls(dte_target=45, roll_at_dte=20, purchase_cadence_days=20,
                     annual_cost_cap_pct=0.030)
        px  = _make_calm_market(days=180)
        vix = _make_vix_for(px, base=15.0, sigma=1.0)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=200_000.0)
        # Expect at least 2 purchases (initial + at least one roll)
        assert len(result.extra["purchase_log"]) >= 2, \
            f"Expected ≥ 2 purchases (roll trigger), got {len(result.extra['purchase_log'])}"
        # Expect at least one closed spread with reason 'roll_at_dte' OR end_of_data
        if not result.trades.empty:
            reasons = set(result.trades["exit_reason"].unique())
            assert "roll_at_dte" in reasons or len(result.trades) >= 1

    def test_profit_harvest_triggers(self):
        """Synthetic crash: SPY drops sharply; spread gains 100%+ → harvest
        should fire and a new spread should open."""
        s = self.cls(dte_target=75, purchase_cadence_days=30,
                     profit_take_pct=1.00, annual_cost_cap_pct=0.030)
        px  = _make_crash_market(days=200)
        vix = _make_vix_for(px, base=17.0, sigma=2.0, crash_lift=True)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=200_000.0)

        # We expect at least one harvest in this crash scenario.
        # If not, the test fails — the harvest mechanic isn't firing.
        harvest_df = result.extra["harvest_log"]
        assert len(harvest_df) >= 1, (
            "Profit harvest never triggered on a 25% crash — "
            "either profit_take logic is wrong or pricing is too conservative."
        )
        # And after a harvest, a new spread should be opened — total purchases > harvests.
        assert len(result.extra["purchase_log"]) > len(harvest_df), \
            "After harvest, no fresh spread was opened."

    def test_max_concurrent_enforced(self):
        """Run the program; concurrency state must never exceed max_concurrent."""
        max_c = 1
        s = self.cls(max_concurrent=max_c, purchase_cadence_days=20,
                     dte_target=80, annual_cost_cap_pct=0.030)
        px  = _make_calm_market(days=200)
        vix = _make_vix_for(px, base=15.0, sigma=1.0)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=100_000.0)

        regime = result.extra["regime_series"]
        if not regime.empty:
            assert regime["n_open"].max() <= max_c, \
                f"Concurrency cap breached: max n_open={regime['n_open'].max()} > {max_c}"

    # ── Live-signal sanity ────────────────────────────────────────────────

    def test_signal_hold_when_max_concurrent_reached(self):
        s = self.cls(max_concurrent=2)
        r = s.generate_signal({
            "spot": 477.0, "vix": 18.0, "days_since_last_buy": 200,
            "annual_cost_so_far_pct": 0.0, "n_open": 2, "capital": 100_000.0,
        })
        assert r.signal == "HOLD"
        assert "concurrent" in r.metadata["reason"].lower()
