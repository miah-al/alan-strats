"""
api/services/runner.py — paper runner sessions: see them all, start and stop the service's own.

A session the service starts is a child process (``python -m api.runner_launch``, i.e.
``scripts/paper_runner.py`` behind the service's bootstrap) with its output in
``paper_state/runner_logs/``; its CSV paper log goes there too (``--log-dir``), never into the
strategy plugin's folder. Runners started anywhere else — the user's own terminal, another checkout,
a scheduler — are found read-only: in the process table (any ``paper_runner`` command line) and by a
fresh heartbeat in any state directory the service reads (a runner the process table cannot show).

The service refuses to start a runner for a strategy that already has one running anywhere, and it
never stops a runner it did not start. It starts one on its own only for an arm (api/services/arms.py):
the scheduled task's script, launched outside the service's process tree and ``adopt``-ed here (so it
outlives a service restart, and a restarted service still knows it as its own). Otherwise only ``start``
does, when a client asks. ``mode: replay`` runs a stored day (fast; no ledger unless asked), ``mode: live``
runs today against the broker's quotes (the runner's own request budget and guards apply).

The platform's scheduled-task script (``scripts/start_paper_runner.ps1 -Strategy <slug>``: data refresh,
the runner restarted until 16:01 ET, then reconcile and archive) counts as a runner for its strategy
from the moment it starts, before its runner process exists.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from api.bootstrap import WORKING_COPY
from api.serialize import to_jsonable

logger = logging.getLogger("alan_trader.api.runner")

HEARTBEAT_FRESH_S = 120.0
STOP_GRACE_S = 10.0
_RUNNER_MARKERS = ("paper_runner", "runner_launch")
_TASK_SCRIPT = "start_paper_runner"
_TASK_DEFAULT_STRATEGY = "ndx_0dte_tasty"          # the script's own default
_TASK_STRATEGY_RX = re.compile(r"-strategy[\s\"']+([A-Za-z0-9_:.\-]+)", re.IGNORECASE)
_TASK_FILE_RX = re.compile(r"-file[\s\"']+[^\"']*start_paper_runner\.ps1", re.IGNORECASE)
_SCRIPT_HOSTS = {"powershell", "pwsh", "cmd"}
#: a shell, an editor or a search tool whose command line merely mentions a runner is not one
_NOT_RUNNERS = {"bash", "sh", "zsh", "dash", "fish", "grep", "rg", "findstr", "git", "code", "node", "notepad"}


def _exe(cmd: list[str]) -> str:
    name = str(cmd[0]).replace("\\", "/").rsplit("/", 1)[-1].lower() if cmd else ""
    return name[:-4] if name.endswith(".exe") else name


class RunnerError(ValueError):
    """A start request the service cannot accept (422)."""


class RunnerConflict(RuntimeError):
    """A runner is already running for the strategy, or the one asked to stop is not the service's (409)."""


class AdoptedProc:
    """A process the service started outside its own process tree (so it outlives the service and the
    desktop's kill-on-close job): known by pid and creation time, polled through the process table. Its
    exit code is the one the launch wrapper writes to ``exit_file`` (-1 when it ended without one)."""

    def __init__(self, pid: int, created: float, exit_file: Optional[str] = None):
        self.pid = int(pid)
        self.created = float(created)
        self.exit_file = exit_file
        self.returncode: Optional[int] = None

    def process(self):
        try:
            import psutil
            p = psutil.Process(self.pid)
            if abs(p.create_time() - self.created) > 2.0:
                return None                                    # the pid was reused: not ours
            if p.status() == psutil.STATUS_ZOMBIE:
                return None
            return p
        except Exception:
            return None

    def poll(self) -> Optional[int]:
        if self.returncode is not None:
            return self.returncode
        if self.process() is not None:
            return None
        code = -1
        if self.exit_file:
            for _ in range(10):                                 # the wrapper writes it as it exits
                try:
                    code = int(Path(self.exit_file).read_text(encoding="utf-8", errors="replace").strip() or -1)
                    break
                except (OSError, ValueError):
                    time.sleep(0.1)
        self.returncode = code
        return code

    def wait(self, timeout: Optional[float] = None) -> Optional[int]:
        end = time.monotonic() + (timeout if timeout is not None else 1e9)
        while self.poll() is None:
            if time.monotonic() >= end:
                raise subprocess.TimeoutExpired("adopted process", timeout)
            time.sleep(0.2)
        return self.returncode

    def send_signal(self, sig) -> None:
        raise OSError("not in the service's console: it is stopped by terminating its process tree")

    def terminate(self) -> None:
        p = self.process()
        if p is not None:
            p.terminate()

    kill = terminate


@dataclass
class Child:
    strategy: str
    mode: str
    date: str
    ledger: bool
    proc: subprocess.Popen
    started: str
    log: str
    cmdline: list
    state: str = "running"
    returncode: Optional[int] = None
    finished: Optional[str] = None
    stop_requested: bool = False
    extra: dict = field(default_factory=dict)
    kind: str = "runner"                     # runner | task_script
    launched_by: str = "request"             # request | arm


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _arg(cmd: list[str], flag: str) -> Optional[str]:
    for i, a in enumerate(cmd):
        if a == flag and i + 1 < len(cmd):
            return cmd[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return None


def parse_runner_cmdline(cmd: list[str]) -> Optional[dict]:
    """(strategy, mode, date) of a paper runner command line, or None if it is not one. The scheduled
    task's script (``start_paper_runner.ps1 [-Strategy slug]``) is a live runner of its strategy
    (``kind: task_script``)."""
    text = " ".join(cmd or [])
    if not any(m in text for m in _RUNNER_MARKERS) or _exe(cmd) in _NOT_RUNNERS:
        return None
    if _TASK_SCRIPT in text.lower() and ".ps1" in text.lower():
        if _exe(cmd) not in _SCRIPT_HOSTS or not _TASK_FILE_RX.search(text):
            return None
        m = _TASK_STRATEGY_RX.search(text)
        return {"strategy": m.group(1) if m else _TASK_DEFAULT_STRATEGY, "mode": "live",
                "date": _dt.date.today().isoformat(), "ledger": True, "kind": "task_script"}
    strategy = _arg(cmd, "--strategy")
    if not strategy:
        return None
    replay = _arg(cmd, "--replay")
    mode = "replay" if replay else ("check" if "--check" in cmd else "live")
    return {"strategy": strategy, "mode": mode, "date": replay or _dt.date.today().isoformat(),
            "ledger": ("--ledger" in cmd) if replay else ("--no-ledger" not in cmd)}


def scan_processes() -> list[dict]:
    """Every paper runner process on the machine (read only: the process table)."""
    try:
        import psutil
    except Exception:
        return []
    out = []
    me = os.getpid()
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        try:
            cmd = p.info.get("cmdline") or []
            if p.info["pid"] == me or not cmd:
                continue
            info = parse_runner_cmdline(cmd)
            if info is None:
                continue
            # a venv launcher and the interpreter it starts share the command line: keep the parent
            info.update(pid=p.info["pid"], ppid=p.ppid(),
                        started=_dt.datetime.fromtimestamp(p.info["create_time"]).astimezone().isoformat(timespec="seconds"),
                        cmdline=" ".join(cmd)[:400])
            out.append(info)
        except Exception:
            continue
    pids = {i["pid"] for i in out}
    return [i for i in out if i["ppid"] not in pids]


def fresh_heartbeats() -> dict[str, dict]:
    """strategy -> the freshest heartbeat under 2 minutes old in any state directory (a runner the
    process table does not show — another machine account, a container — still counts)."""
    from paper import views
    out: dict[str, dict] = {}
    for d in views.state_dirs():
        try:
            files = list(Path(d).glob("heartbeat_*.json"))
        except OSError:
            continue
        for hb in files:
            try:
                h = json.loads(hb.read_text(encoding="utf-8"))
                at = _dt.datetime.fromisoformat(str(h.get("at")))
            except (OSError, ValueError, TypeError):
                continue
            age = (_dt.datetime.now() - at).total_seconds()
            if age > HEARTBEAT_FRESH_S or h.get("note") == "finished":
                continue
            slug = hb.stem[len("heartbeat_"):]
            if slug not in out or str(h.get("at")) > str(out[slug].get("at")):
                out[slug] = dict(h, state_dir=str(d), age_s=round(age, 1))
    return out


class RunnerManager:
    def __init__(self, publish: Optional[Callable[[dict], None]] = None, log_dir: Optional[Path] = None,
                 command: Optional[Callable[[list], list]] = None):
        self.publish = publish
        #: runner arguments -> the command line to run (tests substitute a stand-in)
        self.command = command or (lambda args: [sys.executable, "-m", "api.runner_launch", *args])
        self.log_dir = Path(log_dir) if log_dir else WORKING_COPY / "paper_state" / "runner_logs"
        self._children: dict[int, Child] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        #: called with a Child when one of the service's sessions ends (the arm scheduler records it)
        self.listeners: list[Callable[[Child], None]] = []

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start_monitor(self) -> None:
        self._thread = threading.Thread(target=self._monitor, name="runner-monitor", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        """The service is going away: its runners keep running (a live session must not die with
        an API restart); they simply become external to the next service process."""
        self._stop.set()

    # ── what is running ───────────────────────────────────────────────────────
    def _child_row(self, c: Child) -> dict:
        return {"strategy": c.strategy, "mode": c.mode, "date": c.date, "state": c.state, "pid": c.proc.pid,
                "started": c.started, "managed_by": "service", "ledger": c.ledger, "returncode": c.returncode,
                "finished": c.finished, "log": c.log, "kind": c.kind, "launched_by": c.launched_by}

    def _my_pids(self) -> set[int]:
        """The service's own sessions and everything they started (a task script's runner is its grandchild)."""
        with self._lock:
            mine = list(self._children.values())
        pids = {c.proc.pid for c in mine}
        try:
            import psutil
            for c in mine:
                if c.state != "running":
                    continue
                try:
                    pids |= {p.pid for p in psutil.Process(c.proc.pid).children(recursive=True)}
                except psutil.Error:
                    pass
        except Exception:
            pass
        return pids

    def sessions(self) -> list[dict]:
        self._poll()
        with self._lock:
            mine = list(self._children.values())
        my_pids = self._my_pids()
        rows = [self._child_row(c) for c in sorted(mine, key=lambda c: c.started, reverse=True)]
        procs = scan_processes()
        seen = set()
        for p in procs:
            if p["pid"] in my_pids or p["ppid"] in my_pids:
                continue
            seen.add(p["strategy"])
            rows.append({"strategy": p["strategy"], "mode": p["mode"], "date": p["date"], "state": "running",
                         "pid": p["pid"], "started": p["started"], "managed_by": "external", "ledger": p["ledger"],
                         "returncode": None, "finished": None, "log": None, "cmdline": p["cmdline"]})
        running_mine = {c.strategy for c in mine if c.state == "running"}
        for slug, hb in fresh_heartbeats().items():
            if slug in seen or slug in running_mine:
                continue
            rows.append({"strategy": slug, "mode": "live", "date": hb.get("day"), "state": "running",
                         "pid": None, "started": None, "managed_by": "external", "ledger": None, "returncode": None,
                         "finished": None, "log": None, "heartbeat_at": hb.get("at"), "state_dir": hb.get("state_dir")})
        return to_jsonable(rows)

    def running_elsewhere(self, strategy: str) -> Optional[dict]:
        my_pids = self._my_pids()
        for p in scan_processes():
            if p["strategy"] == strategy and p["pid"] not in my_pids and p["ppid"] not in my_pids:
                return p
        hb = fresh_heartbeats().get(strategy)
        if hb is not None:
            with self._lock:
                mine_running = any(c.strategy == strategy and c.state == "running" for c in self._children.values())
            if not mine_running:
                return {"strategy": strategy, "pid": None, "heartbeat_at": hb.get("at"), "state_dir": hb.get("state_dir")}
        return None

    def mine_running(self, strategy: str) -> Optional[Child]:
        return self._mine_running(strategy)

    def adopt(self, strategy: str, pid: int, created: float, *, log: str, cmdline, exit_file: Optional[str] = None,
              started: Optional[str] = None, kind: str = "task_script", launched_by: str = "arm",
              extra: Optional[dict] = None, emit: bool = True) -> Child:
        """Track a process the service started outside its own tree (an arm's task script) as its own."""
        child = Child(strategy=strategy, mode="live", date=_dt.date.today().isoformat(), ledger=True,
                      proc=AdoptedProc(pid, created, exit_file), started=started or _now(), log=str(log),
                      cmdline=list(cmdline) if isinstance(cmdline, (list, tuple)) else [str(cmdline)],
                      kind=kind, launched_by=launched_by, extra=dict(extra or {}))
        with self._lock:
            self._children[child.proc.pid] = child
        logger.info("paper session %s (%s) is the service's: pid %s", strategy, kind, pid)
        if emit:
            self._emit(child)
        return child

    def _mine_running(self, strategy: str) -> Optional[Child]:
        self._poll()
        with self._lock:
            for c in self._children.values():
                if c.strategy == strategy and c.state == "running":
                    return c
        return None

    # ── start / stop ──────────────────────────────────────────────────────────
    def start(self, strategy: str, body: dict) -> dict:
        from alan_trader.strategy_api import registry as R
        if strategy not in R.STRATEGY_METADATA:
            raise KeyError(strategy)
        try:
            inst = R.get_strategy(strategy).live_instrument() or {}
        except Exception:
            inst = {}
        if not inst:
            raise RunnerError(f"{strategy} has no live session (its live_instrument() is empty)")
        body = body or {}
        mode = str(body.get("mode") or "replay").strip().lower()
        if mode not in ("live", "replay"):
            raise RunnerError("mode must be live or replay")
        today = _dt.date.today()
        if mode == "replay":
            try:
                day = _dt.date.fromisoformat(str(body.get("date"))[:10])
            except ValueError:
                raise RunnerError("a replay needs date: YYYY-MM-DD (a stored session)")
            if day >= today:
                raise RunnerError("a replay runs a past session; for today use mode live")
            ledger = bool(body.get("ledger", False))
        else:
            if body.get("date") and str(body["date"])[:10] != today.isoformat():
                raise RunnerError(f"a live session runs today ({today}), not {body['date']}")
            day = today
            ledger = bool(body.get("ledger", True))
        mine = self._mine_running(strategy)
        if mine is not None:
            raise RunnerConflict(f"{strategy} already has a runner the service started (pid {mine.proc.pid}, "
                                 f"{mine.mode} {mine.date})")
        other = self.running_elsewhere(strategy)
        if other is not None:
            where = f"pid {other['pid']}" if other.get("pid") else f"heartbeat {other.get('heartbeat_at')} in {other.get('state_dir')}"
            raise RunnerConflict(f"{strategy} already has a runner started outside the service ({where}); "
                                 f"the service will not start a second one")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        csv_dir = self.log_dir / strategy / ("replay" if mode == "replay" else "live")
        csv_dir.mkdir(parents=True, exist_ok=True)
        args = ["--strategy", strategy, "--log-dir", str(csv_dir)]
        if mode == "replay":
            args += ["--replay", day.isoformat()] + (["--ledger"] if ledger else [])
        elif not ledger:
            args += ["--no-ledger"]
        cmd = self.command(args)
        log = self.log_dir / f"{strategy}_{mode}_{day.isoformat()}_{stamp}.log"
        env = dict(os.environ)
        env.setdefault("PYTHONPYCACHEPREFIX", str(WORKING_COPY / ".pycache"))
        env["PYTHONUNBUFFERED"] = "1"
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        fh = open(log, "w", encoding="utf-8")
        try:
            proc = subprocess.Popen(cmd, cwd=str(WORKING_COPY), stdout=fh, stderr=subprocess.STDOUT, env=env, **kwargs)
        finally:
            fh.close()
        child = Child(strategy=strategy, mode=mode, date=day.isoformat(), ledger=ledger, proc=proc, started=_now(),
                      log=str(log), cmdline=cmd)
        with self._lock:
            self._children[proc.pid] = child
        logger.info("paper runner started: %s %s %s (pid %s, ledger %s)", strategy, mode, day, proc.pid,
                    "on" if ledger else "off")
        self._emit(child)
        return self._child_row(child)

    def stop(self, strategy: str) -> dict:
        c = self._mine_running(strategy)
        if c is None:
            other = self.running_elsewhere(strategy)
            if other is not None:
                raise RunnerConflict(f"{strategy}'s runner was not started by the service "
                                     f"({'pid ' + str(other['pid']) if other.get('pid') else 'seen by its heartbeat'}); "
                                     f"the service never stops a runner it did not start")
            raise LookupError(f"no runner is running for {strategy}")
        c.stop_requested = True
        if isinstance(c.proc, AdoptedProc):
            self._kill_tree(c.proc)                    # not in the service's console: no graceful signal
        else:
            self._signal(c)
            deadline = time.monotonic() + STOP_GRACE_S
            while time.monotonic() < deadline and c.proc.poll() is None:
                time.sleep(0.2)
            if c.proc.poll() is None:
                self._kill_tree(c.proc)
        self._poll()
        return self._child_row(c)

    def stop_all(self) -> list[dict]:
        """Stop every session the service started (never anything else)."""
        self._poll()
        with self._lock:
            running = sorted({c.strategy for c in self._children.values() if c.state == "running"})
        out = []
        for s in running:
            try:
                out.append(self.stop(s))
            except (LookupError, RunnerConflict):
                continue
        return out

    @staticmethod
    def _kill_tree(proc: subprocess.Popen) -> None:
        """Terminate the service's own child and everything it started (a venv launcher runs the
        interpreter as a child of its own, which terminating the launcher alone would orphan)."""
        try:
            import psutil
            parent = proc.process() if isinstance(proc, AdoptedProc) else psutil.Process(proc.pid)
            if parent is None:
                return
            family = [parent] + parent.children(recursive=True)     # the parent first: a script's retry loop
            # must not start its runner again
            for p in family:
                try:
                    p.terminate()
                except psutil.Error:
                    pass
            _gone, alive = psutil.wait_procs(family, timeout=5)
            for p in alive:
                try:
                    p.kill()
                except psutil.Error:
                    pass
        except Exception:
            proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()

    @staticmethod
    def _signal(c: Child) -> None:
        try:
            if os.name == "nt":
                c.proc.send_signal(signal.CTRL_BREAK_EVENT)      # to its own process group only
            else:
                os.killpg(c.proc.pid, signal.SIGINT)
        except Exception:
            logger.debug("graceful stop signal failed", exc_info=True)

    # ── monitoring ────────────────────────────────────────────────────────────
    def _poll(self) -> None:
        with self._lock:
            children = list(self._children.values())
        for c in children:
            if c.state != "running":
                continue
            rc = c.proc.poll()
            if rc is None:
                continue
            c.returncode = rc
            c.finished = _now()
            c.state = ("stopped" if c.stop_requested else "finished" if rc == 0 else "halted" if rc == 3 else "failed")
            logger.info("paper runner %s %s %s ended: %s (exit %s)", c.strategy, c.mode, c.date, c.state, rc)
            self._emit(c)
            for fn in list(self.listeners):
                try:
                    fn(c)
                except Exception:
                    logger.exception("runner listener failed")

    def _monitor(self) -> None:
        while not self._stop.wait(2.0):
            try:
                self._poll()
            except Exception:
                logger.debug("runner monitor failed", exc_info=True)

    def _emit(self, c: Child) -> None:
        if self.publish is not None:
            try:
                self.publish({"type": "runner", "session": to_jsonable(self._child_row(c))})
            except Exception:
                logger.debug("runner event publish failed", exc_info=True)
