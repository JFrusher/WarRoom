"""Signature matching against logged requests, driven by the rule files."""
from __future__ import annotations

from src import signatures


def _haystack(entry: dict) -> str:
    return " ".join(str(entry.get(field, "")) for field in ("path", "query", "body"))


def matched_rules(entry: dict) -> list[dict]:
    """Return the detection rules whose patterns match this request.

    A rule may scope itself to a path prefix so an endpoint-specific signature
    (e.g. SSRF on the fetch endpoint) does not fire on unrelated traffic.
    """
    hay = _haystack(entry)
    path = str(entry.get("path", ""))
    matched = []
    for rule in signatures.load():
        if rule.get("path") and rule["path"] not in path:
            continue
        if any(p.search(hay) for p in rule["compiled"]):
            matched.append(rule)
    return matched


def inspect(entry: dict) -> list[str]:
    """Return the attack vectors whose signatures match this request."""
    return [r["vector"] for r in matched_rules(entry)]
