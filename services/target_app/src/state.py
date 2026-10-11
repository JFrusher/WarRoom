"""Runtime state shared with the blue team over the state volume.

Two tiny JSON files back this module:

* ``mitigations.json`` - per-vulnerability patch switches the blue team flips.
* ``blocklist.json``   - IPs the blue team is currently rate-limiting.

The target reads both on every request, so a blue-team change applies with no
restart. That is the whole point of "hot-patching without breaking SLA".
"""
from __future__ import annotations

import json

from config import settings

_DEFAULT_MITIGATIONS = {
    "sqli": False, "xss": False, "cmdi": False, "idor": False, "ssrf": False,
}


def _read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def mitigations() -> dict[str, bool]:
    """Return the current patch switches, defaulting to all-vulnerable."""
    data = _read_json(settings.MITIGATIONS_FILE, {})
    return {**_DEFAULT_MITIGATIONS, **data}


def is_patched(vuln: str) -> bool:
    return bool(mitigations().get(vuln, False))


def blocked_ips() -> set[str]:
    data = _read_json(settings.BLOCKLIST_FILE, [])
    return set(data) if isinstance(data, list) else set()
