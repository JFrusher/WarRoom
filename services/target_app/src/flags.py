"""Flag mirroring.

The referee is authoritative for the flag; it publishes the live value to the
shared state volume. The target mirrors that value into two places it can leak
from: the ``flags`` table (reachable via SQL injection) and
``flag_current.txt`` (reachable via arbitrary file read). The stored-XSS path
leaks it at runtime via the admin bot.
"""
from __future__ import annotations

import json
import logging
import threading

from config import settings
from src import db
from src.errors import FlagUnavailableError

log = logging.getLogger("target.flags")


def current() -> str:
    """Return the live flag the referee has published, or raise."""
    try:
        return json.loads(settings.SHARED_FLAG_FILE.read_text())["token"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        raise FlagUnavailableError("referee has not published a flag yet") from exc


def sync() -> None:
    """Mirror the published flag into the DB and flag file so it leaks."""
    try:
        token = current()
    except FlagUnavailableError:
        return
    db.set_flag(token)
    settings.FLAG_DIR.mkdir(parents=True, exist_ok=True)
    settings.FLAG_FILE.write_text(token + "\n")


def start_sync() -> threading.Thread:
    """Spawn a daemon thread that keeps the mirror current as the flag rotates."""
    def _loop() -> None:
        while True:
            sync()
            threading.Event().wait(settings.FLAG_SYNC_SECONDS)

    thread = threading.Thread(target=_loop, name="flag-sync", daemon=True)
    thread.start()
    return thread
