"""
api/marketdata/limits.py — how much the service may ask each provider, and what happens when a
provider pushes back.

Per provider: token buckets (per request kind where the vendor's plan differs by kind, e.g.
Polygon's stock endpoints are the free 5/min tier and its options endpoints the paid one), a daily
budget, and exponential backoff after a 429, a 5xx or a connection failure (15 s doubling to
15 min). A provider that is backing off or has spent its day's budget refuses at once with
``ProviderUnavailable`` — the hub then falls back to the next provider — and is reported
``degraded`` (backing off / nearly spent) or ``down`` (spent / disabled).

``Gate`` is what the service installs as ``data.request_gate``'s gate, so every requests /
yfinance call in the process is counted and limited here. tastytrade is counted here too, but its
hard ceiling is the platform's own ``paper.providers.RequestBudget`` (see providers/tastytrade.py).

Limits can be tuned per provider with environment variables:
``ALAN_TRADER_LIMIT_<PROVIDER>_PER_MIN`` and ``ALAN_TRADER_LIMIT_<PROVIDER>_PER_DAY``.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from data.request_gate import ProviderUnavailable

logger = logging.getLogger("alan_trader.api.marketdata")

CONNECTED, DEGRADED, DOWN = "connected", "degraded", "down"
BACKOFF_START_S = 15.0
BACKOFF_MAX_S = 900.0
#: how long acquire() may wait for a token before refusing (a request thread must not hang)
DEFAULT_MAX_WAIT_S = 30.0


class TokenBucket:
    """``rate_per_min`` tokens a minute, at most ``burst`` banked."""

    def __init__(self, rate_per_min: float, burst: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.rate = max(float(rate_per_min), 0.001) / 60.0
        self.burst = max(float(burst), 1.0)
        self.tokens = self.burst
        self._clock, self._sleep = clock, sleep
        self._t = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        self.tokens = min(self.burst, self.tokens + (now - self._t) * self.rate)
        self._t = now

    def wait_time(self) -> float:
        with self._lock:
            self._refill()
            return 0.0 if self.tokens >= 1.0 else (1.0 - self.tokens) / self.rate

    def take(self, max_wait: Optional[float] = DEFAULT_MAX_WAIT_S) -> float:
        """Take a token, sleeping for one if needed; returns the seconds waited. Raises
        TimeoutError when the wait would exceed ``max_wait``."""
        waited = 0.0
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return waited
                need = (1.0 - self.tokens) / self.rate
            if max_wait is not None and waited + need > max_wait:
                raise TimeoutError(f"next request slot in {need:.0f}s")
            self._sleep(need)
            waited += need


@dataclass
class ProviderPolicy:
    name: str
    per_min: float
    per_day: int
    burst: float = 5.0
    kinds: dict = field(default_factory=dict)      # kind -> (per_min, burst)
    enabled: bool = True

    @classmethod
    def from_env(cls, name: str, per_min: float, per_day: int, burst: float = 5.0, kinds: Optional[dict] = None):
        env = name.upper()
        pm = os.environ.get(f"ALAN_TRADER_LIMIT_{env}_PER_MIN")
        pd_ = os.environ.get(f"ALAN_TRADER_LIMIT_{env}_PER_DAY")
        return cls(name, float(pm) if pm else per_min, int(pd_) if pd_ else per_day, burst, dict(kinds or {}))


class ProviderLimits:
    """The live accounting for one provider."""

    def __init__(self, policy: ProviderPolicy, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, today: Callable[[], _dt.date] = _dt.date.today):
        self.policy = policy
        self.name = policy.name
        self._clock, self._sleep, self._today = clock, sleep, today
        self.bucket = TokenBucket(policy.per_min, policy.burst, clock, sleep)
        self.kind_buckets = {k: TokenBucket(pm, b, clock, sleep) for k, (pm, b) in policy.kinds.items()}
        self._lock = threading.Lock()
        self.recent: deque[float] = deque()          # monotonic times of requests in the last minute
        self.day = today()
        self.calls_today = 0
        self.failures = 0
        self.backoff_until = 0.0
        self.last_error: Optional[str] = None
        self.last_error_at: Optional[str] = None
        self.last_ok_at: Optional[str] = None
        self.detail = ""
        self.disabled_reason: Optional[str] = None if policy.enabled else "disabled"
        #: an external budget (tastytrade's RequestBudget) reports what it has left
        self.external_remaining: Optional[Callable[[], Optional[int]]] = None
        self.on_change: Optional[Callable[["ProviderLimits"], None]] = None
        self._last_state = CONNECTED

    # ── accounting ────────────────────────────────────────────────────────────
    def _roll_day(self) -> None:
        d = self._today()
        if d != self.day:
            self.day, self.calls_today = d, 0

    def _trim(self, now: float) -> None:
        while self.recent and now - self.recent[0] >= 60.0:
            self.recent.popleft()

    def budget_remaining(self) -> Optional[int]:
        rem = self.policy.per_day - self.calls_today
        if self.external_remaining is not None:
            try:
                ext = self.external_remaining()
            except Exception:
                ext = None
            if ext is not None:
                rem = min(rem, ext)
        return max(0, rem)

    def requests_last_min(self) -> int:
        with self._lock:
            self._trim(self._clock())
            return len(self.recent)

    def state(self) -> str:
        with self._lock:
            self._roll_day()
            if self.disabled_reason:
                return DOWN
            rem = self.budget_remaining()
            if rem is not None and rem <= 0:
                return DOWN
            if self._clock() < self.backoff_until:
                return DEGRADED
            if rem is not None and self.policy.per_day and rem < 0.1 * self.policy.per_day:
                return DEGRADED
            return CONNECTED

    def check(self) -> None:
        """Raise ProviderUnavailable when the provider must not be called now."""
        with self._lock:
            self._roll_day()
            if self.disabled_reason:
                raise ProviderUnavailable(self.name, self.disabled_reason)
            now = self._clock()
            if now < self.backoff_until:
                wait = self.backoff_until - now
                raise ProviderUnavailable(self.name, f"backing off after {self.last_error or 'errors'}; "
                                                     f"retry in {wait:.0f}s", retry_after=wait)
            rem = self.budget_remaining()
            if rem is not None and rem <= 0:
                raise ProviderUnavailable(self.name, f"daily request budget spent ({self.policy.per_day})")

    def acquire(self, kind: str = "", max_wait: Optional[float] = DEFAULT_MAX_WAIT_S) -> None:
        self.check()
        try:
            b = self.kind_buckets.get(kind)
            if b is not None:
                b.take(max_wait)
            self.bucket.take(max_wait)
        except TimeoutError as exc:
            raise ProviderUnavailable(self.name, f"rate limited: {exc}") from None
        with self._lock:
            now = self._clock()
            self._trim(now)
            self.recent.append(now)
            self.calls_today += 1

    def ok(self) -> None:
        with self._lock:
            self.failures = 0
            self.backoff_until = 0.0
            self.last_ok_at = _now_iso()
        self._changed()

    def fail(self, reason: str, backoff: bool = True) -> None:
        from api.redact import redact
        with self._lock:
            self.last_error = redact(str(reason))[:300]
            self.last_error_at = _now_iso()
            if backoff:
                self.failures += 1
                delay = min(BACKOFF_MAX_S, BACKOFF_START_S * (2 ** (self.failures - 1)))
                self.backoff_until = self._clock() + delay
                logger.warning("%s: %s — backing off %.0fs", self.name, self.last_error, delay)
        self._changed()

    def note(self, detail: str) -> None:
        self.detail = detail
        self._changed()

    def disable(self, reason: Optional[str]) -> None:
        self.disabled_reason = reason
        self._changed()

    def _changed(self) -> None:
        st = self.state()
        if st != self._last_state:
            self._last_state = st
            if self.on_change is not None:
                try:
                    self.on_change(self)
                except Exception:
                    logger.debug("provider state callback failed", exc_info=True)

    def snapshot(self) -> dict:
        return {"name": self.name, "state": self.state(), "requests_last_min": self.requests_last_min(),
                "budget_remaining": self.budget_remaining(), "last_error": self.last_error,
                "detail": self.disabled_reason or self.detail, "requests_today": self.calls_today,
                "daily_budget": self.policy.per_day, "per_min": self.policy.per_min,
                "backoff_s": max(0.0, round(self.backoff_until - self._clock(), 1)),
                "last_error_at": self.last_error_at, "last_ok_at": self.last_ok_at}


def _now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def default_policies() -> list[ProviderPolicy]:
    """The service's limits. Polygon: the stock endpoints are the plan's free 5/min tier (the
    client's own limiter enforces it too), the options endpoints the paid tier. yfinance and FRED
    publish no quota; these are far below anything that has drawn a 429. tastytrade's hard
    ceiling is the platform's RequestBudget; this policy only counts."""
    return [
        ProviderPolicy.from_env("tastytrade", per_min=20, per_day=3000, burst=5),
        ProviderPolicy.from_env("polygon", per_min=60, per_day=5000, burst=10,
                                kinds={"stocks": (5, 5), "options": (60, 10)}),
        ProviderPolicy.from_env("yfinance", per_min=60, per_day=5000, burst=20),
        ProviderPolicy.from_env("fred", per_min=20, per_day=500, burst=8),
    ]


class Gate:
    """The service's ``data.request_gate`` gate: per-provider limits and accounting."""

    def __init__(self, policies: Optional[list[ProviderPolicy]] = None, **kw):
        self.providers: dict[str, ProviderLimits] = {
            p.name: ProviderLimits(p, **kw) for p in (policies if policies is not None else default_policies())}

    def __getitem__(self, name: str) -> ProviderLimits:
        return self.providers[name]

    def get(self, name: str) -> Optional[ProviderLimits]:
        return self.providers.get(name)

    def acquire(self, provider: str, kind: str = "") -> None:
        p = self.providers.get(provider)
        if p is not None:
            p.acquire(kind)

    def record(self, provider: str, status: Optional[int], exc: Optional[BaseException] = None) -> None:
        p = self.providers.get(provider)
        if p is None:
            return
        if exc is not None and status is None:
            name = type(exc).__name__
            transient = any(k in name for k in ("Timeout", "Connection", "RateLimit", "ChunkedEncoding",
                                                "RemoteDisconnected", "ProtocolError", "SSLError"))
            if "RateLimit" in name:
                p.fail("429 rate limited")
            elif transient:
                p.fail(f"{name}: {str(exc)[:160]}")
            return
        if status is None:
            return
        if status == 429:
            p.fail("429 Too Many Requests")
        elif status >= 500:
            p.fail(f"{status} server error")
        elif status < 400:
            p.ok()
        else:
            # 4xx other than 429: the request, not the provider (a 403 for data outside the plan,
            # a 404 for an unknown ticker) — recorded, no backoff
            p.fail(f"{status} for a request", backoff=False)

    def snapshot(self) -> list[dict]:
        return [p.snapshot() for p in self.providers.values()]
