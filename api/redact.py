"""
api/redact.py — keep secrets out of anything the service emits.

Upstream clients put credentials in URLs (Polygon's ``apiKey=``), and a failed request's
exception message carries that URL into tracebacks, log files, the WebSocket log stream and
error responses. ``redact()`` masks credential-looking query parameters and the literal values
of the secrets in the environment; ``RedactingFilter`` applies it to every log record (message
and traceback) before any handler formats it.
"""
from __future__ import annotations

import logging
import os
import re

_PARAM = re.compile(r"(?i)\b(api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|token|secret|password|client[_-]?secret)=([^&\s'\"<>]+)")
_SECRET_ENV = ("POLYGON_API_KEY", "TT_SECRET", "TT_REFRESH", "FRED_API_KEY")


def _secret_values() -> list[str]:
    return [v for v in (os.environ.get(k, "") for k in _SECRET_ENV) if len(v) >= 8]


def redact(text: str) -> str:
    if not text:
        return text
    out = _PARAM.sub(lambda m: f"{m.group(1)}=***", text)
    for value in _secret_values():
        out = out.replace(value, "***")
    return out


class RedactingFilter(logging.Filter):
    """Rewrites a record's message and traceback text with secrets masked (handlers then format the safe text)."""

    _formatter = logging.Formatter()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            safe = redact(message)
            if safe != message:
                record.msg, record.args = safe, None
            if record.exc_info and record.exc_info[1] is not None:
                if not record.exc_text:
                    record.exc_text = self._formatter.formatException(record.exc_info)
                record.exc_text = redact(record.exc_text)
        except Exception:
            pass
        return True


_FILTER = RedactingFilter()


def install_redaction() -> None:
    """Attach the filter to every handler the process has (root, uvicorn's), once."""
    loggers = [logging.getLogger()] + [logging.getLogger(n) for n in ("uvicorn", "uvicorn.error", "uvicorn.access")]
    for lg in loggers:
        for h in lg.handlers:
            if _FILTER not in h.filters:
                h.addFilter(_FILTER)
