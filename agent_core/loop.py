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
