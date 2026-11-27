"""Start while a higher-priority card waits in Backlog: the start action names that card (T2583).

kuhy, 2026-11-27: "starting a task with lower priority than at least one task still in backlog pops a modal
asking if they are sure". The server decides; the page and the app only ask when `waits` is there. Priority
is the card's (other apps' reports count as low); among several higher cards the highest one is named.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from todoimpl.repotask import lane

from .card import cycle_end
from .status import Status, compute

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .state import RunState
    from .types import TaskLike

RANK: Final = {"high": 0, "medium": 1, "low": 2}
MIDDLE: Final = 1


def _rank(priority: object) -> int:
    return RANK.get(str(priority), MIDDLE)


def backlog(tasks: Iterable[TaskLike], runs: dict[str, RunState | None]) -> list[dict[str, Any]]:
    """Return the cards waiting in Backlog (status `backlog`) as {id, title, priority, lane}."""
    found = []
    for task in tasks:
        run = runs.get(task.id)
        run = None if cycle_end(task, run) else run
        if compute(task, run, live=False, limit_until=None) == Status.BACKLOG:
            found.append(
                {"id": task.id, "title": task.title, "priority": task.priority, "lane": lane.of_card(task)}
            )
    return found


def mark(card: dict[str, Any], waiting: Sequence[dict[str, Any]]) -> None:
    """Add `waits` to the card's enabled start action when a higher-priority Backlog card waits."""
    start = next((a for a in card["actions"] if a["id"] == "start" and a["enabled"]), None)
    mine = _rank(card["priority"])
    higher = [c for c in waiting if c["id"] != card["id"] and _rank(c["priority"]) < mine]
    if start is None or not higher:
        return
    top = min(higher, key=lambda c: (_rank(c["priority"]), lane.rank(c["lane"]), c["title"], c["id"]))
    start["waits"] = {"id": top["id"], "title": top["title"], "priority": top["priority"]}
