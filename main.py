"""
Main entrypoint for SPY options spread trader.

Usage:
  python -m alan_trader.main train              # train model on 2 years of data
  python -m alan_trader.main backtest           # run backtest and show results
  python -m alan_trader.main live               # run live signal generation once
  python -m alan_trader.main live --loop 15     # run every 15 minutes
  python -m alan_trader.main dashboard          # launch Streamlit dashboard (simulated data)
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
        LEARNING_RATE, NUM_EPOCHS, NUM_LAYERS, POLYGON_API_KEY, SEQUENCE_LENGTH,
    )
    from alan_trader.data.features import FEATURE_COLS, build_feature_matrix
    from alan_trader.data.polygon_client import PolygonClient
    from alan_trader.model.trainer import ModelTrainer

    client = PolygonClient(POLYGON_API_KEY)
    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=730)).isoformat()

    logger.info(f"Fetching 2 years of data: {from_date} → {to_date}")
    spy = client.get_aggregates("SPY", from_date, to_date)
    vix = client.get_aggregates("I:VIX", from_date, to_date)
    rate2y = client.get_aggregates("I:UST2Y", from_date, to_date)
    rate10y = client.get_aggregates("I:UST10Y", from_date, to_date)
    news = client.get_news("SPY", from_date, to_date)

    logger.info("Building feature matrix...")
    df = build_feature_matrix(spy, vix, rate2y, rate10y, news)
    logger.info(f"Feature matrix: {df.shape[0]} rows, {len(FEATURE_COLS)} features")

    features = df[FEATURE_COLS].values
    labels = df["label"].values

    from collections import Counter
    logger.info(f"Label distribution: {dict(Counter(labels))}")

    trainer = ModelTrainer(
        num_features=len(FEATURE_COLS),
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
    trainer.save("spy_model")

    print(f"\nTraining complete.")
    print(f"  Best val accuracy:  {max(history['val_acc']):.3f}")
    print(f"  Final val accuracy: {history['val_acc'][-1]:.3f}")
    print(f"  Model saved to saved_models/spy_model.pt")


def cmd_backtest(args):
    from alan_trader.config import (
        BATCH_SIZE, DROPOUT, EARLY_STOPPING_PATIENCE, HIDDEN_SIZE,
        LEARNING_RATE, NUM_EPOCHS, NUM_LAYERS, POLYGON_API_KEY,
        SEQUENCE_LENGTH, TRAIN_SPLIT,
    )
    from alan_trader.data.features import FEATURE_COLS, build_feature_matrix
    from alan_trader.data.polygon_client import PolygonClient
    from alan_trader.model.trainer import ModelTrainer
    from alan_trader.backtest.engine import BacktestEngine

    import numpy as np

    client = PolygonClient(POLYGON_API_KEY)
    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=730)).isoformat()

    logger.info("Fetching historical data for backtest...")
    spy = client.get_aggregates("SPY", from_date, to_date)
    vix = client.get_aggregates("I:VIX", from_date, to_date)
    rate2y = client.get_aggregates("I:UST2Y", from_date, to_date)
    rate10y = client.get_aggregates("I:UST10Y", from_date, to_date)
    news = client.get_news("SPY", from_date, to_date)

    df = build_feature_matrix(spy, vix, rate2y, rate10y, news)
    features = df[FEATURE_COLS].values
    labels = df["label"].values

    # Train/test split (no shuffling — time-series)
    n_train = int(len(features) * TRAIN_SPLIT)
    train_f, test_f = features[:n_train], features[n_train:]
    train_l, test_l = labels[:n_train], labels[n_train:]

    logger.info(f"Train: {n_train} samples | Test: {len(test_f)} samples")

    trainer = ModelTrainer(
        num_features=len(FEATURE_COLS),
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
    probas = trainer.predict_batch(test_f)
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
    parser = argparse.ArgumentParser(description="SPY Options Spread Trader")
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

    dash_p = sub.add_parser("dashboard", help="Launch Streamlit dashboard (simulated data)")
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
