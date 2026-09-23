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


def test_archive_redacts_keys_the_runner_log_printed(tmp_path, monkeypatch):
    """The archive folder is committed; a DEBUG line with a request URL must not carry its key in."""
    from scripts import archive_paper_day as A
    day = date(2026, 9, 23); d = day.isoformat()
    strat = tmp_path / "strat"; (strat / "paper_log").mkdir(parents=True)
    root = tmp_path / "platform"; (root / "logs" / "paper").mkdir(parents=True)
    (root / "logs" / "paper" / f"ndx_0dte_tasty_{d}.log").write_bytes(
        b'2026-09-23 11:26:44,644 DEBUG urllib3.connectionpool: "GET /v2/aggs/x?adjusted=true&apiKey=Sup3rS3cretK3y HTTP/1.1" 403\r\n'
        b'2026-09-23 11:26:44,650 WARNING paper.providers: backfill failed: 403 for url /v2/aggs/x?apiKey=Sup3rS3cretK3y\r\n'
        b'2026-09-23 11:26:45,001 DEBUG httpcore2.http11: receive_response_headers.complete\r\n'
        b'2026-09-23 11:26:46,002 ERROR paper.runner: fetch failed\r\nTraceback (most recent call last):\r\n  boom\r\n')
    monkeypatch.setattr(A, "ROOT", root)
    r = A.gather("ndx_0dte_tasty", day, strat, tmp_path / "backup")
    kept = (r["archive"] / "runner.log").read_bytes()
    assert b"Sup3rS3cretK3y" not in kept and b"apiKey=REDACTED\r\n" in kept
    assert b" DEBUG " not in kept and kept.endswith(b"fetch failed\r\nTraceback (most recent call last):\r\n  boom\r\n")
    with zipfile.ZipFile(r["zip"]) as z:
        assert b"Sup3rS3cretK3y" not in z.read(f"{d}/runner.log")


def test_rearchiving_a_past_day_leaves_out_a_later_sessions_heartbeat(tmp_path, monkeypatch):
    from scripts import archive_paper_day as A
    strat = tmp_path / "strat"; (strat / "paper_log").mkdir(parents=True)
    root = tmp_path / "platform"; (root / "paper_state").mkdir(parents=True)
    hb = root / "paper_state" / "heartbeat_ndx_0dte_tasty.json"
    monkeypatch.setattr(A, "ROOT", root)
    hb.write_text(json.dumps({"day": "2026-09-23", "marked": 1.0}), encoding="utf-8")
    assert "heartbeat.json" in A.gather("ndx_0dte_tasty", date(2026, 9, 23), strat, tmp_path / "backup")["saved"]
    hb.write_text(json.dumps({"day": "2026-09-24", "marked": 2.0}), encoding="utf-8")      # the next session starts
    r = A.gather("ndx_0dte_tasty", date(2026, 9, 23), strat, tmp_path / "backup")          # the morning catch-up
    assert "heartbeat.json" in r["saved"] and json.loads((r["archive"] / "heartbeat.json").read_text(encoding="utf-8"))["marked"] == 1.0
    r = A.gather("ndx_0dte_tasty", date(2026, 9, 22), strat, tmp_path / "backup")          # a day never archived
    assert "heartbeat.json (holds 2026-09-24)" in r["missing"] and not (r["archive"] / "heartbeat.json").exists()
