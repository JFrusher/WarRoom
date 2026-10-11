"""Checks for event ingest, scoring, and the state snapshot."""
from __future__ import annotations

import pytest

from src import app as app_module


@pytest.fixture()
def client():
    app_module.app.testing = True
    with app_module._lock:
        app_module._state["scores"] = {"red": 0, "blue": 0}
        app_module._state["events"].clear()
    return app_module.app.test_client()


def test_ingest_awards_points_to_team(client):
    client.post("/ingest", json={"kind": "flag_captured", "team": "red", "points": 100})
    client.post("/ingest", json={"kind": "detection", "team": "blue", "points": 20})
    snap = client.get("/state").get_json()
    assert snap["scores"] == {"red": 100, "blue": 20}


def test_heartbeat_is_not_feed_noise(client):
    client.post("/ingest", json={"kind": "heartbeat", "ip": "172.0.0.1"})
    snap = client.get("/state").get_json()
    assert snap["events"] == []


def test_event_without_points_still_feeds(client):
    client.post("/ingest", json={"kind": "exploit_attempt", "team": "red", "vector": "sqli"})
    snap = client.get("/state").get_json()
    assert snap["scores"]["red"] == 0
    assert snap["events"][-1]["kind"] == "exploit_attempt"
