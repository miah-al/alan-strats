"""
api/jobs.py — long-running work (screener scans, backtests) off the request path.

A job runs a plain function ``fn(ctx) -> result`` on a thread pool. ``ctx.progress()``
reports progress and is also the cancellation point: once a job is cancelled the next
``progress()`` / ``check()`` raises ``JobCancelled`` and the worker unwinds.
Cancellation is cooperative — a job stuck inside a long library call finishes that
call first — but the job's status becomes ``cancelled`` immediately and whatever the
worker eventually returns is discarded.

Every state or progress change is published as ``{"type": "job", "job": <Job>}``.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from api.events import now_iso
from api.serialize import to_jsonable

logger = logging.getLogger("alan_trader.api.jobs")

QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED = "queued", "running", "succeeded", "failed", "cancelled"
TERMINAL = {SUCCEEDED, FAILED, CANCELLED}


class JobCancelled(BaseException):
    """Raised inside a job when its cancellation was requested.

    A BaseException so that the ``except Exception`` blocks common in the platform
    (and in strategy plugins) do not swallow it."""


class JobError(Exception):
    """A job failure with a message meant for the user (no traceback noise)."""


@dataclass
class Job:
    id: str
    kind: str
    slug: Optional[str]
    title: str
    status: str = QUEUED
    progress: Optional[float] = None
    message: str = ""
    created: str = field(default_factory=now_iso)
    started: Optional[str] = None
    finished: Optional[str] = None
    error: Optional[str] = None
    result: Any = None
    params: dict = field(default_factory=dict)
    cancel_requested: bool = False
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _future: Optional[Future] = field(default=None, repr=False)
    _t0: float = field(default_factory=time.monotonic, repr=False)

    def to_dict(self, include_result: bool = False) -> dict:
        d = {
            "id": self.id, "kind": self.kind, "slug": self.slug, "title": self.title,
            "status": self.status, "progress": self.progress, "message": self.message,
            "created": self.created, "started": self.started, "finished": self.finished,
            "error": self.error, "params": to_jsonable(self.params),
            "cancel_requested": self.cancel_requested,
        }
        if include_result:
            d["result"] = self.result
        return d


class JobContext:
    """What a job function sees: progress reporting + the cancellation check."""

    def __init__(self, manager: "JobManager", job: Job):
        self._m = manager
        self.job = job

    @property
    def cancelled(self) -> bool:
        return self.job._cancel.is_set()

    def check(self) -> None:
        if self.job._cancel.is_set():
            raise JobCancelled()

    def progress(self, fraction: Optional[float] = None, message: Optional[str] = None) -> None:
        self.check()
        changed = False
        if fraction is not None:
            f = max(0.0, min(1.0, float(fraction)))
            if self.job.progress is None or abs(f - self.job.progress) >= 1e-4:
                self.job.progress = round(f, 4)
                changed = True
        if message is not None and message != self.job.message:
            self.job.message = message
            changed = True
        if changed:
            self._m._publish(self.job)


class JobManager:
    def __init__(self, max_workers: int = 2, publish: Optional[Callable[[dict], None]] = None,
                 keep: int = 200):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="api-job")
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._publish_fn = publish
        self._keep = keep

    # ── events ───────────────────────────────────────────────────────────────
    def set_publisher(self, publish: Optional[Callable[[dict], None]]) -> None:
        self._publish_fn = publish

    def _publish(self, job: Job) -> None:
        if self._publish_fn is None:
            return
        try:
            self._publish_fn({"type": "job", "job": job.to_dict(include_result=False)})
        except Exception:
            logger.debug("job event publish failed", exc_info=True)

    # ── API ──────────────────────────────────────────────────────────────────
    def submit(self, kind: str, title: str, fn: Callable[[JobContext], Any], *,
               slug: Optional[str] = None, params: Optional[dict] = None) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, slug=slug, title=title, params=dict(params or {}),
                  message="queued")
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._trim()
        self._publish(job)
        job._future = self._pool.submit(self._run, job, fn)
        return job

    def list(self) -> list[Job]:
        with self._lock:
            return [self._jobs[i] for i in reversed(self._order) if i in self._jobs]

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> Optional[Job]:
        job = self.get(job_id)
        if job is None:
            return None
        if job.status in TERMINAL:
            return job
        job.cancel_requested = True
        job._cancel.set()
        if job._future is not None:
            job._future.cancel()        # succeeds only while still queued
        job.status = CANCELLED
        job.finished = now_iso()
        job.message = "cancelled" if job.started is None else "cancelled (worker stops at its next checkpoint)"
        logger.info("job %s (%s) cancelled", job.id, job.title)
        self._publish(job)
        return job

    def shutdown(self) -> None:
        for job in self.list():
            if job.status not in TERMINAL:
                job._cancel.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ── internals ────────────────────────────────────────────────────────────
    def _trim(self) -> None:
        while len(self._order) > self._keep:
            for i, jid in enumerate(self._order):
                if self._jobs[jid].status in TERMINAL:
                    self._order.pop(i)
                    self._jobs.pop(jid, None)
                    break
            else:
                return

    def _run(self, job: Job, fn: Callable[[JobContext], Any]) -> None:
        if job._cancel.is_set():
            return
        job.status = RUNNING
        job.started = now_iso()
        job.message = "running"
        job._t0 = time.monotonic()
        self._publish(job)
        logger.info("job %s started: %s", job.id, job.title)
        ctx = JobContext(self, job)
        try:
            result = fn(ctx)
            if job._cancel.is_set():
                return                    # already reported as cancelled; drop the result
            job.result = to_jsonable(result)
            job.progress = 1.0
            job.status = SUCCEEDED
            job.message = "done"
            job.finished = now_iso()
            logger.info("job %s succeeded in %.1fs: %s", job.id, time.monotonic() - job._t0, job.title)
        except JobCancelled:
            if job.status != CANCELLED:
                job.status = CANCELLED
                job.finished = now_iso()
                job.message = "cancelled"
            logger.info("job %s stopped after cancellation: %s", job.id, job.title)
        except BaseException as exc:  # noqa: BLE001 — a job must always reach a terminal state
            if job._cancel.is_set():
                return
            job.status = FAILED
            job.error = str(exc) if isinstance(exc, JobError) else f"{type(exc).__name__}: {exc}"
            job.message = "failed"
            job.finished = now_iso()
            if isinstance(exc, JobError):
                logger.warning("job %s failed: %s", job.id, exc)
            else:
                logger.error("job %s failed: %s\n%s", job.id, exc, traceback.format_exc(limit=6))
            if not isinstance(exc, Exception):
                self._publish(job)
                raise
        self._publish(job)
