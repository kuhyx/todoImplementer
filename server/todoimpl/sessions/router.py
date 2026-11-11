"""Name -> handler for the three session mutations; the http layer owns the path, the guard and the status."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl.sessions import delete, mark, resume
from todoimpl.sessions.result import to_payload

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.sessions.commands import CommandRunner
    from todoimpl.sessions.result import MutationResult

ACTIONS: dict[str, Callable[[CommandRunner, object], MutationResult]] = {
    "resume": resume.apply,
    "mark": mark.apply,
    "delete": delete.apply,
}


def mutate(runner: CommandRunner, name: str, body: object) -> dict[str, Any] | None:
    """Run one mutation and return its result payload; None for an unknown name."""
    handler = ACTIONS.get(name)
    return None if handler is None else to_payload(handler(runner, body))
