-- ============================================================
-- alan-strats  |  Portfolio Management Schema
-- SQL Server Express  |  Run after schema.sql
-- ============================================================

USE AlanStrats;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'portfolio')
    EXEC('CREATE SCHEMA portfolio');
GO


-- ============================================================
-- portfolio.Account
-- One row per brokerage account (or paper account).
-- ============================================================

CREATE TABLE portfolio.Account (
    AccountId       INT             NOT NULL IDENTITY(1,1),
    Name            VARCHAR(100)    NOT NULL,           -- "TD Ameritrade - Main"
    BrokerName      VARCHAR(50)     NOT NULL,           -- TD | IBKR | Robinhood | Paper
    AccountNumber   VARCHAR(50)     NULL,
    AccountType     VARCHAR(10)     NOT NULL DEFAULT 'margin',  -- margin|cash|ira|paper
    Currency        CHAR(3)         NOT NULL DEFAULT 'USD',
    IsActive        BIT             NOT NULL DEFAULT 1,
    Notes           NVARCHAR(500)   NULL,
    CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_Account           PRIMARY KEY (AccountId),
    CONSTRAINT CK_Account_Type      CHECK (AccountType IN ('margin','cash','ira','paper'))
);
GO

-- Seed a default paper account
INSERT INTO portfolio.Account (Name, BrokerName, AccountType, Notes)
VALUES ('Paper Account', 'Paper', 'paper', 'Default paper trading account for model validation');
GO


-- ============================================================
-- portfolio.Balance
-- Daily account snapshot — cash, equity, buying power.
-- One row per account per day.
-- ============================================================

CREATE TABLE portfolio.Balance (
    BalanceId       INT             NOT NULL IDENTITY(1,1),
    AccountId       INT             NOT NULL,
    BalanceDate     DATE            NOT NULL,
    CashBalance     DECIMAL(14,2)   NOT NULL DEFAULT 0,
    PortfolioValue  DECIMAL(14,2)   NOT NULL DEFAULT 0,  -- mark-to-market of open positions
    TotalEquity     DECIMAL(14,2)   NOT NULL DEFAULT 0,  -- cash + portfolio value
    DayPnL          DECIMAL(14,2)   NULL,
    OpenPnL         DECIMAL(14,2)   NULL,                -- unrealized P&L
    RealizedPnLYTD  DECIMAL(14,2)   NULL,               -- year-to-date realized
    BuyingPower     DECIMAL(14,2)   NULL,
    MarginUsed      DECIMAL(14,2)   NULL,
    CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_Balance           PRIMARY KEY (BalanceId),
    CONSTRAINT UQ_Balance_Date      UNIQUE      (AccountId, BalanceDate),
    CONSTRAINT FK_Balance_Account   FOREIGN KEY (AccountId) REFERENCES portfolio.Account(AccountId)
);
GO

CREATE INDEX IX_Balance_Date ON portfolio.Balance (AccountId, BalanceDate DESC);
GO


-- ============================================================
-- portfolio.Position
-- One logical position = one spread or single-leg trade.
-- Legs are stored separately in portfolio.Leg.
-- ============================================================

CREATE TABLE portfolio.Position (
    PositionId      INT             NOT NULL IDENTITY(1,1),
    AccountId       INT             NOT NULL,
    Symbol          VARCHAR(10)     NOT NULL,           -- underlying ticker (e.g. HOOD)
    SpreadType      VARCHAR(30)     NOT NULL,           -- iron_condor|bull_put|bear_call|...
    Contracts       SMALLINT        NOT NULL DEFAULT 1, -- number of spreads (1 = 100 shares notional)
    OpenDate        DATE            NOT NULL,
    CloseDate       DATE            NULL,               -- NULL = still open
    Expiration      DATE            NULL,               -- options expiration date
    DTEAtEntry      SMALLINT        NULL,               -- days to expiration when opened

    -- Status
    Status          VARCHAR(20)     NOT NULL DEFAULT 'open',
    -- open | closed | expired | assigned | rolled

    -- Pricing (per-share; multiply by Contracts*100 for dollar value)
    EntryValue      DECIMAL(10,4)   NOT NULL,           -- credit (+) or debit (-) per share
    ExitValue       DECIMAL(10,4)   NULL,               -- value when closed/expired
    MaxProfit       DECIMAL(10,4)   NULL,               -- theoretical max per share
    MaxLoss         DECIMAL(10,4)   NULL,               -- theoretical max loss per share

    -- P&L (dollars, inclusive of commissions)
    RealizedPnL     DECIMAL(12,2)   NULL,               -- filled at close
    PnLPct          DECIMAL(8,4)    NULL,               -- realized / max_profit
    Commission      DECIMAL(10,2)   NOT NULL DEFAULT 0, -- total commissions for all legs

    -- Market context at entry (for analysis)
    SpotAtEntry     DECIMAL(10,4)   NULL,
    VixAtEntry      DECIMAL(8,4)    NULL,
    DeltaAtEntry    DECIMAL(8,4)    NULL,
    ThetaAtEntry    DECIMAL(8,4)    NULL,
    VegaAtEntry     DECIMAL(8,4)    NULL,
    IVRAtEntry      DECIMAL(6,2)    NULL,               -- IV Rank 0-100

    -- Metadata
    Source          VARCHAR(20)     NOT NULL DEFAULT 'manual',
    -- manual | model | import
    ModelSignalId   INT             NULL,               -- FK to ModelSignal if AI-driven
    Tags            VARCHAR(200)    NULL,               -- comma-separated tags
    Notes           NVARCHAR(MAX)   NULL,
    CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),
    UpdatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_Position          PRIMARY KEY (PositionId),
    CONSTRAINT FK_Position_Account  FOREIGN KEY (AccountId) REFERENCES portfolio.Account(AccountId),
    CONSTRAINT CK_Position_Status   CHECK (Status IN ('open','closed','expired','assigned','rolled'))
);
GO

CREATE INDEX IX_Position_Symbol  ON portfolio.Position (Symbol, OpenDate DESC);
CREATE INDEX IX_Position_Status  ON portfolio.Position (Status, AccountId);
GO


-- ============================================================
-- portfolio.Leg
-- Individual contracts that make up a position.
-- (Iron condor = 4 legs, vertical = 2 legs, naked = 1 leg)
-- ============================================================

CREATE TABLE portfolio.Leg (
    LegId           INT             NOT NULL IDENTITY(1,1),
    PositionId      INT             NOT NULL,
    Symbol          VARCHAR(10)     NOT NULL,           -- underlying
    OptionSymbol    VARCHAR(30)     NULL,               -- OCC symbol e.g. HOOD240119C15000
    InstrumentType  VARCHAR(10)     NOT NULL DEFAULT 'option', -- option | stock
    Action          VARCHAR(4)      NOT NULL,           -- BTO | STO | BTC | STC
    Contracts       SMALLINT        NOT NULL DEFAULT 1,
    Strike          DECIMAL(10,2)   NULL,
    Expiration      DATE            NULL,
    ContractType    CHAR(1)         NULL,               -- C | P
    FillPrice       DECIMAL(10,4)   NOT NULL,
    Commission      DECIMAL(8,2)    NOT NULL DEFAULT 0,
    FillDate        DATE            NOT NULL,
    LegOrder        TINYINT         NOT NULL DEFAULT 1, -- display ordering within spread
    CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_Leg               PRIMARY KEY (LegId),
    CONSTRAINT FK_Leg_Position      FOREIGN KEY (PositionId) REFERENCES portfolio.Position(PositionId),
    CONSTRAINT CK_Leg_Action        CHECK (Action IN ('BTO','STO','BTC','STC')),
    CONSTRAINT CK_Leg_ContractType  CHECK (ContractType IN ('C','P') OR ContractType IS NULL)
);
GO

CREATE INDEX IX_Leg_Position ON portfolio.Leg (PositionId);
GO


-- ============================================================
-- portfolio.ModelSignal
-- Every model ENTER signal — whether acted on or not.
-- Enables measuring model accuracy against real outcomes.
-- ============================================================

CREATE TABLE portfolio.ModelSignal (
    SignalId        INT             NOT NULL IDENTITY(1,1),
    SignalDate      DATE            NOT NULL,
    Symbol          VARCHAR(10)     NOT NULL,
    SpreadType      VARCHAR(30)     NOT NULL,
    PredictedLabel  TINYINT         NOT NULL,           -- 0=AVOID 1=SKIP 2=ENTER
    Confidence      DECIMAL(5,4)    NOT NULL,           -- 0.0 – 1.0
    ModelVersion    VARCHAR(50)     NULL,               -- model checkpoint tag
    WasTaken        BIT             NOT NULL DEFAULT 0, -- did the user actually trade it?
    PositionId      INT             NULL,               -- FK if acted upon
    Notes           NVARCHAR(500)   NULL,
    CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_ModelSignal           PRIMARY KEY (SignalId),
    CONSTRAINT FK_ModelSignal_Position  FOREIGN KEY (PositionId)
        REFERENCES portfolio.Position(PositionId),
    CONSTRAINT CK_ModelSignal_Label     CHECK (PredictedLabel IN (0,1,2))
);
GO

CREATE INDEX IX_ModelSignal_Date   ON portfolio.ModelSignal (Symbol, SignalDate DESC);
GO


-- ============================================================
-- portfolio.DailyMark
-- Mark-to-market each open position daily.
-- Populated manually or by a scheduled job.
-- ============================================================

CREATE TABLE portfolio.DailyMark (
    MarkId          INT             NOT NULL IDENTITY(1,1),
    PositionId      INT             NOT NULL,
    MarkDate        DATE            NOT NULL,
    MarkValue       DECIMAL(10,4)   NOT NULL,           -- current spread value per share
    DayPnL          DECIMAL(12,2)   NULL,               -- dollar change vs prior day
    CumPnL          DECIMAL(12,2)   NULL,               -- dollar P&L since open
    DTE             SMALLINT        NULL,               -- days remaining to expiration
    Delta           DECIMAL(8,4)    NULL,
    Theta           DECIMAL(8,4)    NULL,
    Vega            DECIMAL(8,4)    NULL,
    CreatedAt       DATETIME2(0)    NOT NULL DEFAULT SYSUTCDATETIME(),

    CONSTRAINT PK_DailyMark            PRIMARY KEY (MarkId),
    CONSTRAINT UQ_DailyMark_Date       UNIQUE      (PositionId, MarkDate),
    CONSTRAINT FK_DailyMark_Position   FOREIGN KEY (PositionId)
        REFERENCES portfolio.Position(PositionId)
);
GO

CREATE INDEX IX_DailyMark_Position ON portfolio.DailyMark (PositionId, MarkDate DESC);
GO


-- ============================================================
-- VIEWS
-- ============================================================

-- vw_OpenPositions — live positions with latest mark-to-market
-- ============================================================

CREATE VIEW portfolio.vw_OpenPositions AS
SELECT
    p.PositionId,
    p.AccountId,
    a.Name                                          AS Account,
    p.Symbol,
    p.SpreadType,
    p.Contracts,
    p.OpenDate,
    p.Expiration,
    DATEDIFF(day, CAST(GETDATE() AS DATE), p.Expiration) AS DTE,
    p.EntryValue,
    ROUND(p.EntryValue * p.Contracts * 100, 2)      AS EntryDollars,
    p.MaxProfit,
    p.MaxLoss,
    dm.MarkValue                                    AS CurrentValue,
    ROUND((p.EntryValue - dm.MarkValue) * p.Contracts * 100, 2)
                                                    AS UnrealizedPnL,
    CASE WHEN p.MaxProfit > 0
         THEN ROUND((p.EntryValue - dm.MarkValue) / p.MaxProfit * 100, 1)
         ELSE NULL END                              AS PctOfMaxProfit,
    p.VixAtEntry,
    p.IVRAtEntry,
    p.SpotAtEntry,
    p.Source,
    ms.Confidence                                   AS ModelConfidence,
    p.Tags,
    p.Notes,
    p.CreatedAt
FROM portfolio.Position p
JOIN  portfolio.Account      a  ON a.AccountId  = p.AccountId
LEFT JOIN portfolio.ModelSignal  ms ON ms.SignalId  = p.ModelSignalId
OUTER APPLY (
    SELECT TOP 1 MarkValue
    FROM portfolio.DailyMark dm2
    WHERE dm2.PositionId = p.PositionId
    ORDER BY dm2.MarkDate DESC
) dm
WHERE p.Status = 'open';
GO


-- vw_ClosedPositions — completed trades with realised P&L
-- ============================================================

CREATE VIEW portfolio.vw_ClosedPositions AS
SELECT
    p.PositionId,
    p.AccountId,
    a.Name                                          AS Account,
    p.Symbol,
    p.SpreadType,
    p.Contracts,
    p.OpenDate,
    p.CloseDate,
    DATEDIFF(day, p.OpenDate, p.CloseDate)          AS HoldDays,
    p.Expiration,
    p.DTEAtEntry,
    p.Status,
    p.EntryValue,
    p.ExitValue,
    ROUND(p.EntryValue  * p.Contracts * 100, 2)     AS EntryDollars,
    p.MaxProfit,
    p.MaxLoss,
    ROUND(p.MaxProfit   * p.Contracts * 100, 2)     AS MaxProfitDollars,
    p.RealizedPnL,
    p.PnLPct,
    CASE WHEN p.RealizedPnL > 0 THEN 'Win'
         WHEN p.RealizedPnL < 0 THEN 'Loss'
         ELSE 'Breakeven' END                       AS Outcome,
    p.Commission,
    p.VixAtEntry,
    p.IVRAtEntry,
    p.SpotAtEntry,
    p.Source,
    ms.Confidence                                   AS ModelConfidence,
    p.Tags,
    p.Notes
FROM portfolio.Position     p
JOIN  portfolio.Account      a  ON a.AccountId  = p.AccountId
LEFT JOIN portfolio.ModelSignal  ms ON ms.SignalId  = p.ModelSignalId
WHERE p.Status IN ('closed','expired','assigned');
GO


-- vw_StrategyPerformance — win rate & P&L grouped by spread type
-- ============================================================

CREATE VIEW portfolio.vw_StrategyPerformance AS
SELECT
    p.Symbol,
    p.SpreadType,
    COUNT(*)                                                            AS Trades,
    SUM(CASE WHEN p.RealizedPnL > 0  THEN 1 ELSE 0 END)               AS Wins,
    SUM(CASE WHEN p.RealizedPnL <= 0 THEN 1 ELSE 0 END)               AS Losses,
    ROUND(
        100.0 * SUM(CASE WHEN p.RealizedPnL > 0 THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 1)                                 AS WinRate,
    ROUND(SUM(p.RealizedPnL), 2)                                        AS TotalPnL,
    ROUND(AVG(p.RealizedPnL), 2)                                        AS AvgPnL,
    ROUND(MAX(p.RealizedPnL), 2)                                        AS BestTrade,
    ROUND(MIN(p.RealizedPnL), 2)                                        AS WorstTrade,
    ROUND(AVG(CAST(DATEDIFF(day, p.OpenDate, p.CloseDate) AS FLOAT)), 1) AS AvgHoldDays,
    ROUND(AVG(p.PnLPct) * 100, 1)                                       AS AvgPctOfMax
FROM portfolio.Position p
WHERE p.Status IN ('closed','expired','assigned')
  AND p.RealizedPnL IS NOT NULL
GROUP BY p.Symbol, p.SpreadType;
GO


-- vw_MonthlyPnL — P&L aggregated by calendar month
-- ============================================================

CREATE VIEW portfolio.vw_MonthlyPnL AS
SELECT
    YEAR(p.CloseDate)                               AS [Year],
    MONTH(p.CloseDate)                              AS [Month],
    FORMAT(p.CloseDate, 'yyyy-MM')                  AS YearMonth,
    COUNT(*)                                        AS Trades,
    SUM(CASE WHEN p.RealizedPnL > 0 THEN 1 ELSE 0 END) AS Wins,
    ROUND(100.0 * SUM(CASE WHEN p.RealizedPnL > 0 THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 1)           AS WinRate,
    ROUND(SUM(p.RealizedPnL), 2)                    AS MonthlyPnL,
    ROUND(AVG(p.RealizedPnL), 2)                    AS AvgTradePnL,
    ROUND(SUM(SUM(p.RealizedPnL)) OVER (
        ORDER BY YEAR(p.CloseDate), MONTH(p.CloseDate)
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ), 2) AS CumPnL
FROM portfolio.Position p
WHERE p.Status IN ('closed','expired','assigned')
  AND p.RealizedPnL IS NOT NULL
  AND p.CloseDate IS NOT NULL
GROUP BY YEAR(p.CloseDate), MONTH(p.CloseDate), FORMAT(p.CloseDate, 'yyyy-MM');
GO


-- vw_ModelAccuracy — how well did model signals perform when acted upon
-- ============================================================

CREATE VIEW portfolio.vw_ModelAccuracy AS
SELECT
    ms.Symbol,
    ms.SpreadType,
    COUNT(*)                                                AS TotalSignals,
    SUM(CAST(ms.WasTaken AS INT))                           AS SignalsTaken,
    SUM(CASE WHEN ms.WasTaken = 1 AND p.RealizedPnL > 0 THEN 1 ELSE 0 END)
                                                            AS WinsWhenTaken,
    ROUND(
        100.0 * SUM(CASE WHEN ms.WasTaken = 1 AND p.RealizedPnL > 0 THEN 1 ELSE 0 END)
              / NULLIF(SUM(CAST(ms.WasTaken AS INT)), 0), 1
    )                                                       AS WinRateWhenTaken,
    ROUND(AVG(ms.Confidence) * 100, 1)                      AS AvgConfidencePct,
    ROUND(AVG(CASE WHEN ms.WasTaken = 1 THEN p.RealizedPnL END), 2)
                                                            AS AvgPnLWhenTaken,
    ROUND(SUM(CASE WHEN ms.WasTaken = 1 THEN p.RealizedPnL ELSE 0 END), 2)
                                                            AS TotalPnLWhenTaken
FROM portfolio.ModelSignal ms
LEFT JOIN portfolio.Position p ON p.PositionId = ms.PositionId
GROUP BY ms.Symbol, ms.SpreadType;
GO
