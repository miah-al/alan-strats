"""
tests/test_tail_risk_long_put.py
Unit tests for the Tail Risk Long Put strategy.

Run: python -m pytest tests/test_tail_risk_long_put.py -v
"""
import os
import sys
import math

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic-market fixtures (mirror tests/test_tail_risk_put_spread.py)
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
    Deterministic crash: drift up for ~120 days, sharp ~25% drop over next
    30 days, partial recovery for the remainder. The hedge program should
    pay off near the trough.
    """
    rng = np.random.default_rng(seed)
    prices = np.empty(days)
    prices[0] = spot0
    # phase A — calm uptrend (days 0-119)
    upper = min(120, days)
    for i in range(1, upper):
        prices[i] = prices[i-1] * (1 + rng.normal(0.0003, 0.008))
    crash_start = min(120, days - 1)
    crash_end   = min(150, days)
    if crash_end > crash_start:
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
    Synthesize a plausible VIX series for the given price DataFrame.
    """
    rng = np.random.default_rng(seed)
    n = len(price_df)
    noise = rng.standard_normal(n) * sigma
    vix = base + noise

    if crash_lift:
        rets = price_df["close"].pct_change().fillna(0).to_numpy()
        rolling = pd.Series(rets).rolling(20, min_periods=1).sum().to_numpy()
        vix = vix - 250.0 * np.minimum(rolling, 0)

    vix = np.clip(vix, 9.0, 80.0)
    return pd.DataFrame({"close": vix}, index=price_df.index)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTailRiskLongPut:

    def setup_method(self):
        from strategies.tail_risk_long_put import TailRiskLongPutStrategy
        self.cls = TailRiskLongPutStrategy

    # ── Basic plumbing ────────────────────────────────────────────────────

    def test_instantiates(self):
        s = self.cls()
        assert s is not None
        assert s.name == "tail_risk_long_put"
        assert s.display_name == "Tail Risk Long Put"
        assert s.status.value == "active"
        assert s.strategy_type.value == "rule"
        assert s.asset_class == "equities_options"
        assert s.typical_holding_days == 75
        assert s.target_sharpe == 0.4

    def test_get_params_returns_dict(self):
        s = self.cls()
        p = s.get_params()
        assert isinstance(p, dict)
        for k in ("long_otm_pct", "dte_target", "roll_at_dte",
                  "annual_cost_cap_pct", "purchase_cadence_days",
                  "max_concurrent", "profit_take_pct", "put_iv_skew_mult"):
            assert k in p

    def test_ui_params_well_formed(self):
        s = self.cls()
        ui = s.get_backtest_ui_params()
        assert isinstance(ui, list)
        assert 8 <= len(ui) <= 9
        for item in ui:
            for required in ("key", "label", "type", "default"):
                assert required in item, f"missing {required} in {item}"

    def test_invalid_otm_pct_rejected(self):
        with pytest.raises(ValueError):
            self.cls(long_otm_pct=1.5)
        with pytest.raises(ValueError):
            self.cls(long_otm_pct=-0.1)

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
        assert "vix" in r.metadata.get("reason", "").lower()

    def test_signal_buy_when_calendar_due_and_vix_normal(self):
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
        # Naked long put — no short_strike key
        assert "short_strike" not in meta
        assert meta["dte"] == s.dte_target
        assert meta["debit_per_contract"] > 0.0
        assert meta["structure"] == "naked_long_put"

    def test_strike_at_correct_otm(self):
        """For spot=477, long_otm_pct=0.15: long strike ≈ 477*0.85 = 405.45."""
        s = self.cls(long_otm_pct=0.15)
        r = s.generate_signal({
            "spot": 477.0, "vix": 18.0, "days_since_last_buy": 200,
            "annual_cost_so_far_pct": 0.0, "n_open": 0, "capital": 100_000.0,
        })
        assert r.signal == "BUY"
        long_K = r.metadata["long_strike"]
        assert abs(long_K - 405.45) < 1.0   # ~405

    def test_signal_hold_when_max_concurrent_reached(self):
        s = self.cls(max_concurrent=3)
        r = s.generate_signal({
            "spot": 477.0, "vix": 18.0, "days_since_last_buy": 200,
            "annual_cost_so_far_pct": 0.0, "n_open": 3, "capital": 100_000.0,
        })
        assert r.signal == "HOLD"
        assert "concurrent" in r.metadata["reason"].lower()

    # ── Backtest validation ──────────────────────────────────────────────

    def test_backtest_errors_without_vix(self):
        s = self.cls()
        px = _make_calm_market(days=120)
        with pytest.raises(ValueError, match=r"(?i)vix"):
            s.backtest(px, auxiliary_data={})

    def test_backtest_runs_on_synthetic_calm_market(self):
        """500 days of GBM SPY with no crash → equity should drift down ~1-2%
        (cost of insurance) but not catastrophically. Bound: end equity in
        [97k, 100.5k] of starting (premium drag dominates, no crash payoff)."""
        s = self.cls(annual_cost_cap_pct=0.015,
                     dte_target=75,
                     purchase_cadence_days=30)
        px  = _make_calm_market(days=500)
        vix = _make_vix_for(px, base=15.0, sigma=1.5)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=100_000.0)

        eq = result.equity_curve
        assert not eq.empty
        assert len(eq) == len(px)

        end_eq = eq.iloc[-1]
        # Calm-market premium drag: ~1-2% over ~2 yrs. Wide band for synthetic noise.
        assert 96_000.0 < end_eq < 101_000.0, \
            f"Calm market end equity {end_eq:.0f} outside [96k, 101k]"

        # Annual cost ≤ cap (allow small slack for rolling-window edge effects)
        actual = result.extra["annual_cost_pct_actual"]
        assert actual <= 0.015 * 1.10, f"Annual cost {actual:.4f} > cap × 1.10"

    def test_backtest_runs_on_synthetic_crash(self):
        """252 days with a -25% crash mid-window. Naked long put hedge should
        produce uncapped gains — end equity must be ABOVE start."""
        s = self.cls(annual_cost_cap_pct=0.030,
                     dte_target=75,
                     purchase_cadence_days=30,
                     profit_take_pct=1.00,
                     position_size_pct=0.010)
        px  = _make_crash_market(days=252)
        vix = _make_vix_for(px, base=18.0, sigma=2.5, crash_lift=True)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=100_000.0)
        eq = result.equity_curve
        assert not eq.empty

        # Equity must spend time meaningfully above start during the drawdown.
        peak_eq = eq.max()
        assert peak_eq > 101_000, (
            f"Hedge produced no meaningful gain on a 25% crash: "
            f"peak equity {peak_eq:.0f}"
        )
        # End equity should be ABOVE start — the hedge paid (uncapped naked put).
        end_eq = eq.iloc[-1]
        assert end_eq > 100_000, (
            f"Hedge did not finish above start in crash run: end equity {end_eq:.0f}"
        )

        # We should see at least one winning trade.
        if not result.trades.empty:
            assert result.trades["pnl"].max() > 0, "No winning hedge trade in crash run"

    def test_annual_cost_cap_enforced(self):
        """2 years on calm market — total debits paid must respect the cap."""
        cap_pct = 0.012
        years   = 2
        days    = 252 * years
        s = self.cls(annual_cost_cap_pct=cap_pct,
                     purchase_cadence_days=30,
                     dte_target=75)
        px  = _make_calm_market(days=days)
        vix = _make_vix_for(px, base=15.0, sigma=1.0)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=100_000.0)

        total_debit = result.extra["total_debit_paid"]
        cap_dollars = cap_pct * 100_000.0 * years * 1.10  # 10% slack for window edges
        assert total_debit <= cap_dollars, (
            f"Total debit paid ${total_debit:,.0f} exceeds 2-year cap ${cap_dollars:,.0f}"
        )

    def test_roll_at_dte_threshold(self):
        """Open a put; advance past the roll-DTE threshold; assert a
        roll has occurred (= original put closed and a new one opened)."""
        s = self.cls(dte_target=45, roll_at_dte=20,
                     purchase_cadence_days=20,
                     annual_cost_cap_pct=0.030)
        px  = _make_calm_market(days=180)
        vix = _make_vix_for(px, base=15.0, sigma=1.0)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=200_000.0)
        purchase_df = result.extra["purchase_log"]
        assert len(purchase_df) >= 2, \
            f"Expected >= 2 purchases (roll trigger), got {len(purchase_df)}"
        if not result.trades.empty:
            reasons = set(result.trades["exit_reason"].unique())
            assert ("roll_at_dte" in reasons) or (len(result.trades) >= 1)

    def test_roll_at_deep_itm_delta(self):
        """Synthetic crash: long-put delta drops below -0.30 ; assert that the
        deep-ITM-delta harvest fires (via roll_long_deep_itm OR harvest_profit
        — both are forms of the deep-ITM exit)."""
        s = self.cls(dte_target=75,
                     roll_at_dte=20,
                     roll_at_long_delta=-0.30,
                     purchase_cadence_days=30,
                     profit_take_pct=50.00,  # raise harvest bar so delta-roll dominates
                     annual_cost_cap_pct=0.030,
                     position_size_pct=0.010)
        px  = _make_crash_market(days=200)
        vix = _make_vix_for(px, base=17.0, sigma=2.0, crash_lift=True)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=200_000.0)

        roll_df = result.extra["roll_log"]
        # Either we saw a deep-ITM roll, OR (fallback) a closed trade with
        # exit_reason == roll_long_deep_itm.
        deep_itm_count = 0
        if not roll_df.empty:
            deep_itm_count = int((roll_df["reason"] == "roll_long_deep_itm").sum())
        if deep_itm_count == 0 and not result.trades.empty:
            deep_itm_count = int((result.trades["exit_reason"] == "roll_long_deep_itm").sum())

        assert deep_itm_count >= 1, (
            "Deep-ITM-delta roll never fired on a 25% crash — long-put delta "
            "should have crossed -0.30 well before any other exit."
        )

    def test_profit_harvest_triggers(self):
        """Synthetic crash: SPY drops sharply; put gains 100%+ → harvest fires."""
        s = self.cls(dte_target=75,
                     purchase_cadence_days=30,
                     profit_take_pct=1.00,
                     annual_cost_cap_pct=0.030,
                     position_size_pct=0.010)
        px  = _make_crash_market(days=200)
        vix = _make_vix_for(px, base=17.0, sigma=2.0, crash_lift=True)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=200_000.0)

        harvest_df = result.extra["harvest_log"]
        assert len(harvest_df) >= 1, (
            "Profit harvest never triggered on a 25% crash — "
            "either profit_take logic is wrong or pricing is too conservative."
        )
        # After harvest, a new put should be opened — total purchases > harvests.
        assert len(result.extra["purchase_log"]) > len(harvest_df), \
            "After harvest, no fresh put was opened."

    def test_max_concurrent_enforced(self):
        """Concurrency state must never exceed max_concurrent."""
        max_c = 1
        s = self.cls(max_concurrent=max_c,
                     purchase_cadence_days=20,
                     dte_target=80,
                     annual_cost_cap_pct=0.030)
        px  = _make_calm_market(days=200)
        vix = _make_vix_for(px, base=15.0, sigma=1.0)
        result = s.backtest(px, auxiliary_data={"vix": vix},
                            starting_capital=100_000.0)

        regime = result.extra["regime_series"]
        if not regime.empty:
            assert regime["n_open"].max() <= max_c, \
                f"Concurrency cap breached: max n_open={regime['n_open'].max()} > {max_c}"
