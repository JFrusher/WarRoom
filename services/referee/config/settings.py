"""Referee configuration, from the environment with lab-safe defaults."""
from __future__ import annotations

import os
from pathlib import Path

# Shared state volume (also read by the target and blue team).
STATE_DIR = Path(os.getenv("STATE_DIR", "/var/lib/warzone"))

# The authoritative flag. The referee writes it here; the target mirrors it
# into its own DB and flag file to leak. Distributing it as a file keeps the
# referee the single source of truth with no runtime HTTP coupling.
FLAG_FILE = STATE_DIR / "flag.json"

# Append-only match journal: one JSON object per line.
JOURNAL = STATE_DIR / "journal.jsonl"

# Where the referee reports scores/feed for the live view.
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://dashboard:8080")

# Target health endpoint, probed independently for the SLA metric.
TARGET_URL = os.getenv("TARGET_URL", "http://target_app:5000")

FLAG_ROTATE_SECONDS = int(os.getenv("FLAG_ROTATE_SECONDS", "180"))
SLA_PROBE_SECONDS = float(os.getenv("SLA_PROBE_SECONDS", "2.0"))

SCORING_FILE = Path(
    os.getenv("SCORING_FILE", str(Path(__file__).with_name("scoring.yaml")))
)

LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "9000"))
