"""
api/events.py — the ``/api/events`` WebSocket hub.

Messages (server → client, JSON):
  {"type": "hello", "version": "..."}                  on connect
  {"type": "job", "job": Job}                           every job state / progress change
  {"type": "log", "time", "level", "logger", "message"} log records >= INFO
  {"type": "heartbeat", "time"}                         every 15 s

``publish()`` is thread-safe: worker threads (jobs, request threadpool, logging from
anywhere) hand messages to the event loop with ``loop.call_soon_threadsafe``.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import threading
from typing import Optional

HEARTBEAT_SECONDS = 15.0
_QUEUE_MAX = 2000

#: Loggers never forwarded: per-request access lines and the transport's own chatter
#: would drown the useful records (and a record about sending a record would recurse).
_MUTED_PREFIXES = ("uvicorn.access", "httpx", "httpcore", "websockets", "asyncio",
                   "watchfiles", "alan_trader.api.events", "multipart", "peewee")


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


class EventHub:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self.version = ""

    # ── lifecycle ────────────────────────────────────────────────────────────
    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def unbind(self) -> None:
        self._loop = None
        with self._lock:
            clients = list(self._clients)
            self._clients.clear()
        for q in clients:
            try:
                q.put_nowait(None)          # wake the sender so the socket closes
            except asyncio.QueueFull:
                pass

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    # ── subscription (event-loop side) ───────────────────────────────────────
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        with self._lock:
            self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._clients.discard(q)

    def _fanout(self, msg: dict) -> None:
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:     # a stalled client loses messages, never blocks the hub
                pass

    # ── publishing (any thread) ──────────────────────────────────────────────
    def publish(self, msg: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._fanout(msg)
        else:
            try:
                loop.call_soon_threadsafe(self._fanout, msg)
            except RuntimeError:          # loop shutting down
                pass

    async def heartbeat_forever(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            self._fanout({"type": "heartbeat", "time": now_iso()})


class LogForwarder(logging.Handler):
    """Forwards log records >= INFO to the hub as ``{"type": "log", ...}``."""

    def __init__(self, hub: EventHub, level: int = logging.INFO) -> None:
        super().__init__(level)
        self.hub = hub

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(_MUTED_PREFIXES)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                msg = f"{msg} ({type(record.exc_info[1]).__name__}: {record.exc_info[1]})"
            self.hub.publish({
                "type": "log",
                "time": _dt.datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": msg,
            })
        except Exception:                 # logging must never raise
            self.handleError(record)
