"""The priority picker of a card (T2583): kuhy sets high, medium or low on the notes behind it.

A repo card's priority is the highest of its open parts' notes (`service/repocards.py`); a pick sets it on
every note that holds a part of kuhy's or the board's. A card of only other apps' reports is always low
(DOCS-errors.md, T2582): its picker is offered disabled with that reason, and Start still runs it now.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from todoimpl.repotask import lane

from .button import Action
from .status import Status

if TYPE_CHECKING:
    from .types import TaskLike

ID: Final = "priority"
CHOICES: Final = (
    {"id": "high", "label": "High"},
    {"id": "medium", "label": "Medium"},
    {"id": "low", "label": "Low"},
)
LEVELS: Final = tuple(c["id"] for c in CHOICES)
APP_REASON: Final = "other apps' error reports always run last; Start runs them now"
ENDED: Final = (Status.DONE, Status.DONE_MANUALLY)


def refusal(task: TaskLike) -> str | None:
    """Return why the card's priority cannot change, None when a pick can succeed."""
    return APP_REASON if lane.of_card(task) == lane.APP else None


def action(task: TaskLike, status: Status) -> list[Action]:
    """Return the picker of an open card (none once it is done): its value is the card's priority."""
    if status in ENDED:
        return []
    why = refusal(task)
    value = task.priority if task.priority in LEVELS else "medium"
    return [Action(ID, "Priority", why is None, why, value=value, choices=CHOICES)]
