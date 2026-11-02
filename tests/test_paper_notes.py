"""paper/notes.py: a fill note is always valid JSON within the ledger's Notes column (2026-11-02: the old 500 cut fell
inside the JSON of every long entry note, and the app lost the entry's quote, reason and index level)."""
from __future__ import annotations

import json

from paper.notes import CLOSE_PREFIX, NOTES_MAX, note_json

# today's SPX 13:00 entry reason (the note the 500 cut broke), with its parity quote the app reads the mid from
REASON = ("13:00 SPX 7604.60: room max(10, 0.8 x straddle 21.10) = 16.88; short 7625 = the first strike >= 7621.48 | "
          "mid less 0.05 (the fill rule: SPXW spread orders trade within a nickel of the mid) | priced via call parity | "
          "call 7625/7635 bid 1.55 ask 1.70 mid 1.62 age 0 (the credit 1.57) | put 7625/7635 bid 8.10 ask 8.60 mid 8.35 "
          "age 0 | chain odds: P(win) 76.7%, P(full loss) 11.5%")
FILL = {"spread_px": 8.43, "kind": "open", "reason": REASON, "minute": 781, "lots": 6, "k_low": 7625.0,
        "k_high": 7635.0, "direction": "bear", "underlying_px": 7604.6, "provider": "tastytrade"}


def test_a_real_entry_note_is_kept_whole():
    note = note_json(FILL)
    assert len(note) > 500                      # the length the old cut broke
    assert json.loads(note) == FILL             # nothing lost: the app reads the quote and the index level from it


def test_a_closing_note_fits_the_column_with_its_prefix():
    assert len(CLOSE_PREFIX + note_json(FILL)) <= NOTES_MAX


def test_an_over_long_reason_is_shortened_and_the_json_still_parses():
    big = {**FILL, "reason": REASON * 20}       # ~7,000 characters of reason
    note = note_json(big)
    parsed = json.loads(note)
    assert len(note) <= NOTES_MAX - len(CLOSE_PREFIX)
    assert parsed["reason"].endswith("...") and parsed["reason"].startswith(REASON[:100])
    assert {k: v for k, v in parsed.items() if k != "reason"} == {k: v for k, v in FILL.items() if k != "reason"}


def test_escaped_characters_count_toward_the_limit():
    quoted = {**FILL, "reason": 'he said "sell" \\ ' * 400}
    note = note_json(quoted, limit=600)
    assert len(note) <= 600
    json.loads(note)


def test_a_note_without_a_reason_is_left_alone():
    assert json.loads(note_json({"kind": "close", "reason": "settle"})) == {"kind": "close", "reason": "settle"}
