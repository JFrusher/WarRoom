import pytest
from agent_core.decision import Decision, parse_decision

ALLOWED = {"attack", "wait", "stop"}

def test_parses_valid_decision():
    d = parse_decision({"action": "attack", "args": {"vector": "sqli"}, "rationale": "why"}, ALLOWED)
    assert d == Decision("attack", {"vector": "sqli"}, "why")

def test_missing_args_defaults_to_empty():
    d = parse_decision({"action": "stop"}, ALLOWED)
    assert d.args == {} and d.rationale == ""

def test_unknown_action_raises():
    with pytest.raises(ValueError):
        parse_decision({"action": "nuke"}, ALLOWED)

def test_non_dict_raises():
    with pytest.raises(ValueError):
        parse_decision(["not", "a", "dict"], ALLOWED)

def test_non_dict_args_raises():
    with pytest.raises(ValueError):
        parse_decision({"action": "attack", "args": "sqli"}, ALLOWED)
