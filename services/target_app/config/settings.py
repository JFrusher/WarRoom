"""Central configuration for the target application.

Values come from the environment with lab-safe defaults so the app runs the
same way inside Compose and on a bare `flask run` during development.
"""
from __future__ import annotations

import os
from pathlib import Path

# Where the SQLite database lives. Kept on the shared state volume so a
# rotated flag survives a container restart.
DB_PATH = Path(os.getenv("DB_PATH", "/var/lib/warzone/target.db"))

# Directory holding the current flag file. Readable via the (deliberate)
# arbitrary-file-read bug, which is exactly the point.
FLAG_DIR = Path(os.getenv("FLAG_DIR", "/flags"))
FLAG_FILE = FLAG_DIR / "flag_current.txt"

# Append-only JSON-lines request log. The blue team tails this file.
APP_LOG = Path(os.getenv("APP_LOG", "/var/log/app.log"))

# Shared mutable state the blue team writes to when it hot-patches a bug or
# blocks an IP. The target re-reads these every request, so changes take
# effect with no restart.
STATE_DIR = Path(os.getenv("STATE_DIR", "/var/lib/warzone"))
MITIGATIONS_FILE = STATE_DIR / "mitigations.json"
BLOCKLIST_FILE = STATE_DIR / "blocklist.json"

# Dashboard event sink. The target posts attack/score events here.
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://dashboard:8080")

# How often the flag rotates, in seconds.
FLAG_ROTATE_SECONDS = int(os.getenv("FLAG_ROTATE_SECONDS", "180"))

LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "5000"))
