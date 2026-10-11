"""Authoritative flag store, shared with the target via the state volume."""
from __future__ import annotations

import json
import os
import secrets
import tempfile

from config import settings
from src.errors import NoActiveFlagError


def mint() -> str:
    """Return a fresh, unguessable flag token."""
    return f"WARZONE{{{secrets.token_hex(12)}}}"


def write(round_id: str, token: str) -> None:
    """Publish the current flag atomically for the target to mirror."""
    settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"round": round_id, "token": token})
    fd, tmp = tempfile.mkstemp(dir=str(settings.STATE_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(payload)
        os.replace(tmp, settings.FLAG_FILE)
    except BaseException:
        os.unlink(tmp)
        raise


def read() -> tuple[str, str]:
    """Return ``(round_id, token)`` for the live flag, or raise."""
    try:
        data = json.loads(settings.FLAG_FILE.read_text())
        return data["round"], data["token"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        raise NoActiveFlagError("no flag has been minted") from exc
