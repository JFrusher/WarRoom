"""Reconnaissance: fingerprint the target and read its patch posture."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from config import settings
from src import client
from src.errors import ReconError

log = logging.getLogger("red.recon")


@dataclass
class Recon:
    forms: list[str] = field(default_factory=list)
    mitigations: dict[str, bool] = field(default_factory=dict)
    reachable: bool = False


def run(sess: requests.Session) -> Recon:
    """Pull the landing page and health endpoint to map the attack surface."""
    try:
        resp = sess.get(client.url("/"), timeout=settings.HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise ReconError(f"target unreachable: {exc}") from exc

    soup = BeautifulSoup(resp.text, "html.parser")
    forms = [f.get("id", "<unnamed>") for f in soup.find_all("form")]

    health = client.get_json(sess, "/healthz")
    recon = Recon(
        forms=forms,
        mitigations=health.get("mitigations", {}),
        reachable=resp.status_code == 200,
    )
    log.info("recon: forms=%s mitigations=%s", recon.forms, recon.mitigations)
    return recon
