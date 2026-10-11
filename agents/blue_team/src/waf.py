"""Signature matching against logged requests, driven by the rule files."""
from __future__ import annotations

from src import signatures


def _haystack(entry: dict) -> str:
    return " ".join(str(entry.get(field, "")) for field in ("path", "query", "body"))


def matched_rules(entry: dict) -> list[dict]:
    """Return the detection rules whose patterns match this request."""
    hay = _haystack(entry)
    return [r for r in signatures.load() if any(p.search(hay) for p in r["compiled"])]


def inspect(entry: dict) -> list[str]:
    """Return the attack vectors whose signatures match this request."""
    return [r["vector"] for r in matched_rules(entry)]
