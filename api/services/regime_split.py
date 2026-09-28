"""
api/services/regime_split.py — a strategy's paper P&L split by the dealer-GEX regime the service recorded:
the out-of-sample test of "the edge concentrates on negative-gamma days" (docs/research/gex_edge_2026-09.md §3).

``split(strategy, from, to, regime_source, at)``:

* **days** — every trading day in the window: the regime (``app.GexHistory``: ``at=prior_close`` = the
  previous session's end-of-day row, ``at=session`` = the day's 10:55 ET decision-time row), its net GEX,
  spot, flip and spot vs flip, whether the row was ``late``, and the strategy's closed trades and P&L that
  day. A day with no recorded row is ``"unrecorded"`` — kept, never guessed.
* **summary** — per regime: sessions, traded days, trades, win rate (per trade), winning days, P&L and
  P&L per traded day, next to the in-sample backtest's numbers for the same regime.
* **test** — negative minus positive P&L per traded day with Welch's t (live), and the in-sample difference.

The P&L is the ledger's, as strategy-stats reads it (closed trade groups, "P&L $"); a trade counts on the day
it was opened — the day its regime was decided (for 0DTE trades also the day it closed). Read only.
"""
from __future__ import annotations

import datetime as _dt
import math
from typing import Optional

import pandas as pd

from api.serialize import table_from_rows, to_jsonable

NY = "America/New_York"
REGIMES = ("negative", "positive", "near_flip", "unknown", "unrecorded")
SOURCES = ("NDX", "SPX", "SPY")
AT = ("prior_close", "session")
MAX_DAYS = 3 * 366

#: The in-sample reference: the ndx_0dte_tasty backtest split by regime in the GEX study
#: (docs/research/gex_edge_2026-09.md §3, gex_edge_2026-09_ndx.json "t7_trades").
IN_SAMPLE = {
    "ndx_0dte_tasty": {
        "source": "docs/research/gex_edge_2026-09.md §3 — the backtest's trades split by regime",
        "regime_basis": "SPY's proxy GEX rebuilt from stored monthly-expiry snapshots (volume for open interest), "
                        "not NDX / SPX / SPY live GEX as recorded now",
        "window": {"from": "2024-08-02", "to": "2026-07-13"}, "capital": 30000.0,
        "params": "v2.2 defaults incl. the VXN >= 20 gate", "trades": 2615, "days": 303,
        "prior_close": {
            "negative": {"days": 253, "share_of_days": 0.835, "pnl": 1155383.5, "pnl_per_day": 4566.73,
                         "win_days": 0.7945, "win_rate": 0.9360, "trades_per_day": 9.15},
            "positive": {"days": 32, "share_of_days": 0.1056, "pnl": 75397.5, "pnl_per_day": 2356.17,
                         "win_days": 0.6563, "win_rate": 0.9000, "trades_per_day": 5.94},
            "near_flip": {"days": 18, "share_of_days": 0.0594, "pnl": 35812.5, "pnl_per_day": 1989.58,
                          "win_days": 0.5000, "win_rate": 0.8829, "trades_per_day": 6.17},
            "negative_minus_positive_per_day": {"diff": 2210.56, "t": 2.60, "p": 0.012,
                                                "net_of_vxn": 1350.0, "net_of_vxn_p": 0.088},
        },
        "session": {                          # the proxy regime at 10:00 ET (the study's nearest to 10:55)
            "negative": {"days": 217, "pnl_per_day": 4589.57, "win_days": 0.7834},
            "positive": {"days": 60, "pnl_per_day": 3349.37, "win_days": 0.7000},
            "near_flip": {"days": 26, "pnl_per_day": 2680.58, "win_days": 0.7308},
            "negative_minus_positive_per_day": {"diff": 1240.20},
        },
    },
}

DAY_FIELDS = ["date", "regime", "net_gex", "spot", "flip", "spot_vs_flip", "dist_to_flip_pct", "late", "regime_slot",
              "trades", "wins", "pnl"]
_DAY_HEADERS = {"date": "Date", "regime": "Regime", "net_gex": "Net GEX", "spot": "Spot", "flip": "Flip",
                "spot_vs_flip": "Spot vs Flip", "dist_to_flip_pct": "Dist to Flip", "late": "Late",
                "regime_slot": "Recorded Slot", "trades": "Trades", "wins": "Wins", "pnl": "P&L"}
_DAY_FORMATS = {"net_gex": "money", "spot": "price", "flip": "price", "dist_to_flip_pct": "ratio",
                "trades": "int", "wins": "int", "pnl": "money"}
SUM_FIELDS = ["regime", "sessions", "days", "trades", "win_rate", "win_days", "pnl", "pnl_per_day", "late_sessions",
              "bt_days", "bt_pnl_per_day", "bt_win_days", "bt_win_rate"]
_SUM_HEADERS = {"regime": "Regime", "sessions": "Sessions", "days": "Traded Days", "trades": "Trades",
                "win_rate": "Win Rate", "win_days": "Winning Days", "pnl": "P&L", "pnl_per_day": "P&L / Day",
                "late_sessions": "Late Rows", "bt_days": "Backtest Days", "bt_pnl_per_day": "Backtest P&L / Day",
                "bt_win_days": "Backtest Winning Days", "bt_win_rate": "Backtest Win Rate"}
_SUM_FORMATS = {"win_rate": "ratio", "win_days": "ratio", "pnl": "money", "pnl_per_day": "money",
                "bt_pnl_per_day": "money", "bt_win_days": "ratio", "bt_win_rate": "ratio", "sessions": "int",
                "days": "int", "trades": "int", "late_sessions": "int", "bt_days": "int"}


def _date(v) -> Optional[_dt.date]:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        return pd.Timestamp(v).date()
    except (TypeError, ValueError):
        return None


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _today() -> _dt.date:
    return pd.Timestamp.now(tz=NY).date()


def trades_by_day(strategy: str) -> tuple[pd.DataFrame, int]:
    """(the strategy's closed trades: opened, closed, pnl — as strategy-stats reads the ledger; open positions)."""
    from api.services import paper as P
    open_groups, closed_rows, _ = P.load()
    df = pd.DataFrame([{"opened": _date(r.get("Open Date")), "closed": _date(r.get("Close Date")),
                        "pnl": _num(r.get("P&L $")) or 0.0}
                       for r in closed_rows or [] if str(r.get("Strategy") or "manual") == strategy],
                      columns=["opened", "closed", "pnl"])
    opens = sum(1 for g in (open_groups or {}).values()
                if not g.empty and str(g["StrategyName"].iloc[0]) == strategy)
    return df, opens


def trading_days(first: _dt.date, last: _dt.date) -> list[_dt.date]:
    from api.services.gex_recorder import trading_day
    out, d = [], first
    while d <= last:
        if trading_day(d):
            out.append(d)
        d += _dt.timedelta(days=1)
    return out


def _welch(a: list[float], b: list[float]) -> dict:
    out = {"n_negative": len(a), "n_positive": len(b), "diff": None, "t": None, "p": None,
           "enough": len(a) >= 2 and len(b) >= 2}
    if a and b:
        out["diff"] = round(sum(a) / len(a) - sum(b) / len(b), 2)
    if out["enough"]:
        try:
            from scipy import stats
            r = stats.ttest_ind(a, b, equal_var=False)
            if math.isfinite(r.statistic):
                out["t"], out["p"] = round(float(r.statistic), 3), round(float(r.pvalue), 4)
        except Exception:  # noqa: BLE001 — the difference stands without its test
            pass
    return out


def split(strategy: str = "ndx_0dte_tasty", from_date: Optional[str] = None, to_date: Optional[str] = None,
          regime_source: str = "NDX", at: str = "prior_close") -> dict:
    from api.services import gex_recorder as REC
    src = regime_source.upper()
    if src not in SOURCES:
        raise ValueError(f"regime_source must be one of {', '.join(SOURCES)}")
    if at not in AT:
        raise ValueError(f"at must be one of {', '.join(AT)}")
    today = _today()
    trades, open_positions = trades_by_day(strategy)
    fd = _dt.date.fromisoformat(from_date[:10]) if from_date else None
    td = min(_dt.date.fromisoformat(to_date[:10]), today) if to_date else today     # no day that has not come
    if fd is None:
        fd = min(trades["opened"].dropna()) if not trades.empty and trades["opened"].notna().any() else td
    if fd > td:
        raise ValueError("from must not be after to")
    if (td - fd).days > MAX_DAYS:
        raise ValueError(f"the window is limited to {MAX_DAYS} days")
    kind = "eod" if at == "prior_close" else "session"
    rows = REC.rows(src, kind, fd - _dt.timedelta(days=10), td)
    by_date = {_date(r.TradeDate): r for r in rows.itertuples(index=False)}
    trades = trades[(trades["opened"] >= fd) & (trades["opened"] <= td)] if not trades.empty else trades
    per_day = {d: g for d, g in trades.groupby("opened")} if not trades.empty else {}
    days = sorted(set(trading_days(fd, td)) | set(per_day))

    out_days = []
    for d in days:
        key = REC.previous_trading_day(d) if at == "prior_close" else d
        r = by_date.get(key)
        g = per_day.get(d)
        n = int(len(g)) if g is not None else 0
        row = {"date": d, "regime": "unrecorded", "net_gex": None, "spot": None, "flip": None, "spot_vs_flip": None,
               "dist_to_flip_pct": None, "late": None, "regime_slot": None, "regime_source": src, "trades": n,
               "wins": int((g["pnl"] > 0).sum()) if n else 0, "pnl": round(float(g["pnl"].sum()), 2) if n else 0.0}
        if r is not None:
            spot, flip = _num(r.Spot), _num(r.Flip)
            row.update(regime=str(r.Regime or "unknown"), net_gex=_num(r.NetGex), spot=spot, flip=flip,
                       spot_vs_flip=(None if spot is None or flip is None else
                                     "above" if spot > flip else "below" if spot < flip else "at"),
                       dist_to_flip_pct=_num(r.DistToFlipPct), late=bool(r.Late),
                       regime_slot=pd.Timestamp(r.SlotTs).to_pydatetime(), recorded_source=r.Source)
        out_days.append(row)

    ref = IN_SAMPLE.get(strategy)
    ref_at = (ref or {}).get(at) or {}
    summary = []
    for reg in REGIMES:
        ds = [x for x in out_days if x["regime"] == reg]
        traded = [x for x in ds if x["trades"]]
        n_tr = sum(x["trades"] for x in traded)
        pnl = round(sum(x["pnl"] for x in traded), 2)
        b = ref_at.get(reg) or {}
        summary.append({"regime": reg, "sessions": len(ds), "days": len(traded), "trades": n_tr,
                        "win_rate": round(sum(x["wins"] for x in traded) / n_tr, 4) if n_tr else None,
                        "win_days": round(sum(1 for x in traded if x["pnl"] > 0) / len(traded), 4) if traded else None,
                        "pnl": pnl, "pnl_per_day": round(pnl / len(traded), 2) if traded else None,
                        "late_sessions": sum(1 for x in ds if x["late"]),
                        "in_sample": b or None, "bt_days": b.get("days"), "bt_pnl_per_day": b.get("pnl_per_day"),
                        "bt_win_days": b.get("win_days"), "bt_win_rate": b.get("win_rate")})
    neg = [x["pnl"] for x in out_days if x["regime"] == "negative" and x["trades"]]
    pos = [x["pnl"] for x in out_days if x["regime"] == "positive" and x["trades"]]
    test = {"negative_minus_positive_per_day": _welch(neg, pos),
            "in_sample": ref_at.get("negative_minus_positive_per_day")}
    recorded = sum(1 for x in out_days if x["regime"] != "unrecorded")
    notes = []
    if not out_days or not recorded:
        notes.append(f"no {src} {kind} rows recorded for this window yet (app.GexHistory; the service records them "
                     f"while it runs — see /api/market/gex-recorder)")
    if ref:
        notes.append("in_sample regimes are SPY's volume-proxy GEX; live ones are the recorded " + src +
                     " GEX, and the backtest ran at $30k capital — compare shapes (negative vs positive), not "
                     "dollar levels")
    days_table = table_from_rows([{f: x.get(f) for f in DAY_FIELDS} for x in out_days], field_order=DAY_FIELDS,
                                 headers=_DAY_HEADERS, formats=_DAY_FORMATS,
                                 types={"date": "date", "regime": "string", "spot_vs_flip": "string",
                                        "late": "bool", "regime_slot": "datetime", "trades": "integer",
                                        "wins": "integer"})
    sum_table = table_from_rows([{f: x.get(f) for f in SUM_FIELDS} for x in summary], field_order=SUM_FIELDS,
                                headers=_SUM_HEADERS, formats=_SUM_FORMATS,
                                types={"regime": "string", "sessions": "integer", "days": "integer",
                                       "trades": "integer", "late_sessions": "integer", "bt_days": "integer"})
    from api.services import paper as P
    return to_jsonable({"strategy": strategy, "from": fd, "to": td, "regime_source": src, "at": at,
                        "account_id": P.account_id(), "sessions": len(out_days), "recorded_sessions": recorded,
                        "traded_days": sum(1 for x in out_days if x["trades"]),
                        "trades": sum(x["trades"] for x in out_days),
                        "pnl": round(sum(x["pnl"] for x in out_days), 2), "open_positions": open_positions,
                        "days": out_days, "summary": summary, "test": test,
                        "in_sample": ({k: v for k, v in ref.items() if k not in AT} if ref else None),
                        "notes": notes, "table": days_table, "summary_table": sum_table})
