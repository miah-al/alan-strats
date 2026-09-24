"""
data/request_gate.py — one gate every outbound market-data request of the process passes.

The platform talks to its data vendors from many places (PolygonClient, yfinance helpers, FRED
CSV downloads in the sync jobs and the Market page, strategy plugins' own calls). A process that
must never get its keys rate-limited or its IP blocked — the service — installs a *gate* here and
then turns on the hooks, and from then on every such request asks the gate first:

  * ``requests`` (Polygon, FRED, anything else over ``requests``): ``HTTPAdapter.send`` is wrapped,
    and the request's host names its provider;
  * yfinance (curl_cffi underneath): ``YfData._make_request`` is wrapped.

``gate.acquire(provider, kind)`` may wait briefly for a token or raise ``ProviderUnavailable``
(over budget, backing off after a 429/5xx); ``gate.record(provider, status, exc)`` reports the
outcome so the gate can back off. With no gate installed (the Dash app, the paper runner, scripts)
nothing changes: the hooks are only installed by a process that asks for them.
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Optional, Protocol
from urllib.parse import urlsplit

logger = logging.getLogger("data.request_gate")


class ProviderUnavailable(RuntimeError):
    """The gate refused a request: the provider is over its budget or backing off.

    Deliberately not a ``requests.RequestException``: a client's own retry loop must not
    retry it (retrying is exactly what the gate is preventing)."""

    def __init__(self, provider: str, reason: str, retry_after: Optional[float] = None):
        super().__init__(f"{provider}: {reason}")
        self.provider = provider
        self.reason = reason
        self.retry_after = retry_after


class Gate(Protocol):
    def acquire(self, provider: str, kind: str = "") -> None: ...

    def record(self, provider: str, status: Optional[int], exc: Optional[BaseException] = None) -> None: ...


_GATE: Optional[Gate] = None
_LOCK = threading.Lock()
_HOOKS: dict = {}

#: host (suffix) -> provider name
HOSTS = {
    "api.polygon.io": "polygon",
    "fred.stlouisfed.org": "fred",
    "api.stlouisfed.org": "fred",
    "finance.yahoo.com": "yfinance",
    "yahoo.com": "yfinance",
    "api.tastyworks.com": "tastytrade",
    "api.tastytrade.com": "tastytrade",
    "api.cert.tastyworks.com": "tastytrade",
}


def install(gate: Optional[Gate]) -> None:
    """Make ``gate`` the process's gate (None removes it; the hooks then pass through)."""
    global _GATE
    _GATE = gate


def installed() -> Optional[Gate]:
    return _GATE


def provider_for_url(url: str) -> Optional[str]:
    try:
        host = (urlsplit(str(url)).hostname or "").lower()
    except ValueError:
        return None
    for suffix, name in HOSTS.items():
        if host == suffix or host.endswith("." + suffix):
            return name
    return None


def polygon_kind(url: str) -> str:
    """Polygon's plans are per asset class: options endpoints are paid, stock ones the free tier."""
    path = urlsplit(str(url)).path
    return "options" if ("/options/" in path or "/ticker/O:" in path or "/O:" in path) else "stocks"


def acquire(provider: str, kind: str = "") -> None:
    g = _GATE
    if g is not None:
        g.acquire(provider, kind)


def record(provider: str, status: Optional[int], exc: Optional[BaseException] = None) -> None:
    g = _GATE
    if g is not None:
        try:
            g.record(provider, status, exc)
        except Exception:                      # accounting must never break a request
            logger.debug("gate.record failed", exc_info=True)


@contextmanager
def call(provider: str, kind: str = ""):
    """``with call("fred"): ...`` — acquire, run, record (a status of 200 when the block completes)."""
    acquire(provider, kind)
    try:
        yield
    except ProviderUnavailable:
        raise
    except BaseException as exc:
        record(provider, getattr(getattr(exc, "response", None), "status_code", None), exc)
        raise
    else:
        record(provider, 200, None)


# ── hooks ─────────────────────────────────────────────────────────────────────

def _install_requests_hook() -> None:
    from requests.adapters import HTTPAdapter
    if "requests" in _HOOKS:
        return
    original = HTTPAdapter.send

    def send(self, request, *args, **kwargs):
        provider = provider_for_url(request.url) if _GATE is not None else None
        if provider is None:
            return original(self, request, *args, **kwargs)
        kind = polygon_kind(request.url) if provider == "polygon" else ""
        acquire(provider, kind)
        try:
            resp = original(self, request, *args, **kwargs)
        except BaseException as exc:
            record(provider, None, exc)
            raise
        record(provider, resp.status_code, None)
        return resp

    send.__wrapped__ = original              # type: ignore[attr-defined]
    HTTPAdapter.send = send
    _HOOKS["requests"] = (HTTPAdapter, original)


def _install_yfinance_hook() -> None:
    if "yfinance" in _HOOKS:
        return
    try:
        from yfinance.data import YfData
    except Exception:                         # yfinance not installed: nothing to gate
        return
    original = YfData._make_request

    def _make_request(self, url, request_method, *args, **kwargs):
        if _GATE is None:
            return original(self, url, request_method, *args, **kwargs)
        acquire("yfinance", "")
        try:
            resp = original(self, url, request_method, *args, **kwargs)
        except BaseException as exc:
            status = 429 if "RateLimit" in type(exc).__name__ else None
            record("yfinance", status, exc)
            raise
        record("yfinance", getattr(resp, "status_code", None), None)
        return resp

    _make_request.__wrapped__ = original      # type: ignore[attr-defined]
    YfData._make_request = _make_request
    _HOOKS["yfinance"] = (YfData, original)


def install_hooks() -> None:
    """Route every requests / yfinance call of this process through the gate (idempotent)."""
    with _LOCK:
        _install_requests_hook()
        _install_yfinance_hook()


def uninstall_hooks() -> None:
    with _LOCK:
        hk = _HOOKS.pop("requests", None)
        if hk is not None:
            hk[0].send = hk[1]
        hk = _HOOKS.pop("yfinance", None)
        if hk is not None:
            hk[0]._make_request = hk[1]


def hooks_installed() -> list[str]:
    return sorted(_HOOKS)
