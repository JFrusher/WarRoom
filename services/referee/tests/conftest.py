from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="warzone-ref-"))
os.environ.setdefault("DASHBOARD_URL", "http://localhost:9")
os.environ.setdefault("TARGET_URL", "http://localhost:9")
os.environ.setdefault("FLAG_ROTATE_SECONDS", "3600")
