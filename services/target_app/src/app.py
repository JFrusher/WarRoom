"""War Zone target application.

A small Flask service with three intentional, realistic OWASP bugs:

* SQL injection at ``POST /api/v1/auth/login``
* stored XSS at ``/api/v1/comments``
* command injection / arbitrary file read at ``POST /api/v1/diagnostics/ping``

Each bug has a safe code path that the blue team can switch on at runtime via
the shared mitigation file. Nothing here reaches outside the container.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from flask import Flask, Response, g, jsonify, render_template, render_template_string, request

from config import settings
from src import db, events, flags, scenario, state
from src.errors import DiagnosticsError, FlagUnavailableError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("target.app")

app = Flask(__name__, template_folder="../templates")

_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]{1,253}$")
_XSS_STEAL_MARKER = "warzone-steal"


# --------------------------------------------------------------------------- #
# Request pipeline: structured logging + blue-team rate limiting
# --------------------------------------------------------------------------- #
@app.before_request
def _enforce_blocklist():
    g.request_body = request.get_data(as_text=True)
    ip = request.remote_addr
    if ip in state.blocked_ips():
        _log_request(status=429)
        return jsonify(error="rate limited"), 429
    if ip in state.throttled_ips():
        # Blue's intermediate tier: slowed, not blocked, so the SLA holds.
        time.sleep(settings.THROTTLE_DELAY_SECONDS)
    return None


@app.after_request
def _log_after(response: Response) -> Response:
    if response.status_code != 429:  # 429s are already logged pre-dispatch
        _log_request(status=response.status_code)
    return response


def _log_request(status: int) -> None:
    """Append one JSON line describing the request for the blue team to tail."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ip": request.remote_addr,
        "method": request.method,
        "path": request.path,
        "query": request.query_string.decode("utf-8", "replace"),
        "body": getattr(g, "request_body", ""),
        "ua": request.headers.get("User-Agent", ""),
        "status": status,
    }
    try:
        settings.APP_LOG.parent.mkdir(parents=True, exist_ok=True)
        with settings.APP_LOG.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError as exc:
        log.warning("could not write request log: %s", exc)


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
@app.get("/")
def index() -> str:
    comments = db.list_comments()
    if not state.is_patched("xss"):
        # Vulnerable: bodies are marked safe and rendered verbatim.
        rendered = [{"author": c["author"], "body": c["body"]} for c in comments]
    else:
        rendered = [
            {"author": html.escape(c["author"]), "body": html.escape(c["body"])}
            for c in comments
        ]
    return render_template("index.html", comments=rendered, patched=state.mitigations())


@app.get("/healthz")
def healthz():
    events.publish("heartbeat", {"ip": request.remote_addr})
    return jsonify(status="ok", mitigations=state.mitigations())


# --------------------------------------------------------------------------- #
# A) SQL injection — authentication bypass & user extraction
# --------------------------------------------------------------------------- #
@app.post("/api/v1/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", ""))
    password = str(data.get("password", ""))

    if state.is_patched("sqli"):
        with db.connect() as conn:
            row = conn.execute(
                "SELECT id, username, role FROM users "
                "WHERE username = ? AND password = ?",
                (username, password),
            ).fetchone()
    else:
        # Intentionally vulnerable: user input concatenated straight into SQL.
        query = (
            "SELECT id, username, role FROM users "
            f"WHERE username = '{username}' AND password = '{password}'"
        )
        with db.connect() as conn:
            try:
                row = conn.execute(query).fetchone()
            except Exception as exc:  # surface SQL errors to the attacker
                return jsonify(error=f"query failed: {exc}"), 400

    if row is None:
        return jsonify(error="invalid credentials"), 401

    body = {"username": row["username"], "role": row["role"], "token": f"sess-{row['id']}"}
    if row["role"] == "admin":
        # Admin console leaks the live flag to whoever reaches it.
        try:
            body["flag"] = flags.current()
        except FlagUnavailableError:
            pass
    return jsonify(body)


# --------------------------------------------------------------------------- #
# B) Stored XSS — comments rendered without escaping
# --------------------------------------------------------------------------- #
@app.get("/api/v1/comments")
def get_comments():
    return jsonify(comments=db.list_comments())


@app.post("/api/v1/comments")
def post_comment():
    data = request.get_json(silent=True) or {}
    author = str(data.get("author", "anonymous"))
    body = str(data.get("body", ""))
    if not body:
        return jsonify(error="comment body is required"), 400

    # Always store the raw body; index() escapes at render time when the XSS
    # patch is on, which also protects comments stored before it was enabled.
    db.add_comment(author=author, body=body)
    return jsonify(status="stored"), 201


# --------------------------------------------------------------------------- #
# C) Command injection / arbitrary file read
# --------------------------------------------------------------------------- #
@app.post("/api/v1/diagnostics/ping")
def diagnostics_ping():
    data = request.get_json(silent=True) or {}
    host = str(data.get("host", "127.0.0.1"))

    try:
        output = _run_ping(host)
    except DiagnosticsError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(host=host, output=output)


def _run_ping(host: str) -> str:
    if state.is_patched("cmdi"):
        if not _HOST_RE.match(host):
            raise DiagnosticsError("invalid host")
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", "1", host],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return proc.stdout or proc.stderr
    # Intentionally vulnerable: host interpolated into a shell command.
    try:
        proc = subprocess.run(
            f"ping -c 1 -W 1 {host}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired as exc:
        raise DiagnosticsError("command timed out") from exc
    return proc.stdout or proc.stderr


# --------------------------------------------------------------------------- #
# D) Insecure direct object reference (broken object-level authorization)
# --------------------------------------------------------------------------- #
@app.get("/api/v1/users/<int:uid>/profile")
def user_profile(uid: int):
    if not scenario.enabled("idor"):
        return jsonify(error="not found"), 404
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (uid,)
        ).fetchone()
    if row is None:
        return jsonify(error="no such user"), 404
    if state.is_patched("idor") and request.headers.get("X-Session") != f"sess-{uid}":
        # Safe path: you may only read your own profile.
        return jsonify(error="forbidden"), 403

    profile = {"id": row["id"], "username": row["username"], "role": row["role"]}
    if row["role"] == "admin":
        # The admin's profile carries the flag; without the authz check any
        # caller can read it by walking ids.
        try:
            profile["flag"] = flags.current()
        except FlagUnavailableError:
            pass
    return jsonify(profile)


# --------------------------------------------------------------------------- #
# E) Server-side request forgery
# --------------------------------------------------------------------------- #
@app.post("/api/v1/fetch")
def fetch_url():
    if not scenario.enabled("ssrf"):
        return jsonify(error="not found"), 404
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", ""))

    if state.is_patched("ssrf"):
        host = (urlparse(url).hostname or "").lower()
        if host in settings.SSRF_BLOCKED_HOSTS or host.startswith(("10.", "192.168.", "172.")):
            return jsonify(error="blocked host"), 400
    try:
        resp = requests.get(url, timeout=3)
    except requests.RequestException as exc:
        return jsonify(error=str(exc)), 502
    return jsonify(url=url, status=resp.status_code, body=resp.text[:2000])


# --------------------------------------------------------------------------- #
# Honeytoken: a decoy no legitimate client should ever request
# --------------------------------------------------------------------------- #
_DECOY_FLAG = "WARZONE{decoy-do-not-submit}"


@app.get("/admin/backup.sql")
def honeytoken():
    # No real user has a reason to hit this, so any access is a high-fidelity
    # signal for the blue team. The token here is a decoy the referee rejects.
    return Response(
        f"-- database backup\nINSERT INTO flags VALUES ('{_DECOY_FLAG}');\n",
        mimetype="application/sql",
    )


def _safe_flag() -> str:
    try:
        return flags.current()
    except FlagUnavailableError:
        return ""


# --------------------------------------------------------------------------- #
# F) Server-side template injection
# --------------------------------------------------------------------------- #
@app.post("/api/v1/render")
def render_preview():
    if not scenario.enabled("ssti"):
        return jsonify(error="not found"), 404
    data = request.get_json(silent=True) or {}
    template = str(data.get("template", ""))
    if state.is_patched("ssti"):
        # Safe path: treat input as data, never evaluate it as a template.
        return jsonify(rendered=html.escape(template))
    # Intentionally vulnerable: user input rendered as a Jinja template, which
    # exposes the app config (where the flag lives) via {{ config['FLAG'] }}.
    app.config["FLAG"] = _safe_flag()
    try:
        return jsonify(rendered=render_template_string(template))
    except Exception as exc:  # surface template errors to the attacker
        return jsonify(error=str(exc)), 400


# --------------------------------------------------------------------------- #
# G) JWT "alg: none" authentication bypass
# --------------------------------------------------------------------------- #
_JWT_SECRET = b"warzone-signing-secret"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _issue_jwt(username: str) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({"username": username}).encode())
    signing_input = f"{header}.{payload}"
    sig = _b64url(hmac.new(_JWT_SECRET, signing_input.encode(), hashlib.sha256).digest())
    return f"{signing_input}.{sig}"


def _verify_jwt(token: str) -> dict | None:
    try:
        header_b64, payload_b64, sig = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    if header.get("alg") == "none":
        # Intentionally vulnerable: an unsigned token is trusted. The patch
        # rejects alg=none and requires a verified HS256 signature.
        return None if state.is_patched("jwt") else payload
    expected = _b64url(
        hmac.new(_JWT_SECRET, f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
    )
    return payload if hmac.compare_digest(expected, sig) else None


@app.post("/api/v1/token")
def issue_token():
    if not scenario.enabled("jwt"):
        return jsonify(error="not found"), 404
    data = request.get_json(silent=True) or {}
    return jsonify(token=_issue_jwt(str(data.get("username", "alice"))))


@app.post("/api/v1/account")
def account():
    if not scenario.enabled("jwt"):
        return jsonify(error="not found"), 404
    data = request.get_json(silent=True) or {}
    token = str(data.get("token", "")) or request.headers.get("Authorization", "").removeprefix("Bearer ")
    claims = _verify_jwt(token)
    if not claims:
        return jsonify(error="invalid token"), 401
    body = {"username": claims.get("username")}
    if claims.get("username") == "admin":
        body["flag"] = _safe_flag()
    return jsonify(body)


# --------------------------------------------------------------------------- #
# Simulated admin browser: the stored-XSS flag leak
# --------------------------------------------------------------------------- #
def _admin_xss_bot() -> None:
    """Periodically 'view' comments as an admin.

    If an unescaped comment carries the steal marker, the admin's browser
    would run it and exfiltrate the session. We simulate that by posting the
    live flag back as an ``admin-bot`` comment for the attacker to read.
    """
    leaked_for: str | None = None
    while True:
        time.sleep(3)
        if state.is_patched("xss"):
            continue
        try:
            live = flags.current()
        except FlagUnavailableError:
            continue
        if live == leaked_for:
            continue
        hits = [
            c for c in db.list_comments()
            if _XSS_STEAL_MARKER in c["body"].lower() and "<script" in c["body"].lower()
        ]
        if hits:
            # The admin's browser "runs" the stored payload and leaks its
            # session. Red reads this comment and submits the flag to score.
            db.add_comment("admin-bot", f"session cookie leaked: {live}")
            leaked_for = live


def _bootstrap() -> None:
    db.init_schema()
    flags.sync()
    flags.start_sync()
    threading.Thread(target=_admin_xss_bot, name="admin-xss-bot", daemon=True).start()


_bootstrap()


if __name__ == "__main__":
    app.run(host=settings.LISTEN_HOST, port=settings.LISTEN_PORT, threaded=True)
