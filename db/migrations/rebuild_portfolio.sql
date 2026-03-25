CREATE TABLE portfolio.Account (
    AccountId    INT IDENTITY(1,1) PRIMARY KEY,
    AccountName  VARCHAR(100) NOT NULL,
    AccountType  VARCHAR(50)  NOT NULL,
    Currency     VARCHAR(10)  NOT NULL DEFAULT 'USD',
    OpenDate     DATE         NOT NULL DEFAULT CAST(GETDATE() AS DATE),
    Status       VARCHAR(20)  NOT NULL DEFAULT 'Active'
);

CREATE TABLE portfolio.Security (
    SecurityId    INT IDENTITY(1,1) PRIMARY KEY,
    Symbol        VARCHAR(50)   NOT NULL,
    Underlying    VARCHAR(20),
    SecurityType  VARCHAR(20)   NOT NULL,
    OptionType    VARCHAR(5),
    Strike        DECIMAL(12,4),
    Expiration    DATE,
    Multiplier    INT           NOT NULL DEFAULT 100,
    CreatedDate   DATE          NOT NULL DEFAULT CAST(GETDATE() AS DATE),
    CONSTRAINT UQ_Security UNIQUE (Symbol, SecurityType, Strike, Expiration, OptionType)
);

CREATE TABLE portfolio.[Transaction] (
    TransactionId     INT IDENTITY(1,1) PRIMARY KEY,
    BusinessDate      DATE          NOT NULL,
    AccountId         INT           NOT NULL REFERENCES portfolio.Account(AccountId),
    TradeGroupId      VARCHAR(50),
    StrategyName      VARCHAR(100),
    SecurityId        INT           NOT NULL REFERENCES portfolio.Security(SecurityId),
    Direction         VARCHAR(10)   NOT NULL,
    Quantity          DECIMAL(18,4) NOT NULL,
    TransactionPrice  DECIMAL(18,6) NOT NULL,
    Commission        DECIMAL(10,4) NOT NULL DEFAULT 0,
    LegType           VARCHAR(50),
    Source            VARCHAR(50),
    Notes             VARCHAR(500),
    CreatedAt         DATETIME      NOT NULL DEFAULT GETDATE()
);

CREATE TABLE portfolio.Position (
    PositionId    INT IDENTITY(1,1) PRIMARY KEY,
    BusinessDate  DATE          NOT NULL,
    AccountId     INT           NOT NULL REFERENCES portfolio.Account(AccountId),
    SecurityId    INT           NOT NULL REFERENCES portfolio.Security(SecurityId),
    StrategyName  VARCHAR(100),
    TradeGroupId  VARCHAR(50),
    Quantity      DECIMAL(18,4) NOT NULL,
    AvgCostPrice  DECIMAL(18,6),
    ClosePrice    DECIMAL(18,6),
    UnrealizedPnL DECIMAL(18,4),
    RealizedPnL   DECIMAL(18,4) NOT NULL DEFAULT 0,
    Status        VARCHAR(20)   NOT NULL DEFAULT 'Open',
    CONSTRAINT UQ_Position UNIQUE (BusinessDate, AccountId, SecurityId, TradeGroupId)
);

CREATE TABLE portfolio.Leg (
    LegId         INT IDENTITY(1,1) PRIMARY KEY,
    BusinessDate  DATE          NOT NULL,
    PositionId    INT           NOT NULL REFERENCES portfolio.Position(PositionId),
    SecurityId    INT           NOT NULL REFERENCES portfolio.Security(SecurityId),
    LegType       VARCHAR(50),
    Quantity      DECIMAL(18,4) NOT NULL,
    EntryPrice    DECIMAL(18,6),
    ClosePrice    DECIMAL(18,6),
    UnrealizedPnL DECIMAL(18,4)
);

CREATE TABLE portfolio.Balance (
    BalanceId    INT IDENTITY(1,1) PRIMARY KEY,
    BusinessDate DATE          NOT NULL,
    AccountId    INT           NOT NULL REFERENCES portfolio.Account(AccountId),
    BalanceType  VARCHAR(50)   NOT NULL,
    Amount       DECIMAL(18,4) NOT NULL,
    Notes        VARCHAR(200)
);

INSERT INTO portfolio.Account (AccountName, AccountType) VALUES ('Default Trading', 'Paper');
