"""
api/services/arms.py — arming scheduled PAPER runs: the service as the one place that starts them.

An arm (``app.RunnerArm``) says "run <strategy> [variant] on paper: once on <date>, or every weekday". The
scheduler (a thread, every 15 s) starts each armed run at its time on trading days (weekends and exchange
holidays skipped) and records what happened in the arm's ``last_result``:

  ndx_0dte_tasty    exactly what the Windows scheduled task did ("AlanTrader paper NDX", registered by the
                    platform's scripts/register_paper_task.ps1): at 10:30 ET, from the live checkout,
                        powershell -NoProfile -ExecutionPolicy Bypass -File "<live>\\scripts\\start_paper_runner.ps1" -Strategy ndx_0dte_tasty
                    — the script refreshes the reference data, runs the runner (restarting it if it dies before
                    16:01 ET), then stores the day's minutes, checks the data, reconciles and archives. Its
                    outputs land where they always did (the live checkout's paper_state / paper_log, the
                    strategies' paper_log, the archive). The service launches it through WMI
                    (Win32_Process.Create): outside the service's process tree and the desktop's kill-on-close
                    job — so closing the app or restarting the service does not kill the day's session — and
                    with the user's own logon environment, as the task had. Its console output goes to
                    paper_state/runner_logs/arm/ in the service's checkout. The service tracks it as its own
                    (pid + creation time in the arm row), so the kill switch still works after a restart.
  gex_positioning   (the GEX paper allocator) at 15:50 ET, in the service — see api/services/gex_alloc.py.
  ndx_gamma_walls   the platform's paper runner for the strategy, started at 09:25 ET from THIS checkout (so the
                    strategy overlay applies — api/bootstrap.py) and detached the same way (WMI):
                        "<venv python>" -m api.runner_launch --strategy ndx_gamma_walls --poll 15 --log-dir <…>
                    It waits for the open and exits after 16:01 ET; a late start (up to 15:00, the end of its entry
                    window) builds no stream backfill (the strategy needs no lookback).

Rules: if a runner for the strategy is already running anywhere (the service's own or external: another
process, the scheduled task, a fresh heartbeat), the day is "skipped: already running (...)". A service that
comes up after the run's time but inside its window (10:30–16:00 ET for the NDX runner) starts it late and
says so; after the window the day is "missed". A day is claimed in the table before anything starts, so two
service processes never start the same run twice.

``ALAN_TRADER_ARMS``: ``db`` (default: app.RunnerArm) | ``memory`` (the test suite: nothing persists) |
``off``. ``ALAN_TRADER_ARM_SCHEDULER``: ``1`` (default) | ``0`` (arms are kept but nothing is started).
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

logger = logging.getLogger("alan_trader.api.arms")

NY = "America/New_York"
TICK_S = 15.0
LATE_AFTER_S = 120.0


class ArmError(ValueError):
    """An arm request the service cannot accept (422)."""


@dataclass(frozen=True)
class Spec:
    kind: str                    # script | allocator
    at: _dt.time                 # when the run starts (ET)
    until: _dt.time              # the last moment a late start still makes sense (ET)
    variants: tuple = ("",)      # "" = the strategy has no variants
    label: str = ""


SPECS: dict[str, Spec] = {
    "ndx_0dte_tasty": Spec("script", _dt.time(10, 30), _dt.time(16, 0), ("",),
                           "the scheduled task's start_paper_runner.ps1 from the live checkout"),
    "gex_positioning": Spec("allocator", _dt.time(15, 50), _dt.time(16, 0), ("vix", "gex"),
                            "the service's GEX paper allocator on the whole paper account"),
    "ndx_gamma_walls": Spec("runner", _dt.time(9, 25), _dt.time(15, 0), ("",),
                            "the platform's paper runner from the service checkout (detached)"),
    # the maker's window is 13:00-15:45 and its 30-minute lookback is backfilled from the broker's candle feed, so it
    # starts after lunch: polling from the open would spend half the day's shared broker budget for nothing
    "ndx_0dte_maker": Spec("runner", _dt.time(12, 25), _dt.time(15, 30), ("",),
                           "the platform's paper runner from the service checkout (detached; the strategy is an overlay)"),
}
RUNNER_POLL_S = 15


def enabled_store() -> str:
    m = os.environ.get("ALAN_TRADER_ARMS", "db").strip().lower()
    return m if m in ("db", "memory", "off") else "db"


def scheduler_on() -> bool:
    return os.environ.get("ALAN_TRADER_ARM_SCHEDULER", "1").strip().lower() not in ("0", "off", "false", "no")


def trading_day(d: _dt.date) -> bool:
    from api.services.gex_recorder import trading_day as td
    return td(d)


def _et(ts_utc) -> Optional[pd.Timestamp]:
    if ts_utc is None or (isinstance(ts_utc, float) and pd.isna(ts_utc)):
        return None
    t = pd.Timestamp(ts_utc)
    t = t.tz_localize("UTC") if t.tzinfo is None else t
    return t.tz_convert(NY)


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


# ── the arm store ─────────────────────────────────────────────────────────────

_ROW = ("id", "strategy", "variant", "schedule", "date", "mode", "armed_at", "last_run_date", "last_run_at",
        "last_result", "run_pid", "run_created", "run_log")


class MemoryArmStore:
    """Arms in memory (the test suite's; nothing persists)."""

    def __init__(self):
        self._rows: dict[int, dict] = {}
        self._next = 1
        self._lock = threading.Lock()

    def active(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._rows.values() if r["active"]]

    def arm(self, strategy: str, variant: str, schedule: str, date: Optional[_dt.date]) -> dict:
        with self._lock:
            for r in self._rows.values():
                if r["active"] and r["strategy"] == strategy and r["variant"] == variant:
                    r.update(schedule=schedule, date=date, armed_at=_utcnow())
                    return dict(r)
            r = {"id": self._next, "strategy": strategy, "variant": variant, "schedule": schedule, "date": date,
                 "mode": "paper", "armed_at": _utcnow(), "last_run_date": None, "last_run_at": None,
                 "last_result": None, "run_pid": None, "run_created": None, "run_log": None, "active": True}
            self._rows[self._next] = r
            self._next += 1
            return dict(r)

    def disarm(self, strategy: str, variant: Optional[str] = None) -> list[dict]:
        out = []
        with self._lock:
            for r in self._rows.values():
                if r["active"] and r["strategy"] == strategy and (variant is None or r["variant"] == variant):
                    r["active"] = False
                    out.append(dict(r))
        return out

    def claim(self, arm_id: int, day: _dt.date, result: str) -> bool:
        with self._lock:
            r = self._rows.get(arm_id)
            if r is None or not r["active"] or (r["last_run_date"] is not None and r["last_run_date"] >= day):
                return False
            r.update(last_run_date=day, last_run_at=_utcnow(), last_result=result, run_pid=None, run_created=None,
                     run_log=None)
            return True

    def record(self, arm_id: int, result: str, *, pid: Optional[int] = None, created: Optional[float] = None,
               log: Optional[str] = None, keep_run: bool = False) -> None:
        with self._lock:
            r = self._rows.get(arm_id)
            if r is None:
                return
            r.update(last_result=result[:400], last_run_at=_utcnow())
            if not keep_run:
                r.update(run_pid=pid, run_created=created, run_log=log)


class DbArmStore:
    """app.RunnerArm (through the service's write guard; the app schema is on its allow-list)."""

    _SELECT = ("SELECT ArmId, Strategy, Variant, Schedule, ArmDate, Mode, ArmedAt, LastRunDate, LastRunAt, "
               "LastResult, RunPid, RunCreated, RunLog FROM app.RunnerArm")

    def _eng(self):
        from api.services.db import require_db
        return require_db()

    @staticmethod
    def _row(r) -> dict:
        d = dict(zip(_ROW, r))
        for k in ("date", "last_run_date"):
            if d[k] is not None and isinstance(d[k], _dt.datetime):
                d[k] = d[k].date()
        d["variant"] = d["variant"] or ""
        return d

    def active(self) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("RunnerArm"):
            return []
        with self._eng().connect() as c:
            rows = c.execute(text(self._SELECT + " WHERE Active = 1 ORDER BY Strategy, Variant")).fetchall()
        return [self._row(r) for r in rows]

    def arm(self, strategy: str, variant: str, schedule: str, date: Optional[_dt.date]) -> dict:
        from sqlalchemy import text
        from api.services import appdb
        appdb.ensure("RunnerArm")
        with self._eng().begin() as c:
            n = c.execute(text("UPDATE app.RunnerArm SET Schedule = :sch, ArmDate = :d, ArmedAt = SYSUTCDATETIME(), "
                               "UpdatedAt = SYSUTCDATETIME() WHERE Strategy = :s AND Variant = :v AND Active = 1"),
                          {"sch": schedule, "d": date, "s": strategy, "v": variant}).rowcount
            if not n:
                c.execute(text("INSERT INTO app.RunnerArm (Strategy, Variant, Schedule, ArmDate, Mode) "
                               "VALUES (:s, :v, :sch, :d, 'paper')"),
                          {"s": strategy, "v": variant, "sch": schedule, "d": date})
            r = c.execute(text(self._SELECT + " WHERE Strategy = :s AND Variant = :v AND Active = 1"),
                          {"s": strategy, "v": variant}).fetchone()
        return self._row(r)

    def disarm(self, strategy: str, variant: Optional[str] = None) -> list[dict]:
        from sqlalchemy import text
        from api.services import appdb
        if not appdb.exists("RunnerArm"):
            return []
        where = "Strategy = :s AND Active = 1" + (" AND Variant = :v" if variant is not None else "")
        params = {"s": strategy, "v": variant}
        with self._eng().begin() as c:
            rows = c.execute(text(self._SELECT + " WHERE " + where), params).fetchall()
            c.execute(text("UPDATE app.RunnerArm SET Active = 0, DisarmedAt = SYSUTCDATETIME(), "
                           "UpdatedAt = SYSUTCDATETIME() WHERE " + where), params)
        return [self._row(r) for r in rows]

    def claim(self, arm_id: int, day: _dt.date, result: str) -> bool:
        from sqlalchemy import text
        with self._eng().begin() as c:
            n = c.execute(text("UPDATE app.RunnerArm SET LastRunDate = :d, LastRunAt = SYSUTCDATETIME(), "
                               "LastResult = :res, RunPid = NULL, RunCreated = NULL, RunLog = NULL, "
                               "UpdatedAt = SYSUTCDATETIME() WHERE ArmId = :id AND Active = 1 AND "
                               "(LastRunDate IS NULL OR LastRunDate < :d)"),
                          {"d": day, "res": result[:400], "id": arm_id}).rowcount
        return n == 1

    def record(self, arm_id: int, result: str, *, pid: Optional[int] = None, created: Optional[float] = None,
               log: Optional[str] = None, keep_run: bool = False) -> None:
        from sqlalchemy import text
        run = "" if keep_run else ", RunPid = :pid, RunCreated = :cr, RunLog = :log"
        with self._eng().begin() as c:
            c.execute(text("UPDATE app.RunnerArm SET LastResult = :res, LastRunAt = SYSUTCDATETIME(), "
                           "UpdatedAt = SYSUTCDATETIME()" + run + " WHERE ArmId = :id"),
                      {"res": result[:400], "pid": pid, "cr": created, "log": log, "id": arm_id})


def make_store():
    m = enabled_store()
    if m == "memory":
        return MemoryArmStore()
    if m == "off":
        return None
    return DbArmStore()


# ── launching the scheduled task's script ────────────────────────────────────

def live_checkout() -> Path:
    """The checkout the scheduled task ran from (``ALAN_TRADER_TASK_CHECKOUT``, default the main checkout)."""
    env = os.environ.get("ALAN_TRADER_TASK_CHECKOUT")
    if env:
        return Path(env)
    from api.config import main_checkout
    main = main_checkout()
    if main is None:
        raise RuntimeError("the live checkout is not known (the service is not a linked worktree); set "
                           "ALAN_TRADER_TASK_CHECKOUT")
    return main


def task_command(strategy: str, checkout: Optional[Path] = None) -> str:
    """The scheduled task's own command line (register_paper_task.ps1's /TR)."""
    script = (checkout or live_checkout()) / "scripts" / "start_paper_runner.ps1"
    return f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script}" -Strategy {strategy}'


def wrapped_command(strategy: str, log: Path, checkout: Optional[Path] = None) -> str:
    """The task's command, its console output captured to ``log`` and its exit code to ``log``.exit."""
    return (f'cmd.exe /d /v:on /s /c "{task_command(strategy, checkout)} > "{log}" 2>&1 '
            f'& echo !ERRORLEVEL! > "{log}.exit""')


def wmi_launch(command: str, cwd: str) -> tuple[int, float]:
    """Start ``command`` through Win32_Process.Create: a process of the user's own, not a child of the service
    (so neither the desktop's kill-on-close job nor a service restart ends it), with the user's logon
    environment. Returns (pid, creation time)."""
    import psutil
    ps = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
          "@{CommandLine=$env:ALAN_TRADER_ARM_CMD; CurrentDirectory=$env:ALAN_TRADER_ARM_CWD}; "
          "'' + $r.ReturnValue + ' ' + $r.ProcessId")
    env = dict(os.environ, ALAN_TRADER_ARM_CMD=command, ALAN_TRADER_ARM_CWD=cwd)
    kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps],
                         capture_output=True, text=True, env=env, timeout=90, **kw)
    parts = (out.stdout or "").split()
    if len(parts) != 2 or parts[0] != "0":
        raise RuntimeError(f"Win32_Process.Create failed: {' '.join(parts) or (out.stderr or '').strip()[:200]}")
    pid = int(parts[1])
    return pid, psutil.Process(pid).create_time()


def python_exe() -> str:
    """The service checkout's own interpreter (its venv), else this process's."""
    import sys
    from api.bootstrap import WORKING_COPY
    venv = WORKING_COPY / ".venv-win" / "Scripts" / "python.exe"
    return str(venv) if venv.is_file() else sys.executable


def runner_command(strategy: str, log: Path, csv_dir: Path, py: Optional[str] = None) -> str:
    """The platform's paper runner for ``strategy`` from this checkout (live, ledger on), its console output
    captured to ``log`` and its exit code to ``log``.exit."""
    inner = (f'"{py or python_exe()}" -m api.runner_launch --strategy {strategy} --poll {RUNNER_POLL_S} '
             f'--log-dir "{csv_dir}"')
    return f'cmd.exe /d /v:on /s /c "{inner} > "{log}" 2>&1 & echo !ERRORLEVEL! > "{log}.exit""'


def launch_runner(strategy: str, log_dir: Path) -> dict:
    from api.bootstrap import WORKING_COPY
    log_dir.mkdir(parents=True, exist_ok=True)
    csv_dir = WORKING_COPY / "paper_state" / "runner_logs" / strategy / "live"
    csv_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{strategy}_{_dt.datetime.now():%Y-%m-%d_%H%M%S}.log"
    cmd = runner_command(strategy, log, csv_dir)
    pid, created = wmi_launch(cmd, str(WORKING_COPY))
    return {"pid": pid, "created": created, "log": str(log), "exit_file": f"{log}.exit", "cmdline": cmd,
            "task_command": cmd, "cwd": str(WORKING_COPY)}


def launch_later(strategy: str, at: str, day: Optional[_dt.date] = None, log_dir: Optional[Path] = None) -> dict:
    """The fallback when the service will not be running at an arm's time: a detached process (WMI, as the arms)
    that sleeps until ``at`` (ET) on ``day`` and then runs the same paper runner the arm would
    (``python -m api.launch_later``). The service does not track it: it is an external runner to it."""
    from api.bootstrap import WORKING_COPY
    log_dir = log_dir or (WORKING_COPY / "paper_state" / "runner_logs" / "arm")
    log_dir.mkdir(parents=True, exist_ok=True)
    csv_dir = WORKING_COPY / "paper_state" / "runner_logs" / strategy / "live"
    csv_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{strategy}_later_{_dt.datetime.now():%Y-%m-%d_%H%M%S}.log"
    inner = (f'"{python_exe()}" -m api.launch_later --at {at}' + (f" --date {day.isoformat()}" if day else "") +
             f' -- --strategy {strategy} --poll {RUNNER_POLL_S} --log-dir "{csv_dir}"')
    cmd = f'cmd.exe /d /v:on /s /c "{inner} > "{log}" 2>&1 & echo !ERRORLEVEL! > "{log}.exit""'
    pid, created = wmi_launch(cmd, str(WORKING_COPY))
    return {"pid": pid, "created": created, "log": str(log), "cmdline": cmd}


def launch_task_script(strategy: str, log_dir: Path) -> dict:
    checkout = live_checkout()
    script = checkout / "scripts" / "start_paper_runner.ps1"
    if not script.is_file():
        raise RuntimeError(f"{script} is not there")
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{strategy}_{_dt.datetime.now():%Y-%m-%d_%H%M%S}.log"
    cmd = wrapped_command(strategy, log, checkout)
    pid, created = wmi_launch(cmd, str(checkout))
    return {"pid": pid, "created": created, "log": str(log), "exit_file": f"{log}.exit", "cmdline": cmd,
            "task_command": task_command(strategy, checkout), "cwd": str(checkout)}


# ── the scheduler ─────────────────────────────────────────────────────────────

class ArmScheduler:
    def __init__(self, store, runners, publish: Optional[Callable[[dict], None]] = None,
                 clock: Optional[Callable[[], pd.Timestamp]] = None,
                 launcher: Optional[Callable[[str], dict]] = None, allocator=None,
                 runner_launcher: Optional[Callable[[str], dict]] = None):
        from api.bootstrap import WORKING_COPY
        self.store = store
        self.runners = runners
        self.publish = publish
        self.clock = clock or (lambda: pd.Timestamp.now(tz=NY))
        self.log_dir = WORKING_COPY / "paper_state" / "runner_logs" / "arm"
        self.launcher = launcher or (lambda strategy: launch_task_script(strategy, self.log_dir))
        self.runner_launcher = runner_launcher or (lambda strategy: launch_runner(strategy, self.log_dir))
        self.allocator = allocator
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._runs: dict[int, int] = {}          # service session pid -> arm id
        if runners is not None:
            runners.listeners.append(self._on_session_end)

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self.store is None:
            logger.info("runner arms off (ALAN_TRADER_ARMS=off)")
            return
        try:
            self.adopt_running()
        except Exception:
            logger.exception("could not look for the arms' running sessions")
        if not scheduler_on():
            logger.info("arm scheduler off (ALAN_TRADER_ARM_SCHEDULER): arms are kept, nothing is started")
            return
        self._thread = threading.Thread(target=self._run, name="arm-scheduler", daemon=True)
        self._thread.start()
        try:
            n = len(self.store.active())
        except Exception:
            n = "?"
        logger.info("arm scheduler on: %s active arm(s)", n)

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(TICK_S):
            try:
                self.tick()
            except Exception:
                logger.exception("arm scheduler tick failed")

    # ── events ────────────────────────────────────────────────────────────────
    def _event(self, event: str, arm: dict, detail: str = "", **extra) -> dict:
        ev = {"type": "arm", "event": event, "strategy": arm["strategy"], "variant": arm.get("variant") or None,
              "schedule": arm.get("schedule"), "mode": "paper", "detail": detail,
              "at": self.clock().isoformat(timespec="seconds"), **extra}
        logger.info("arm %s%s: %s%s", arm["strategy"], f":{arm['variant']}" if arm.get("variant") else "", event,
                    f" — {detail}" if detail else "")
        if self.publish is not None:
            try:
                from api.serialize import to_jsonable
                self.publish(to_jsonable(ev))
            except Exception:
                logger.debug("arm event publish failed", exc_info=True)
        return ev

    # ── arming ────────────────────────────────────────────────────────────────
    def _need_store(self):
        if self.store is None:
            raise ArmError("arms are off in this service (ALAN_TRADER_ARMS=off)")
        return self.store

    def arm(self, strategy: str, schedule: str = "weekdays", date: Optional[str] = None,
            variant: Optional[str] = None) -> list[dict]:
        store = self._need_store()
        spec = SPECS.get(strategy)
        if spec is None:
            raise ArmError(f"no scheduled paper run is defined for {strategy!r}; armable: {', '.join(SPECS)}")
        schedule = (schedule or "weekdays").strip().lower()
        if schedule not in ("once", "weekdays"):
            raise ArmError("schedule must be once or weekdays")
        variants = self._variants(strategy, spec, variant)
        if spec.kind == "allocator" and self.allocator is None:
            raise ArmError(f"{strategy}'s paper allocator is not available in this service")
        now = self.clock()
        day = None
        if schedule == "once":
            if date:
                try:
                    day = _dt.date.fromisoformat(str(date)[:10])
                except ValueError:
                    raise ArmError(f"{date!r} is not an ISO date (YYYY-MM-DD)")
            else:
                day = self._next_day(now, spec, include_today=True)
            if not trading_day(day):
                raise ArmError(f"{day} is not a trading day")
            if day < now.date() or (day == now.date() and now.time() >= spec.until):
                raise ArmError(f"{day}'s run window ({spec.at:%H:%M}–{spec.until:%H:%M} ET) has passed")
        elif date:
            raise ArmError("date goes with schedule once")
        out = []
        for v in variants:
            row = store.arm(strategy, v, schedule, day)
            view = self._view(row, now)
            self._event("armed", row, f"{schedule}{' ' + str(day) if day else ''}; next run {view['next_run']}")
            out.append(view)
        from api.serialize import to_jsonable
        return to_jsonable(out)

    def disarm(self, strategy: str, variant: Optional[str] = None) -> list[dict]:
        store = self._need_store()
        spec = SPECS.get(strategy)
        if spec is None:
            raise ArmError(f"no scheduled paper run is defined for {strategy!r}")
        vs = None if variant in (None, "", "both", "all") else self._variants(strategy, spec, variant)
        rows = []
        for v in (vs or [None]):
            rows += store.disarm(strategy, v)
        now = self.clock()
        for r in rows:
            self._event("disarmed", r, "a running session is not stopped by disarming (use stop)")
        from api.serialize import to_jsonable
        return to_jsonable([dict(self._view(r, now), active=False) for r in rows])

    @staticmethod
    def _variants(strategy: str, spec: Spec, variant: Optional[str]) -> list[str]:
        v = (variant or "").strip().lower()
        if spec.variants == ("",):
            if v:
                raise ArmError(f"{strategy} has no variants")
            return [""]
        if v in ("", "both", "all"):
            return list(spec.variants)
        if v not in spec.variants:
            raise ArmError(f"variant must be one of {', '.join(spec.variants)} or both")
        return [v]

    # ── the view ──────────────────────────────────────────────────────────────
    @staticmethod
    def _next_day(now: pd.Timestamp, spec: Spec, include_today: bool) -> _dt.date:
        d = now.date()
        if not (include_today and trading_day(d) and now.time() < spec.until):
            d += _dt.timedelta(days=1)
        while not trading_day(d):
            d += _dt.timedelta(days=1)
        return d

    def next_run(self, arm: dict, now: pd.Timestamp) -> Optional[pd.Timestamp]:
        spec = SPECS.get(arm["strategy"])
        if spec is None:
            return None
        today = now.date()
        if arm["schedule"] == "once":
            day = arm["date"]
            if day is None or (arm["last_run_date"] is not None and arm["last_run_date"] >= day) or day < today:
                return None
            if day == today and now.time() >= spec.until:
                return None
        else:
            day = self._next_day(now, spec, include_today=arm["last_run_date"] != today)
        at = pd.Timestamp(_dt.datetime.combine(day, spec.at)).tz_localize(NY)
        return max(at, now) if day == today else at

    def _view(self, arm: dict, now: pd.Timestamp) -> dict:
        spec = SPECS.get(arm["strategy"])
        running = None
        if self.runners is not None and spec is not None and spec.kind in ("script", "runner"):
            c = self.runners.mine_running(arm["strategy"])
            running = c.proc.pid if c is not None else None
        nr = self.next_run(arm, now)
        return {"id": arm["id"], "strategy": arm["strategy"], "variant": arm["variant"] or None,
                "schedule": arm["schedule"], "date": arm["date"], "mode": "paper", "active": True,
                "armed_at": _et(arm["armed_at"]), "next_run": nr,
                "last_run": _et(arm["last_run_at"]) if arm["last_run_date"] is not None else None,
                "last_run_date": arm["last_run_date"], "last_result": arm["last_result"],
                "running": running is not None, "pid": running, "log": arm.get("run_log"),
                "kind": spec.kind if spec else None,
                "window": {"at": spec.at.strftime("%H:%M"), "until": spec.until.strftime("%H:%M"),
                           "timezone": NY} if spec else None,
                "status": self._status(arm, spec, nr, running, now)}

    def _status(self, arm, spec, nr, running, now) -> Optional[dict]:
        if self.allocator is not None and spec is not None and spec.kind == "allocator":
            try:
                return self.allocator.status(arm["variant"])
            except Exception as exc:  # noqa: BLE001
                return {"error": f"{type(exc).__name__}: {exc}"[:200]}
        return None

    def arms(self) -> list[dict]:
        from api.serialize import to_jsonable
        if self.store is None:
            return []
        now = self.clock()
        return to_jsonable([self._view(a, now) for a in self.store.active()])

    # ── the schedule ──────────────────────────────────────────────────────────
    def tick(self, now: Optional[pd.Timestamp] = None) -> list[dict]:
        """Start (or skip / miss) what is due at ``now``; returns the events published."""
        if self.store is None:
            return []
        now = now or self.clock()
        today, t = now.date(), now.time()
        events = []
        for arm in self.store.active():
            spec = SPECS.get(arm["strategy"])
            if spec is None:
                continue
            if arm["schedule"] == "once" and arm["date"] is not None and arm["date"] < today \
                    and (arm["last_run_date"] is None or arm["last_run_date"] < arm["date"]):
                why = f"missed: the service was not running during {arm['date']}'s window ({spec.at:%H:%M}–{spec.until:%H:%M} ET)"
                if self.store.claim(arm["id"], arm["date"], why):
                    events.append(self._event("missed", arm, why))
                continue
            if not trading_day(today) or (arm["schedule"] == "once" and arm["date"] != today):
                continue
            if arm["last_run_date"] is not None and arm["last_run_date"] >= today:
                continue
            if t < spec.at:
                continue
            if t >= spec.until:
                armed = _et(arm["armed_at"])
                if armed is None or armed.date() < today or armed.time() < spec.until:
                    why = (f"missed: the service was not running between {spec.at:%H:%M} and "
                           f"{spec.until:%H:%M} ET")
                    if self.store.claim(arm["id"], today, why):
                        events.append(self._event("missed", arm, why))
                continue
            if not self.store.claim(arm["id"], today, "starting"):
                continue                                   # another service process has it
            late = (now - pd.Timestamp(_dt.datetime.combine(today, spec.at)).tz_localize(NY)).total_seconds() \
                > LATE_AFTER_S
            try:
                events.append(self._start(arm, spec, now, late))
            except Exception as exc:  # noqa: BLE001 — recorded, and the next arm is still handled
                why = f"failed to start: {type(exc).__name__}: {exc}"
                self.store.record(arm["id"], why)
                events.append(self._event("failed", arm, why))
        return events

    def _late_note(self, spec: Spec, now: pd.Timestamp, late: bool) -> str:
        return f" late at {now:%H:%M} ET (scheduled {spec.at:%H:%M}; the service was not running then)" if late else ""

    def _start(self, arm: dict, spec: Spec, now: pd.Timestamp, late: bool) -> dict:
        if spec.kind == "allocator":
            if self.allocator is None:
                raise RuntimeError("the GEX paper allocator is not available in this service")
            res = self.allocator.run(arm["variant"], now=now)
            note = self._late_note(spec, now, late)
            msg = f"ran{note}: {res.get('summary', '')}".strip()
            self.store.record(arm["id"], msg)
            return self._event("ran", arm, msg, decision=res)
        mine = self.runners.mine_running(arm["strategy"])
        if mine is not None:
            why = f"skipped: already running (started by the service, pid {mine.proc.pid})"
            self.store.record(arm["id"], why)
            return self._event("skipped", arm, why)
        other = self.runners.running_elsewhere(arm["strategy"])
        if other is not None:
            where = f"pid {other['pid']}" if other.get("pid") else f"heartbeat in {other.get('state_dir')}"
            why = f"skipped: already running (external, {where})"
            self.store.record(arm["id"], why)
            return self._event("skipped", arm, why)
        info = (self.runner_launcher if spec.kind == "runner" else self.launcher)(arm["strategy"])
        child = self.runners.adopt(arm["strategy"], info["pid"], info["created"], log=info["log"],
                                   cmdline=info.get("cmdline") or "", exit_file=info.get("exit_file"),
                                   kind="runner" if spec.kind == "runner" else "task_script",
                                   extra={"arm_id": arm["id"], "task_command": info.get("task_command")})
        with self._lock:
            self._runs[child.proc.pid] = arm["id"]
        msg = f"started{self._late_note(spec, now, late)} (pid {info['pid']})"
        self.store.record(arm["id"], msg, pid=info["pid"], created=info["created"], log=info["log"])
        return self._event("started", arm, msg, pid=info["pid"], log=info["log"], late=late,
                           command=info.get("task_command"))

    # ── the sessions it started ──────────────────────────────────────────────
    def _on_session_end(self, child) -> None:
        with self._lock:
            arm_id = self._runs.pop(child.proc.pid, None)
        if arm_id is None or self.store is None:
            return
        at = self.clock()
        if child.state == "stopped":
            event, msg = "stopped", f"stopped at {at:%H:%M} ET (kill switch)"
        elif child.state == "finished":
            event, msg = "finished", f"finished at {at:%H:%M} ET (exit 0)"
        else:
            event, msg = "failed", f"ended at {at:%H:%M} ET (exit {child.returncode})"
        arm = next((a for a in self.store.active() if a["id"] == arm_id), None) or \
            {"id": arm_id, "strategy": child.strategy, "variant": "", "schedule": None}
        self.store.record(arm_id, msg, keep_run=True)
        self._event(event, arm, msg, pid=child.proc.pid, log=child.log)

    def adopt_running(self) -> int:
        """After a service restart: an arm's session still running (same pid and creation time) is the
        service's again; one that ended while the service was down gets its result."""
        if self.store is None or self.runners is None:
            return 0
        from api.services.runner import AdoptedProc
        n = 0
        for arm in self.store.active():
            pid, created = arm.get("run_pid"), arm.get("run_created")
            if not pid or not created or not str(arm.get("last_result") or "").startswith("started"):
                continue
            log = arm.get("run_log")
            proc = AdoptedProc(int(pid), float(created), f"{log}.exit" if log else None)
            if proc.poll() is None:
                child = self.runners.adopt(arm["strategy"], int(pid), float(created), log=log or "",
                                           cmdline="(adopted after a service restart)",
                                           exit_file=f"{log}.exit" if log else None, extra={"arm_id": arm["id"]},
                                           emit=False)
                with self._lock:
                    self._runs[child.proc.pid] = arm["id"]
                n += 1
            else:
                code = proc.returncode
                msg = (f"finished while the service was down (exit {code})" if code == 0 else
                       f"ended while the service was down (exit {code})")
                self.store.record(arm["id"], msg, keep_run=True)
        return n


if __name__ == "__main__":                       # python -m api.services.arms later ndx_gamma_walls 09:25 2026-09-25
    import sys as _sys
    if len(_sys.argv) >= 4 and _sys.argv[1] == "later":
        from api.bootstrap import bootstrap
        bootstrap()
        out = launch_later(_sys.argv[2], _sys.argv[3],
                           _dt.date.fromisoformat(_sys.argv[4]) if len(_sys.argv) > 4 else None)
        print(out)
    else:
        print("usage: python -m api.services.arms later <strategy> <HH:MM> [YYYY-MM-DD]")
