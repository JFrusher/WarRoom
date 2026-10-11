"""Test fixtures: point the app at throwaway temp storage before import."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="warzone-test-"))
os.environ.update(
    DB_PATH=str(_TMP / "target.db"),
    FLAG_DIR=str(_TMP / "flags"),
    APP_LOG=str(_TMP / "app.log"),
    STATE_DIR=str(_TMP / "state"),
    FLAG_ROTATE_SECONDS="3600",
    DASHBOARD_URL="http://localhost:9",  # unreachable: publishes no-op in tests
)

import json  # noqa: E402

import pytest  # noqa: E402

from config import settings  # noqa: E402
from src import app as app_module  # noqa: E402


@pytest.fixture()
def client():
    settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
    app_module.app.testing = True
    return app_module.app.test_client()


@pytest.fixture()
def set_mitigation():
    def _apply(**flags_on: bool):
        settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
        settings.MITIGATIONS_FILE.write_text(json.dumps(flags_on))

    yield _apply
    if settings.MITIGATIONS_FILE.exists():
        settings.MITIGATIONS_FILE.unlink()
