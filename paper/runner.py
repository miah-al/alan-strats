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

import pandas as pd

from strategy_api.live import Quote
from strategy_api import registry as R
from .providers import ReplayProvider, TastytradeProvider, Bar, now_et
from . import ledger as L

logger = logging.getLogger("paper.runner")

SESSION_OPEN = dtime(9, 30)
SESSION_CLOSE_MIN = 16 * 60
MAX_FILLS_PER_SESSION = 60          # runaway guard: more fills than this in a day means bad data, not trading
VXN_MAX_AGE_DAYS = 4                # the gate's VXN close must be at most this many days old
FETCH_BACKOFF_MAX_S = 300          # a failing quote feed is polled less and less often, never faster than this cap
FETCH_FAILURES_TO_HALT = 12        # ~25 minutes of backoff-spaced failures: stop asking, alert, keep the state
MIN_POLL_S = 10                    # the broker's API is never polled faster than this, whatever the flag says
QUOTE_SILENCE_ALERT_MIN = 5         # alert when no quote fetch has succeeded for this long during the session
STATE_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / "paper_state"
LOG_COLS = ["ts", "minute", "event", "ndx", "k_low", "k_high", "kind", "direction", "bid", "ask", "last", "age",
            "limit", "fill", "lots", "cash", "reason", "tgid", "long_symbol", "short_symbol", "note",
            "spread", "long_bid", "long_ask", "long_age", "short_bid", "short_ask", "short_age"]   # quoted width and the legs behind it


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
                 account_name: str = "Paper Account", params: Optional[dict] = None, state_dir: Optional[Path] = None, starting_cash: Optional[float] = None,
                 notify: bool = False):
        self.slug = slug
        self.provider = provider
        self.db = engine_db
        self.write_ledger = write_ledger and engine_db is not None
        self.strategy = R.get_strategy(slug)
        if params:
            self.strategy = type(self.strategy)(**{**self.strategy.get_params(), **params})
        inst = self.strategy.live_instrument() or {}
        self.underlying = str(inst.get("underlying", getattr(provider, "underlying", "NDX"))).upper()
        self.account_id = L.ensure_paper_account(engine_db, account_name, starting_cash=starting_cash) if self.write_ledger else None
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
        self.notify = bool(notify)
        self.halted: Optional[str] = None

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
        if not new:                                             # an older column set in the file: rewrite it on the current one
            with p.open("r", newline="", encoding="utf-8") as f:
                r = csv.DictReader(f); old_cols = r.fieldnames or []; old_rows = list(r) if old_cols != LOG_COLS else []
            if old_cols != LOG_COLS:
                with p.open("w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=LOG_COLS); w.writeheader()
                    for o in old_rows:
                        w.writerow({k: o.get(k, "") for k in LOG_COLS})
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
                       lots=f["lots"], cash=f["cash"], reason=f["reason"], tgid=tg, long_symbol=ls or "", short_symbol=ss or "", note="",
                       spread=(round(q.ask - q.bid, 2) if q else ""))
            if q is not None and getattr(q, "legs", None):
                (lb, la, lage), (sb, sa, sage) = q.legs
                row.update(long_bid=lb, long_ask=la, long_age=lage, short_bid=sb, short_ask=sa, short_age=sage)
            self._log(day, row)
            logger.info("%s %s %s %s/%s @ %s (%s)", row["ts"][11:16], f["kind"], f["direction"], f["kl"], f["kh"], f["px"], f["reason"])
            if self.write_ledger and f["kind"] in ("open", "add", "close"):
                try:
                    new_pid = L.record_fill(self.db, self.account_id, self.slug, self.underlying, expiry, day, f,
                                            ls or f"{self.underlying}-{f['kl']:.0f}", ss or f"{self.underlying}-{f['kh']:.0f}", position_id=pid,
                                            extra={"provider": getattr(self.provider, "name", "?"), "bid": (q.bid if q else None), "ask": (q.ask if q else None), "last": (q.last if q else None),
                                                   # per-leg quotes so the ledger can book each leg at its own
                                                   # price instead of hanging the whole debit on the long one
                                                   **({"long_bid": q.legs[0][0], "long_ask": q.legs[0][1],
                                                       "short_bid": q.legs[1][0], "short_ask": q.legs[1][1]}
                                                      if (q is not None and getattr(q, "legs", None)) else {})})
                    if f["kind"] == "open" and new_pid is not None:
                        self._tgids.setdefault(self._unit_key(f), []).append(int(new_pid))
                except Exception as exc:
                    logger.error("ledger write failed: %s", exc)
            elif f["kind"] == "open":                                   # no ledger: still track the unit
                self._tgids.setdefault(self._unit_key(f), []).append(-1)

    def _alert(self, text: str) -> None:
        """WhatsApp (engine.notify) when --notify is on and configured; always logged."""
        logger.info("ALERT %s", text)
        if not self.notify:
            return
        try:
            from engine.notify import whatsapp_configured
            from engine.signal_alerts import send_trade_alert
            if whatsapp_configured():
                send_trade_alert(f"📄 paper {self.slug}: {text}")
        except Exception as exc:
            logger.warning("alert failed: %s", exc)

    def _preflight(self, day: date) -> list[str]:
        """Checks before a live session: database, VXN freshness for the gate, the strategy's live hooks."""
        problems = []
        if self.db is None:
            problems.append("no database engine")
        else:
            try:
                from db.client import get_price_bars
                from datetime import timedelta
                vx = get_price_bars(self.db, "VXN", day - timedelta(days=30), day - timedelta(days=1))
                if vx is None or len(vx) == 0:
                    problems.append("no VXN daily bars: run scripts.bootstrap_market_data")
                else:
                    last = pd.Timestamp(vx["date"].iloc[-1]).date()
                    if (day - last).days > VXN_MAX_AGE_DAYS:
                        problems.append(f"VXN close is stale ({last}); run scripts.bootstrap_market_data")
            except Exception as exc:
                problems.append(f"VXN check failed: {exc}")
        if not self.strategy.live_instrument():
            problems.append("strategy exposes no live instrument")
        return problems

    def _step(self, session, minute: int, bar: Bar, quote_fn, is_last: bool, day: date, expiry: date, symbols_fn) -> bool:
        """One bar through the engine with the guards. Returns False when the session must halt."""
        if self.halted:
            return False
        try:
            session.on_bar(minute, bar.close, quote_fn, is_last=is_last, high=bar.high, low=bar.low)
        except Exception as exc:
            self.halted = f"engine error at {bar.ts:%H:%M}: {exc}"
            logger.exception("engine error; halting the session")
            self._alert(self.halted)
            return False
        self._write_new_fills(session, day, expiry, bar.close, symbols_fn)
        if len(session.fills) > MAX_FILLS_PER_SESSION:
            self.halted = f"runaway guard: {len(session.fills)} fills"
            logger.error(self.halted)
            self._alert(self.halted)
            return False
        return True

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
        # the strategy's own feature set and gate-model verdict (shadow unless the strategy says "on")
        ai = {}
        try:
            if hasattr(self.strategy, "ai_features") and hasattr(self.strategy, "ai_verdict"):
                sf = self.strategy.ai_features(day, list(self._day_bars), self.db)
                ai = self.strategy.ai_verdict(sf)
                feats["ai"] = {k: v for k, v in ai.items() if k != "features"}
                feats["ai_features"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in sf.items()}
                if ai.get("mode") == "on" and ai.get("verdict") == "skip":
                    session.ai_blocked = f"ai gate skip (p={ai.get('p')})"
                    logger.info("AI gate ON: skip today (p=%s); no new entries", ai.get("p"))
                    self._alert(f"AI gate: skip today (p={ai.get('p')})")
                elif ai.get("mode") == "shadow":
                    logger.info("AI gate shadow: %s (p=%s, model %s)", ai.get("verdict"), ai.get("p"), ai.get("model"))
        except Exception as exc:
            feats["ai_error"] = str(exc)[:80]
        self._log(day, dict(ts=str(datetime.combine(day, dtime(0, 0)) + timedelta(minutes=minute)), minute=minute, event="features",
                            ndx=feats.get("level", ""), note=json.dumps(feats, default=str)))
        if self.write_ledger:
            try:
                L.record_session(self.db, day, self.underlying, self.slug, bool(session.blocked_reason), session.blocked_reason,
                                 note=f"features {json.dumps(feats)}")
            except Exception as exc:
                logger.warning("session features not recorded: %s", exc)

    def _log_mark(self, day: date, now: datetime, pos, q) -> None:
        """One row per poll per open position: the quote, and the target it is being measured against.

        The engine acts on bar closes; this records what the price did between them, so "the target
        was available but the bar had passed" becomes a number instead of an impression.
        """
        try:
            avg = float(getattr(pos, "avg_px", 0.0) or 0.0)
            target = avg + float(getattr(self.strategy.params, "target_pts", 5.0))
            p = self.log_dir / f"marks_{day.isoformat()}.csv"
            new = not p.exists()
            with p.open("a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["ts", "direction", "k_low", "k_high", "units", "avg_px", "target",
                                "bid", "ask", "mid", "age", "at_target"])
                w.writerow([now.isoformat(timespec="seconds"), pos.direction, pos.k_low, pos.k_high,
                            getattr(pos, "units", ""), round(avg, 2), round(target, 2),
                            round(float(q.bid), 2), round(float(q.ask), 2), round(float(q.last), 2),
                            q.age, int(float(q.last) >= target)])
        except Exception:
            pass

    def _heartbeat(self, day: date, now: datetime, session, note: str = "", live_marks: dict | None = None,
                   live_legs: dict | None = None, spot: float | None = None) -> None:
        """A small file the Paper tab reads: when the runner last polled, what it holds, the day so far.

        ``live_marks`` carries each open position's mark from the quote in hand at THIS poll. The
        engine only remarks a position when a minute bar closes, so without this the page could show
        a price up to a minute old however often it was refreshed, and would sit unchanged through
        three perfectly good quotes. These are for display only; the engine still decides on bars.
        """
        try:
            hb = {"slug": self.slug, "day": str(day), "at": now.isoformat(timespec="seconds"), "provider": getattr(self.provider, "name", "?"),
                  "open_positions": len(session.positions), "fills": len(session.fills), "trades": len(session.trades),
                  "marked": round(session.marked(), 0), "day_pnl": round(session.day_pnl, 0), "halted": self.halted or "", "note": note,
                  "live_marks": live_marks or {}, "live_legs": live_legs or {}, "spot": spot, "underlying": self.underlying,
                  "marks_at": now.isoformat(timespec="seconds") if live_marks else "",
                  "api_calls_today": getattr(getattr(self.provider, "budget", None), "calls_today", None)}   # how many broker requests so far
            (self.state_dir / f"heartbeat_{self.slug}.json").write_text(json.dumps(hb), encoding="utf-8")
        except Exception:
            pass

    def _force_settlement(self, session, day: date, quote_fn, expiry: date, symbols_fn, why: str) -> None:
        """The session is over but positions are still open (a missed final bar, a halt): settle
        them now at the last known spot so the ledger and the state never carry a unit overnight."""
        if not session.positions:
            return
        S = float(session.closes[-1]) if session.closes else 0.0
        logger.warning("%d position(s) still open at session end (%s); settling at the last spot %.2f", len(session.positions), why, S)
        try:
            session.on_bar(SESSION_CLOSE_MIN, S, quote_fn, is_last=True)
        except Exception as exc:
            logger.exception("forced settlement failed: %s", exc)
        self._write_new_fills(session, day, expiry, S, symbols_fn)
        self._alert(f"{day}: {why}; open units settled at the last spot; day P&L {session.day_pnl:+,.0f}")

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
            if not self._step(session, minute, bar, quote_fn, prov.is_last_bar(), day, prov.expiry, prov.leg_symbols):
                break
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
        poll = max(MIN_POLL_S, int(poll_seconds or getattr(prov, "poll_seconds", 15)))
        fetch_failures = 0
        day = day or now_fn().date()
        problems = self._preflight(day)
        for pr in problems:
            logger.error("preflight: %s", pr)
        blocked, why = self._gate(day)
        if not blocked and any("VXN" in pr for pr in problems):
            blocked, why = True, "stale or missing VXN (preflight)"
        n_chain = 0
        for attempt in range(3):                                   # the chain call can fail on a flaky connection
            try:
                n_chain = prov.load_chain(day); break
            except Exception as exc:
                logger.warning("chain load failed (%d/3): %s", attempt + 1, exc); sleep_fn(20)
        if n_chain == 0 and not blocked:
            blocked, why = True, f"no {prov.root} contracts expire today"
        logger.info("%s %s: gate %s; %d contracts in today's %s chain", self.slug, day, (f"BLOCKED ({why})" if blocked else "open"), n_chain, prov.root)
        self._alert(f"{day} gate {'BLOCKED: ' + why if blocked else 'open'}; {n_chain} contracts")
        try:                                                    # the exact rules this session ran with, in its own diary
            _pp = self.strategy.params; _pd = _pp.as_dict() if hasattr(_pp, "as_dict") else dict(vars(_pp))
            logger.info("%s %s: params %s", self.slug, day, json.dumps(_pd, default=str, sort_keys=True))
        except Exception:
            pass
        if self.write_ledger:
            L.record_session(self.db, day, self.underlying, self.slug, blocked, why, note=f"live {prov.name}, {n_chain} contracts")
        session = self._restore(day, why) or self.strategy.live_session(day, blocked_reason=why)
        res = RunResult(day, self.slug, prov.name, blocked, why)
        carry = int(getattr(self.strategy.params, "carry_min", 30))
        cur_minute: Optional[datetime] = None
        quotes: dict = {}
        # late start: feed the engine today's earlier bars so its lookback and the features are complete
        start_now = now_fn()
        # Not "no history" but "not enough history": a session restarted mid-morning resumes holding
        # the handful of bars it had polled before stopping, which is worse than none -- it looks
        # populated, so the backfill is skipped, and the engine then waits out the whole lookback
        # again before it can signal. The backfill runs to now, so it supersedes that partial history.
        need = int(getattr(self.strategy.params, "lookback_min", 30))
        if len(session.closes) < need and start_now.time() > SESSION_OPEN and hasattr(prov, "backfill_bars"):
            back = prov.backfill_bars(day, start_now.replace(second=0, microsecond=0))
            if back:
                logger.info("late start %s: backfilling %d bars from %s (had %d)",
                            start_now.strftime("%H:%M"), len(back), back[0].ts.strftime("%H:%M"), len(session.closes))
                session.closes.clear()
                self._day_bars.clear()
                for b in back:
                    m = _minute_of(b.ts) + 1
                    self._day_bars.append(b)
                    session.closes.append(float(b.close))        # history only: no decisions on backfilled bars
                    session.last_minute = m

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
        last_good_fetch: Optional[datetime] = None
        silence_alerted = False
        while True:
            now = now_fn()
            if now.time() >= until:
                break
            if now.time() < SESSION_OPEN:
                self._heartbeat(day, now, session, "waiting for the open")
                sleep_fn(min(60, poll)); continue
            try:
                quotes = prov.fetch(watched_symbols())
                last_good_fetch = now
                silence_alerted = False
            except Exception as exc:
                fetch_failures += 1
                logger.warning("fetch failed (%d in a row): %s", fetch_failures, exc)
                if last_good_fetch is not None and not silence_alerted and (now - last_good_fetch).total_seconds() >= QUOTE_SILENCE_ALERT_MIN * 60:
                    self._alert(f"no quotes for {QUOTE_SILENCE_ALERT_MIN} minutes ({exc}); {len(session.positions)} open"); silence_alerted = True
                # a rejected credential is never retried: re-asking cannot fix it and looks like abuse to the broker
                if "rejected the credentials" in str(exc) or fetch_failures >= FETCH_FAILURES_TO_HALT:
                    self.halted = f"quote feed halted after {fetch_failures} failures: {str(exc)[:120]}"
                    logger.error(self.halted); self._alert(self.halted)
                    self._heartbeat(day, now, session, "halted: quote feed"); self._save_state(session, day, finished=False)
                    break
                wait = min(FETCH_BACKOFF_MAX_S, poll * (2 ** min(fetch_failures - 1, 5)))     # 15, 30, 60, 120, 240, 300 ...
                self._heartbeat(day, now, session, f"fetch failing ({fetch_failures}), next try in {wait}s: {str(exc)[:60]}")
                sleep_fn(wait); continue
            fetch_failures = 0
            # Remark every open position off the quote just fetched, so the page moves with the
            # market rather than in once-a-minute steps. Costs nothing: these quotes are in hand.
            live_marks: dict = {}
            live_legs: dict = {}
            for pos in session.positions:
                try:
                    qv = prov.quote_vertical(pos.kind, pos.k_low, pos.k_high, quotes, now, carry)
                    if qv is not None:
                        live_marks[f"{pos.direction}|{float(pos.k_low)}|{float(pos.k_high)}"] = round(float(qv.last), 2)
                        # Every poll's mark against the target the engine will only check at the next
                        # bar close. Near expiry the quote can travel several points inside a minute,
                        # so the question of how much a bar-close check leaves on the table is real --
                        # and unanswerable without keeping the intra-bar prices somewhere.
                        self._log_mark(day, now, pos, qv)
                    # the legs too, so the position popup can price each one without opening its own
                    # broker connection from inside the web process
                    for sym in prov.leg_symbols(pos.kind, pos.k_low, pos.k_high):
                        lq = quotes.get(sym) if sym else None
                        if lq is not None and lq.bid is not None and lq.ask is not None and lq.ask >= lq.bid:
                            live_legs[str(sym)] = round((float(lq.bid) + float(lq.ask)) / 2.0, 2)
                except Exception:
                    pass
            iq = quotes.get(self.underlying)
            spot_now = float(iq.last) if (iq is not None and iq.last is not None) else None
            self._heartbeat(day, now, session, live_marks=live_marks, live_legs=live_legs, spot=spot_now)
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
                    if not self._step(session, minute, bar, quote_fn, is_last, day, prov.expiry or day, prov.leg_symbols):
                        break
                    n += 1
                    for f in session.fills[-3:]:
                        if f["m"] == minute and f["kind"] in ("open", "add", "close"):
                            self._alert(f"{bar.ts:%H:%M} {f['kind']} {f['direction']} {f['kl']:.0f}/{f['kh']:.0f} @ {f['px']:.2f} ({f['reason']}); day {session.day_pnl:+,.0f}")
                    self._write_new_fills(session, day, prov.expiry or day, bar.close, prov.leg_symbols)
                    self._save_state(session, day)
                    if n % 15 == 0 or session.fills:
                        logger.info("%s bar %s close %.2f | open %d | marked %+.0f | fills %d", day, bar.ts.strftime("%H:%M"), bar.close,
                                    len(session.positions), session.marked(), len(session.fills))
                cur_minute = this_minute
            sleep_fn(poll)
        if session.positions and now_fn().time() >= dtime(16, 0):
            self._force_settlement(session, day, quote_fn, prov.expiry or day, prov.leg_symbols,
                                   "session ended with open units" + (f" ({self.halted})" if self.halted else ""))
        self._save_state(session, day, finished=True)
        self._heartbeat(day, now_fn(), session, "finished")
        res.trades, res.fills, res.day_pnl, res.bars = session.trades, session.fills, session.day_pnl, n
        res.n_fills_written, res.log_path, res.state_path = self._written, str(self._log_path(day)), str(self._state_path(day))
        if self.write_ledger:
            L.record_day_balance(self.db, self.account_id, day, session.day_pnl)
        logger.info("session done: %d bars, %d trades, day P&L %+.0f%s", n, len(session.trades), session.day_pnl, (f"; HALTED: {self.halted}" if self.halted else ""))
        self._alert(f"{day} done: {len(session.trades)} trades, day P&L {session.day_pnl:+,.0f}" + (f"; HALTED: {self.halted}" if self.halted else ""))
        res.reason = res.reason or (self.halted or "")
        return res
