"""Scenario loader: which vulnerabilities are present in this match."""
from __future__ import annotations

import functools

import yaml

from config import settings


@functools.lru_cache(maxsize=1)
def _scenario() -> dict:
    return yaml.safe_load(settings.SCENARIO_FILE.read_text())


def name() -> str:
    return _scenario().get("name", "default")


def enabled(vector: str) -> bool:
    return vector in _scenario().get("enabled", [])
