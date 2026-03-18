"""
Strategy registry — metadata for all 30 strategies + lazy factory.
"""

from alan_trader.strategies.base import BaseStrategy, StubStrategy, StrategyStatus

# ─────────────────────────────────────────────────────────────────────────────
# Metadata for all 30 strategies
# ─────────────────────────────────────────────────────────────────────────────

STRATEGY_METADATA: dict[str, dict] = {
    # ── Fully implemented ──────────────────────────────────────────────────
    "options_spread": {
        "display_name": "Spread",
        "type": "ai",
        "status": "active",
        "icon": "🤖",
        "description": "LSTM attention model predicts 5-day price direction → enters bull call or bear put vertical spreads.",
        "asset_class": "equities_options",
        "typical_holding_days": 5,
        "target_sharpe": 1.2,
        "class_path": "alan_trader.strategies.spy_options_spread.OptionsSpreadStrategy",
        # ── capability flags ─────────────────────────────────────────────
        "requires_training": True,   # has a meaningful fit() / train step
        "uses_ml": True,             # uses a neural network (PyTorch)
        "requires_ticker": True,     # needs equity price data
        "required_data": ["price", "vix", "rates", "news"],
    },
    "dividend_arb": {
        "display_name": "Dividend Arbitrage",
        "type": "rule",
        "status": "active",
        "icon": "💰",
        "description": "Buy before ex-dividend date, capture dividend, hedge equity downside with short-dated put.",
        "asset_class": "equities_options",
        "typical_holding_days": 4,
        "target_sharpe": 0.9,
        "class_path": "alan_trader.strategies.dividend_arbitrage.DividendArbitrageStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "vix", "dividends"],
    },
    "vol_arbitrage": {
        "display_name": "Vol Arbitrage",
        "type": "rule",
        "status": "active",
        "icon": "📊",
        "description": (
            "Scans options chain for put-call parity violations. "
            "Executes conversions when calls are overpriced and reversals when puts are overpriced."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 3,
        "target_sharpe": 1.4,
        "class_path": "alan_trader.strategies.vol_arbitrage.VolArbitrageStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "options_chain"],
    },

    # ── VIX strategies ─────────────────────────────────────────────────────
    "vix_mean_reversion": {
        "display_name": "VIX Mean Reversion",
        "type": "rule",
        "status": "stub",
        "description": "Short VXX / buy UVXY puts when VIX spikes far above 20-day MA. Reverse when mean-reverts.",
        "asset_class": "volatility",
        "typical_holding_days": 7,
        "target_sharpe": 1.1,
        "class_path": "",
    },
    "vix_term_structure": {
        "display_name": "VIX Term Structure",
        "type": "rule",
        "status": "stub",
        "description": "Trade VIX futures contango/backwardation: sell front-month when curve is steep contango.",
        "asset_class": "volatility",
        "typical_holding_days": 14,
        "target_sharpe": 1.0,
        "class_path": "",
    },
    "vix_spike_fade": {
        "display_name": "VIX Spike Fade",
        "type": "ai",
        "status": "stub",
        "description": "ML model detects capitulation VIX spikes (>30) and enters SPY bull call spreads.",
        "asset_class": "equities_options",
        "typical_holding_days": 3,
        "target_sharpe": 1.3,
        "class_path": "",
    },

    # ── Pairs trading ──────────────────────────────────────────────────────
    "pairs_spy_qqq": {
        "display_name": "SPY/QQQ Pairs",
        "type": "rule",
        "status": "stub",
        "description": "Statistical arbitrage: mean-revert the SPY/QQQ spread. Cointegration-based entry/exit.",
        "asset_class": "equities",
        "typical_holding_days": 5,
        "target_sharpe": 0.9,
        "class_path": "",
    },
    "pairs_spy_iwm": {
        "display_name": "SPY/IWM Pairs",
        "type": "rule",
        "status": "stub",
        "description": "Large-cap vs small-cap spread trade triggered by Russell/S&P divergence signals.",
        "asset_class": "equities",
        "typical_holding_days": 7,
        "target_sharpe": 0.8,
        "class_path": "",
    },
    "pairs_spy_dia": {
        "display_name": "SPY/DIA Pairs",
        "type": "rule",
        "status": "stub",
        "description": "S&P 500 vs Dow Jones Industrial mean-reversion pairs trade.",
        "asset_class": "equities",
        "typical_holding_days": 5,
        "target_sharpe": 0.7,
        "class_path": "",
    },

    # ── Momentum ───────────────────────────────────────────────────────────
    "momentum_cross_sector": {
        "display_name": "Cross-Sector Momentum",
        "type": "rule",
        "status": "stub",
        "description": "Long top-3 sectors by 12-month momentum, short bottom-3. Monthly rebalance.",
        "asset_class": "equities",
        "typical_holding_days": 21,
        "target_sharpe": 0.9,
        "class_path": "",
    },
    "momentum_12_1": {
        "display_name": "12-1 Price Momentum",
        "type": "rule",
        "status": "stub",
        "description": "Classic Jegadeesh-Titman: 12-month return minus last month. Monthly rebalance.",
        "asset_class": "equities",
        "typical_holding_days": 21,
        "target_sharpe": 0.8,
        "class_path": "",
    },
    "momentum_risk_on_off": {
        "display_name": "Risk-On / Risk-Off",
        "type": "ai",
        "status": "stub",
        "description": "LSTM classifier on macro features: switch between SPY (risk-on) and TLT (risk-off).",
        "asset_class": "equities",
        "typical_holding_days": 10,
        "target_sharpe": 1.0,
        "class_path": "",
    },

    # ── Options structures ──────────────────────────────────────────────────
    "iron_condor_weekly": {
        "display_name": "Weekly Iron Condor",
        "type": "rule",
        "status": "stub",
        "description": "Sell 16-delta iron condors on SPY every Monday. Close at 50% profit or 21 DTE.",
        "asset_class": "equities_options",
        "typical_holding_days": 4,
        "target_sharpe": 1.1,
        "class_path": "",
    },
    "calendar_spread_vix": {
        "display_name": "Calendar Spread (VIX)",
        "type": "rule",
        "status": "stub",
        "description": "Buy back-month VIX call, sell front-month. Profit from term structure collapse.",
        "asset_class": "volatility",
        "typical_holding_days": 14,
        "target_sharpe": 0.9,
        "class_path": "",
    },
    "butterfly_atm": {
        "display_name": "ATM Butterfly",
        "type": "rule",
        "status": "stub",
        "description": "Sell ATM butterfly on low-IV days expecting pinning. 3-day hold.",
        "asset_class": "equities_options",
        "typical_holding_days": 3,
        "target_sharpe": 0.8,
        "class_path": "",
    },

    # ── Earnings ───────────────────────────────────────────────────────────
    "earnings_vol_crush": {
        "display_name": "Earnings Vol Crush",
        "type": "rule",
        "status": "stub",
        "description": "Sell straddles before earnings to capture IV crush after announcement.",
        "asset_class": "equities_options",
        "typical_holding_days": 2,
        "target_sharpe": 1.1,
        "class_path": "",
    },
    "earnings_straddle": {
        "display_name": "Earnings Straddle",
        "type": "rule",
        "status": "stub",
        "description": "Buy ATM straddle before earnings expecting move > implied move.",
        "asset_class": "equities_options",
        "typical_holding_days": 2,
        "target_sharpe": 0.8,
        "class_path": "",
    },
    "earnings_pin_risk": {
        "display_name": "Earnings Pin Risk",
        "type": "ai",
        "status": "stub",
        "description": "Predict pinning to round strikes at expiry after earnings. ML-based.",
        "asset_class": "equities_options",
        "typical_holding_days": 1,
        "target_sharpe": 1.0,
        "class_path": "",
    },

    # ── Macro ──────────────────────────────────────────────────────────────
    "macro_yield_curve": {
        "display_name": "Yield Curve Regime",
        "type": "ai",
        "status": "stub",
        "description": "LSTM on yield curve shape (2s10s, 3m10y) predicts SPY regime for positioning.",
        "asset_class": "equities",
        "typical_holding_days": 20,
        "target_sharpe": 0.9,
        "class_path": "",
    },
    "macro_fed_cycle": {
        "display_name": "Fed Cycle Play",
        "type": "rule",
        "status": "stub",
        "description": "Enter bull spreads at first Fed cut; bear spreads at first hike after long pause.",
        "asset_class": "equities_options",
        "typical_holding_days": 30,
        "target_sharpe": 0.9,
        "class_path": "",
    },
    "macro_inflation_regime": {
        "display_name": "Inflation Regime",
        "type": "ai",
        "status": "stub",
        "description": "Classify inflation regime (rising/stable/falling) via NLP on CPI reports → sector tilt.",
        "asset_class": "equities",
        "typical_holding_days": 21,
        "target_sharpe": 0.8,
        "class_path": "",
    },

    # ── Statistical arbitrage ───────────────────────────────────────────────
    "stat_arb_etf_basket": {
        "display_name": "ETF Basket Stat Arb",
        "type": "rule",
        "status": "stub",
        "description": "Arbitrage mispricing between SPY and its underlying sector ETF basket.",
        "asset_class": "equities",
        "typical_holding_days": 1,
        "target_sharpe": 1.2,
        "class_path": "",
    },
    "stat_arb_sector_rotation": {
        "display_name": "Sector Rotation Arb",
        "type": "rule",
        "status": "stub",
        "description": "Mean-revert sector ETF spreads relative to SPY using PCA residuals.",
        "asset_class": "equities",
        "typical_holding_days": 5,
        "target_sharpe": 0.9,
        "class_path": "",
    },
    "stat_arb_index_recon": {
        "display_name": "Index Reconstitution",
        "type": "rule",
        "status": "stub",
        "description": "Trade additions/deletions to S&P 500 index between announcement and effective date.",
        "asset_class": "equities",
        "typical_holding_days": 10,
        "target_sharpe": 1.1,
        "class_path": "",
    },

    # ── ML variants ────────────────────────────────────────────────────────
    "ml_gradient_boost": {
        "display_name": "Gradient Boost Signal",
        "type": "ai",
        "status": "stub",
        "description": "XGBoost model on 60+ features predicts next-week SPY return direction.",
        "asset_class": "equities",
        "typical_holding_days": 5,
        "target_sharpe": 1.1,
        "class_path": "",
    },
    "ml_transformer_seq": {
        "display_name": "Transformer Sequence",
        "type": "ai",
        "status": "stub",
        "description": "Temporal Fusion Transformer on multi-horizon time series for spread selection.",
        "asset_class": "equities_options",
        "typical_holding_days": 5,
        "target_sharpe": 1.4,
        "class_path": "",
    },
    "ml_ensemble_stacking": {
        "display_name": "Ensemble Stacking",
        "type": "ai",
        "status": "stub",
        "description": "Meta-learner stacks LSTM, XGBoost, and random-forest signals → consensus.",
        "asset_class": "equities_options",
        "typical_holding_days": 5,
        "target_sharpe": 1.3,
        "class_path": "",
    },

    # ── Tail risk / hedges ─────────────────────────────────────────────────
    "tail_risk_long_put": {
        "display_name": "Tail Risk Long Put",
        "type": "rule",
        "status": "stub",
        "description": "Hold 1–5% OTM SPY puts as portfolio insurance. Roll monthly.",
        "asset_class": "equities_options",
        "typical_holding_days": 30,
        "target_sharpe": -0.5,
    },
    "tail_risk_put_spread": {
        "display_name": "Tail Risk Put Spread",
        "type": "rule",
        "status": "stub",
        "description": "Buy 5% OTM put, sell 10% OTM put. Cheaper hedge with defined payoff.",
        "asset_class": "equities_options",
        "typical_holding_days": 30,
        "target_sharpe": -0.3,
        "class_path": "",
    },

    # ── Cross-asset ─────────────────────────────────────────────────────────
    "crypto_corr_spy": {
        "display_name": "Crypto / SPY Correlation",
        "type": "ai",
        "status": "stub",
        "description": "Trade SPY based on BTC/ETH risk-on lead signal from overnight crypto returns.",
        "asset_class": "cross_asset",
        "typical_holding_days": 1,
        "target_sharpe": 0.9,
        "class_path": "",
    },
    "commodities_oil_spy": {
        "display_name": "Oil / SPY Divergence",
        "type": "rule",
        "status": "stub",
        "description": "Enter SPY spreads when CL (crude oil) and equity correlation diverges historically.",
        "asset_class": "cross_asset",
        "typical_holding_days": 5,
        "target_sharpe": 0.8,
        "class_path": "",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

def get_strategy(slug: str) -> BaseStrategy:
    """
    Lazy-load and return an instantiated strategy by slug.
    Returns StubStrategy if not implemented or class_path is empty.
    """
    meta = STRATEGY_METADATA.get(slug)
    if meta is None:
        raise KeyError(f"Unknown strategy slug: {slug!r}")

    class_path = meta.get("class_path", "")
    if not class_path or meta.get("status") == "stub":
        return StubStrategy(slug, meta)

    # Lazy import
    module_path, class_name = class_path.rsplit(".", 1)
    try:
        import importlib
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls()
    except (ImportError, AttributeError) as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not load {class_path}: {e} — using stub")
        return StubStrategy(slug, meta)


def get_all_strategies() -> dict[str, BaseStrategy]:
    """Return dict of slug → strategy instance for all registered strategies."""
    return {slug: get_strategy(slug) for slug in STRATEGY_METADATA}


def get_active_strategies() -> dict[str, BaseStrategy]:
    """Return only strategies with status=active."""
    return {
        slug: get_strategy(slug)
        for slug, meta in STRATEGY_METADATA.items()
        if meta.get("status") == "active"
    }


def registry_dataframe() -> "pd.DataFrame":
    """Return a DataFrame of all strategy metadata (for dashboard table)."""
    import pandas as pd
    rows = []
    for slug, meta in STRATEGY_METADATA.items():
        rows.append({
            "slug": slug,
            "Name": meta["display_name"],
            "Type": meta["type"].upper(),
            "Status": meta["status"].capitalize(),
            "Asset Class": meta.get("asset_class", ""),
            "Typical Hold (days)": meta.get("typical_holding_days", ""),
            "Target Sharpe": meta.get("target_sharpe", ""),
            "Description": meta.get("description", ""),
        })
    return pd.DataFrame(rows).set_index("slug")
