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

import agent_core
from config import rules, settings
from src import report, state, strategy, waf
from src.behaviour import BehaviourDetector
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


def handle(entry: dict, table: ThreatTable, behaviour: BehaviourDetector,
           bstate: strategy.BlueState, decide) -> None:
    ip = entry.get("ip") or "unknown"
    if ip in rules.WHITELIST:
        return

    matched = waf.matched_rules(entry)
    behavioural = behaviour.inspect(entry)
    if not matched and not behavioural:
        return

    hits = list(dict.fromkeys(
        [r["vector"] for r in matched] + [b["vector"] for b in behavioural]
    ))
    techniques = sorted(
        {r["mitre"] for r in matched} | {t for b in behavioural for t in b["techniques"]}
    )

    # Score this detection exactly once, then let the policy decide the response.
    score = table.record(ip, len(hits))
    log.info("detected %s from %s (score=%d)", ",".join(hits), ip, score)
    report.emit("detection", {"ip": ip, "vectors": hits,
                              "techniques": techniques, "score": score})

    bstate.ip, bstate.vectors, bstate.techniques, bstate.score = ip, hits, techniques, score
    agent_core.drive(lambda: strategy.observe_blue(bstate), decide,
                     lambda d: strategy.dispatch_blue(bstate, d),
                     max_steps=6, stop=frozenset({"stop", "wait"}))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    log.info("blue team online, tailing %s", settings.APP_LOG)
    table = ThreatTable()
    behaviour = BehaviourDetector()
    bstate = strategy.BlueState()
    decide = strategy.make_blue_policy()
    for line in tail(settings.APP_LOG):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            handle(entry, table, behaviour, bstate, decide)


if __name__ == "__main__":
    main()
