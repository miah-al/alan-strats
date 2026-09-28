"""
api/marketdata/hub.py — the market-data hub: who watches what, who serves it, who hears about it.

Watchers (a ``/api/stream`` client, the alert engine, the paper order book, a one-off snapshot)
watch symbols; the hub keeps one upstream subscription per symbol however many watch it and drops
it when the last one leaves (snapshot watchers linger a minute so a burst of requests for the same
symbol is one subscription). Each watched symbol is *routed* to the first provider in preference
order that can serve it now — the tastytrade streamer while it is connected, else Polygon, else
yfinance — and re-routed when a provider connects, degrades or goes down.

Streaming providers push partial updates through ``emit`` (any thread); polling providers are
polled by the hub's tick, never faster than their ``poll_interval`` (>= 15 s) per batch. Updates
merge into one ``QuoteState`` per symbol and fan out to stream clients at most 4 times a second per
symbol (the latest state wins), then to listeners (alerts, working orders).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from api.marketdata import symbols as SYM
from api.marketdata.limits import CONNECTED, DEGRADED, DOWN, Gate
from api.marketdata.model import QuoteState, empty_quote
from api.marketdata.providers.base import Provider
from data.request_gate import ProviderUnavailable

logger = logging.getLogger("alan_trader.api.marketdata.hub")

MIN_SEND_INTERVAL_S = 0.25          # <= 4 quote messages / s per symbol
QUOTE_PROVIDERS = ("tastytrade", "polygon", "yfinance")
SNAPSHOT_LINGER_S = 60.0
MIN_POLL_INTERVAL_S = 15.0
CLIENT_QUEUE_MAX = 5000
TICK_S = 1.0


@dataclass
class StreamClient:
    id: str
    queue: asyncio.Queue
    symbols: set = field(default_factory=set)
    dropped: int = 0


class MarketDataHub:
    def __init__(self, gate: Gate, providers: list[Provider]):
        self.gate = gate
        self.providers = list(providers)
        self.by_name = {p.name: p for p in self.providers}
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self.quotes: dict[str, QuoteState] = {}
        self.watchers: dict[str, set[str]] = {}          # symbol -> watcher ids
        self.linger: dict[str, float] = {}               # symbol -> monotonic deadline of a snapshot watch
        self.route: dict[str, str] = {}                  # symbol -> provider name
        self.clients: dict[str, StreamClient] = {}
        self.listeners: list[Callable[[str, dict], None]] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._pending: set[str] = set()
        self._last_sent: dict[str, float] = {}
        self._next_poll: dict[str, float] = {}
        self._polling: set[str] = set()
        self._poll_now: set[str] = set()
        self._states: dict[str, str] = {}
        self._tick_task: Optional[asyncio.Task] = None
        self._wake: Optional[asyncio.Event] = None
        self.started = False
        self.messages_sent = 0

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._loop = loop or asyncio.get_running_loop()
        self._wake = asyncio.Event()
        for p in self.providers:
            try:
                p.start(self.emit)
            except Exception:
                logger.exception("provider %s failed to start", p.name)
        self._states = {p.name: p.state() for p in self.providers}
        self._tick_task = self._loop.create_task(self._tick_forever())
        self.started = True

    def add_provider(self, p: Provider, first: bool = False) -> None:
        """Add a provider (tests inject fakes this way); started at once when the hub runs."""
        self.providers.insert(0, p) if first else self.providers.append(p)
        self.by_name[p.name] = p
        if self.started:
            p.start(self.emit)
            self._states[p.name] = p.state()

    async def stop(self) -> None:
        if self._tick_task is not None:
            self._tick_task.cancel()
        for p in self.providers:
            try:
                await asyncio.to_thread(p.stop)
            except Exception:
                logger.debug("provider %s stop failed", p.name, exc_info=True)
        with self._lock:
            clients = list(self.clients.values())
        for c in clients:
            try:
                c.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
        self.started = False

    # ── watching ──────────────────────────────────────────────────────────────
    def watch(self, owner: str, symbols: Iterable[str]) -> list[str]:
        """``owner`` watches ``symbols`` (canonical spellings returned); upstream subscribes on first watch."""
        added = []
        syms = [SYM.normalize(s) for s in symbols]
        with self._lock:
            for s in syms:
                w = self.watchers.setdefault(s, set())
                if not w:
                    added.append(s)
                w.add(owner)
        for s in added:
            self._assign(s)
        return syms

    def unwatch(self, owner: str, symbols: Iterable[str]) -> None:
        dropped = []
        with self._lock:
            for s in symbols:
                try:
                    s = SYM.normalize(s)
                except ValueError:
                    continue
                w = self.watchers.get(s)
                if not w:
                    continue
                w.discard(owner)
                if not w and self.linger.get(s, 0) <= time.monotonic():
                    dropped.append(s)
        for s in dropped:
            self._release(s)

    def unwatch_all(self, owner: str) -> None:
        with self._lock:
            mine = [s for s, w in self.watchers.items() if owner in w]
        self.unwatch(owner, mine)

    def watching(self, owner: str) -> set[str]:
        with self._lock:
            return {s for s, w in self.watchers.items() if owner in w}

    def _watched(self, s: str) -> bool:
        return bool(self.watchers.get(s)) or self.linger.get(s, 0) > time.monotonic()

    def _best(self, s: str) -> Optional[Provider]:
        for p in self.providers:
            try:
                if p.supports(s):
                    return p
            except Exception:
                continue
        return None

    def _assign(self, s: str) -> None:
        p = self._best(s)
        with self._lock:
            old = self.route.get(s)
            if p is None:
                self.route.pop(s, None)
            else:
                self.route[s] = p.name
        if old == (p.name if p else None):
            return
        if old is not None:
            self._drop_from(old, s)
        if p is not None:
            if p.streaming:
                p.subscribe([s])
            else:
                with self._lock:
                    self._poll_now.add(p.name)

    def _drop_from(self, name: str, s: str) -> None:
        p = self.by_name.get(name)
        if p is not None and p.streaming:
            try:
                p.unsubscribe([s])
            except Exception:
                logger.debug("unsubscribe %s from %s failed", s, name, exc_info=True)

    def _release(self, s: str) -> None:
        with self._lock:
            if self._watched(s):
                return
            name = self.route.pop(s, None)
            self.watchers.pop(s, None)
            self.linger.pop(s, None)
        if name is not None:
            self._drop_from(name, s)

    # ── updates from providers (any thread) ───────────────────────────────────
    def emit(self, symbol: str, source: str, event_time: Optional[float] = None, **fields) -> None:
        with self._lock:
            q = self.quotes.get(symbol)
            if q is None:
                q = self.quotes[symbol] = QuoteState(symbol)
            changed = q.update(source, event_time, **fields)
            watched = self._watched(symbol)
            self._cond.notify_all()
        if changed and watched:
            loop = self._loop
            if loop is not None and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(self._request_flush, symbol)
                except RuntimeError:
                    pass

    def _request_flush(self, symbol: str) -> None:
        if symbol in self._pending:
            return
        self._pending.add(symbol)
        wait = max(0.0, self._last_sent.get(symbol, 0.0) + MIN_SEND_INTERVAL_S - time.monotonic())
        self._loop.call_later(wait, self._flush, symbol)

    def _flush(self, symbol: str) -> None:
        self._pending.discard(symbol)
        self._last_sent[symbol] = time.monotonic()
        with self._lock:
            q = self.quotes.get(symbol)
            msg = q.to_message() if q is not None else None
            targets = [c for c in self.clients.values() if symbol in c.symbols]
            listeners = list(self.listeners)
        if msg is None:
            return
        for c in targets:
            self._send(c, msg)
        for fn in listeners:
            try:
                fn(symbol, msg)
            except Exception:
                logger.exception("quote listener failed")

    def _send(self, c: StreamClient, msg: dict) -> None:
        try:
            c.queue.put_nowait(msg)
            self.messages_sent += 1
        except asyncio.QueueFull:
            c.dropped += 1

    # ── stream clients (event-loop side) ──────────────────────────────────────
    def connect(self) -> StreamClient:
        c = StreamClient(id="ws-" + uuid.uuid4().hex[:10], queue=asyncio.Queue(maxsize=CLIENT_QUEUE_MAX))
        with self._lock:
            self.clients[c.id] = c
        for st in self.statuses():
            self._send(c, st)
        return c

    def disconnect(self, c: StreamClient) -> None:
        with self._lock:
            self.clients.pop(c.id, None)
        self.unwatch_all(c.id)

    def client_subscribe(self, c: StreamClient, symbols: Iterable[str]) -> tuple[list[str], list[str]]:
        ok, bad = [], []
        for s in symbols:
            try:
                ok.append(SYM.normalize(s))
            except ValueError:
                bad.append(str(s))
        with self._lock:
            c.symbols.update(ok)
        self.watch(c.id, ok)
        with self._lock:
            ready = [self.quotes[s].to_message() for s in ok if s in self.quotes and self.quotes[s].has_price]
        for m in ready:
            self._send(c, m)
        return ok, bad

    def client_unsubscribe(self, c: StreamClient, symbols: Iterable[str]) -> list[str]:
        syms = []
        for s in symbols:
            try:
                syms.append(SYM.normalize(s))
            except ValueError:
                continue
        with self._lock:
            c.symbols.difference_update(syms)
        self.unwatch(c.id, syms)
        return syms

    def broadcast(self, msg: dict) -> None:
        with self._lock:
            clients = list(self.clients.values())
        for c in clients:
            self._send(c, msg)

    # ── snapshots (any thread) ────────────────────────────────────────────────
    def _fresh(self, s: str) -> bool:
        q = self.quotes.get(s)
        if q is None or not q.has_price:
            return False
        name = self.route.get(s)
        p = self.by_name.get(name) if name else None
        age = q.age() or 0.0
        if p is not None and p.streaming and self._watched(s) and q.source == p.name:
            return True                                 # a live subscription keeps it current
        limit = (max(p.poll_interval, MIN_POLL_INTERVAL_S) + 5.0) if p is not None and not p.streaming else 5.0
        return age <= limit

    def snapshot(self, symbols: Iterable[str], wait: float = 3.0) -> list[dict]:
        """Current quotes for ``symbols``: cached where fresh, otherwise watched for a minute (one
        upstream subscription) and waited for up to ``wait`` seconds."""
        syms = []
        for s in symbols:
            try:
                syms.append(SYM.normalize(s))
            except ValueError as exc:
                syms.append(("!", str(s), str(exc)))
        real = [s for s in syms if isinstance(s, str)]
        with self._lock:
            need = [s for s in real if not self._fresh(s)]
            deadline = time.monotonic() + SNAPSHOT_LINGER_S
            for s in need:
                self.linger[s] = max(self.linger.get(s, 0.0), deadline)
            fresh_route = [s for s in need if s not in self.route]
        for s in fresh_route:
            self._assign(s)
        if need:
            with self._lock:
                for s in need:
                    name = self.route.get(s)
                    if name and not self.by_name[name].streaming:
                        self._poll_now.add(name)
            self._poke()
            end = time.monotonic() + max(0.0, wait)
            with self._cond:
                while time.monotonic() < end:
                    if all((self.quotes.get(s) is not None and self.quotes[s].has_price) for s in need):
                        break
                    self._cond.wait(timeout=min(0.2, max(0.0, end - time.monotonic())))
        out = []
        with self._lock:
            for s in syms:
                if not isinstance(s, str):
                    out.append(empty_quote(s[1], s[2]))
                    continue
                q = self.quotes.get(s)
                if q is not None and q.has_price:
                    out.append(q.to_message())
                else:
                    reason = "no provider can serve this symbol now" if s not in self.route else \
                        f"no data yet from {self.route[s]}"
                    out.append(empty_quote(s, reason))
        return out

    def quote(self, symbol: str, wait: float = 3.0) -> dict:
        return self.snapshot([symbol], wait)[0]

    def price(self, symbol: str, wait: float = 3.0) -> Optional[float]:
        """A number to value ``symbol`` at: an index at its last level (its bid/ask is a synthetic
        band), anything else at the mid when two-sided, else the last trade."""
        m = self.quote(symbol, wait)
        order = ("last", "mid") if SYM.is_index(m.get("symbol") or symbol) else ("mid", "last")
        for k in order:
            if m.get(k) is not None:
                return float(m[k])
        return None

    def _poke(self) -> None:
        """Run the tick now (new symbols to poll) instead of at the next second."""
        loop, wake = self._loop, self._wake
        if loop is not None and wake is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(wake.set)
            except RuntimeError:
                pass

    # ── status ────────────────────────────────────────────────────────────────
    def providers_status(self) -> list[dict]:
        out = []
        for p in self.providers:
            d = p.limits.snapshot()
            with self._lock:
                d["symbols"] = sum(1 for s, n in self.route.items() if n == p.name)
            d["streaming"] = p.streaming
            extra = getattr(p, "status_detail", None)
            if callable(extra):
                try:
                    d["stream"] = extra()
                except Exception:
                    pass
            out.append(d)
        for name, lim in self.gate.providers.items():
            if name not in self.by_name:
                d = lim.snapshot()
                d["streaming"] = False
                d["symbols"] = 0
                if name in QUOTE_PROVIDERS:
                    d["state"] = DOWN
                    d["detail"] = "not enabled as a quote provider (ALAN_TRADER_PROVIDERS); its requests are still gated"
                else:
                    d["detail"] = d["detail"] or "request gate only (the service's own downloads)"
                out.append(d)
        return out

    def statuses(self) -> list[dict]:
        return [{"type": "status", "provider": p.name, "state": p.state(),
                 "detail": p.limits.detail or (p.limits.disabled_reason or "") or (p.limits.last_error or "")}
                for p in self.providers]

    # ── the tick: expiry of lingering watches, re-routing, polling, status changes ──
    async def _tick_forever(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("market-data hub tick failed")
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=TICK_S)
            except asyncio.TimeoutError:
                pass
            self._wake.clear()

    async def _tick(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [s for s, d in self.linger.items() if d <= now]
            for s in expired:
                self.linger.pop(s, None)
            expired = [s for s in expired if not self.watchers.get(s)]
        for s in expired:
            self._release(s)
        # status changes -> stream clients; a provider coming or going re-routes its symbols
        changed = False
        for p in self.providers:
            st = p.state()
            if self._states.get(p.name) != st:
                self._states[p.name] = st
                changed = True
                detail = p.limits.detail or p.limits.disabled_reason or p.limits.last_error or ""
                logger.info("market data: %s is %s%s", p.name, st, f" ({detail})" if detail else "")
                self.broadcast({"type": "status", "provider": p.name, "state": st, "detail": detail})
        self._reroute(force=changed)
        # polling
        with self._lock:
            by_provider: dict[str, list[str]] = {}
            for s, name in self.route.items():
                if self._watched(s):
                    by_provider.setdefault(name, []).append(s)
            poll_now = set(self._poll_now)
            self._poll_now.clear()
        for name, syms in by_provider.items():
            p = self.by_name.get(name)
            if p is None or p.streaming or name in self._polling:
                continue
            due = self._next_poll.get(name, 0.0)
            if now < due and name not in poll_now:
                continue
            if name in poll_now and now < due:
                # new symbols between regular polls: fetch just those that have no data yet
                with self._lock:
                    syms = [s for s in syms if not (s in self.quotes and self.quotes[s].has_price)]
                if not syms:
                    continue
            else:
                self._next_poll[name] = now + max(p.poll_interval, MIN_POLL_INTERVAL_S)
            self._polling.add(name)
            self._loop.create_task(self._poll(p, syms))

    def _reroute(self, force: bool = False) -> None:
        with self._lock:
            watched = [s for s in set(self.watchers) | set(self.linger) if self._watched(s)]
            current = dict(self.route)
        for s in watched:
            best = self._best(s)
            if (best.name if best else None) != current.get(s):
                self._assign(s)

    async def _poll(self, p: Provider, syms: list[str]) -> None:
        try:
            got = await asyncio.to_thread(p.poll, syms)
            for s, d in (got or {}).items():
                self.emit(s, p.name, d.get("time"), **(d.get("fields") or {}))
        except ProviderUnavailable as exc:
            logger.info("poll %s skipped: %s", p.name, exc.reason)
        except Exception as exc:  # noqa: BLE001
            p.limits.fail(f"poll: {type(exc).__name__}: {exc}", backoff=False)
            logger.warning("poll %s failed: %s", p.name, exc)
        finally:
            self._polling.discard(p.name)


def state_rank(state: str) -> int:
    return {CONNECTED: 0, DEGRADED: 1, DOWN: 2}.get(state, 3)
