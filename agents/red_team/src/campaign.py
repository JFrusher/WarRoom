"""Kill-chain definition: run vectors in ATT&CK order and report coverage.

The stages are ordered the way a real intrusion flows, each labelled with the
MITRE ATT&CK tactic it represents, so a campaign demonstrates attacks as a
chain rather than as isolated point exploits.
"""
from __future__ import annotations

# (vector, ATT&CK tactic) in intended execution order.
CHAIN: list[tuple[str, str]] = [
    ("ssrf", "TA0007 Discovery"),
    ("idor", "TA0009 Collection"),
    ("jwt", "TA0006 Credential Access"),
    ("sqli", "TA0006 Credential Access"),
    ("ssti", "TA0002 Execution"),
    ("cmdi", "TA0002 Execution"),
    ("xss", "TA0002 Execution"),
]
