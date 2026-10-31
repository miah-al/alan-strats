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


def test_job_errors_messages_and_results_are_redacted(monkeypatch):
    import time
    from api.jobs import JobError, JobManager
    monkeypatch.setenv("POLYGON_API_KEY", "SECRETKEY1234567890")
    jm = JobManager(max_workers=1)
    url = "https://api.polygon.io/v2/aggs/x?limit=5&apiKey=SECRETKEY1234567890"

    def fails(ctx):
        ctx.progress(0.5, f"fetching {url}")
        raise JobError(f"403 for url: {url}")

    def returns(ctx):
        return {"results": [{"detail": f"HTTPError for url: {url}"}]}

    a, b = jm.submit("sync", "a", fails), jm.submit("sync", "b", returns)
    for _ in range(100):
        if jm.get(a.id).status in ("failed",) and jm.get(b.id).status == "succeeded":
            break
        time.sleep(0.05)
    for j in (jm.get(a.id), jm.get(b.id)):
        text = str(j.to_dict(include_result=True))
        assert "SECRETKEY1234567890" not in text and ("apiKey=***" in text or "***" in text)
    jm.shutdown()
    from db.sync_jobs import _mask_urls
    assert _mask_urls(url).endswith("apiKey=***")
