-- ============================================================
-- alan-strats  |  Market Data Schema  (current, all migrations applied)
-- SQL Server Express  |  Windows Auth
-- Run once on a fresh database.
-- ============================================================

USE master;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'AlanStrats')
    CREATE DATABASE AlanStrats;
GO

USE AlanStrats;
GO

-- ============================================================
-- SCHEMA
-- ============================================================

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'mkt')
    EXEC('CREATE SCHEMA mkt');
GO


-- ============================================================
-- mkt.Ticker
-- ============================================================

CREATE TABLE mkt.Ticker (
    TickerId        SMALLINT        NOT NULL IDENTITY(1,1),
    Symbol          VARCHAR(10)     NOT NULL,
    Name            VARCHAR(100)    NULL,
    AssetClass      VARCHAR(20)     NOT NULL DEFAULT 'equity',   -- equity | etf | index
    IsActive        BIT             NOT NULL DEFAULT 1,
    CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_Ticker            PRIMARY KEY (TickerId),
    CONSTRAINT UQ_Ticker_Symbol     UNIQUE      (Symbol)
);
GO


-- ============================================================
-- mkt.PriceBar
-- ============================================================

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

    CONSTRAINT PK_PriceBar          PRIMARY KEY (TickerId, BarDate),
    CONSTRAINT FK_PriceBar_Ticker   FOREIGN KEY (TickerId) REFERENCES mkt.Ticker(TickerId)
);
GO

CREATE INDEX IX_PriceBar_BarDate ON mkt.PriceBar (BarDate DESC);
GO


-- ============================================================
-- mkt.OptionSnapshot
-- EOD options chain — one row per contract per day.
-- ============================================================

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

    CONSTRAINT PK_OptionSnapshot PRIMARY KEY (
        TickerId, SnapshotDate, ExpirationDate, Strike, ContractType
    ),
    CONSTRAINT FK_OptionSnapshot_Ticker FOREIGN KEY (TickerId) REFERENCES mkt.Ticker(TickerId),
    CONSTRAINT CK_OptionSnapshot_Type   CHECK (ContractType IN ('C', 'P'))
);
GO

CREATE INDEX IX_OptionSnapshot_Ticker_Date
    ON mkt.OptionSnapshot (TickerId, SnapshotDate DESC);

CREATE INDEX IX_OptionSnapshot_Ticker_Expiry
    ON mkt.OptionSnapshot (TickerId, ExpirationDate, SnapshotDate DESC);

CREATE INDEX IX_OptionSnapshot_Contract
    ON mkt.OptionSnapshot (TickerId, SnapshotDate, ContractType, Strike);
GO


-- ============================================================
-- mkt.MacroBar
-- Full yield curve (3M-30Y), SOFR, jobless claims — from FRED.
-- ============================================================

CREATE TABLE mkt.MacroBar (
    BarDate         DATE            NOT NULL,
    Rate2Y          DECIMAL(6,4)    NULL,   -- 2-year Treasury yield
    Rate10Y         DECIMAL(6,4)    NULL,   -- 10-year Treasury yield
    YieldSpread     DECIMAL(6,4)    NULL,   -- 10Y - 2Y
    Rate3M          DECIMAL(6,4)    NULL,   -- 3-month Treasury yield
    Rate6M          DECIMAL(6,4)    NULL,   -- 6-month Treasury yield
    Rate1Y          DECIMAL(6,4)    NULL,   -- 1-year  Treasury yield
    Rate5Y          DECIMAL(6,4)    NULL,   -- 5-year  Treasury yield
    Rate30Y         DECIMAL(6,4)    NULL,   -- 30-year Treasury yield
    Curve3m10y      DECIMAL(6,4)    NULL,   -- 10Y - 3M spread
    Curve5y30y      DECIMAL(6,4)    NULL,   -- 30Y - 5Y spread
    CurveButterfly  DECIMAL(6,4)    NULL,   -- 2Y - (0.5*3M + 0.5*10Y)
    Sofr            DECIMAL(6,4)    NULL,   -- Secured Overnight Financing Rate
    JoblessClaims   INT             NULL,   -- weekly initial jobless claims
    CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_MacroBar PRIMARY KEY (BarDate)
);
GO


-- ============================================================
-- mkt.VixBar
-- Daily VIX OHLCV from CBOE.
-- ============================================================

CREATE TABLE mkt.VixBar (
    BarDate         DATE            NOT NULL,
    [Open]          DECIMAL(8,4)    NOT NULL,
    High            DECIMAL(8,4)    NOT NULL,
    Low             DECIMAL(8,4)    NOT NULL,
    [Close]         DECIMAL(8,4)    NOT NULL,
    CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_VixBar PRIMARY KEY (BarDate)
);
GO


-- ============================================================
-- mkt.News
-- News articles from Polygon, tagged to a ticker.
-- Sentiment pre-computed via VADER at insert time.
-- ============================================================

CREATE TABLE mkt.News (
    NewsId          INT             NOT NULL IDENTITY(1,1),
    TickerId        SMALLINT        NOT NULL,
    ArticleId       VARCHAR(50)     NOT NULL,
    PublishedAt     DATETIME2(0)    NOT NULL,
    PublishedDate   DATE            NOT NULL,
    Title           NVARCHAR(MAX)   NOT NULL,
    Description     NVARCHAR(MAX)   NULL,
    Sentiment       DECIMAL(5,4)    NULL,   -- VADER compound: -1.0 to +1.0
    CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_News          PRIMARY KEY (NewsId),
    CONSTRAINT UQ_News_Article  UNIQUE      (TickerId, ArticleId),
    CONSTRAINT FK_News_Ticker   FOREIGN KEY (TickerId) REFERENCES mkt.Ticker(TickerId)
);
GO

CREATE INDEX IX_News_PublishedDate ON mkt.News (TickerId, PublishedDate DESC);
GO


-- ============================================================
-- mkt.SyncLog
-- Tracks the last successful sync per ticker + data type.
-- ============================================================

CREATE TABLE mkt.SyncLog (
    SyncLogId       INT             NOT NULL IDENTITY(1,1),
    TickerId        SMALLINT        NULL,           -- NULL = all tickers (VIX, Macro)
    DataType        VARCHAR(30)     NOT NULL,       -- PriceBar | OptionSnapshot | VixBar | MacroBar | News
    LastSyncDate    DATE            NOT NULL,
    RowsInserted    INT             NOT NULL DEFAULT 0,
    SyncedAt        DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),
    ErrorMessage    NVARCHAR(MAX)   NULL,

    CONSTRAINT PK_SyncLog        PRIMARY KEY (SyncLogId),
    CONSTRAINT FK_SyncLog_Ticker FOREIGN KEY (TickerId) REFERENCES mkt.Ticker(TickerId)
);
GO

CREATE INDEX IX_SyncLog_Lookup
    ON mkt.SyncLog (TickerId, DataType, SyncedAt DESC);
GO


-- ============================================================
-- Seed: default tickers
-- ============================================================

INSERT INTO mkt.Ticker (Symbol, Name, AssetClass) VALUES
    ('HOOD', 'Robinhood Markets',  'equity'),
    ('SPY',  'SPDR S&P 500 ETF',  'etf'),
    ('QQQ',  'Invesco QQQ Trust', 'etf'),
    ('AAPL', 'Apple Inc.',        'equity'),
    ('TSLA', 'Tesla Inc.',        'equity'),
    ('MARA', 'Marathon Digital',  'equity');
GO
