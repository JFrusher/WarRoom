"""Red-team observation, scripted policy, and tool dispatch.

The brain chooses one action per move; this module executes it against the
lab-locked target. Scripted mode reproduces the original kill-chain order."""
from __future__ import annotations
import logging
import os
import time
from dataclasses import dataclass, field

from agent_core import Decision, LLMPolicy
from src import campaign, profiles, report, submit
from src.errors import ExploitFailed
from src.exploits import cmdi, idor, jwt, sqli, ssrf, ssti, xss
from src.recon import Recon

log = logging.getLogger("red.strategy")

_EXPLOITS = {m.VECTOR: m for m in (sqli, xss, cmdi, idor, ssrf, ssti, jwt)}
RED_CHAIN = [vector for vector, _ in campaign.CHAIN]
RED_ACTIONS = {"attack", "wait", "stop"}

RED_SYSTEM = (
    "You are the red-team operator in a sealed, local security lab. Each turn "
    "you receive a JSON observation and must reply with ONLY a JSON object: "
    '{"action": <one of attack|wait|stop>, "args": {...}, "rationale": <one short line>}. '
    'attack args: {"vector": one of ' + "|".join(sorted(_EXPLOITS)) + ', "obfuscate": true|false}. '
    'wait args: {"seconds": number}. Pick the next move to capture flags you '
    "have not captured yet; obfuscate to evade the defender's WAF; stop when "
    "there is nothing useful left. You may only act against this lab."
)


@dataclass
class RedState:
    sess: object
    recon: Recon
    attempted: set = field(default_factory=set)
    captured: set = field(default_factory=set)
    last_vector: str | None = None
    last_verdict: str | None = None


def observe_red(state: RedState) -> dict:
    return {
        "attempted": sorted(state.attempted),
        "captured": sorted(state.captured),
        "last_vector": state.last_vector,
        "last_verdict": state.last_verdict,
        "mitigations": state.recon.mitigations,
        "forms": state.recon.forms,
    }


def scripted_red(obs: dict) -> Decision:
    for vector in RED_CHAIN:
        if vector not in obs["attempted"]:
            return Decision("attack", {"vector": vector, "obfuscate": False},
                            f"next in chain: {vector}")
    return Decision("stop", {}, "all vectors attempted")


def dispatch_red(state: RedState, decision: Decision) -> None:
    if decision.action == "wait":
        time.sleep(float(decision.args.get("seconds", 1.0)))
        return
    if decision.action != "attack":
        return
    vector = decision.args.get("vector")
    if vector not in _EXPLOITS:
        log.warning("ignoring unknown vector %r", vector)
        return
    state.attempted.add(vector)
    state.last_vector = vector
    profiles.use("stealth" if decision.args.get("obfuscate") else "loud")
    report.emit("thought", {"rationale": decision.rationale, "action": "attack", "vector": vector})
    report.emit("exploit_attempt", {"vector": vector})
    try:
        flag = _EXPLOITS[vector].capture(state.sess)
    except ExploitFailed as exc:
        log.warning("[%s] %s", vector, exc)
        state.last_verdict = "failed"
        report.emit("exploit_failed", {"vector": vector})
        return
    verdict = submit.submit(state.sess, flag, vector)
    state.last_verdict = verdict["status"]
    if verdict["status"] == "accepted":
        state.captured.add(vector)
    report.emit("exploit_success", {"vector": vector, "flag": flag})


def make_red_policy(sess):
    if os.getenv("BRAIN", "scripted") == "llm":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit("BRAIN=llm requires ANTHROPIC_API_KEY")
        return LLMPolicy(RED_SYSTEM, RED_ACTIONS, scripted_red).decide
    return scripted_red
