"""Minimal, lab-scoped payload variants.

These exist only so the red/blue game has a second move: when the blue team's
WAF starts blocking a textbook payload, the agent retries with one lightly
varied form. This is intentionally *not* a general-purpose evasion toolkit;
it is three fixed alternates, one per bug, aimed at this lab's target.
"""
from __future__ import annotations


def sqli_variant(payload: str) -> str:
    """Swap spaces for inline comments, a classic WAF-space-filter dodge."""
    return payload.replace(" ", "/**/")


def xss_variant(payload: str) -> str:
    """Re-case the tag name to slip a case-sensitive ``<script`` match."""
    return payload.replace("<script", "<ScRiPt").replace("</script", "</ScRiPt")


def cmdi_variant(payload: str) -> str:
    """Use a newline separator instead of ``;`` to dodge a semicolon filter."""
    return payload.replace("; ", "\n")
