"""
Training loop with early stopping, class-imbalance weighting, and model persistence.
Supports dual-head training: direction classification + spread price regression.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, random_split

from alan_trader.model.architecture import SequenceDataset, SpreadSignalModel

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent / "saved_models"
MODEL_DIR.mkdir(exist_ok=True)


class ModelTrainer:
    def __init__(
        self,
        num_features: int = 0,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.3,
        lr: float = 1e-3,
        batch_size: int = 64,
        num_epochs: int = 100,
        patience: int = 15,
        seq_len: int = 30,
        enter_boost: float = 2.0,
        device: Optional[str] = None,
        feature_cols: Optional[list] = None,
    ):
        self.feature_cols = list(feature_cols) if feature_cols else []
        self.num_features = len(self.feature_cols) if self.feature_cols else num_features
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.dropout = dropout
        self.seq_len = seq_len
        self.batch_size = batch_size
        self.num_epochs = num_epochs
        self.patience = patience
        self.enter_boost = enter_boost
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))

        self.model = SpreadSignalModel(self.num_features, hidden_size, num_layers, dropout).to(self.device)
        self.optimizer = torch.optim.AdamW(self.model.parameters(), lr=lr, weight_decay=1e-4)
        self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer, mode="min", factor=0.5, patience=5
        )
        self.scaler = StandardScaler()

        # Price regression state
        self._has_price_regression = False
        self._price_mean = 0.0
        self._price_std = 1.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        spread_prices: Optional[np.ndarray] = None,
    ) -> dict:
        """
        Train on (features, labels). Features should be raw (unscaled).
        Optionally train price regression head when spread_prices is provided.
        Returns dict with train/val loss history.
        """
        features = self.scaler.fit_transform(features)

        # Normalise spread prices for stable regression loss
        if spread_prices is not None:
            self._has_price_regression = True
            self._price_mean = float(np.mean(spread_prices))
            self._price_std = float(np.std(spread_prices)) + 1e-8
            sp_norm = (spread_prices - self._price_mean) / self._price_std
        else:
            self._has_price_regression = False
            sp_norm = None

        dataset = SequenceDataset(features, labels, self.seq_len, spread_prices=sp_norm)

        n_val = max(1, int(0.15 * len(dataset)))
        n_train = len(dataset) - n_val
        train_ds, val_ds = random_split(
            dataset, [n_train, n_val],
            generator=torch.Generator().manual_seed(42)
        )

        # Class weights to handle imbalance; multiply ENTER weight by enter_boost
        # to counteract models collapsing to SKIP/AVOID on rare trade signals
        class_counts = np.bincount(labels, minlength=3).astype(float)
        class_counts = np.where(class_counts == 0, 1, class_counts)
        w = 1.0 / class_counts
        w[2] *= self.enter_boost  # class 2 = ENTER
        weights = torch.tensor(w, dtype=torch.float32).to(self.device)
        criterion = nn.CrossEntropyLoss(weight=weights)

        _eff_bs = min(self.batch_size, len(train_ds))
        train_loader = DataLoader(train_ds, batch_size=_eff_bs, shuffle=True, drop_last=False)
        val_loader = DataLoader(val_ds, batch_size=self.batch_size, shuffle=False)

        history = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": []}
        best_val_loss = float("inf")
        patience_counter = 0
        best_state = None

        for epoch in range(1, self.num_epochs + 1):
            train_loss, train_acc = self._train_epoch(train_loader, criterion)
            val_loss, val_acc = self._eval_epoch(val_loader, criterion)
            self.scheduler.step(val_loss)

            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)
            history["train_acc"].append(train_acc)
            history["val_acc"].append(val_acc)

            if epoch % 10 == 0 or epoch == 1:
                logger.info(
                    f"Epoch {epoch:3d} | train={train_loss:.4f} | val={val_loss:.4f} | acc={val_acc:.3f}"
                )

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                best_state = {k: v.cpu().clone() for k, v in self.model.state_dict().items()}
            else:
                patience_counter += 1
                if patience_counter >= self.patience:
                    logger.info(f"Early stopping at epoch {epoch}")
                    break

        if best_state:
            self.model.load_state_dict(best_state)
        return history

    def predict(self, features: np.ndarray) -> np.ndarray:
        """
        Returns class probabilities (3,) for the latest window in features.
        """
        scaled = self.scaler.transform(features)
        t = torch.tensor(scaled, dtype=torch.float32)
        if len(t) < self.seq_len:
            raise ValueError(f"Need at least {self.seq_len} rows for inference")
        window = t[-self.seq_len:].unsqueeze(0).to(self.device)
        self.model.eval()
        proba = self.model.predict_proba(window).cpu().numpy()
        return proba[0]  # (3,)

    def predict_batch(self, features: np.ndarray) -> tuple:
        """
        Run inference over all possible windows.
        Returns (probas, price_preds):
          probas      — (N-seq_len, 3)
          price_preds — (N-seq_len,) in original price units, or None
        """
        scaled = self.scaler.transform(features)
        dummy_labels = np.zeros(len(scaled), dtype=int)
        dataset = SequenceDataset(scaled, dummy_labels, self.seq_len)
        if len(dataset) == 0:
            n_out = max(0, len(scaled) - self.seq_len)
            empty = np.zeros((n_out, 3), dtype=np.float32)
            empty[:] = [1/3, 1/3, 1/3]
            return empty, None
        loader = DataLoader(dataset, batch_size=256, shuffle=False)
        self.model.eval()
        all_proba = []
        all_price = []
        with torch.no_grad():
            for x, _, _ in loader:
                x = x.to(self.device)
                if self._has_price_regression:
                    logits, price_pred = self.model.forward_dual(x)
                    proba = torch.softmax(logits, dim=-1)
                    # Denormalise back to original price units
                    p = price_pred.squeeze(-1).cpu().numpy()
                    all_price.append(p * self._price_std + self._price_mean)
                else:
                    proba = torch.softmax(self.model(x), dim=-1)
                all_proba.append(proba.cpu().numpy())

        probas = np.vstack(all_proba)
        price_preds = np.concatenate(all_price) if self._has_price_regression else None
        return probas, price_preds

    def get_model_summary(self) -> dict:
        """Return architecture summary dict for display."""
        m = self.model
        h = m.lstm.hidden_size

        def _params(module):
            return sum(p.numel() for p in module.parameters())

        layers = [
            {
                "Layer": "Input",
                "Description": f"Sequence of {self.seq_len} steps × {self.num_features} features",
                "Output Shape": f"(batch, {self.seq_len}, {self.num_features})",
                "Parameters": 0,
            },
            {
                "Layer": "LSTM",
                "Description": f"{self.num_features}→{h} hidden, {m.lstm.num_layers} layers, dropout={m.dropout.p:.1f}",
                "Output Shape": f"(batch, {self.seq_len}, {h})",
                "Parameters": _params(m.lstm),
            },
            {
                "Layer": "Attention",
                "Description": f"Linear({h}, 1) → softmax over seq → context",
                "Output Shape": f"(batch, {h})",
                "Parameters": _params(m.attention),
            },
            {
                "Layer": "LayerNorm + Dropout",
                "Description": f"LayerNorm({h}), Dropout({m.dropout.p:.1f})",
                "Output Shape": f"(batch, {h})",
                "Parameters": _params(m.norm),
            },
            {
                "Layer": "Direction Head",
                "Description": f"Linear({h},{h//2}) → ReLU → Dropout → Linear({h//2},3) → softmax",
                "Output Shape": "(batch, 3)  [bear, neutral, bull]",
                "Parameters": _params(m.head),
            },
            {
                "Layer": "Price Head",
                "Description": f"Linear({h},{h//2}) → ReLU → Linear({h//2},1)",
                "Output Shape": "(batch, 1)  [spread price $]",
                "Parameters": _params(m.price_head),
            },
        ]

        total = sum(p.numel() for p in m.parameters())
        return {
            "layers": layers,
            "total_params": total,
            "trainable_params": sum(p.numel() for p in m.parameters() if p.requires_grad),
        }

    def compute_confusion_matrix(self, features: np.ndarray, labels: np.ndarray) -> np.ndarray:
        """Return 3×3 confusion matrix (rows=true, cols=pred) on unscaled features."""
        import torch
        from alan_trader.model.architecture import SequenceDataset
        from torch.utils.data import DataLoader
        scaled = self.scaler.transform(features)
        ds     = SequenceDataset(scaled, labels, self.seq_len)
        if len(ds) == 0:
            return np.zeros((3, 3), dtype=float)
        loader = DataLoader(ds, batch_size=256, shuffle=False)
        self.model.eval()
        preds, trues = [], []
        with torch.no_grad():
            for x, y, _ in loader:
                out = self.model(x.to(self.device)).argmax(1).cpu().numpy()
                preds.extend(out); trues.extend(y.numpy())
        cm = np.zeros((3, 3), dtype=float)
        for t, p in zip(trues, preds):
            cm[int(t), int(p)] += 1
        return cm

    def compute_feature_importance(
        self, features: np.ndarray, labels: np.ndarray, feat_names: Optional[list] = None
    ) -> "pd.Series":
        """Permutation importance on unscaled features. Returns Series sorted descending."""
        import pandas as pd
        import torch
        from alan_trader.model.architecture import SequenceDataset
        from torch.utils.data import DataLoader

        names = feat_names or self.feature_cols or [str(i) for i in range(features.shape[1])]
        scaled = self.scaler.transform(features.copy())

        def _acc():
            ds = SequenceDataset(scaled, labels, self.seq_len)
            loader = DataLoader(ds, batch_size=256)
            self.model.eval()
            correct = total = 0
            with torch.no_grad():
                for x, y, _ in loader:
                    correct += (self.model(x.to(self.device)).argmax(1)
                                == y.to(self.device)).sum().item()
                    total += len(y)
            return correct / total if total else 0.0

        baseline = _acc()
        rng = np.random.default_rng(0)
        imp = {}
        for i, name in enumerate(names):
            if i >= scaled.shape[1]: continue
            saved = scaled[:, i].copy()
            rng.shuffle(scaled[:, i])
            imp[name] = max(0.0, baseline - _acc())
            scaled[:, i] = saved
        return pd.Series(imp).sort_values(ascending=False)

    def save(self, name: str = "spy_model"):
        path = MODEL_DIR / f"{name}.pt"
        torch.save({
            "model_state": self.model.state_dict(),
            "scaler_mean": self.scaler.mean_,
            "scaler_scale": self.scaler.scale_,
            "num_features": self.num_features,
            "feature_cols": self.feature_cols,
            "has_price_regression": self._has_price_regression,
            "price_mean": self._price_mean,
            "price_std": self._price_std,
        }, path)
        logger.info(f"Model saved to {path}")

    def load(self, name: str = "spy_model"):
        path = MODEL_DIR / f"{name}.pt"
        ckpt = torch.load(path, map_location=self.device)
        self.model.load_state_dict(ckpt["model_state"])
        self.scaler.mean_ = ckpt["scaler_mean"]
        self.scaler.scale_ = ckpt["scaler_scale"]
        self.feature_cols = ckpt.get("feature_cols", self.feature_cols)
        self._has_price_regression = ckpt.get("has_price_regression", False)
        self._price_mean = ckpt.get("price_mean", 0.0)
        self._price_std = ckpt.get("price_std", 1.0)
        logger.info(f"Model loaded from {path}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _train_epoch(self, loader: DataLoader, criterion: nn.Module) -> tuple:
        if len(loader) == 0:
            return 0.0, 0.0
        self.model.train()
        total_loss = 0.0
        correct = 0
        total = 0
        for x, y, sp in loader:
            x, y, sp = x.to(self.device), y.to(self.device), sp.to(self.device)
            self.optimizer.zero_grad()
            if self._has_price_regression:
                logits, price_pred = self.model.forward_dual(x)
                cls_loss = criterion(logits, y)
                mse_loss = F.mse_loss(price_pred.squeeze(-1), sp)
                loss = 0.7 * cls_loss + 0.3 * mse_loss
            else:
                logits = self.model(x)
                loss = criterion(logits, y)
            loss.backward()
            nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.optimizer.step()
            total_loss += loss.item()
            correct += (logits.argmax(1) == y).sum().item()
            total += len(y)
        return total_loss / len(loader), correct / total

    def _eval_epoch(self, loader: DataLoader, criterion: nn.Module) -> tuple:
        self.model.eval()
        total_loss = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for x, y, sp in loader:
                x, y, sp = x.to(self.device), y.to(self.device), sp.to(self.device)
                if self._has_price_regression:
                    logits, price_pred = self.model.forward_dual(x)
                    cls_loss = criterion(logits, y)
                    mse_loss = F.mse_loss(price_pred.squeeze(-1), sp)
                    loss = 0.7 * cls_loss + 0.3 * mse_loss
                else:
                    logits = self.model(x)
                    loss = criterion(logits, y)
                total_loss += loss.item()
                correct += (logits.argmax(1) == y).sum().item()
                total += len(y)
        return total_loss / len(loader), correct / total
