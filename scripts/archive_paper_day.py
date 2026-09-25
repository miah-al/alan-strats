"""Gather everything a paper session wrote into one dated folder, so an issue found days later can be
traced from a single place: the event log (every order event with both legs' quotes), the runner's own
diary (warnings, backoffs, halts, request counts), the session state and heartbeat, the reconciliation
against the backtest replay, and a snapshot of the day's ledger rows. Then zip the folder to a backup
location outside both repositories.

    python -m scripts.archive_paper_day --strategy ndx_0dte_tasty              # today
    python -m scripts.archive_paper_day --strategy ndx_0dte_tasty --day 2026-09-22 --backup-dir D:\\paper_backups

Archive folder: <strategy folder>/paper_log/archive/<date>/ (tracked by git, committed with the daily review).
Backup zip:     <backup-dir>/<slug>_<date>.zip (default: alan-trader-logs/, a folder beside the alan_trader repo).
Exit code 1 when the day has no event log at all (nothing ran), so a scheduler can see it.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# alan_trader is this checkout by file path, whatever its folder is called; the parent stays off sys.path
# (beside the live checkout it would expose that copy) — api/bootstrap.py.
from api.bootstrap import register_platform_package  # noqa: E402

register_platform_package()

# credentials carried in a query string, as urllib3's DEBUG log prints them
_SECRET_IN_URL = re.compile(rb"(?i)((?:api[_-]?key|access_token|refresh_token|client_secret)=)[^&\s\"')]+")


_RECORD_START = re.compile(rb"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} ([A-Z]+) ")


def _without_debug(log: bytes) -> bytes:
    """The runner's diary without DEBUG records. A session run with -v logs every HTTP exchange (2.5 of
    2026-09-23's 2.8 MB); the full file stays in logs/paper/. A traceback's lines go with their record."""
    keep, out = True, []
    for line in log.splitlines(keepends=True):
        m = _RECORD_START.match(line)
        if m:
            keep = m.group(1) != b"DEBUG"
        if keep:
            out.append(line)
    return b"".join(out)


def _day_of(path: Path):
    """The session day a heartbeat was written for, or None when it cannot be read."""
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("day")
    except Exception:
        return None


def gather(slug: str, day: date, strategy_folder: Path, backup_dir: Path) -> dict:
    """Copy the day's files into the archive folder and zip it. Returns what was saved and what was missing."""
    d = day.isoformat()
    log_dir = strategy_folder / "paper_log"
    archive = log_dir / "archive" / d
    archive.mkdir(parents=True, exist_ok=True)
    sources = {
        "events.csv": log_dir / f"{d}.csv",
        "marks.csv": log_dir / f"marks_{d}.csv",          # every poll's mark against the target, between bar checks
        "reconcile.md": log_dir / f"reconcile_{d}.md",
        "runner.log": ROOT / "logs" / "paper" / f"{slug}_{d}.log",
        "state.json": ROOT / "paper_state" / f"{slug}_{d}.json",
        "heartbeat.json": ROOT / "paper_state" / f"heartbeat_{slug}.json",
    }
    saved, missing = [], []
    for name, src in sources.items():
        if not src.exists():
            missing.append(name)
        elif name == "heartbeat.json" and _day_of(src) not in (None, d):
            # one file per strategy, rewritten every session: a later day's must not be filed under this one;
            # a copy saved when this day was first archived is kept
            if _day_of(archive / name) == d:
                saved.append(name)
            else:
                missing.append(f"heartbeat.json (holds {_day_of(src)})")
        elif name == "runner.log":
            # the archive is committed, and a DEBUG line prints whole request URLs, key and all (2026-09-23)
            (archive / name).write_bytes(_SECRET_IN_URL.sub(rb"\1REDACTED", _without_debug(src.read_bytes()))); saved.append(name)
        else:
            shutil.copy2(src, archive / name); saved.append(name)
    # the ledger rows the runner wrote for the day, as the page will show them
    try:
        from db.client import get_engine
        from paper.ledger import load_paper_positions
        df = load_paper_positions(get_engine(), slug, from_date=day)
        df = df[df["OpenDate"].astype(str).str[:10] == d] if len(df) else df
        (archive / "ledger_positions.csv").write_text(df.to_csv(index=False), encoding="utf-8"); saved.append("ledger_positions.csv")
    except Exception as exc:
        (archive / "ledger_positions.err").write_text(str(exc), encoding="utf-8"); missing.append(f"ledger_positions.csv ({exc})")
    (archive / "manifest.json").write_text(json.dumps({"slug": slug, "day": d, "saved": saved, "missing": missing}, indent=2), encoding="utf-8")
    backup_dir.mkdir(parents=True, exist_ok=True)
    zip_path = backup_dir / f"{slug}_{d}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(archive.iterdir()):
            z.write(f, f"{d}/{f.name}")
    return {"archive": archive, "zip": zip_path, "saved": saved, "missing": missing}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--day", default=None)
    ap.add_argument("--backup-dir", default=None, help="where the dated zip goes (default: alan-trader-logs, beside the alan_trader repo)")
    args = ap.parse_args(argv)
    from paper.runner import PaperSession
    folder = PaperSession._strategy_folder(args.strategy)
    if folder is None:
        print(f"cannot archive: strategy folder for {args.strategy} not found"); return 1
    day = date.fromisoformat(args.day) if args.day else date.today()
    backup_dir = Path(args.backup_dir) if args.backup_dir else ROOT.parent / "alan-trader-logs"   # parallel to the repos, outside both
    r = gather(args.strategy, day, folder, backup_dir)
    print(f"{day} archived to {r['archive']}; backup {r['zip']}")
    print("  saved:", ", ".join(r["saved"]) or "nothing")
    if r["missing"]:
        print("  missing:", ", ".join(r["missing"]))
    return 1 if "events.csv" in r["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
