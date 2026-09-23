"""The end-of-day archive gathers every file a session wrote into one dated folder and a zip, and says
what was missing (offline: a temp strategy folder, temp log and state dirs, no database)."""
from __future__ import annotations

import json
import zipfile
from datetime import date


def test_archive_gathers_the_days_files(tmp_path, monkeypatch):
    from scripts import archive_paper_day as A
    day = date(2026, 9, 22); d = day.isoformat()
    strat = tmp_path / "strat"; (strat / "paper_log").mkdir(parents=True)
    (strat / "paper_log" / f"{d}.csv").write_text("ts,event\n2026-09-22 11:00:00,open\n", encoding="utf-8")
    (strat / "paper_log" / f"reconcile_{d}.md").write_text("# ok\n", encoding="utf-8")
    root = tmp_path / "platform"; (root / "logs" / "paper").mkdir(parents=True); (root / "paper_state").mkdir()
    (root / "logs" / "paper" / f"ndx_0dte_tasty_{d}.log").write_text("INFO fine\n", encoding="utf-8")
    (root / "paper_state" / f"ndx_0dte_tasty_{d}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(A, "ROOT", root)
    r = A.gather("ndx_0dte_tasty", day, strat, tmp_path / "backup")
    assert set(r["saved"]) >= {"events.csv", "reconcile.md", "runner.log", "state.json"}
    assert "heartbeat.json" in r["missing"]                                  # not written: reported, not fatal
    assert (r["archive"] / "manifest.json").exists() and (r["archive"] / "runner.log").read_text(encoding="utf-8") == "INFO fine\n"
    with zipfile.ZipFile(r["zip"]) as z:
        names = z.namelist()
    assert f"{d}/events.csv" in names and f"{d}/manifest.json" in names
    assert json.loads((r["archive"] / "manifest.json").read_text(encoding="utf-8"))["day"] == d
