"""LLM policy: ask Claude for one structured decision; fall back to a scripted
policy on any failure so a demo never hard-stops. The model only *chooses*;
the agent's own code executes the chosen action."""
from __future__ import annotations
import json
import logging
from typing import Callable
from agent_core.decision import Decision, parse_decision

log = logging.getLogger("agent_core.brain")


class LLMPolicy:
    def __init__(self, system, allowed_actions, fallback: Callable[[dict], Decision],
                 *, model="claude-sonnet-5-5", client=None, max_tokens=2048):
        self.system = system
        self.allowed = set(allowed_actions)
        self.fallback = fallback
        self.model = model
        self.max_tokens = max_tokens
        if client is None:
            import anthropic  # imported lazily so scripted mode needs no SDK/key
            client = anthropic.Anthropic()
        self.client = client
        self.history: list[dict] = []

    def decide(self, obs: dict) -> Decision:
        self.history.append({"role": "user", "content": json.dumps(obs)})
        try:
            msg = self.client.messages.create(
                model=self.model, max_tokens=self.max_tokens,
                system=self.system, messages=self.history,
            )
            if getattr(msg, "stop_reason", None) == "refusal":
                raise ValueError("model refused")
            text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
            decision = parse_decision(json.loads(text), self.allowed)
            self.history.append({"role": "assistant", "content": text})
            return decision
        except Exception as exc:  # parse, validation, refusal, or API error
            log.warning("LLM decision failed (%s); using scripted fallback", exc)
            self.history.pop()  # drop the unanswered user turn; keep history clean
            return self.fallback(obs)
