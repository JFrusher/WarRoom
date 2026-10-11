"""Append-only match journal (JSON lines).

Every scored event is recorded here so a match can be replayed and turned
into an after-action report. The journal, not in-memory state, is the record
of truth that survives a referee restart.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from config import settings


def append(kind: str, payload: dict) -> dict:
    """Append one timestamped entry and return it."""
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "kind": kind, **payload}
    settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
    with settings.JOURNAL.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def read_all() -> list[dict]:
    """Return every journal entry, oldest first."""
    try:
        lines = settings.JOURNAL.read_text().splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
