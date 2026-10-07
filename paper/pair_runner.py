"""The paper runner for a strategy that trades two indexes at once (2026-10-07: ndx_spx_ratio, NDXP call spreads against
SPXW put spreads). Paper only: nothing here can place an order.

A pair strategy declares itself in ``live_instrument()``: ``pair: True`` and ``legs`` = one entry per index
({"index": "NDX", "root": "NDXP"}, {"index": "SPX", "root": "SPXW"}). ``scripts.paper_runner`` hands such a strategy here.

- Quotes: one ``TastytradeProvider`` per index, each streaming its own index level and legs over DXLink (no REST budget;
  REST only for a leg the stream has not sent yet, or as the fallback when the stream drops).
- Bars: each index's 1-minute bars are built from the polls, as the single-index runner does; a late start backfills
  both from the broker's candle feed, as history only.
- The engine: ``on_bar(minute, {"NDX": close, "SPX": close}, quote_fn)`` once a minute, where
  ``quote_fn(index, kind, k_low, k_high)`` is that index's vertical (long terms) from the latest quotes; ``warm`` for
  backfilled bars.
- The ledger: a structure fill carries one entry per vertical; each is booked as its own position through
  ``record_structure_fill`` (the NDX call spread on NDX, the 4 SPX put spreads on SPX), so the Positions page shows the
  two spreads the way the trade is held at the broker.
- State and heartbeat: the same files and shapes as the single-index runner (paper_state/<slug>_<day>.json,
  heartbeat_<slug>.json), so the service's runner list, the marks and a restart all work unchanged.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Callable, Optional

from strategy_api import registry as R
from . import ledger as L
from .providers import Bar, LegQuote, now_et
from .runner import RunResult, SESSION_OPEN, STATE_DIR, PaperSession

logger = logging.getLogger("paper.pair_runner")

PAIR_UNTIL = dtime(15, 50)        # pair strategies are flat by their own flatten time (15:45 for ndx_spx_ratio)
MIN_POLL_S = 2                    # the quotes stream; REST is only the fallback, budgeted by the provider
QUOTE_MAX_AGE_S = 60.0            # a leg quote older than this is no quote
MAX_FILLS = 200                   # runaway guard (rest + cancel + open + close rows)
FETCH_FAILURES_TO_HALT = 12
FETCH_BACKOFF_MAX_S = 120

LOG_COLS = ["ts", "minute", "event", "direction", "ndx", "spx", "z", "px", "lots", "cash", "reason",
            "ndx_vertical", "ndx_qty", "ndx_px", "ndx_bid", "ndx_ask", "spx_vertical", "spx_qty", "spx_px", "spx_bid",
            "spx_ask", "positions"]


def _minute_of(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute


def leg_prices(px: float, legs) -> tuple[float, float]:
    """A vertical's price split into its two legs at their own mids, both shifted by half the gap so they still
    difference to ``px`` (paper.ledger._leg_prices' rule); (px, 0) without leg quotes."""
    try:
        (lb, la, *_), (sb, sa, *_) = legs
        lm, sm = (float(lb) + float(la)) / 2.0, (float(sb) + float(sa)) / 2.0
    except (TypeError, ValueError):
        return float(px), 0.0
    gap = (lm - sm) - float(px)
    lpx, spx_ = lm - gap / 2.0, sm + gap / 2.0
    if lpx <= 0 or spx_ < 0:
        return float(px), 0.0
    return round(lpx, 4), round(spx_, 4)


def vertical_subfill(f: dict, v: dict, commission_per_leg: float = L.COMMISSION_PER_LEG) -> dict:
    """One vertical of a pair fill as a ``record_structure_fill`` fill: its own price, contracts and cash (the cash
    of the fill's verticals adds up to the fill's)."""
    sign = 1 if f["direction"] == "long" else -1
    qty = int(v["qty"])
    opening = f["kind"] == "open"
    cash = (-sign * float(v["px"]) * L.MULT * qty - 2 * qty * commission_per_leg) if opening else (sign * float(v["px"]) * L.MULT * qty)
    cp = "C" if v["kind"] == "call" else "P"
    k_long, k_short = (v["kl"], v["kh"]) if v["kind"] == "call" else (v["kh"], v["kl"])
    lpx, spx_ = leg_prices(float(v["px"]), v.get("legs"))
    return dict(m=f["m"], kind=f["kind"], direction=f["direction"], struct=f"{str(v['index']).lower()}_{v['kind']}_vertical",
                px=float(v["px"]), lots=qty, cash=round(cash, 2), reason=f.get("reason", ""), kl=float(v["kl"]), kh=float(v["kh"]),
                legs=[[cp, float(k_long), 1, lpx], [cp, float(k_short), -1, spx_]], ndx=f.get("ndx"))


class PairSession:
    """Runs one pair strategy for one session against one live provider per index."""

    def __init__(self, slug: str, providers: dict, engine_db=None, *, write_ledger: bool = True,
                 log_dir: Optional[Path] = None, account_name: str = "Paper Account", params: Optional[dict] = None,
                 state_dir: Optional[Path] = None, starting_cash: Optional[float] = None, notify: bool = False):
        self.slug = slug
        self.providers = dict(providers)                     # index -> provider
        self.db = engine_db
        self.write_ledger = write_ledger and engine_db is not None
        self.strategy = R.get_strategy(slug)
        if params:
            self.strategy = type(self.strategy)(**{**self.strategy.get_params(), **params})
        inst = self.strategy.live_instrument() or {}
        self.legs = list(inst.get("legs") or [])
        self.indexes = [str(x["index"]).upper() for x in self.legs]
        missing = [i for i in self.indexes if i not in self.providers]
        if len(self.indexes) != 2 or missing:
            raise ValueError(f"{slug}: a pair strategy needs two indexes with a provider each (legs {self.indexes}, "
                             f"missing providers {missing})")
        self.underlying = self.indexes[0]
        self.account_id = L.ensure_paper_account(engine_db, account_name, starting_cash=starting_cash) if self.write_ledger else None
        folder = PaperSession._strategy_folder(slug)
        self.log_dir = Path(log_dir) if log_dir else (folder / "paper_log" if folder else STATE_DIR / "paper_log")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir = Path(state_dir) if state_dir else STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.notify = bool(notify)
        self.halted: Optional[str] = None
        self._tgids: dict[tuple, list] = {}
        self._written = 0
        self._quotes: dict[str, dict] = {i: {} for i in self.indexes}
        self._spot: dict[str, Optional[float]] = {i: None for i in self.indexes}
        self._last_close: dict[str, Optional[float]] = {i: None for i in self.indexes}
        self._now_fn: Callable[[], datetime] = now_et

    # ── borrowed from the single-index runner (they only use slug, state_dir, db, account_id, notify) ──
    def _alert(self, text: str) -> None:
        PaperSession._alert(self, text)                      # type: ignore[arg-type]

    def _other_runners_active(self, day: date) -> list:
        return PaperSession._other_runners_active(self, day)  # type: ignore[arg-type]

    def _record_day_balance(self, day: date, sleep_fn=time.sleep, wait_s: float = 600.0) -> None:
        PaperSession._record_day_balance(self, day, sleep_fn=sleep_fn, wait_s=wait_s)  # type: ignore[arg-type]

    # ── files ─────────────────────────────────────────────────────────────────
    def _state_path(self, day: date) -> Path:
        return self.state_dir / f"{self.slug}_{day.isoformat()}.json"

    def _log_path(self, day: date) -> Path:
        return self.log_dir / f"{day.isoformat()}.csv"

    def _log(self, day: date, row: dict) -> None:
        p = self._log_path(day)
        new = not p.exists()
        with p.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=LOG_COLS)
            if new:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in LOG_COLS})

    def _log_bar(self, day: date, ts: datetime, closes: dict, source: str, fresh: bool = False) -> None:
        try:
            p = self.log_dir / f"underlying_{day.isoformat()}.csv"
            new = fresh or not p.exists()
            with p.open("w" if fresh else "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["ts", *self.indexes, "source"])
                w.writerow([ts.strftime("%Y-%m-%d %H:%M"), *[("" if closes.get(i) is None else round(float(closes[i]), 2))
                                                              for i in self.indexes], source])
        except OSError:
            pass

    def _write_decisions(self, session, day: date) -> None:
        """Every decision bar's stretch and what was done (the data an AI on this strategy would learn from)."""
        try:
            rows = list(getattr(session, "decisions", []) or [])
            if not rows:
                return
            p = self.log_dir / f"decisions_{day.isoformat()}.csv"
            cols = sorted({k for r in rows for k in r})
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                for r in rows:
                    w.writerow(r)
        except OSError:
            pass

    def _save_state(self, session, day: date, finished: bool = False) -> None:
        try:
            st = session.to_dict()
            st.setdefault("day_pnl", round(float(session.day_pnl), 2))
            self._state_path(day).write_text(json.dumps({
                "state": st, "written": self._written,
                "tgids": {"|".join(map(str, k)): v for k, v in self._tgids.items()},
                "provider": self._provider_name(), "pair": self.indexes, "finished": finished}, default=str), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("state save failed: %s", exc)

    def _provider_name(self) -> str:
        names = {getattr(p, "name", "?") for p in self.providers.values()}
        return names.pop() if len(names) == 1 else "+".join(sorted(names))

    def _restore(self, day: date, blocked_reason: str):
        p = self._state_path(day)
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("finished"):
                logger.info("state for %s is a finished session; starting fresh", day); return None
            if d.get("provider") != self._provider_name():
                logger.info("state for %s came from provider %r; starting fresh", day, d.get("provider")); return None
            fresh = self.strategy.live_session(day, blocked_reason=blocked_reason)
            session = type(fresh).from_dict(self.strategy.params, d["state"])
            self._written = int(d.get("written", 0))
            self._tgids = {}
            for k, v in (d.get("tgids") or {}).items():
                parts = k.split("|")
                self._tgids[tuple(parts[:-2]) + (float(parts[-2]), float(parts[-1]))] = list(v)
            logger.info("resumed %s from %s: %d fills, %s open", day, p.name, len(session.fills),
                        "1 structure" if getattr(session, "open", None) else "nothing")
            return session
        except Exception as exc:  # noqa: BLE001
            logger.warning("state restore failed (%s); starting fresh", exc)
            return None

    # ── quotes ────────────────────────────────────────────────────────────────
    def _symbols(self, index: str, kind: str, k_low: float, k_high: float) -> list:
        return [s for s in self.providers[index].leg_symbols(kind, k_low, k_high) if s]

    def _watched(self, session) -> dict:
        """The legs of the open structure, by index (the pending entry's strikes are only known at its bar)."""
        out: dict = {i: [] for i in self.indexes}
        for pos in getattr(session, "positions", []) or []:
            idx = str(getattr(pos, "index", "")).upper()
            if idx in out:
                out[idx] += self._symbols(idx, pos.cp, pos.k_low, pos.k_high)
        return out

    def _fresh(self, lq: Optional[LegQuote], now: datetime) -> bool:
        if lq is None:
            return False
        ref = lq.updated or lq.last_time
        return ref is None or (now - ref).total_seconds() <= QUOTE_MAX_AGE_S

    def quote_fn(self, index: str, kind: str, k_low: float, k_high: float):
        """The vertical's two-sided quote (long terms) from the latest quotes of ``index``; a strike the engine has just
        chosen is fetched now. None when a leg is missing, stale, crossed or the quote is too wide."""
        index = str(index).upper()
        prov = self.providers.get(index)
        if prov is None:
            return None
        syms = self._symbols(index, kind, k_low, k_high)
        if len(syms) != 2:
            return None
        quotes = self._quotes[index]
        now = self._now_fn()
        if any(s not in quotes or not self._fresh(quotes.get(s), now) for s in syms):
            try:
                got = prov.fetch(syms)
                quotes.update(got)
                if index in got and got[index].last is not None:
                    self._spot[index] = float(got[index].last)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s quote fetch failed: %s", index, exc)
                return None
        if any(not self._fresh(quotes.get(s), now) for s in syms):
            return None
        return prov.quote_vertical(kind, k_low, k_high, quotes, now, 390)

    # ── fills ─────────────────────────────────────────────────────────────────
    def _write_new_fills(self, session, day: date) -> None:
        fills = session.fills
        while self._written < len(fills):
            f = fills[self._written]; self._written += 1
            ts = datetime.combine(day, dtime(0, 0)) + timedelta(minutes=int(f["m"]))
            vs = list(f.get("verticals") or [])
            row = dict(ts=str(ts), minute=f["m"], event=f["kind"], direction=f.get("direction", ""), ndx=f.get("ndx", ""),
                       spx=f.get("spx", ""), z=f.get("z", ""), px=(f.get("px") if f["kind"] in ("open", "close") else ""),
                       lots=f.get("lots", ""), cash=f.get("cash", ""), reason=f.get("reason", ""))
            for v in vs:
                pre = str(v["index"]).lower()
                if pre in ("ndx", "spx"):
                    row.update({f"{pre}_vertical": f"{v['kl']:.0f}/{v['kh']:.0f} {v['kind']}", f"{pre}_qty": v["qty"],
                                f"{pre}_px": v["px"], f"{pre}_bid": v.get("bid", ""), f"{pre}_ask": v.get("ask", "")})
            pids = []
            if f["kind"] in ("open", "close"):
                for v in vs:
                    pids.append(self._book(session, day, f, v))
                self._alert(f"{ts:%H:%M} {f['kind']} {f['direction']} ratio @ {float(f['px']):.2f} "
                            f"({str(f.get('reason', ''))[:160]}); day {session.day_pnl:+,.0f}")
            row["positions"] = "|".join(str(x) for x in pids if x is not None)
            self._log(day, row)
            logger.info("%s %s %s %s", ts.strftime("%H:%M"), f["kind"], f.get("direction", ""), str(f.get("reason", ""))[:200])

    def _book(self, session, day: date, f: dict, v: dict) -> Optional[int]:
        """One vertical of an open / close fill to the ledger as its own structure position; returns the position id."""
        index = str(v["index"]).upper()
        sub = vertical_subfill(f, v, getattr(getattr(self.strategy, "params", None), "commission_per_leg", L.COMMISSION_PER_LEG))
        key = (sub["struct"], sub["direction"], float(sub["kl"]), float(sub["kh"]))
        syms = self._symbols(index, v["kind"], v["kl"], v["kh"])
        if len(syms) != 2:
            syms = [f"{index}-{sub['legs'][0][1]:.0f}{sub['legs'][0][0]}", f"{index}-{sub['legs'][1][1]:.0f}{sub['legs'][1][0]}"]
        stack = self._tgids.setdefault(key, [])
        pid = stack[-1] if (sub["kind"] == "close" and stack) else None
        if not self.write_ledger:
            if sub["kind"] == "open":
                stack.append(-1); return -1
            if stack:
                stack.pop()
            return pid
        try:
            prov = self.providers[index]
            new_pid = L.record_structure_fill(self.db, self.account_id, self.slug, index, getattr(prov, "expiry", None) or day, day,
                                              sub, syms, position_id=pid,
                                              extra={"provider": getattr(prov, "name", "?"), "pair": "+".join(self.indexes),
                                                     "bid": v.get("bid"), "ask": v.get("ask"), "spx": f.get("spx")})
            if sub["kind"] == "open" and new_pid is not None:
                stack.append(int(new_pid)); return int(new_pid)
            if sub["kind"] == "close" and stack:
                stack.pop()
            return pid
        except Exception as exc:  # noqa: BLE001
            logger.error("ledger write failed (%s vertical): %s", index, exc)
            return None

    # ── the heartbeat ─────────────────────────────────────────────────────────
    def _heartbeat(self, day: date, now: datetime, session, note: str = "", marks: Optional[dict] = None) -> None:
        live_marks: dict = dict(marks or {})
        live_legs: dict = {}
        for pos in getattr(session, "positions", []) or []:
            try:
                key = f"{pos.direction}|{float(pos.k_low)}|{float(pos.k_high)}"
                if key not in live_marks and pos.last_mark is not None:
                    live_marks[key] = round(float(pos.last_mark), 2)
                idx = str(pos.index).upper()
                for s in self._symbols(idx, pos.cp, pos.k_low, pos.k_high):
                    lq = self._quotes[idx].get(s)
                    if lq is not None and lq.bid is not None and lq.ask is not None and lq.ask >= lq.bid:
                        live_legs[str(s)] = round((float(lq.bid) + float(lq.ask)) / 2.0, 2)
            except Exception:  # noqa: BLE001
                continue
        calls = 0
        for p in self.providers.values():
            calls += int(getattr(getattr(p, "budget", None), "calls_today", 0) or 0)
        try:
            hb = {"slug": self.slug, "day": str(day), "at": now.isoformat(timespec="seconds"), "provider": self._provider_name(),
                  "open_positions": len(getattr(session, "positions", []) or []), "fills": len(session.fills),
                  "trades": len(session.trades), "marked": round(float(session.marked()), 0), "day_pnl": round(float(session.day_pnl), 0),
                  "halted": self.halted or "", "note": note, "live_marks": live_marks, "live_legs": live_legs,
                  "spot": self._spot.get(self.underlying), "underlying": self.underlying, "pair": self.indexes,
                  "spots": dict(self._spot), "marks_at": now.isoformat(timespec="seconds") if live_marks else "",
                  "api_calls_today": calls}
            (self.state_dir / f"heartbeat_{self.slug}.json").write_text(json.dumps(hb, default=str), encoding="utf-8")
        except OSError:
            pass

    # ── the session ───────────────────────────────────────────────────────────
    def _gate(self, day: date) -> tuple[bool, str]:
        try:
            return self.strategy.session_gate(day)
        except Exception as exc:  # noqa: BLE001
            return True, f"gate error: {exc}"

    def _backfill(self, session, day: date, until: datetime) -> int:
        """A late start: both indexes' earlier bars from the broker's candle feed, as history only (``warm``)."""
        series: dict = {}
        for idx, prov in self.providers.items():
            if not hasattr(prov, "backfill_bars"):
                return 0
            series[idx] = {b.ts: float(b.close) for b in (prov.backfill_bars(day, until) or [])}
        if any(not s for s in series.values()):
            return 0
        stamps = sorted(set().union(*[set(s) for s in series.values()]))
        last: dict = {}
        n = 0
        for i, ts in enumerate(stamps):
            for idx in self.indexes:
                if ts in series[idx]:
                    last[idx] = series[idx][ts]
            if len(last) < len(self.indexes):
                continue
            session.warm(_minute_of(ts) + 1, dict(last))
            self._log_bar(day, ts, last, "broker candles", fresh=(n == 0))
            n += 1
        for idx in self.indexes:
            self._last_close[idx] = last.get(idx)
        return n

    def run_live(self, day: Optional[date] = None, poll_seconds: Optional[int] = None, until: dtime = PAIR_UNTIL,
                 now_fn: Callable[[], datetime] = now_et, sleep_fn: Callable[[float], None] = time.sleep) -> RunResult:
        self._now_fn = now_fn
        poll = max(MIN_POLL_S, int(poll_seconds or 5))
        day = day or now_fn().date()
        blocked, why = self._gate(day)
        n_chain = {}
        for idx, prov in self.providers.items():
            n_chain[idx] = 0
            for attempt in range(3):
                try:
                    n_chain[idx] = prov.load_chain(day); break
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s chain load failed (%d/3): %s", idx, attempt + 1, exc); sleep_fn(20)
        if not blocked and any(n == 0 for n in n_chain.values()):
            blocked, why = True, "no same-day chain: " + ", ".join(f"{i} {n}" for i, n in n_chain.items())
        logger.info("%s %s: gate %s; chains %s", self.slug, day, (f"BLOCKED ({why})" if blocked else "open"), n_chain)
        self._alert(f"{day} gate {'BLOCKED: ' + why if blocked else 'open'}; chains {n_chain}")
        try:
            logger.info("%s %s: params %s", self.slug, day, json.dumps(self.strategy.params.as_dict(), default=str, sort_keys=True))
        except Exception:  # noqa: BLE001
            pass
        if self.write_ledger:
            try:
                L.record_session(self.db, day, self.underlying, self.slug, blocked, why,
                                 note=f"live pair {'+'.join(self.indexes)}, chains {n_chain}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("session row not written: %s", exc)
        res = RunResult(day, self.slug, self._provider_name(), blocked, why)
        session = self._restore(day, why) or self.strategy.live_session(day, blocked_reason=why)
        if blocked:
            self._save_state(session, day, finished=True)
            self._heartbeat(day, now_fn(), session, f"blocked: {why}")
            return res
        start = now_fn()
        if start.time() > SESSION_OPEN:
            n = self._backfill(session, day, start.replace(second=0, microsecond=0))
            if n:
                logger.info("late start %s: %d backfilled bars of %s", start.strftime("%H:%M"), n, "+".join(self.indexes))
        cur_minute: Optional[datetime] = None
        failures = 0
        n_bars = 0
        while True:
            now = now_fn()
            if now.time() >= until:
                break
            if now.time() < SESSION_OPEN:
                self._heartbeat(day, now, session, "waiting for the open")
                sleep_fn(min(30, poll)); continue
            ok = True
            watched = self._watched(session)
            for idx, prov in self.providers.items():
                try:
                    got = prov.fetch(watched.get(idx, []))
                    self._quotes[idx].update(got)
                    q = got.get(idx)
                    if q is not None and q.last is not None:
                        self._spot[idx] = float(q.last)
                    prov.sample_underlying(got, now)
                except Exception as exc:  # noqa: BLE001
                    ok = False
                    logger.warning("%s fetch failed: %s", idx, exc)
            if not ok:
                failures += 1
                if failures >= FETCH_FAILURES_TO_HALT:
                    self.halted = f"quote feed halted after {failures} failed polls"
                    logger.error(self.halted); self._alert(self.halted)
                    break
                wait = min(FETCH_BACKOFF_MAX_S, poll * (2 ** min(failures - 1, 5)))
                self._heartbeat(day, now, session, f"fetch failing ({failures}), next try in {wait}s")
                sleep_fn(wait); continue
            failures = 0
            # marks between bars, from this poll's quotes (display only; the engine marks and decides on bars)
            marks: dict = {}
            for pos in getattr(session, "positions", []) or []:
                try:
                    q = self.quote_fn(pos.index, pos.cp, pos.k_low, pos.k_high)
                    if q is not None:
                        marks[f"{pos.direction}|{float(pos.k_low)}|{float(pos.k_high)}"] = round(float(q.last), 2)
                except Exception:  # noqa: BLE001
                    pass
            self._heartbeat(day, now, session, marks=marks)
            this_minute = now.replace(second=0, microsecond=0)
            if cur_minute is None:
                cur_minute = this_minute
            if this_minute > cur_minute:
                bars = {idx: prov.close_minute(cur_minute) for idx, prov in self.providers.items()}
                closes = {}
                for idx in self.indexes:
                    b = bars.get(idx)
                    if b is not None:
                        self._last_close[idx] = float(b.close)
                    closes[idx] = self._last_close.get(idx)
                if all(v is not None for v in closes.values()) and any(b is not None for b in bars.values()):
                    minute = _minute_of(cur_minute) + 1
                    self._log_bar(day, cur_minute, closes, "polled")
                    try:
                        session.on_bar(minute, closes, self.quote_fn)
                    except Exception as exc:  # noqa: BLE001
                        self.halted = f"engine error at {cur_minute:%H:%M}: {exc}"
                        logger.exception("engine error; halting the session"); self._alert(self.halted)
                        break
                    n_bars += 1
                    self._write_new_fills(session, day)
                    self._save_state(session, day)
                    if len(session.fills) > MAX_FILLS:
                        self.halted = f"runaway guard: {len(session.fills)} fills"
                        logger.error(self.halted); self._alert(self.halted)
                        break
                    if n_bars % 15 == 0:
                        logger.info("%s bar %s NDX/SPX %s | open %s | day %+.0f | fills %d", day, cur_minute.strftime("%H:%M"),
                                    closes, "yes" if getattr(session, "open", None) else "no", session.day_pnl, len(session.fills))
                cur_minute = this_minute
            sleep_fn(poll)
        # anything still open (a halt, a late restart): closed at the last marks, never carried overnight
        if getattr(session, "positions", None):
            try:
                minute = max(_minute_of(now_fn()) + 1, int(getattr(session, "last_minute", 0) or 0) + 1)
                closes = {i: (self._last_close.get(i) or self._spot.get(i)) for i in self.indexes}
                if all(v is not None for v in closes.values()):
                    session.on_bar(minute, closes, self.quote_fn, is_last=True)
                    self._write_new_fills(session, day)
            except Exception as exc:  # noqa: BLE001
                logger.exception("closing the open structure at the end failed: %s", exc)
                self._alert(f"{day}: the open structure could not be closed at the end ({exc}); check the ledger")
        self._write_decisions(session, day)
        self._save_state(session, day, finished=True)
        self._heartbeat(day, now_fn(), session, "finished")
        res.trades, res.fills, res.day_pnl, res.bars = session.trades, session.fills, session.day_pnl, n_bars
        res.n_fills_written, res.log_path, res.state_path = self._written, str(self._log_path(day)), str(self._state_path(day))
        if self.write_ledger:
            try:
                self._record_day_balance(day, sleep_fn=sleep_fn)
            except Exception as exc:  # noqa: BLE001
                logger.warning("day balance not written: %s", exc)
        logger.info("session done: %d bars, %d trades, day P&L %+.0f%s", n_bars, len(session.trades), session.day_pnl,
                    (f"; HALTED: {self.halted}" if self.halted else ""))
        self._alert(f"{day} done: {len(session.trades)} trades, day P&L {session.day_pnl:+,.0f}"
                    + (f"; HALTED: {self.halted}" if self.halted else ""))
        res.reason = res.reason or (self.halted or "")
        return res


def check(strategy, providers: dict, day: date) -> int:
    """--check for a pair strategy: both chains, both index levels and the two verticals it would trade now (read-only)."""
    from .providers import now_et as _now
    ok = True
    spots = {}
    for idx, prov in providers.items():
        n = prov.load_chain(day)
        print(f"tastytrade session ok; {n} {prov.root} contracts expiring {day}")
        ok = ok and n > 0
        q = prov.fetch([]).get(idx)
        spots[idx] = float(q.last) if q is not None and q.last is not None else None
        print(f"  {idx}: {spots[idx]}")
    if all(v is not None for v in spots.values()) and hasattr(strategy, "check_structures"):
        args = [spots[str(x["index"]).upper()] for x in (strategy.live_instrument().get("legs") or [])]
        for idx, kind, kl, kh, label in strategy.check_structures(*args):
            prov = providers[idx]
            syms = [s for s in prov.leg_symbols(kind, kl, kh) if s]
            qs = prov.fetch(syms) if len(syms) == 2 else {}
            v = prov.quote_vertical(kind, kl, kh, qs, _now(), 390) if len(syms) == 2 else None
            print(f"  {label}: " + (f"bid {v.bid:.2f} ask {v.ask:.2f} mid {v.last:.2f}" if v else "no two-sided quote"))
    return 0 if ok else 1


def main_pair(args, strategy, inst: dict, params: dict, engine, starting_cash) -> int:
    """``scripts.paper_runner`` for a pair strategy (live and --check; there is no replay of two indexes)."""
    from .providers import TastytradeProvider
    if getattr(args, "replay", None):
        print(f"{args.strategy} is a pair strategy ({'+'.join(x['index'] for x in inst.get('legs') or [])}): the runner has "
              "no replay for two indexes; its research harness is in the strategy's folder")
        return 2
    providers = {}
    try:
        for leg in inst.get("legs") or []:
            idx = str(leg["index"]).upper()
            providers[idx] = TastytradeProvider(idx, str(leg["root"]).upper(), is_test=args.test_env,
                                                poll_seconds=args.poll, stream=not args.check)
    except RuntimeError as exc:
        print(f"cannot start: {exc}"); return 1
    if args.check:
        return check(strategy, providers, date.today())
    ps = PairSession(args.strategy, providers, engine, write_ledger=not args.no_ledger, params=params, notify=args.notify,
                     log_dir=(Path(args.log_dir) if args.log_dir else None), starting_cash=starting_cash)
    res = ps.run_live(poll_seconds=args.poll)
    print(f"\n{res.slug} {res.day} [{res.provider}] {'BLOCKED: ' + res.reason if res.blocked else 'traded'}")
    print(f"bars {res.bars}; fills {len(res.fills)} logged {res.n_fills_written}"
          f"{'; ledger updated' if ps.write_ledger else '; ledger untouched (dry run)'}; trades {len(res.trades)}; "
          f"day P&L {res.day_pnl:+,.0f}")
    for t in res.trades:
        print(f"  {t['entry_time']}-{t['exit_time']} {t['direction']:5s} {t.get('ndx_spread', '')} + {t.get('spx_spread', '')} "
              f"{t['entry_px']:.2f} -> {t['exit_px']:.2f} {t['exit_reason']:7s} {t['pnl']:+,.0f}")
    print(f"log: {res.log_path}\nstate: {res.state_path}")
    if ps.halted:
        print(f"HALTED: {ps.halted}")
        return 3
    return 0
