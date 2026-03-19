"""
portfolio_client.py — CRUD helpers for the portfolio.* schema.
All functions accept a SQLAlchemy engine and return plain DataFrames or dicts.
"""
from __future__ import annotations

import datetime
import pandas as pd
from sqlalchemy import text


# ── helpers ───────────────────────────────────────────────────────────────────

def _df(conn, sql: str, params: dict | None = None) -> pd.DataFrame:
    res = conn.execute(text(sql), params or {})
    rows = res.fetchall()
    cols = list(res.keys())
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


def _scalar(conn, sql: str, params: dict | None = None):
    res = conn.execute(text(sql), params or {})
    row = res.fetchone()
    return row[0] if row else None


# ── accounts ──────────────────────────────────────────────────────────────────

def get_accounts(engine) -> pd.DataFrame:
    with engine.connect() as c:
        return _df(c, "SELECT AccountId, Name, BrokerName, AccountType, IsActive "
                      "FROM portfolio.Account WHERE IsActive = 1 ORDER BY AccountId")


def ensure_default_account(engine) -> int:
    """Return AccountId=1 (paper account); create it if it doesn't exist."""
    with engine.connect() as c:
        aid = _scalar(c, "SELECT TOP 1 AccountId FROM portfolio.Account WHERE IsActive=1 ORDER BY AccountId")
        if aid is not None:
            return int(aid)
    # Re-seed if table is empty
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO portfolio.Account (Name, BrokerName, AccountType, Notes)
            VALUES ('Paper Account','Paper','paper','Default paper account')
        """))
        return int(_scalar(c, "SELECT SCOPE_IDENTITY()") or 1)


# ── balances ──────────────────────────────────────────────────────────────────

def get_latest_balance(engine, account_id: int) -> dict:
    with engine.connect() as c:
        row = _df(c,
            "SELECT TOP 1 * FROM portfolio.Balance "
            "WHERE AccountId = :aid ORDER BY BalanceDate DESC",
            {"aid": account_id}
        )
    return row.iloc[0].to_dict() if not row.empty else {}


def upsert_balance(engine, account_id: int, bal_date: datetime.date,
                   cash: float, portfolio_val: float, **kwargs) -> None:
    total = cash + portfolio_val
    with engine.begin() as c:
        exists = _scalar(c,
            "SELECT 1 FROM portfolio.Balance WHERE AccountId=:aid AND BalanceDate=:d",
            {"aid": account_id, "d": bal_date}
        )
        if exists:
            c.execute(text("""
                UPDATE portfolio.Balance
                SET CashBalance=:cash, PortfolioValue=:pv, TotalEquity=:te,
                    DayPnL=:day, OpenPnL=:open, RealizedPnLYTD=:ytd,
                    BuyingPower=:bp, MarginUsed=:mu
                WHERE AccountId=:aid AND BalanceDate=:d
            """), {"cash": cash, "pv": portfolio_val, "te": total,
                   "day": kwargs.get("day_pnl"), "open": kwargs.get("open_pnl"),
                   "ytd": kwargs.get("realized_ytd"), "bp": kwargs.get("buying_power"),
                   "mu": kwargs.get("margin_used"), "aid": account_id, "d": bal_date})
        else:
            c.execute(text("""
                INSERT INTO portfolio.Balance
                    (AccountId, BalanceDate, CashBalance, PortfolioValue, TotalEquity,
                     DayPnL, OpenPnL, RealizedPnLYTD, BuyingPower, MarginUsed)
                VALUES (:aid,:d,:cash,:pv,:te,:day,:open,:ytd,:bp,:mu)
            """), {"aid": account_id, "d": bal_date, "cash": cash, "pv": portfolio_val,
                   "te": total, "day": kwargs.get("day_pnl"), "open": kwargs.get("open_pnl"),
                   "ytd": kwargs.get("realized_ytd"), "bp": kwargs.get("buying_power"),
                   "mu": kwargs.get("margin_used")})


def get_balance_history(engine, account_id: int, days: int = 90) -> pd.DataFrame:
    with engine.connect() as c:
        return _df(c,
            "SELECT BalanceDate, TotalEquity, DayPnL, OpenPnL, RealizedPnLYTD "
            "FROM portfolio.Balance "
            "WHERE AccountId=:aid AND BalanceDate >= DATEADD(day,-:d,GETDATE()) "
            "ORDER BY BalanceDate",
            {"aid": account_id, "d": days}
        )


# ── positions ─────────────────────────────────────────────────────────────────

def get_open_positions(engine, account_id: int | None = None) -> pd.DataFrame:
    # Filter via the base table (views don't expose AccountId in their SELECT)
    pid_filter = ""
    params: dict = {}
    if account_id is not None:
        pid_filter = "WHERE PositionId IN (SELECT PositionId FROM portfolio.Position WHERE AccountId = :aid)"
        params["aid"] = account_id
    with engine.connect() as c:
        return _df(c,
            f"SELECT * FROM portfolio.vw_OpenPositions {pid_filter} ORDER BY OpenDate DESC",
            params
        )


def get_closed_positions(engine, account_id: int | None = None,
                         symbol: str | None = None,
                         spread_type: str | None = None,
                         from_date: datetime.date | None = None,
                         to_date: datetime.date | None = None) -> pd.DataFrame:
    where_parts = ["1=1"]
    params: dict = {}
    if account_id:
        where_parts.append(
            "PositionId IN (SELECT PositionId FROM portfolio.Position WHERE AccountId = :aid)"
        )
        params["aid"] = account_id
    if symbol:
        where_parts.append("Symbol = :sym"); params["sym"] = symbol
    if spread_type:
        where_parts.append("SpreadType = :st"); params["st"] = spread_type
    if from_date:
        where_parts.append("CloseDate >= :fd"); params["fd"] = from_date
    if to_date:
        where_parts.append("CloseDate <= :td"); params["td"] = to_date
    where = " AND ".join(where_parts)
    with engine.connect() as c:
        return _df(c,
            f"SELECT * FROM portfolio.vw_ClosedPositions WHERE {where} ORDER BY CloseDate DESC",
            params
        )


def insert_position(engine, account_id: int, symbol: str, spread_type: str,
                    contracts: int, open_date: datetime.date, expiration: datetime.date,
                    dte_at_entry: int, entry_value: float, max_profit: float,
                    max_loss: float, commission: float = 0.0,
                    spot: float | None = None, vix: float | None = None,
                    ivr: float | None = None, source: str = "manual",
                    model_signal_id: int | None = None,
                    tags: str | None = None, notes: str | None = None) -> int:
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO portfolio.Position
                (AccountId, Symbol, SpreadType, Contracts, OpenDate, Expiration,
                 DTEAtEntry, EntryValue, MaxProfit, MaxLoss, Commission,
                 SpotAtEntry, VixAtEntry, IVRAtEntry, Source, ModelSignalId, Tags, Notes)
            VALUES
                (:aid, :sym, :st, :ct, :od, :exp, :dte, :ev, :mp, :ml, :comm,
                 :spot, :vix, :ivr, :src, :msid, :tags, :notes)
        """), {
            "aid": account_id, "sym": symbol, "st": spread_type, "ct": contracts,
            "od": open_date, "exp": expiration, "dte": dte_at_entry,
            "ev": entry_value, "mp": max_profit, "ml": max_loss, "comm": commission,
            "spot": spot, "vix": vix, "ivr": ivr, "src": source,
            "msid": model_signal_id, "tags": tags, "notes": notes,
        })
        return int(_scalar(c, "SELECT SCOPE_IDENTITY()") or 0)


def close_position(engine, position_id: int, close_date: datetime.date,
                   exit_value: float, realized_pnl: float,
                   status: str = "closed") -> None:
    with engine.begin() as c:
        pos = _df(c,
            "SELECT MaxProfit, Contracts FROM portfolio.Position WHERE PositionId=:pid",
            {"pid": position_id}
        )
        max_p = float(pos.iloc[0]["MaxProfit"]) if not pos.empty and pos.iloc[0]["MaxProfit"] else 0
        pnl_pct = realized_pnl / (max_p * float(pos.iloc[0]["Contracts"]) * 100) if max_p else None
        c.execute(text("""
            UPDATE portfolio.Position
            SET CloseDate=:cd, ExitValue=:ev, RealizedPnL=:pnl, PnLPct=:pct,
                Status=:status, UpdatedAt=SYSUTCDATETIME()
            WHERE PositionId=:pid
        """), {"cd": close_date, "ev": exit_value, "pnl": realized_pnl,
               "pct": pnl_pct, "status": status, "pid": position_id})


def insert_leg(engine, position_id: int, symbol: str, action: str,
               contracts: int, fill_price: float, fill_date: datetime.date,
               strike: float | None = None, expiration: datetime.date | None = None,
               contract_type: str | None = None, commission: float = 0.0,
               leg_order: int = 1, option_symbol: str | None = None) -> None:
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO portfolio.Leg
                (PositionId, Symbol, OptionSymbol, Action, Contracts,
                 Strike, Expiration, ContractType, FillPrice, Commission, FillDate, LegOrder)
            VALUES
                (:pid, :sym, :osym, :act, :ct, :sk, :exp, :ctype, :fp, :comm, :fd, :lo)
        """), {
            "pid": position_id, "sym": symbol, "osym": option_symbol,
            "act": action, "ct": contracts, "sk": strike, "exp": expiration,
            "ctype": contract_type, "fp": fill_price, "comm": commission,
            "fd": fill_date, "lo": leg_order,
        })


def get_legs(engine, position_id: int) -> pd.DataFrame:
    with engine.connect() as c:
        return _df(c,
            "SELECT * FROM portfolio.Leg WHERE PositionId=:pid ORDER BY LegOrder",
            {"pid": position_id}
        )


# ── model signals ─────────────────────────────────────────────────────────────

def insert_signal(engine, signal_date: datetime.date, symbol: str,
                  spread_type: str, label: int, confidence: float,
                  model_version: str | None = None) -> int:
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO portfolio.ModelSignal
                (SignalDate, Symbol, SpreadType, PredictedLabel, Confidence, ModelVersion)
            VALUES (:d, :sym, :st, :lbl, :conf, :mv)
        """), {"d": signal_date, "sym": symbol, "st": spread_type,
               "lbl": label, "conf": confidence, "mv": model_version})
        return int(_scalar(c, "SELECT SCOPE_IDENTITY()") or 0)


def link_signal_to_position(engine, signal_id: int, position_id: int) -> None:
    with engine.begin() as c:
        c.execute(text(
            "UPDATE portfolio.ModelSignal SET WasTaken=1, PositionId=:pid WHERE SignalId=:sid"
        ), {"pid": position_id, "sid": signal_id})
        c.execute(text(
            "UPDATE portfolio.Position SET ModelSignalId=:sid WHERE PositionId=:pid"
        ), {"sid": signal_id, "pid": position_id})


# ── analytics ─────────────────────────────────────────────────────────────────

def get_strategy_performance(engine) -> pd.DataFrame:
    with engine.connect() as c:
        return _df(c, "SELECT * FROM portfolio.vw_StrategyPerformance ORDER BY TotalPnL DESC")


def get_monthly_pnl(engine) -> pd.DataFrame:
    # Bypass vw_MonthlyPnL — FORMAT() in window ORDER BY exceeds SQL Server's 900-byte limit.
    # Use integer Year/Month in the window function instead.
    with engine.connect() as c:
        return _df(c, """
            SELECT
                YEAR(p.CloseDate)   AS [Year],
                MONTH(p.CloseDate)  AS [Month],
                FORMAT(p.CloseDate, 'yyyy-MM') AS YearMonth,
                COUNT(*)            AS Trades,
                SUM(CASE WHEN p.RealizedPnL > 0 THEN 1 ELSE 0 END) AS Wins,
                ROUND(100.0 * SUM(CASE WHEN p.RealizedPnL > 0 THEN 1 ELSE 0 END)
                            / NULLIF(COUNT(*), 0), 1) AS WinRate,
                ROUND(SUM(p.RealizedPnL), 2)  AS MonthlyPnL,
                ROUND(AVG(p.RealizedPnL), 2)  AS AvgTradePnL,
                ROUND(SUM(SUM(p.RealizedPnL)) OVER (
                    ORDER BY YEAR(p.CloseDate), MONTH(p.CloseDate)
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ), 2) AS CumPnL
            FROM portfolio.Position p
            WHERE p.Status IN ('closed','expired','assigned')
              AND p.RealizedPnL IS NOT NULL
              AND p.CloseDate IS NOT NULL
            GROUP BY YEAR(p.CloseDate), MONTH(p.CloseDate), FORMAT(p.CloseDate, 'yyyy-MM')
            ORDER BY [Year], [Month]
        """)


def get_model_accuracy(engine) -> pd.DataFrame:
    with engine.connect() as c:
        return _df(c, "SELECT * FROM portfolio.vw_ModelAccuracy ORDER BY TotalPnLWhenTaken DESC")


def get_kpis(engine, account_id: int) -> dict:
    """Returns headline KPIs for the dashboard header."""
    with engine.connect() as c:
        bal = _df(c,
            "SELECT TOP 1 TotalEquity, DayPnL, RealizedPnLYTD "
            "FROM portfolio.Balance WHERE AccountId=:aid ORDER BY BalanceDate DESC",
            {"aid": account_id}
        )
        open_ct = _scalar(c,
            "SELECT COUNT(*) FROM portfolio.Position WHERE AccountId=:aid AND Status='open'",
            {"aid": account_id}
        ) or 0
        perf = _df(c,
            "SELECT COUNT(*) AS T, SUM(CASE WHEN RealizedPnL>0 THEN 1 ELSE 0 END) AS W "
            "FROM portfolio.Position WHERE AccountId=:aid AND Status IN ('closed','expired','assigned')",
            {"aid": account_id}
        )

    total_eq = float(bal.iloc[0]["TotalEquity"]) if not bal.empty else None
    day_pnl  = float(bal.iloc[0]["DayPnL"])      if not bal.empty and bal.iloc[0]["DayPnL"] else None
    ytd_pnl  = float(bal.iloc[0]["RealizedPnLYTD"]) if not bal.empty and bal.iloc[0]["RealizedPnLYTD"] else None
    total_t  = int(perf.iloc[0]["T"])  if not perf.empty else 0
    wins     = int(perf.iloc[0]["W"])  if not perf.empty and perf.iloc[0]["W"] else 0
    win_rate = round(wins / total_t * 100, 1) if total_t > 0 else None

    return {
        "total_equity": total_eq,
        "day_pnl":      day_pnl,
        "ytd_pnl":      ytd_pnl,
        "open_positions": int(open_ct),
        "total_trades": total_t,
        "wins":         wins,
        "win_rate":     win_rate,
    }
