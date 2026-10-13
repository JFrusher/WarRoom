# Hybrid Agent Brains — Design

**Date:** 2026-10-12
**Status:** Approved for planning
**Scope:** Replace the red and blue agents' fixed control loops with a shared,
policy-driven agent loop whose "brain" can be a deterministic script (CI) or an
LLM (demo). Add live reasoning narration to the dashboard. Keep the lab fully
lab-locked and the existing test suites green.

## Goal and intent

War Zone today is a scripted battle: red marches a hard-coded kill chain
(`campaign.CHAIN`), blue reflexively patches on first signature match
(`monitor.handle`). The outcome structure is fixed; only timing varies.

This project makes both agents *reason*: each observes what it can see, decides
one action, acts, and explains why — with the explanation streamed to the
dashboard so a viewer watches two agents think. The purpose is a **portfolio
showcase**: it must demo impressively to others. The brains are the headline;
the "watch them think" view matters but is secondary polish.

**Hybrid brain:** the LLM *chooses* an action; deterministic code *executes* it.
The model never touches the network. This is the whole safety story — "an AI
that hacks" stays lab-locked by construction, because the model can only pick
from a fixed enum of tools and our code owns every payload and destination.

## Non-goals (out of scope — future sub-projects)

- Richer target world: fog of war, dynamic vuln injection, extra services.
- Any change to the seven vulnerabilities or their exploit/patch code.
- A central tick scheduler. Red (one-shot `docker compose run`) and blue
  (long-running tailer) stay independent processes racing over shared files.
  The `Policy`/`Observation` shape is designed so the Tier-3 world can bolt on
  later without a rewrite.

## Architecture

New shared package `agent_core`, consumed by both agents. Four small units:

### `Observation`
A snapshot the agent builds from what it can see this loop. No hidden state.

- **Red:** recon posture (forms, which vectors look patched, reachable),
  vectors captured this round, last action's verdict, whether its IP is
  throttled/blocked, current red/blue scores.
- **Blue:** vectors/techniques in the detection being handled, this IP's threat
  score, vectors already patched, current SLA, whether IP is whitelisted.

### `Tool`
A named action with a typed schema. Each wraps a function that **already exists
and is already tested** — the framework adds dispatch, not attack capability.
Tool args are enums and bounded values; the LLM cannot invent a target, URL, or
shell string.

- **Red tools:** `recon` (→ `recon.run`), `exploit` (→ the 7 `capture()`
  modules; args `vector` enum + `obfuscate` bool), `submit` (→ `submit.submit`;
  args `flag`, `vector`), `wait` (sleep; arg `seconds`).
  - New decision surface: `obfuscate` per attempt makes "textbook vs evasion
    first" a choice instead of today's profile constant. This is where red's
    brain and blue's WAF actually spar.
- **Blue tools:** `patch` (→ `state.enable_mitigation`), `throttle`
  (→ `state.throttle_ip`), `block` (→ `state.block_ip`), `wait` (no-op watch).
  - New decision surface: `wait` makes "observe, don't act yet" a real,
    visible choice with a cost — blue can hold instead of patching on first
    sight, the way a real SOC analyst weighs it.

### `Policy`
The brain. One method: `decide(observation) -> Decision(action, args, rationale)`.
Two implementations behind one interface:

- **`ScriptedPolicy`** — today's exact behaviour (red's fixed chain, blue's
  patch-on-sight). The **CI brain**: deterministic, free, no API key. Both
  agents default to it so existing tests run unchanged.
- **`LLMPolicy`** — one `messages.create` per decision returning a structured
  `Decision` (see below). Model is config.

### `Agent` loop
`observe → policy.decide → dispatch tool (our code) → record result → emit
rationale → repeat`. Replaces the inner `for`-loops in `red/cli.py` and
`blue/monitor.py`. Brain selected by a `--brain scripted|llm` flag / env var on
each agent.

## The LLM policy (hybrid split)

Python `anthropic` SDK. Model **`claude-sonnet-5-5`** both sides (config value,
swappable per side).

- **One structured decision per call.** Use structured outputs
  (`output_config.format`, strict schema) to return
  `{action, args, rationale}`. Not the tool-runner — we execute ourselves, so
  the model only *selects*. (Sonnet 5.5 rejects forced `tool_choice`; structured
  outputs sidesteps that entirely.)
- **Adaptive thinking on** (default). Effort left at default initially; tune per
  side before a demo if needed.
- **Per-match memory = the "smart" feel.** Each agent keeps one append-only
  `messages` list for the whole round, so the brain remembers what it tried,
  what scored, what got blocked. Stable prefix (system prompt + schema) is
  prompt-cached.
- **System prompt** per agent sets role + rules: sealed lab, choose exactly one
  action from the toolbox each turn, lab target only, one-line rationale.

### Guardrails
- LLM output constrained to the schema (enum action + bounded args). Cannot emit
  a destination or payload.
- Execution layer stays hard-pinned to the lab target via `config.settings`,
  unchanged.
- Server-side refusal fallback enabled by default on the request.
- **Graceful degradation:** if a decision refuses (`stop_reason == "refusal"`)
  or fails to parse/validate, the agent falls back to `ScriptedPolicy` for that
  one move and continues. A demo never hard-stops. (The scripted brain already
  exists, so this is free.)

## Narration to the dashboard (secondary)

The `rationale` rides existing rails: agent `report.emit` → referee `/ingest` →
dashboard Socket.IO feed. Add one event kind `thought` carrying
`{team, rationale, action}`. Dashboard gains a reasoning lane (red thoughts /
blue thoughts) beside the score feed. Thin by design — reading data already
flowing, not new plumbing.

## Error handling

- LLM call failures (network, 5xx, 429): SDK retries, then fall back to
  `ScriptedPolicy` for that move (same path as refusal/parse failure).
- Decision referencing an unknown action/vector: rejected by schema; if it still
  slips through, dispatch raises and the agent logs + falls back for that move.
- No API key present with `--brain llm`: fail fast at startup with a clear
  message (don't silently run scripted).

## Testing

- **`ScriptedPolicy` keeps every existing suite green.** Both agents default to
  scripted in CI; current unit suites and `tests/e2e_smoke.py` run unchanged,
  no API key.
- **New `agent_core` units:** observation builder, tool dispatch, and decision
  parsing against a fake Anthropic client returning a canned
  `{action, args, rationale}` — assert the right function is dispatched with the
  right args.
- **Guardrail test:** feed a refusal / unparseable decision; assert fallback to
  `ScriptedPolicy` and that the loop continues.
- Each new piece of logic leaves one runnable self-check; no new frameworks.

## Files (expected)

- `agent_core/` — new shared package: `observation.py`, `tool.py`, `policy.py`
  (`ScriptedPolicy`, `LLMPolicy`), `agent.py`, `decision.py` (schema).
- `agents/red_team/src/cli.py` — `--brain` flag; loop delegates to `Agent`.
- `agents/blue_team/src/monitor.py` — `--brain`; `handle` delegates to `Agent`.
- `dashboard/` — `thought` event handling + reasoning lane (`app.py`,
  `dashboard.js`, `dashboard.html`).
- Tests alongside each.
- Packaging: `agent_core` vendored/installed into both agent images
  (requirements + Dockerfile touch).
