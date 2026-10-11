"""Attack profiles: how loud the red agent is.

loud    — no delay, textbook payloads first (easy for the WAF to catch).
stealth — jitter between requests and lead with the obfuscated payload, trying
          to capture a flag before the blue team's signature fires. The referee
          awards a stealth bonus for a capture that happens before detection.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    min_delay: float
    max_delay: float
    obfuscate_first: bool


LOUD = Profile("loud", 0.0, 0.0, False)
STEALTH = Profile("stealth", 0.4, 1.2, True)
_BY_NAME = {p.name: p for p in (LOUD, STEALTH)}

ACTIVE: Profile = LOUD


def use(name: str) -> Profile:
    """Select the active profile by name."""
    global ACTIVE
    ACTIVE = _BY_NAME[name]
    return ACTIVE


def payload_order(primary: str, variant: str) -> tuple[str, str]:
    """Return the two payload forms in the order this profile should try them."""
    return (variant, primary) if ACTIVE.obfuscate_first else (primary, variant)


def pace() -> None:
    """Sleep a profile-dependent jitter between actions."""
    if ACTIVE.max_delay > 0:
        time.sleep(random.uniform(ACTIVE.min_delay, ACTIVE.max_delay))
