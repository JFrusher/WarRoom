"""Referee HTTP surface, SLA prober, and flag-rotation timer.

The referee is the neutral authority: it owns the flag, validates captures,
scores both sides, probes availability independently, and forwards a live
feed to the dashboard. It never serves the vulnerable app, so scoring is not
decided by the thing under attack.
"""
from __future__ import annotations

import logging
import threading
import time

import requests
from flask import Flask, jsonify, request

from config import settings
from src import report as report_mod
from src.match import Match

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("referee")

app = Flask(__name__)
match = Match()


def _forward(event: dict) -> None:
    """Relay a scored event to the dashboard for the live view."""
    try:
        requests.post(f"{settings.DASHBOARD_URL}/ingest", json=event, timeout=2.0)
    except requests.RequestException as exc:
        log.debug("dashboard forward failed: %s", exc)


@app.post("/flags/submit")
def submit_flag():
    data = request.get_json(silent=True) or {}
    verdict = match.submit_flag(str(data.get("flag", "")).strip(),
                                str(data.get("vector", "unknown")))
    if verdict["status"] == "accepted":
        _forward({"kind": "flag_captured", "team": "red",
                  "vector": verdict["vector"], "points": verdict["points"]})
    code = 200 if verdict["status"] in ("accepted", "duplicate") else 400
    return jsonify(verdict), code


@app.post("/ingest")
def ingest():
    event = request.get_json(silent=True) or {}
    enriched = match.ingest_blue(event)
    _forward(enriched)
    return jsonify(status="ok")


@app.get("/state")
def state():
    return jsonify(match.state())


@app.get("/report")
def report():
    # No probes yet -> None, so the report awards no SLA points either (matches
    # the same guard in match.state()).
    return jsonify(report_mod.build(match.uptime() if match.sla_total else None))


@app.post("/round/start")
def round_start():
    return jsonify(match.start_round())


@app.get("/healthz")
def healthz():
    return jsonify(status="ok", round=match.round_id)


def _sla_prober() -> None:
    while True:
        ok = False
        try:
            ok = requests.get(f"{settings.TARGET_URL}/healthz", timeout=2.0).status_code == 200
        except requests.RequestException:
            ok = False
        match.record_sla(ok)
        time.sleep(settings.SLA_PROBE_SECONDS)


def _rotator() -> None:
    while True:
        time.sleep(settings.FLAG_ROTATE_SECONDS)
        match.rotate_flag()


def _bootstrap() -> None:
    match.restore()  # carry cumulative scores across a referee restart
    match.start_round()
    threading.Thread(target=_sla_prober, name="sla-prober", daemon=True).start()
    threading.Thread(target=_rotator, name="flag-rotator", daemon=True).start()


_bootstrap()


if __name__ == "__main__":
    app.run(host=settings.LISTEN_HOST, port=settings.LISTEN_PORT, threaded=True)
