"""The ledger's fill notes: JSON that always parses and always fits portfolio.[Transaction].Notes.

Until 2026-11-02 the column was NVARCHAR(500) and the ledgers cut each note at 500 characters. A runner's entry note
(its reason, with the quote and the chain odds) runs past that, so the cut fell inside the JSON and the app lost the
entry's quote, reason and index level (the Trades tab's "Cost vs mid" then counted only settlements). The column is
NVARCHAR(2000) now (db/schema.sql); a note longer than that loses the end of its reason, never the JSON around it.
"""
from __future__ import annotations

import json

NOTES_MAX = 2000                  # portfolio.[Transaction].Notes, NVARCHAR(2000)
CLOSE_PREFIX = "CLOSE "           # the Paper Trading page closes a trade group on a note that starts with it


def note_json(payload: dict, limit: int = NOTES_MAX - len(CLOSE_PREFIX)) -> str:
    """``payload`` as JSON within ``limit`` characters: an over-long ``reason`` is shortened (ending "..."), so the note
    stays valid JSON. Only a payload too long without any reason is returned over the limit; the insert's own cut at
    NOTES_MAX still keeps the row writable then."""
    out = json.dumps(payload, default=str)
    reason = payload.get("reason")
    while len(out) > limit and isinstance(reason, str) and reason:
        keep = len(reason) - (len(out) - limit) - len("...")
        reason = reason[:keep] + "..." if keep > 0 else ""
        out = json.dumps({**payload, "reason": reason}, default=str)
    return out
