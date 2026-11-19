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

from todoimpl.board.state import load, run_dir
from todoimpl.board.types import is_manual
from todoimpl.todo_mcp.model import TodoError
from todoimpl.umbrella.note import is_umbrella

from . import label
from .classify import ClassifyError, build_prompt, claude_classifier, parse
from .repos import Listing

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.service.cache import TaskCache
    from todoimpl.service.cards import CardTask
    from todoimpl.todo_mcp.client import TodoClient

log = logging.getLogger("todoimpl.triage")
TICK = 5.0
RETRY_S = 600.0
PER_TICK = 2
CLOSED = ("done", "abandoned")


class TriageService:
    """Labels repo-less notes; `tick()` is one pass, `start()` runs it on a daemon thread."""

    def __init__(  # noqa: PLR0913 - the collaborators, all injectable for tests
        self,
        client: TodoClient,
        cache: TaskCache,
        root: Path,
        *,
        classifier: Callable[[str], str] | None = None,
        repos: Callable[[], list[str]] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Nothing runs until `tick()` or `start()`."""
        self.client, self.cache, self.root, self._clock = client, cache, root, clock
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
            try:
                verdict = parse(self._classifier(build_prompt(card.title, card.body, repos)), repos)
            except ClassifyError as exc:
                log.warning("triage of %s failed: %s", card.id, exc)
                self._failed[card.id] = self._clock()
                continue
            directory = run_dir(self.root, card.id)
            label.save(directory, verdict, label.digest(card.title, card.body), self._clock())
            self._act(card, verdict, directory)
            done += 1
        return done

    def _act(self, card: CardTask, verdict: label.Verdict, directory: Path) -> None:
        """Do what a label needs without a click: existing_repo sets the repo (the card joins that repo's)."""
        if verdict.label != label.EXISTING_REPO:
            return
        try:
            self.client.update_task(card.item.note_id[:8], repo=verdict.repo)
        except TodoError as exc:
            log.warning("setting the repo of %s failed: %s", card.id, exc)
            label.save(directory, verdict, label.digest(card.title, card.body), self._clock(), error=str(exc))
            return
        self.cache.refresh()

    def start(self) -> None:
        """Tick on a daemon thread."""

        def loop() -> None:
            while True:
                try:
                    self.tick()
                except Exception:
                    log.exception("triage tick failed")
                time.sleep(TICK)

        threading.Thread(target=loop, name="triage", daemon=True).start()
