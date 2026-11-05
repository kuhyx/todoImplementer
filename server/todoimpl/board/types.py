"""Small shared types: the usage limit, the shape of a todo note, and time formatting for reasons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

HALF_DAY = 20 * 3600


class TaskLike(Protocol):
    """What the board needs from an item; `id` is its card id `<note id8>-<index>`."""

    @property
    def id(self) -> str: ...  # noqa: D102
    @property
    def title(self) -> str: ...  # noqa: D102
    @property
    def body(self) -> str: ...  # noqa: D102
    @property
    def repo(self) -> str | None: ...  # noqa: D102
    @property
    def status(self) -> str: ...  # noqa: D102
    @property
    def priority(self) -> str: ...  # noqa: D102
    @property
    def done_check(self) -> str | None: ...  # noqa: D102


@dataclass(frozen=True)
class Limit:
    """Claude plan limit: `until` is None when none is active (mirrors common.schema.json limit)."""

    active: bool = False
    until: float | None = None
    credits_available: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return the JSON object of the contract."""
        return {"active": self.active, "until": self.until, "credits_available": self.credits_available}


def fmt_when(epoch: float, now: float) -> str:
    """Return a local clock time, with the weekday when it is not within the next ~20 hours."""
    moment = datetime.fromtimestamp(epoch).astimezone()
    return moment.strftime("%H:%M" if abs(epoch - now) < HALF_DAY else "%a %H:%M")
