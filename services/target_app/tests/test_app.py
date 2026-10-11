"""End-to-end checks for the three intentional bugs and their patches."""
from __future__ import annotations

from config import settings
from src import app as app_module
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


def test_idor_leaks_admin_profile_flag(client):
    resp = client.get("/api/v1/users/1/profile")
    assert resp.status_code == 200
    assert resp.get_json()["flag"] == flags.current()


def test_idor_patch_requires_matching_session(client, set_mitigation):
    set_mitigation(idor=True)
    assert client.get("/api/v1/users/1/profile").status_code == 403


class _StubResponse:
    status_code = 200

    def __init__(self, text: str) -> None:
        self.text = text


def test_ssrf_fetches_internal_metadata(client, monkeypatch):
    flag = flags.current()
    monkeypatch.setattr(
        app_module.requests, "get",
        lambda url, timeout=0: _StubResponse(f'{{"flag": "{flag}"}}'),
    )
    resp = client.post("/api/v1/fetch", json={"url": "http://metadata/"})
    assert flag in resp.get_json()["body"]


def test_ssrf_patch_blocks_internal_host(client, set_mitigation):
    set_mitigation(ssrf=True)
    resp = client.post("/api/v1/fetch", json={"url": "http://metadata/"})
    assert resp.status_code == 400


def test_target_mirrors_the_referee_flag(client):
    # The target leaks whatever the referee published; it no longer scores.
    assert flags.current() == "WARZONE{deadbeefdeadbeefdeadbeef}"
    assert client.post("/api/v1/flags/submit", json={}).status_code == 404
