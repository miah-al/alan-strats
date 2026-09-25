"""
api/marketdata/service.py — build the service's hub from the environment.

``ALAN_TRADER_PROVIDERS``: comma-separated providers in preference order (default
``tastytrade,polygon,yfinance``; ``none`` for no quote providers at all — the test suite's default,
so no test ever opens a live stream). The request gate is installed whatever the providers: it
limits every upstream call the service's other endpoints make too.
"""
from __future__ import annotations

import logging
import os

from api.marketdata.hub import MarketDataHub
from api.marketdata.limits import Gate

logger = logging.getLogger("alan_trader.api.marketdata")

DEFAULT_PROVIDERS = "tastytrade,polygon,yfinance"


def provider_names() -> list[str]:
    raw = os.environ.get("ALAN_TRADER_PROVIDERS", DEFAULT_PROVIDERS)
    if raw.strip().lower() in ("", "none", "off"):
        return []
    return [n.strip().lower() for n in raw.split(",") if n.strip()]


def build_hub(names: list[str] | None = None, gate: Gate | None = None) -> MarketDataHub:
    from engine.env import get_polygon_api_key, tastytrade_credentials
    gate = gate or Gate()
    providers = []
    for n in (provider_names() if names is None else names):
        if n == "tastytrade":
            from api.config import external_state_dirs, service_state_dir
            from api.marketdata.providers.tastytrade import ServiceBrokerBudget, StreamerLock, TastytradeProvider
            budget = ServiceBrokerBudget(service_state_dir(), external_state_dirs())
            lock = StreamerLock(service_state_dir() / "tastytrade_streamer.lock")
            providers.append(TastytradeProvider(gate["tastytrade"], budget, tastytrade_credentials(), lock=lock))
        elif n == "polygon":
            from api.marketdata.providers.polygon import PolygonProvider
            providers.append(PolygonProvider(gate["polygon"], get_polygon_api_key()))
        elif n == "yfinance":
            from api.marketdata.providers.yfinance import YFinanceProvider
            providers.append(YFinanceProvider(gate["yfinance"]))
        else:
            logger.warning("unknown market-data provider %r ignored", n)
    return MarketDataHub(gate, providers)
