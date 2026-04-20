"""
Strategy registry — metadata for all strategies + lazy factory.
"""

from alan_trader.strategies.base import BaseStrategy, StubStrategy, StrategyStatus

# ─────────────────────────────────────────────────────────────────────────────
# Metadata for all 30 strategies
# ─────────────────────────────────────────────────────────────────────────────

STRATEGY_METADATA: dict[str, dict] = {
    # ── Iron Condor strategies (quant-designed, replacing generic options_spread) ──
    "iron_condor_ai": {
        "display_name": "Iron Condor — AI",
        "type": "ai",
        "status": "active",
        "icon": "🎯",
        "description": (
            "AI-powered Iron Condor. Gradient boosting model predicts range-bound conditions "
            "using 18 features (IVR, term structure, momentum, VIX regime, macro). "
            "Strike placement adapts to regime. Walk-forward: retrains every 30 bars."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 24,
        "target_sharpe": 1.8,
        "class_path": "alan_trader.strategies.iron_condor_ai.IronCondorAIStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": True,
        "required_data": ["price", "vix", "rates"],
        "has_screener": True,
    },
    "iron_condor_rules": {
        "display_name": "Iron Condor — Rules",
        "type": "rule",
        "status": "active",
        "icon": "📐",
        "description": (
            "Rules-based Iron Condor. Enters when IVR ≥ 45%, VIX 16–35, ADX ≤ 22 (range-bound), "
            "and ATR is calm. 50% profit target, 21 DTE time exit, 2× stop loss. "
            "Transparent, auditable, battle-tested rules from 30 years of quant experience."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 24,
        "target_sharpe": 1.5,
        "class_path": "alan_trader.strategies.iron_condor_rules.IronCondorRulesStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "vix"],
        "has_screener": True,
    },
    "conversion_arb": {
        "display_name": "Conversion Arb (Div)",
        "type": "rule",
        "status": "inactive",
        "icon": "⚖️",
        "description": (
            "⚠️ Requires combo orders (stock + options) not supported atomically on Robinhood. "
            "Edge is sub-10bps and wiped by execution slippage at retail. Needs IBKR + real-time NBBO. "
            "True dividend arb via put-call parity — theoretical edge is real but not retail-executable."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 5,
        "target_sharpe": 1.1,
        "class_path": None,
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "vix", "dividends"],
        "has_screener": False,
    },
    "dividend_arb": {
        "display_name": "Dividend Arbitrage",
        "type": "rule",
        "status": "inactive",
        "icon": "💰",
        "description": (
            "⚠️ No durable edge: ATM put hedge cost ≈ dividend yield in efficient markets. "
            "Tax treatment is punitive for short holds in taxable accounts. "
            "Expected Sharpe 0.4–0.7 before tax drag. Dropped from active trading."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 4,
        "target_sharpe": 0.9,
        "class_path": None,
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "vix", "dividends"],
        "has_screener": False,
    },
    "vol_arbitrage": {
        "display_name": "IV Skew Premium Capture",
        "type": "rule",
        "status": "active",
        "icon": "📊",
        "description": (
            "Harvests structural put IV overpricing via a fully defined-risk, RH-compliant spread. "
            "Bull put spread at skew strike + long call + bear call spread hedge. 5 legs, max loss defined at entry."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 3,
        "target_sharpe": 1.4,
        "class_path": "alan_trader.strategies.vol_arbitrage.VolArbitrageStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "options_chain"],
        "has_screener": True,
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
        "display_name": "VIX Term Structure AI",
        "type": "ai",
        "status": "active",
        "icon": "📉",
        "description": (
            "GBM classifier predicts VIX contango vs backwardation regime. "
            "Sells bull put credit spreads on SPY in contango (P < 0.40). "
            "Buys bear put debit spreads in backwardation (P > 0.60). "
            "12 features: VIX momentum, vol-of-vol, IV-RV spread, SPY trend. Walk-forward, 90-bar warmup."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 14,
        "target_sharpe": 1.3,
        "class_path": "alan_trader.strategies.vix_term_structure.VIXTermStructureStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": False,
        "required_data": ["price", "vix"],
        "has_screener": True,
    },
    "vix_spike_fade": {
        "display_name": "VIX Spike Fade",
        "type": "rule",
        "status": "active",
        "icon": "📉",
        "description": (
            "Buys bull call spreads on any broad-market ticker (e.g. SPY, QQQ, IWM) during "
            "VIX panic spikes (VIX > 25 and 30%+ above 20-day avg). Captures mean-reversion of "
            "fear-driven volatility within 5-15 days. Ticker is a parameter — no hardcoding."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 10,
        "target_sharpe": 1.8,
        "class_path": "alan_trader.strategies.vix_spike_fade.VIXSpikeFadeStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "vix"],
        "has_screener": True,
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
        "display_name": "Earnings Vol Crush — AI",
        "type": "ai",
        "status": "active",
        "icon": "💥",
        "description": (
            "Enters credit spread after earnings gap when IV is still elevated but directional risk is resolved. "
            "Gap up → bear call spread above gap. Gap down → bull put spread below gap. "
            "GBM predicts P(stock contained) using gap magnitude, IVR, and vol context. "
            "Walk-forward, 30-event warmup."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 10,
        "target_sharpe": 1.2,
        "class_path": "alan_trader.strategies.earnings_vol_crush.EarningsVolCrushStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": True,
        "required_data": ["price", "vix"],
        "has_screener": True,
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

    # ── Systematic vol selling ───────────────────────────────────────────────
    "wheel_strategy": {
        "display_name": "The Wheel",
        "type": "rule",
        "status": "stub",
        "icon": "🎡",
        "description": (
            "Sell cash-secured puts on pullbacks. When assigned, sell covered calls at or above cost basis. "
            "Repeat until called away. Pure theta extraction with defined equity entry."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 30,
        "target_sharpe": 1.0,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price", "options_chain"],
    },
    "0dte_condor": {
        "display_name": "0-DTE Iron Condor",
        "type": "rule",
        "status": "stub",
        "icon": "⚡",
        "description": (
            "Sell same-day-expiry SPY/SPX iron condors at the open. "
            "Place wings at 1-sigma expected move. Close at 50% profit or 200% loss. "
            "Exploits the steepest theta-decay window in the options lifecycle."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 1,
        "target_sharpe": 1.2,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price", "options_chain", "vix"],
    },
    "iv_rank_credit": {
        "display_name": "IV Rank Credit Spread",
        "type": "hybrid",
        "status": "stub",
        "icon": "📐",
        "description": (
            "Enter short-premium positions only when IV Rank > 50th percentile (options are expensive). "
            "Select spread type (bull put or bear call) based on trend filter. "
            "Systematically harvests volatility risk premium when it is statistically elevated."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 21,
        "target_sharpe": 1.2,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price", "options_chain", "vix"],
    },
    "vix_futures_roll": {
        "display_name": "VIX Futures Roll Yield",
        "type": "rule",
        "status": "stub",
        "icon": "🌀",
        "description": (
            "Systematically short front-month VIX futures when the VIX term structure is in contango "
            "(spot < M1 < M2). Harvest the roll-down yield. Size position by steepness of contango. "
            "Similar to the SVXY / XIV strategy but with explicit position limits."
        ),
        "asset_class": "volatility",
        "typical_holding_days": 30,
        "target_sharpe": 1.1,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["vix", "vix_futures"],
    },
    "tail_risk_collar": {
        "display_name": "Zero-Cost Collar",
        "type": "rule",
        "status": "stub",
        "icon": "🛡️",
        "description": (
            "Buy OTM SPY put (downside protection), fund it by selling OTM call (upside cap). "
            "Target near-zero net premium. Converts long equity exposure into a defined risk/reward band. "
            "Useful as a portfolio-level hedge during elevated drawdown risk."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 30,
        "target_sharpe": 0.4,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price", "options_chain", "vix"],
    },

    # ── Intraday / microstructure ────────────────────────────────────────────
    "opening_range_breakout": {
        "display_name": "Opening Range Breakout",
        "type": "hybrid",
        "status": "stub",
        "icon": "🔔",
        "description": (
            "Define the high/low of the first 30 minutes after open (ORB). "
            "Enter long call spread on break above range, put spread on break below. "
            "ML filter qualifies breaks by volume confirmation and overnight gap alignment."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 1,
        "target_sharpe": 1.1,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["price_intraday", "volume"],
    },
    "vwap_reversion": {
        "display_name": "VWAP Mean Reversion",
        "type": "rule",
        "status": "stub",
        "icon": "📉",
        "description": (
            "Enter when SPY deviates more than 0.4% from anchored VWAP with declining volume. "
            "Target reversion to VWAP within the session. "
            "High win rate in low-volatility trending sessions; skip on high-VIX days."
        ),
        "asset_class": "equities",
        "typical_holding_days": 1,
        "target_sharpe": 1.0,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price_intraday", "volume"],
    },
    "gap_fade": {
        "display_name": "Gap Fade",
        "type": "hybrid",
        "status": "stub",
        "icon": "🪃",
        "description": (
            "When SPY gaps up or down more than 0.5% at the open without fundamental news catalyst, "
            "fade the gap expecting mean reversion to prior close by midday. "
            "ML model filters out gap-and-go days using pre-market volume + futures momentum."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 1,
        "target_sharpe": 1.0,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["price_intraday", "futures", "news"],
    },

    # ── Event-driven ─────────────────────────────────────────────────────────
    "fomc_event_straddle": {
        "display_name": "FOMC Event Straddle",
        "type": "rule",
        "status": "stub",
        "icon": "🏦",
        "description": (
            "Buy ATM SPY straddle 3 days before scheduled FOMC meeting. "
            "Sell one leg immediately after the announcement, hold survivor for follow-through. "
            "Captures the IV expansion into the event and the directional move after."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 5,
        "target_sharpe": 0.9,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price", "options_chain", "vix", "fomc_calendar"],
    },
    "earnings_drift": {
        "display_name": "Post-Earnings Drift",
        "type": "ai",
        "status": "stub",
        "icon": "📣",
        "description": (
            "Exploit the PEAD (post-earnings announcement drift) anomaly: stocks that beat by large margins "
            "continue drifting upward for 5–20 days. ML model ranks magnitude of surprise vs IV. "
            "Enter bull call spread the morning after earnings; exit at 10-day mark or 50% profit."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 10,
        "target_sharpe": 1.1,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["price", "earnings", "options_chain"],
    },
    "expiry_max_pain": {
        "display_name": "OpEx Max Pain Pin",
        "type": "rule",
        "status": "stub",
        "icon": "📌",
        "description": (
            "On expiration Fridays, calculate the max-pain strike (where total option value is minimized). "
            "Enter ATM butterfly centered on max-pain when spot is within 0.5% of the pin. "
            "Market makers' delta hedging tends to pin prices near this level into close."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 1,
        "target_sharpe": 0.9,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price", "options_chain"],
    },
    "turn_of_month": {
        "display_name": "Turn-of-Month Effect",
        "type": "rule",
        "status": "stub",
        "icon": "🗓️",
        "description": (
            "Enter bull call spreads on SPY on the last trading day of each month; close on day +3. "
            "Exploits the systematic end-of-month institutional rebalancing and pension fund inflows "
            "that historically produce a 4-day positive edge around month-end."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 4,
        "target_sharpe": 0.8,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price", "options_chain"],
    },

    # ── Alt data / flow signals ──────────────────────────────────────────────
    "options_flow_scanner": {
        "display_name": "Options Flow Scanner",
        "type": "ai",
        "status": "stub",
        "icon": "🌊",
        "description": (
            "Detect unusually large block and sweep trades in the options market (> 10× average daily volume "
            "on a single strike). ML model scores each flow event by size, urgency (AON vs sweep), "
            "and direction vs existing OI. Follow smart-money directional bets with defined-risk spreads."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 3,
        "target_sharpe": 1.2,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["options_chain", "price"],
    },
    "news_sentiment_nlp": {
        "display_name": "News Sentiment NLP",
        "type": "ai",
        "status": "stub",
        "icon": "📰",
        "description": (
            "Fine-tuned FinBERT model scores real-time news articles and earnings call transcripts. "
            "Aggregate daily sentiment score across top stories. Enter bull/bear spreads when sentiment "
            "diverges sharply from recent price action (sentiment leads price by 1–3 days)."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 3,
        "target_sharpe": 1.0,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["price", "news"],
    },
    "gex_positioning": {
        "display_name": "Dealer Gamma Exposure",
        "type": "rule",
        "status": "active",
        "icon": "⚙️",
        "description": (
            "Classifies the volatility regime from Dealer Gamma Exposure (GEX) and sizes SPY / cash "
            "exposure accordingly. Positive GEX → dealers long gamma → vol-suppressed → heavy equity. "
            "Negative GEX → dealers short gamma → moves amplified → cut exposure. "
            "Live mode uses Polygon options chain; backtest uses VIX as a GEX proxy."
        ),
        "asset_class": "equities",
        "typical_holding_days": 5,
        "target_sharpe": 1.1,
        "class_path": "alan_trader.strategies.gex_positioning.GexPositioningStrategy",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price", "vix"],
    },
    "short_squeeze_detector": {
        "display_name": "Short Squeeze Detector",
        "type": "ai",
        "status": "stub",
        "icon": "🚀",
        "description": (
            "Screen for stocks with short interest > 20% of float, high borrow cost, and a positive "
            "catalyst trigger (beat + raise, breakout on volume). ML model scores squeeze potential. "
            "Enter OTM bull call spreads sized for asymmetric payoff on explosive moves."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 5,
        "target_sharpe": 1.3,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["price", "short_interest", "options_chain", "news"],
    },

    # ── Technical / systematic trend ─────────────────────────────────────────
    "trend_ma_crossover": {
        "display_name": "Dual MA Crossover",
        "type": "rule",
        "status": "stub",
        "icon": "📈",
        "description": (
            "50/200 SMA golden cross → buy bull call spread; death cross → buy bear put spread on SPY. "
            "Hold until opposite crossover. Use spread instead of equity for defined max loss. "
            "Classic trend-following applied to ETF options for leverage efficiency."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 60,
        "target_sharpe": 0.7,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price"],
    },
    "bollinger_squeeze": {
        "display_name": "Bollinger Band Squeeze",
        "type": "hybrid",
        "status": "stub",
        "icon": "🗜️",
        "description": (
            "Detect volatility contraction (Bollinger Bands narrowing to 6-month low). Enter long straddle "
            "or directional spread on the initial breakout bar with volume confirmation. "
            "ML classifier predicts breakout direction using order flow and macro regime context."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 5,
        "target_sharpe": 1.0,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["price", "volume", "vix"],
    },
    "rsi_mean_reversion": {
        "display_name": "RSI Extreme Reversion",
        "type": "rule",
        "status": "stub",
        "icon": "↩️",
        "description": (
            "Enter bull put spread when SPY 2-period RSI drops below 10 (extreme oversold). "
            "Enter bear call spread when RSI exceeds 90. "
            "Larry Connors-style high-win-rate mean reversion; tight hold of 2–4 days."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 3,
        "target_sharpe": 1.1,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price"],
    },

    # ── Regime-aware ML ──────────────────────────────────────────────────────
    "regime_hmm": {
        "display_name": "HMM Regime Classifier",
        "type": "ai",
        "status": "stub",
        "icon": "🔮",
        "description": (
            "Hidden Markov Model on daily returns, realized vol, and VIX detects market regime: "
            "bull (low vol, trending), bear (high vol, trending), or choppy (high vol, mean-reverting). "
            "Acts as a master filter — routes signals from other strategies through regime gating."
        ),
        "asset_class": "equities",
        "typical_holding_days": 0,   # meta-strategy, no direct positions
        "target_sharpe": 0.0,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["price", "vix"],
    },
    "reinforcement_agent": {
        "display_name": "RL Execution Agent",
        "type": "ai",
        "status": "stub",
        "icon": "🧠",
        "description": (
            "Proximal Policy Optimization (PPO) agent learns when to enter, size, and exit spread positions. "
            "State space: price features, Greeks, portfolio P&L, time features. "
            "Reward: risk-adjusted P&L penalized by drawdown. Trained in sim, validated on paper account."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 5,
        "target_sharpe": 1.5,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["price", "options_chain", "vix"],
    },
    "neural_regime_transformer": {
        "display_name": "Regime Transformer",
        "type": "ai",
        "status": "stub",
        "icon": "🔬",
        "description": (
            "Temporal Fusion Transformer trained on 40+ macro and technical features. "
            "Outputs probability distribution over 5 regimes (crash, bear, chop, bull, melt-up). "
            "Used to dynamically tilt portfolio allocation across all other strategies."
        ),
        "asset_class": "equities",
        "typical_holding_days": 0,
        "target_sharpe": 0.0,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["price", "vix", "rates", "macro"],
    },
    "online_adaptive_model": {
        "display_name": "Online Adaptive LSTM",
        "type": "ai",
        "status": "stub",
        "icon": "🔄",
        "description": (
            "LSTM that updates weights continuously using a sliding 60-day window (online learning). "
            "Adapts to regime shifts without full retraining. "
            "Exponentially weighted loss favours recent data. Replaces static weekly retraining."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 5,
        "target_sharpe": 1.3,
        "class_path": "",
        "requires_training": True,
        "uses_ml": True,
        "required_data": ["price", "vix", "rates"],
    },

    # ── Portfolio construction ────────────────────────────────────────────────
    "risk_parity_alloc": {
        "display_name": "Risk Parity Allocation",
        "type": "rule",
        "status": "stub",
        "icon": "⚖️",
        "description": (
            "Allocate capital across active strategies so each contributes equal marginal risk "
            "(equal volatility contribution). Rebalance weekly. "
            "Prevents any single strategy from dominating portfolio drawdown."
        ),
        "asset_class": "portfolio",
        "typical_holding_days": 7,
        "target_sharpe": 1.0,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["strategy_returns"],
    },
    "min_variance_hedge": {
        "display_name": "Minimum Variance Hedge",
        "type": "rule",
        "status": "stub",
        "icon": "🧮",
        "description": (
            "Continuously estimate the portfolio beta to SPY and overlay an SPX put spread hedge "
            "sized to neutralise 80% of directional market exposure. "
            "Targets near-zero portfolio beta while preserving strategy alpha."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 30,
        "target_sharpe": 0.6,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price", "options_chain", "strategy_returns"],
    },

    # ── Fixed income / rates signals ─────────────────────────────────────────
    "rates_spy_rotation_options": {
        "display_name": "TLT / SPY Rotation (Options)",
        "type": "rule",
        "status": "active",
        "icon": "🎯",
        "description": (
            "Long calls and puts only — no short selling. "
            "Same regime detection as TLT/SPY Rotation (Growth/Inflation/Fear/Risk-On) "
            "but positions are long calls on the favored asset or long puts in Inflation. "
            "Retail-friendly: max loss = premium paid."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 30,
        "target_sharpe": 0.7,
        "class_path": "alan_trader.strategies.rates_spy_rotation_options.RatesSpyRotationOptionsStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": False,
        "required_data": ["price", "rates", "tlt", "vix", "spy_options", "tlt_options"],
    },
    "rates_spy_rotation": {
        "display_name": "TLT / SPY Rotation",
        "type": "rule",
        "status": "active",
        "icon": "🔁",
        "description": (
            "Rotate between SPY and TLT based on rate-equity regime: Growth / Inflation / Fear / Risk-On. "
            "Regime detected from 20-day yield change + 20-day SPY return; 3-day confirmation before switching. "
            "Classic flight-to-safety tactical asset allocation with defined per-regime weights."
        ),
        "asset_class": "equities",
        "typical_holding_days": 21,
        "target_sharpe": 0.8,
        "class_path": "alan_trader.strategies.rates_spy_rotation.RatesSpyRotationStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": False,
        "required_data": ["price", "rates", "tlt"],
        "has_screener": True,
    },
    "vol_calendar_spread": {
        "display_name": "Vol Regime Calendar Spread",
        "type": "ai",
        "status": "active",
        "icon": "📅",
        "description": (
            "XGBoost 3-class classifier predicts IV compression / expansion for any optionable ticker. "
            "COMPRESS → short calendar (credit). EXPAND → long calendar (debit). "
            "16 features across IV term structure, VRP, market context, and news sentiment."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 21,
        "target_sharpe": 1.2,
        "class_path": "alan_trader.strategies.vol_calendar_spread.VolCalendarSpreadStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": True,
        "required_data": ["price", "options_chain", "vix", "news"],
        "has_screener": True,
    },
    "ivr_credit_spread": {
        "display_name": "IVR Credit Spread",
        "type": "rule",
        "status": "active",
        "icon": "💹",
        "description": "Sells defined-risk vertical spreads on any liquid optionable ticker when IV rank ≥ 50%. Bull put spread in uptrend, bear call spread in downtrend. Harvests the variance risk premium systematically. Ticker is a parameter.",
        "asset_class": "equities_options",
        "typical_holding_days": 21,
        "target_sharpe": 1.2,
        "class_path": "alan_trader.strategies.ivr_credit_spread.IVRCreditSpreadStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "vix"],
        "has_screener": True,
    },
    "credit_spread_signal": {
        "display_name": "Credit Spread Canary",
        "type": "rule",
        "status": "stub",
        "icon": "🐦",
        "description": (
            "Monitor HYG/LQD credit spread as a leading indicator for equity stress. "
            "When IG-HY spread widens > 2σ above 60-day mean, shift to defensive bear call spreads. "
            "Credit markets price in stress 2–3 weeks before equities reprice."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 14,
        "target_sharpe": 0.9,
        "class_path": "",
        "requires_training": False,
        "uses_ml": False,
        "required_data": ["price", "credit_spreads"],
    },

    # ── Earnings strategies ───────────────────────────────────────────────────
    "earnings_iv_crush": {
        "display_name": "Earnings IV Crush",
        "type": "rule",
        "status": "active",
        "icon": "🎯",
        "description": (
            "Sells defined-risk iron condors 1 day before earnings. Captures the systematic "
            "overpricing of post-earnings uncertainty (implied move consistently exceeds actual "
            "move by 20-40%). Closes at next-day open after IV collapse."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 1,
        "target_sharpe": 1.7,
        "class_path": "alan_trader.strategies.earnings_iv_crush.EarningsIVCrushStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "vix", "earnings"],
        "has_screener": True,
    },
    "earnings_post_drift": {
        "display_name": "Earnings Post-Drift",
        "type": "rule",
        "status": "active",
        "icon": "🚀",
        "description": (
            "Buys bull call spreads the morning after large EPS beats (>10% surprise). "
            "Captures the SUE effect — markets systematically underreact to earnings beats, "
            "stocks drift 2-4% higher over 2-3 weeks post-announcement."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 14,
        "target_sharpe": 1.3,
        "class_path": "alan_trader.strategies.earnings_post_drift.EarningsPostDriftStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "vix", "earnings"],
        "has_screener": True,
    },
    "vol_term_structure_regime": {
        "display_name": "Vol Term Structure Regime",
        "type": "ai",
        "status": "active",
        "icon": "📐",
        "description": (
            "LSTM classifies IV term structure regime (contango/backwardation) to time "
            "premium selling vs buying. Trades bull put spreads in contango, long straddles "
            "in backwardation."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 14,
        "target_sharpe": 1.3,
        "class_path": "alan_trader.strategies.vol_term_structure_regime.VolTermStructureRegimeStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": True,
        "has_screener": True,
        "required_data": ["price", "options", "vix", "rates"],
    },

    # ── OI / flow-driven ML strategies ──────────────────────────────────────
    "oi_imbalance_put_fade": {
        "display_name": "OI Imbalance Put Fade",
        "type": "ai",
        "status": "active",
        "icon": "📉",
        "description": (
            "Logistic regression detects retail put-buying extremes on high-IV stocks. "
            "Sells a bull put spread (7–14 DTE) when put/call OI imbalance spikes and "
            "ATM put IV is elevated beyond fair value. Exits at 50% profit, 2× loss, or 5 DTE."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 10,
        "target_sharpe": 1.3,
        "class_path": "alan_trader.strategies.oi_imbalance_put_fade.OIImbalancePutFadeStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": True,
        "has_screener": True,
        "required_data": ["price", "options", "vix", "fomc"],
    },
    "short_squeeze_vol_expansion": {
        "display_name": "Short Squeeze Vol Expansion",
        "type": "ai",
        "status": "active",
        "icon": "🚀",
        "description": (
            "LightGBM classifier detects early short-squeeze setups via call OI surge + low IV. "
            "When dealers go short gamma on call side, forced delta hedging creates momentum. "
            "Trades a bull call spread (14–21 DTE) to capture the directional squeeze move. "
            "Features: call OI concentration, vol/OI ratio, OTM call OI change, ATM IV, VIX context."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 14,
        "target_sharpe": 1.4,
        "class_path": "alan_trader.strategies.short_squeeze_vol_expansion.ShortSqueezeVolExpansionStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": True,
        "has_screener": True,
        "required_data": ["price", "options", "vix", "fomc"],
    },
    "iv_skew_momentum": {
        "display_name": "IV Skew Momentum",
        "type": "ai",
        "status": "active",
        "icon": "📐",
        "description": (
            "LightGBM 3-class classifier trained on IV skew shape and momentum. "
            "When put skew accelerates (put IV rising faster than call IV), the options market "
            "is pricing in downside risk before price reacts. "
            "Bullish signal → bull call spread; bearish signal → bear put spread. "
            "11 features: skew level, skew z-score, skew 5d momentum, IVR, realized vol, VIX, market context."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 21,
        "target_sharpe": 1.3,
        "class_path": "alan_trader.strategies.iv_skew_momentum.IVSkewMomentumStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": True,
        "required_data": ["price", "options", "vix"],
        "has_screener": True,
    },
    "gamma_flip_breakout": {
        "display_name": "Gamma Flip Breakout",
        "type": "ai",
        "status": "active",
        "icon": "⚡",
        "description": (
            "XGBoost binary classifier trained on dealer Gamma Exposure (GEX), distance to GEX flip level, "
            "and momentum. Above the flip → dealers long gamma → dampen moves → iron condor. "
            "Below the flip → dealers short gamma → amplify moves → strangle. "
            "11 features: net GEX, GEX flow, dist-to-flip, GEX ratio, ATR, volume ratio, macro context."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 14,
        "target_sharpe": 1.4,
        "class_path": "alan_trader.strategies.gamma_flip_breakout.GammaFlipBreakoutStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": True,
        "required_data": ["price", "options", "vix"],
        "has_screener": True,
    },
    "dealer_gamma_regime": {
        "display_name": "Dealer Gamma Regime",
        "type": "rule",
        "status": "active",
        "icon": "🧲",
        "description": (
            "Trades the actual dealer gamma mechanic with three regime-specific options structures. "
            "Negative GEX (spot < flip) → long straddle, capturing trend amplification. "
            "Positive GEX (spot > flip) → iron condor anchored on detected call/put walls, capturing pin. "
            "Near-flip → long straddle on regime inflection. "
            "GEX computed from options chain; sized by distance-to-flip, not by VIX bands."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 18,
        "target_sharpe": 1.5,
        "class_path": "alan_trader.strategies.dealer_gamma_regime.DealerGammaRegimeStrategy",
        "requires_training": False,
        "uses_ml": False,
        "requires_ticker": True,
        "required_data": ["price", "options_chain", "vix"],
        "has_screener": True,
    },

    # ── New AI strategies (2026-04-06) ──────────────────────────────────────
    "momentum_regime_spread": {
        "display_name": "Momentum Regime Spread — AI",
        "type": "ai",
        "status": "active",
        "icon": "🎯",
        "description": (
            "3-class GBM classifies SPY into bull / bear / chop momentum regimes. "
            "Bull → buy bull call debit spread. Bear → buy bear put debit spread. Chop → flat. "
            "Max loss bounded to debit paid. 11 features: momentum, VIX, trend. Walk-forward, 90-bar warmup."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 10,
        "target_sharpe": 1.1,
        "class_path": "alan_trader.strategies.momentum_regime_spread.MomentumRegimeSpreadStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": False,
        "required_data": ["price", "vix"],
        "has_screener": True,
    },
    "covered_call_ai": {
        "display_name": "Covered Call Optimizer — AI",
        "type": "ai",
        "status": "active",
        "icon": "📈",
        "description": (
            "AI-optimized covered call writing. GBM selects strike delta and DTE based on IVR, "
            "momentum, earnings proximity, and vol regime. Aggressive 0.30 delta in high-IVR "
            "low-momentum regimes; conservative 0.15 delta in strong uptrends. Skips when IVR low. "
            "Walk-forward, 90-bar warmup."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 21,
        "target_sharpe": 1.0,
        "class_path": "alan_trader.strategies.covered_call_ai.CoveredCallAIStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": True,
        "required_data": ["price", "vix"],
        "has_screener": True,
    },
    "rs_credit_spread": {
        "display_name": "RS Credit Spread — AI",
        "type": "ai",
        "status": "active",
        "icon": "🔄",
        "description": (
            "Sells bear call spread on weakest sector ETF + bull put spread on strongest sector ETF. "
            "GBM predicts P(sector stays contained) for each leg independently. "
            "Exploits institutional rebalancing mean-reversion. Weekly rebalance, SPY ADX filter. "
            "Requires 11 SPDR sector ETF data."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 10,
        "target_sharpe": 1.2,
        "class_path": "alan_trader.strategies.rs_credit_spread.RSCreditSpreadStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": False,
        "required_data": ["price", "vix", "sectors"],
        "has_screener": True,
    },

    # ── Put Steal ──────────────────────────────────────────────────────────────
    "put_steal": {
        "display_name": "Put Steal — Interest Arb AI",
        "type": "ai",
        "status": "active",
        "icon": "🪤",
        "description": (
            "Exploits retail put holders who fail to exercise deep ITM American puts early "
            "(Barraclough-Whaley 2011). NII = X(1-e^{-rT}) - call(S,X,T): when NII > 0, "
            "the long forfeits interest income to the short. "
            "Sells bull put spreads when NII > threshold and GBM classifier confirms low crash risk. "
            "Works best in high-rate, low-vol environments. Walk-forward: 90-bar warmup, retrains every 20 bars."
        ),
        "asset_class": "equities_options",
        "typical_holding_days": 21,
        "target_sharpe": 1.5,
        "class_path": "alan_trader.strategies.put_steal.PutStealStrategy",
        "requires_training": True,
        "uses_ml": True,
        "requires_ticker": True,
        "required_data": ["price", "vix", "rates"],
        "has_screener": True,
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
