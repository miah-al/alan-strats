"""Secrets never leave the service in logs, tracebacks or error bodies."""
import logging

from api.redact import RedactingFilter, redact


def test_query_credentials_are_masked():
    url = "https://api.polygon.io/v2/aggs/ticker/NDX/range/1/minute/x/y?apiKey=abcDEF123456&adjusted=true"
    assert redact(url) == "https://api.polygon.io/v2/aggs/ticker/NDX/range/1/minute/x/y?apiKey=***&adjusted=true"
    assert redact("refresh_token=zzz999&x=1 password=hunter22") == "refresh_token=***&x=1 password=***"


def test_secret_values_from_the_environment_are_masked(monkeypatch):
    monkeypatch.setenv("TT_SECRET", "s3cr3t-value-1234")
    assert redact("header Authorization: s3cr3t-value-1234") == "header Authorization: ***"


def test_filter_masks_message_and_traceback():
    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "GET %s failed", ("https://h/?apiKey=KEY12345678",), None)
    try:
        raise RuntimeError("403 for url https://h/?apiKey=KEY12345678")
    except RuntimeError:
        import sys
        record.exc_info = sys.exc_info()
    RedactingFilter().filter(record)
    assert "KEY12345678" not in record.getMessage()
    assert "KEY12345678" not in record.exc_text
