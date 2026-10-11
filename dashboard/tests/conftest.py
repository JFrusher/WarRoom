from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# Keep the SLA poller from interfering with assertions during tests.
os.environ.setdefault("SLA_POLL_SECONDS", "3600")
os.environ.setdefault("TARGET_URL", "http://localhost:9")
