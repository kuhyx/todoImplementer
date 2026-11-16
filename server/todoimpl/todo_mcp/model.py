"""Value types shared by the todo MCP client modules."""

from __future__ import annotations

from dataclasses import dataclass


class TodoError(Exception):
    """Any non-success from the todo MCP server; never means "no tasks"."""


class UnreachableError(TodoError):
    """The todo MCP did not answer (timeout, refused, or errors while it was already failing); retry later."""


def upstream_text(text: str) -> str:
    """Prefix a todo failure with its source, unless it already names the todo MCP ("not answering")."""
    return text if text.startswith("todo MCP") else f"todo MCP: {text}"


@dataclass(frozen=True)
class Task:
    """One todo-app note; ``id`` is the 8-char prefix, status is ``todo|in progress|done|abandoned``.

    ``created_by`` is ``kuhy`` or ``claude`` (old notes lack it: kuhy).
    ``list_tasks`` leaves ``body`` "" and ``done_check`` None (list lines lack them).
    """

    id: str
    title: str
    body: str
    repo: str | None
    status: str
    priority: str
    done_check: str | None
    created_by: str = "kuhy"
