"""
api/marketdata/providers/tastytrade.py — quotes, index levels and option greeks from tastytrade's
DXLink streamer; option chains (expirations, strikes, symbols) from its REST API.

One streamer connection for the whole service, on its own thread and event loop. Subscriptions are
diffed against what the hub wants (one upstream subscription per symbol, dropped when the last
watcher leaves). The OAuth session is the platform's (``TT_SECRET`` / ``TT_REFRESH`` from .env):
the refresh-token grant mints this process its own access token, so it does not touch the paper
runner's session — both hold independent access tokens from the same refresh token.

Every REST request (the OAuth refresh, the streamer's quote token, option chains) is counted by the
platform's broker ``RequestBudget`` — the same class and the same day file (``paper_state/
broker_calls_<day>.json``) the paper runner uses, so the service and any runner it starts share
one daily cap — and the day's total also includes the counts runners started from other checkouts
publish in their own ``paper_state`` (read, never written). Streaming itself costs no REST budget.
A dropped connection reconnects with backoff (30 s doubling to 15 min); a credential error stops
it and marks the provider down. This module never places, changes or cancels an order.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from datetime import date
from pathlib import Path
from typing import Optional

from api.marketdata import symbols as SYM
from api.marketdata.limits import ProviderLimits
from api.marketdata.providers.base import Emit, Provider
from data.request_gate import ProviderUnavailable

logger = logging.getLogger("alan_trader.api.marketdata.tastytrade")

RECONNECT_START_S = 30.0
RECONNECT_MAX_S = 900.0
CHAIN_TTL_S = 4 * 3600.0          # a nested chain changes with new listings (daily): one REST call per underlying per 4 h
LOCK_RETRY_S = 60.0
SUB_CHUNK = 250


class StreamerLock:
    """One streamer per checkout, across processes: a service started twice from the same checkout
    (by hand and by the desktop app, say) must not open two broker streams. The holder writes its
    pid into ``<paper_state>/tastytrade_streamer.lock``; another process finds a live holder and
    stays off the broker (falling back to the other providers), retrying every minute so it takes
    over when the holder exits. A lock whose pid is gone is stale and is taken over."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.pid = os.getpid()

    def holder(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _alive(pid) -> bool:
        try:
            import psutil
            if not psutil.pid_exists(int(pid)):
                return False
            cmd = " ".join(psutil.Process(int(pid)).cmdline()).lower()
            return "python" in cmd or "api" in cmd
        except Exception:
            return True                                  # cannot tell: assume it is alive (the safe side)

    def acquire(self) -> bool:
        for _ in range(2):
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                h = self.holder()
                if int(h.get("pid") or 0) == self.pid:
                    return True
                if h.get("pid") and self._alive(h["pid"]):
                    return False
                try:                                     # stale: its process is gone
                    self.path.unlink()
                except OSError:
                    return False
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": self.pid, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           "port": os.environ.get("ALAN_TRADER_API_PORT", "8765")}, f)
            return True
        return False

    def release(self) -> None:
        if int(self.holder().get("pid") or 0) == self.pid:
            try:
                self.path.unlink()
            except OSError:
                pass


class ServiceBrokerBudget:
    """The platform's ``RequestBudget`` (5 s between calls, 20 a minute, 3000 a day, a day file
    shared by every process of this checkout), plus the counts other checkouts' runners publish,
    read-only, so the day's cap holds across all of them."""

    def __init__(self, state_dir: Path, external_dirs: list[Path], per_day: int = 3000,
                 min_interval_s: float = 5.0, per_minute: int = 20):
        from paper.providers import RequestBudget
        self.state_dir = Path(state_dir)
        self.external_dirs = [Path(d) for d in external_dirs]
        self._rb = RequestBudget(min_interval_s=min_interval_s, per_minute=per_minute, per_day=per_day,
                                 shared_path=self.state_dir / f"broker_calls_{date.today().isoformat()}.json")
        self._rb.shared_calls = self._read(self._rb.shared_path)
        self.per_day = per_day

    @staticmethod
    def _read(path: Path) -> int:
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
            return int(d.get("calls", 0)) if d.get("date", date.today().isoformat()) == date.today().isoformat() else 0
        except (OSError, ValueError, TypeError):
            return 0

    def external_calls(self) -> int:
        day = date.today().isoformat()
        return sum(self._read(d / f"broker_calls_{day}.json") for d in self.external_dirs)

    def used(self) -> int:
        own = max(self._rb.calls_today, self._rb.shared_calls, self._read(self._rb.shared_path))
        return own + self.external_calls()

    def remaining(self) -> int:
        return max(0, self.per_day - self.used())

    def take(self) -> None:
        if self.used() >= self.per_day:
            raise ProviderUnavailable("tastytrade", f"broker request budget spent: {self.used()} calls today "
                                                    f"across this checkout and runners elsewhere (cap {self.per_day})")
        try:
            self._rb.take()
        except RuntimeError as exc:
            raise ProviderUnavailable("tastytrade", str(exc)) from None

    @property
    def calls_today(self) -> int:
        return self._rb.calls_today


class TastytradeProvider(Provider):
    name = "tastytrade"
    streaming = True
    capabilities = frozenset({"quotes", "options", "greeks", "chain"})
    #: where this provider ranks per chain field group (api/marketdata/options.py; lower first)
    chain_ranks = {"skeleton": 0, "quotes": 0, "greeks": 0, "sizes": 0}

    def __init__(self, limits: ProviderLimits, budget: Optional[ServiceBrokerBudget] = None,
                 credentials: Optional[tuple[str, str]] = None, is_test: bool = False,
                 lock: Optional[StreamerLock] = None):
        super().__init__(limits)
        self.budget = budget
        self.lock = lock
        self._lock_reason: Optional[str] = None
        self._creds = credentials
        self.is_test = is_test
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._want: set[str] = set()
        self._lock = threading.Lock()
        self._wake: Optional[asyncio.Event] = None
        self._session = None
        self._streamer = None
        self.connected = False
        self.connects = 0
        self.events = 0
        self._chains: dict[str, tuple[float, list]] = {}
        self._to_stream: dict[str, str] = {}              # OCC -> the streamer symbol the chain API gave
        self._from_stream: dict[str, str] = {}
        if budget is not None:
            limits.external_remaining = budget.remaining

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self, emit: Emit) -> None:
        super().start(emit)
        if not self._creds:
            self.limits.disable("no tastytrade credentials (TT_SECRET / TT_REFRESH in .env)")
            return
        try:
            import tastytrade  # noqa: F401
        except Exception:
            self.limits.disable("tastytrade SDK not installed")
            return
        logging.getLogger("tastytrade").setLevel(logging.WARNING)   # the SDK logs every frame at DEBUG
        if self.budget is None:
            self.limits.disable("no broker request budget configured")
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="tastytrade-streamer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._wake_up)
            except RuntimeError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=10)

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception:
            logger.exception("tastytrade streamer thread ended")
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    def _wake_up(self) -> None:
        if self._wake is not None:
            self._wake.set()

    # ── what the hub asks ─────────────────────────────────────────────────────
    def supports(self, symbol: str) -> bool:
        return self.connected and self.available()

    def subscribe(self, symbols: list[str]) -> None:
        with self._lock:
            self._want.update(symbols)
        self._poke()

    def unsubscribe(self, symbols: list[str]) -> None:
        with self._lock:
            self._want.difference_update(symbols)
        self._poke()

    def wanted(self) -> set[str]:
        with self._lock:
            return set(self._want)

    def _poke(self) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._wake_up)
            except RuntimeError:
                pass

    # ── the connection ────────────────────────────────────────────────────────
    async def _take(self) -> None:
        """One REST request's worth of budget (the RequestBudget sleeps: keep it off the loop)."""
        self.limits.check()
        await asyncio.to_thread(self.budget.take)
        self.limits.acquire("rest", max_wait=0)

    async def _refresh(self, force: bool = False) -> None:
        s = self._session
        if s is None:
            raise ProviderUnavailable(self.name, "no session")
        if not force and time.time() < s.session_expiration - 120:
            return
        await self._take()
        await s.refresh(force=True)

    async def _main(self) -> None:
        from tastytrade import DXLinkStreamer, Session
        self._wake = asyncio.Event()
        delay = RECONNECT_START_S
        secret, refresh = self._creds
        try:
            while not self._stop.is_set():
                if not await self._hold_lock():
                    continue
                delay = await self._connect_once(DXLinkStreamer, Session, secret, refresh, delay)
        finally:
            if self.lock is not None:
                self.lock.release()
        self.limits.note("stopped")

    async def _hold_lock(self) -> bool:
        """True when this process may stream; otherwise waits a minute (the hub serves from the
        fallbacks meanwhile) and returns False."""
        if self.lock is None or self.lock.acquire():
            if self._lock_reason is not None and self.limits.disabled_reason == self._lock_reason:
                self.limits.disable(None)
            self._lock_reason = None
            return True
        h = self.lock.holder()
        reason = (f"another service process (pid {h.get('pid')}, port {h.get('port')}) holds the tastytrade "
                  f"streamer for this checkout; retrying every {LOCK_RETRY_S:.0f}s")
        if self._lock_reason != reason:
            logger.info("tastytrade: %s", reason)
        self._lock_reason = reason
        self.limits.disable(reason)
        try:
            await asyncio.wait_for(self._wait_stop(), timeout=LOCK_RETRY_S)
        except asyncio.TimeoutError:
            pass
        return False

    async def _connect_once(self, DXLinkStreamer, Session, secret: str, refresh: str, delay: float) -> float:
        """One connection's life, then the wait before the next; returns the next backoff."""
        try:
            self.limits.note("connecting")
            async with Session(secret, refresh, is_test=self.is_test) as session:
                self._session = session
                await self._refresh(force=True)
                await self._take()                            # the streamer's /api-quote-tokens
                async with DXLinkStreamer(session) as st:
                    self._streamer = st
                    self.connected = True
                    self.connects += 1
                    self.limits.ok()
                    self.limits.note(f"DXLink streamer connected (connection #{self.connects})")
                    logger.info("tastytrade DXLink streamer connected")
                    delay = RECONNECT_START_S
                    await self._serve(st)
            if self._stop.is_set():
                return delay
        except ProviderUnavailable as exc:
            self.limits.note(f"not connecting: {exc.reason}")
            logger.warning("tastytrade: %s", exc)
            delay = max(delay, 300.0)
        except Exception as exc:  # noqa: BLE001 — any failure: report, back off, reconnect
            msg = f"{type(exc).__name__}: {exc}"
            if any(k in msg.lower() for k in ("invalid_grant", "invalid_client", "secret mismatch")):
                self.limits.disable("tastytrade rejected the credentials (TT_SECRET / TT_REFRESH)")
                logger.error("tastytrade rejected the credentials; streaming disabled")
                self._stop.set()
                return delay
            self.limits.fail(f"streamer: {msg[:200]}")
        finally:
            self._down()
            self._session = None
        if self._stop.is_set():
            return delay
        self.limits.note(f"reconnecting in {delay:.0f}s")
        try:
            await asyncio.wait_for(self._wait_stop(), timeout=delay)
        except asyncio.TimeoutError:
            pass
        return min(delay * 2, RECONNECT_MAX_S)

    def _down(self) -> None:
        self.connected = False
        self._streamer = None

    async def _wait_stop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(0.5)

    async def _serve(self, st) -> None:
        from tastytrade.dxfeed import Greeks, Quote, Summary, Trade
        pumps = [asyncio.create_task(self._pump(st, cls)) for cls in (Quote, Trade, Summary, Greeks)]
        have: set[str] = set()
        try:
            while not self._stop.is_set():
                for t in pumps:
                    if t.done():                                  # a listener died: the connection is gone
                        exc = t.exception()
                        raise exc if exc else ConnectionError("streamer listener ended")
                want = self.wanted()
                add, rem = sorted(want - have), sorted(have - want)
                if add:
                    await self._sub(st, add, True)
                    have.update(add)
                if rem:
                    await self._sub(st, rem, False)
                    have.difference_update(rem)
                if time.time() > self._session.session_expiration - 120:
                    try:
                        await self._refresh()                     # keep REST usable for chains
                    except ProviderUnavailable as exc:
                        self.limits.note(f"streaming; REST paused: {exc.reason}")
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
        finally:
            for t in pumps:
                t.cancel()

    async def _sub(self, st, syms: list[str], add: bool) -> None:
        from tastytrade.dxfeed import Greeks, Quote, Summary, Trade
        stream = [self._stream_sym(s) for s in syms]
        opts = [self._stream_sym(s) for s in syms if SYM.is_option(s)]
        # in chunks: a subscription message over the socket's frame limit closes the connection
        for i in range(0, len(stream), SUB_CHUNK):
            part = stream[i:i + SUB_CHUNK]
            for cls in (Quote, Trade, Summary):
                await (st.subscribe(cls, part) if add else st.unsubscribe(cls, part))
        for i in range(0, len(opts), SUB_CHUNK):
            part = opts[i:i + SUB_CHUNK]
            await (st.subscribe(Greeks, part) if add else st.unsubscribe(Greeks, part))
        logger.debug("tastytrade %s %d symbols", "subscribed" if add else "unsubscribed", len(syms))

    def _stream_sym(self, sym: str) -> str:
        return self._to_stream.get(sym) or SYM.to_streamer(sym)

    async def _pump(self, st, cls) -> None:
        name = cls.__name__
        async for ev in st.listen(cls):
            try:
                self._handle(name, ev)
            except Exception:
                logger.debug("bad %s event", name, exc_info=True)

    def _handle(self, kind: str, ev) -> None:
        raw = str(ev.event_symbol)
        sym = self._from_stream.get(raw) or SYM.from_streamer(raw)
        self.events += 1
        g = getattr
        if kind == "Quote":
            t = max(g(ev, "bid_time", 0) or 0, g(ev, "ask_time", 0) or 0) / 1000.0 or None
            self.emit(sym, self.name, t, bid=ev.bid_price, ask=ev.ask_price,
                      bid_size=g(ev, "bid_size", None), ask_size=g(ev, "ask_size", None))
        elif kind == "Trade":
            t = (g(ev, "time", 0) or 0) / 1000.0 or None
            self.emit(sym, self.name, t, last=ev.price, volume=g(ev, "day_volume", None))
        elif kind == "Summary":
            self.emit(sym, self.name, None, prev_close=g(ev, "prev_day_close_price", None),
                      open=g(ev, "day_open_price", None), high=g(ev, "day_high_price", None),
                      low=g(ev, "day_low_price", None), oi=g(ev, "open_interest", None))
        elif kind == "Greeks":
            t = (g(ev, "time", 0) or 0) / 1000.0 or None
            self.emit(sym, self.name, t, iv=ev.volatility, delta=ev.delta, gamma=ev.gamma, theta=ev.theta,
                      vega=ev.vega, theo=ev.price)

    # ── option chains (REST, cached) ─────────────────────────────────────────
    def _call(self, coro, timeout: float = 60.0):
        loop = self._loop
        if loop is None or loop.is_closed() or self._session is None:
            coro.close()
            raise ProviderUnavailable(self.name, "not connected")
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)

    def _nested(self, underlying: str) -> list:
        hit = self._chains.get(underlying)
        if hit is not None and time.monotonic() - hit[0] < CHAIN_TTL_S:
            return hit[1]

        async def fetch():
            from tastytrade.instruments import NestedOptionChain
            await self._refresh()
            await self._take()
            return await NestedOptionChain.get(self._session, underlying)

        chains = self._call(fetch())
        self._chains[underlying] = (time.monotonic(), list(chains))
        return list(chains)

    def expirations(self, underlying: str, root: Optional[str] = None) -> list[date]:
        out = set()
        for ch in self._nested(underlying):
            if root is not None and ch.root_symbol != root:
                continue
            for e in ch.expirations:
                out.add(e.expiration_date)
        return sorted(d for d in out if d >= date.today())

    def chain_contracts(self, underlying: str, expiry: date, root: Optional[str] = None) -> list[tuple[float, str, str]]:
        """[(strike, call OCC, put OCC)] for one expiry. Where two roots expire the same day (SPX's
        AM monthly and PM weekly) the requested ``root`` is used, else the PM-settled one."""
        cands = []
        for ch in self._nested(underlying):
            for e in ch.expirations:
                if e.expiration_date == expiry:
                    cands.append((str(getattr(e, "settlement_type", "") or "").upper(), ch.root_symbol, e))
        if not cands:
            return []
        cands.sort(key=lambda c: (root is not None and c[1] != root, c[0] != "PM", c[1] != underlying))
        if root is not None and cands[0][1] != root:
            return []
        _, _, exp = cands[0]
        out = []
        for s in exp.strikes:
            try:
                call, put = SYM.normalize(s.call), SYM.normalize(s.put)
            except ValueError:
                continue
            for occ, stream in ((call, getattr(s, "call_streamer_symbol", "")), (put, getattr(s, "put_streamer_symbol", ""))):
                if stream:
                    self._to_stream[occ] = stream
                    self._from_stream[stream] = occ
            out.append((float(s.strike_price), call, put))
        return sorted(out)

    def status_detail(self) -> dict:
        return {"connected": self.connected, "connects": self.connects, "events": self.events,
                "subscriptions": len(self.wanted()),
                "broker_calls_today": self.budget.calls_today if self.budget else None,
                "broker_budget_remaining": self.budget.remaining() if self.budget else None}
