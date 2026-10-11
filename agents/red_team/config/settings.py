"""Red-team configuration.

The target is fixed to the lab. There is deliberately no command-line or
free-form override: the agent resolves its target from a small allow-list and
refuses to run against anything else. This keeps the tooling confined to the
local range it was built for.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

# Only these authorities are ever acceptable as a target.
_ALLOWED_HOSTS = {
    "target_app:5000",   # Compose service name
    "127.0.0.1:5000",    # loopback
    "localhost:5000",
}

# The referee adjudicates captures; it is also confined to the lab.
_ALLOWED_REFEREES = {
    "referee:9000",
    "127.0.0.1:9000",
    "localhost:9000",
}

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://dashboard:8080")

HTTP_TIMEOUT = 5.0
USER_AGENT = "warzone-red/1.0"


def resolve_target() -> str:
    """Return the validated target base URL or raise if it is off-range."""
    url = os.getenv("TARGET_URL", "http://target_app:5000").rstrip("/")
    authority = urlparse(url).netloc
    if authority not in _ALLOWED_HOSTS:
        raise ValueError(
            f"refusing to target {authority!r}; this agent is confined to the "
            f"local lab ({', '.join(sorted(_ALLOWED_HOSTS))})"
        )
    return url


def resolve_referee() -> str:
    """Return the validated referee base URL or raise if it is off-range."""
    url = os.getenv("REFEREE_URL", "http://referee:9000").rstrip("/")
    authority = urlparse(url).netloc
    if authority not in _ALLOWED_REFEREES:
        raise ValueError(
            f"refusing to use referee {authority!r}; this agent is confined to "
            f"the local lab ({', '.join(sorted(_ALLOWED_REFEREES))})"
        )
    return url


TARGET_URL = resolve_target()
REFEREE_URL = resolve_referee()
