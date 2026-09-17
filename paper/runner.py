"""The paper-trading loop.

Every minute of the session the runner: builds the underlying's 1-minute bar, asks the strategy's
session engine to act on it (``on_bar``) with a quote function that answers from the provider,
writes any new fills to the portfolio ledger and to a CSV paper log in the strategy folder, and
saves the engine state so a restart resumes where it left off.

Two clocks: ``run_replay`` walks a stored session as fast as it can (tests, dry runs, the
reconciliation replay); ``run_live`` follows the wall clock with a real-time provider.
Strategy logic never lives here: the engine and the gate come from the plugin
(strategy_api.live).
"""
from __future__ import annotations

import csv
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Callable, Optional

from strategy_api.live import Quote
from strategy_api import registry as R
from .providers import ReplayProvider, TastytradeProvider, Bar, now_et
from . import ledger as L

logger = logging.getLogger("paper.runner")

SESSION_OPEN = dtime(9, 30)
SESSION_CLOSE_MIN = 16 * 60
STATE_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / "paper_state"
LOG_COLS = ["ts", "minute", "event", "ndx", "k_low", "k_high", "kind", "direction", "bid", "ask", "last", "age",
            "limit", "fill", "lots", "cash", "reason", "tgid", "long_symbol", "short_symbol", "note"]


def _minute_of(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute


@dataclass
class RunResult:
    day: date
    slug: str
    provider: str
    blocked: bool
    reason: str
    trades: list = field(default_factory=list)
    fills: list = field(default_factory=list)
    day_pnl: float = 0.0
    bars: int = 0
    n_fills_written: int = 0
    log_path: Optional[str] = None
    state_path: Optional[str] = None


class PaperSession:
    """Runs one strategy for one session against one provider."""

    def __init__(self, slug: str, provider, engine_db=None, *, write_ledger: bool = True, log_dir: Optional[Path] = None,
                 account_name: str = "Paper Account", params: Optional[dict] = None, state_dir: Optional[Path] = None):
        self.slug = slug
        self.provider = provider
        self.db = engine_db
        self.write_ledger = write_ledger and engine_db is not None
        self.strategy = R.get_strategy(slug)
        if params:
            self.strategy = type(self.strategy)(**{**self.strategy.get_params(), **params})
        inst = self.strategy.live_instrument() or {}
        self.underlying = str(inst.get("underlying", getattr(provider, "underlying", "NDX"))).upper()
        self.account_id = L.ensure_paper_account(engine_db, account_name) if self.write_ledger else None
        folder = self._strategy_folder(slug)
        self.log_dir = Path(log_dir) if log_dir else (folder / "paper_log" if folder else STATE_DIR / "paper_log")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir = Path(state_dir) if state_dir else STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._tgids: dict[tuple, list[str]] = {}
        self._written = 0
        self._last_quote: dict = {}
        self._day_bars: list = []
        self._features_logged = False

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _strategy_folder(slug: str) -> Optional[Path]:
        """The strategy's own folder in the plugin (where guide.md lives)."""
        try:
            g = R.find_guide(slug)
            if g:
                return Path(g).parent
            t = R.tests_dir_for(slug)
            if t:
                return Path(t).parent
        except Exception:
            pass
        return None

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

    def _unit_key(self, fill: dict) -> tuple:
        return (fill["direction"], fill["kl"], fill["kh"])

    def _position_id(self, fill: dict) -> Optional[int]:
        """The ledger PositionId of the unit a fill belongs to (units keyed by direction and strikes,
        oldest first when two share strikes). ``open`` has none yet; the ledger returns it."""
        stack = self._tgids.setdefault(self._unit_key(fill), [])
        if fill["kind"] == "open":
            return None
        if fill["kind"] == "close":
            return stack.pop(0) if stack else None
        return stack[-1] if stack else None

    def _write_new_fills(self, session, day: date, expiry: date, S: float, symbols_fn: Callable) -> None:
        fills = session.fills
        while self._written < len(fills):
            f = fills[self._written]; self._written += 1
            kind_cp = "call" if f["direction"] == "bull" else "put"
            ls, ss = symbols_fn(kind_cp, f["kl"], f["kh"])
            pid = self._position_id(f) if f["kind"] in ("open", "add", "close") else None
            tg = "" if pid is None else str(pid)
            q = self._last_quote.get((kind_cp, f["kl"], f["kh"]))
            row = dict(ts=str(datetime.combine(day, dtime(0, 0)) + timedelta(minutes=int(f["m"]))), minute=f["m"], event=f["kind"], ndx=round(S, 2),
                       k_low=f["kl"], k_high=f["kh"], kind=kind_cp, direction=f["direction"],
                       bid=(round(q.bid, 2) if q else ""), ask=(round(q.ask, 2) if q else ""), last=(round(q.last, 2) if q else ""), age=(q.age if q else ""),
                       limit=(f["px"] if f["kind"] in ("rest", "cancel") else ""), fill=(f["px"] if f["kind"] in ("open", "add", "close") else ""),
                       lots=f["lots"], cash=f["cash"], reason=f["reason"], tgid=tg, long_symbol=ls or "", short_symbol=ss or "", note="")
            self._log(day, row)
            logger.info("%s %s %s %s/%s @ %s (%s)", row["ts"][11:16], f["kind"], f["direction"], f["kl"], f["kh"], f["px"], f["reason"])
            if self.write_ledger and f["kind"] in ("open", "add", "close"):
                try:
                    new_pid = L.record_fill(self.db, self.account_id, self.slug, self.underlying, expiry, day, f,
                                            ls or f"{self.underlying}-{f['kl']:.0f}", ss or f"{self.underlying}-{f['kh']:.0f}", position_id=pid,
                                            extra={"provider": getattr(self.provider, "name", "?"), "bid": (q.bid if q else None), "ask": (q.ask if q else None), "last": (q.last if q else None)})
                    if f["kind"] == "open" and new_pid is not None:
                        self._tgids.setdefault(self._unit_key(f), []).append(int(new_pid))
                except Exception as exc:
                    logger.error("ledger write failed: %s", exc)
            elif f["kind"] == "open":                                   # no ledger: still track the unit
                self._tgids.setdefault(self._unit_key(f), []).append(-1)

    def _log_session_features(self, session, day: date, minute: int) -> None:
        """Once per session, at the strategy's first entry minute: the ex-ante features a gate model
        could use (prior VXN, overnight gap, prior-day move, morning range), written as a `features`
        row in the CSV log and appended to the session's ModelSignal note. The day's outcome is in
        the same log, so a shadow gate can be scored later without re-running anything."""
        if self._features_logged or not self._day_bars:
            return
        start_min = int(getattr(self.strategy.params, "entry_start_min", 11 * 60))
        if minute < start_min:
            return
        self._features_logged = True
        feats: dict = {"minute": minute}
        try:
            o = self._day_bars[0].open; hi = max(b.high for b in self._day_bars); lo = min(b.low for b in self._day_bars); last = self._day_bars[-1].close
            feats.update(am_range_pct=round((hi - lo) / last * 100, 3), am_move_pct=round((last / o - 1) * 100, 3), open=round(o, 2), level=round(last, 2))
            if self.db is not None:
                from db.client import get_price_bars
                from datetime import timedelta
                px = get_price_bars(self.db, self.underlying, day - timedelta(days=10), day - timedelta(days=1))
                if len(px) >= 2:
                    c1, c2 = float(px["close"].iloc[-1]), float(px["close"].iloc[-2])
                    feats.update(gap_pct=round((o / c1 - 1) * 100, 3), prev_day_pct=round((c1 / c2 - 1) * 100, 3), prev_close=round(c1, 2))
                vx = get_price_bars(self.db, "VXN", day - timedelta(days=10), day - timedelta(days=1))
                if len(vx):
                    feats["vxn_prev"] = round(float(vx["close"].iloc[-1]), 2)
        except Exception as exc:
            feats["error"] = str(exc)[:80]
        self._log(day, dict(ts=str(datetime.combine(day, dtime(0, 0)) + timedelta(minutes=minute)), minute=minute, event="features",
                            ndx=feats.get("level", ""), note=json.dumps(feats)))
        if self.write_ledger:
            try:
                L.record_session(self.db, day, self.underlying, self.slug, bool(session.blocked_reason), session.blocked_reason,
                                 note=f"features {json.dumps(feats)}")
            except Exception as exc:
                logger.warning("session features not recorded: %s", exc)

    def _save_state(self, session, day: date, finished: bool = False) -> None:
        try:
            self._state_path(day).write_text(json.dumps({"state": session.to_dict(), "written": self._written,
                                                         "tgids": {"|".join(map(str, k)): v for k, v in self._tgids.items()},
                                                         "provider": getattr(self.provider, "name", "?"), "finished": finished}, default=str), encoding="utf-8")
        except Exception as exc:
            logger.warning("state save failed: %s", exc)

    def _restore(self, day: date, blocked_reason: str):
        p = self._state_path(day)
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("finished"):
                logger.info("state for %s is a finished session; starting fresh", day); return None
            if d.get("provider") != getattr(self.provider, "name", "?"):
                logger.info("state for %s came from provider %r, not %r; starting fresh", day, d.get("provider"), getattr(self.provider, "name", "?")); return None
            fresh = self.strategy.live_session(day, blocked_reason=blocked_reason)
            session = type(fresh).from_dict(self.strategy.params, d["state"])
            self._written = int(d.get("written", 0))
            self._tgids = {tuple((float(x) if i else x) for i, x in enumerate(k.split("|"))): v for k, v in d.get("tgids", {}).items()}
            logger.info("resumed %s from %s: %d fills, %d open", day, p.name, len(session.fills), len(session.positions))
            return session
        except Exception as exc:
            logger.warning("state restore failed (%s); starting fresh", exc)
            return None

    def _gate(self, day: date) -> tuple[bool, str]:
        try:
            return self.strategy.session_gate(day)
        except Exception as exc:
            logger.error("gate check failed: %s", exc)
            return True, f"gate error: {exc}"

    # ── replay ────────────────────────────────────────────────────────────────
    def run_replay(self, day: date, resume: bool = False) -> RunResult:
        prov: ReplayProvider = self.provider
        blocked, why = self._gate(day)
        session = (self._restore(day, why) if resume else None) or self.strategy.live_session(day, blocked_reason=why)
        if self.write_ledger:
            L.record_session(self.db, day, self.underlying, self.slug, blocked, why, note=f"replay half_spread={prov.h}")
        if not prov.has_option_data() and not blocked:
            logger.warning("%s: no option prints stored; the engine will find no quotes", day)
        res = RunResult(day, self.slug, prov.name, blocked, why)

        def quote_fn(S, k_low, k_high, kind, minute):
            q = prov.quote_vertical(kind, k_low, k_high, minute)
            self._last_quote[(kind, k_low, k_high)] = q
            return q

        n = 0
        while True:
            bar = prov.next_bar()
            if bar is None:
                break
            n += 1
            minute = _minute_of(bar.ts) + 1
            self._day_bars.append(bar)
            self._log_session_features(session, day, minute)
            session.on_bar(minute, bar.close, quote_fn, is_last=prov.is_last_bar(), high=bar.high, low=bar.low)
            self._write_new_fills(session, day, prov.expiry, bar.close, prov.leg_symbols)
        self._save_state(session, day, finished=True)
        res.trades, res.fills, res.day_pnl, res.bars = session.trades, session.fills, session.day_pnl, n
        res.n_fills_written, res.log_path, res.state_path = self._written, str(self._log_path(day)), str(self._state_path(day))
        if self.write_ledger:
            L.record_day_balance(self.db, self.account_id, day, session.day_pnl)
        return res

    # ── live ──────────────────────────────────────────────────────────────────
    def run_live(self, day: Optional[date] = None, poll_seconds: Optional[int] = None, until: dtime = dtime(16, 1),
                 now_fn: Callable[[], datetime] = now_et, sleep_fn: Callable[[float], None] = time.sleep) -> RunResult:
        """Follow the clock (``now_fn``, injectable for tests) with a real-time provider: poll quotes,
        build the underlying's minute bars, drive the engine at each minute's end."""
        prov = self.provider
        poll = int(poll_seconds or getattr(prov, "poll_seconds", 15))
        day = day or now_fn().date()
        blocked, why = self._gate(day)
        n_chain = prov.load_chain(day)
        logger.info("%s %s: gate %s; %d contracts in today's %s chain", self.slug, day, (f"BLOCKED ({why})" if blocked else "open"), n_chain, prov.root)
        if self.write_ledger:
            L.record_session(self.db, day, self.underlying, self.slug, blocked, why, note=f"live {prov.name}, {n_chain} contracts")
        session = self._restore(day, why) or self.strategy.live_session(day, blocked_reason=why)
        res = RunResult(day, self.slug, prov.name, blocked, why)
        carry = int(getattr(self.strategy.params, "carry_min", 30))
        cur_minute: Optional[datetime] = None
        quotes: dict = {}

        def quote_fn(S, k_low, k_high, kind, minute):
            nonlocal quotes
            ls, ss = prov.leg_symbols(kind, k_low, k_high)
            if not ls or not ss:
                return None
            if ls not in quotes or ss not in quotes:                 # a strike the engine just chose: fetch it now
                try:
                    quotes.update(prov.fetch([ls, ss]))
                except Exception as exc:
                    logger.warning("quote fetch failed: %s", exc); return None
            q = prov.quote_vertical(kind, k_low, k_high, quotes, now_fn(), carry)
            self._last_quote[(kind, k_low, k_high)] = q
            return q

        def watched_symbols() -> list[str]:
            syms = []
            for pos in session.positions:
                syms += list(prov.leg_symbols(pos.kind, pos.k_low, pos.k_high))
            if getattr(session, "pending", None) is not None:
                pe = session.pending; syms += list(prov.leg_symbols(pe.kind, pe.k_low, pe.k_high))
            return [s for s in syms if s]

        n = 0
        while True:
            now = now_fn()
            if now.time() >= until:
                break
            if now.time() < SESSION_OPEN:
                sleep_fn(min(60, poll)); continue
            try:
                quotes = prov.fetch(watched_symbols())
            except Exception as exc:
                logger.warning("fetch failed: %s", exc); sleep_fn(poll); continue
            prov.sample_underlying(quotes, now)
            this_minute = now.replace(second=0, microsecond=0)
            if cur_minute is None:
                cur_minute = this_minute
            if this_minute > cur_minute:                                # the previous minute is complete
                bar = prov.close_minute(cur_minute)
                if bar is not None:
                    minute = _minute_of(bar.ts) + 1
                    is_last = minute >= SESSION_CLOSE_MIN
                    self._day_bars.append(bar)
                    self._log_session_features(session, day, minute)
                    session.on_bar(minute, bar.close, quote_fn, is_last=is_last, high=bar.high, low=bar.low)
                    n += 1
                    self._write_new_fills(session, day, prov.expiry or day, bar.close, prov.leg_symbols)
                    self._save_state(session, day)
                    if n % 15 == 0 or session.fills:
                        logger.info("%s bar %s close %.2f | open %d | marked %+.0f | fills %d", day, bar.ts.strftime("%H:%M"), bar.close,
                                    len(session.positions), session.marked(), len(session.fills))
                cur_minute = this_minute
            sleep_fn(poll)
        self._save_state(session, day, finished=True)
        res.trades, res.fills, res.day_pnl, res.bars = session.trades, session.fills, session.day_pnl, n
        res.n_fills_written, res.log_path, res.state_path = self._written, str(self._log_path(day)), str(self._state_path(day))
        if self.write_ledger:
            L.record_day_balance(self.db, self.account_id, day, session.day_pnl)
        logger.info("session done: %d bars, %d trades, day P&L %+.0f", n, len(session.trades), session.day_pnl)
        return res
