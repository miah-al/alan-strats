"""
api/marketdata/providers/base.py — what the hub expects of a provider.

A provider is either *streaming* (the hub tells it which symbols it wants; it pushes updates with
``emit``) or *polling* (the hub calls ``poll(symbols)`` on a schedule, never faster than
``poll_interval`` seconds per batch). Both may also answer the option-chain questions
(``expirations`` / ``chain``). Every upstream request goes through the provider's
``ProviderLimits`` (``self.limits``), directly or via the ``data.request_gate`` hooks.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from api.marketdata.limits import CONNECTED, DOWN, ProviderLimits

#: emit(symbol, source, event_time_epoch_or_None, **fields)
Emit = Callable[..., None]


class Provider:
    name = "provider"
    streaming = False
    poll_interval = 15.0
    #: quotes | options | greeks | chain
    capabilities: frozenset = frozenset()

    def __init__(self, limits: ProviderLimits):
        self.limits = limits

    # lifecycle
    def start(self, emit: Emit) -> None:
        self.emit = emit

    def stop(self) -> None:
        pass

    # what it can do right now
    def state(self) -> str:
        return self.limits.state()

    def available(self) -> bool:
        return self.state() != DOWN

    def healthy(self) -> bool:
        return self.state() == CONNECTED

    def supports(self, symbol: str) -> bool:
        return False

    # streaming
    def subscribe(self, symbols: list[str]) -> None:
        raise NotImplementedError

    def unsubscribe(self, symbols: list[str]) -> None:
        raise NotImplementedError

    # polling: {symbol: {"fields": {...}, "time": epoch|None}}
    def poll(self, symbols: list[str]) -> dict[str, dict]:
        raise NotImplementedError

    # options
    def expirations(self, underlying: str) -> list[date]:
        raise NotImplementedError

    def chain(self, underlying: str, expiry: date, spot: Optional[float], strikes: int) -> Optional[dict]:
        """{"rows": [{"strike", "call": {...}, "put": {...}}], "asof", "source"} or None."""
        raise NotImplementedError
