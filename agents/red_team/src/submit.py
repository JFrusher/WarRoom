"""Submit captured flags to the target scoreboard."""
from __future__ import annotations

import logging

import requests

from config import settings
from src.errors import SubmissionError

log = logging.getLogger("red.submit")


def submit(sess: requests.Session, flag: str, vector: str) -> dict:
    """Send a captured flag to the referee for scoring and return the verdict."""
    try:
        resp = sess.post(
            f"{settings.REFEREE_URL}/flags/submit",
            json={"flag": flag, "vector": vector},
            timeout=settings.HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise SubmissionError(f"submission request failed: {exc}") from exc

    body = resp.json() if resp.content else {}
    status = body.get("status")
    if status not in {"accepted", "duplicate"}:
        raise SubmissionError(body.get("reason", "flag rejected"))
    log.info("flag %s via %s -> %s", flag, vector, status)
    return body
