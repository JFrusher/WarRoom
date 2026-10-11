"""After-action report built from the match journal.

Turns the raw journal into the numbers a SOC actually reviews: who scored,
how fast each vector was detected and mitigated (MTTD / MTTR), and whether
the service stayed up.
"""
from __future__ import annotations

import sys

from src import journal


def build() -> dict:
    entries = journal.read_all()
    captures = [e for e in entries if e["kind"] == "flag_captured"]
    detections = [e for e in entries if e["kind"] == "detection"]
    mitigations = [e for e in entries if e["kind"] == "mitigation"]

    red = sum(e.get("points", 0) for e in captures)
    blue = sum(e.get("points", 0) for e in entries if e.get("team") == "blue")

    return {
        "rounds": [e["round"] for e in entries if e["kind"] == "round_start"],
        "scores": {"red": red, "blue": blue},
        "captures": [
            {"vector": e["vector"], "points": e["points"],
             "detected_first": e.get("detected_first")}
            for e in captures
        ],
        "vectors_detected": sorted({v for e in detections for v in e.get("vectors", [])}),
        "vectors_mitigated": sorted({e["vector"] for e in mitigations if e.get("vector")}),
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
        f"captured before detection: {', '.join(report['undetected_captures']) or 'none'}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(print(render(build())))
