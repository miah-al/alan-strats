"""
Live trader: fetches latest data, updates model, generates signals.
Designed to run intraday on a schedule (cron / APScheduler).

NOTE: This does NOT auto-execute orders. It prints signals and spreads
to place manually or via a broker API (IBKR, Tastytrade, etc.).
"""

import json
import logging
import os
import pickle
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from alan_trader.config import (
    DTE_TARGET, POLYGON_API_KEY, SEQUENCE_LENGTH,
    HIDDEN_SIZE, NUM_LAYERS, DROPOUT, LEARNING_RATE,
    BATCH_SIZE, NUM_EPOCHS, EARLY_STOPPING_PATIENCE,
    MAX_LOSS_PCT, POSITION_SIZE_PCT,
)
from alan_trader.data.features import FEATURE_COLS, build_feature_matrix
from alan_trader.data.polygon_client import PolygonClient
from alan_trader.model.trainer import ModelTrainer
from alan_trader.trading.spread_selector import contracts_to_trade, select_spread

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent.parent / "saved_models" / "live_state.json"


class LiveTrader:
    def __init__(self, ticker: str = "SPY", portfolio_value: float = 100_000, paper: bool = True):
        self.ticker = ticker.upper()
        self.portfolio_value = portfolio_value
        self.paper = paper
        self.client = PolygonClient(POLYGON_API_KEY)
        self.trainer: ModelTrainer | None = None
        self.last_full_train: datetime | None = None
        self.state: dict = self._load_state()

    # ------------------------------------------------------------------
    # Main entry points
    # ------------------------------------------------------------------

    def run_once(self):
        """Call this on your schedule (e.g., every 15 min during market hours)."""
        logger.info(f"=== LiveTrader tick @ {datetime.now()} | ticker={self.ticker} ===")

        # 1. Refresh / train model
        self._maybe_retrain()

        if self.trainer is None:
            logger.warning("Model not trained yet, skipping signal generation")
            return

        # 2. Fetch latest features
        feature_df = self._fetch_recent_features()
        if feature_df is None or len(feature_df) < SEQUENCE_LENGTH:
            logger.warning("Insufficient data for signal")
            return

        avail    = [c for c in FEATURE_COLS if c in feature_df.columns]
        features = feature_df[avail].values

        # 3. Generate signal
        proba = self.trainer.predict(features)
        signal_class = int(np.argmax(proba))
        signal_names = {0: "BEAR", 1: "NEUTRAL", 2: "BULL"}

        logger.info(f"Signal: {signal_names[signal_class]} | proba={proba.round(3)}")

        # 4. Select spread
        spot_price = feature_df["close"].iloc[-1]
        vix = feature_df["vix"].iloc[-1] if "vix" in feature_df.columns else 20.0

        expiry = self._find_target_expiry()
        if expiry is None:
            logger.warning("No suitable expiry found")
            return

        chain = self.client.get_options_chain(self.ticker, expiry)
        if chain.empty:
            logger.warning(f"Empty options chain for {expiry}")
            return

        spread = select_spread(
            signal_proba=proba,
            spy_price=spot_price,
            vix=vix,
            chain=chain,
            target_expiration=expiry,
            portfolio_value=self.portfolio_value,
            max_loss_pct=MAX_LOSS_PCT,
        )

        n_contracts = contracts_to_trade(spread, self.portfolio_value, MAX_LOSS_PCT)

        print("\n" + "=" * 60)
        print(f"  SIGNAL: {signal_names[signal_class]}  |  Confidence: {proba[signal_class]:.1%}")
        print(f"  {self.ticker}: ${spot_price:.2f}  |  VIX: {vix:.1f}")
        print(f"  Spread: {spread.spread_type.upper()}")
        print(f"  Strikes: {spread.long_strike}/{spread.short_strike}  Exp: {spread.expiration}")
        print(f"  Net debit/credit: ${spread.debit_or_credit:.2f}")
        print(f"  Max profit: ${spread.max_profit:.2f}  Max loss: ${spread.max_loss:.2f}")
        print(f"  Breakeven: ${spread.breakeven:.2f}")
        print(f"  Suggested contracts: {n_contracts}")
        if self.paper:
            print("  *** PAPER TRADING — no orders sent ***")
        print("=" * 60 + "\n")

        self._save_signal(spread, proba, n_contracts, spot_price)

    # ------------------------------------------------------------------
    # Model training / updating
    # ------------------------------------------------------------------

    def _maybe_retrain(self):
        now = datetime.now()
        needs_full_train = (
            self.trainer is None
            or self.last_full_train is None
            or (now - self.last_full_train).days >= 7
        )

        if needs_full_train:
            logger.info("Starting full model retraining...")
            self._full_retrain()
            self.last_full_train = now

    def _full_retrain(self):
        to_date = date.today().isoformat()
        from_date = (date.today() - timedelta(days=730)).isoformat()  # 2 years

        logger.info(f"Fetching data {from_date} → {to_date}")
        feature_df = self._fetch_historical_features(from_date, to_date)
        if feature_df is None or len(feature_df) < 200:
            logger.error("Not enough historical data to train")
            return

        avail    = [c for c in FEATURE_COLS if c in feature_df.columns]
        features = feature_df[avail].values
        labels   = feature_df["label"].values

        self.trainer = ModelTrainer(
            feature_cols=avail,
            hidden_size=HIDDEN_SIZE,
            num_layers=NUM_LAYERS,
            dropout=DROPOUT,
            lr=LEARNING_RATE,
            batch_size=BATCH_SIZE,
            num_epochs=NUM_EPOCHS,
            patience=EARLY_STOPPING_PATIENCE,
            seq_len=SEQUENCE_LENGTH,
        )
        history = self.trainer.fit(features, labels)
        self.trainer.save(f"{self.ticker.lower()}_model_live")
        logger.info(f"Training complete. Final val acc: {history['val_acc'][-1]:.3f}")

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _fetch_historical_features(self, from_date: str, to_date: str) -> pd.DataFrame | None:
        try:
            bars   = self.client.get_aggregates(self.ticker, from_date, to_date)
            vix    = self.client.get_aggregates("I:VIX", from_date, to_date)
            rate2y = self.client.get_aggregates("I:UST2Y", from_date, to_date)
            rate10y = self.client.get_aggregates("I:UST10Y", from_date, to_date)
            news   = self.client.get_news(self.ticker, from_date, to_date)
            return build_feature_matrix(bars, vix, rate2y, rate10y, news)
        except Exception as e:
            logger.exception(f"Error fetching historical features: {e}")
            return None

    def _fetch_recent_features(self) -> pd.DataFrame | None:
        """Fetch last 60 days for inference (need seq_len worth of clean data)."""
        to_date = date.today().isoformat()
        from_date = (date.today() - timedelta(days=90)).isoformat()
        return self._fetch_historical_features(from_date, to_date)

    def _find_target_expiry(self) -> str | None:
        """Find expiry closest to DTE_TARGET days out."""
        target = date.today() + timedelta(days=DTE_TARGET)
        exps = self.client.get_expirations(self.ticker, as_of=date.today().isoformat())
        if not exps:
            return None
        exp_dates = [date.fromisoformat(e) for e in exps]
        best = min(exp_dates, key=lambda d: abs((d - target).days))
        return best.isoformat()

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                return json.load(f)
        return {"signals": []}

    def _save_signal(self, spread, proba, contracts, spot_price):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "ticker": self.ticker,
            "spot_price": spot_price,
            "spread_type": spread.spread_type,
            "long_strike": spread.long_strike,
            "short_strike": spread.short_strike,
            "expiration": spread.expiration,
            "debit_credit": spread.debit_or_credit,
            "max_profit": spread.max_profit,
            "max_loss": spread.max_loss,
            "contracts": contracts,
            "proba_bear": float(proba[0]),
            "proba_neutral": float(proba[1]),
            "proba_bull": float(proba[2]),
        }
        self.state.setdefault("signals", []).append(entry)
        STATE_FILE.parent.mkdir(exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)
        logger.info(f"Signal saved to {STATE_FILE}")
