"""
api/services/appdb.py — the service's own ``app`` schema in AlanStrats.

Created on first use (idempotent, each object only if missing), through the same write guard as
everything else — DDL is allowed in this schema only:

  app.PaperOrder   paper orders: the order as sent, its status, fills and the trade group it made
  app.Watchlist    named symbol lists
  app.Alert        price / change / IV alerts and when they fired
  app.IvHistory    each symbol's daily 30-day ATM IV (vol-stats' IV rank / percentile history)
  app.BacktestRun  a summary of every backtest job that succeeded (strategy-stats' expectation)
"""
from __future__ import annotations

import logging
import threading

from api.services.db import require_db

logger = logging.getLogger("alan_trader.api.appdb")

_TABLES = {
    "PaperOrder": """
        CREATE TABLE app.PaperOrder (
            OrderId            INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_PaperOrder PRIMARY KEY,
            AccountId          INT            NOT NULL,
            ClientOrderId      NVARCHAR(64)   NULL,
            Underlying         NVARCHAR(16)   NOT NULL,
            Strategy           NVARCHAR(50)   NOT NULL,
            Label              NVARCHAR(200)  NULL,
            OrderType          NVARCHAR(10)   NOT NULL,
            LimitPrice         DECIMAL(18,4)  NULL,
            Tif                NVARCHAR(8)    NOT NULL,
            Status             NVARCHAR(12)   NOT NULL,
            LegsJson           NVARCHAR(MAX)  NOT NULL,
            FillsJson          NVARCHAR(MAX)  NULL,
            FillPrice          DECIMAL(18,4)  NULL,
            TradeGroupId       NVARCHAR(50)   NULL,
            ClosesTradeGroupId NVARCHAR(50)   NULL,
            Message            NVARCHAR(400)  NULL,
            TradeDate          DATE           NOT NULL,
            CreatedAt          DATETIME2      NOT NULL CONSTRAINT DF_PaperOrder_Created DEFAULT SYSUTCDATETIME(),
            UpdatedAt          DATETIME2      NOT NULL CONSTRAINT DF_PaperOrder_Updated DEFAULT SYSUTCDATETIME(),
            FilledAt           DATETIME2      NULL
        )""",
    "Watchlist": """
        CREATE TABLE app.Watchlist (
            Name        NVARCHAR(100)  NOT NULL CONSTRAINT PK_Watchlist PRIMARY KEY,
            SymbolsJson NVARCHAR(MAX)  NOT NULL,
            CreatedAt   DATETIME2      NOT NULL CONSTRAINT DF_Watchlist_Created DEFAULT SYSUTCDATETIME(),
            UpdatedAt   DATETIME2      NOT NULL CONSTRAINT DF_Watchlist_Updated DEFAULT SYSUTCDATETIME()
        )""",
    "Alert": """
        CREATE TABLE app.Alert (
            AlertId     INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Alert PRIMARY KEY,
            Symbol      NVARCHAR(40)   NOT NULL,
            Field       NVARCHAR(16)   NOT NULL,
            Op          NVARCHAR(16)   NOT NULL,
            Value       FLOAT          NOT NULL,
            Note        NVARCHAR(400)  NULL,
            OnceOnly    BIT            NOT NULL CONSTRAINT DF_Alert_Once DEFAULT 1,
            Active      BIT            NOT NULL CONSTRAINT DF_Alert_Active DEFAULT 1,
            CreatedAt   DATETIME2      NOT NULL CONSTRAINT DF_Alert_Created DEFAULT SYSUTCDATETIME(),
            TriggeredAt DATETIME2      NULL,
            LastValue   FLOAT          NULL,
            TriggerCount INT           NOT NULL CONSTRAINT DF_Alert_Count DEFAULT 0
        )""",
    "IvHistory": """
        CREATE TABLE app.IvHistory (
            Symbol      NVARCHAR(40)   NOT NULL,
            TradeDate   DATE           NOT NULL,
            Iv30        FLOAT          NOT NULL,
            UpdatedAt   DATETIME2      NOT NULL CONSTRAINT DF_IvHistory_Updated DEFAULT SYSUTCDATETIME(),
            CONSTRAINT PK_IvHistory PRIMARY KEY (Symbol, TradeDate)
        )""",
    "BacktestRun": """
        CREATE TABLE app.BacktestRun (
            RunId          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_BacktestRun PRIMARY KEY,
            Slug           NVARCHAR(80)   NOT NULL,
            Ticker         NVARCHAR(20)   NOT NULL,
            FromDate       DATE           NOT NULL,
            ToDate         DATE           NOT NULL,
            Capital        FLOAT          NULL,
            ParamsJson     NVARCHAR(MAX)  NULL,
            Trades         INT            NULL,
            WinRate        FLOAT          NULL,
            AvgPnl         FLOAT          NULL,
            AvgWin         FLOAT          NULL,
            AvgLoss        FLOAT          NULL,
            ProfitFactor   FLOAT          NULL,
            TotalReturnPct FLOAT          NULL,
            Sharpe         FLOAT          NULL,
            MaxDrawdownPct FLOAT          NULL,
            RunAt          DATETIME2      NOT NULL CONSTRAINT DF_BacktestRun_RunAt DEFAULT SYSUTCDATETIME()
        )""",
}
_INDEXES = {
    ("PaperOrder", "UX_PaperOrder_Client"):
        "CREATE UNIQUE INDEX UX_PaperOrder_Client ON app.PaperOrder (AccountId, ClientOrderId) "
        "WHERE ClientOrderId IS NOT NULL",
    ("PaperOrder", "IX_PaperOrder_Status"):
        "CREATE INDEX IX_PaperOrder_Status ON app.PaperOrder (AccountId, Status)",
}

_LOCK = threading.Lock()
_READY: set[str] = set()


def exists(table: str) -> bool:
    """Whether ``app.<table>`` exists (read only; readers use it so a GET never creates anything)."""
    if table in _READY:
        return True
    from sqlalchemy import text
    with require_db().connect() as c:
        return c.execute(text("SELECT OBJECT_ID(:n, 'U')"), {"n": f"app.{table}"}).scalar() is not None


def ensure(*tables: str) -> None:
    """Create the ``app`` schema and the named tables (default: all) if they do not exist."""
    wanted = list(tables) or list(_TABLES)
    if all(t in _READY for t in wanted):
        return
    from sqlalchemy import text
    with _LOCK:
        eng = require_db()
        with eng.begin() as c:
            if c.execute(text("SELECT 1 FROM sys.schemas WHERE name = 'app'")).fetchone() is None:
                c.exec_driver_sql("CREATE SCHEMA app")
                logger.info("created schema app")
        for t in wanted:
            if t in _READY:
                continue
            with eng.begin() as c:
                if c.execute(text("SELECT OBJECT_ID(:n, 'U')"), {"n": f"app.{t}"}).scalar() is None:
                    c.exec_driver_sql(_TABLES[t])
                    logger.info("created table app.%s", t)
                for (tbl, name), ddl in _INDEXES.items():
                    if tbl != t:
                        continue
                    if c.execute(text("SELECT 1 FROM sys.indexes WHERE name = :n AND object_id = OBJECT_ID(:t)"),
                                 {"n": name, "t": f"app.{t}"}).fetchone() is None:
                        c.exec_driver_sql(ddl)
            _READY.add(t)
