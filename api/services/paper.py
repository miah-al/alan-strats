"""
api/services/paper.py — the paper account, read-only.

Built on the paper account's headless data layer (``paper/views.py``, formerly the Paper
Trading page's ``data.py``):
the ledger load, net entry, liquidation value, capital at risk, structure label,
runner ownership and the runner-published marks. The account arithmetic mirrors the
page's ``refresh_all`` card by card, so the figures tie to the same cash.

Marks: a position is priced by the paper session that holds it (its heartbeat /
state files under ``<checkout>/paper_state``), expired legs settle at intrinsic, and
anything else falls back to its entry value. Nothing here opens a broker connection.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from api.serialize import series, table_from_df, table_from_rows, to_jsonable
from api.services.db import require_db

logger = logging.getLogger("alan_trader.api.paper")


def PD():
    """The paper account's data module (``paper.views``)."""
    from paper import views
    return views


def account_id() -> int:
    """The paper account shown and traded (``ALAN_TRADER_PAPER_ACCOUNT_ID``, default the runner's)."""
    from api.config import paper_account_id
    return paper_account_id()


def _labels() -> dict[str, str]:
    from api.services.strategies import labels
    try:
        return labels()
    except Exception:
        return {}


def _today() -> _dt.date:
    return _dt.date.today()


def load() -> tuple[dict, list, pd.DataFrame]:
    """(open_groups, closed_rows, txns_df). Raises DatabaseUnavailable when the DB is down
    (the page's own loader turns every failure into 'no data')."""
    from engine.positions import get_closed_trade_groups, get_open_trade_groups, load_transactions
    eng = require_db()
    txns = load_transactions(eng, account_id())
    if txns is None or txns.empty:
        return {}, [], pd.DataFrame()
    return get_open_trade_groups(txns), get_closed_trade_groups(txns), txns


def _deposit_cash() -> float:
    from sqlalchemy import text
    with require_db().connect() as conn:
        row = conn.execute(text("""
            SELECT TOP 1 Amount FROM portfolio.Balance
            WHERE AccountId = :aid AND BalanceType = 'Cash'
            ORDER BY BusinessDate DESC
        """), {"aid": account_id()}).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def _trade_cash_flow(txns: pd.DataFrame) -> float:
    """Net cash of every non-cash row: the booked Amount when the runner wrote one,
    else price x quantity x multiplier (SELL +, BUY -) — as the page computes it."""
    total = 0.0
    if txns is None or txns.empty:
        return total
    for _, r in txns.iterrows():
        if str(r.get("SecurityType", "")).lower() == "cash":
            continue
        dirn = str(r.get("Direction", "")).upper()
        qty = float(r.get("Quantity") or 0)
        px = float(r.get("TransactionPrice") or 0)
        mult = float(r.get("Multiplier") or 1)
        amt = r.get("Amount")
        if amt is not None and amt == amt:
            total += float(amt)
        else:
            total += (1.0 if dirn == "SELL" else -1.0) * qty * px * mult
    return total


# ── Groups for the order book ─────────────────────────────────────────────────

def open_group(trade_group_id: str) -> Optional[pd.DataFrame]:
    """The open trade group's ledger rows (non-cash), or None when it is not open."""
    open_groups, _c, _t = load()
    grp = open_groups.get(str(trade_group_id))
    if grp is None:
        return None
    return _noncash(grp)


def known_group(trade_group_id: str) -> bool:
    _o, _c, txns = load()
    return (not txns.empty and "TradeGroupId" in txns.columns
            and bool((txns["TradeGroupId"].astype(str) == str(trade_group_id)).any()))


# ── Live marks from the market-data hub ───────────────────────────────────────
# A position no paper runner prices (one placed through the service, say) is marked at the hub's
# current mids — the same quotes its paper fills came from — instead of at its entry price. A group
# the runner holds keeps the runner's own mark; an expired leg settles at intrinsic; a group with any
# leg the hub cannot price keeps the page's entry-value fallback (never a mix).

def _leg_symbol(r) -> Optional[str]:
    from api.marketdata import symbols as SYM
    try:
        return SYM.normalize(str(r.get("Symbol") or ""))
    except ValueError:
        return None


#: paper/providers.py PARITY_TAG: the runner's note on a put vertical it booked as a call credit spread's equivalent
PARITY_TAG = "priced via call parity"


def _parity_group(grp: pd.DataFrame) -> bool:
    """A two-leg put vertical the runner booked as the equivalent of a call credit spread -- its opening note says
    'priced via call parity' (ndx_gamma_walls). The runner marks it off the calls at its strikes (the quoted side:
    its own deep in-the-money puts are quoted so wide that a mark taken from them wanders between polls), and so
    does the hub fallback here, the same way: paper/providers.py parity_put_quote."""
    try:
        if "Notes" not in grp.columns or not grp["Notes"].astype(str).str.contains(PARITY_TAG, regex=False).any():
            return False
        legs = _noncash(grp)
        legs = legs[legs["SecurityType"].astype(str).str.lower() == "option"]
        return len(legs) == 2 and all(str(t).upper().startswith("P") for t in legs["OptionType"])
    except Exception:
        return False


def _parity_call_symbols(grp: pd.DataFrame) -> dict:
    """{put leg symbol: the call at the same strike and expiry} for a parity group (canonical spellings)."""
    from api.marketdata import symbols as SYM
    out: dict = {}
    for _, r in _noncash(grp).iterrows():
        s = _leg_symbol(r)
        o = SYM.parse_option(s) if s else None
        if o is not None and o.right == "P":
            out[s] = SYM.make_option(o.root, o.expiry, "C", o.strike).occ
    return out


def _parity_value(grp: pd.DataFrame, quotes: dict):
    """(liquidation value, source, legs) of a parity group off the calls' mids, or None while a call is unquoted.
    Per leg the put is the call less its intrinsic, call - (S - K); across an equal-size vertical the spot
    cancels, so each leg contributes sign x qty x mult x (call mid + strike) and the sum is width - the call
    spread's value: the number the runner marks the position at."""
    calls = _parity_call_symbols(grp)
    mv, sources, n = 0.0, set(), 0
    for _, r in _noncash(grp).iterrows():
        q = quotes.get(calls.get(_leg_symbol(r) or "", "")) or {}
        if q.get("mid") is None:
            return None
        qty = abs(float(r.get("Quantity") or 0))
        mult = float(r.get("Multiplier") or 100)
        sign = 1.0 if str(r.get("Direction", "")).upper().startswith("B") else -1.0
        mv += sign * qty * mult * (float(q["mid"]) + float(r.get("Strike") or 0))
        n += 1
        if q.get("source"):
            sources.add(str(q["source"]))
    bound = PD()._vertical_bound(grp)
    if bound is not None:
        mv = min(bound[1], max(bound[0], mv))
    return round(mv, 2), "market data (" + ", ".join(sorted(sources)) + ") by call parity", n


def _hub_quotes(open_groups: dict, runner_marks: dict, hub, all_groups: bool = False) -> dict:
    """One snapshot of the open groups' legs (runner-held groups too with ``all_groups``: their greeks),
    their underlyings and SPY."""
    if hub is None or not getattr(hub, "providers", None) or not open_groups:
        return {}
    pd_ = PD()
    today = _today()
    syms: set[str] = set()
    if all_groups:
        syms.add("SPY")
        for grp in open_groups.values():
            u = grp["Underlying"].dropna() if "Underlying" in grp.columns else pd.Series(dtype=str)
            if not u.empty:
                syms.add(_canon(str(u.iloc[0])))
    for tgid, grp in open_groups.items():
        if not all_groups and pd_.runner_mark_for(runner_marks, tgid) is not None:
            continue
        for _, r in _noncash(grp).iterrows():
            exp = r.get("Expiration")
            if exp is not None and not pd.isna(exp) and pd.Timestamp(exp).date() < today:
                continue
            s = _leg_symbol(r)
            if s:
                syms.add(s)
        if _parity_group(grp):
            syms.update(_parity_call_symbols(grp).values())       # marked off the calls at the same strikes
    if not syms:
        return {}
    try:
        return {q["symbol"]: q for q in hub.snapshot(sorted(syms), wait=2.0)}
    except Exception as exc:
        logger.warning("hub marks unavailable: %s", exc)
        return {}


def _hub_value(tgid, grp: pd.DataFrame, runner_marks: dict, quotes: Optional[dict]):
    """(liquidation value, "market data (<source>)", legs) or None."""
    if not quotes:
        return None
    pd_ = PD()
    if pd_.runner_mark_for(runner_marks, tgid) is not None:
        return None
    if _parity_group(grp):
        pv = _parity_value(grp, quotes)
        if pv is not None:
            return pv
    today = _today()
    mv, sources, n = 0.0, set(), 0
    cache: dict = {}
    for _, r in _noncash(grp).iterrows():
        st = str(r.get("SecurityType") or "").lower()
        qty = abs(float(r.get("Quantity") or 0))
        mult = float(r.get("Multiplier") or (100 if st == "option" else 1))
        sign = 1.0 if str(r.get("Direction", "")).upper().startswith("B") else -1.0
        exp = r.get("Expiration")
        px = None
        if st == "option" and exp is not None and not pd.isna(exp) and pd.Timestamp(exp).date() < today:
            px = pd_._expired_option_intrinsic(r, None, cache)
            src = "expiry settlement"
        else:
            q = quotes.get(_leg_symbol(r) or "") or {}
            px = q.get("mid")
            if px is None and st != "option":
                px = q.get("last")
            src = q.get("source")
        if px is None:
            return None
        mv += sign * qty * float(px) * mult
        n += 1
        if src:
            sources.add(str(src))
    bound = pd_._vertical_bound(grp)
    if bound is not None:
        mv = min(bound[1], max(bound[0], mv))
    return round(mv, 2), "market data (" + ", ".join(sorted(sources)) + ")", n


# ── Summary ───────────────────────────────────────────────────────────────────

def summary(hub=None) -> dict:
    pd_ = PD()
    open_groups, closed_rows, txns = load()
    runner_marks = pd_.paper_runner_marks()
    hub_quotes = _hub_quotes(open_groups, runner_marks, hub)
    market_value = total_entry = 0.0
    n_priced = n_total = 0
    for tgid, grp in open_groups.items():
        total_entry += pd_._net_entry(grp)
        try:
            mv, _live, np_, nt = pd_.live_market_value({tgid: grp})
        except Exception:
            mv, np_, nt = 0.0, 0, 0
        hv = _hub_value(tgid, grp, runner_marks, hub_quotes)
        if hv is not None:
            mv, np_, nt = hv[0], hv[2], hv[2]
        market_value += mv
        n_priced += np_
        n_total += nt

    deposit_cash = _deposit_cash()
    cash = deposit_cash + _trade_cash_flow(txns)
    equity = cash + market_value
    realized = float(sum(r.get("P&L $", 0) or 0 for r in closed_rows)) if closed_rows else 0.0
    unrealized_entry_basis = total_entry + market_value
    starting = deposit_cash if deposit_cash else (equity or 0.0)
    total_pnl = (equity - starting) if starting else (unrealized_entry_basis + realized)
    unrealized = (total_pnl - realized) if starting else unrealized_entry_basis
    total_return = ((equity - starting) / starting) if starting else 0.0
    today = _today().isoformat()
    today_pnl = sum(r.get("P&L $", 0) or 0 for r in closed_rows
                    if str(r.get("Close Date", ""))[:10] == today) if closed_rows else 0.0
    n_closed = len(closed_rows or [])
    wins = sum(1 for r in closed_rows or [] if (r.get("P&L $", 0) or 0) > 0)
    return to_jsonable({
        "starting_capital": starting,
        "cash": cash,
        "market_value": market_value,
        "equity": equity,
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "total_pnl": total_pnl,
        "total_return": total_return,
        "open_positions": len(open_groups),
        "closed_positions": n_closed,
        "asof": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "live_marks": bool(n_total > 0 and n_priced == n_total),
        # additions beyond contract v1
        "total_return_pct": total_return * 100.0,
        "unrealized_pnl_entry_basis": unrealized_entry_basis,
        "today_realized_pnl": today_pnl,
        "wins": wins,
        "win_rate": (wins / n_closed) if n_closed else None,
        "deposits": deposit_cash,
        "legs_priced": n_priced,
        "legs_total": n_total,
        "marks_sources": sorted({v[2] for v in runner_marks.values()}),
    })


# ── Positions ─────────────────────────────────────────────────────────────────

_POS_FIELDS = ["trade_group_id", "strategy", "strategy_label", "underlying", "structure", "expiry", "dte",
               "contracts", "opened", "closed", "entry_net", "mark", "market_value", "pnl", "pnl_pct",
               "max_risk", "managed_by", "status", "priced_by", "is_live", "legs", "alert",
               # position risk (v2)
               "spot", "direction", "units", "entry_credit_debit", "entry_type", "pnl_pct_of_max", "max_profit",
               "max_loss", "breakevens", "short_strikes", "short_delta", "nearest_short_strike", "sigma_to_short",
               "delta", "gamma", "theta", "vega", "beta_spy", "beta_delta_spy", "greeks_source", "runner_feed"]
_POS_HEADERS = {"trade_group_id": "Trade Group", "strategy": "Strategy (slug)", "strategy_label": "Strategy",
                "underlying": "Underlying", "structure": "Structure", "expiry": "Expiry", "dte": "DTE",
                "contracts": "Contracts", "opened": "Opened", "closed": "Closed", "entry_net": "Net Entry",
                "mark": "Mark", "market_value": "Market Value", "pnl": "P&L", "pnl_pct": "P&L %",
                "max_risk": "Max Risk", "managed_by": "Managed By", "status": "Status",
                "priced_by": "Priced By", "is_live": "Live", "legs": "Legs", "alert": "Alert",
                "spot": "Spot", "direction": "Direction", "units": "Units", "entry_credit_debit": "Entry (per unit)",
                "entry_type": "Credit/Debit", "pnl_pct_of_max": "% of Max Profit", "max_profit": "Max Profit",
                "max_loss": "Max Loss", "breakevens": "Breakevens", "short_strikes": "Short Strikes",
                "short_delta": "Short Δ", "nearest_short_strike": "Nearest Short", "sigma_to_short": "σ to Short",
                "delta": "Delta", "gamma": "Gamma", "theta": "Theta", "vega": "Vega", "beta_spy": "Beta (SPY)",
                "beta_delta_spy": "β-Δ (SPY shs)", "greeks_source": "Greeks From", "runner_feed": "Runner Feed"}
_POS_FORMATS = {"entry_net": "money", "market_value": "money", "pnl": "money", "max_risk": "money",
                "pnl_pct": "pct", "mark": "price", "contracts": "int", "dte": "int", "legs": "int",
                "spot": "price", "entry_credit_debit": "price", "pnl_pct_of_max": "pct", "max_profit": "money",
                "max_loss": "money", "breakevens": "list", "short_strikes": "list", "nearest_short_strike": "price",
                "theta": "money", "vega": "money", "units": "int"}
_POS_TYPES = {"trade_group_id": "string", "strategy": "string", "strategy_label": "string",
              "underlying": "string", "structure": "string", "expiry": "date", "dte": "integer",
              "contracts": "number", "opened": "date", "closed": "date", "entry_net": "number",
              "mark": "number", "market_value": "number", "pnl": "number", "pnl_pct": "number",
              "max_risk": "number", "managed_by": "string", "status": "string", "priced_by": "string",
              "is_live": "bool", "legs": "integer", "alert": "string",
              "spot": "number", "direction": "string", "units": "integer", "entry_credit_debit": "number",
              "entry_type": "string", "pnl_pct_of_max": "number", "max_profit": "number", "max_loss": "number",
              "breakevens": "string", "short_strikes": "string", "short_delta": "number",
              "nearest_short_strike": "number", "sigma_to_short": "number", "delta": "number", "gamma": "number",
              "theta": "number", "vega": "number", "beta_spy": "number", "beta_delta_spy": "number",
              "greeks_source": "string", "runner_feed": "string"}


def _closing_mask(grp: pd.DataFrame) -> pd.Series:
    notes = grp.get("Notes", pd.Series("", index=grp.index)).fillna("").astype(str).str.upper()
    src = grp.get("Source", pd.Series("", index=grp.index)).fillna("").astype(str).str.upper()
    return notes.str.contains("CLOSE") | (src == "CLOSE")


def _noncash(grp: pd.DataFrame) -> pd.DataFrame:
    if "SecurityType" not in grp.columns:
        return grp
    return grp[grp["SecurityType"].astype(str).str.lower() != "cash"]


def _expiry(grp: pd.DataFrame) -> Optional[_dt.date]:
    if "Expiration" not in grp.columns:
        return None
    exps = grp["Expiration"].dropna()
    if exps.empty:
        return None
    try:
        return pd.to_datetime(exps).min().date()
    except Exception:
        return None


def _contracts(grp: pd.DataFrame) -> Optional[float]:
    """Position size: the largest net quantity held in any one security (a 2-lot
    vertical is 2, a 1-lot condor 1)."""
    g = _noncash(grp)
    if g.empty or "Symbol" not in g.columns:
        return None
    signed = g.apply(lambda r: (1.0 if str(r.get("Direction", "")).upper() == "BUY" else -1.0)
                     * abs(float(r.get("Quantity") or 0)), axis=1)
    net = signed.groupby(g["Symbol"]).sum().abs()
    top = float(net.max()) if len(net) else 0.0
    if top == 0.0:   # a closed group nets to zero: report the size it was opened with
        top = float(g["Quantity"].abs().max()) if "Quantity" in g.columns else 0.0
    return top or None


def _multiplier(grp: pd.DataFrame) -> float:
    g = _noncash(grp)
    if "Multiplier" in g.columns and not g["Multiplier"].dropna().empty:
        try:
            return float(g["Multiplier"].dropna().max()) or 1.0
        except Exception:
            pass
    return 100.0


def _alert_level(grp, label, upnl, ne) -> str:
    try:
        from engine.positions import compute_position_alerts
        levels = {a.get("level", "") for a in compute_position_alerts(grp, label, upnl, ne)}
    except Exception:
        return "ok"
    return "error" if "error" in levels else ("warning" if "warning" in levels else "ok")


def _open_row(tgid: str, grp: pd.DataFrame, runner_marks: dict, labels: dict,
              hub_quotes: Optional[dict] = None, hub=None) -> dict:
    pd_ = PD()
    slug = str(grp["StrategyName"].iloc[0]) if not grp.empty else ""
    label = labels.get(slug, slug)
    und = (grp["Underlying"].dropna().iloc[0] if "Underlying" in grp.columns and not grp["Underlying"].dropna().empty
           else (grp["Symbol"].iloc[0] if not grp.empty else "?"))
    ne = pd_._net_entry(grp)
    try:
        mv, is_live, _, _ = pd_.live_market_value({tgid: grp})
    except Exception:
        mv, is_live = 0.0, False
    hv = _hub_value(tgid, grp, runner_marks, hub_quotes)
    if hv is not None:
        mv, is_live = hv[0], True
    upnl = ne + mv
    risk = pd_.position_risk(grp)
    basis = risk if (risk and risk > 0) else (abs(ne) if ne else None)
    exp = _expiry(grp)
    n = _contracts(grp)
    rm = pd_.runner_mark_for(runner_marks, tgid)
    if rm is not None:
        mark, priced_by = float(rm[0]), rm[2]
    else:
        mark = (mv / (n * _multiplier(grp))) if n else None
        priced_by = hv[1] if hv is not None else "entry price"
    feed = pd_.managed_by_runner(tgid)
    rk = _risk(grp, str(und), hub_quotes, hub)
    maxp = rk.get("max_profit")
    return {
        "trade_group_id": str(tgid), "strategy": slug, "strategy_label": label, "underlying": str(und),
        "expiry": exp,
        "dte": (exp - _today()).days if exp else None, "contracts": n,
        "opened": str(grp["BusinessDate"].min())[:10] if "BusinessDate" in grp.columns else None,
        "closed": None, "entry_net": ne, "mark": mark, "market_value": mv, "pnl": upnl,
        "pnl_pct": (upnl / basis * 100.0) if basis else None, "max_risk": risk,
        "status": "open", "priced_by": priced_by,
        "is_live": bool(is_live), "legs": int(len(_noncash(grp))), "alert": _alert_level(grp, label, upnl, ne),
        **{k: v for k, v in rk.items() if k != "first_expiry"},
        "structure": rk.get("structure") or pd_.structure_label(grp),
        "pnl_pct_of_max": (upnl / maxp * 100.0) if (maxp and maxp > 0) else None,
        "managed_by": "runner" if feed else "manual", "runner_feed": feed,
    }


def _risk(grp: pd.DataFrame, und: str, quotes: Optional[dict], hub) -> dict:
    """The position-risk fields (api/services/risk.py) on the quotes already fetched for the table."""
    from api.services import risk as RK
    try:
        quotes = quotes or {}
        legs = RK.net_legs(_noncash(grp))
        spot = _quote_price(quotes.get(_canon(und)), index=_is_index(und))
        spy = _quote_price(quotes.get("SPY"))
        greeks = RK.leg_greeks(hub, legs, spot, wait=0.0, quotes=quotes)
        return RK.position_risk_fields(hub, _noncash(grp), und, spot=spot, spy=spy, greeks=greeks)
    except Exception as exc:  # noqa: BLE001 — a risk figure must never cost the row
        logger.warning("risk for a %s position failed: %s", und, exc)
        return {}


def _canon(sym: str) -> str:
    from api.marketdata import symbols as SYM
    try:
        return SYM.normalize(sym)
    except ValueError:
        return sym


def _is_index(sym: str) -> bool:
    from api.marketdata import symbols as SYM
    return SYM.is_index(_canon(sym))


def _quote_price(q: Optional[dict], index: bool = False) -> Optional[float]:
    if not q:
        return None
    for k in (("last", "mid") if index else ("mid", "last")):
        if q.get(k) is not None:
            return float(q[k])
    return None


def _closed_row(r: dict, txns: pd.DataFrame, labels: dict) -> dict:
    pd_ = PD()
    tgid = r.get("TradeGroupId")
    grp = _noncash(txns[txns["TradeGroupId"].astype(str) == str(tgid)]) if "TradeGroupId" in txns.columns else txns.iloc[0:0]
    opening = grp[~_closing_mask(grp)] if not grp.empty else grp
    slug = str(r.get("Strategy") or "")
    pnl = float(r.get("P&L $") or 0.0)
    ne = pd_._net_entry(opening) if not opening.empty else float(r.get("Net Entry") or 0.0)
    risk = pd_.position_risk(opening) if not opening.empty else None
    basis = risk if (risk and risk > 0) else (abs(ne) if ne else None)
    exp = _expiry(grp)
    od, cd = r.get("Open Date"), r.get("Close Date")
    extra: dict = {}
    if not opening.empty:
        try:
            from api.services import risk as RK
            legs_ = RK.net_legs(opening)
            extra = {"structure": RK.describe_structure(legs_) or pd_.structure_label(opening),
                     **{k: v for k, v in RK.payoff_stats(opening, None).items()},
                     "short_strikes": sorted({l.strike for l in legs_ if l.is_option and l.qty < 0})}
            maxp = extra.get("max_profit")
            extra["pnl_pct_of_max"] = (pnl / maxp * 100.0) if (maxp and maxp > 0) else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("closed-row figures failed: %s", exc)
    return {
        **extra,
        "trade_group_id": str(tgid), "strategy": slug, "strategy_label": labels.get(slug, slug),
        "underlying": str(r.get("Underlying", "?")),
        "structure": extra.get("structure") or (pd_.structure_label(opening) if not opening.empty else ""),
        "expiry": exp, "dte": None, "contracts": _contracts(opening) if not opening.empty else None,
        "opened": str(od)[:10] if od is not None else None, "closed": str(cd)[:10] if cd is not None else None,
        "entry_net": ne, "mark": None, "market_value": 0.0, "pnl": pnl,
        "pnl_pct": (pnl / basis * 100.0) if basis else None, "max_risk": risk, "managed_by": None,
        "status": "closed", "priced_by": "closed", "is_live": False, "legs": int(len(grp)),
        "alert": "win" if pnl > 0 else ("loss" if pnl < 0 else "flat"),
    }


def positions(status: str = "open", hub=None) -> dict:
    open_groups, closed_rows, txns = load()
    labels = _labels()
    rows: list[dict] = []
    if status in ("open", "all"):
        marks = PD().paper_runner_marks()
        hq = _hub_quotes(open_groups, marks, hub, all_groups=True)
        opened = [_open_row(t, g, marks, labels, hq, hub) for t, g in open_groups.items()]
        rows += sorted(opened, key=lambda x: (x["opened"] or "", x["trade_group_id"]), reverse=True)
    if status in ("closed", "all"):
        closed = [_closed_row(r, txns, labels) for r in closed_rows or []]
        rows += sorted(closed, key=lambda x: (x["closed"] or "", x["trade_group_id"]), reverse=True)
    if not rows:
        from api.serialize import column
        return {"columns": [column(f, header=_POS_HEADERS.get(f, f), type=_POS_TYPES.get(f, "string"),
                                   format=_POS_FORMATS.get(f)) for f in _POS_FIELDS], "rows": []}
    return table_from_rows(rows, field_order=_POS_FIELDS, headers=_POS_HEADERS, formats=_POS_FORMATS,
                           types=_POS_TYPES)


# ── Legs ──────────────────────────────────────────────────────────────────────

class UnknownTradeGroup(KeyError):
    pass


_LEG_HEADERS = {"transaction_id": "Txn", "date": "Date", "symbol": "Symbol", "underlying": "Underlying",
                "security_type": "Security", "type": "Type", "strike": "Strike", "expiry": "Expiry",
                "side": "Side", "quantity": "Qty", "multiplier": "Mult", "entry_price": "Entry Price",
                "mark": "Mark", "mark_source": "Mark Source", "pnl": "P&L", "commission": "Commission",
                "amount": "Amount", "leg_type": "Leg", "source": "Source", "closing": "Closing", "notes": "Notes",
                "iv": "IV", "delta": "Delta", "gamma": "Gamma", "theta": "Theta", "vega": "Vega",
                "greeks_source": "Greeks From"}
_LEG_TYPES = {"transaction_id": "integer", "date": "date", "strike": "number", "expiry": "date",
              "quantity": "number", "multiplier": "number", "entry_price": "number", "mark": "number",
              "mark_source": "string", "pnl": "number", "commission": "number", "amount": "number",
              "closing": "bool", "iv": "number", "delta": "number", "gamma": "number", "theta": "number",
              "vega": "number", "greeks_source": "string"}


def legs(trade_group_id: str, hub=None) -> dict:
    pd_ = PD()
    open_groups, _closed, txns = load()
    if txns.empty or "TradeGroupId" not in txns.columns:
        raise UnknownTradeGroup(trade_group_id)
    grp = txns[txns["TradeGroupId"].astype(str) == str(trade_group_id)]
    if grp.empty:
        raise UnknownTradeGroup(trade_group_id)
    grp = _noncash(grp)
    is_open = str(trade_group_id) in {str(k) for k in open_groups}
    live, spot = pd_.live_leg_prices(grp) if is_open else ({}, None)
    closing = _closing_mask(grp)
    settle_cache: dict = {}
    greeks: dict = {}
    q: dict = {}
    calls = _parity_call_symbols(grp) if (is_open and _parity_group(grp)) else {}      # a parity-booked put: off the calls
    if is_open:
        from api.services import risk as RK
        und = str(grp["Underlying"].dropna().iloc[0]) if "Underlying" in grp.columns and not grp["Underlying"].dropna().empty else ""
        try:
            nl = RK.net_legs(grp)
            if hub is not None and getattr(hub, "providers", None):
                q = {m["symbol"]: m for m in hub.snapshot([_canon(und)] + [l.symbol for l in nl] + sorted(calls.values()), wait=2.0)}
            if spot is None:
                spot = _quote_price(q.get(_canon(und)), index=_is_index(und))
            by_ledger = RK.leg_greeks(hub, nl, spot, wait=0.0, quotes=q)
            greeks = {l.ledger_symbol: by_ledger.get(l.symbol) or {} for l in nl}
        except Exception as exc:  # noqa: BLE001
            logger.warning("leg greeks for %s failed: %s", trade_group_id, exc)
    rows = []
    for idx, r in grp.iterrows():
        st = str(r.get("SecurityType") or "").lower()
        sym = str(r.get("Symbol", ""))
        side = str(r.get("Direction", "")).upper()
        qty = abs(float(r.get("Quantity") or 0))
        mult = float(r.get("Multiplier") or (100 if st == "option" else 1))
        entry = float(r.get("TransactionPrice") or 0)
        mark, src = None, None
        if is_open and st == "option":
            px = (live.get(sym) or {}).get("price")
            if px is not None and float(px) > 0:
                mark, src = float(px), "paper runner feed"
            else:
                ex = pd_._expired_option_intrinsic(r, None, settle_cache)
                if ex is not None:
                    mark, src = float(ex), "expiry settlement"
        g = greeks.get(sym) or {}
        cq = q.get(calls.get(_leg_symbol(r) or "", "")) or {} if calls else {}
        if is_open and mark is None and cq.get("mid") is not None and spot is not None:
            from paper.providers import parity_leg_mid
            mark = round(parity_leg_mid(float(cq["mid"]), float(spot), float(r.get("Strike") or 0)), 4)
            src = f"market data ({cq.get('source')}) by call parity"
        if is_open and mark is None and g.get("mark") is not None:
            mark, src = float(g["mark"]), f"market data ({g.get('mark_source')})"
        pnl = ((1.0 if side == "BUY" else -1.0) * (mark - entry) * qty * mult) if mark is not None else None
        rows.append({
            "transaction_id": r.get("TransactionId"), "date": r.get("BusinessDate"), "symbol": sym,
            "underlying": r.get("Underlying"), "security_type": r.get("SecurityType"),
            "type": r.get("OptionType") if st == "option" else r.get("SecurityType"),
            "strike": r.get("Strike"), "expiry": r.get("Expiration"), "side": side, "quantity": qty,
            "multiplier": mult, "entry_price": entry, "mark": mark, "mark_source": src, "pnl": pnl,
            "commission": r.get("Commission"), "amount": r.get("Amount"), "leg_type": r.get("LegType"),
            "source": r.get("Source"), "closing": bool(closing.loc[idx]), "notes": r.get("Notes"),
            "iv": g.get("iv"), "delta": g.get("delta"), "gamma": g.get("gamma"), "theta": g.get("theta"),
            "vega": g.get("vega"), "greeks_source": g.get("source"),
        })
    table = table_from_rows(rows, headers=_LEG_HEADERS, types=_LEG_TYPES,
                            formats={"entry_price": "price", "mark": "price", "pnl": "money",
                                     "amount": "money", "commission": "money", "strike": "price", "iv": "ratio"})
    table.update({"trade_group_id": str(trade_group_id), "status": "open" if is_open else "closed",
                  "spot": spot})
    return to_jsonable(table)


# ── Transactions ──────────────────────────────────────────────────────────────

def transactions(limit: Optional[int] = None) -> dict:
    _o, _c, txns = load()
    if txns.empty:
        return {"columns": [], "rows": []}
    df = txns.copy()
    labels = _labels()
    if "StrategyName" in df.columns:
        df.insert(df.columns.get_loc("StrategyName") + 1, "StrategyLabel",
                  df["StrategyName"].map(lambda s: labels.get(str(s), str(s))))
    if limit:
        df = df.head(int(limit))
    return table_from_df(df, formats={"TransactionPrice": "price", "Amount": "money", "Commission": "money",
                                      "Strike": "price"})


# ── Equity ────────────────────────────────────────────────────────────────────

def _cash_series(txns: pd.DataFrame, start, end) -> pd.Series:
    """Daily cash: net deposits + cumulative trade cash flow (the ledger alone, no prices)."""
    from sqlalchemy import text
    t = txns.copy()
    t["BusinessDate"] = pd.to_datetime(t["BusinessDate"])
    first = min(t["BusinessDate"].min().normalize(), pd.Timestamp(start).normalize())
    idx = pd.date_range(first, pd.Timestamp(end).normalize(), freq="D")
    noncash = _noncash(t)

    def _cf(r):
        amt = r.get("Amount")
        if amt is not None and amt == amt:
            return float(amt)
        mult = float(r.get("Multiplier") or (100 if str(r.get("SecurityType", "")).lower() == "option" else 1))
        return ((1 if str(r["Direction"]).upper() == "SELL" else -1)
                * float(r["Quantity"] or 0) * float(r["TransactionPrice"] or 0) * mult)

    cf = pd.Series(0.0, index=idx)
    if not noncash.empty:
        daily = pd.Series(noncash.apply(_cf, axis=1).values, index=noncash["BusinessDate"].dt.normalize().values)
        cf = daily.groupby(level=0).sum().reindex(idx, fill_value=0).cumsum()
    dep_s = pd.Series(0.0, index=idx)
    with require_db().connect() as conn:
        dep = pd.read_sql(text("""
            SELECT BusinessDate, Amount FROM portfolio.Balance
            WHERE AccountId = :aid AND BalanceType = 'Cash'
            ORDER BY BusinessDate ASC
        """), conn, params={"aid": account_id()})
    if not dep.empty:
        dep["BusinessDate"] = pd.to_datetime(dep["BusinessDate"])
        dep["Amount"] = pd.to_numeric(dep["Amount"], errors="coerce")
        dep_s = (dep.dropna().groupby("BusinessDate")["Amount"].last()
                 .reindex(idx, method="ffill").bfill().fillna(0.0))
    s = dep_s + cf
    return s[s.index >= pd.Timestamp(start)]


def equity(from_date: Optional[str], to_date: Optional[str]) -> dict:
    """Mark-to-market equity (the page's ``mtm_equity_series``: ledger + daily closes)
    and the cash line."""
    _o, _c, txns = load()
    end = _dt.date.fromisoformat(to_date) if to_date else _today()
    start = _dt.date.fromisoformat(from_date) if from_date else end - _dt.timedelta(days=30)
    if txns.empty:
        return {"series": [series(None, "equity"), series(None, "cash")], "from": start, "to": end}
    df = PD().mtm_equity_series(txns, start, end, account_id=account_id())
    eq = pd.Series(df["Amount"].values, index=pd.to_datetime(df["BusinessDate"])) if not df.empty else None
    cash = _cash_series(txns, start, end)
    return to_jsonable({"series": [series(eq, "equity"), series(cash, "cash")], "from": start, "to": end,
                        "method": "mark-to-market: net deposits + trade cash flow + holdings x daily close"})


# ── Runner ────────────────────────────────────────────────────────────────────

def state_dir() -> Path:
    """Where the paper runners publish state (``paper.views.STATE_DIR``)."""
    return Path(PD().STATE_DIR)


def runner(limit: int = 30) -> dict:
    """Runner sessions from every state directory the service reads: this checkout's
    ``paper_state`` and other checkouts' (read only) — a runner started elsewhere shows here too."""
    dirs = [Path(x) for x in PD().state_dirs()]
    d = dirs[0]
    sessions = []
    heartbeats: dict[str, dict] = {}
    files = []
    for sd in dirs:
        if not sd.is_dir():
            continue
        for hb in sd.glob("heartbeat_*.json"):
            try:
                h = json.loads(hb.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            slug = hb.stem[len("heartbeat_"):]
            if slug not in heartbeats or str(h.get("at") or "") > str(heartbeats[slug].get("at") or ""):
                heartbeats[slug] = h
        files += [f for f in sd.glob("*_????-??-??.json")
                  if not f.name.startswith("heartbeat_") and not f.name.startswith("broker_calls_")]
    files = sorted(files, key=lambda f: (f.stem.rsplit("_", 1)[-1], f.stat().st_mtime), reverse=True)[:limit]
    for f in files:
        slug, day = f.stem.rsplit("_", 1)
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            sessions.append({"strategy": slug, "date": day, "state": "unreadable", "detail": {"error": str(exc)}})
            continue
        session = st.get("state") or {}
        hb = heartbeats.get(slug) if (heartbeats.get(slug) or {}).get("day") == day else None
        if st.get("finished"):
            state = "finished"
        elif hb and hb.get("halted"):
            state = "halted"
        elif hb and hb.get("at"):
            try:
                age = (_dt.datetime.now() - _dt.datetime.fromisoformat(hb["at"])).total_seconds()
            except ValueError:
                age = None
            state = "running" if age is not None and age <= 120 else "stale"
        else:
            state = "saved"
        detail = {"provider": st.get("provider"), "finished": bool(st.get("finished")),
                  "written": st.get("written"),
                  "open_positions": len(session.get("positions") or []),
                  "fills": len(session.get("fills") or []), "trades": len(session.get("trades") or []),
                  "day_pnl": session.get("day_pnl"), "blocked_reason": session.get("blocked_reason"),
                  "heartbeat": hb}
        detail["state_dir"] = str(f.parent)
        sessions.append({"strategy": slug, "date": day, "state": state, "detail": detail})
    marks = {k: {"mark": v[0], "units": v[1], "source": v[2]} for k, v in PD().paper_runner_marks().items()}
    return to_jsonable({"sessions": sessions, "marks": marks, "state_dir": str(d), "state_dir_exists": d.is_dir(),
                        "state_dirs": [str(x) for x in dirs], "heartbeats": heartbeats})
