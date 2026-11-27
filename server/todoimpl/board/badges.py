"""The card's cheap-tier badges (contracts `tier_badges`): the server decides, the page only draws them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.runner.tier import is_cheap

if TYPE_CHECKING:
    from .state import RunState
    from .types import TaskLike


def tier_badges(task: TaskLike, run: RunState | None) -> dict[str, bool]:
    """Cheap from the run's record (else from the note), free only while not escalated."""
    extra = run.extra if run is not None else {}
    if "tier" in extra:
        cheap = extra["tier"] == "cheap"
    else:
        cheap = is_cheap(task.title, task.body, getattr(task, "parts", ()))
    escalated = bool(extra.get("escalated"))
    free = (bool(extra.get("free_models")) and not escalated) or extra.get("route") == "free"  # T2531
    return {"cheap": cheap, "free": free, "escalated": escalated}
