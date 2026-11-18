"""GET /api/sessions and POST /api/sessions/<resume|mark|delete|handoff> (contracts/sessions.schema.json).

The POSTs run after the same Origin + CSRF check as Ship (`Router.post`): this server is reachable through
Caddy and Google sign-in, and a resume opens a terminal on the desktop. Mutation outcomes, refusals
included, are HTTP 200 with the `result` shape; only bad JSON is a 400. A handoff creates the task through
the board's new-task service and presses the card's Start the way POST /api/new-task does.
"""

from __future__ import annotations

import json
import re
from http import HTTPStatus
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from todoimpl.sessions import api, router

from .backend import BackendError
from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from todoimpl.sessions.commands import CommandRunner
    from todoimpl.sessions.handoff import Board

    from .backend import Backend
    from .newtask import NewTask

GET_PATH = "/api/sessions"
POST_PATH = re.compile(r"/api/sessions/(resume|mark|delete|handoff)")


class Host(Protocol):
    """What the routes need from the Router: its command runner, the backend and the card's Start click."""

    sessions_runner: CommandRunner
    backend: Backend

    def start_card(self, card: str) -> Reply:
        """Press Start on `card` exactly as the page does."""
        ...


@runtime_checkable
class TaskMaker(Protocol):
    """The part of `NewTaskService` a handoff drives."""

    def check_twin(self, task: NewTask) -> None:
        """Raise BackendError when the title is open already."""

    def create(self, task: NewTask) -> tuple[str, str]:
        """Add the task; return (note id8, card)."""
        ...


class _Board:
    """`handoff.Board` over the backend's new-task service and the Router's Start."""

    def __init__(self, tasks: TaskMaker, host: Host) -> None:
        self._tasks = tasks
        self._host = host

    def check_twin(self, task: NewTask) -> None:
        self._tasks.check_twin(task)

    def create(self, task: NewTask) -> tuple[str, str]:
        return self._tasks.create(task)

    def start(self, card: str) -> bool:
        try:
            return self._host.start_card(card).status == HTTPStatus.OK
        except BackendError:
            return False


def _board(host: Host) -> Board | None:
    tasks = getattr(host.backend, "new_task_service", None)
    return _Board(tasks, host) if isinstance(tasks, TaskMaker) else None


def listing(host: Host) -> Reply:
    """Serve the scanned list of manual sessions."""
    return json_reply(api.listing(host.sessions_runner))


def handle_post(host: Host, found: re.Match[str], raw: bytes) -> Reply:
    """Run the mutation the path names on the JSON body (an empty body is `{}`)."""
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        return error_reply("bad_request", "body is not valid JSON")
    board = _board(host) if found.group(1) == "handoff" else None
    payload = router.mutate(host.sessions_runner, found.group(1), body, board)
    assert payload is not None  # noqa: S101 - POST_PATH only matches the four known names
    return json_reply(payload)
