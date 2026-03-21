"""
Main entrypoint for alan-strats options spread trader.

Usage:
  python -m alan_trader.main train              # train model on 2 years of data
  python -m alan_trader.main backtest           # run backtest and show results
  python -m alan_trader.main live               # run live signal generation once
  python -m alan_trader.main live --loop 15     # run every 15 minutes
  python -m alan_trader.main dashboard          # launch Streamlit dashboard (simulated data)

Add --ticker NVDA to any command to run on a ticker other than SPY.
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_train(args):
    from alan_trader.config import (
        BATCH_SIZE, DROPOUT, EARLY_STOPPING_PATIENCE, HIDDEN_SIZE,
        LEARNING_RATE, NUM_EPOCHS, NUM_LAYERS, SEQUENCE_LENGTH,
    )
    from alan_trader.data.features import FEATURE_COLS, build_feature_matrix
    from alan_trader.db.loader import load_training_data
    from alan_trader.model.trainer import ModelTrainer

    ticker = args.ticker.upper()

    logger.info(f"Loading training data from DB for {ticker}...")
    data = load_training_data(ticker=ticker)
    spy    = data["spy"]
    vix    = data["vix"]
    rate2y = data["rate2y"]
    rate10y = data["rate10y"]
    macro  = data["macro"]
    news   = data["news"]

    logger.info("Building feature matrix...")
    df = build_feature_matrix(spy, vix, rate2y, rate10y, news, macro_df=macro)
    avail    = [c for c in FEATURE_COLS if c in df.columns]
    logger.info(f"Feature matrix: {df.shape[0]} rows, {len(avail)} features")

    features = df[avail].values
    labels = df["label"].values

    from collections import Counter
    logger.info(f"Label distribution: {dict(Counter(labels))}")

    trainer = ModelTrainer(
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
    history = trainer.fit(features, labels)
    model_name = f"{ticker.lower()}_model"
    trainer.save(model_name)

    print(f"\nTraining complete.")
    print(f"  Ticker:             {ticker}")
    print(f"  Best val accuracy:  {max(history['val_acc']):.3f}")
    print(f"  Final val accuracy: {history['val_acc'][-1]:.3f}")
    print(f"  Model saved to saved_models/{model_name}.pt")


def cmd_backtest(args):
    from alan_trader.config import (
        BATCH_SIZE, DROPOUT, EARLY_STOPPING_PATIENCE, HIDDEN_SIZE,
        LEARNING_RATE, NUM_EPOCHS, NUM_LAYERS,
        SEQUENCE_LENGTH, TRAIN_SPLIT,
    )
    from alan_trader.data.features import FEATURE_COLS, build_feature_matrix
    from alan_trader.db.loader import load_training_data
    from alan_trader.model.trainer import ModelTrainer
    from alan_trader.backtest.engine import BacktestEngine

    import numpy as np

    ticker = args.ticker.upper()

    logger.info(f"Loading data from DB for {ticker} backtest...")
    data = load_training_data(ticker=ticker)
    spy    = data["spy"]
    vix    = data["vix"]
    rate2y = data["rate2y"]
    rate10y = data["rate10y"]
    macro  = data["macro"]
    news   = data["news"]

    df = build_feature_matrix(spy, vix, rate2y, rate10y, news, macro_df=macro)
    avail    = [c for c in FEATURE_COLS if c in df.columns]
    features = df[avail].values
    labels   = df["label"].values

    # Train/test split (no shuffling — time-series)
    n_train = int(len(features) * TRAIN_SPLIT)
    train_f, test_f = features[:n_train], features[n_train:]
    train_l, test_l = labels[:n_train], labels[n_train:]

    logger.info(f"Train: {n_train} samples | Test: {len(test_f)} samples")

    trainer = ModelTrainer(
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
    trainer.fit(train_f, train_l)

    # Predict on test set
    test_df = df.iloc[n_train:].reset_index()
    probas, _ = trainer.predict_batch(test_f)
    logger.info(f"Running backtest on {len(probas)} bars...")

    engine = BacktestEngine(
        starting_capital=100_000,
        position_size_pct=0.05,
        max_loss_pct=0.02,
        take_profit_pct=0.60,
        hold_days=5,
        min_confidence=0.45,
    )
    equity_df = engine.run(test_df, probas, seq_len=SEQUENCE_LENGTH)
    engine.report()

    if args.plot:
        engine.plot_equity()


def cmd_dashboard(args):
    import subprocess
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard", "app.py")
    print(f"Launching dashboard at http://localhost:{args.port}")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", dashboard_path,
        "--server.port", str(args.port),
        "--server.headless", "false",
        "--theme.base", "dark",
    ])


def cmd_live(args):
    from alan_trader.live.trader import LiveTrader

    trader = LiveTrader(
        ticker=args.ticker,
        portfolio_value=float(args.capital),
        paper=not args.real,
    )

    if args.loop:
        interval = int(args.loop) * 60
        logger.info(f"Running every {args.loop} minutes. Ctrl+C to stop.")
        while True:
            try:
                trader.run_once()
            except Exception as e:
                logger.exception(f"Error in live tick: {e}")
            time.sleep(interval)
    else:
        trader.run_once()


def main():
    parser = argparse.ArgumentParser(description="alan-strats Options Spread Trader")
    parser.add_argument("--ticker", default="SPY", metavar="TICKER",
                        help="Underlying ticker symbol (default: SPY)")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("train", help="Train model on 2 years of historical data")

    bt = sub.add_parser("backtest", help="Run walk-forward backtest")
    bt.add_argument("--plot", action="store_true", help="Show equity curve plot")

    live_p = sub.add_parser("live", help="Run live signal generation")
    live_p.add_argument("--loop", type=int, default=0, metavar="MINUTES",
                        help="Run repeatedly every N minutes")
    live_p.add_argument("--capital", default=100000, help="Portfolio value in dollars")
    live_p.add_argument("--real", action="store_true",
                        help="REAL trading mode (default: paper)")

    dash_p = sub.add_parser("dashboard", help="Launch Streamlit dashboard")
    dash_p.add_argument("--port", type=int, default=8501, help="Port for Streamlit server")

    args = parser.parse_args()

    # Dashboard doesn't need API key
    if args.cmd == "dashboard":
        cmd_dashboard(args)
        return

    # All other commands require API key
    if not os.environ.get("POLYGON_API_KEY"):
        print("ERROR: Set the POLYGON_API_KEY environment variable first.")
        print("  export POLYGON_API_KEY=your_key_here")
        print()
        print("  To run the dashboard with simulated data (no API key needed):")
        print("  python -m alan_trader.main dashboard")
        sys.exit(1)

    if args.cmd == "train":
        cmd_train(args)
    elif args.cmd == "backtest":
        cmd_backtest(args)
    elif args.cmd == "live":
        cmd_live(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
