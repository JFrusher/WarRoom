"""Detection-as-code: load and compile the rule files under config/rules/.

Rules are data, not code: each lives in its own versioned YAML file carrying a
severity and a MITRE ATT&CK technique id, and is unit-tested. Adding a
detection means adding a file, not editing Python.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).resolve().parents[1] / "config" / "rules"
_REQUIRED = {"id", "title", "vector", "severity", "mitre", "patterns"}


@functools.lru_cache(maxsize=1)
def load() -> list[dict]:
    """Return every rule with its patterns pre-compiled, sorted by filename."""
    rules: list[dict] = []
    for path in sorted(RULES_DIR.glob("*.yml")):
        raw = yaml.safe_load(path.read_text())
        missing = _REQUIRED - raw.keys()
        if missing:
            raise ValueError(f"{path.name} is missing fields: {sorted(missing)}")
        rules.append({**raw, "compiled": [re.compile(p, re.I) for p in raw["patterns"]]})
    return rules
