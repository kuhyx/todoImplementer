"""Background triage: label every repo-less note once per text, and act on the labels that need no click.

Never on the board fetch path: a Haiku call takes seconds, the fetch has a 100 ms budget. The loop reads the
cache, classifies at most `PER_TICK` new or edited notes per tick and writes `triage.json` into the card's run
dir. A classifier failure leaves the note untriaged (Yours) and is retried after `RETRY_S`.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from todoimpl.board.repos import repo_path
from todoimpl.board.state import RunState, load, run_dir, save
from todoimpl.board.types import is_manual
from todoimpl.repotask.ids import repo_card_id
from todoimpl.todo_mcp.model import TodoError
from todoimpl.umbrella.note import is_umbrella

from . import label, newrepo, umbrella
from .classify import ClassifyError, build_prompt, claude_classifier, parse
from .repos import Listing

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.service.cache import TaskCache
    from todoimpl.service.cards import CardTask
    from todoimpl.service.scheduling import SchedulerLike
    from todoimpl.todo_mcp.client import TodoClient

log = logging.getLogger("todoimpl.triage")
TICK = 5.0
RETRY_S = 600.0
PER_TICK = 2
CLOSED = ("done", "abandoned")


def _spawn(job: Callable[[], None]) -> None:
    threading.Thread(target=job, name="new-repo", daemon=True).start()


class TriageService:
    """Labels repo-less notes (`tick()` is one pass, `watch()` runs it on a daemon thread) and starts them."""

    def __init__(  # noqa: PLR0913 - the collaborators, all injectable for tests
        self,
        client: TodoClient,
        cache: TaskCache,
        root: Path,
        *,
        scheduler: SchedulerLike,
        classifier: Callable[[str], str] | None = None,
        repos: Callable[[], list[str]] | None = None,
        clock: Callable[[], float] = time.time,
        spawn: Callable[[Callable[[], None]], None] = _spawn,
        provision: Callable[..., str] = newrepo.provision,
        src: Path | None = None,
    ) -> None:
        """Nothing runs until `tick()`, `watch()` or `start()`."""
        self.client, self.cache, self.root, self._clock = client, cache, root, clock
        self.scheduler, self._spawn, self._provision = scheduler, spawn, provision
        self.src = src or repo_path("kuhyx/x").parent  # ~/src, or $TODOIMPL_SRC
        self._busy: set[str] = set()
        self._classifier = classifier or (lambda prompt: claude_classifier(prompt, root))
        self.repos = repos or Listing().get
        self._failed: dict[str, float] = {}

    def eligible(self) -> list[CardTask]:
        """Open single-note cards with no repo, not manual by title, with no run yet."""
        cards = self.cache.snapshot().tasks
        ids = {card.id for card in cards}
        return [
            card
            for card in cards
            if card.repo is None
            and card.status not in CLOSED
            and not is_umbrella(card.body)
            and not is_manual(card.title)
            and f"{card.item.note_id[:8]}-1" not in ids  # a note with sections is several cards: not triaged
            and load(run_dir(self.root, card.id)) is None
        ]

    def due(self) -> list[CardTask]:
        """Cards whose text has no label yet or changed since, minus those a failure keeps waiting."""
        now, out = self._clock(), []
        for card in self.eligible():
            stored = label.load(run_dir(self.root, card.id))
            if stored is not None and stored.get("digest") == label.digest(card.title, card.body):
                continue
            if now - self._failed.get(card.id, -RETRY_S) >= RETRY_S:
                out.append(card)
        return out

    def tick(self) -> int:
        """Triage up to `PER_TICK` due notes; return how many got a label."""
        done = 0
        for card in self.due()[:PER_TICK]:
            repos = self.repos()
            files = umbrella.workflow_names(repos, lambda r: repo_path(r, self.src))
            try:
                verdict = parse(self._classifier(build_prompt(card.title, card.body, repos, files)), repos)
            except ClassifyError as exc:
                log.warning("triage of %s failed: %s", card.id, exc)
                self._failed[card.id] = self._clock()
                continue
            directory = run_dir(self.root, card.id)
            label.save(directory, verdict, label.digest(card.title, card.body), self._clock())
            self.cache.set_triage(card.id, verdict.label)  # the board shows it now, not after the next fetch
            self._act(card, verdict, directory)
            done += 1
        return done

    def _act(self, card: CardTask, verdict: label.Verdict, directory: Path) -> None:
        """Do what a label needs without a click: existing_repo sets the repo, all_repos makes an umbrella."""
        note, fields = card.item.note_id[:8], {}
        if verdict.label == label.EXISTING_REPO:
            fields = {"repo": verdict.repo}
        elif verdict.label == label.ALL_REPOS:
            found = umbrella.matching(
                self.repos(), verdict.token, verdict.path, lambda r: repo_path(r, self.src)
            )
            if not found:  # no child, no umbrella: the note stays Yours with the reason on its label
                label.update(directory, error="no repo matches")
                return
            label.update(directory, repos=found)
            fields = {"body": umbrella.body(card.title, card.item.body, found, note)}
        else:
            return
        try:
            self.client.update_task(note, **fields)
        except TodoError as exc:
            log.warning("setting the repo of %s failed: %s", card.id, exc)
            label.update(directory, error=str(exc))
            return
        self.cache.refresh()

    def watch(self) -> None:
        """Tick on a daemon thread."""

        def loop() -> None:
            while True:
                try:
                    self.tick()
                except Exception:
                    log.exception("triage tick failed")
                time.sleep(TICK)

        threading.Thread(target=loop, name="triage", daemon=True).start()

    # ---- Start of a repo-less card ----
    def start(self, id8: str, *, auto_ship: bool | None = None) -> None:
        """Start a card: a `new_repo` card gets its repo first (off the click), any other starts as it is."""
        from todoimpl.runner.scheduler import RunnerError  # noqa: PLC0415 - the scheduler imports the service

        card = next((c for c in self.cache.snapshot().tasks if c.id == id8), None)
        directory = run_dir(self.root, id8)
        if card is None or card.repo is not None or label.label_of(directory) != label.NEW_REPO:
            self.scheduler.start(id8, auto_ship=auto_ship)
            return
        if id8 in self._busy:
            msg = f"{id8} is being created"
            raise RunnerError(msg, "conflict")
        self._busy.add(id8)
        self._spawn(lambda: self._create(card, auto_ship=auto_ship))

    def _create(self, card: CardTask, *, auto_ship: bool | None) -> None:
        """Make the repo, give it to the note, start the repo's card; a failure rests as a failed run."""
        directory, note = run_dir(self.root, card.id), card.item.note_id[:8]
        try:
            stored = label.load(directory) or {}
            repo = self._provision(
                directory, self.src, note=note, title=card.title, name=str(stored.get("name")),
            )  # fmt: skip
            self.client.update_task(note, repo=repo)
            self.cache.refresh()  # the scheduler resolves card ids through the cache
            new = repo_card_id(repo)
            label.update(directory, repo=repo, new_card=new)
            self.scheduler.start(new, auto_ship=auto_ship)
        except Exception as exc:  # noqa: BLE001 - whatever failed, kuhy sees it on the card and may Retry
            log.warning("new repo for %s failed: %s", card.id, exc)
            save(directory, RunState(card.id, "failed", error=f"new repo: {exc}", started_at=self._clock()))
        finally:
            self._busy.discard(card.id)
            self.cache.poke()
