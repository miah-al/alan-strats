"""
SPY Options Spread strategy — wraps BacktestEngine + ModelTrainer as a BaseStrategy.
"""

import warnings
import numpy as np
import pandas as pd

from alan_trader.strategies.base import (
    BaseStrategy, BacktestResult, SignalResult, StrategyStatus, StrategyType,
)
from alan_trader.risk.metrics import compute_all_metrics


class OptionsSpreadStrategy(BaseStrategy):
    name                 = "options_spread"
    display_name         = "Options Spread"
    strategy_type        = StrategyType.AI_DRIVEN
    status               = StrategyStatus.ACTIVE
    description          = ("LSTM + attention model predicts 5-day price direction. "
                            "Bull signal → bull call spread. Bear signal → bear put spread. "
                            "Spread width and type adapted to VIX regime.")
    asset_class          = "equities_options"
    typical_holding_days = 5
    target_sharpe        = 1.2

    def __init__(
        self,
        seq_len: int = 30,
        hidden_size: int = 64,
        num_layers: int = 1,
        dropout: float = 0.2,
        lr: float = 1e-3,
        batch_size: int = 32,
        num_epochs: int = 40,
        patience: int = 15,
        min_confidence: float = 0.38,
        hold_days: int = 5,
        otm_pct: float = 0.0,
        max_loss_pct: float = 0.02,
        spread_type: str = "bull_call",
    ):
        self.seq_len        = seq_len
        self.hidden_size    = hidden_size
        self.num_layers     = num_layers
        self.dropout        = dropout
        self.lr             = lr
        self.batch_size     = batch_size
        self.num_epochs     = num_epochs
        self.patience       = patience
        self.min_confidence = min_confidence
        self.hold_days      = hold_days
        self.otm_pct        = otm_pct
        self.max_loss_pct   = max_loss_pct
        self.spread_type    = spread_type
        self._trainer       = None
        self._train_history = {}

    def fit(self, features: np.ndarray, labels: np.ndarray) -> dict:
        from alan_trader.model.trainer import ModelTrainer
        self._trainer = ModelTrainer(
            num_features=features.shape[1],
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout,
            lr=self.lr,
            batch_size=self.batch_size,
            num_epochs=self.num_epochs,
            patience=self.patience,
            seq_len=self.seq_len,
        )
        self._train_history = self._trainer.fit(features, labels)
        return self._train_history

    def generate_signal(self, market_snapshot: dict) -> SignalResult:
        if self._trainer is None:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "model not trained"})
        features_df = market_snapshot.get("features_df")
        if features_df is None or len(features_df) < self.seq_len:
            return SignalResult(self.name, "HOLD", 0.0, 0.0,
                                metadata={"reason": "insufficient features"})
        from alan_trader.data.features import FEATURE_COLS
        avail = [c for c in FEATURE_COLS if c in features_df.columns]
        proba = self._trainer.predict(features_df[avail].values)
        cls   = int(np.argmax(proba))
        conf  = float(proba[cls])
        signal_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
        return SignalResult(
            strategy_name=self.name,
            signal=signal_map[cls],
            confidence=conf,
            position_size_pct=self.max_loss_pct if conf > self.min_confidence else 0.0,
            metadata={"proba": proba.tolist(), "class": cls},
        )

    def backtest(
        self,
        price_data: pd.DataFrame,
        auxiliary_data: dict,
        starting_capital: float = 100_000,
        **kwargs,
    ) -> BacktestResult:
        from alan_trader.data.features import build_feature_matrix, FEATURE_COLS, add_spread_price_target
        from alan_trader.model.trainer import ModelTrainer
        from alan_trader.backtest.engine import BacktestEngine

        vix    = auxiliary_data.get("vix",    pd.DataFrame())
        rate2y = auxiliary_data.get("rate2y", pd.DataFrame())
        rate10y = auxiliary_data.get("rate10y", pd.DataFrame())
        news   = auxiliary_data.get("news",   pd.DataFrame())

        # Allow caller (e.g. dashboard) to override spread_type and num_epochs
        spread_type = kwargs.get("spread_type", self.spread_type)
        num_epochs  = kwargs.get("num_epochs",  self.num_epochs)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = build_feature_matrix(price_data, vix, rate2y, rate10y, news,
                                      spread_type=spread_type)

        if len(df) < 100:
            return self._empty_result()

        # Compute theoretical spread price at each bar (regression target)
        df = add_spread_price_target(df)

        avail         = [c for c in FEATURE_COLS if c in df.columns]
        features      = df[avail].values
        labels        = df["label"].values
        spread_prices = df["spread_price_target"].values
        n_train       = int(len(features) * 0.80)

        trainer = ModelTrainer(
            feature_cols=avail,
            hidden_size=self.hidden_size,
            num_layers=self.num_layers,
            dropout=self.dropout,
            lr=self.lr,
            batch_size=self.batch_size,
            num_epochs=num_epochs,
            patience=self.patience,
            seq_len=self.seq_len,
        )
        self._train_history = trainer.fit(
            features[:n_train],
            labels[:n_train],
            spread_prices=spread_prices[:n_train],
        )
        self._trainer = trainer

        test_features = features[n_train:]
        test_df       = df.iloc[n_train:].reset_index()
        probas, price_preds = trainer.predict_batch(test_features)

        engine = BacktestEngine(
            starting_capital=starting_capital,
            max_loss_pct=self.max_loss_pct,
            hold_days=self.hold_days,
            min_confidence=self.min_confidence,
            otm_pct=self.otm_pct,
            spread_type=spread_type,
        )
        equity_df = engine.run(
            test_df, probas,
            seq_len=self.seq_len,
            price_predictions=price_preds,
        )
        trades_df = pd.DataFrame([vars(t) for t in engine.trades]) if engine.trades else pd.DataFrame()

        equity = equity_df["equity"]
        equity.index = pd.to_datetime(equity.index)
        daily_ret = equity.pct_change().dropna()

        bm_ret = equity_df["price"].pct_change().dropna() if "price" in equity_df.columns else None

        metrics = compute_all_metrics(
            equity_curve=equity,
            trades_df=trades_df,
            benchmark_returns=bm_ret,
        )

        # Aligned test-period arrays for visualisation (seq_len offset applied)
        date_col = "date" if "date" in test_df.columns else "index"
        test_dates  = test_df.iloc[self.seq_len:][date_col].values
        actual_sp   = test_df.iloc[self.seq_len:]["spread_price_target"].values if "spread_price_target" in test_df.columns else None

        extra = {
            "spread_price_predictions": price_preds,
            "spread_price_actuals":     actual_sp,
            "test_dates":               test_dates,
            "feature_cols":             avail,
            "feature_df_tail":          df.tail(60),
            "model_summary":            trainer.get_model_summary(),
        }

        return BacktestResult(
            strategy_name=self.name,
            equity_curve=equity,
            daily_returns=daily_ret,
            trades=trades_df,
            metrics=metrics,
            params=self.get_params(),
            extra=extra,
        )

    def is_trainable(self) -> bool:
        return True

    def get_model_name(self, ticker: str = "SPY") -> str:
        return f"options_spread_{ticker.lower()}"

    def get_backtest_ui_params(self) -> list:
        from alan_trader.data.features import SPREAD_TYPE_OPTIONS
        return [
            {
                "key": "spread_type", "label": "Spread type", "type": "selectbox",
                "options": list(SPREAD_TYPE_OPTIONS.keys()),
                "format_func": lambda k: SPREAD_TYPE_OPTIONS[k],
                "default": "bull_call",
            },
            {"key": "seq_len",        "label": "Seq length",     "type": "slider", "min": 10,   "max": 60,   "default": 30,   "step": 1,    "col": 0},
            {"key": "hold_days",      "label": "Hold days",      "type": "slider", "min": 2,    "max": 15,   "default": 5,    "step": 1,    "col": 1},
            {"key": "min_confidence", "label": "Min confidence", "type": "slider", "min": 0.33, "max": 0.70, "default": 0.38, "step": 0.01, "col": 2},
            {
                "key": "otm_pct",    "label": "OTM %",          "type": "slider", "min": 0,    "max": 40,   "default": 0,    "step": 5,    "col": 0, "row": 1,
                "help": "How far OTM the long strike is. 0 = ATM, 20 = 20% OTM.",
            },
            {"key": "num_epochs",     "label": "Train epochs",   "type": "slider", "min": 20,   "max": 200,  "default": 60,   "step": 10,   "col": 1, "row": 1},
        ]

    def get_params(self) -> dict:
        return {
            "seq_len":        self.seq_len,
            "hidden_size":    self.hidden_size,
            "num_layers":     self.num_layers,
            "dropout":        self.dropout,
            "lr":             self.lr,
            "min_confidence": self.min_confidence,
            "hold_days":      self.hold_days,
            "otm_pct":        self.otm_pct,
            "max_loss_pct":   self.max_loss_pct,
            "spread_type":    self.spread_type,
        }

    def _empty_result(self) -> BacktestResult:
        eq = pd.Series([100_000.0], name="equity")
        return BacktestResult(
            strategy_name=self.name,
            equity_curve=eq,
            daily_returns=pd.Series(dtype=float),
            trades=pd.DataFrame(),
            metrics={},
            params=self.get_params(),
        )
