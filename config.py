"""
Configuration for SPY options spread trader.
"""

POLYGON_API_KEY = "YOUR_POLYGON_API_KEY"  # Set via env var POLYGON_API_KEY

# Data settings
LOOKBACK_YEARS = 2
SEQUENCE_LENGTH = 30          # Days of history fed into the LSTM
TRAIN_SPLIT = 0.8

# Options spread settings
SPREAD_WIDTH_DOLLARS = 5      # Strike spread width ($5 wide)
DTE_TARGET = 30               # Target days-to-expiration for new trades
DTE_MIN = 7                   # Don't enter if less than 7 DTE
MAX_LOSS_PCT = 0.02           # Max 2% portfolio loss per trade
POSITION_SIZE_PCT = 0.05      # 5% of portfolio per trade

# Model architecture
HIDDEN_SIZE = 128
NUM_LAYERS = 2
DROPOUT = 0.3
LEARNING_RATE = 1e-3
BATCH_SIZE = 64
NUM_EPOCHS = 100
EARLY_STOPPING_PATIENCE = 15

# Live trading
UPDATE_INTERVAL_MINUTES = 15  # Retrain/update model every N minutes (intraday)
RETRAIN_INTERVAL_DAYS = 7     # Full retrain weekly

# Tickers used as features
FEATURE_TICKERS = ["SPY", "QQQ", "IWM"]
VIX_TICKER = "I:VIX"
RATE_2Y = "I:UST2Y"
RATE_10Y = "I:UST10Y"

# Multi-strategy portfolio settings
MULTI_STRATEGY_CAPITAL = 100_000   # Total portfolio value across all strategies
KELLY_FRACTION = 0.25              # Fractional Kelly multiplier (1.0 = full Kelly, risky)
MAX_STRATEGY_WEIGHT = 0.40         # No single strategy exceeds 40% of portfolio
MIN_STRATEGY_WEIGHT = 0.02         # Every active strategy gets at least 2%
CORRELATION_WINDOW_DAYS = 60       # Rolling window for return correlation

# Risk settings
RISK_FREE_ANNUAL = 0.05            # Risk-free rate for Sharpe/Sortino (approx 5% = current T-bill)
VAR_CONFIDENCE = 0.95              # VaR / CVaR confidence level
