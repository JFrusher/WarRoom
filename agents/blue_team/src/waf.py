"""Signature matching against logged requests."""
from __future__ import annotations

from config import rules


def inspect(entry: dict) -> list[str]:
    """Return the list of attack vectors whose signatures match this request.

    The request path, query string, and body are concatenated and tested
    against every signature group.
    """
    haystack = " ".join(
        str(entry.get(field, "")) for field in ("path", "query", "body")
    )
    hits: list[str] = []
    for vector, patterns in rules.SIGNATURES.items():
        if any(pattern.search(haystack) for pattern in patterns):
            hits.append(vector)
    return hits
