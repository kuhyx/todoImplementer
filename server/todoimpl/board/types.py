"""Small shared types: the usage limit, the shape of a todo note, and time formatting for reasons."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    @property
    def created_by(self) -> str: ...  # noqa: D102


MANUAL_PREFIX = "MANUAL WORK REQUIRED:"
MANUAL_REASON = "MANUAL WORK REQUIRED: this is for you, Claude does not start it"


def is_manual(title: str) -> bool:
    """Return True for a note whose title says a human must do it (exact caps, title start)."""
    return title.startswith(MANUAL_PREFIX)


@dataclass(frozen=True)
class Credits:
    """The paced free credits as the server words them (mirrors credits.schema.json)."""

    enabled: bool = False
    state: str = "off"
    text: str = "Free API credits fallback is off: runs wait for the plan limit."
    route: str | None = None
    period_start: float = 0.0
    week: int = 1
    monthly_usd: float = 0.0
    cap_usd: float = 0.0
    spent_period_usd: float = 0.0
    credit_turns_period: int = 0
    remaining_usd: float = 0.0
    over_cap: bool = False
    running_credit_turns: int = 0
    cost_factor: float = 1.0
    batches: dict[str, object] = field(
        default_factory=lambda: {"pending": 0, "est_usd": 0.0, "oldest_at": None}
    )  # pending one-shots on the Batches API (T2532)

    def to_dict(self) -> dict[str, object]:
        """Return the JSON object of the contract."""
        return asdict(self)


@dataclass(frozen=True)
class Limit:
    """Claude plan limit: `until` is None when none is active (mirrors common.schema.json limit)."""

    active: bool = False
    until: float | None = None
    credits: Credits = Credits()
    weekly_hold: str = "none"  # T2533: none, low_medium or all
    weekly_used: float | None = None

    @property
    def holds(self) -> bool:
        """True when the limit keeps turns from starting: active and the free credits cannot take over."""
        return self.active and (self.credits.state != "ready" or self.credits.over_cap)

    def to_dict(self) -> dict[str, object]:
        """Return the JSON object of the contract."""
        return {"active": self.active, "until": self.until, "credits": self.credits.to_dict()}


def fmt_when(epoch: float, now: float) -> str:
    """Return a local clock time, with the weekday when it is not within the next ~20 hours."""
    moment = datetime.fromtimestamp(epoch).astimezone()
    return moment.strftime("%H:%M" if abs(epoch - now) < HALF_DAY else "%a %H:%M")
