"""Composition root: the real Scheduler, TodoClient, board, usage and lessons behind the http Backend."""

from __future__ import annotations

import importlib
from pathlib import Path

from todoimpl.board.state import run_root
from todoimpl.http.main import REPO, git_build_id
from todoimpl.todo_mcp.client import TodoClient

from .backend import ServiceBackend
from .cache import TaskCache
from .cards import CardTask, card_tasks
from .closed import ClosedNotes
from .scheduling import SchedulerLike
from .view import ItemView

__all__ = ["CardTask", "ItemView", "ServiceBackend", "TaskCache", "build_backend"]


def build_backend(
    root: Path | None = None,
    build: str | None = None,
    client: TodoClient | None = None,
    scheduler: SchedulerLike | None = None,
    *,
    refresh: bool = True,
) -> ServiceBackend:
    """Wire everything; the first note fetch happens here, the refresh thread keeps it fresh afterwards.

    A todo-MCP failure does not stop startup: the board then answers with that error until a refresh works.
    """
    root = root or run_root()
    client = client or TodoClient.from_env()
    closed = ClosedNotes(client, root)

    def fetch() -> list[CardTask]:
        notes = client.list_tasks(full=True)
        cards = [card for note in notes for card in card_tasks(note)]
        return cards + closed.cards({note.id[:8] for note in notes})

    cache = TaskCache(fetch)
    if refresh:
        # Before the Scheduler: its recovery drives resolve card ids through this cache at once.
        cache.refresh()
    if scheduler is None:
        module = importlib.import_module("todoimpl.runner.scheduler")
        scheduler = module.Scheduler(ItemView(client, cache), root)
    if callable(start_watch := getattr(scheduler, "start_phone_watch", None)):
        start_watch()
    backend = ServiceBackend(cache, scheduler, root, build or git_build_id(REPO))
    if refresh:
        cache.start()
    return backend
