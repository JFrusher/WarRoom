"""Best-effort attack telemetry for the dashboard live feed."""
from __future__ import annotations

import logging

import requests

from config import settings

log = logging.getLogger("red.report")


def emit(kind: str, payload: dict) -> None:
    try:
        requests.post(
            f"{settings.DASHBOARD_URL}/ingest",
            json={"kind": kind, "team": "red", **payload},
            timeout=2.0,
        )
    except requests.RequestException as exc:
        log.debug("dashboard report failed: %s", exc)
