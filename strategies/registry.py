"""
Strategy registry — metadata for all strategies + lazy factory.
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
        "class_path": "alan_trader.strategies.options_spread.OptionsSpreadStrategy",
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
