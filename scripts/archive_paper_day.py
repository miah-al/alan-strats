"""Gather everything a paper session wrote into one dated folder, so an issue found days later can be
traced from a single place: the event log (every order event with both legs' quotes), the runner's own
diary (warnings, backoffs, halts, request counts), the session state and heartbeat, the reconciliation
against the backtest replay, and a snapshot of the day's ledger rows. Then zip the folder to a backup
location outside both repositories.

    python -m scripts.archive_paper_day --strategy ndx_0dte_tasty              # today
    python -m scripts.archive_paper_day --strategy ndx_0dte_tasty --day 2026-09-22 --backup-dir D:\\paper_backups

Archive folder: <strategy folder>/paper_log/archive/<date>/ (tracked by git, committed with the daily review).
Backup zip:     <backup-dir>/<slug>_<date>.zip (default: alan_trader_paper_archive/, a folder beside the alan_trader repo).
Exit code 1 when the day has no event log at all (nothing ran), so a scheduler can see it.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT.parent), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def gather(slug: str, day: date, strategy_folder: Path, backup_dir: Path) -> dict:
    """Copy the day's files into the archive folder and zip it. Returns what was saved and what was missing."""
    d = day.isoformat()
    log_dir = strategy_folder / "paper_log"
    archive = log_dir / "archive" / d
    archive.mkdir(parents=True, exist_ok=True)
    sources = {
        "events.csv": log_dir / f"{d}.csv",
        "reconcile.md": log_dir / f"reconcile_{d}.md",
        "runner.log": ROOT / "logs" / "paper" / f"{slug}_{d}.log",
        "state.json": ROOT / "paper_state" / f"{slug}_{d}.json",
        "heartbeat.json": ROOT / "paper_state" / f"heartbeat_{slug}.json",
    }
    saved, missing = [], []
    for name, src in sources.items():
        if src.exists():
            shutil.copy2(src, archive / name); saved.append(name)
        else:
            missing.append(name)
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
    ap.add_argument("--backup-dir", default=None, help="where the dated zip goes (default: alan_trader_paper_archive beside the alan_trader repo)")
    args = ap.parse_args(argv)
    from paper.runner import PaperSession
    folder = PaperSession._strategy_folder(args.strategy)
    if folder is None:
        print(f"cannot archive: strategy folder for {args.strategy} not found"); return 1
    day = date.fromisoformat(args.day) if args.day else date.today()
    backup_dir = Path(args.backup_dir) if args.backup_dir else ROOT.parent / "alan_trader_paper_archive"   # parallel to the repos, outside both
    r = gather(args.strategy, day, folder, backup_dir)
    print(f"{day} archived to {r['archive']}; backup {r['zip']}")
    print("  saved:", ", ".join(r["saved"]) or "nothing")
    if r["missing"]:
        print("  missing:", ", ".join(r["missing"]))
    return 1 if "events.csv" in r["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
