"""TodoClient: typed access to the todo app's MCP task tools."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from todoimpl.todo_mcp.items import Item, mark_done, sections, split_items
from todoimpl.todo_mcp.model import Task, TodoError
from todoimpl.todo_mcp.parse import added_id, parse_detail, parse_list, to_wire
from todoimpl.todo_mcp.transport import Transport
from todoimpl.umbrella.note import is_umbrella, tick

__all__ = ["Item", "Task", "TodoClient", "TodoError"]

DEFAULT_URL = "http://127.0.0.1:8735/mcp"
_TOKEN_REL = Path(".config") / "todo-mcp-client" / "token"
_UPDATE_FIELDS = frozenset({"title", "body", "done_check", "priority", "status", "repo"})


class TodoClient:
    """Every non-success raises ``TodoError``; notes without a repo are invisible to list/search.

    ``list_tasks(no_repo=True)`` is the one way to list them (the server's `no_repo` argument).
    """

    def __init__(  # noqa: D107
        self, url: str, token: str, timeout: float = 20.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.url = url
        self._transport = Transport(url, token, timeout, clock)

    def __repr__(self) -> str:  # noqa: D105
        return f"TodoClient({self.url!r})"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> TodoClient:
        """Read TODOIMPL_MCP_URL and the raw token from TODOIMPL_MCP_TOKEN_FILE."""
        env = os.environ if env is None else env
        home = Path(env.get("HOME") or Path.home())
        path = Path(env.get("TODOIMPL_MCP_TOKEN_FILE") or home / _TOKEN_REL)
        try:
            token = path.read_text().strip()
        except OSError as err:
            msg = f"cannot read MCP token file {path}: {err}"
            raise TodoError(msg) from err
        if not token:
            msg = f"MCP token file {path} is empty"
            raise TodoError(msg)
        return cls(env.get("TODOIMPL_MCP_URL") or DEFAULT_URL, token)

    def list_tasks(
        self, status: str | None = None, repo: str | None = None, *, full: bool = False, no_repo: bool = False
    ) -> list[Task]:
        """Open notes by default; ``full=True`` adds body and done_check via get_task.

        ``no_repo=True`` lists the notes that have no repo instead (kuhy's ideas, the board's Yours lane).
        """
        args: dict[str, object] = {}
        if no_repo:
            args["no_repo"] = True
        if status is not None:
            args["status"] = to_wire(status)
        if repo is not None:
            args["repo"] = repo
        tasks = parse_list(self._transport.call_tool("list_tasks", args))
        return [self.get_task(task.id) for task in tasks] if full else tasks

    def search_tasks(self, query: str) -> list[Task]:  # noqa: D102
        return parse_list(self._transport.call_tool("search_tasks", {"query": query}))

    def get_task(self, id8: str) -> Task:  # noqa: D102
        return parse_detail(self._transport.call_tool("get_task", {"id": id8}))

    def update_task(self, id8: str, **fields: str | None) -> Task:
        """Change title/body/done_check/priority/status/repo; None skips, "" clears."""
        unknown = set(fields) - _UPDATE_FIELDS
        if unknown:
            msg = f"unknown update field(s): {sorted(unknown)}"
            raise TodoError(msg)
        args: dict[str, object] = {"id": id8}
        for key, value in fields.items():
            if value is not None:
                args[key] = to_wire(value) if key == "status" else value
        self._transport.call_tool("update_task", args)
        return self.get_task(id8)

    def close_task(self, id8: str, evidence: str) -> None:
        """Mark done; the server refuses blank evidence."""
        self._transport.call_tool("close_task", {"id": id8, "evidence": evidence})

    def add_task(
        self, repo: str, title: str, body: str = "", done_check: str | None = None, priority: str = "medium"
    ) -> Task:
        """Append a section to the repo's open note (or create it) and return that note."""
        args: dict[str, object] = {"repo": repo, "title": title, "priority": priority}
        if body:
            args["body"] = body
        if done_check is not None:
            args["done_check"] = done_check
        return self.get_task(added_id(self._transport.call_tool("add_task", args)))

    def close_item(self, item: Item, evidence: str) -> None:
        """Mark one section done; close the note once every section is. Fails closed on a moved section."""
        if not evidence.strip():
            msg = "evidence: required, not blank"
            raise TodoError(msg)
        task = self.get_task(item.note_id)
        if is_umbrella(task.body):  # one item: its `## ` sections are children, never marked here
            self.close_task(item.note_id, evidence)
            return
        current = split_items(task)
        if item.index >= len(current) or current[item.index].title != item.title:
            msg = f"section {item.title!r} moved or gone in note {item.note_id}"
            raise TodoError(msg)
        if sections(task.body) and current[item.index].status != "done":
            self.update_task(item.note_id, body=mark_done(task.body, item.index, evidence))
            current = split_items(self.get_task(item.note_id))
        if all(entry.status == "done" for entry in current) or not sections(task.body):
            self.close_task(item.note_id, evidence)

    def tick_child(self, id8: str, key: str, mark: str = "x") -> None:
        """Set child `key`'s open checkbox in an umbrella note to `mark`; no write when it is not open."""
        task = self.get_task(id8)
        body = tick(task.body, key, mark)
        if body != task.body:
            self.update_task(id8, body=body)
