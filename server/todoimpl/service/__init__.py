"""Composition root: the real Scheduler, TodoClient, board, usage and lessons behind the http Backend."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board.state import run_root
from todoimpl.credits import ledger
from todoimpl.http.main import REPO, git_build_id
from todoimpl.repotask import legacy
from todoimpl.runner.autocheck import AutoCloser
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.umbrella import registry

from .backend import ServiceBackend
from .cache import TaskCache
from .cards import CardTask
from .closed import ClosedNotes
from .repocards import group_cards
from .scheduling import SchedulerLike
from .view import ItemView

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["CardTask", "ItemView", "ServiceBackend", "TaskCache", "board_fetch", "build_backend"]


def board_fetch(client: TodoClient, root: Path) -> Callable[[], list[CardTask]]:
    """Return the cache's fetch: one card per repo (its open parts), the other notes' cards, the Done ones."""
    closed = ClosedNotes(client, root)

    def fetch() -> list[CardTask]:
        notes = client.list_tasks(full=True)
        notes += registry.notes(client, root, {n.id[:8] for n in notes})  # repo-less umbrellas
        cards = group_cards(notes, lambda card: legacy.older(root, card))
        return cards + closed.cards({note.id[:8] for note in notes}, {card.id for card in cards})

    return fetch


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
    ledger.load(root)  # rebuilds the credit ledger from the streams once, if it is missing
    cache = TaskCache(board_fetch(client, root))
    if refresh:
        # Before the Scheduler: its recovery drives resolve card ids through this cache at once.
        cache.refresh()
    if scheduler is None:
        module = importlib.import_module("todoimpl.runner.scheduler")
        scheduler = module.Scheduler(ItemView(client, cache, root), root)
    if callable(start_watch := getattr(scheduler, "start_phone_watch", None)):
        start_watch()
    # Imported here: apikey.monitor needs service.cards, so a top-level import would be circular.
    from todoimpl.apikey.monitor import KeyMonitor  # noqa: PLC0415
    from todoimpl.gateway.monitor import GatewayMonitor  # noqa: PLC0415 - gateway imports the runner
    from todoimpl.merge.service import MergeService  # noqa: PLC0415 - merge.apply imports service.cards
    from todoimpl.newtask.service import NewTaskService  # noqa: PLC0415 - it imports service.cards
    from todoimpl.runner.limitprobe import LimitProbe  # noqa: PLC0415 - runner imports the service view

    monitor = KeyMonitor(client, after_write=cache.poke)
    probe = LimitProbe(root)
    gateway = GatewayMonitor(root)
    backend = ServiceBackend(
        cache, scheduler, root, build or git_build_id(REPO), key_monitor=monitor, limit_probe=probe,
        gateway=gateway,
    )  # fmt: skip
    backend.merge_service = MergeService(client, cache, root)
    backend.new_task_service = NewTaskService(client, cache)
    if refresh:
        cache.start()
        monitor.start()  # first check runs on its own thread: a slow network never delays startup
        probe.start()
        gateway.start()  # a dead gateway only makes its reading `down`
        # Auto close: polls trusted done_checks every 5 min (first tick now); off until settings.json says so.
        # A repo task ships its ticked parts; a closing run belongs to one section's card: no repo cards here.
        AutoCloser(root, lambda: [c for c in cache.snapshot().tasks if not c.parts], scheduler).start()
    return backend
