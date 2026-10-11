"""Internal metadata service — the SSRF prize.

Stands in for a cloud instance-metadata endpoint (169.254.169.254). It is only
reachable on the lab's internal network, never published to the host, so the
only way to read it is to make the target fetch it on your behalf (SSRF).
It serves the live flag, which the referee publishes to the shared volume.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify

FLAG_FILE = Path(os.getenv("STATE_DIR", "/var/lib/warzone")) / "flag.json"

app = Flask(__name__)


def _flag() -> str:
    try:
        return json.loads(FLAG_FILE.read_text())["token"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return "unavailable"


@app.get("/")
@app.get("/latest/meta-data/")
def root():
    return jsonify(service="metadata", note="internal only", flag=_flag())


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
