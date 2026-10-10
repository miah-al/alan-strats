"""
api/services/day_stop.py — the account-wide day stop (2026-10-08, the owner's go after a −$4,240 day).

The trader's system limit ``account_day_stop`` (the Limits page, System; $, 0 = none): when the paper account's day P&L
— its equity now against its equity at the last close (``limits.account_day_change``; before 2026-10-12 it was every
scope's P&L since entry, which made multi-day holdings look like today's) — is that far down, every armed strategy's new entries are turned off for the rest of the day
through the supervisor's control (``sup_entries`` = 0, by "system"). The runners read it every poll; open positions
keep their own exits. It fires once a day and only takes risk off: nothing here opens, adds or closes anything.
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
from typing import Callable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("alan_trader.api.day_stop")

ET = ZoneInfo("America/New_York")
TICK_S = 30
LIMIT = "account_day_stop"
OPEN, CLOSE = _dt.time(9, 30), _dt.time(16, 0)


class AccountDayStop:
    def __init__(self, limits_fn: Callable[[], object], usage_fn: Callable[[], dict],
                 publish: Optional[Callable[[dict], None]] = None, clock: Optional[Callable[[], _dt.datetime]] = None,
                 tick_s: float = TICK_S):
        self._limits_fn = limits_fn              # -> api.services.limits.Limits (scopes, values, set)
        self._usage_fn = usage_fn                # -> limits.paper_usage(): {scope: {day_pnl, ...}}
        self._publish = publish
        self._clock = clock or (lambda: _dt.datetime.now(ET).replace(tzinfo=None))
        self._tick_s = tick_s
        self._fired: Optional[_dt.date] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── the check ─────────────────────────────────────────────────────────────
    @staticmethod
    def account_day_pnl(usage: dict) -> float:
        """The account's day: its equity change since the last close (``system.account_day``) when known, else every
        scope's P&L summed (which counts multi-day positions' P&L since entry)."""
        acct = ((usage or {}).get("system") or {}).get("account_day")
        if acct is not None:
            return float(acct)
        return float(sum(float((u or {}).get("day_pnl") or 0.0) for s, u in (usage or {}).items() if s != "system"))

    def tick(self, now: Optional[_dt.datetime] = None) -> Optional[dict]:
        """Fire when the account's day P&L is at or below -limit during the session; returns what it did, else None."""
        now = now or self._clock()
        if now.weekday() >= 5 or not (OPEN <= now.time() < CLOSE) or self._fired == now.date():
            return None
        lim = self._limits_fn()
        try:
            stop = abs(float(lim.values("system").get(LIMIT) or 0.0))
        except (TypeError, ValueError):
            return None
        if stop <= 0:
            return None
        day = self.account_day_pnl(self._usage_fn())
        if day > -stop:
            return None
        reason = f"account day stop: the account is {day:+,.0f} today, at or past -{stop:,.0f}"
        done, failed = [], []
        for scope, kind, _label in lim.scopes():
            if kind != "strategy":
                continue
            try:
                lim.set(scope, "sup_entries", 0, by="system", reason=reason)
                done.append(scope)
            except Exception as exc:  # noqa: BLE001 — one scope must not keep the others on
                failed.append(f"{scope}: {exc}")
        self._fired = now.date()
        logger.warning("%s; new entries off for %s%s", reason, ", ".join(done) or "no strategy",
                       f" (failed: {'; '.join(failed)})" if failed else "")
        out = {"type": "day_stop", "day_pnl": round(day, 2), "limit": stop, "strategies": done, "failed": failed,
               "at": now.isoformat(timespec="seconds"), "reason": reason}
        if self._publish:
            try:
                self._publish(out)
            except Exception:  # noqa: BLE001
                logger.debug("day stop: publish failed", exc_info=True)
        return out

    # ── the thread ────────────────────────────────────────────────────────────
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="account-day-stop", daemon=True)
        self._thread.start()
        logger.info("account day stop on (limit %s, checked every %ss)", LIMIT, self._tick_s)

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._tick_s):
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                logger.exception("account day stop: check failed")
