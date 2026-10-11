"""After-action report built from the match journal.

Turns the raw journal into the numbers a SOC actually reviews: who scored,
how fast each vector was detected and mitigated (MTTD / MTTR), and whether
the service stayed up.
"""
from __future__ import annotations

import sys
from datetime import datetime

from src import journal, scoring


def _ts(entry: dict) -> datetime:
    return datetime.fromisoformat(entry["ts"])


def _latency_by_vector(entries: list[dict], kind: str, round_start: dict[str, datetime]) -> dict:
    """Seconds from a round's start to the first matching event per vector."""
    out: dict[str, float] = {}
    for e in entries:
        if e["kind"] != kind or e["round"] not in round_start:
            continue
        vectors = e.get("vectors") or ([e["vector"]] if e.get("vector") else [])
        for vector in vectors:
            latency = (_ts(e) - round_start[e["round"]]).total_seconds()
            out[vector] = min(out.get(vector, latency), latency)
    return {v: round(s, 2) for v, s in out.items()}


def build(uptime: float | None = None) -> dict:
    entries = journal.read_all()
    captures = [e for e in entries if e["kind"] == "flag_captured"]
    detections = [e for e in entries if e["kind"] == "detection"]
    mitigations = [e for e in entries if e["kind"] == "mitigation"]
    round_start = {e["round"]: _ts(e) for e in entries if e["kind"] == "round_start"}

    red = sum(e.get("points", 0) for e in captures)
    blue = sum(e.get("points", 0) for e in entries if e.get("team") == "blue")
    if uptime is not None:  # same SLA term the live scoreboard applies
        blue += scoring.sla_points(uptime)

    return {
        "rounds": list(round_start),
        "scores": {"red": red, "blue": blue},
        "captures": [
            {"vector": e["vector"], "points": e["points"],
             "detected_first": e.get("detected_first")}
            for e in captures
        ],
        "vectors_detected": sorted({v for e in detections for v in e.get("vectors", [])}),
        "vectors_mitigated": sorted({e["vector"] for e in mitigations if e.get("vector")}),
        "techniques_detected": sorted({t for e in detections for t in e.get("techniques", [])}),
        "mttd_seconds": _latency_by_vector(entries, "detection", round_start),
        "mttr_seconds": _latency_by_vector(entries, "mitigation", round_start),
        "undetected_captures": [
            e["vector"] for e in captures if not e.get("detected_first")
        ],
    }


def render(report: dict) -> str:
    lines = [
        "WAR ZONE — after-action report",
        "=" * 34,
        f"rounds played : {len(report['rounds'])}",
        f"final score   : red {report['scores']['red']}  |  blue {report['scores']['blue']}",
        f"vectors detected : {', '.join(report['vectors_detected']) or 'none'}",
        f"vectors mitigated: {', '.join(report['vectors_mitigated']) or 'none'}",
        f"ATT&CK techniques: {', '.join(report['techniques_detected']) or 'none'}",
        f"MTTD (s)         : {report['mttd_seconds'] or 'n/a'}",
        f"MTTR (s)         : {report['mttr_seconds'] or 'n/a'}",
        f"captured before detection: {', '.join(report['undetected_captures']) or 'none'}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(print(render(build())))
