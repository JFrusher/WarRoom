"""Shared HTTP session for the red-team modules."""
from __future__ import annotations

import re

import requests

from config import settings
from src.errors import ReconError

FLAG_RE = re.compile(r"WARZONE\{[0-9a-f]+\}")


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": settings.USER_AGENT})
    return s


def url(path: str) -> str:
    return f"{settings.TARGET_URL}{path}"


def find_flag(text: str) -> str | None:
    """Return the first flag token embedded in ``text``, if any."""
    match = FLAG_RE.search(text or "")
    return match.group(0) if match else None


def get_json(sess: requests.Session, path: str, **kwargs) -> dict:
    try:
        resp = sess.get(url(path), timeout=settings.HTTP_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise ReconError(f"GET {path} failed: {exc}") from exc
    return resp.json() if resp.content else {}
