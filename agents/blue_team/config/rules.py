"""Scoring weights and defence thresholds.

Detection signatures live as data in config/rules/*.yml (loaded by
src.signatures); this module holds only the numeric knobs.
"""
from __future__ import annotations

import os

# Threat points added to an IP's running score for each detected hit.
HIT_SCORE = 10

# Graduated response ladder by threat score: observe < throttle < block.
# Hot-patching the matched vector happens on first detection, independent of
# these thresholds.
THROTTLE_THRESHOLD = 15
BLOCK_THRESHOLD = 25

# Infrastructure IPs that must never be blocked, to protect the SLA.
WHITELIST = set(filter(None, os.getenv("WHITELIST", "").split(",")))
