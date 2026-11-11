"""Which route a turn takes: the plan, the free API credits, or neither (the run waits for the limit).

One cheap, network-free decision shared by the engine's queue, the driver, the board and the actions: the
setting, the SDK venv, the key status the monitor cached and the exhausted marker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from todoimpl.apikey import cache
from todoimpl.usage.limits import limit_state

from . import live, marks, pacing, sdk, setting

if TYPE_CHECKING:
    from pathlib import Path

PLAN = "plan"
CREDITS = "credits"
READY_TEXT = "Turns run on free API credits, paced by week (model sonnet)."
CAPPED_TEXT = "Free API credits are at this week's cap: turns use the plan."
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
    """Return the contract's `credits` object: the fallback state, the pace and the route a new turn takes."""
    state, text = state_of(root, now)
    pace = pacing.pace(root, now)
    chosen = choose(root, now).route
    return {
        "enabled": setting.enabled(),
        "state": state,
        "text": CAPPED_TEXT if state == "ready" and pace.over_cap else text,
        "route": chosen,
        "period_start": pace.period_start,
        "week": pace.week,
        "monthly_usd": pace.monthly_usd,
        "cap_usd": pace.cap_usd,
        "spent_period_usd": pace.spent_usd,
        "credit_turns_period": pace.turns,
        "remaining_usd": pace.remaining_usd,
        "over_cap": pace.over_cap,
        "running_credit_turns": pace.running,
        "cost_factor": pace.cost_factor,
    }


def choose(root: Path, now: float) -> Choice:
    """Credits while the fallback is ready and the weekly pace has room; else the plan, or a wait if limited.

    The cap is hard (`pacing.Pace.over_cap`): past it a turn never takes the credits, not even while the
    plan is limited; it waits for the plan's limit instead.
    """
    if state_of(root, now)[0] == "ready" and not pacing.pace(root, now).over_cap:
        return Choice(CREDITS)
    state = limit_state(root)
    return Choice(None, state.until) if state.active(now) else Choice(PLAN)


def claim(root: Path, now: float, card: str) -> Choice:
    """`choose`, and when it picks the credits, count `card` as running one in the same locked step.

    Two cards deciding at once would otherwise both see room under the cap. `runner.turn.run_turn` ends it.
    """
    with live.LOCK:
        choice = choose(root, now)
        if choice.route == CREDITS:
            live.begin(root, card)
        return choice


def watch(root: Path, card: str, usd: float, now: float) -> bool:
    """Record what `card`'s credit turn has cost so far; at the cap stop every running credit turn at once.

    Return True when the cap was reached. The stopped turns go on at the plan (`runner.pipeline`). This is the
    hard stop behind the start gate: the gate keeps new turns out, this one cuts the running ones.
    """
    with live.LOCK:
        live.set_cost(root, card, usd)
        victims = live.stoppers(root) if pacing.pace(root, now).hard_stop else []
    for hit, stop in victims:
        hit()
        stop()
    return bool(victims)
