"""
JSON-backed portfolio history store.

Persists positions, transactions and daily snapshots so you can
"go back in time" and see exactly what was held on any date and
which strategy put it there.

Schema (portfolio_history.json):
{
  "last_updated": "2026-03-15",
  "snapshots":     [ DaySnapshot, ... ],   // one per equity-curve bar
  "positions":     [ Position,    ... ],   // every trade ever opened
  "transactions":  [ Transaction, ... ]    // OPEN + CLOSE events
}
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date as date_type
from pathlib import Path
from typing import Optional

import pandas as pd

STORE_PATH = Path(__file__).parent.parent / "portfolio_history.json"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _iso(val) -> str:
    """Convert any date-like value to an ISO date string, or '' on failure."""
    if val is None:
        return ""
    s = str(val)
    if s in ("NaT", "None", "nan", ""):
        return ""
    try:
        return str(pd.Timestamp(val).date())
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Position:
    """Represents a single spread that was opened (may now be closed)."""
    position_id: str
    strategy: str
    spread_type: str
    long_strike: float
    short_strike: float
    expiration: str
    entry_date: str        # ISO
    entry_cost: float      # net debit per share
    contracts: int


@dataclass
class Transaction:
    """A single OPEN or CLOSE event."""
    transaction_id: str
    strategy: str
    tx_type: str           # "OPEN" | "CLOSE"
    spread_type: str
    long_strike: float
    short_strike: float
    expiration: str
    date: str              # ISO
    price: float           # entry_cost (OPEN) or exit_value (CLOSE)
    contracts: int
    realized_pnl: float = 0.0
    exit_reason: str = ""
    linked_id: str = ""    # position_id this event belongs to


@dataclass
class DaySnapshot:
    """Portfolio state at end of a single trading day."""
    date: str
    equity: float
    cash: float = 0.0              # equity minus cost basis of open positions
    positions_value: float = 0.0   # cost basis of open positions
    open_position_ids: list = field(default_factory=list)
    strategy_weights: dict = field(default_factory=dict)
    daily_pnl: float = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Store
# ──────────────────────────────────────────────────────────────────────────────

class PortfolioStore:

    def __init__(self, path: Path = STORE_PATH):
        self.path = Path(path)
        self._snapshots: list[dict] = []
        self._positions: dict[str, dict] = {}   # position_id → dict
        self._transactions: list[dict] = []
        self.last_updated: str = ""

    # ── Persistence ────────────────────────────────────────────────────────

    def save(self):
        data = {
            "last_updated": self.last_updated,
            "snapshots":    self._snapshots,
            "positions":    list(self._positions.values()),
            "transactions": self._transactions,
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load(self) -> bool:
        """Load from disk. Returns True if the file existed."""
        if not self.path.exists():
            return False
        with open(self.path) as f:
            data = json.load(f)
        self._snapshots    = data.get("snapshots", [])
        self._positions    = {p["position_id"]: p for p in data.get("positions", [])}
        self._transactions = data.get("transactions", [])
        self.last_updated  = data.get("last_updated", "")
        return True

    # ── Build from backtest results ─────────────────────────────────────────

    def ingest_backtest(self, results: list, report: dict):
        """
        Convert BacktestResult list + portfolio report into the store's internal
        representation, then write to disk.
        """
        self._snapshots    = []
        self._positions    = {}
        self._transactions = []

        weights = report.get("weights", {})

        # Normalize blended equity index to ISO date strings
        blended: pd.Series = report.get("blended_equity", pd.Series(dtype=float))
        if not blended.empty:
            blended = blended.copy()
            blended.index = pd.Index([_iso(d) for d in blended.index])
        elif results:
            # Fall back to first result's equity curve when no blended curve exists
            blended = results[0].equity_curve.copy()
            blended.index = pd.Index([_iso(d) for d in blended.index])

        # ── Build positions & transactions ──────────────────────────────────
        # Also build a list of (pos_id, entry_iso, exit_iso) for snapshot lookup
        intervals: list[tuple[str, str, str]] = []

        for res in results:
            strategy  = res.strategy_name
            trades_df = res.trades

            if isinstance(trades_df, list):
                trades_df = (
                    pd.DataFrame([vars(t) for t in trades_df])
                    if trades_df else pd.DataFrame()
                )
            if trades_df.empty:
                continue

            for _, row in trades_df.iterrows():
                entry_d = _iso(row.get("entry_date"))
                exit_d  = _iso(row.get("exit_date"))

                if not entry_d:
                    continue

                pos_id = uuid.uuid4().hex[:10]

                pos = Position(
                    position_id=pos_id,
                    strategy=strategy,
                    spread_type=str(row.get("spread_type", "")),
                    long_strike=float(row.get("long_strike", 0)),
                    short_strike=float(row.get("short_strike", 0)),
                    expiration=str(row.get("expiration", "")),
                    entry_date=entry_d,
                    entry_cost=float(row.get("entry_cost", 0)),
                    contracts=int(row.get("contracts", 1)),
                )
                self._positions[pos_id] = asdict(pos)
                intervals.append((pos_id, entry_d, exit_d or "9999-12-31"))

                # OPEN transaction
                self._transactions.append(asdict(Transaction(
                    transaction_id=uuid.uuid4().hex[:10],
                    strategy=strategy,
                    tx_type="OPEN",
                    spread_type=pos.spread_type,
                    long_strike=pos.long_strike,
                    short_strike=pos.short_strike,
                    expiration=pos.expiration,
                    date=entry_d,
                    price=pos.entry_cost,
                    contracts=pos.contracts,
                    linked_id=pos_id,
                )))

                # CLOSE transaction (only if the trade was actually closed)
                if exit_d:
                    self._transactions.append(asdict(Transaction(
                        transaction_id=uuid.uuid4().hex[:10],
                        strategy=strategy,
                        tx_type="CLOSE",
                        spread_type=pos.spread_type,
                        long_strike=pos.long_strike,
                        short_strike=pos.short_strike,
                        expiration=pos.expiration,
                        date=exit_d,
                        price=float(row.get("exit_value", 0)),
                        contracts=pos.contracts,
                        realized_pnl=float(row.get("pnl", 0)),
                        exit_reason=str(row.get("exit_reason", "")),
                        linked_id=pos_id,
                    )))

        # ── Build daily snapshots ───────────────────────────────────────────
        all_dates  = sorted(blended.index.tolist()) if not blended.empty else []
        prev_equity: Optional[float] = None

        for d in all_dates:
            eq_val     = float(blended.get(d, 0.0))
            daily_pnl  = round(eq_val - prev_equity, 2) if prev_equity is not None else 0.0
            prev_equity = eq_val

            open_ids = [pid for pid, e, x in intervals if e <= d <= x]

            # Cash = equity minus the cost basis of all open positions
            pos_cost = sum(
                self._positions[pid]["entry_cost"] * self._positions[pid]["contracts"] * 100
                for pid in open_ids
                if pid in self._positions
            )
            cash_val = round(eq_val - pos_cost, 2)

            self._snapshots.append(asdict(DaySnapshot(
                date=d,
                equity=round(eq_val, 2),
                cash=cash_val,
                positions_value=round(pos_cost, 2),
                open_position_ids=open_ids,
                strategy_weights={k: round(float(v), 4) for k, v in weights.items()},
                daily_pnl=daily_pnl,
            )))

        self.last_updated = str(date_type.today())
        self.save()

    # ── Query ───────────────────────────────────────────────────────────────

    def get_all_dates(self) -> list[str]:
        return [s["date"] for s in self._snapshots]

    def get_snapshot(self, target_date: str) -> Optional[dict]:
        """Return the snapshot closest to (but not after) target_date."""
        candidates = [s for s in self._snapshots if s["date"] <= target_date]
        if not candidates:
            return self._snapshots[0] if self._snapshots else None
        return max(candidates, key=lambda s: s["date"])

    def get_positions_at(self, target_date: str) -> list[dict]:
        """Return all positions that were open on target_date."""
        snap = self.get_snapshot(target_date)
        if not snap:
            return []
        return [
            self._positions[i]
            for i in snap["open_position_ids"]
            if i in self._positions
        ]

    def get_transactions(self, start: str = "", end: str = "",
                         strategies: Optional[list] = None,
                         tx_types: Optional[list] = None) -> list[dict]:
        """Return transactions filtered by date range, strategy, and type."""
        txns = self._transactions
        if start:
            txns = [t for t in txns if t["date"] >= start]
        if end:
            txns = [t for t in txns if t["date"] <= end]
        if strategies:
            txns = [t for t in txns if t["strategy"] in strategies]
        if tx_types:
            txns = [t for t in txns if t["tx_type"] in tx_types]
        return sorted(txns, key=lambda t: t["date"], reverse=True)

    def all_strategies(self) -> list[str]:
        return sorted({t["strategy"] for t in self._transactions})

    def is_empty(self) -> bool:
        return len(self._snapshots) == 0

    @staticmethod
    def get_demo_positions() -> list[dict]:
        """Realistic-looking simulated positions shown when no real data exists."""
        from datetime import timedelta
        today = date_type.today()
        return [
            {
                "position_id": "demo_1",
                "strategy": "iron_condor_rules",
                "spread_type": "bull_call",
                "long_strike": 520.0,
                "short_strike": 525.0,
                "expiration": str(today + timedelta(days=18)),
                "entry_date": str(today - timedelta(days=6)),
                "entry_cost": 2.35,
                "contracts": 5,
            },
            {
                "position_id": "demo_2",
                "strategy": "vol_arbitrage",
                "spread_type": "bear_put",
                "long_strike": 515.0,
                "short_strike": 510.0,
                "expiration": str(today + timedelta(days=11)),
                "entry_date": str(today - timedelta(days=2)),
                "entry_cost": 1.90,
                "contracts": 8,
            },
            {
                "position_id": "demo_3",
                "strategy": "dividend_arb",
                "spread_type": "bull_put",
                "long_strike": 510.0,
                "short_strike": 516.0,
                "expiration": str(today + timedelta(days=4)),
                "entry_date": str(today - timedelta(days=1)),
                "entry_cost": -1.65,
                "contracts": 3,
            },
        ]
