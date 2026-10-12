from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="warzone-blue-"))

# repo root, so `import agent_core` works in tests
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
