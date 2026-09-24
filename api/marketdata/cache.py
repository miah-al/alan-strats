"""
api/marketdata/cache.py — short-lived caches with single-flight loading.

``TTLCache.get_or_load(key, ttl, loader)`` returns a cached value younger than ``ttl`` seconds;
otherwise exactly one caller runs ``loader()`` while concurrent callers for the same key wait for
its result (so ten clients opening the same chain cost one upstream request, not ten). A loader
that raises caches nothing and re-raises to every waiter.

The service's minimums (CONTRACT v2): quotes >= 1 s, snapshots / chains >= 15 s, daily data >= 5 min.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Hashable, Optional

QUOTE_TTL = 1.0
SNAPSHOT_TTL = 15.0
CHAIN_TTL = 15.0
EXPIRATIONS_TTL = 300.0
DAILY_TTL = 300.0


class _Flight:
    __slots__ = ("event", "value", "error")

    def __init__(self):
        self.event = threading.Event()
        self.value: Any = None
        self.error: Optional[BaseException] = None


class TTLCache:
    def __init__(self, max_items: int = 2000, clock: Callable[[], float] = time.monotonic):
        self._data: dict[Hashable, tuple[float, Any]] = {}
        self._flights: dict[Hashable, _Flight] = {}
        self._lock = threading.Lock()
        self._max = max_items
        self._clock = clock
        self.hits = self.misses = 0

    def get(self, key: Hashable, ttl: float) -> tuple[bool, Any]:
        with self._lock:
            hit = self._data.get(key)
            if hit is not None and self._clock() - hit[0] < ttl:
                self.hits += 1
                return True, hit[1]
        return False, None

    def put(self, key: Hashable, value: Any) -> None:
        with self._lock:
            if len(self._data) >= self._max:
                # drop the oldest tenth
                for k, _ in sorted(self._data.items(), key=lambda kv: kv[1][0])[: max(1, self._max // 10)]:
                    self._data.pop(k, None)
            self._data[key] = (self._clock(), value)

    def age(self, key: Hashable) -> Optional[float]:
        with self._lock:
            hit = self._data.get(key)
            return None if hit is None else self._clock() - hit[0]

    def invalidate(self, key: Hashable) -> None:
        with self._lock:
            self._data.pop(key, None)

    def get_or_load(self, key: Hashable, ttl: float, loader: Callable[[], Any], timeout: float = 120.0,
                    cache_errors: tuple = (), error_ttl: float = 60.0) -> Any:
        """``cache_errors``: exception types remembered for ``error_ttl`` seconds (a "no data" answer
        should not send the next ten requests upstream again)."""
        ok, val = self.get(key, ttl)
        if ok:
            return _unwrap(val, self._data.get(key), error_ttl, self._clock)
        with self._lock:
            hit = self._data.get(key)
            if hit is not None and self._clock() - hit[0] < ttl:
                self.hits += 1
                return _unwrap(hit[1], hit, error_ttl, self._clock)
            flight = self._flights.get(key)
            leader = flight is None
            if leader:
                flight = self._flights[key] = _Flight()
                self.misses += 1
        if not leader:
            if not flight.event.wait(timeout):
                raise TimeoutError(f"waited {timeout:.0f}s for another request to load {key!r}")
            if flight.error is not None:
                raise flight.error
            return flight.value
        try:
            flight.value = loader()
            self.put(key, flight.value)
            return flight.value
        except BaseException as exc:
            flight.error = exc
            if cache_errors and isinstance(exc, cache_errors):
                self.put(key, _Error(exc))
            raise
        finally:
            with self._lock:
                self._flights.pop(key, None)
            flight.event.set()


class _Error:
    __slots__ = ("exc",)

    def __init__(self, exc: BaseException):
        self.exc = exc


def _unwrap(val: Any, entry, error_ttl: float, clock) -> Any:
    if isinstance(val, _Error):
        if entry is not None and clock() - entry[0] < error_ttl:
            raise val.exc
        raise _Expired()
    return val


class _Expired(Exception):
    pass


#: The process-wide cache the service's market endpoints share.
CACHE = TTLCache()


def cached(key: Hashable, ttl: float, loader: Callable[[], Any], cache_errors: tuple = (),
           error_ttl: float = 60.0) -> Any:
    try:
        return CACHE.get_or_load(key, ttl, loader, cache_errors=cache_errors, error_ttl=error_ttl)
    except _Expired:
        CACHE.invalidate(key)
        return CACHE.get_or_load(key, ttl, loader, cache_errors=cache_errors, error_ttl=error_ttl)
