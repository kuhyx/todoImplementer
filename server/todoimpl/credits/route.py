"""Which route a turn takes: the plan, the free API credits, or neither (the run waits for the limit).

One cheap, network-free decision shared by the engine's queue, the driver, the board and the actions: the
setting, the SDK venv, the key status the monitor cached and the exhausted marker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from todoimpl.apikey import cache
from todoimpl.usage.limits import limit_state

from . import marks, sdk, setting

if TYPE_CHECKING:
    from pathlib import Path

PLAN = "plan"
CREDITS = "credits"
READY_TEXT = "Free API credits take over while the plan limit is active (model sonnet)."
OFF_TEXT = "Free API credits fallback is off: runs wait for the plan limit."
EXHAUSTED_TEXT = "Free API credits exhausted: runs wait until the plan limit resets."


@dataclass(frozen=True)
class Choice:
    """`route` None: the plan limit holds the turn back until `until`."""

    route: str | None
    until: float | None = None


def state_of(root: Path, now: float) -> tuple[str, str]:
    """Return (state, text) of the fallback for the contract's `credits` object."""
    if not setting.enabled():
        return "off", OFF_TEXT
    if sdk.python() is None:
        return "unavailable", sdk.MISSING
    ok, why = cache.usable()
    if not ok:
        return "unavailable", f"Free API credits unavailable: {why}."
    if marks.exhausted(root, now):
        return "exhausted", EXHAUSTED_TEXT
    return "ready", READY_TEXT


def view(root: Path, now: float) -> dict[str, Any]:
    """Return the contract's `credits` object."""
    state, text = state_of(root, now)
    return {"enabled": setting.enabled(), "state": state, "text": text}


def choose(root: Path, now: float) -> Choice:
    """Plan while no limit is active; credits while one is and the fallback is ready; else wait.

    The `credits_first` setting sends turns to the credits even with no limit while they are ready, and to the
    plan when they are not (exhausted, key or SDK missing): the plan is then the fallback, never a wait.
    """
    state = limit_state(root)
    if not state.active(now):
        return Choice(CREDITS if setting.credits_first() and state_of(root, now)[0] == "ready" else PLAN)
    return Choice(CREDITS) if state_of(root, now)[0] == "ready" else Choice(None, state.until)
