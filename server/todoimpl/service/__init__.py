"""Composition root: the real Scheduler, TodoClient, board, usage and lessons behind the http Backend."""

from __future__ import annotations

import importlib
from pathlib import Path

from todoimpl.board.state import run_root
from todoimpl.http.main import REPO, git_build_id
from todoimpl.runner.autocheck import AutoCloser
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.umbrella import registry

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
        notes += registry.notes(client, root, {n.id[:8] for n in notes})  # repo-less umbrellas
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
    # Imported here: apikey.monitor needs service.cards, so a top-level import would be circular.
    from todoimpl.apikey.monitor import KeyMonitor  # noqa: PLC0415
    from todoimpl.merge.service import MergeService  # noqa: PLC0415 - merge.apply imports service.cards
    from todoimpl.runner.limitprobe import LimitProbe  # noqa: PLC0415 - runner imports the service view

    monitor = KeyMonitor(client, after_write=cache.poke)
    probe = LimitProbe(root)
    backend = ServiceBackend(
        cache, scheduler, root, build or git_build_id(REPO), key_monitor=monitor, limit_probe=probe
    )
    backend.merge_service = MergeService(client, cache, root)
    if refresh:
        cache.start()
        monitor.start()  # first check runs on its own thread: a slow network never delays startup
        probe.start()
        # Auto close: polls trusted done_checks every 5 min (first tick now); off until settings.json says so.
        AutoCloser(root, lambda: cache.snapshot().tasks, scheduler).start()
    return backend
