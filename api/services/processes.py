"""
api/services/processes.py — the process monitor: everything a trading day depends on, in one table.

The runners start hidden (arms.wmi_launch), so there is no window to look at any more; this is where one looks. A row
per: the service itself; the broker stream; the quote recorder; every run armed for today and every runner session
the service can see; Claude's desk feed (scripts.claude_desk feed). Each row carries a status -- ok | warn | bad |
idle -- and the reason, so "expected but not running" is as visible as "running":

  runner rows  before its start: idle ("starts 12:30"); running with a heartbeat under 2 minutes: ok; running but
               silent (a heartbeat 2-7 minutes old, e.g. backing off a spent broker budget): warn; older, or no
               heartbeat at all: bad; finished (the heartbeat says so, or it exited 0): idle; exited early with an
               error while its day was still open: bad; its window passed with no run today: bad ("missed").

Read only: it looks at the process table, heartbeat files and logs. Stopping a runner stays POST /runner/{s}/stop.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
from pathlib import Path
from typing import Optional

HEARTBEAT_OK_S = 120
HEARTBEAT_SILENT_S = 420          # a runner backing off a failing feed waits up to 300 s between heartbeats
SESSION_END = _dt.time(16, 2)     # runners exit after 16:01 ET


def runner_status(now: _dt.datetime, *, at: Optional[_dt.time], until: Optional[_dt.time], alive: bool,
                  ran_today: bool, hb_age_s: Optional[float], hb_note: str = "", returncode: Optional[int] = None,
                  kind: str = "runner") -> tuple[str, str]:
    """(status, reason) of one armed run. Pure: the rules the table shows, testable without processes."""
    t = now.time()
    if kind == "allocator":                                  # runs inside the service at its time; nothing to watch
        return ("idle", "ran today") if ran_today else ("idle", f"runs {at:%H:%M}" if at else "armed")
    if alive:
        if "finished" in hb_note:
            return "idle", "finished"
        if hb_age_s is None:
            return "warn", "running, no heartbeat yet"
        if hb_age_s <= HEARTBEAT_OK_S:
            return "ok", "running"
        if hb_age_s <= HEARTBEAT_SILENT_S:
            return "warn", f"silent {hb_age_s:.0f}s" + (f" ({hb_note[:60]})" if hb_note else "")
        return "bad", f"silent {hb_age_s:.0f}s: running but not reporting"
    if ran_today:
        if "finished" in hb_note or returncode == 0 or t >= SESSION_END:
            return "idle", "finished"
        return "bad", f"stopped early (exit {returncode})" if returncode is not None else "stopped early"
    if at is not None and t < at:
        return "idle", f"starts {at:%H:%M}"
    if until is not None and t > until:
        return "bad", f"missed: no run today (window {at:%H:%M}-{until:%H:%M})" if at else "missed"
    return "warn", "due now, not started yet"


def _proc_info(pid: Optional[int]) -> dict:
    """Uptime, memory (the whole tree: a task script's work happens in its grandchild) and CPU of a live pid."""
    if not pid:
        return {"alive": False}
    try:
        import psutil
        p = psutil.Process(int(pid))
        if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
            return {"alive": False}
        tree = [p] + p.children(recursive=True)
        rss = sum(x.memory_info().rss for x in tree if x.is_running())
        cpu = sum(x.cpu_percent(interval=None) for x in tree if x.is_running())
        return {"alive": True, "uptime_s": round(time.time() - p.create_time()), "rss_mb": round(rss / 2**20, 1),
                "cpu_pct": round(cpu, 1)}
    except Exception:
        return {"alive": False}


def _heartbeat(slug: str) -> tuple[Optional[float], str, Optional[dict]]:
    """(age in seconds, note, the heartbeat) of the freshest heartbeat_<slug>.json of TODAY in any state directory."""
    from paper import views
    dirs = list(views.state_dirs())
    try:                                                     # runners of the main checkout (a task script) beat there
        from api.config import external_state_dirs
        dirs += [d for d in external_state_dirs() if d not in dirs]
    except Exception:
        pass
    best = None
    for d in dirs:
        f = Path(d) / f"heartbeat_{slug}.json"
        try:
            h = json.loads(f.read_text(encoding="utf-8"))
            at = _dt.datetime.fromisoformat(str(h.get("at")))
        except (OSError, ValueError, TypeError):
            continue
        if str(h.get("day")) != _dt.date.today().isoformat():
            continue
        if best is None or at > best[0]:
            best = (at, h)
    if best is None:
        return None, "", None
    at, h = best
    return round((_dt.datetime.now() - at).total_seconds(), 1), str(h.get("note") or h.get("halted") or ""), h


def _last_log_line(path: Optional[str]) -> str:
    if not path:
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 4096))
            lines = [ln for ln in f.read().decode("utf-8", "replace").splitlines() if ln.strip() and " DEBUG " not in ln]
        return lines[-1][:200] if lines else ""
    except OSError:
        return ""


def _desk_feed() -> dict:
    try:
        import psutil
        for p in psutil.process_iter(["pid", "cmdline"]):
            cmd = " ".join(p.info.get("cmdline") or [])
            if "claude_desk" in cmd and " feed" in cmd and "python" in cmd.lower():
                # the venv launcher and its interpreter share the line: report the parent
                parent = p.parent()
                if parent is not None and "claude_desk" in " ".join(parent.cmdline() or []):
                    continue
                return {"pid": p.info["pid"], **_proc_info(p.info["pid"])}
    except Exception:
        pass
    return {"alive": False}


def snapshot(app_state, now: Optional[_dt.datetime] = None) -> dict:
    now = now or _dt.datetime.now()
    rows: list[dict] = []
    me = _proc_info(os.getpid())
    rows.append({"name": "service", "kind": "service", "status": "ok", "reason": "running", "pid": os.getpid(), **me})

    hub = getattr(app_state, "market", None)
    try:
        tt = next((p for p in (hub.providers_status() if hub else []) if p.get("name") == "tastytrade"), None)
    except Exception:
        tt = None
    st = (tt or {}).get("state")
    status = {"connected": "ok", "degraded": "warn"}.get(st, "bad")
    detail = str((tt or {}).get("detail") or "")
    # "connected (connection #44)": the stream keeps dropping and coming back. Each drop is a window in which a quote can
    # go stale; flag a flapping stream even while it reads connected (2026-09-29: 44 reconnects in 80 minutes).
    import re
    m = re.search(r"connection #(\d+)", detail)
    uptime_min = max(1.0, (me.get("uptime_s") or 60) / 60.0)
    if status == "ok" and m and int(m.group(1)) > 3 and int(m.group(1)) / uptime_min > 0.1:
        status = "warn"
        detail += f"; {int(m.group(1))} connections in {uptime_min:.0f} min: flapping"
    rows.append({"name": "stream: tastytrade", "kind": "stream", "status": status,
                 "reason": f"{st or 'not configured'}" + (f" ({detail})" if detail else "")})

    rec = getattr(app_state, "quote_recorder", None)
    try:
        rs = rec.status() if rec else None
    except Exception:
        rs = None
    market_hours = _dt.time(9, 29) <= now.time() <= _dt.time(16, 1) and now.weekday() < 5
    if rs is None:
        rows.append({"name": "quote recorder", "kind": "recorder", "status": "idle", "reason": "not running in this service"})
    else:
        ok = rs.get("on") and (rs.get("watching") or not market_hours)
        rows.append({"name": "quote recorder", "kind": "recorder", "status": "ok" if ok else ("warn" if market_hours else "idle"),
                     "reason": f"watching {rs.get('watching')} contracts, {rs.get('written')} rows written"
                               + (f"; last error: {rs['last_error']}" if rs.get("last_error") else "")})

    runner = getattr(app_state, "runner", None)
    arms = getattr(app_state, "arms", None)
    try:
        sessions = runner.sessions() if runner else []
    except Exception:
        sessions = []
    by_slug: dict[str, dict] = {}
    for s in sessions:                                        # the newest session of each strategy
        if s.get("mode") == "live" and s.get("strategy") not in by_slug:
            by_slug[s["strategy"]] = s
    try:
        armed = arms.arms() if arms else []
    except Exception:
        armed = []
    seen = set()
    today = now.date().isoformat()
    for a in sorted(armed, key=lambda a: str((a.get("window") or {}).get("at") or "")):
        slug = a.get("strategy"); seen.add(slug)
        w = a.get("window") or {}
        at = _dt.time.fromisoformat(w["at"]) if w.get("at") else None
        until = _dt.time.fromisoformat(w["until"]) if w.get("until") else None
        s = by_slug.get(slug) or {}
        pid = s.get("pid") or a.get("pid")
        info = _proc_info(pid)
        age, note, hb = _heartbeat(slug)
        ran = str(a.get("last_run_date") or "")[:10] == today
        status, reason = runner_status(now, at=at, until=until, alive=info.get("alive", False), ran_today=ran,
                                       hb_age_s=age, hb_note=note, returncode=s.get("returncode"), kind=a.get("kind") or "runner")
        rows.append({"name": f"runner: {slug}", "kind": a.get("kind") or "runner", "strategy": slug, "status": status,
                     "reason": reason, "pid": pid if info.get("alive") else None, **{k: v for k, v in info.items() if k != "alive"},
                     "heartbeat_age_s": age, "window": f"{w.get('at', '')}-{w.get('until', '')}",
                     "last_log": _last_log_line(s.get("log") or a.get("log")), "day_pnl": (hb or {}).get("marked")})
    for slug, s in by_slug.items():                           # a runner nobody armed (started by hand, another checkout)
        if slug in seen or s.get("state") != "running":
            continue
        info = _proc_info(s.get("pid"))
        age, note, hb = _heartbeat(slug)
        status, reason = runner_status(now, at=None, until=None, alive=info.get("alive", True), ran_today=True,
                                       hb_age_s=age, hb_note=note)
        rows.append({"name": f"runner: {slug}", "kind": "runner", "strategy": slug, "status": status,
                     "reason": reason + " (not armed)", "pid": s.get("pid"), **{k: v for k, v in info.items() if k != "alive"},
                     "heartbeat_age_s": age, "last_log": _last_log_line(s.get("log")), "day_pnl": (hb or {}).get("marked")})

    desk = _desk_feed()
    in_session = _dt.time(9, 40) <= now.time() <= _dt.time(16, 1) and now.weekday() < 5
    rows.append({"name": "desk: claude (feed)", "kind": "desk", "status": "ok" if desk.get("alive") else ("warn" if in_session else "idle"),
                 "reason": "running" if desk.get("alive") else ("not running (Claude's session may be closed)" if in_session else "outside the session"),
                 "pid": desk.get("pid"), **{k: v for k, v in desk.items() if k not in ("alive", "pid")}})

    summary = {k: sum(1 for r in rows if r["status"] == k) for k in ("ok", "warn", "bad", "idle")}
    return {"asof": now.isoformat(timespec="seconds"), "summary": summary, "rows": rows}
