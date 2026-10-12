# Hybrid Agent Brains Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the red and blue agents' fixed loops with a shared policy-driven loop whose brain is either a deterministic script (CI) or an LLM (demo), and surface each decision's reasoning on the dashboard.

**Architecture:** A repo-root `agent_core` package holds the only genuinely shared code — a `Decision` type, a `parse_decision` validator, a `drive()` observe→decide→dispatch loop, and an `LLMPolicy` that asks Claude for one structured decision per move and falls back to a scripted policy on any failure. Each agent keeps its own observation builder, scripted policy, and tool dispatch (a `strategy.py`), because those differ per side. The LLM only ever *chooses* an action from a fixed set; the agent's own code *executes* it, so the lab stays locked by construction.

**Tech Stack:** Python 3.12, `anthropic` SDK (model `claude-sonnet-5-5`), existing Flask/requests/Socket.IO stack. Docker Compose with per-agent build contexts moved to repo root so both images can copy `agent_core`.

**Spec:** `docs/superpowers/specs/2026-10-12-hybrid-agent-brains-design.md`

## Global Constraints

- Python 3.12 (matches existing `python:3.12-slim` images). No new runtime deps except `anthropic` in the two agent images.
- Model string is exactly `claude-sonnet-5-5` (never a date-suffixed variant). Model is a config value, swappable per side.
- The LLM returns a decision; the agent's own deterministic code executes it. The model never makes a network call and never emits a target/URL/payload — only an `action` name plus bounded `args`.
- Existing lab-lock is unchanged: `config.settings` still resolves the target/referee from the fixed allow-list.
- `agent_core` must be importable both in Docker (copied into each image) and in the test runner (repo root on `sys.path`).
- Both agents default to the scripted brain (`BRAIN` env unset or `scripted`), so CI and `tests/e2e_smoke.py` run with no API key.

## Review Focus

- **Malformed / non-JSON model output** → `json.loads` raises → fall back to scripted for that move, don't crash. (Task 3)
- **`stop_reason == "refusal"`** → treat as failure and fall back without reading `content`. (Task 3)
- **Decision names an unknown action or vector** → dispatch rejects it (logs + no-op/fallback), never a `KeyError`. (parse: Task 1; red dispatch: Task 4; blue dispatch: Task 5)
- **`BRAIN=llm` with no `ANTHROPIC_API_KEY`** → fail fast at startup with a clear message, not mid-match. (Task 4 red, Task 5 blue)
- **LLM never emits `stop` / blue never settles** → `drive(max_steps=...)` caps the loop so a round always ends. (Task 2)

---

### Task 1: `agent_core` decision type + validator

**Files:**
- Create: `agent_core/__init__.py`
- Create: `agent_core/decision.py`
- Create: `agent_core/tests/__init__.py`
- Create: `agent_core/tests/conftest.py`
- Test: `agent_core/tests/test_decision.py`

**Interfaces:**
- Produces: `Decision(action: str, args: dict, rationale: str)`; `parse_decision(data: dict, allowed: set[str]) -> Decision` (raises `ValueError` on bad shape or action not in `allowed`).

- [ ] **Step 1: conftest puts repo root on path**

`agent_core/tests/conftest.py`:
```python
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
```

- [ ] **Step 2: Write the failing test**

`agent_core/tests/test_decision.py`:
```python
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
```

- [ ] **Step 3: Run it, verify it fails**

Run: `cd agent_core && python -m pytest tests/test_decision.py -q`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement**

`agent_core/decision.py`:
```python
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
```

`agent_core/__init__.py`:
```python
from agent_core.decision import Decision, parse_decision
from agent_core.loop import drive
from agent_core.brain import LLMPolicy

__all__ = ["Decision", "parse_decision", "drive", "LLMPolicy"]
```
Note: `loop` and `brain` are created in Tasks 2 and 3; until then, comment out those two imports from `__all__`/`__init__` or implement Tasks 1–3 before running the package import. (Subagent workers: add each import as its module lands.)

- [ ] **Step 5: Run, verify pass**

Run: `cd agent_core && python -m pytest tests/test_decision.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent_core/__init__.py agent_core/decision.py agent_core/tests/
git commit -m "feat(agent_core): decision type and validator"
```

---

### Task 2: `agent_core` drive loop

**Files:**
- Create: `agent_core/loop.py`
- Test: `agent_core/tests/test_loop.py`

**Interfaces:**
- Consumes: `Decision` (Task 1).
- Produces: `drive(observe, decide, dispatch, *, max_steps=20, stop=frozenset({"stop"})) -> int` — runs observe→decide→dispatch until `decision.action in stop` or `max_steps` reached; returns the number of dispatched (acting) steps. A `stop`/`wait` action is never dispatched.

- [ ] **Step 1: Write the failing test**

`agent_core/tests/test_loop.py`:
```python
from agent_core.decision import Decision
from agent_core.loop import drive

def test_runs_until_stop():
    seq = [Decision("go"), Decision("go"), Decision("stop")]
    done = []
    steps = drive(lambda: {}, lambda obs: seq.pop(0), lambda d: done.append(d.action))
    assert steps == 2 and done == ["go", "go"]

def test_max_steps_caps_runaway():
    steps = drive(lambda: {}, lambda obs: Decision("go"), lambda d: None, max_steps=5)
    assert steps == 5  # never emits stop; cap ends it

def test_wait_in_stop_set_ends_without_dispatch():
    dispatched = []
    steps = drive(lambda: {}, lambda obs: Decision("wait"), lambda d: dispatched.append(d),
                  stop=frozenset({"stop", "wait"}))
    assert steps == 0 and dispatched == []
```

- [ ] **Step 2: Run, verify fail**

Run: `cd agent_core && python -m pytest tests/test_loop.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

`agent_core/loop.py`:
```python
"""The shared observe -> decide -> act loop both agents run."""
from __future__ import annotations
from typing import Callable
from agent_core.decision import Decision


def drive(
    observe: Callable[[], dict],
    decide: Callable[[dict], Decision],
    dispatch: Callable[[Decision], None],
    *,
    max_steps: int = 20,
    stop: frozenset[str] = frozenset({"stop"}),
) -> int:
    """Run the agent loop until a stop action or ``max_steps``. Returns the
    number of actions dispatched. ``max_steps`` is the guard that guarantees a
    round ends even if the brain never says stop."""
    steps = 0
    for _ in range(max_steps):
        decision = decide(observe())
        if decision.action in stop:
            break
        dispatch(decision)
        steps += 1
    return steps
```

- [ ] **Step 4: Run, verify pass**

Run: `cd agent_core && python -m pytest tests/test_loop.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent_core/loop.py agent_core/tests/test_loop.py
git commit -m "feat(agent_core): drive loop with max-steps guard"
```

---

### Task 3: `agent_core` LLM policy with scripted fallback

**Files:**
- Create: `agent_core/brain.py`
- Test: `agent_core/tests/test_brain.py`

**Interfaces:**
- Consumes: `Decision`, `parse_decision` (Task 1).
- Produces: `LLMPolicy(system: str, allowed_actions, fallback: Callable[[dict], Decision], *, model="claude-sonnet-5-5", client=None, max_tokens=2048)` with method `decide(obs: dict) -> Decision`. On refusal, parse failure, validation failure, or API error, logs a warning and returns `fallback(obs)`. Keeps an append-only `history` of user/assistant turns across the match.

- [ ] **Step 1: Write the failing test** (fake client — no network, no key)

`agent_core/tests/test_brain.py`:
```python
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
```

- [ ] **Step 2: Run, verify fail**

Run: `cd agent_core && python -m pytest tests/test_brain.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

`agent_core/brain.py`:
```python
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
```
Note on model behaviour: `claude-sonnet-5-5` runs adaptive thinking when `thinking` is omitted (fine — the text block carries the JSON; the extractor already skips thinking blocks). We ask for JSON via the system prompt rather than the structured-output wrapper; `parse_decision` + the fallback give the same safety with no dependence on the exact `output_config.format` shape.

- [ ] **Step 4: Run, verify pass**

Run: `cd agent_core && python -m pytest tests/test_brain.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Wire `__init__.py` imports**

Ensure `agent_core/__init__.py` now imports `drive` and `LLMPolicy` (from Tasks 2–3). Run `cd agent_core && python -c "import agent_core"` — expect no error.

- [ ] **Step 6: Commit**

```bash
git add agent_core/brain.py agent_core/tests/test_brain.py agent_core/__init__.py
git commit -m "feat(agent_core): LLM policy with scripted fallback"
```

---

### Task 4: Red agent — strategy + `agent` subcommand

**Files:**
- Create: `agents/red_team/src/strategy.py`
- Modify: `agents/red_team/src/cli.py` (add `agent` subcommand + dispatch)
- Modify: `agents/red_team/tests/conftest.py` (add repo root to path)
- Test: `agents/red_team/tests/test_red.py` (append cases)

**Interfaces:**
- Consumes: `agent_core.drive`, `agent_core.LLMPolicy`, `agent_core.Decision`; existing `recon.run`, `_EXPLOITS` map, `submit.submit`, `report.emit`, `profiles.use`.
- Produces: `RedState`; `observe_red(state) -> dict`; `scripted_red(obs) -> Decision`; `dispatch_red(state, decision) -> None`; `make_red_policy(sess) -> Callable[[dict], Decision]`. Red actions: `{"attack", "wait", "stop"}` (args: `attack` → `{vector, obfuscate}`, `wait` → `{seconds}`).

- [ ] **Step 1: conftest adds repo root**

Append to `agents/red_team/tests/conftest.py`:
```python
# repo root, so `import agent_core` works in tests
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
```

- [ ] **Step 2: Write failing tests**

Append to `agents/red_team/tests/test_red.py`:
```python
from src import strategy
from src.recon import Recon
from agent_core.decision import Decision

def _state():
    return strategy.RedState(sess=None, recon=Recon(forms=[], mitigations={}, reachable=True))

def test_scripted_red_picks_next_unattempted_in_chain_order():
    obs = {"attempted": [], "captured": [], "mitigations": {}, "forms": [],
           "last_vector": None, "last_verdict": None}
    d = strategy.scripted_red(obs)
    assert d.action == "attack" and d.args["vector"] == strategy.RED_CHAIN[0]

def test_scripted_red_stops_when_all_attempted():
    obs = {"attempted": list(strategy.RED_CHAIN), "captured": [], "mitigations": {},
           "forms": [], "last_vector": None, "last_verdict": None}
    assert strategy.scripted_red(obs).action == "stop"

def test_dispatch_unknown_vector_is_noop(monkeypatch):
    st = _state()
    strategy.dispatch_red(st, Decision("attack", {"vector": "bogus"}, "x"))
    assert st.attempted == set()  # rejected, no crash
```

- [ ] **Step 3: Run, verify fail**

Run: `cd agents/red_team && python -m pytest tests/test_red.py -q`
Expected: FAIL (no `strategy`).

- [ ] **Step 4: Implement `strategy.py`**

`agents/red_team/src/strategy.py`:
```python
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
    "attack args: {\"vector\": one of " + "|".join(sorted(_EXPLOITS)) + ", \"obfuscate\": true|false}. "
    "wait args: {\"seconds\": number}. Pick the next move to capture flags you "
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
```

- [ ] **Step 5: Wire the `agent` subcommand in `cli.py`**

In `agents/red_team/src/cli.py`, add imports `from src import strategy` and `import agent_core`, add a subparser, and a handler:
```python
def cmd_agent(sess) -> int:
    state = strategy.RedState(sess=sess, recon=recon.run(sess))
    decide = strategy.make_red_policy(sess)
    agent_core.drive(lambda: strategy.observe_red(state), decide,
                     lambda d: strategy.dispatch_red(state, d), max_steps=12)
    print(f"captured {sorted(state.captured)}")
    return 0 if state.captured else 2
```
Register `sub.add_parser("agent", help="run the policy-driven brain (BRAIN=scripted|llm)")` and route `if args.command == "agent": return cmd_agent(sess)` in `main`.

- [ ] **Step 6: Run tests, verify pass**

Run: `cd agents/red_team && python -m pytest tests/ -q`
Expected: PASS (new + existing).

- [ ] **Step 7: Commit**

```bash
git add agents/red_team/src/strategy.py agents/red_team/src/cli.py agents/red_team/tests/
git commit -m "feat(red): policy-driven agent brain"
```

---

### Task 5: Blue agent — strategy + policy-driven `handle`

**Files:**
- Create: `agents/blue_team/src/strategy.py`
- Modify: `agents/blue_team/src/monitor.py` (`handle` delegates to the loop)
- Modify: `agents/blue_team/tests/conftest.py` (add repo root to path)
- Test: `agents/blue_team/tests/test_blue.py` (append cases)

**Interfaces:**
- Consumes: `agent_core.drive`, `agent_core.LLMPolicy`, `agent_core.Decision`; `config.rules` (`THROTTLE_THRESHOLD=15`, `BLOCK_THRESHOLD=25`); `src.state` (`enable_mitigation`, `throttle_ip`, `block_ip`); `src.report`.
- Produces: `BlueState`; `observe_blue(state) -> dict`; `scripted_blue(obs) -> Decision`; `dispatch_blue(state, decision) -> None`; `make_blue_policy() -> Callable[[dict], Decision]`. Blue actions: `{"patch", "throttle", "block", "wait", "stop"}` (args: `patch` → `{vector}`, `throttle`/`block` → `{ip}`). Loop stop set is `{"stop", "wait"}`.

- [ ] **Step 1: conftest adds repo root**

Append to `agents/blue_team/tests/conftest.py`:
```python
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
```

- [ ] **Step 2: Write failing tests**

Append to `agents/blue_team/tests/test_blue.py`:
```python
from src import strategy
from agent_core.decision import Decision

def test_scripted_blue_patches_unpatched_hit_first():
    obs = {"ip": "1.2.3.4", "vectors": ["sqli"], "score": 10, "patched": [],
           "blocked": False, "throttled": False}
    d = strategy.scripted_blue(obs)
    assert d.action == "patch" and d.args["vector"] == "sqli"

def test_scripted_blue_blocks_over_threshold_once_patched():
    obs = {"ip": "1.2.3.4", "vectors": ["sqli"], "score": 30, "patched": ["sqli"],
           "blocked": False, "throttled": False}
    assert strategy.scripted_blue(obs).action == "block"

def test_scripted_blue_waits_when_nothing_to_do():
    obs = {"ip": "1.2.3.4", "vectors": ["sqli"], "score": 5, "patched": ["sqli"],
           "blocked": False, "throttled": False}
    assert strategy.scripted_blue(obs).action == "wait"

def test_dispatch_patch_records_and_is_idempotent():
    st = strategy.BlueState()
    strategy.dispatch_blue(st, Decision("patch", {"vector": "sqli"}, "x"))
    assert "sqli" in st.patched
```

- [ ] **Step 3: Run, verify fail**

Run: `cd agents/blue_team && python -m pytest tests/test_blue.py -q`
Expected: FAIL (no `strategy`).

- [ ] **Step 4: Implement `strategy.py`**

`agents/blue_team/src/strategy.py`:
```python
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
```

- [ ] **Step 5: Rewire `monitor.py` `handle`**

Replace the enforce/report block of `handle` with: compute `hits`, `techniques`, `score` as today (keep `table.record` called exactly once), emit the `detection` event as today, then set those on a `BlueState` and drive the loop. Thread one `BlueState` and one `decide` through `main` (create once, pass into `handle`), so patched/blocked/throttled persist across detections:
```python
from src import strategy
import agent_core

def handle(entry, table, behaviour, bstate, decide):
    ip = entry.get("ip") or "unknown"
    if ip in rules.WHITELIST:
        return
    matched = waf.matched_rules(entry)
    behavioural = behaviour.inspect(entry)
    if not matched and not behavioural:
        return
    hits = list(dict.fromkeys([r["vector"] for r in matched] + [b["vector"] for b in behavioural]))
    techniques = sorted({r["mitre"] for r in matched} | {t for b in behavioural for t in b["techniques"]})
    score = table.record(ip, len(hits))
    log.info("detected %s from %s (score=%d)", ",".join(hits), ip, score)
    report.emit("detection", {"ip": ip, "vectors": hits, "techniques": techniques, "score": score})
    bstate.ip, bstate.vectors, bstate.techniques, bstate.score = ip, hits, techniques, score
    agent_core.drive(lambda: strategy.observe_blue(bstate), decide,
                     lambda d: strategy.dispatch_blue(bstate, d),
                     max_steps=6, stop=frozenset({"stop", "wait"}))
```
And in `main`, create once and pass in:
```python
bstate = strategy.BlueState()
decide = strategy.make_blue_policy()
...
    handle(entry, table, behaviour, bstate, decide)
```

- [ ] **Step 6: Run tests, verify pass**

Run: `cd agents/blue_team && python -m pytest tests/ -q`
Expected: PASS. If an existing test calls `handle(entry, table, behaviour)` directly, update it to pass a `BlueState()` and `strategy.scripted_blue`.

- [ ] **Step 7: Commit**

```bash
git add agents/blue_team/src/strategy.py agents/blue_team/src/monitor.py agents/blue_team/tests/
git commit -m "feat(blue): policy-driven analyst brain"
```

---

### Task 6: Dashboard — surface reasoning in the feed

**Files:**
- Modify: `dashboard/static/dashboard.js` (show `rationale` for `thought` events)
- Test: `dashboard/tests/test_dashboard.py` (append a case)

**Interfaces:**
- Consumes: the `thought` events emitted by red (→ dashboard `/ingest`) and blue (→ referee `/ingest` → forwarded). No server change: `/ingest` already appends any non-heartbeat event and broadcasts it.

- [ ] **Step 1: Write the failing test**

Append to `dashboard/tests/test_dashboard.py` (follow the file's existing client fixture/pattern):
```python
def test_thought_event_is_kept_in_feed(client):
    client.post("/ingest", json={"team": "red", "kind": "thought",
                                 "rationale": "pivoting to cmdi", "action": "attack"})
    events = client.get("/state").get_json()["events"]
    assert any(e.get("kind") == "thought" and e.get("rationale") == "pivoting to cmdi"
               for e in events)
```

- [ ] **Step 2: Run, verify fail or pass**

Run: `cd dashboard && python -m pytest tests/test_dashboard.py -q`
Expected: This likely PASSES already (ingest is generic). If so, it's a guard test confirming thoughts survive ingest; keep it. The real change is the JS below (not unit-tested; verified in the browser).

- [ ] **Step 3: Show rationale in `pushEvent`**

In `dashboard/static/dashboard.js`, change the `detail` line in `pushEvent` so thoughts show their reasoning:
```javascript
  const detail =
    event.rationale || event.vector || (event.vectors || []).join(",") || event.ip || "";
```
And dim thought rows so they read as reasoning, not scoring events — after the `li.className = ...` line:
```javascript
  if (event.kind === "thought") li.className += " italic text-slate-500";
```

- [ ] **Step 4: Run, verify pass**

Run: `cd dashboard && python -m pytest tests/test_dashboard.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/static/dashboard.js dashboard/tests/test_dashboard.py
git commit -m "feat(dashboard): surface agent reasoning in the feed"
```

Note: a dedicated red/blue reasoning lane was skipped (YAGNI) — thoughts ride the existing feed. Add a lane when the feed gets too noisy to read.

---

### Task 7: Packaging — ship `agent_core` into both images

**Files:**
- Modify: `docker-compose.yml` (red_team + blue_team build contexts → repo root; add `ANTHROPIC_API_KEY` and `BRAIN` env)
- Modify: `agents/red_team/Dockerfile`, `agents/blue_team/Dockerfile` (root context paths + copy `agent_core`)
- Modify: `agents/red_team/requirements.txt`, `agents/blue_team/requirements.txt` (add `anthropic`)
- Modify: `tests/run_all.sh` (add `agent_core` suite)
- Modify: `README.md` (one line: `BRAIN=llm` + key to enable the LLM brain)

**Interfaces:** none (build/wiring only).

- [ ] **Step 1: Add the dep** — append to both agent `requirements.txt`:
```
anthropic==0.69.0
```
(Confirm the latest `anthropic` pin at implementation time; any recent 0.69+ is fine.)

- [ ] **Step 2: Repoint build contexts** in `docker-compose.yml` for `red_team` and `blue_team`:
```yaml
    build:
      context: .
      dockerfile: agents/red_team/Dockerfile
```
```yaml
    build:
      context: .
      dockerfile: agents/blue_team/Dockerfile
```
Add to each agent's `environment:` block:
```yaml
      BRAIN: ${BRAIN:-scripted}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
```

- [ ] **Step 3: Update Dockerfiles for root context.** `agents/red_team/Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY agents/red_team/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent_core ./agent_core
COPY agents/red_team/config ./config
COPY agents/red_team/src ./src
ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["--help"]
```
`agents/blue_team/Dockerfile` — same context changes, keeping its `CMD ["python", "-m", "src.monitor"]`.

- [ ] **Step 4: Add `agent_core` to the test runner.** In `tests/run_all.sh`, add `"agent_core"` to the suite list (before `agents/red_team`).

- [ ] **Step 5: Verify the whole suite**

Run: `bash tests/run_all.sh`
Expected: every suite PASS, including `agent_core`, and the e2e smoke test unchanged (scripted brain, no key).

- [ ] **Step 6: Document the switch.** In `README.md`, under running the lab, add:
```
Set BRAIN=llm and export ANTHROPIC_API_KEY to run the LLM-driven brains
(default BRAIN=scripted needs no key and is what CI runs).
```

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml agents/*/Dockerfile agents/*/requirements.txt tests/run_all.sh README.md
git commit -m "build: ship agent_core into both agent images; BRAIN switch"
```

---

## Notes / deliberate simplifications

- Spec said "structured outputs" for the decision; the plan uses prompt-instructed JSON + `parse_decision` + scripted fallback instead. Same safety (validation + fallback), no dependence on the exact `output_config.format` wire shape. Upgrade to structured outputs if malformed-JSON fallbacks show up often in practice.
- Spec listed `exploit` and `submit` as separate red tools; the plan folds them into one `attack` action (capture + submit) so one move = one scored attempt — fewer LLM calls, less for the brain to track.
- Red observation omits the live scoreboard (one GET to the referee) — skipped as YAGNI; add it to `observe_red` if the brain needs score awareness to play well.
- `obfuscate` reuses the existing `profiles` loud/stealth mechanism rather than touching any exploit code.
