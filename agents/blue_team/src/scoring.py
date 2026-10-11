"""Per-IP threat scoring."""
from __future__ import annotations

from collections import defaultdict

from config import rules


class ThreatTable:
    """Accumulates threat points per source IP and flags block candidates."""

    def __init__(self) -> None:
        self._scores: dict[str, int] = defaultdict(int)

    def record(self, ip: str, hit_count: int) -> int:
        """Add points for ``hit_count`` signature hits and return the new score."""
        self._scores[ip] += hit_count * rules.HIT_SCORE
        return self._scores[ip]

    def should_block(self, ip: str) -> bool:
        return self._scores[ip] >= rules.BLOCK_THRESHOLD

    def score(self, ip: str) -> int:
        return self._scores[ip]
