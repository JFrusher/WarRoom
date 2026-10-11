"""Blue-team paths and endpoints, taken from the environment."""
from __future__ import annotations

import os
from pathlib import Path

APP_LOG = Path(os.getenv("APP_LOG", "/var/log/app.log"))

STATE_DIR = Path(os.getenv("STATE_DIR", "/var/lib/warzone"))
MITIGATIONS_FILE = STATE_DIR / "mitigations.json"
BLOCKLIST_FILE = STATE_DIR / "blocklist.json"

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://dashboard:8080")

# Seconds between polls when the log file has no new lines.
TAIL_IDLE_SLEEP = float(os.getenv("TAIL_IDLE_SLEEP", "0.5"))
