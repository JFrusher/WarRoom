"""Real-time log monitor: detect, hot-patch, and rate-limit.

Tails the target's JSON request log, scores each source IP, switches on the
matching mitigation the first time a vector is seen, and blocks an IP once it
crosses the threat threshold. Whitelisted infrastructure is never blocked so
the service SLA is preserved.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from pathlib import Path

from config import rules, settings
from src import report, state, waf
from src.scoring import ThreatTable

log = logging.getLogger("blue.monitor")


def tail(path: Path) -> Iterator[str]:
    """Yield lines from ``path`` from the start, then keep yielding new ones.

    Reading from the beginning avoids a startup race: the target's health
    check creates the log before the blue team attaches, so an attack logged
    in that window would be missed if we seeked to the end.
    """
    while not path.exists():
        log.info("waiting for %s", path)
        time.sleep(1.0)
    with path.open("r") as fh:
        while True:
            line = fh.readline()
            if not line:
                time.sleep(settings.TAIL_IDLE_SLEEP)
                continue
            yield line


def handle(entry: dict, table: ThreatTable) -> None:
    ip = entry.get("ip") or "unknown"
    if ip in rules.WHITELIST:
        return

    hits = waf.inspect(entry)
    if not hits:
        return

    score = table.record(ip, len(hits))
    log.info("detected %s from %s (score=%d)", ",".join(hits), ip, score)

    # Enforce first, report after: a slow or unresponsive dashboard must never
    # delay hot-patching or blocking.
    patched = [v for v in hits if state.enable_mitigation(v)]
    for vector in patched:
        log.info("hot-patched %s", vector)
    blocked = table.should_block(ip) and state.block_ip(ip)
    if blocked:
        log.info("rate-limiting %s", ip)

    report.emit("detection", {"ip": ip, "vectors": hits, "score": score})
    for vector in patched:
        report.emit("mitigation", {"vector": vector})
    if blocked:
        report.emit("block", {"ip": ip})


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    log.info("blue team online, tailing %s", settings.APP_LOG)
    table = ThreatTable()
    for line in tail(settings.APP_LOG):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            handle(entry, table)


if __name__ == "__main__":
    main()
