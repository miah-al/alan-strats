"""
PyTorch model: LSTM with attention for SPY options spread signal generation.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class AttentionLayer(nn.Module):
    def __init__(self, hidden_size: int):
        super().__init__()
        self.attn = nn.Linear(hidden_size, 1)

    def forward(self, lstm_output: torch.Tensor) -> torch.Tensor:
        """
        lstm_output: (batch, seq_len, hidden_size)
        Returns: (batch, hidden_size) — weighted sum of hidden states.
        """
        weights = self.attn(lstm_output).squeeze(-1)    # (batch, seq_len)
        weights = F.softmax(weights, dim=1).unsqueeze(1) # (batch, 1, seq_len)
        context = torch.bmm(weights, lstm_output).squeeze(1)  # (batch, hidden_size)
        return context


class SpreadSignalModel(nn.Module):
    """
    LSTM + Attention model with two output heads:
      - classification head: (batch, 3) logits for [bear, neutral, bull]
      - price head:          (batch, 1) spread price regression

    Inputs:  (batch, seq_len, num_features)
    """

    def __init__(
        self,
        num_features: int,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.3,
        num_classes: int = 3,
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=num_features,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.attention = AttentionLayer(hidden_size)
        self.dropout = nn.Dropout(dropout)
        self.norm = nn.LayerNorm(hidden_size)
        # Direction classification head
        self.head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size // 2, num_classes),
        )
        # Spread price regression head
        self.price_head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, 1),
        )

    def _encode(self, x: torch.Tensor) -> torch.Tensor:
        """Shared encoder: LSTM → attention → norm+dropout → context vector."""
        lstm_out, _ = self.lstm(x)
        context = self.attention(lstm_out)
        return self.norm(self.dropout(context))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Returns classification logits (batch, num_classes)."""
        return self.head(self._encode(x))

    def forward_dual(self, x: torch.Tensor) -> tuple:
        """Returns (logits, price_pred) — (batch, num_classes), (batch, 1)."""
        ctx = self._encode(x)
        return self.head(ctx), self.price_head(ctx)

    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            return F.softmax(self.forward(x), dim=-1)


# ---------------------------------------------------------------------------
# Sequence dataset
# ---------------------------------------------------------------------------

import numpy as np
from torch.utils.data import Dataset


class SequenceDataset(Dataset):
    """
    Sliding-window dataset over feature matrix.
    Each sample is (seq_len, num_features) → (label, spread_price).
    spread_prices defaults to zeros when not provided.
    """

    def __init__(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        seq_len: int,
        spread_prices: np.ndarray = None,
    ):
        assert len(features) == len(labels)
        self.features = torch.tensor(features, dtype=torch.float32)
        self.labels = torch.tensor(labels, dtype=torch.long)
        self.seq_len = seq_len
        sp = spread_prices if spread_prices is not None else np.zeros(len(features), dtype=np.float32)
        self.spread_prices = torch.tensor(sp, dtype=torch.float32)

    def __len__(self):
        return len(self.features) - self.seq_len

    def __getitem__(self, idx):
        x  = self.features[idx: idx + self.seq_len]
        y  = self.labels[idx + self.seq_len]
        sp = self.spread_prices[idx + self.seq_len]
        return x, y, sp
