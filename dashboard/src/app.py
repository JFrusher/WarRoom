"""Real-time orchestrator and dashboard.

Collects events from the target and both agents on ``/ingest``, keeps a small
in-memory scoreboard, polls the target for SLA uptime, and streams everything
to connected browsers over Socket.IO.
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from threading import Lock

import requests
from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("dashboard")

TARGET_URL = os.getenv("TARGET_URL", "http://target_app:5000")
SLA_POLL_SECONDS = float(os.getenv("SLA_POLL_SECONDS", "2.0"))

app = Flask(__name__, template_folder="../templates", static_folder="../static")
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

_lock = Lock()
_state = {
    "scores": {"red": 0, "blue": 0},
    "sla": {"ok": 0, "total": 0},
    "mitigations": {"sqli": False, "xss": False, "cmdi": False},
    "events": deque(maxlen=100),
}


def _snapshot() -> dict:
    sla = _state["sla"]
    uptime = round(100 * sla["ok"] / sla["total"], 2) if sla["total"] else 100.0
    return {
        "scores": dict(_state["scores"]),
        "mitigations": dict(_state["mitigations"]),
        "uptime": uptime,
        "events": list(_state["events"]),
    }


@app.get("/")
def index() -> str:
    return render_template("dashboard.html")


@app.get("/state")
def state():
    with _lock:
        return jsonify(_snapshot())


@app.post("/ingest")
def ingest():
    event = request.get_json(silent=True) or {}
    event["ts"] = datetime.now(timezone.utc).isoformat()

    with _lock:
        team = event.get("team")
        points = event.get("points")
        if team in ("red", "blue") and isinstance(points, (int, float)):
            _state["scores"][team] += int(points)
        if event.get("kind") != "heartbeat":
            _state["events"].append(event)
        snapshot = _snapshot()

    if event.get("kind") != "heartbeat":
        socketio.emit("event", event)
    socketio.emit("scores", snapshot["scores"])
    return jsonify(status="ok")


def _poll_sla() -> None:
    """Poll the target health endpoint and broadcast uptime + patch state."""
    while True:
        ok = False
        mitigations = None
        try:
            resp = requests.get(f"{TARGET_URL}/healthz", timeout=2.0)
            ok = resp.status_code == 200
            mitigations = resp.json().get("mitigations")
        except requests.RequestException:
            ok = False

        with _lock:
            _state["sla"]["total"] += 1
            if ok:
                _state["sla"]["ok"] += 1
            if mitigations:
                _state["mitigations"] = mitigations
            snapshot = _snapshot()

        socketio.emit("sla", {"uptime": snapshot["uptime"]})
        socketio.emit("mitigations", snapshot["mitigations"])
        time.sleep(SLA_POLL_SECONDS)


@socketio.on("connect")
def _on_connect() -> None:
    with _lock:
        socketio.emit("snapshot", _snapshot())


socketio.start_background_task(_poll_sla)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8080, allow_unsafe_werkzeug=True)
