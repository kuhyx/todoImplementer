"""Value types shared by the todo MCP client modules."""

from __future__ import annotations

from dataclasses import dataclass


class TodoError(Exception):
    """Any non-success from the todo MCP server; never means "no tasks"."""


@dataclass(frozen=True)
class Task:
    """One todo-app note; ``id`` is the 8-char prefix, status is ``todo|in progress|done|abandoned``.

    ``list_tasks`` leaves ``body`` "" and ``done_check`` None (list lines lack them).
    """

    id: str
    title: str
    body: str
    repo: str | None
    status: str
    priority: str
    done_check: str | None
