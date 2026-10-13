"""The one thing both agents' brains share: a validated decision."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Decision:
    action: str
    args: dict = field(default_factory=dict)
    rationale: str = ""


def parse_decision(data: dict, allowed: set[str]) -> Decision:
    """Validate a raw decision dict (e.g. parsed LLM JSON). Raise ValueError
    if it is not a well-formed decision or names an action outside ``allowed``."""
    if not isinstance(data, dict):
        raise ValueError("decision is not an object")
    action = data.get("action")
    if action not in allowed:
        raise ValueError(f"unknown action {action!r}")
    args = data.get("args") or {}
    if not isinstance(args, dict):
        raise ValueError("args is not an object")
    return Decision(action=action, args=args, rationale=str(data.get("rationale", "")))
