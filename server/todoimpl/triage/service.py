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

from todoimpl.board.clone import wants_public
from todoimpl.board.repos import repo_path
from todoimpl.board.state import RunState, load, run_dir, save
from todoimpl.board.types import is_manual
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner import batchshot
from todoimpl.todo_mcp.model import TodoError
from todoimpl.umbrella.note import is_umbrella

from . import label, newrepo, umbrella
from .classify import NOT_RESEARCH, PRESSED, ClassifyError, build_prompt, claude_classifier, has_url, parse
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
        self._background = classifier or (lambda prompt: claude_classifier(prompt, root, batch=True))  # T2532
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
                verdict = self._verdict(card, repos, files)
            except ClassifyError as exc:
                log.warning("triage of %s failed: %s", card.id, exc)
                self._failed[card.id] = batchshot.failed_at(self._clock(), exc, RETRY_S)  # T2532
                continue
            directory = run_dir(self.root, card.id)
            label.save(directory, verdict, label.digest(card.title, card.body), self._clock())
            self.cache.set_triage(card.id, verdict.label)  # the board shows it now, not after the next fetch
            self._act(card, verdict, directory)
            done += 1
        return done

    def _verdict(self, card: CardTask, repos: list[str], files: list[str], hint: str = "") -> label.Verdict:
        """Classify one note; `research` needs a URL, else the model is asked once more (T2090)."""
        prompt = build_prompt(card.title, card.body, repos, files) + hint
        ask = self._classifier if hint else self._background  # kuhy waits on a pressed Start: never a batch
        verdict = parse(ask(prompt), repos)
        if verdict.label != label.RESEARCH or has_url(card.title, card.body):
            return verdict
        verdict = parse(ask(prompt + NOT_RESEARCH), repos)
        if verdict.label == label.RESEARCH:  # still no URL: it is no reading list, kuhy decides
            return label.Verdict(label.MANUAL, f"no URL to read: {verdict.reason}")
        return verdict

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

    def busy(self) -> frozenset[str]:
        """Return the cards whose repo is being made or whose pressed note is being triaged (T2529)."""
        return frozenset(self._busy)

    # ---- Start of a repo-less card ----
    def start(self, id8: str, *, auto_ship: bool | None = None) -> None:
        """Start a card off the click: `new_repo` gets its repo first, a note nothing can start is triaged."""
        from todoimpl.runner.scheduler import RunnerError  # noqa: PLC0415 - the scheduler imports the service

        card = next((c for c in self.cache.snapshot().tasks if c.id == id8), None)
        stored = label.label_of(run_dir(self.root, id8))
        if card is None or card.repo is not None or is_umbrella(card.body) or stored == label.RESEARCH:
            self.scheduler.start(id8, auto_ship=auto_ship)
            return
        if id8 in self._busy:
            msg = f"{id8} is being created"
            raise RunnerError(msg, "conflict")
        self._busy.add(id8)
        job = self._create if stored == label.NEW_REPO else self._pressed
        self._spawn(lambda: job(card, auto_ship=auto_ship))

    def _pressed(self, card: CardTask, *, auto_ship: bool | None) -> None:
        """Triage a note with no startable label as code work, then route it (T2092: kuhy pressed Start).

        A repo joins that repo's card, a new repo is made, an umbrella is started; a note still not code (or
        any failure) rests as a failed run with the reason, and Retry asks again.
        """
        from todoimpl.runner.scheduler import RunnerError  # noqa: PLC0415 - the scheduler imports the service

        directory = run_dir(self.root, card.id)
        try:
            repos = self.repos()
            files = umbrella.workflow_names(repos, lambda r: repo_path(r, self.src))
            verdict = self._verdict(card, repos, files, PRESSED)
            label.save(directory, verdict, label.digest(card.title, card.body), self._clock())
            self.cache.set_triage(card.id, verdict.label)
            if verdict.label == label.MANUAL:
                msg = f"still not code: {verdict.reason}"
                raise ClassifyError(msg)  # noqa: TRY301 - one failure path for the whole route
            if verdict.label == label.NEW_REPO:
                self._create(card, auto_ship=auto_ship)
                return
            if verdict.label in (label.EXISTING_REPO, label.ALL_REPOS):
                self._act(card, verdict, directory)
                if error := (label.load(directory) or {}).get("error"):
                    raise ClassifyError(str(error))  # noqa: TRY301
            if verdict.label == label.EXISTING_REPO:  # the note is a part of the repo's card: start that card
                try:
                    self.scheduler.start(repo_card_id(str(verdict.repo)), auto_ship=auto_ship)
                except RunnerError as exc:  # a card at work takes the part in its next cycle
                    log.info("card of %s not started: %s", verdict.repo, exc)
            else:
                self.scheduler.start(card.id, auto_ship=auto_ship)
        except Exception as exc:  # noqa: BLE001 - whatever failed, kuhy sees it on the card and may Retry
            log.warning("start of %s failed: %s", card.id, exc)
            save(directory, RunState(card.id, "failed", error=f"start: {exc}", started_at=self._clock()))
        finally:
            self._busy.discard(card.id)
            self.cache.poke()

    def _create(self, card: CardTask, *, auto_ship: bool | None) -> None:
        """Make the repo, give it to the note, start the repo's card; a failure rests as a failed run."""
        directory, note = run_dir(self.root, card.id), card.item.note_id[:8]
        try:
            stored = label.load(directory) or {}
            repo = self._provision(
                directory, self.src, note=note, title=card.title, name=str(stored.get("name")),
                public=wants_public(card.item.body),
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
