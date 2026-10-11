"""War Zone target application.

A small Flask service with three intentional, realistic OWASP bugs:

* SQL injection at ``POST /api/v1/auth/login``
* stored XSS at ``/api/v1/comments``
* command injection / arbitrary file read at ``POST /api/v1/diagnostics/ping``

Each bug has a safe code path that the blue team can switch on at runtime via
the shared mitigation file. Nothing here reaches outside the container.
"""
from __future__ import annotations

import html
import json
import logging
import re
import subprocess
import threading
import time
from datetime import datetime, timezone

from flask import Flask, Response, g, jsonify, render_template, request

from config import settings
from src import db, events, flags, state
from src.errors import DiagnosticsError, FlagUnavailableError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("target.app")

app = Flask(__name__, template_folder="../templates")

# Vectors already credited to the red team for the live flag. Reset on every
# rotation so each flag is worth one capture per attack class.
_awarded: set[str] = set()
_awarded_lock = threading.Lock()
_awarded_flag: str | None = None

_HOST_RE = re.compile(r"^[A-Za-z0-9.\-]{1,253}$")
_XSS_STEAL_MARKER = "warzone-steal"


# --------------------------------------------------------------------------- #
# Request pipeline: structured logging + blue-team rate limiting
# --------------------------------------------------------------------------- #
@app.before_request
def _enforce_blocklist():
    g.request_body = request.get_data(as_text=True)
    if request.remote_addr in state.blocked_ips():
        _log_request(status=429)
        return jsonify(error="rate limited"), 429
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

    stored = body if not state.is_patched("xss") else html.escape(body)
    db.add_comment(author=author, body=stored)
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
# Flag submission & red-team scoring
# --------------------------------------------------------------------------- #
@app.post("/api/v1/flags/submit")
def submit_flag():
    data = request.get_json(silent=True) or {}
    token = str(data.get("flag", "")).strip()
    vector = str(data.get("vector", "unknown"))

    try:
        live = flags.current()
    except FlagUnavailableError:
        return jsonify(error="no active flag"), 503

    if token != live:
        return jsonify(status="rejected", reason="stale or incorrect flag"), 400

    with _awarded_lock:
        _sync_awarded(live)
        if vector in _awarded:
            return jsonify(status="duplicate", vector=vector), 200
        _awarded.add(vector)

    events.publish("flag_captured", {"team": "red", "vector": vector, "points": 100})
    return jsonify(status="accepted", vector=vector, points=100), 200


def _sync_awarded(live: str) -> None:
    """Clear the credited-vector set when the flag has rotated."""
    global _awarded_flag
    if _awarded_flag != live:
        _awarded.clear()
        _awarded_flag = live


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
    flags.rotate()
    flags.start_rotation()
    threading.Thread(target=_admin_xss_bot, name="admin-xss-bot", daemon=True).start()


_bootstrap()


if __name__ == "__main__":
    app.run(host=settings.LISTEN_HOST, port=settings.LISTEN_PORT, threaded=True)
