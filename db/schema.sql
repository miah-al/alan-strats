-- ============================================================
-- alan-strats  |  Full Database Schema
-- SQL Server Express  |  Windows Auth
-- Run once on a fresh database — fully idempotent.
-- ============================================================

USE master;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'AlanStrats')
    CREATE DATABASE AlanStrats;
GO

USE AlanStrats;
GO

-- ============================================================
-- SCHEMAS
-- ============================================================

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'mkt')
    EXEC('CREATE SCHEMA mkt');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'portfolio')
    EXEC('CREATE SCHEMA portfolio');
GO


-- ============================================================
-- mkt.Ticker
-- Security master — equities, ETFs, indices, cash, options
-- ============================================================

IF OBJECT_ID('mkt.Ticker', 'U') IS NULL
BEGIN
    CREATE TABLE mkt.Ticker (
        TickerId        SMALLINT        NOT NULL IDENTITY(1,1),
        Symbol          VARCHAR(10)     NOT NULL,
        Name            VARCHAR(100)    NULL,
        AssetClass      VARCHAR(20)     NOT NULL DEFAULT 'equity',   -- equity | etf | index | cash
        InstrumentType  VARCHAR(10)     NULL,                         -- stock | etf | index | cash | option
        Exchange        VARCHAR(20)     NULL,
        Currency        CHAR(3)         NOT NULL DEFAULT 'USD',
        IsActive        BIT             NOT NULL DEFAULT 1,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_Ticker        PRIMARY KEY (TickerId),
        CONSTRAINT UQ_Ticker_Symbol UNIQUE      (Symbol)
    );
END
ELSE
BEGIN
    -- Add columns if upgrading from older schema
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('mkt.Ticker') AND name = 'InstrumentType')
        ALTER TABLE mkt.Ticker ADD InstrumentType VARCHAR(10) NULL;
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('mkt.Ticker') AND name = 'Exchange')
        ALTER TABLE mkt.Ticker ADD Exchange VARCHAR(20) NULL;
    IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('mkt.Ticker') AND name = 'Currency')
        ALTER TABLE mkt.Ticker ADD Currency CHAR(3) NOT NULL DEFAULT 'USD';
END
GO

-- Backfill InstrumentType from AssetClass
UPDATE mkt.Ticker SET InstrumentType = 'etf'   WHERE AssetClass = 'etf'    AND InstrumentType IS NULL;
UPDATE mkt.Ticker SET InstrumentType = 'stock' WHERE AssetClass = 'equity' AND InstrumentType IS NULL;
UPDATE mkt.Ticker SET InstrumentType = 'index' WHERE AssetClass = 'index'  AND InstrumentType IS NULL;
GO

-- Seed tickers
IF NOT EXISTS (SELECT 1 FROM mkt.Ticker WHERE Symbol = 'CASH')
    INSERT INTO mkt.Ticker (Symbol, Name, AssetClass, InstrumentType, IsActive)
    VALUES ('CASH', 'Cash (USD)', 'cash', 'cash', 1);

IF NOT EXISTS (SELECT 1 FROM mkt.Ticker WHERE Symbol = 'SPY')
    INSERT INTO mkt.Ticker (Symbol, Name, AssetClass, InstrumentType, Exchange)
    VALUES ('SPY', 'SPDR S&P 500 ETF Trust', 'etf', 'etf', 'NYSE');
ELSE
    UPDATE mkt.Ticker SET InstrumentType = 'etf', Exchange = 'NYSE' WHERE Symbol = 'SPY';

IF NOT EXISTS (SELECT 1 FROM mkt.Ticker WHERE Symbol = 'TLT')
    INSERT INTO mkt.Ticker (Symbol, Name, AssetClass, InstrumentType, Exchange)
    VALUES ('TLT', 'iShares 20+ Year Treasury Bond ETF', 'etf', 'etf', 'NYSE');
ELSE
    UPDATE mkt.Ticker SET InstrumentType = 'etf', Exchange = 'NYSE' WHERE Symbol = 'TLT';

IF NOT EXISTS (SELECT 1 FROM mkt.Ticker WHERE Symbol = 'HOOD')
    INSERT INTO mkt.Ticker (Symbol, Name, AssetClass, InstrumentType) VALUES ('HOOD', 'Robinhood Markets', 'equity', 'stock');

IF NOT EXISTS (SELECT 1 FROM mkt.Ticker WHERE Symbol = 'QQQ')
    INSERT INTO mkt.Ticker (Symbol, Name, AssetClass, InstrumentType) VALUES ('QQQ', 'Invesco QQQ Trust', 'etf', 'etf');

IF NOT EXISTS (SELECT 1 FROM mkt.Ticker WHERE Symbol = 'AAPL')
    INSERT INTO mkt.Ticker (Symbol, Name, AssetClass, InstrumentType) VALUES ('AAPL', 'Apple Inc.', 'equity', 'stock');

IF NOT EXISTS (SELECT 1 FROM mkt.Ticker WHERE Symbol = 'TSLA')
    INSERT INTO mkt.Ticker (Symbol, Name, AssetClass, InstrumentType) VALUES ('TSLA', 'Tesla Inc.', 'equity', 'stock');

IF NOT EXISTS (SELECT 1 FROM mkt.Ticker WHERE Symbol = 'MARA')
    INSERT INTO mkt.Ticker (Symbol, Name, AssetClass, InstrumentType) VALUES ('MARA', 'Marathon Digital', 'equity', 'stock');
GO


-- ============================================================
-- mkt.PriceBar
-- Daily OHLCV price bars
-- ============================================================

IF OBJECT_ID('mkt.PriceBar', 'U') IS NULL
BEGIN
    CREATE TABLE mkt.PriceBar (
        TickerId        SMALLINT        NOT NULL,
        BarDate         DATE            NOT NULL,
        [Open]          DECIMAL(12,4)   NOT NULL,
        High            DECIMAL(12,4)   NOT NULL,
        Low             DECIMAL(12,4)   NOT NULL,
        [Close]         DECIMAL(12,4)   NOT NULL,
        Volume          BIGINT          NOT NULL,
        Vwap            DECIMAL(12,4)   NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_PriceBar        PRIMARY KEY (TickerId, BarDate),
        CONSTRAINT FK_PriceBar_Ticker FOREIGN KEY (TickerId) REFERENCES mkt.Ticker(TickerId)
    );

    CREATE INDEX IX_PriceBar_BarDate ON mkt.PriceBar (BarDate DESC);
END
GO


-- ============================================================
-- mkt.OptionSnapshot
-- EOD options chain — one row per contract per day
-- ============================================================

IF OBJECT_ID('mkt.OptionSnapshot', 'U') IS NULL
BEGIN
    CREATE TABLE mkt.OptionSnapshot (
        TickerId            SMALLINT        NOT NULL,
        SnapshotDate        DATE            NOT NULL,
        ExpirationDate      DATE            NOT NULL,
        Strike              DECIMAL(10,2)   NOT NULL,
        ContractType        CHAR(1)         NOT NULL,   -- C | P
        Bid                 DECIMAL(10,4)   NULL,
        Ask                 DECIMAL(10,4)   NULL,
        Mid                 DECIMAL(10,4)   NULL,
        LastPrice           DECIMAL(10,4)   NULL,
        ImpliedVol          DECIMAL(8,6)    NULL,
        Delta               DECIMAL(8,6)    NULL,
        Gamma               DECIMAL(10,8)   NULL,
        Theta               DECIMAL(8,6)    NULL,
        Vega                DECIMAL(8,6)    NULL,
        OpenInterest        INT             NULL,
        Volume              INT             NULL,
        CreatedAt           DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_OptionSnapshot        PRIMARY KEY (TickerId, SnapshotDate, ExpirationDate, Strike, ContractType),
        CONSTRAINT FK_OptionSnapshot_Ticker FOREIGN KEY (TickerId) REFERENCES mkt.Ticker(TickerId),
        CONSTRAINT CK_OptionSnapshot_Type   CHECK (ContractType IN ('C', 'P'))
    );

    CREATE INDEX IX_OptionSnapshot_Ticker_Date   ON mkt.OptionSnapshot (TickerId, SnapshotDate DESC);
    CREATE INDEX IX_OptionSnapshot_Ticker_Expiry ON mkt.OptionSnapshot (TickerId, ExpirationDate, SnapshotDate DESC);
    CREATE INDEX IX_OptionSnapshot_Contract      ON mkt.OptionSnapshot (TickerId, SnapshotDate, ContractType, Strike);
END
GO


-- ============================================================
-- mkt.MacroBar
-- Full yield curve (3M–30Y), SOFR, jobless claims — from FRED
-- ============================================================

IF OBJECT_ID('mkt.MacroBar', 'U') IS NULL
BEGIN
    CREATE TABLE mkt.MacroBar (
        BarDate         DATE            NOT NULL,
        Rate2Y          DECIMAL(6,4)    NULL,
        Rate10Y         DECIMAL(6,4)    NULL,
        YieldSpread     DECIMAL(6,4)    NULL,
        Rate3M          DECIMAL(6,4)    NULL,
        Rate6M          DECIMAL(6,4)    NULL,
        Rate1Y          DECIMAL(6,4)    NULL,
        Rate5Y          DECIMAL(6,4)    NULL,
        Rate30Y         DECIMAL(6,4)    NULL,
        Curve3m10y      DECIMAL(6,4)    NULL,
        Curve5y30y      DECIMAL(6,4)    NULL,
        CurveButterfly  DECIMAL(6,4)    NULL,
        Sofr            DECIMAL(6,4)    NULL,
        JoblessClaims   INT             NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_MacroBar PRIMARY KEY (BarDate)
    );
END
GO


-- ============================================================
-- mkt.VixBar
-- Daily VIX OHLCV
-- ============================================================

IF OBJECT_ID('mkt.VixBar', 'U') IS NULL
BEGIN
    CREATE TABLE mkt.VixBar (
        BarDate         DATE            NOT NULL,
        [Open]          DECIMAL(8,4)    NOT NULL,
        High            DECIMAL(8,4)    NOT NULL,
        Low             DECIMAL(8,4)    NOT NULL,
        [Close]         DECIMAL(8,4)    NOT NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_VixBar PRIMARY KEY (BarDate)
    );
END
GO


-- ============================================================
-- mkt.FomcCalendar
-- FOMC meeting dates
-- ============================================================

IF OBJECT_ID('mkt.FomcCalendar', 'U') IS NULL
BEGIN
    CREATE TABLE mkt.FomcCalendar (
        MeetingId       INT             NOT NULL IDENTITY(1,1),
        MeetingDate     DATE            NOT NULL,
        IsRateDecision  BIT             NOT NULL DEFAULT 1,
        RateChange      DECIMAL(4,2)    NULL,
        Notes           NVARCHAR(200)   NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_FomcCalendar      PRIMARY KEY (MeetingId),
        CONSTRAINT UQ_FomcCalendar_Date UNIQUE (MeetingDate)
    );
END
GO


-- ============================================================
-- mkt.News
-- News articles from Polygon, VADER-scored sentiment
-- ============================================================

IF OBJECT_ID('mkt.News', 'U') IS NULL
BEGIN
    CREATE TABLE mkt.News (
        NewsId          INT             NOT NULL IDENTITY(1,1),
        TickerId        SMALLINT        NOT NULL,
        ArticleId       VARCHAR(50)     NOT NULL,
        PublishedAt     DATETIME2(0)    NOT NULL,
        PublishedDate   DATE            NOT NULL,
        Title           NVARCHAR(MAX)   NOT NULL,
        Description     NVARCHAR(MAX)   NULL,
        Sentiment       DECIMAL(5,4)    NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_News          PRIMARY KEY (NewsId),
        CONSTRAINT UQ_News_Article  UNIQUE      (TickerId, ArticleId),
        CONSTRAINT FK_News_Ticker   FOREIGN KEY (TickerId) REFERENCES mkt.Ticker(TickerId)
    );

    CREATE INDEX IX_News_PublishedDate ON mkt.News (TickerId, PublishedDate DESC);
END
GO


-- ============================================================
-- mkt.SyncLog
-- Last successful sync per ticker + data type
-- ============================================================

IF OBJECT_ID('mkt.SyncLog', 'U') IS NULL
BEGIN
    CREATE TABLE mkt.SyncLog (
        SyncLogId       INT             NOT NULL IDENTITY(1,1),
        TickerId        SMALLINT        NULL,
        DataType        VARCHAR(30)     NOT NULL,
        LastSyncDate    DATE            NOT NULL,
        RowsInserted    INT             NOT NULL DEFAULT 0,
        SyncedAt        DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),
        ErrorMessage    NVARCHAR(MAX)   NULL,

        CONSTRAINT PK_SyncLog        PRIMARY KEY (SyncLogId),
        CONSTRAINT FK_SyncLog_Ticker FOREIGN KEY (TickerId) REFERENCES mkt.Ticker(TickerId)
    );

    CREATE INDEX IX_SyncLog_Lookup ON mkt.SyncLog (TickerId, DataType, SyncedAt DESC);
END
GO


-- ============================================================
-- portfolio.Account
-- One row per brokerage / paper account
-- ============================================================

IF OBJECT_ID('portfolio.Account', 'U') IS NULL
BEGIN
    CREATE TABLE portfolio.Account (
        AccountId       INT             NOT NULL IDENTITY(1,1),
        Name            VARCHAR(100)    NOT NULL,
        BrokerName      VARCHAR(50)     NOT NULL,
        AccountNumber   VARCHAR(50)     NULL,
        AccountType     VARCHAR(10)     NOT NULL DEFAULT 'margin',
        Currency        CHAR(3)         NOT NULL DEFAULT 'USD',
        IsActive        BIT             NOT NULL DEFAULT 1,
        Notes           NVARCHAR(500)   NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_Account      PRIMARY KEY (AccountId),
        CONSTRAINT CK_Account_Type CHECK (AccountType IN ('margin','cash','ira','paper'))
    );

    INSERT INTO portfolio.Account (Name, BrokerName, AccountType, Notes)
    VALUES ('Paper Account', 'Paper', 'paper', 'Default paper trading account');
END
GO


-- ============================================================
-- portfolio.Balance
-- Daily account balance snapshots
-- ============================================================

IF OBJECT_ID('portfolio.Balance', 'U') IS NULL
BEGIN
    CREATE TABLE portfolio.Balance (
        BalanceId       INT             NOT NULL IDENTITY(1,1),
        AccountId       INT             NOT NULL,
        BalanceDate     DATE            NOT NULL,
        CashBalance     DECIMAL(14,2)   NOT NULL DEFAULT 0,
        PortfolioValue  DECIMAL(14,2)   NOT NULL DEFAULT 0,
        TotalEquity     DECIMAL(14,2)   NOT NULL DEFAULT 0,
        DayPnL          DECIMAL(12,2)   NULL,
        RealizedYTD     DECIMAL(12,2)   NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_Balance         PRIMARY KEY (BalanceId),
        CONSTRAINT UQ_Balance_Date    UNIQUE (AccountId, BalanceDate),
        CONSTRAINT FK_Balance_Account FOREIGN KEY (AccountId) REFERENCES portfolio.Account(AccountId)
    );
END
GO


-- ============================================================
-- portfolio.Position
-- Generic position — equities, ETF rotations, option spreads
-- ============================================================

IF OBJECT_ID('portfolio.Position', 'U') IS NULL
BEGIN
    CREATE TABLE portfolio.Position (
        PositionId      BIGINT          NOT NULL IDENTITY(1,1),
        AccountId       INT             NOT NULL,
        SecurityId      BIGINT          NOT NULL,
        PositionType    VARCHAR(20)     NOT NULL DEFAULT 'equity',
        Direction       VARCHAR(5)      NOT NULL DEFAULT 'long',
        Quantity        DECIMAL(12,4)   NOT NULL,
        OpenDate        DATE            NOT NULL,
        CloseDate       DATE            NULL,
        Status          VARCHAR(20)     NOT NULL DEFAULT 'open',
        AvgEntryPrice   DECIMAL(10,4)   NOT NULL,
        AvgExitPrice    DECIMAL(10,4)   NULL,
        RealizedPnL     DECIMAL(12,2)   NULL,
        Commission      DECIMAL(10,2)   NOT NULL DEFAULT 0,
        Regime          VARCHAR(30)     NULL,
        StrategyName    VARCHAR(50)     NULL,
        Source          VARCHAR(20)     NOT NULL DEFAULT 'manual',
        Tags            VARCHAR(200)    NULL,
        Notes           NVARCHAR(MAX)   NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),
        UpdatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_Position         PRIMARY KEY (PositionId),
        CONSTRAINT FK_Position_Account FOREIGN KEY (AccountId)  REFERENCES portfolio.Account(AccountId),
        CONSTRAINT CK_Position_Status  CHECK (Status   IN ('open','closed','expired','assigned','rolled')),
        CONSTRAINT CK_Position_Type    CHECK (PositionType IN ('equity','etf_rotation','option_spread','cash')),
        CONSTRAINT CK_Position_Dir     CHECK (Direction IN ('long','short'))
    );

    CREATE INDEX IX_Position_Security ON portfolio.Position (SecurityId, OpenDate DESC);
    CREATE INDEX IX_Position_Status   ON portfolio.Position (Status, AccountId);
END
GO


-- ============================================================
-- portfolio.Leg
-- Individual option legs for spread positions
-- ============================================================

IF OBJECT_ID('portfolio.Leg', 'U') IS NULL
BEGIN
    CREATE TABLE portfolio.Leg (
        LegId           INT             NOT NULL IDENTITY(1,1),
        PositionId      BIGINT          NOT NULL,
        Symbol          VARCHAR(10)     NOT NULL,
        OptionSymbol    VARCHAR(30)     NULL,
        InstrumentType  VARCHAR(10)     NOT NULL DEFAULT 'option',
        Action          VARCHAR(4)      NOT NULL,
        Contracts       SMALLINT        NOT NULL DEFAULT 1,
        Strike          DECIMAL(10,2)   NULL,
        Expiration      DATE            NULL,
        ContractType    CHAR(1)         NULL,
        FillPrice       DECIMAL(10,4)   NOT NULL,
        Commission      DECIMAL(8,2)    NOT NULL DEFAULT 0,
        FillDate        DATE            NOT NULL,
        LegOrder        TINYINT         NOT NULL DEFAULT 1,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_Leg              PRIMARY KEY (LegId),
        CONSTRAINT FK_Leg_Position     FOREIGN KEY (PositionId)   REFERENCES portfolio.Position(PositionId),
        CONSTRAINT CK_Leg_Action       CHECK (Action IN ('BTO','STO','BTC','STC')),
        CONSTRAINT CK_Leg_ContractType CHECK (ContractType IN ('C','P') OR ContractType IS NULL)
    );

    CREATE INDEX IX_Leg_Position ON portfolio.Leg (PositionId);
END
GO


-- ============================================================
-- portfolio.DailyMark
-- Daily MTM per position
-- ============================================================

IF OBJECT_ID('portfolio.DailyMark', 'U') IS NULL
BEGIN
    CREATE TABLE portfolio.DailyMark (
        MarkId          INT             NOT NULL IDENTITY(1,1),
        PositionId      BIGINT          NOT NULL,
        MarkDate        DATE            NOT NULL,
        MarkValue       DECIMAL(10,4)   NOT NULL,
        DayPnL          DECIMAL(12,2)   NULL,
        CumPnL          DECIMAL(12,2)   NULL,
        DTE             SMALLINT        NULL,
        Delta           DECIMAL(8,4)    NULL,
        Theta           DECIMAL(8,4)    NULL,
        Vega            DECIMAL(8,4)    NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_DailyMark          PRIMARY KEY (MarkId),
        CONSTRAINT UQ_DailyMark_Date     UNIQUE (PositionId, MarkDate),
        CONSTRAINT FK_DailyMark_Position FOREIGN KEY (PositionId) REFERENCES portfolio.Position(PositionId)
    );

    CREATE INDEX IX_DailyMark_Position ON portfolio.DailyMark (PositionId, MarkDate DESC);
END
GO


-- ============================================================
-- portfolio.ModelSignal
-- Logged model signals with outcome tracking
-- ============================================================

IF OBJECT_ID('portfolio.ModelSignal', 'U') IS NULL
BEGIN
    CREATE TABLE portfolio.ModelSignal (
        SignalId        INT             NOT NULL IDENTITY(1,1),
        SignalDate      DATE            NOT NULL,
        Symbol          VARCHAR(10)     NOT NULL,
        SpreadType      VARCHAR(30)     NOT NULL,
        PredictedLabel  TINYINT         NOT NULL,
        Confidence      DECIMAL(5,4)    NOT NULL,
        ModelVersion    VARCHAR(50)     NULL,
        WasTaken        BIT             NOT NULL DEFAULT 0,
        PositionId      BIGINT          NULL,
        Notes           NVARCHAR(500)   NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_ModelSignal          PRIMARY KEY (SignalId),
        CONSTRAINT FK_ModelSignal_Position FOREIGN KEY (PositionId) REFERENCES portfolio.Position(PositionId),
        CONSTRAINT CK_ModelSignal_Label    CHECK (PredictedLabel IN (0,1,2))
    );

    CREATE INDEX IX_ModelSignal_Date ON portfolio.ModelSignal (Symbol, SignalDate DESC);
END
GO


-- ============================================================
-- portfolio.[Transaction]
-- Every buy/sell/deposit/dividend/fee event
-- ============================================================

IF OBJECT_ID('portfolio.Transaction', 'U') IS NULL
BEGIN
    CREATE TABLE portfolio.[Transaction] (
        TransactionId   BIGINT          NOT NULL IDENTITY(1,1),
        AccountId       INT             NOT NULL,
        SecurityId      BIGINT          NOT NULL,
        PositionId      BIGINT          NULL,
        TransactionDate DATE            NOT NULL,
        Action          VARCHAR(10)     NOT NULL,
        Quantity        DECIMAL(12,4)   NULL,
        Price           DECIMAL(10,4)   NULL,
        Amount          DECIMAL(14,2)   NOT NULL,
        Commission      DECIMAL(8,2)    NOT NULL DEFAULT 0,
        Regime          VARCHAR(30)     NULL,
        StrategyName    VARCHAR(50)     NULL,
        Notes           NVARCHAR(500)   NULL,
        CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_Transaction  PRIMARY KEY (TransactionId),
        CONSTRAINT FK_Txn_Account  FOREIGN KEY (AccountId)  REFERENCES portfolio.Account(AccountId),
        CONSTRAINT FK_Txn_Position FOREIGN KEY (PositionId) REFERENCES portfolio.Position(PositionId),
        CONSTRAINT CK_Txn_Action   CHECK (Action IN ('BUY','SELL','DEPOSIT','WITHDRAW','DIVIDEND','FEE'))
    );

    CREATE INDEX IX_Transaction_Account  ON portfolio.[Transaction] (AccountId,  TransactionDate DESC);
    CREATE INDEX IX_Transaction_Security ON portfolio.[Transaction] (SecurityId, TransactionDate DESC);
END
GO


-- ============================================================
-- portfolio.Holding
-- Current position snapshot per account + security
-- ============================================================

IF OBJECT_ID('portfolio.Holding', 'U') IS NULL
BEGIN
    CREATE TABLE portfolio.Holding (
        HoldingId       INT             NOT NULL IDENTITY(1,1),
        AccountId       INT             NOT NULL,
        SecurityId      BIGINT          NOT NULL,
        Shares          DECIMAL(12,4)   NOT NULL DEFAULT 0,
        AvgCostBasis    DECIMAL(10,4)   NOT NULL DEFAULT 0,
        CurrentPrice    DECIMAL(10,4)   NULL,
        MarketValue     DECIMAL(14,2)   NULL,
        UnrealizedPnL   DECIMAL(14,2)   NULL,
        UpdatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_Holding         PRIMARY KEY (HoldingId),
        CONSTRAINT UQ_Holding         UNIQUE (AccountId, SecurityId),
        CONSTRAINT FK_Holding_Account FOREIGN KEY (AccountId) REFERENCES portfolio.Account(AccountId)
    );
END
GO


-- ============================================================
-- Views
-- ============================================================

CREATE OR ALTER VIEW portfolio.vw_OpenPositions AS
SELECT
    p.PositionId,
    p.AccountId,
    a.Name                                              AS Account,
    t.Symbol,
    t.Name                                              AS SecurityName,
    p.PositionType,
    p.Direction,
    p.Quantity,
    p.OpenDate,
    p.AvgEntryPrice,
    ROUND(p.Quantity * p.AvgEntryPrice, 2)              AS EntryDollars,
    p.Regime,
    p.StrategyName,
    dm.MarkValue                                        AS CurrentPrice,
    ROUND(
        CASE p.Direction
            WHEN 'long'  THEN (dm.MarkValue - p.AvgEntryPrice) * p.Quantity
            WHEN 'short' THEN (p.AvgEntryPrice - dm.MarkValue) * p.Quantity
        END, 2)                                         AS UnrealizedPnL,
    p.Source,
    p.Tags,
    p.Notes,
    p.CreatedAt
FROM portfolio.Position p
JOIN  portfolio.Account a  ON a.AccountId = p.AccountId
LEFT JOIN mkt.Ticker    t  ON CAST(t.TickerId AS BIGINT) = p.SecurityId
OUTER APPLY (
    SELECT TOP 1 MarkValue
    FROM portfolio.DailyMark dm2
    WHERE dm2.PositionId = p.PositionId
    ORDER BY dm2.MarkDate DESC
) dm
WHERE p.Status = 'open';
GO


CREATE OR ALTER VIEW portfolio.vw_ClosedPositions AS
SELECT
    p.PositionId,
    p.AccountId,
    a.Name                                              AS Account,
    t.Symbol,
    t.Name                                              AS SecurityName,
    p.PositionType,
    p.Direction,
    p.Quantity,
    p.OpenDate,
    p.CloseDate,
    DATEDIFF(day, p.OpenDate, p.CloseDate)              AS HoldDays,
    p.Status,
    p.AvgEntryPrice,
    p.AvgExitPrice,
    ROUND(p.Quantity * p.AvgEntryPrice, 2)              AS EntryDollars,
    p.RealizedPnL,
    CASE WHEN p.RealizedPnL > 0 THEN 'Win'
         WHEN p.RealizedPnL < 0 THEN 'Loss'
         ELSE 'Breakeven' END                           AS Outcome,
    p.Commission,
    p.Regime,
    p.StrategyName,
    p.Source,
    p.Tags,
    p.Notes
FROM portfolio.Position p
JOIN  portfolio.Account a  ON a.AccountId = p.AccountId
LEFT JOIN mkt.Ticker    t  ON CAST(t.TickerId AS BIGINT) = p.SecurityId
WHERE p.Status IN ('closed','expired','assigned','rolled');
GO


CREATE OR ALTER VIEW portfolio.vw_StrategyPerformance AS
SELECT
    t.Symbol,
    p.StrategyName,
    p.PositionType,
    COUNT(*)                                                                AS Trades,
    SUM(CASE WHEN p.RealizedPnL > 0  THEN 1 ELSE 0 END)                   AS Wins,
    SUM(CASE WHEN p.RealizedPnL <= 0 THEN 1 ELSE 0 END)                   AS Losses,
    ROUND(
        100.0 * SUM(CASE WHEN p.RealizedPnL > 0 THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 1)                                     AS WinRate,
    ROUND(SUM(p.RealizedPnL), 2)                                            AS TotalPnL,
    ROUND(AVG(p.RealizedPnL), 2)                                            AS AvgPnL,
    ROUND(MAX(p.RealizedPnL), 2)                                            AS BestTrade,
    ROUND(MIN(p.RealizedPnL), 2)                                            AS WorstTrade,
    ROUND(AVG(CAST(DATEDIFF(day, p.OpenDate, p.CloseDate) AS FLOAT)), 1)   AS AvgHoldDays
FROM portfolio.Position p
LEFT JOIN mkt.Ticker t ON CAST(t.TickerId AS BIGINT) = p.SecurityId
WHERE p.Status IN ('closed','expired','assigned','rolled')
  AND p.RealizedPnL IS NOT NULL
GROUP BY t.Symbol, p.StrategyName, p.PositionType;
GO


CREATE OR ALTER VIEW portfolio.vw_MonthlyPnL AS
SELECT
    YEAR(p.CloseDate)                                   AS [Year],
    MONTH(p.CloseDate)                                  AS [Month],
    FORMAT(p.CloseDate, 'yyyy-MM')                      AS YearMonth,
    COUNT(*)                                            AS Trades,
    SUM(CASE WHEN p.RealizedPnL > 0 THEN 1 ELSE 0 END) AS Wins,
    ROUND(100.0 * SUM(CASE WHEN p.RealizedPnL > 0 THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 1)               AS WinRate,
    ROUND(SUM(p.RealizedPnL), 2)                        AS MonthlyPnL,
    ROUND(AVG(p.RealizedPnL), 2)                        AS AvgTradePnL,
    ROUND(SUM(SUM(p.RealizedPnL)) OVER (
        ORDER BY YEAR(p.CloseDate), MONTH(p.CloseDate)
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ), 2)                                               AS CumPnL
FROM portfolio.Position p
WHERE p.Status IN ('closed','expired','assigned','rolled')
  AND p.RealizedPnL IS NOT NULL
  AND p.CloseDate IS NOT NULL
GROUP BY YEAR(p.CloseDate), MONTH(p.CloseDate), FORMAT(p.CloseDate, 'yyyy-MM');
GO


CREATE OR ALTER VIEW portfolio.vw_ModelAccuracy AS
SELECT
    ms.Symbol,
    ms.SpreadType,
    COUNT(*)                                                                    AS TotalSignals,
    SUM(CAST(ms.WasTaken AS INT))                                               AS SignalsTaken,
    SUM(CASE WHEN ms.WasTaken = 1 AND p.RealizedPnL > 0 THEN 1 ELSE 0 END)    AS WinsWhenTaken,
    ROUND(
        100.0 * SUM(CASE WHEN ms.WasTaken = 1 AND p.RealizedPnL > 0 THEN 1 ELSE 0 END)
              / NULLIF(SUM(CAST(ms.WasTaken AS INT)), 0), 1
    )                                                                           AS WinRateWhenTaken,
    ROUND(AVG(ms.Confidence) * 100, 1)                                          AS AvgConfidencePct,
    ROUND(AVG(CASE WHEN ms.WasTaken = 1 THEN p.RealizedPnL END), 2)            AS AvgPnLWhenTaken,
    ROUND(SUM(CASE WHEN ms.WasTaken = 1 THEN p.RealizedPnL ELSE 0 END), 2)     AS TotalPnLWhenTaken
FROM portfolio.ModelSignal ms
LEFT JOIN portfolio.Position p ON p.PositionId = ms.PositionId
GROUP BY ms.Symbol, ms.SpreadType;
GO


PRINT 'AlanStrats schema created / verified successfully.';
