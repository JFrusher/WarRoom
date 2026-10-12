import json
from agent_core.decision import Decision
from agent_core.brain import LLMPolicy

ALLOWED = {"attack", "wait", "stop"}

class _Block:
    def __init__(self, text): self.type, self.text = "text", text

class _Msg:
    def __init__(self, text, stop_reason="end_turn"):
        self.content, self.stop_reason = [_Block(text)], stop_reason

class _FakeMessages:
    def __init__(self, msg): self._msg = msg
    def create(self, **kw): return self._msg

class _FakeClient:
    def __init__(self, msg): self.messages = _FakeMessages(msg)

def _fallback(obs): return Decision("stop", {}, "fallback")

def test_parses_model_decision():
    body = json.dumps({"action": "attack", "args": {"vector": "sqli"}, "rationale": "weak login"})
    p = LLMPolicy("sys", ALLOWED, _fallback, client=_FakeClient(_Msg(body)))
    assert p.decide({"state": 1}) == Decision("attack", {"vector": "sqli"}, "weak login")

def test_malformed_json_falls_back():
    p = LLMPolicy("sys", ALLOWED, _fallback, client=_FakeClient(_Msg("not json")))
    assert p.decide({}) == Decision("stop", {}, "fallback")

def test_refusal_falls_back():
    body = json.dumps({"action": "attack", "args": {}, "rationale": "x"})
    p = LLMPolicy("sys", ALLOWED, _fallback, client=_FakeClient(_Msg(body, stop_reason="refusal")))
    assert p.decide({}) == Decision("stop", {}, "fallback")

def test_unknown_action_falls_back():
    body = json.dumps({"action": "nuke", "args": {}, "rationale": "x"})
    p = LLMPolicy("sys", ALLOWED, _fallback, client=_FakeClient(_Msg(body)))
    assert p.decide({}) == Decision("stop", {}, "fallback")
