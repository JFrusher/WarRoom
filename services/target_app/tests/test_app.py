"""End-to-end checks for the three intentional bugs and their patches."""
from __future__ import annotations

from config import settings
from src import flags


def test_sqli_auth_bypass_leaks_admin_flag(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin'--", "password": "anything"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["role"] == "admin"
    assert data["flag"] == flags.current()


def test_sqli_patch_blocks_bypass(client, set_mitigation):
    set_mitigation(sqli=True)
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin'--", "password": "anything"},
    )
    assert resp.status_code == 401


def test_valid_login_has_no_flag(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "password123"},
    )
    assert resp.status_code == 200
    assert "flag" not in resp.get_json()


def test_stored_xss_persists_raw_payload(client):
    payload = "<script>alert(1)</script>"
    client.post("/api/v1/comments", json={"author": "mallory", "body": payload})
    page = client.get("/").get_data(as_text=True)
    assert payload in page  # rendered verbatim -> stored XSS


def test_xss_patch_escapes_payload(client, set_mitigation):
    set_mitigation(xss=True)
    payload = "<script>alert(2)</script>"
    client.post("/api/v1/comments", json={"author": "mallory", "body": payload})
    page = client.get("/").get_data(as_text=True)
    assert payload not in page
    assert "&lt;script&gt;" in page


def test_command_injection_executes_injected_command(client):
    resp = client.post(
        "/api/v1/diagnostics/ping",
        json={"host": "127.0.0.1; echo warzone-injected"},
    )
    assert "warzone-injected" in resp.get_json()["output"]


def test_arbitrary_file_read_leaks_flag_file(client):
    flag = flags.current()
    resp = client.post(
        "/api/v1/diagnostics/ping",
        json={"host": f"127.0.0.1; cat {settings.FLAG_FILE}"},
    )
    assert flag in resp.get_json()["output"]


def test_cmdi_patch_rejects_metacharacters(client, set_mitigation):
    set_mitigation(cmdi=True)
    resp = client.post(
        "/api/v1/diagnostics/ping",
        json={"host": "127.0.0.1; cat /etc/passwd"},
    )
    assert resp.status_code == 400


def test_flag_submission_scores_once_per_vector(client):
    flag = flags.current()
    first = client.post("/api/v1/flags/submit", json={"flag": flag, "vector": "sqli"})
    assert first.get_json()["status"] == "accepted"
    dup = client.post("/api/v1/flags/submit", json={"flag": flag, "vector": "sqli"})
    assert dup.get_json()["status"] == "duplicate"


def test_flag_submission_rejects_wrong_flag(client):
    resp = client.post(
        "/api/v1/flags/submit", json={"flag": "WARZONE{nope}", "vector": "sqli"}
    )
    assert resp.status_code == 400


def test_flag_submission_rejects_unknown_vector(client):
    flag = flags.current()
    resp = client.post(
        "/api/v1/flags/submit", json={"flag": flag, "vector": "made-up"}
    )
    assert resp.status_code == 400
    assert resp.get_json()["reason"] == "unknown vector"
