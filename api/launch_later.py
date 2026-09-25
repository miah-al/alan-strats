"""
python -m api.launch_later --at HH:MM [--date YYYY-MM-DD] -- <paper_runner arguments>

Wait until that time (ET) on that day, then run the platform's paper runner through the service's bootstrap
(api.runner_launch). The arms' fallback when the service itself will not be running at an arm's time: started
detached the evening before (api.services.arms.launch_later), it sleeps through the night and starts the session
before the open. Nothing else: it never trades, it only starts the runner at the time given.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
import time


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rest: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, rest = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="python -m api.launch_later")
    ap.add_argument("--at", required=True, help="HH:MM, US/Eastern")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today if the time is still ahead, else tomorrow)")
    a = ap.parse_args(argv)
    import zoneinfo
    ny = zoneinfo.ZoneInfo("America/New_York")
    hh, mm = (int(x) for x in a.at.split(":"))
    now = _dt.datetime.now(ny)
    day = _dt.date.fromisoformat(a.date) if a.date else (now.date() if now.time() < _dt.time(hh, mm)
                                                       else now.date() + _dt.timedelta(days=1))
    target = _dt.datetime.combine(day, _dt.time(hh, mm), tzinfo=ny)
    print(f"launch_later: waiting until {target.isoformat()} to run the paper runner {' '.join(rest)}", flush=True)
    while True:
        left = (target - _dt.datetime.now(ny)).total_seconds()
        if left <= 0:
            break
        time.sleep(min(60.0, left))
    if _dt.datetime.now(ny) - target > _dt.timedelta(hours=6):
        print("launch_later: more than 6 hours late; not starting", flush=True)
        return 4
    from api.runner_launch import main as run
    return int(run(rest) or 0)


if __name__ == "__main__":
    sys.exit(main())
