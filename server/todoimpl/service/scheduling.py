"""What the service needs from todoimpl.runner.scheduler.Scheduler (brief interface)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator


class SchedulerLike(Protocol):
    """Scheduler(client, root) as the brief specifies it."""

    def start(self, id8: str, *, auto_ship: bool | None = None) -> None:  # noqa: D102
        ...

    def spec_answers(self, id8: str, answers: dict[str, str]) -> None:  # noqa: D102
        ...

    def spec_ok(self, id8: str) -> None:  # noqa: D102
        ...

    def send(self, id8: str, text: str) -> None:  # noqa: D102
        ...

    def ship(self, id8: str) -> None:  # noqa: D102
        ...

    def cancel(self, id8: str) -> None:  # noqa: D102
        ...

    def close_item(self, id8: str) -> None:  # noqa: D102
        ...

    def auto_start(self, id8: str, passed_at: float) -> bool:  # noqa: D102
        ...

    def running(self) -> set[str]:  # noqa: D102
        ...

    def subscribe(self, id8: str) -> Iterator[dict[str, Any]]:  # noqa: D102
        ...
