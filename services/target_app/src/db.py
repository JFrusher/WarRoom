"""Thin SQLite helper layer.

The login path deliberately builds SQL by string concatenation; that bug
lives in :mod:`src.app`, not here. This module only owns connection handling
and schema setup so the rest of the code stays readable.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from config import settings


def connect() -> sqlite3.Connection:
    """Open a connection with row access by column name."""
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema() -> None:
    """Create tables and seed baseline data if the database is empty."""
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role     TEXT NOT NULL DEFAULT 'user'
            );

            CREATE TABLE IF NOT EXISTS comments (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                author  TEXT NOT NULL,
                body    TEXT NOT NULL,
                created TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS flags (
                id    INTEGER PRIMARY KEY CHECK (id = 1),
                token TEXT NOT NULL
            );
            """
        )
        seeded = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        if seeded == 0:
            conn.executemany(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                [
                    ("admin", "s3cr3t-admin-pass", "admin"),
                    ("alice", "password123", "user"),
                    ("bob", "hunter2", "user"),
                ],
            )
        conn.commit()


def set_flag(token: str) -> None:
    """Store the current flag token (single-row upsert)."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO flags (id, token) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET token = excluded.token",
            (token,),
        )
        conn.commit()


def get_flag() -> str | None:
    """Return the current flag token, or ``None`` if not yet set."""
    with connect() as conn:
        row = conn.execute("SELECT token FROM flags WHERE id = 1").fetchone()
        return row["token"] if row else None


def add_comment(author: str, body: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO comments (author, body) VALUES (?, ?)", (author, body)
        )
        conn.commit()


def list_comments() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT author, body, created FROM comments ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]
