#!/usr/bin/env python
"""Initialise the target database and mint the first flag.

Useful for local runs outside Docker. The app also does this on startup, so
running it is optional, but it makes the SQLite file inspectable up front.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import db, flags  # noqa: E402


def main() -> None:
    db.init_schema()
    token = flags.rotate()
    print(f"database ready at {db.settings.DB_PATH}")
    print(f"minted flag: {token}")


if __name__ == "__main__":
    main()
