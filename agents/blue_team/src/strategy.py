"""Blue-team observation, scripted policy, and tool dispatch.

Per detection, the agent loops observe->decide->act until it chooses to wait.
Scripted mode reproduces the original reflex: patch each hit vector, then
throttle/block by threat score."""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field

from agent_core import Decision, LLMPolicy
from config import rules
from src import report, state

log = logging.getLogger("blue.strategy")

BLUE_ACTIONS = {"patch", "throttle", "block", "wait", "stop"}

BLUE_SYSTEM = (
    "You are the blue-team analyst defending a sealed, local security lab. Each "
    "turn you receive a JSON observation of one detection and must reply with "
    'ONLY a JSON object: {"action": <patch|throttle|block|wait|stop>, "args": {...}, '
    '"rationale": <one short line>}. patch args: {"vector": <name>}. throttle/block '
    'args: {"ip": <ip>}. Patch a hit vector you have not patched; throttle or '
    "block the source as its threat score rises; wait when you have done enough. "
    "Blocking benign traffic costs you, so weigh it."
)


@dataclass
class BlueState:
    patched: set = field(default_factory=set)
    blocked: set = field(default_factory=set)
    throttled: set = field(default_factory=set)
    # set per detection before driving the loop:
    ip: str = ""
    vectors: list = field(default_factory=list)
    techniques: list = field(default_factory=list)
    score: int = 0


def observe_blue(st: BlueState) -> dict:
    return {
        "ip": st.ip,
        "vectors": st.vectors,
        "score": st.score,
        "patched": sorted(st.patched),
        "blocked": st.ip in st.blocked,
        "throttled": st.ip in st.throttled,
    }


def scripted_blue(obs: dict) -> Decision:
    unpatched = [v for v in obs["vectors"] if v not in obs["patched"]]
    if unpatched:
        return Decision("patch", {"vector": unpatched[0]}, f"patch {unpatched[0]}")
    if obs["score"] >= rules.BLOCK_THRESHOLD and not obs["blocked"]:
        return Decision("block", {"ip": obs["ip"]}, "over block threshold")
    if obs["score"] >= rules.THROTTLE_THRESHOLD and not obs["throttled"]:
        return Decision("throttle", {"ip": obs["ip"]}, "over throttle threshold")
    return Decision("wait", {}, "observing")


def dispatch_blue(st: BlueState, decision: Decision) -> None:
    a = decision.action
    if a == "patch":
        vector = decision.args.get("vector")
        if not vector:
            return
        if state.enable_mitigation(vector):
            report.emit("mitigation", {"vector": vector})
        st.patched.add(vector)
        report.emit("thought", {"rationale": decision.rationale, "action": "patch", "vector": vector})
    elif a == "block":
        ip = decision.args.get("ip")
        if ip and state.block_ip(ip):
            report.emit("block", {"ip": ip})
        if ip:
            st.blocked.add(ip)
        report.emit("thought", {"rationale": decision.rationale, "action": "block", "ip": ip})
    elif a == "throttle":
        ip = decision.args.get("ip")
        if ip and state.throttle_ip(ip):
            report.emit("throttle", {"ip": ip})
        if ip:
            st.throttled.add(ip)
        report.emit("thought", {"rationale": decision.rationale, "action": "throttle", "ip": ip})


def make_blue_policy():
    if os.getenv("BRAIN", "scripted") == "llm":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit("BRAIN=llm requires ANTHROPIC_API_KEY")
        return LLMPolicy(BLUE_SYSTEM, BLUE_ACTIONS, scripted_blue).decide
    return scripted_blue
