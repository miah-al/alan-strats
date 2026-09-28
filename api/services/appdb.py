"""
api/services/appdb.py — the service's own ``app`` schema in AlanStrats.

Created on first use (idempotent, each object only if missing), through the same write guard as
everything else — DDL is allowed in this schema only:

  app.PaperOrder   paper orders: the order as sent, its status, fills and the trade group it made
  app.Watchlist    named symbol lists
  app.Alert        price / change / IV alerts and when they fired
  app.IvHistory    each symbol's daily 30-day ATM IV (vol-stats' IV rank / percentile history)
  app.BacktestRun  a summary of every backtest job that succeeded (strategy-stats' expectation)
  app.GexHistory   live dealer GEX recorded each trading day (and every 30 min while streaming)
  app.RunnerArm    armed scheduled paper runs (a strategy, its variant, once / weekdays) and their last result
  app.GexAllocState the GEX paper allocator's state per variant (the VIX variant's streak / cooldown)
  app.GexAllocLog  the GEX paper allocator's daily decisions (regime, weight, target, orders)
  app.EventLog     the event desk's manual event log (war news / posts: kind, region, barrels lost?)
  app.EventDeskSetting  the event desk's settings (the war-regime switch)
  app.EventDeskLog the event desk's allocators' daily decisions (oil_fade / btc_dip: trade or not, and why)
  app.EventSignalLog the post-close signal log (USO 2σ moves, VIX 2σ, BTC −3%) with the trader's tag and outcomes
  app.CryptoFlushSignal the crypto liquidation-flush triggers (R0) and their log-only paper micro-future legs
  app.MorningBrief the AI morning brief's decision row per strategy and day (api/services/morning_brief.py)
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
    "GexHistory": """
        CREATE TABLE app.GexHistory (
            Id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_GexHistory PRIMARY KEY,
            Ticker         NVARCHAR(20)   NOT NULL,
            Kind           NVARCHAR(10)   NOT NULL,
            SlotTs         DATETIME2      NOT NULL,
            TradeDate      DATE           NOT NULL,
            Spot           FLOAT          NULL,
            NetGex         FLOAT          NULL,
            CallGex        FLOAT          NULL,
            PutGex         FLOAT          NULL,
            Flip           FLOAT          NULL,
            CallWall       FLOAT          NULL,
            PutWall        FLOAT          NULL,
            DistToFlipPct  FLOAT          NULL,
            Regime         NVARCHAR(12)   NULL,
            MaxPain        FLOAT          NULL,
            NetGex0Dte     FLOAT          NULL,
            Contracts      INT            NULL,
            Source         NVARCHAR(60)   NULL,
            RecordedAt     DATETIME2      NOT NULL CONSTRAINT DF_GexHistory_At DEFAULT SYSUTCDATETIME()
        )""",
    "RunnerArm": """
        CREATE TABLE app.RunnerArm (
            ArmId          INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_RunnerArm PRIMARY KEY,
            Strategy       NVARCHAR(80)   NOT NULL,
            Variant        NVARCHAR(20)   NOT NULL CONSTRAINT DF_RunnerArm_Variant DEFAULT '',
            Schedule       NVARCHAR(10)   NOT NULL,
            ArmDate        DATE           NULL,
            Mode           NVARCHAR(10)   NOT NULL CONSTRAINT DF_RunnerArm_Mode DEFAULT 'paper',
            Active         BIT            NOT NULL CONSTRAINT DF_RunnerArm_Active DEFAULT 1,
            ArmedAt        DATETIME2      NOT NULL CONSTRAINT DF_RunnerArm_ArmedAt DEFAULT SYSUTCDATETIME(),
            DisarmedAt     DATETIME2      NULL,
            LastRunDate    DATE           NULL,
            LastRunAt      DATETIME2      NULL,
            LastResult     NVARCHAR(400)  NULL,
            RunPid         INT            NULL,
            RunCreated     FLOAT          NULL,
            RunLog         NVARCHAR(400)  NULL,
            UpdatedAt      DATETIME2      NOT NULL CONSTRAINT DF_RunnerArm_Updated DEFAULT SYSUTCDATETIME()
        )""",
    "GexAllocState": """
        CREATE TABLE app.GexAllocState (
            Variant        NVARCHAR(10)   NOT NULL CONSTRAINT PK_GexAllocState PRIMARY KEY,
            AsOf           DATE           NULL,
            StateJson      NVARCHAR(MAX)  NOT NULL,
            UpdatedAt      DATETIME2      NOT NULL CONSTRAINT DF_GexAllocState_Updated DEFAULT SYSUTCDATETIME()
        )""",
    "GexAllocLog": """
        CREATE TABLE app.GexAllocLog (
            Id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_GexAllocLog PRIMARY KEY,
            Variant        NVARCHAR(10)   NOT NULL,
            TradeDate      DATE           NOT NULL,
            Status         NVARCHAR(20)   NOT NULL,
            Regime         NVARCHAR(20)   NULL,
            Weight         FLOAT          NULL,
            Equity         FLOAT          NULL,
            Price          FLOAT          NULL,
            CurrentShares  INT            NULL,
            TargetShares   INT            NULL,
            DetailJson     NVARCHAR(MAX)  NULL,
            DecidedAt      DATETIME2      NOT NULL CONSTRAINT DF_GexAllocLog_At DEFAULT SYSUTCDATETIME()
        )""",
    "EventLog": """
        CREATE TABLE app.EventLog (
            EventId        INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EventLog PRIMARY KEY,
            Ts             DATETIME2      NOT NULL,
            Kind           NVARCHAR(16)   NOT NULL,
            Region         NVARCHAR(80)   NULL,
            EventText      NVARCHAR(1000) NOT NULL,
            BarrelsLost    NVARCHAR(8)    NOT NULL CONSTRAINT DF_EventLog_Barrels DEFAULT 'unknown',
            Source         NVARCHAR(400)  NULL,
            CreatedAt      DATETIME2      NOT NULL CONSTRAINT DF_EventLog_Created DEFAULT SYSUTCDATETIME()
        )""",
    "EventDeskSetting": """
        CREATE TABLE app.EventDeskSetting (
            Name           NVARCHAR(40)   NOT NULL CONSTRAINT PK_EventDeskSetting PRIMARY KEY,
            ValueJson      NVARCHAR(MAX)  NOT NULL,
            UpdatedAt      DATETIME2      NOT NULL CONSTRAINT DF_EventDeskSetting_Updated DEFAULT SYSUTCDATETIME()
        )""",
    "EventDeskLog": """
        CREATE TABLE app.EventDeskLog (
            Id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EventDeskLog PRIMARY KEY,
            Playbook       NVARCHAR(24)   NOT NULL,
            TradeDate      DATE           NOT NULL,
            Status         NVARCHAR(20)   NOT NULL,
            Verdict        NVARCHAR(12)   NULL,
            Action         NVARCHAR(12)   NULL,
            TradeGroupId   NVARCHAR(50)   NULL,
            Summary        NVARCHAR(400)  NULL,
            DetailJson     NVARCHAR(MAX)  NULL,
            DecidedAt      DATETIME2      NOT NULL CONSTRAINT DF_EventDeskLog_At DEFAULT SYSUTCDATETIME()
        )""",
    "EventSignalLog": """
        CREATE TABLE app.EventSignalLog (
            Id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EventSignalLog PRIMARY KEY,
            TradeDate      DATE           NOT NULL,
            Symbol         NVARCHAR(10)   NOT NULL,
            ClosePx        FLOAT          NULL,
            ChangePct      FLOAT          NULL,
            MoveZ          FLOAT          NULL,
            LevelZ         FLOAT          NULL,
            Mean20         FLOAT          NULL,
            Sd20           FLOAT          NULL,
            VixClose       FLOAT          NULL,
            VixChangePct   FLOAT          NULL,
            Ovx            FLOAT          NULL,
            Tag            NVARCHAR(24)   NULL,
            Note           NVARCHAR(400)  NULL,
            TaggedAt       DATETIME2      NULL,
            HalfBack       BIT            NULL,
            HalfBackDays   INT            NULL,
            R3             FLOAT          NULL,
            R10            FLOAT          NULL,
            R20            FLOAT          NULL,
            OutcomeAsOf    DATE           NULL,
            CreatedAt      DATETIME2      NOT NULL CONSTRAINT DF_EventSignalLog_Created DEFAULT SYSUTCDATETIME()
        )""",
    "CryptoFlushSignal": """
        CREATE TABLE app.CryptoFlushSignal (
            Id             INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_CryptoFlushSignal PRIMARY KEY,
            Ts             DATETIME2      NOT NULL,
            Coin           NVARCHAR(8)    NOT NULL,
            Price          FLOAT          NULL,
            Max240         FLOAT          NULL,
            DropPct        FLOAT          NULL,
            Oi             FLOAT          NULL,
            OiMax240       FLOAT          NULL,
            OiDropPct      FLOAT          NULL,
            OiAgeMin       FLOAT          NULL,
            Trade          BIT            NOT NULL CONSTRAINT DF_CryptoFlushSignal_Trade DEFAULT 0,
            Micro          NVARCHAR(8)    NULL,
            Size           FLOAT          NULL,
            EntryTs        DATETIME2      NULL,
            EntryPrice     FLOAT          NULL,
            ExitTs         DATETIME2      NULL,
            ExitPrice      FLOAT          NULL,
            PnlUsd         FLOAT          NULL,
            RetPct         FLOAT          NULL,
            R1h            FLOAT          NULL,
            R4h            FLOAT          NULL,
            R24h           FLOAT          NULL,
            CreatedAt      DATETIME2      NOT NULL CONSTRAINT DF_CryptoFlushSignal_Created DEFAULT SYSUTCDATETIME()
        )""",
    "MorningBrief": """
        CREATE TABLE app.MorningBrief (
            BriefId        INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_MorningBrief PRIMARY KEY,
            Strategy       NVARCHAR(80)   NOT NULL CONSTRAINT DF_MorningBrief_Strategy DEFAULT 'ndx_0dte_condor',
            BriefDate      DATE           NOT NULL,
            CreatedAt      DATETIME2      NOT NULL CONSTRAINT DF_MorningBrief_Created DEFAULT SYSUTCDATETIME(),
            Decision       NVARCHAR(12)   NOT NULL,
            Confidence     FLOAT          NOT NULL,
            SizeMultiplier FLOAT          NOT NULL,
            Headline       NVARCHAR(400)  NULL,
            ReasonsJson    NVARCHAR(MAX)  NULL,
            EventsJson     NVARCHAR(MAX)  NULL,
            FlagsJson      NVARCHAR(MAX)  NULL,
            ChangeMind     NVARCHAR(600)  NULL,
            Source         NVARCHAR(60)   NOT NULL,
            PromptVersion  NVARCHAR(30)   NULL,
            InputsJson     NVARCHAR(MAX)  NULL,
            NotesJson      NVARCHAR(MAX)  NULL
        )""",
}
_INDEXES = {
    ("GexAllocLog", "UX_GexAllocLog_Day"):
        "CREATE UNIQUE INDEX UX_GexAllocLog_Day ON app.GexAllocLog (Variant, TradeDate)",
    ("RunnerArm", "UX_RunnerArm_Active"):
        "CREATE UNIQUE INDEX UX_RunnerArm_Active ON app.RunnerArm (Strategy, Variant) WHERE Active = 1",
    ("GexHistory", "UX_GexHistory_Slot"):
        "CREATE UNIQUE INDEX UX_GexHistory_Slot ON app.GexHistory (Ticker, Kind, SlotTs)",
    ("PaperOrder", "UX_PaperOrder_Client"):
        "CREATE UNIQUE INDEX UX_PaperOrder_Client ON app.PaperOrder (AccountId, ClientOrderId) "
        "WHERE ClientOrderId IS NOT NULL",
    ("PaperOrder", "IX_PaperOrder_Status"):
        "CREATE INDEX IX_PaperOrder_Status ON app.PaperOrder (AccountId, Status)",
    ("EventLog", "IX_EventLog_Ts"):
        "CREATE INDEX IX_EventLog_Ts ON app.EventLog (Ts)",
    ("EventDeskLog", "UX_EventDeskLog_Day"):
        "CREATE UNIQUE INDEX UX_EventDeskLog_Day ON app.EventDeskLog (Playbook, TradeDate)",
    ("EventSignalLog", "UX_EventSignalLog_Day"):
        "CREATE UNIQUE INDEX UX_EventSignalLog_Day ON app.EventSignalLog (TradeDate, Symbol)",
    ("CryptoFlushSignal", "IX_CryptoFlushSignal_Ts"):
        "CREATE INDEX IX_CryptoFlushSignal_Ts ON app.CryptoFlushSignal (Coin, Ts)",
    ("MorningBrief", "UX_MorningBrief_Day"):
        "CREATE UNIQUE INDEX UX_MorningBrief_Day ON app.MorningBrief (Strategy, BriefDate)",
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
