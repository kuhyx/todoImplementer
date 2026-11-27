"""Composition root: the real Scheduler, TodoClient, board, usage and lessons behind the http Backend."""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board.state import run_dir, run_root
from todoimpl.credits import ledger
from todoimpl.errors.loop import ErrorLoop
from todoimpl.http.main import REPO, git_build_id
from todoimpl.nolimit.tick import Loop as NoLimitLoop
from todoimpl.peer import service as peer
from todoimpl.repotask import foldasks, legacy
from todoimpl.runner.autocheck import AutoCloser
from todoimpl.runner.resetwatch import ResetWatch
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.triage.label import label_of
from todoimpl.umbrella import registry

from . import repoalias
from .backend import ServiceBackend
from .cache import TaskCache
from .cards import CardTask
from .closed import ClosedNotes
from .known_repos import KnownRepos
from .notedone import NoteDoneWatcher
from .repocards import group_cards, released_in
from .runtitles import RunTitles, card_titles
from .scheduling import SchedulerLike
from .view import ItemView

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.newtask.service import NewTaskService

__all__ = ["CardTask", "ItemView", "ServiceBackend", "TaskCache", "board_fetch", "build_backend"]


def board_fetch(
    client: TodoClient, root: Path, run_titles: RunTitles | None = None
) -> Callable[[], list[CardTask]]:
    """Return the cache's fetch: one card per repo (its open parts), the other notes' cards, the Done ones.

    `run_titles` learns, on each fetch, the names of run dirs that no card or part shows (/api/usage).
    """
    closed = ClosedNotes(client, root)

    def fetch() -> list[CardTask]:
        notes = client.list_tasks(full=True)
        # Repo-less notes (kuhy's ideas) are cards in the Yours lane (T2058); an older server that ignores
        # `no_repo` answers with the repo notes again, so a note counts once.
        seen = {n.id for n in notes}
        notes += [n for n in client.list_tasks(full=True, no_repo=True) if n.id not in seen]
        notes = repoalias.heal(client, notes)  # one name per real repo: its checkout's origin (T2272)
        notes += registry.notes(client, root, {n.id[:8] for n in notes})  # repo-less umbrellas not listed
        foldasks.fold_all(root, notes)  # answers from a former `-1` card, once (T2114)
        cards = group_cards(notes, lambda card: legacy.older(root, card), released_in(root))
        # A repo-less note's triage label (a file in its run dir) rides on its card.
        cards = [
            replace(c, triage=found) if c.repo is None and (found := label_of(run_dir(root, c.id))) else c
            for c in cards
        ]
        cards += closed.cards({note.id[:8] for note in notes}, {card.id for card in cards})
        if run_titles is not None:
            run_titles.update(card_titles(cards))
        return cards

    return fetch


def repo_fetch(client: TodoClient, root: Path) -> Callable[[str], list[CardTask]]:
    """Return the cache's one-repo read: the repo's open notes grouped as `board_fetch` groups them."""

    def fetch(repo: str) -> list[CardTask]:
        notes = client.list_tasks(repo=repo, full=True)
        return group_cards(notes, lambda card: legacy.older(root, card), released_in(root))

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
    run_titles = RunTitles(client, root)
    cache = TaskCache(board_fetch(client, root, run_titles), repo_fetch=repo_fetch(client, root))
    cache.run_titles = run_titles
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
    from todoimpl.asks.service import AskService  # noqa: PLC0415 - it imports http.backend
    from todoimpl.gateway.monitor import GatewayMonitor  # noqa: PLC0415 - gateway imports the runner
    from todoimpl.merge.auto import AutoMerge  # noqa: PLC0415 - it imports the merge service
    from todoimpl.merge.service import MergeService  # noqa: PLC0415 - merge.apply imports service.cards
    from todoimpl.newtask.service import NewTaskService  # noqa: PLC0415 - it imports service.cards
    from todoimpl.runner.holdceiling import Ceiling  # noqa: PLC0415 - runner imports the service view
    from todoimpl.runner.limitprobe import LimitProbe  # noqa: PLC0415 - runner imports the service view
    from todoimpl.stall.watch import StallWatch  # noqa: PLC0415 - runner imports the service view
    from todoimpl.triage.service import TriageService  # noqa: PLC0415 - it imports service.cards

    monitor = KeyMonitor(client, after_write=cache.poke)
    probe = LimitProbe(root)
    gateway = GatewayMonitor(root)
    backend = ServiceBackend(
        cache, scheduler, root, build or git_build_id(REPO), key_monitor=monitor, limit_probe=probe,
        gateway=gateway,
    )  # fmt: skip
    backend.merge_service = MergeService(client, cache, root)
    if refresh:  # a test backend never reaches for gh
        backend.known_repos = KnownRepos().get
        backend.known_repos()  # first fetch starts now, off this thread
    auto_merge = AutoMerge(backend.merge_service)
    new_tasks = NewTaskService(client, cache)
    backend.new_task_service = new_tasks
    backend.ask_service = AskService(cache, scheduler, root)
    backend.triage_service = TriageService(client, cache, root, scheduler=scheduler)
    if refresh:
        backend.peer_hub = peer.start(root, scheduler)  # sessions message each other (DOCS-peer.md)
        cache.start()
        backend.ask_service.start()  # 24 h auto-adopt of reversible choices
        auto_merge.start()  # Haiku groups similar notes, the board merges them itself (DOCS-merge.md)
        backend.triage_service.watch()  # labels notes without a repo (DOCS-triage.md)
        NoteDoneWatcher(cache, client, scheduler, root).start()  # a note done in the todo app (T2065)
        # Each first check runs on its own thread: a slow network never delays startup; a dead gateway
        # only makes its reading `down`.
        for watcher in (monitor, probe, gateway):
            watcher.start()
        Ceiling(scheduler).start()  # an idle build-lock holder gives the lock on after 2 min (T2166)
        # Auto close: polls trusted done_checks every 5 min (first tick now); off until settings.json says so.
        # A repo task ships its ticked parts; a closing run belongs to one section's card: no repo cards here.
        AutoCloser(root, lambda: [c for c in cache.snapshot().tasks if not c.parts], scheduler).start()
        # App errors: one ticket per identical error, started by the gate (DOCS-errors.md).
        ErrorLoop(
            root, cards=lambda: cache.snapshot().tasks, tasks=client, creator=new_tasks,
            starter=scheduler, refresh=cache.refresh,
        ).start()  # fmt: skip
        _start_upkeep(backend, root, cache, new_tasks, scheduler)
        # A running card quiet over 60 s is logged and filed (DOCS-errors.md, "Stalls").
        StallWatch(root).start()
    return backend


def _start_upkeep(
    backend: ServiceBackend,
    root: Path,
    cache: TaskCache,
    new_tasks: NewTaskService,
    scheduler: SchedulerLike,
) -> None:
    """Start the loops that work with no tokens or file their own notes: no-limit runner, reset watch."""
    # No Claude route at all: rerun repo gates and apply autofixes with no tokens (DOCS-nolimit.md).
    backend.nolimit = NoLimitLoop(root).start()
    # A usage reset files one token optimization note and starts it first (DOCS-credits.md).
    ResetWatch(root, lambda: cache.snapshot().tasks, new_tasks, scheduler).start()
