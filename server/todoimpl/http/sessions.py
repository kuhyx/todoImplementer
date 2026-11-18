"""GET /api/sessions and POST /api/sessions/<resume|mark|delete|handoff> (contracts/sessions.schema.json).

The POSTs run after the same Origin + CSRF check as Ship (`Router.post`): this server is reachable through
Caddy and Google sign-in, and a resume opens a terminal on the desktop. Mutation outcomes, refusals
included, are HTTP 200 with the `result` shape; only bad JSON is a 400. A handoff creates the task through
the board's new-task service and presses the card's Start the way POST /api/new-task does.
"""

from __future__ import annotations

import json
import logging
import re
from http import HTTPStatus
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from todoimpl.sessions import api, router
from todoimpl.sessions.handoff import NOT_STARTED, STARTED, WAITS

from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from todoimpl.sessions.commands import CommandRunner
    from todoimpl.sessions.handoff import Board

    from .backend import Backend
    from .newtask import NewTask

GET_PATH = "/api/sessions"
POST_PATH = re.compile(r"/api/sessions/(resume|mark|delete|handoff)")
log = logging.getLogger("todoimpl.http")


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

    def adopt(self, task: NewTask, key: str) -> tuple[str, str] | None:
        """Return (note id8, card) of the task's own open section, else None."""
        ...

    def add(self, task: NewTask) -> str:
        """Add the task; return its note id8."""
        ...

    def card_of(self, note8: str, task: NewTask) -> str | None:
        """Return the card holding the section, None when it never shows."""
        ...


@runtime_checkable
class Waiter(Protocol):
    """The Scheduler's `start_when_free` (runner/whenfree.py)."""

    def start_when_free(self, card: str) -> bool:
        """Arm the card's Start for when its run ships; False when nothing holds it."""
        ...


class _Board:
    """`handoff.Board` over the backend's new-task service, the Router's Start and the Scheduler's wait."""

    def __init__(self, tasks: TaskMaker, host: Host, waiter: Waiter | None) -> None:
        self._tasks = tasks
        self._host = host
        self._waiter = waiter

    def check_twin(self, task: NewTask) -> None:
        self._tasks.check_twin(task)

    def adopt(self, task: NewTask, key: str) -> tuple[str, str] | None:
        return self._tasks.adopt(task, key)

    def add(self, task: NewTask) -> str:
        return self._tasks.add(task)

    def card_of(self, note8: str, task: NewTask) -> str | None:
        return self._tasks.card_of(note8, task)

    def start(self, card: str) -> str:
        # As POST /api/new-task (`_guard` around Start): the task exists now, so a Start that breaks only
        # leaves the card waiting; it must not turn the handoff into a 500 that leaves the session unmarked.
        # A Start refused because a run holds the card arms its start for when that run ships (kuhy,
        # 2026-11-18); a card that came free between the two looks is pressed again.
        try:
            if self._pressed(card):
                return STARTED
            if self._waiter is not None and self._waiter.start_when_free(card):
                return WAITS
            return STARTED if self._pressed(card) else NOT_STARTED
        except Exception:
            log.exception("handoff: Start of %s failed", card)
            return NOT_STARTED

    def _pressed(self, card: str) -> bool:
        return self._host.start_card(card).status == HTTPStatus.OK


def _board(host: Host) -> Board | None:
    tasks = getattr(host.backend, "new_task_service", None)
    waiter = getattr(host.backend, "scheduler", None)
    return (
        _Board(tasks, host, waiter if isinstance(waiter, Waiter) else None)
        if isinstance(tasks, TaskMaker)
        else None
    )


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
