"""Which parts kuhy may still edit (856c0f0a): an unticked part the run has not reached yet.

A live run holds the first part it still owes, whether the card shows it `working` (the run works) or
`todo` (it waits in Needs you, a pause, the gate, the queue or a Cancel that Start resumes): the run has
already read that part. Every later part, every part of a resting card and kuhy's manual parts stay
editable. The route checks the same `edit` again before it writes (http/partedit.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .status import Status

if TYPE_CHECKING:
    from .types import TaskLike

RESTING = frozenset({Status.BACKLOG, Status.YOURS, Status.DONE, Status.DONE_MANUALLY})
REACHED = "the run is on this part"
REASONS = {"done": "ticked: Ship closes it", "held": "an older run owns it", "working": REACHED}


def with_edit(parts: list[dict[str, Any]], status: Status) -> list[dict[str, Any]]:
    """Add `edit: {enabled, reason}` to each part the card shows; a disabled one says why."""
    owed = status not in RESTING
    for part in parts:
        reason = REASONS.get(part["state"])
        if part["state"] in {"todo", "working"} and owed:
            reason, owed = REACHED, False
        part["edit"] = {"enabled": reason is None, "reason": reason}
    return parts


def with_bodies(card: dict[str, Any], task: TaskLike) -> None:
    """Detail only: each part's own text, the editor's start value (the board stays small)."""
    bodies = {part.key: part.body for part in getattr(task, "parts", ())}
    for part in card.get("parts", ()):
        part["body"] = bodies.get(part["id"], "")
