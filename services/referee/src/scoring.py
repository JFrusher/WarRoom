"""Scoring rubric: load the YAML config and compute points.

Keeping the formulas here (not scattered in the HTTP layer) means the rubric
is testable in isolation and tunable from one file.
"""
from __future__ import annotations

import functools

import yaml

from config import settings


@functools.lru_cache(maxsize=1)
def rubric() -> dict:
    return yaml.safe_load(settings.SCORING_FILE.read_text())


def valid_vectors() -> set[str]:
    return set(rubric()["valid_vectors"])


def _decay(base: float, elapsed: float, window: float) -> float:
    """Linear decay from ``base`` at elapsed=0 to 0 at elapsed>=window."""
    if elapsed <= 0:
        return base
    if elapsed >= window:
        return 0.0
    return base * (1 - elapsed / window)


def red_points(time_to_capture: float, detected_first: bool) -> int:
    r = rubric()["red"]
    pts = r["base"] + _decay(r["speed_bonus_max"], time_to_capture, r["speed_bonus_window"])
    if not detected_first:
        pts += r["stealth_bonus"]
    return round(pts)


def blue_detect_points(time_to_detect: float) -> int:
    b = rubric()["blue"]
    return round(_decay(b["detect_base"], time_to_detect, b["detect_window"]))


def blue_mitigate_points(time_to_mitigate: float) -> int:
    b = rubric()["blue"]
    return round(_decay(b["mitigate_base"], time_to_mitigate, b["mitigate_window"]))


def sla_points(uptime_fraction: float) -> int:
    return round(rubric()["blue"]["sla_weight"] * max(0.0, min(1.0, uptime_fraction)))


def false_positive_penalty(count: int) -> int:
    return rubric()["blue"]["false_positive_penalty"] * count
