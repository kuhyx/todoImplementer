"""What the errors loop needs from the rest of the server (all of it is injectable in tests)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from todoimpl.http.newtask import NewTask
    from todoimpl.todo_mcp.model import Task


class Tasks(Protocol):
    """The todo client: read a note, write its text."""

    def get_task(self, id8: str) -> Task: ...  # noqa: D102
    def update_task(self, id8: str, **fields: str | None) -> Task: ...  # noqa: D102


class Creator(Protocol):
    """`NewTaskService`: add a part to the repo's note."""

    def create(self, task: NewTask) -> tuple[str, str | None]: ...  # noqa: D102


class Starter(Protocol):
    """The Scheduler: Start a card with auto-ship and the error mark in `extra`."""

    def start(  # noqa: D102
        self, card: str, *, auto_ship: bool | None = None, extra: dict[str, Any] | None = None
    ) -> None: ...
