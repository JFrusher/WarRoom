"""Fire-and-forget event publishing to the dashboard.

The dashboard owns the scoreboard; the target just reports facts (a flag was
captured, the service answered a health check). Network hiccups must never
take the target down, so every publish swallows transport errors.
"""
from __future__ import annotations

import logging

import requests

from config import settings

log = logging.getLogger("target.events")

_TIMEOUT = 2.0


def publish(kind: str, payload: dict) -> None:
    """POST a single event to the dashboard ingest endpoint."""
    try:
        requests.post(
            f"{settings.DASHBOARD_URL}/ingest",
            json={"kind": kind, **payload},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        log.debug("dashboard publish failed (%s): %s", kind, exc)
