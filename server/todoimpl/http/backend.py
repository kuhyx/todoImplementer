"""What the HTTP layer needs from the rest of the system (the Scheduler plus board/usage/lessons)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator

ERROR_CODES = (
    "bad_request",
    "forbidden",
    "not_found",
    "disabled",
    "conflict",
    "internal",
    "upstream_unavailable",
)


class BackendError(Exception):
    """A refusal the page should see as-is; code is one of contracts/common.schema.json error codes."""

    def __init__(self, code: str, message: str) -> None:
        """Keep the code and the text the page will show."""
        super().__init__(message)
        self.code = code
        self.message = message


class Backend(Protocol):
    """Reads return contract-shaped dicts; actions return nothing and raise BackendError to refuse."""

    def board(self) -> dict[str, Any]:
        """GET /api/board body."""
        ...

    def task(self, id8: str) -> dict[str, Any] | None:
        """GET /api/task/<id8> body, or None for an unknown task."""
        ...

    def shot(self, id8: str, name: str) -> bytes | None:
        """PNG bytes of `<run dir>/shots/<name>` (name already validated), None when absent."""
        ...

    def usage(self) -> dict[str, Any]:
        """GET /api/usage body."""
        ...

    def subscribe(self, id8: str) -> Iterator[dict[str, Any]]:
        """Live events (activity|stage|cost|done) for one task; blocks between events."""
        ...

    def start(self, id8: str, *, auto_ship: bool | None = None) -> None:
        """Start the next stage chain; `auto_ship` None keeps the run's stored choice."""
        ...

    def spec_answers(self, id8: str, answers: dict[str, str]) -> None:
        """Record answers to spec questions."""
        ...

    def spec_ok(self, id8: str) -> None:
        """Spec OK click."""
        ...

    def send(self, id8: str, text: str) -> None:
        """Send text to the task's Claude session."""
        ...

    def ship(self, id8: str) -> None:
        """Ship click."""
        ...

    def cancel(self, id8: str) -> None:
        """Cancel the run."""
        ...

    def credits(self, id8: str) -> None:
        """Run on credits click."""
        ...

    def go(self, id8: str) -> None:
        """Go click on a permission block: run its one-line command, rerun on exit 0."""
        ...

    def rerun(self, id8: str) -> None:
        """Done, rerun click: kuhy ran the command himself."""
        ...

    def lesson_approve(self, id8: str, lesson_id: str) -> None:
        """Approve a drafted lesson."""
        ...
