"""Behavioural detection: catch what static signatures cannot.

IDOR has no payload to match, so a regex WAF never sees it. Watching the
*pattern* of access does: a client walking several distinct object ids in a
short span is enumerating. This is the behavioural complement to the rule
files and the only way the blue team catches the IDOR vector.
"""
from __future__ import annotations

import re
from collections import defaultdict

_PROFILE_RE = re.compile(r"/api/v1/users/(\d+)/profile")

# Distinct object ids from one IP before enumeration is called.
ENUM_THRESHOLD = 2


class BehaviourDetector:
    def __init__(self) -> None:
        self._profile_ids: dict[str, set[str]] = defaultdict(set)
        self._fired: set[tuple[str, str]] = set()

    def inspect(self, entry: dict) -> list[dict]:
        """Return behavioural detections for this request (once per IP+vector)."""
        ip = entry.get("ip") or "unknown"
        hits: list[dict] = []
        match = _PROFILE_RE.search(str(entry.get("path", "")))
        if match:
            self._profile_ids[ip].add(match.group(1))
            key = (ip, "idor")
            if len(self._profile_ids[ip]) >= ENUM_THRESHOLD and key not in self._fired:
                self._fired.add(key)
                hits.append({"vector": "idor", "techniques": ["T1087"]})  # Account Discovery
        return hits
