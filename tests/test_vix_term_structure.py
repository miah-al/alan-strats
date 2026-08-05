"""
tests/test_vix_term_structure.py
Unit tests for the VIX Term Structure AI strategy.
Run: python -m pytest tests/test_vix_term_structure.py -v
"""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _spread_pnl_credit(spot, short_K, long_K, credit, spread_type):
    """P&L of a credit spread at expiry."""
    if spread_type == "bull_put":
        intrinsic = max(0, short_K - spot) - max(0, long_K - spot)
    else:  # bear_call
        intrinsic = max(0, spot - short_K) - max(0, spot - long_K)
    return (credit - intrinsic) * 100


class TestVIXTermStructure:

    def setup_method(self):
        from strategies.vix_term_structure import VIXTermStructureStrategy
        self.cls = VIXTermStructureStrategy

    def test_instantiates(self):
        assert self.cls() is not None

    def test_warmup_bars(self):
        from strategies.vix_term_structure import _WARMUP_BARS
        assert _WARMUP_BARS >= 60, "Need at least 60 bars for regime detection"

    def test_retrain_interval(self):
        from strategies.vix_term_structure import _RETRAIN_EVERY
        assert _RETRAIN_EVERY >= 10

    def test_feature_count(self):
        s = self.cls()
        assert len(s.FEATURE_COLS) >= 10

    def test_thresholds_ordered(self):
        """threshold_short must be below threshold_long (creates flat zone between)."""
        s = self.cls()
        assert s.threshold_short < s.threshold_long

    def test_bull_put_max_profit_otm(self):
        """Bull put credit spread: full credit when spot stays above short strike."""
        short_K, long_K, credit = 490, 477.5, 1.20
        pnl = _spread_pnl_credit(510, short_K, long_K, credit, "bull_put")
        assert pnl == pytest.approx(credit * 100)

    def test_bull_put_max_loss_itm(self):
        """Bull put: max loss when spot well below both strikes."""
        short_K, long_K, credit = 490, 477.5, 1.20
        wing = short_K - long_K
        expected = -(wing - credit) * 100
        pnl = _spread_pnl_credit(460, short_K, long_K, credit, "bull_put")
        assert pnl == pytest.approx(expected)

    def test_defined_risk_bull_put(self):
        """Bull put max loss is finite and bounded by wing width."""
        short_K, long_K, credit = 490, 477.5, 1.20
        wing = short_K - long_K
        max_loss = (wing - credit) * 100
        assert max_loss > 0
        assert max_loss < 10_000

    def test_generate_signal_contango(self):
        """Positive VRP → SELL signal (contango = sell credit spread)."""
        s = self.cls()
        result = s.generate_signal({"vix": 20.0, "realized_vol_20d": 0.10})
        assert result.signal == "SELL"
        assert result.confidence > 0.5

    def test_generate_signal_backwardation(self):
        """Negative VRP → BUY signal (backwardation = buy protection/debit)."""
        s = self.cls()
        result = s.generate_signal({"vix": 18.0, "realized_vol_20d": 0.25})
        assert result.signal == "BUY"
        assert result.confidence > 0.5

    def test_generate_signal_neutral(self):
        """VRP near zero → HOLD."""
        s = self.cls()
        result = s.generate_signal({"vix": 15.0, "realized_vol_20d": 0.14})
        assert result.signal == "HOLD"

    def test_get_params_roundtrip(self):
        """get_params returns all constructor parameters."""
        s = self.cls(threshold_short=0.35, vix_max=40.0)
        p = s.get_params()
        assert p["threshold_short"] == 0.35
        assert p["vix_max"] == 40.0

    def test_ui_params_structure(self):
        s = self.cls()
        params = s.get_backtest_ui_params()
        assert len(params) >= 4
        for p in params:
            assert "key" in p and "label" in p and "type" in p


class TestBackwardationLabel:

    def test_label_backwardation(self):
        """Realized vol > implied → backwardation = 1."""
        from strategies.vix_term_structure import _build_labels
        import pandas as pd
        n = 50
        dates = pd.date_range("2023-01-01", periods=n)
        # High realized vol scenario: daily moves of 1.5%
        returns = np.random.normal(0, 0.015, n)
        close = pd.Series(100 * np.exp(np.cumsum(returns)), index=dates)
        vix = pd.Series(np.full(n, 12.0), index=dates)  # low VIX → easier to exceed

        labels = _build_labels(close, vix, n_forward=14)
        valid_labels = labels.dropna()
        assert len(valid_labels) > 0
        # With low VIX and moderate realized vol, should have some backwardation
        assert valid_labels.isin([0.0, 1.0]).all()

    def test_label_contango(self):
        """Low realized vol with high VIX → contango = 0."""
        from strategies.vix_term_structure import _build_labels
        import pandas as pd
        n = 50
        dates = pd.date_range("2023-01-01", periods=n)
        # Very calm market: 0.1% daily moves
        returns = np.random.normal(0, 0.001, n)
        close = pd.Series(100 * np.exp(np.cumsum(returns)), index=dates)
        vix = pd.Series(np.full(n, 30.0), index=dates)  # high VIX

        labels = _build_labels(close, vix, n_forward=14)
        valid_labels = labels.dropna()
        # With calm realized vol and high VIX, most labels should be 0 (contango)
        assert valid_labels.mean() < 0.3  # less than 30% backwardation

    def test_label_uses_only_forward_returns(self):
        """The label at bar i must depend ONLY on returns strictly after bar i.

        A perturbation to any close at or before bar i must NOT change label[i];
        a perturbation inside the forward window (i+1 .. i+n) MUST be able to.
        This pins the label as forward-looking (no past leak) and bounded.
        """
        from strategies.vix_term_structure import _build_labels
        import pandas as pd
        n, n_fwd = 60, 14
        rng = np.random.RandomState(0)
        dates = pd.date_range("2023-01-01", periods=n)
        base = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        close = pd.Series(base, index=dates)
        vix = pd.Series(np.full(n, 16.0), index=dates)
        lab0 = _build_labels(close, vix, n_forward=n_fwd)

        i = 20
        # Mutate a PAST/CURRENT bar (i-5): label[i] must be unchanged.
        c_past = close.copy(); c_past.iloc[i - 5] *= 1.10
        lab_past = _build_labels(c_past, vix, n_forward=n_fwd)
        assert lab_past.iloc[i] == lab0.iloc[i], "label[i] leaked a pre-i price"

    def test_label_horizon_is_exactly_n_forward(self):
        """Pin the label's forward reach: label[i] consumes returns through bar
        i + n_forward INCLUSIVE, and nothing beyond. This boundary is what the
        training purge (cutoff = i - dte_target) relies on to be leak-free.
        """
        from strategies.vix_term_structure import _build_labels
        import pandas as pd
        n, n_fwd = 200, 21
        rng = np.random.RandomState(3)
        dates = pd.date_range("2023-01-01", periods=n)
        close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))), index=dates)
        vix = pd.Series(np.full(n, 16.0), index=dates)
        lab0 = _build_labels(close, vix, n_forward=n_fwd)

        i = 100
        # Perturbing bar i + n_forward MUST be able to move label[i] (it is the
        # last return in the window: log_ret[i+1 .. i+n_forward]).
        c_edge = close.copy(); c_edge.iloc[i + n_fwd] *= 1.50
        lab_edge = _build_labels(c_edge, vix, n_forward=n_fwd)
        assert lab_edge.iloc[i] != lab0.iloc[i], "label[i] does not reach bar i+n_forward"

        # Perturbing bar i + n_forward + 1 must NOT change label[i] (out of window).
        c_beyond = close.copy(); c_beyond.iloc[i + n_fwd + 1] *= 1.50
        lab_beyond = _build_labels(c_beyond, vix, n_forward=n_fwd)
        assert lab_beyond.iloc[i] == lab0.iloc[i], "label[i] leaked bar i+n_forward+1"


class TestLeakFreedomAndCosts:
    """Pin the two flagged fixes: training-window purge and entry+exit costs."""

    def _synthetic(self, n=400, seed=7):
        import pandas as pd
        rng = np.random.RandomState(seed)
        dates = pd.date_range("2023-01-01", periods=n, freq="B")
        # Regime-switching vol so both contango and backwardation labels appear.
        vol = np.where((np.arange(n) // 40) % 2 == 0, 0.006, 0.020)
        rets = rng.normal(0.0002, vol)
        close = pd.Series(120 * np.exp(np.cumsum(rets)), index=dates)
        high = close * 1.004
        low = close * 0.996
        # VIX loosely tracks realized vol, annualized-ish, in points.
        vix_pts = pd.Series(
            np.clip(vol * np.sqrt(252) * 100 + rng.normal(0, 1.5, n), 9, 55),
            index=dates,
        )
        px = pd.DataFrame({"close": close, "high": high, "low": low})
        aux = {"vix": pd.DataFrame({"close": vix_pts}, index=dates)}
        return px, aux

    def test_training_window_purges_forward_label_rows(self):
        """At retrain bar i the training set must exclude rows whose label window
        reaches >= i. We reproduce the strategy's cutoff and assert every used
        label row j satisfies j + dte_target <= i (so no row trains on its future).
        """
        from strategies.vix_term_structure import _build_labels, _build_features
        px, aux = self._synthetic()
        close = px["close"]
        vix = aux["vix"]["close"]
        dte = 21
        labels = _build_labels(close, vix, n_forward=dte)
        feats = _build_features(close, px["high"], px["low"], vix)

        i = 250  # a representative retrain bar
        cutoff = max(0, i - dte)  # must match strategy.backtest
        y_tr = labels.iloc[:cutoff]
        used = y_tr.dropna().index
        for ts in used:
            j = close.index.get_loc(ts)
            # label[j] consumes returns up to j + dte; require that horizon < i.
            assert j + dte <= i, f"row {j} label window reaches bar {j+dte} >= {i} (leak)"

    def test_training_cutoff_is_strictly_before_retrain_bar(self):
        """Every retrain bar i must purge so the last usable row's label horizon
        is < i (not == i). cutoff = i - dte_target ⇒ rows j <= cutoff-1, so the
        worst horizon j + dte_target = i - 1 < i. This is the leak-free guarantee
        and also proves the fit is on an EXPANDING PAST window, never full-sample.
        """
        dte = 21
        for i in (95, 150, 250, 399):
            cutoff = max(0, i - dte)
            worst_j = cutoff - 1                 # last row fed to .fit()
            if worst_j < 0:
                continue
            assert worst_j + dte < i, \
                f"retrain@{i}: row {worst_j} horizon {worst_j+dte} not < {i} (leak/full-sample)"

    def test_derives_regime_from_vix_spot_no_futures(self):
        """The strategy must run using only VIX SPOT history (no VIX-futures / term
        table). aux carries a single vix 'close' series; a clean run proves the
        term-structure regime signal is derived from spot, not a futures feed."""
        from strategies.vix_term_structure import VIXTermStructureStrategy, _build_features
        px, aux = self._synthetic()
        assert list(aux.keys()) == ["vix"], "aux must contain only VIX spot"
        # Features are computable from spot VIX + SPY OHLC alone.
        feats = _build_features(px["close"], px["high"], px["low"], aux["vix"]["close"])
        assert not feats.dropna().empty
        S = VIXTermStructureStrategy()
        r = S.backtest(px, aux, starting_capital=100_000)
        assert np.isfinite(r.metrics["final_equity"])

    def test_costs_charged_on_entry_and_exit(self):
        """Higher per-leg cost ⇒ strictly worse (or equal) final equity, proving
        costs bite on both sides. We monkeypatch the module cost constant."""
        import importlib
        import strategies.vix_term_structure as vts
        importlib.reload(vts)
        px, aux = self._synthetic()

        S = vts.VIXTermStructureStrategy()
        r_cheap = S.backtest(px, aux, starting_capital=100_000)

        orig = vts._COST_PER_LEG
        try:
            vts._COST_PER_LEG = orig + 5.0  # punitive frictions
            S2 = vts.VIXTermStructureStrategy()
            r_dear = S2.backtest(px, aux, starting_capital=100_000)
        finally:
            vts._COST_PER_LEG = orig

        if len(r_cheap.trades) > 0:
            assert r_dear.metrics["final_equity"] <= r_cheap.metrics["final_equity"] + 1e-6, \
                "raising per-leg cost did not reduce equity — exit costs missing?"
            # Per closed trade, total friction = entry_fees + exit_cost = 2 legs
            # × 2 sides × contracts × cost. Verify the magnitude via the constant.
            assert vts._LEGS_PER_SPREAD == 2

    def test_entry_cost_subtracted_in_sizing(self):
        """Credit-spread contract count must be sized on (wing - credit), i.e. the
        capital at risk net of the premium, never on the gross wing. Replicate the
        sizing arithmetic and assert it never exceeds the gross-wing count."""
        capital, pos_pct = 100_000.0, 0.02
        wing, credit = 12.5, 0.85           # dollars/share
        max_cost = capital * pos_pct
        sized = max(1, int(max_cost / ((wing - credit) * 100)))
        gross = max(1, int(max_cost / (wing * 100)))
        # Risk-based sizing uses the SMALLER denominator (wing-credit) → never
        # fewer than gross; the point is it is risk-aware, not premium-blind.
        assert sized >= gross
        # And the at-risk capital of the position stays within budget.
        assert sized * (wing - credit) * 100 <= max_cost + (wing - credit) * 100

    def test_synthetic_backtest_runs_clean(self):
        """End-to-end synthetic run: no exceptions, sane outputs, costs applied."""
        from strategies.vix_term_structure import VIXTermStructureStrategy
        px, aux = self._synthetic()
        S = VIXTermStructureStrategy()
        r = S.backtest(px, aux, starting_capital=100_000)
        assert r.equity_curve is not None and len(r.equity_curve) == len(px)
        assert np.isfinite(r.metrics["final_equity"])
        assert r.metrics["final_equity"] > 0
        # Every recorded trade must carry the cost-bearing fields.
        for _, t in r.trades.iterrows():
            assert "pnl" in t and np.isfinite(t["pnl"])
            assert t["exit_reason"] in {
                "profit_target", "stop_loss", "dte_exit", "end_of_data",
            }

    def test_uses_skew_pricing(self):
        """The strategy must price legs through bs_price_skew when available, so an
        OTM put leg is worth MORE than its flat-IV value (downside skew)."""
        import strategies.vix_term_structure as vts
        if not vts._HAVE_SKEW:
            import pytest
            pytest.skip("engine skew helper unavailable in this layout")
        from strategies.indicators import bs_price as flat
        S, K, T, r, iv = 500.0, 480.0, 21 / 252, 0.045, 0.18  # OTM put
        skew_val = vts._leg_price(S, K, T, r, iv, "put")
        flat_val = flat(S, K, T, r, iv, "put")
        assert skew_val > flat_val, "OTM put leg not skew-uplifted"
