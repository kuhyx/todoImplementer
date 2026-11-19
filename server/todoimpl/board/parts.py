"""The parts of a repo task as its card shows them: one server-computed state per part."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .types import is_manual

if TYPE_CHECKING:
    from todoimpl.repotask.model import Part

    from .state import RunState
    from .types import TaskLike

_NEEDS = re.compile(r"(?m)^\s*Needs:\s*(.+?)\s*$")
NO_ASK = "yours: the note has no Needs: line saying what"
TICKS = "parts_ticks"  # overlay of the run dir's parts-done.json: {"done": [...], "progress": {key: {...}}}


def is_repo_task(task: TaskLike) -> bool:
    """Say whether the card is a repo task (it has parts); a section card or an umbrella has none."""
    return bool(getattr(task, "parts", ()))


def kuhys(title: str, parts: tuple[Part, ...] | list[Part] = ()) -> bool:
    """Say whether the work is kuhy's: a manual note, or a repo task with no part for Claude.

    A repo task's parts decide, not its title (a card with only manual parts is titled after the first),
    since a part whose asks kuhy answered is Claude's again (T1994).
    """
    return not any(part.actionable for part in parts) if parts else is_manual(title)


def parts_of(task: TaskLike, run: RunState | None, *, working: bool) -> list[dict[str, Any]] | None:
    """Return the card's `parts`, None for a card that is not a repo task.

    done = ticked in the run; human / held = never the run's; working = the first part still owed while the
    run works; every other part waits (todo).
    """
    parts = getattr(task, "parts", ())
    if not parts:
        return None
    ticks = run.extra.get(TICKS, {}) if run is not None else {}
    done = set(ticks.get("done", ()))
    progress = ticks.get("progress", {})
    out, current = [], working
    for part in parts:
        if part.held:
            state = "held"
        elif part.human:
            state = "human"
        elif part.key in done:
            state = "done"
        elif current:
            state, current = "working", False
        else:
            state = "todo"
        out.append({"id": part.key, "title": part.title, "state": state, "steps": progress.get(part.key)})
    return out


def manual_ask(task: TaskLike) -> str:
    """Return the card line for human work: the `Needs:` lines of its manual note or human parts (T1951)."""
    bodies = [task.body] if is_manual(task.title) else []
    bodies += [part.body for part in getattr(task, "parts", ()) if part.human]
    asks = dict.fromkeys(m.group(1) for body in bodies for m in _NEEDS.finditer(body or ""))
    return "yours: " + " · ".join(asks) if asks else NO_ASK
