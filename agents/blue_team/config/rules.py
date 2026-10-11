"""WAF signatures, scoring weights, and defence thresholds.

Signatures are deliberately pattern-based (not a full parser): the point of
the lab is to watch them catch textbook payloads and miss lightly obfuscated
ones, which is exactly how a regex WAF behaves in the wild.
"""
from __future__ import annotations

import os
import re

# Per-vector detection signatures matched against request path + body.
SIGNATURES: dict[str, list[re.Pattern]] = {
    "sqli": [
        re.compile(r"'\s*or\s*'?\d", re.I),
        re.compile(r"union\s+select", re.I),
        re.compile(r"'\s*--", re.I),
    ],
    "xss": [
        re.compile(r"<script", re.I),
        re.compile(r"onerror\s*=", re.I),
        re.compile(r"javascript:", re.I),
    ],
    "cmdi": [
        re.compile(r";\s*(cat|ls|id|whoami)\b", re.I),
        re.compile(r"\|\s*(cat|ls|id|whoami)\b", re.I),
        re.compile(r"/etc/passwd"),
    ],
}

# Threat points added to an IP's running score for each detected hit.
HIT_SCORE = 10

# Once an IP crosses this score it is rate-limited (blocked).
BLOCK_THRESHOLD = 25

# Infrastructure IPs that must never be blocked, to protect the SLA.
WHITELIST = set(filter(None, os.getenv("WHITELIST", "").split(",")))
