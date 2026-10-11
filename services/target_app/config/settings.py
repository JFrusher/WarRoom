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
THROTTLE_FILE = STATE_DIR / "throttle.json"

# Added latency for a throttled IP (blue's intermediate response tier).
THROTTLE_DELAY_SECONDS = float(os.getenv("THROTTLE_DELAY_SECONDS", "0.3"))

# The referee owns the flag and publishes it here; the target mirrors it into
# its DB and flag file so the vulnerabilities leak the live value.
SHARED_FLAG_FILE = STATE_DIR / "flag.json"
FLAG_SYNC_SECONDS = float(os.getenv("FLAG_SYNC_SECONDS", "2.0"))

# Dashboard event sink. The target posts attack/score events here.
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://dashboard:8080")

LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "5000"))

# Which scenario (set of enabled vulnerabilities) this instance runs.
SCENARIO = os.getenv("SCENARIO", "default")
SCENARIO_FILE = Path(
    os.getenv("SCENARIO_FILE",
              str(Path(__file__).resolve().parents[1] / "scenarios" / f"{SCENARIO}.yaml"))
)

# Hosts the SSRF-patched fetch endpoint refuses (internal / link-local).
SSRF_BLOCKED_HOSTS = ("metadata", "localhost", "127.0.0.1", "169.254.169.254", "0.0.0.0")
