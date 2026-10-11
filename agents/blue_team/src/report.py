"""Best-effort defence telemetry for the referee (which scores and forwards)."""
from __future__ import annotations

import logging

import requests

from config import settings

log = logging.getLogger("blue.report")


def emit(kind: str, payload: dict) -> None:
    try:
        requests.post(
            f"{settings.REFEREE_URL}/ingest",
            json={"kind": kind, "team": "blue", **payload},
            timeout=2.0,
        )
    except requests.RequestException as exc:
        log.debug("referee report failed: %s", exc)
