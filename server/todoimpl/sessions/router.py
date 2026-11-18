"""Name -> handler for the four session mutations; the http layer owns the path, the guard and the status."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl.sessions import delete, handoff, mark, resume
from todoimpl.sessions.result import to_payload

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.sessions.commands import CommandRunner
    from todoimpl.sessions.handoff import Board
    from todoimpl.sessions.result import MutationResult

type Handler = Callable[[CommandRunner, object, Board | None], MutationResult]

# Only handoff talks to the board; the other three act on the transcripts and the marks file alone.
ACTIONS: dict[str, Handler] = {
    "resume": lambda runner, body, _board: resume.apply(runner, body),
    "mark": lambda runner, body, _board: mark.apply(runner, body),
    "delete": lambda runner, body, _board: delete.apply(runner, body),
    "handoff": handoff.apply,
}


def mutate(
    runner: CommandRunner, name: str, body: object, board: Board | None = None
) -> dict[str, Any] | None:
    """Run one mutation and return its result payload; None for an unknown name."""
    handler = ACTIONS.get(name)
    return None if handler is None else to_payload(handler(runner, body, board))
