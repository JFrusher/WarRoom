"""Match state machine: rounds, flag lifecycle, and authoritative scoring.

In-memory state is the live scoreboard; the journal is the durable record.
A match accumulates score across rounds; per-round state (which vectors are
already captured or detected) resets when a new round starts.
"""
from __future__ import annotations

import threading
import time
import uuid

from src import journal, oracle, scoring
from src.errors import NoActiveFlagError, NoActiveRoundError


class Match:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.round_id: str | None = None
        self.started_at: float | None = None
        self.red_score = 0
        self.blue_score = 0
        self._captured: set[str] = set()      # vectors red has scored this round
        self._detected: dict[str, float] = {}  # vector -> first detection time
        self._mitigated: set[str] = set()
        self.sla_ok = 0
        self.sla_total = 0

    # -- round lifecycle --------------------------------------------------- #
    def start_round(self) -> dict:
        with self._lock:
            self.round_id = uuid.uuid4().hex[:8]
            self.started_at = time.monotonic()
            self._captured.clear()
            self._detected.clear()
            self._mitigated.clear()
            oracle.write(self.round_id, oracle.mint())
            return journal.append("round_start", {"round": self.round_id})

    def rotate_flag(self) -> None:
        with self._lock:
            if self.round_id is None:
                return
            oracle.write(self.round_id, oracle.mint())
            journal.append("flag_rotated", {"round": self.round_id})

    def _elapsed(self) -> float:
        if self.started_at is None:
            raise NoActiveRoundError("no round is running")
        return time.monotonic() - self.started_at

    # -- scoring ----------------------------------------------------------- #
    def submit_flag(self, token: str, vector: str) -> dict:
        if vector not in scoring.valid_vectors():
            return {"status": "rejected", "reason": "unknown vector"}
        with self._lock:
            try:
                _, live = oracle.read()
            except NoActiveFlagError:
                return {"status": "rejected", "reason": "no active flag"}
            if token != live:
                return {"status": "rejected", "reason": "stale or incorrect flag"}
            if vector in self._captured:
                return {"status": "duplicate", "vector": vector}
            self._captured.add(vector)
            detected_first = vector in self._detected
            points = scoring.red_points(self._elapsed(), detected_first)
            self.red_score += points
            journal.append(
                "flag_captured",
                {"round": self.round_id, "vector": vector, "points": points,
                 "detected_first": detected_first, "team": "red"},
            )
            return {"status": "accepted", "vector": vector, "points": points}

    def ingest_blue(self, event: dict) -> dict:
        """Score a blue detection/mitigation/block event. Returns the enriched
        event (with awarded points) for forwarding to the dashboard."""
        kind = event.get("kind")
        with self._lock:
            valid = scoring.valid_vectors()
            points = 0
            if kind == "detection":
                for vector in event.get("vectors", []):
                    if vector in valid and vector not in self._detected:
                        self._detected[vector] = self._elapsed()
                        points += scoring.blue_detect_points(self._detected[vector])
            elif kind == "mitigation":
                vector = event.get("vector")
                if vector in valid and vector not in self._mitigated:
                    self._mitigated.add(vector)
                    points = scoring.blue_mitigate_points(self._elapsed())
            self.blue_score += points
            enriched = {**event, "team": "blue", "points": points}
            journal.append(kind or "blue_event", {"round": self.round_id, **enriched})
            return enriched

    def record_sla(self, ok: bool) -> None:
        with self._lock:
            self.sla_total += 1
            if ok:
                self.sla_ok += 1

    def uptime(self) -> float:
        return self.sla_ok / self.sla_total if self.sla_total else 1.0

    def restore(self) -> None:
        """Rebuild cumulative scores from the durable journal after a restart,
        so /state agrees with the journal-based /report."""
        with self._lock:
            entries = journal.read_all()
            self.red_score = sum(
                e.get("points", 0) for e in entries if e.get("kind") == "flag_captured"
            )
            self.blue_score = sum(
                e.get("points", 0) for e in entries if e.get("team") == "blue"
            )

    def state(self) -> dict:
        with self._lock:
            # SLA is a live metric (not journalled); fold it into the blue
            # total so availability counts, per the rubric's sla_weight.
            blue = self.blue_score + scoring.sla_points(self.uptime())
            return {
                "round": self.round_id,
                "scores": {"red": self.red_score, "blue": blue},
                "uptime": round(100 * self.uptime(), 2),
                "captured": sorted(self._captured),
                "detected": sorted(self._detected),
                "mitigated": sorted(self._mitigated),
            }
