"""Flag generation and rotation.

A single live flag is stored in two places on purpose, one per attack class:

* the ``flags`` table  -> reachable through SQL injection
* ``flag_current.txt`` -> reachable through arbitrary file read

The stored-XSS path leaks its own flag at runtime (see :mod:`src.app`).
"""
from __future__ import annotations

import logging
import secrets
import threading

from config import settings
from src import db
from src.errors import FlagUnavailableError

log = logging.getLogger("target.flags")


def mint() -> str:
    """Return a fresh, unguessable flag token."""
    return f"WARZONE{{{secrets.token_hex(12)}}}"


def rotate() -> str:
    """Generate a new flag and persist it to the DB and the flag file."""
    token = mint()
    db.set_flag(token)
    settings.FLAG_DIR.mkdir(parents=True, exist_ok=True)
    settings.FLAG_FILE.write_text(token + "\n")
    log.info("flag rotated")
    return token


def current() -> str:
    """Return the live flag, raising if storage has not been initialised."""
    token = db.get_flag()
    if not token:
        raise FlagUnavailableError("no flag has been minted yet")
    return token


def start_rotation() -> threading.Thread:
    """Spawn a daemon thread that rotates the flag on a fixed interval."""
    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(settings.FLAG_ROTATE_SECONDS):
            rotate()

    thread = threading.Thread(target=_loop, name="flag-rotator", daemon=True)
    thread.start()
    return thread
