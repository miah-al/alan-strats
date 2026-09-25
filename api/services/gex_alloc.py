"""
api/services/gex_alloc.py — the GEX paper allocator: gex_positioning traded on the WHOLE paper account.

Two variants, each sized on the whole account's equity (together they can exceed 1x — paper allows it; the
paper order engine has no buying-power check, so nothing is shrunk), each in the ledger under its own
strategy name:

  gex_positioning:vix   the backtest's logic exactly: VIX -> five regimes -> 90 / 80 / 60 / 35 / 15 % SPY,
                        a 3-day confirmation and a 5-day cooldown (the strategy's own parameters and
                        ``_classify_vix``). Its streak / confirmed regime / held regime / days since the last
                        change persist in app.GexAllocState; the first run seeds them by replaying the rules
                        over the stored VIX closes (about two years, on SPY's trading days, carried forward as
                        the backtest does), so day 1 holds what the backtest would hold. Each run applies one
                        day: today's VIX at ~15:50 ET stands in for the close.
  gex_positioning:gex   the strategy's ``generate_signal`` on SPY's live net GEX in $B per 1% move
                        (``net_gex_billions`` = /api/market/gex/SPY?source=hub's net_gex / 1e9 — the units
                        ``_classify_gex`` expects), no confirmation (the author's live mode).

Once per armed trading day (api/services/arms.py, 15:50 ET): target shares = floor(weight x account equity /
SPY price). If |target - current| is worth at least 1% of equity, it rebalances with paper market orders
through the service's own order book: a buy opens a new lot; a reduction closes whole lots, oldest first,
only lots held at least one night (the account's ETF rule), then buys back any remainder. One decision per
variant per day (app.GexAllocLog is unique on variant + day; the order ids are idempotent).
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import math
import os
import sys
import threading
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger("alan_trader.api.gex_alloc")

NY = "America/New_York"
SLUG = "gex_positioning"
VARIANTS = ("vix", "gex")
LEDGER = {"vix": "gex_positioning:vix", "gex": "gex_positioning:gex"}
UNDERLYING = "SPY"
MIN_TRADE_FRAC = 0.01
SEED_DAYS = 730


def min_hold_nights() -> int:
    try:
        return max(0, int(os.environ.get("ALAN_TRADER_GEX_ALLOC_MIN_NIGHTS", "1")))
    except ValueError:
        return 1


# ── the strategy (read only) ─────────────────────────────────────────────────

def strategy():
    """A fresh gex_positioning instance with its default parameters (imported read only from the plugin)."""
    from alan_trader.strategy_api import registry as R
    return R.get_strategy(SLUG)


def _module(s):
    return sys.modules[type(s).__module__]


def vix_regime(s, vix: float) -> str:
    return _module(s)._classify_vix(float(vix), s.vix_low, s.vix_mid_low, s.vix_mid_high, s.vix_high)


def weight_of(s, regime: str) -> float:
    return float(_module(s)._ALLOC[regime])


def label_of(s, regime: str) -> str:
    return str(getattr(_module(s), "_REGIME_LABEL", {}).get(regime, regime))


# ── the VIX variant's state machine: the backtest's loop, one day at a time ───

def seed_state(s, raw: str, day: _dt.date) -> dict:
    """The backtest's first day: confirmed = the raw regime, held = Neutral, ready to switch."""
    return {"prev_raw": raw, "streak": 1, "confirmed": raw, "held": "Neutral", "days_since": int(s.cooldown_days),
            "asof": day.isoformat()}


def step(state: dict, s, raw: str, day: _dt.date) -> tuple[dict, bool]:
    """One more day (the backtest's loop body for i > 0). Returns (new state, whether the held regime changed)."""
    st = dict(state)
    st["streak"] = st["streak"] + 1 if raw == st["prev_raw"] else 1
    st["confirmed"] = raw if st["streak"] >= int(s.confirm_days) else st["confirmed"]
    st["prev_raw"] = raw
    st["days_since"] = int(st["days_since"]) + 1
    changed = False
    if st["confirmed"] != st["held"] and st["days_since"] >= int(s.cooldown_days):
        st["held"], st["days_since"], changed = st["confirmed"], 0, True
    st["asof"] = day.isoformat()
    return st, changed


def replay(s, vix: pd.Series, state: Optional[dict] = None) -> tuple[dict, list[dict]]:
    """Apply the days of ``vix`` (date -> close, ascending) to ``state`` (None: seed on the first day).
    Returns the final state and each day's path (date, raw, confirmed, held, weight)."""
    path = []
    for d, v in vix.items():
        day = pd.Timestamp(d).date()
        raw = vix_regime(s, v)
        if state is None:
            state = seed_state(s, raw, day)
        else:
            state, _ = step(state, s, raw, day)
        path.append({"date": day, "vix": float(v), "raw": raw, "confirmed": state["confirmed"], "held": state["held"],
                     "weight": weight_of(s, state["held"])})
    return state, path


def aligned_vix(dates: list, vix: pd.Series) -> pd.Series:
    """VIX closes on the given trading days, carried forward, 20 where there is none (as the backtest)."""
    idx = pd.to_datetime(pd.Index(dates))
    v = pd.Series(vix.values, index=pd.to_datetime(vix.index)).sort_index()
    v = v[~v.index.duplicated(keep="last")]
    return v.reindex(idx).ffill().fillna(20.0)


# ── sizing and the rebalance plan (pure) ─────────────────────────────────────

def target_shares(weight: float, equity: float, price: float) -> int:
    if not (price and price > 0 and equity and equity > 0):
        return 0
    return max(0, int(math.floor(weight * equity / price)))


def plan(target: int, lots: list[dict], today: _dt.date, price: float, equity: float,
         min_frac: float = MIN_TRADE_FRAC, min_nights: int = 1) -> dict:
    """lots: [{"trade_group_id", "shares", "opened": date}] (long SPY lots of one variant). Returns
    {"action": hold|rebalance, "current", "target", "close": [lots], "buy": shares, "reason"}."""
    current = int(sum(int(l["shares"]) for l in lots))
    diff = target - current
    out = {"action": "hold", "current": current, "target": target, "close": [], "buy": 0, "reason": ""}
    if abs(diff) * float(price) < min_frac * float(equity):
        out["reason"] = (f"|target - current| = {abs(diff)} shares (${abs(diff) * price:,.0f}) is under "
                         f"{min_frac:.0%} of equity (${min_frac * equity:,.0f})")
        return out
    if diff > 0:
        out.update(action="rebalance", buy=diff, reason=f"buy {diff}")
        return out
    closable = sorted((l for l in lots if (today - l["opened"]).days >= min_nights), key=lambda l: (l["opened"],
                                                                                                    l["trade_group_id"]))
    after, close = current, []
    for l in closable:
        if after <= target:
            break
        close.append(l)
        after -= int(l["shares"])
    if not close:
        out["reason"] = (f"reduce by {-diff}: every lot was opened less than {min_nights} night(s) ago "
                         f"(the account's ETF holding rule)")
        return out
    buy = max(target - after, 0)
    out.update(action="rebalance", close=close, buy=buy,
               reason=f"close {len(close)} lot(s) ({current - after} shares)" + (f", buy back {buy}" if buy else ""))
    return out


# ── the store ─────────────────────────────────────────────────────────────────

class MemoryAllocStore:
    def __init__(self):
        self.states: dict[str, dict] = {}
        self.logs: list[dict] = []
        self._lock = threading.Lock()

    def get_state(self, variant: str) -> Optional[dict]:
        with self._lock:
            s = self.states.get(variant)
            return dict(s) if s else None

    def put_state(self, variant: str, state: dict) -> None:
        with self._lock:
            self.states[variant] = dict(state)

    def decided(self, variant: str, day: _dt.date) -> Optional[dict]:
        with self._lock:
            return next((dict(r) for r in self.logs if r["variant"] == variant and r["date"] == day), None)

    def add_log(self, row: dict) -> bool:
        with self._lock:
            if any(r["variant"] == row["variant"] and r["date"] == row["date"] for r in self.logs):
                return False
            self.logs.append(dict(row, decided_at=_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)))
            return True

    def recent(self, since: _dt.date) -> list[dict]:
        with self._lock:
            return sorted((dict(r) for r in self.logs if r["date"] >= since),
                          key=lambda r: (-r["date"].toordinal(), r["variant"]))      # as the table: newest, then A-Z


class DbAllocStore:
    def _eng(self):
        from api.services.db import require_db
        return require_db()

    def get_state(self, variant: str) -> Optional[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("GexAllocState"):
            return None
        with self._eng().connect() as c:
            r = c.execute(text("SELECT StateJson FROM app.GexAllocState WHERE Variant = :v"), {"v": variant}).fetchone()
        return json.loads(r[0]) if r else None

    def put_state(self, variant: str, state: dict) -> None:
        from sqlalchemy import text
        from api.services import appdb
        appdb.ensure("GexAllocState")
        body = json.dumps(state, default=str)
        asof = state.get("asof")
        with self._eng().begin() as c:
            n = c.execute(text("UPDATE app.GexAllocState SET StateJson = :j, AsOf = :d, UpdatedAt = SYSUTCDATETIME() "
                               "WHERE Variant = :v"), {"j": body, "d": asof, "v": variant}).rowcount
            if not n:
                c.execute(text("INSERT INTO app.GexAllocState (Variant, AsOf, StateJson) VALUES (:v, :d, :j)"),
                          {"v": variant, "d": asof, "j": body})

    _COLS = ("Variant", "TradeDate", "Status", "Regime", "Weight", "Equity", "Price", "CurrentShares", "TargetShares",
             "DetailJson", "DecidedAt")

    def _row(self, r) -> dict:
        d = dict(zip(("variant", "date", "status", "regime", "weight", "equity", "price", "current", "target",
                      "detail", "decided_at"), r))
        d["detail"] = json.loads(d["detail"]) if d["detail"] else {}
        if isinstance(d["date"], _dt.datetime):
            d["date"] = d["date"].date()
        return d

    def decided(self, variant: str, day: _dt.date) -> Optional[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("GexAllocLog"):
            return None
        with self._eng().connect() as c:
            r = c.execute(text(f"SELECT {', '.join(self._COLS)} FROM app.GexAllocLog WHERE Variant = :v AND "
                               f"TradeDate = :d"), {"v": variant, "d": day}).fetchone()
        return self._row(r) if r else None

    def add_log(self, row: dict) -> bool:
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        from api.services import appdb
        appdb.ensure("GexAllocLog")
        try:
            with self._eng().begin() as c:
                c.execute(text("INSERT INTO app.GexAllocLog (Variant, TradeDate, Status, Regime, Weight, Equity, Price, "
                               "CurrentShares, TargetShares, DetailJson) VALUES (:v, :d, :st, :rg, :w, :eq, :px, :cur, "
                               ":tgt, :det)"),
                          {"v": row["variant"], "d": row["date"], "st": row["status"], "rg": row.get("regime"),
                           "w": row.get("weight"), "eq": row.get("equity"), "px": row.get("price"),
                           "cur": row.get("current"), "tgt": row.get("target"),
                           "det": json.dumps(row.get("detail") or {}, default=str)})
            return True
        except IntegrityError:
            return False

    def recent(self, since: _dt.date) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("GexAllocLog"):
            return []
        with self._eng().connect() as c:
            rows = c.execute(text(f"SELECT {', '.join(self._COLS)} FROM app.GexAllocLog WHERE TradeDate >= :d "
                                  f"ORDER BY TradeDate DESC, Variant"), {"d": since}).fetchall()
        return [self._row(r) for r in rows]


def make_store():
    from api.services.arms import enabled_store
    m = enabled_store()
    return MemoryAllocStore() if m == "memory" else (None if m == "off" else DbAllocStore())


# ── the live inputs (each replaceable in tests) ──────────────────────────────

class LiveInputs:
    def __init__(self, hub):
        self.hub = hub

    def vix_now(self) -> tuple[Optional[float], str]:
        """VIX now: the market-data hub's index level, else yfinance's ^VIX."""
        if self.hub is not None and getattr(self.hub, "providers", None):
            try:
                px = self.hub.price("VIX", wait=3.0)
                if px:
                    return float(px), "hub"
            except Exception as exc:  # noqa: BLE001
                logger.info("hub VIX unavailable: %s", exc)
        try:
            from data.stock_data import yf_stock_price
            px = yf_stock_price("^VIX")
            if px:
                return float(px), "yfinance"
        except Exception as exc:  # noqa: BLE001
            logger.info("yfinance VIX unavailable: %s", exc)
        return None, "none"

    def spy_price(self) -> Optional[float]:
        from api.services import market as M
        return M.gex_spot(UNDERLYING, self.hub)

    def spy_net_gex(self) -> tuple[Optional[float], str]:
        from api.marketdata.limits import patience
        from api.services import market as M
        with patience(120.0):
            g = M.gex(UNDERLYING, "hub", hub=self.hub)
        return (float(g["net_gex"]) if g.get("net_gex") is not None else None), str(g.get("source") or "")

    def vix_history(self, until: _dt.date, days: int = SEED_DAYS) -> tuple[pd.Series, dict]:
        """(VIX closes on SPY's stored trading days up to ``until``, notes). The stored closes (mkt.VixBar, topped up
        from CBOE first when behind); days CBOE has not published yet come from yfinance's ^VIX; a day neither has
        is carried forward, as the backtest does."""
        from api.marketdata.limits import patience
        from api.services.db import require_db
        from db.client import get_price_bars, get_vix_bars
        eng = require_db()
        start = until - _dt.timedelta(days=days)
        v = get_vix_bars(eng, start, until)
        last = pd.Timestamp(v.index.max()).date() if v is not None and len(v) else None
        if last is None or last < until:
            try:
                from db.sync_jobs import run_sync
                with patience(60.0):
                    run_sync("vix", None, (last or start), until)
                v = get_vix_bars(eng, start, until)
            except Exception as exc:  # noqa: BLE001 — carried forward, as the backtest does
                logger.info("VIX top-up failed: %s", exc)
        try:
            from api.services.bars_topup import top_up
            top_up(UNDERLYING, until)
        except Exception as exc:  # noqa: BLE001
            logger.info("SPY daily bars not topped up: %s", exc)
        bars = get_price_bars(eng, UNDERLYING, start, until)
        dates = list(pd.to_datetime(bars["date"])) if bars is not None and not bars.empty else list(pd.to_datetime(v.index))
        closes = pd.Series(pd.to_numeric(v["close"], errors="coerce").values, index=pd.to_datetime(v.index))             if v is not None and len(v) else pd.Series(dtype=float)
        notes: dict = {"stored_vix_to": str(closes.index.max().date()) if len(closes) else None}
        missing = [d for d in dates if not len(closes) or d > closes.index.max()]
        if missing:
            try:
                import yfinance as yf
                h = yf.Ticker("^VIX").history(start=missing[0].date().isoformat(),
                                              end=(until + _dt.timedelta(days=1)).isoformat(), auto_adjust=False)
                got = {pd.Timestamp(pd.Timestamp(i).date()): float(c) for i, c in h["Close"].items()}
                add = {d: got[d] for d in missing if d in got}
                if add:
                    closes = pd.concat([closes, pd.Series(add)]).sort_index()
                    notes["vix_from_yfinance"] = {str(d.date()): round(x, 2) for d, x in add.items()}
            except Exception as exc:  # noqa: BLE001 — carried forward instead
                notes["vix_yfinance_error"] = f"{type(exc).__name__}: {exc}"[:200]
            left = [str(d.date()) for d in missing if d not in closes.index]
            if left:
                notes["vix_carried_forward"] = left
        return aligned_vix(dates, closes), notes

    def equity(self) -> float:
        from api.services import paper as P
        return float(P.summary(hub=self.hub)["equity"])

    def lots(self, ledger_name: str) -> list[dict]:
        """The variant's open long SPY lots: [{"trade_group_id", "shares", "opened"}]."""
        from api.services import paper as P
        open_groups, _closed, _t = P.load()
        out = []
        for tgid, grp in (open_groups or {}).items():
            if grp.empty or str(grp["StrategyName"].iloc[0]) != ledger_name:
                continue
            g = grp[grp["SecurityType"].astype(str).str.lower() == "stock"]
            g = g[g["Symbol"].astype(str).str.upper() == UNDERLYING]
            if g.empty:
                continue
            q = sum(abs(float(r["Quantity"] or 0)) * (1 if str(r["Direction"]).upper().startswith("B") else -1)
                    for _, r in g.iterrows())
            if round(q) <= 0:
                continue
            out.append({"trade_group_id": str(tgid), "shares": int(round(q)),
                        "opened": pd.Timestamp(g["BusinessDate"].min()).date()})
        return out


# ── the allocator ─────────────────────────────────────────────────────────────

class GexAllocator:
    def __init__(self, hub, orders, publish: Optional[Callable[[dict], None]] = None, store=None, inputs=None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None):
        self.orders = orders
        self.publish = publish
        self.store = store if store is not None else make_store()
        self.inputs = inputs or LiveInputs(hub)
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self._lock = threading.Lock()

    # ── the VIX variant's regime today ───────────────────────────────────────
    def _vix_decision(self, s, day: _dt.date) -> tuple[str, float, dict]:
        from api.services.gex_recorder import previous_trading_day
        prev = previous_trading_day(day)
        state = self.store.get_state("vix")
        detail: dict = {}
        if state is None or _dt.date.fromisoformat(state["asof"]) < prev:
            hist = self.inputs.vix_history(prev)
            if isinstance(hist, tuple):
                hist, notes = hist
                detail["vix_history"] = notes
            if state is not None:
                hist = hist[pd.to_datetime(hist.index).date > _dt.date.fromisoformat(state["asof"])]
                detail["caught_up"] = [str(pd.Timestamp(d).date()) for d in hist.index]
            else:
                detail["seeded"] = {"from": str(pd.Timestamp(hist.index.min()).date()) if len(hist) else None,
                                    "to": str(pd.Timestamp(hist.index.max()).date()) if len(hist) else None,
                                    "days": int(len(hist))}
            state, _ = replay(s, hist, state)
            if state is None:
                raise LookupError("no stored VIX closes to seed the VIX variant from")
        elif _dt.date.fromisoformat(state["asof"]) >= day:
            raise RuntimeError(f"the VIX variant's state is already at {state['asof']}")
        vix, src = self.inputs.vix_now()
        if vix is None:
            raise LookupError("no VIX level now (hub and yfinance both unavailable)")
        raw = vix_regime(s, vix)
        before = dict(state)
        state, changed = step(state, s, raw, day)
        detail.update(vix=vix, vix_source=src, raw_regime=raw, confirmed=state["confirmed"], streak=state["streak"],
                      days_since_change=state["days_since"], held_before=before["held"], regime_changed=changed,
                      confirm_days=int(s.confirm_days), cooldown_days=int(s.cooldown_days))
        self.store.put_state("vix", state)
        return state["held"], weight_of(s, state["held"]), detail

    def _gex_decision(self, s, day: _dt.date) -> tuple[str, float, dict]:
        net, src = self.inputs.spy_net_gex()
        if net is None:
            raise LookupError("no live SPY net GEX")
        vix, vsrc = self.inputs.vix_now()
        net_b = net / 1e9                                    # $ per 1% move -> $B, what _classify_gex expects
        sig = s.generate_signal({"net_gex_billions": net_b, "vix": vix if vix is not None else 20.0})
        md = sig.metadata or {}
        state = {"regime": md.get("regime"), "weight": md.get("spy_weight"), "net_gex_billions": net_b,
                 "asof": day.isoformat()}
        self.store.put_state("gex", state)
        return str(md["regime"]), float(md["spy_weight"]), {"net_gex": net, "net_gex_billions": round(net_b, 4),
                                                           "gex_source": src, "vix": vix, "vix_source": vsrc,
                                                           "signal": sig.signal, "source": md.get("source"),
                                                           "thresholds_b": [s.gex_neg_thr * 2, s.gex_neg_thr,
                                                                            s.gex_pos_thr, s.gex_pos_thr * 2]}

    # ── one day's decision ───────────────────────────────────────────────────
    def run(self, variant: str, now: Optional[pd.Timestamp] = None) -> dict:
        if variant not in VARIANTS:
            raise ValueError(f"variant must be one of {', '.join(VARIANTS)}")
        if self.store is None:
            raise RuntimeError("the allocator's store is off (ALAN_TRADER_ARMS=off)")
        now = now or self.clock()
        day = now.date()
        with self._lock:
            prior = self.store.decided(variant, day)
            if prior is not None:
                return {"variant": variant, "date": day, "status": "already_decided", "summary":
                        f"{variant}: already decided today ({prior['status']})", "prior": prior}
            s = strategy()
            row = {"variant": variant, "date": day, "ledger_strategy": LEDGER[variant]}
            try:
                regime, w, detail = (self._vix_decision if variant == "vix" else self._gex_decision)(s, day)
                equity = self.inputs.equity()
                price = self.inputs.spy_price()
                if not price:
                    raise LookupError("no SPY price")
                lots = self.inputs.lots(LEDGER[variant])
                tgt = target_shares(w, equity, price)
                p = plan(tgt, lots, day, price, equity, MIN_TRADE_FRAC, min_hold_nights())
                row.update(regime=regime, regime_label=label_of(s, regime), weight=w, equity=round(equity, 2),
                           price=price, current=p["current"], target=tgt)
                orders = self._execute(variant, day, regime, w, p) if p["action"] == "rebalance" else []
                bad = [o for o in orders if o.get("status") != "filled"]
                status = "held" if p["action"] == "hold" else ("rebalanced" if not bad else "order_failed")
                detail.update(plan=p["reason"], lots=[{**l, "opened": str(l["opened"])} for l in lots],
                              orders=orders, min_trade=f"{MIN_TRADE_FRAC:.0%} of equity",
                              min_hold_nights=min_hold_nights())
                row.update(status=status, detail=detail)
                summary = (f"{variant}: {regime} {w:.0%} SPY -> target {tgt} shares (equity ${equity:,.0f}, SPY "
                           f"{price:.2f}); had {p['current']}: " + (p["reason"] if p["action"] == "hold" else
                           "; ".join(o["text"] for o in orders)))
                row["summary"] = summary
                other = next(v for v in VARIANTS if v != variant)
                try:
                    other_sh = sum(int(l["shares"]) for l in self.inputs.lots(LEDGER[other]))
                    detail["combined_exposure_x"] = round((tgt + other_sh) * price / equity, 3) if equity else None
                except Exception:  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001 — a failed decision is logged, never half-done silently
                logger.exception("GEX allocator %s failed", variant)
                row.update(status="failed", detail={"error": f"{type(exc).__name__}: {exc}"[:400]},
                           summary=f"{variant}: failed — {type(exc).__name__}: {exc}"[:400])
            self.store.add_log(row)
            self._emit(row)
            return row

    def _execute(self, variant: str, day: _dt.date, regime: str, w: float, p: dict) -> list[dict]:
        out = []
        tag = f"gexalloc-{variant}-{day.isoformat()}"
        for l in p["close"]:
            try:
                r = self.orders.close_position(l["trade_group_id"], {"order_type": "market",
                                                                     "client_order_id": f"{tag}-close-{l['trade_group_id']}"[:64]})
                out.append({"side": "sell", "quantity": l["shares"], "closes_trade_group_id": l["trade_group_id"],
                            "order_id": r.get("order_id"), "status": r.get("status"), "fill_price": r.get("fill_price"),
                            "message": r.get("message"),
                            "text": f"sold lot {l['trade_group_id']} ({l['shares']}) {r.get('status')}"})
            except Exception as exc:  # noqa: BLE001
                out.append({"side": "sell", "quantity": l["shares"], "closes_trade_group_id": l["trade_group_id"],
                            "status": "error", "message": f"{type(exc).__name__}: {exc}"[:300],
                            "text": f"sell of lot {l['trade_group_id']} failed: {exc}"})
        if p["buy"] > 0:
            body = {"account": "paper", "underlying": UNDERLYING, "order_type": "market", "tif": "day",
                    "legs": [{"type": "stock", "side": "buy", "quantity": int(p["buy"])}],
                    "strategy": LEDGER[variant], "label": f"GEX allocator {variant}: {regime} {w:.0%} SPY",
                    "client_order_id": f"{tag}-buy"}
            try:
                r = self.orders.place(body)
                out.append({"side": "buy", "quantity": int(p["buy"]), "order_id": r.get("order_id"),
                            "status": r.get("status"), "fill_price": r.get("fill_price"),
                            "trade_group_id": r.get("trade_group_id"), "message": r.get("message"),
                            "text": f"bought {p['buy']} {r.get('status')}"
                                    + (f" @ {r['fill_price']:.2f}" if r.get("fill_price") else "")})
            except Exception as exc:  # noqa: BLE001
                out.append({"side": "buy", "quantity": int(p["buy"]), "status": "error",
                            "message": f"{type(exc).__name__}: {exc}"[:300], "text": f"buy of {p['buy']} failed: {exc}"})
        return out

    def _emit(self, row: dict) -> None:
        from api.serialize import to_jsonable
        logger.info("GEX allocator %s %s: %s", row["variant"], row["date"], row.get("summary"))
        if self.publish is not None:
            try:
                self.publish(to_jsonable({"type": "gex_alloc", **{k: v for k, v in row.items() if k != "detail"},
                                          "orders": (row.get("detail") or {}).get("orders", [])}))
            except Exception:
                logger.debug("allocator event publish failed", exc_info=True)

    # ── reading ───────────────────────────────────────────────────────────────
    def status(self, variant: str) -> dict:
        state = self.store.get_state(variant) if self.store is not None else None
        try:
            lots = self.inputs.lots(LEDGER[variant])
            shares = sum(l["shares"] for l in lots)
        except Exception as exc:  # noqa: BLE001
            lots, shares = None, None
            logger.debug("allocator lots unavailable: %s", exc)
        last = None
        if self.store is not None:
            rec = self.store.recent(self.clock().date() - _dt.timedelta(days=14))
            last = next((r for r in rec if r["variant"] == variant), None)
        return {"variant": variant, "ledger_strategy": LEDGER[variant], "shares": shares, "lots": len(lots or []),
                "state": state, "last_decision": ({k: last.get(k) for k in ("date", "status", "regime", "weight",
                                                                             "current", "target")} if last else None)}

    def log(self, days: int = 30) -> dict:
        from api.serialize import table_from_rows, to_jsonable
        rows = self.store.recent(self.clock().date() - _dt.timedelta(days=int(days))) if self.store is not None else []
        flat = [{"date": r["date"], "variant": r["variant"], "status": r["status"], "regime": r.get("regime"),
                 "weight": r.get("weight"), "equity": r.get("equity"), "price": r.get("price"),
                 "current": r.get("current"), "target": r.get("target"),
                 "orders": "; ".join(o.get("text", "") for o in (r.get("detail") or {}).get("orders", [])),
                 "note": (r.get("detail") or {}).get("plan") or (r.get("detail") or {}).get("error")} for r in rows]
        table = table_from_rows(flat, field_order=["date", "variant", "status", "regime", "weight", "equity", "price",
                                                   "current", "target", "orders", "note"],
                                headers={"date": "Date", "variant": "Variant", "status": "Status", "regime": "Regime",
                                         "weight": "SPY Weight", "equity": "Equity", "price": "SPY", "current": "Had",
                                         "target": "Target", "orders": "Orders", "note": "Note"},
                                formats={"weight": "ratio", "equity": "money", "price": "price", "current": "int",
                                         "target": "int"},
                                types={"date": "date", "current": "integer", "target": "integer"})
        return to_jsonable({"strategy": SLUG, "days": int(days), "decisions": rows, "table": table})
