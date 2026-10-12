from agent_core.decision import Decision
from agent_core.loop import drive

def test_runs_until_stop():
    seq = [Decision("go"), Decision("go"), Decision("stop")]
    done = []
    steps = drive(lambda: {}, lambda obs: seq.pop(0), lambda d: done.append(d.action))
    assert steps == 2 and done == ["go", "go"]

def test_max_steps_caps_runaway():
    steps = drive(lambda: {}, lambda obs: Decision("go"), lambda d: None, max_steps=5)
    assert steps == 5

def test_wait_in_stop_set_ends_without_dispatch():
    dispatched = []
    steps = drive(lambda: {}, lambda obs: Decision("wait"), lambda d: dispatched.append(d),
                  stop=frozenset({"stop", "wait"}))
    assert steps == 0 and dispatched == []
