"""Shared-state writer: this is how the blue team hot-patches and blocks.

The target reads these two files on every request, so writing them applies a
fix or a block with no restart and no dropped connections.
"""
from __future__ import annotations

import json

from config import settings


def _read(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def enable_mitigation(vector: str) -> bool:
    """Switch on the safe code path for ``vector``. Return True if newly set."""
    settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
    current = _read(settings.MITIGATIONS_FILE, {})
    if current.get(vector):
        return False
    current[vector] = True
    settings.MITIGATIONS_FILE.write_text(json.dumps(current))
    return True


def block_ip(ip: str) -> bool:
    """Add ``ip`` to the rate-limit blocklist. Return True if newly added."""
    settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
    current = _read(settings.BLOCKLIST_FILE, [])
    if ip in current:
        return False
    current.append(ip)
    settings.BLOCKLIST_FILE.write_text(json.dumps(current))
    return True
