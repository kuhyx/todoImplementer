"""Suggestions and clicks: classify in the background, cache in merge.json, merge or dismiss on a click."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from todoimpl.http.backend import BackendError
from todoimpl.todo_mcp.model import TodoError

from . import incremental
from .apply import OPEN, UPSTREAM, MergeError, apply_merge
from .classify import claude_classifier, parse_groups
from .live import live_reason
from .store import MergeState, MergeStore
from .text import fingerprint
from .umbrella import create_umbrella

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.service.cache import TaskCache
    from todoimpl.service.cards import CardTask
    from todoimpl.todo_mcp.client import TodoClient

log = logging.getLogger("todoimpl.merge")
NOT_FOUND = "not_found"
CONFLICT = "conflict"
INTERVAL = 600.0  # at most one classification per 10 minutes
MIN_MEMBERS = 2


def _spawn(job: Callable[[], None]) -> None:
    threading.Thread(target=job, name="merge-classify", daemon=True).start()


@dataclass(frozen=True)
class Suggestion:
    """A validated group still made of open notes."""

    id: str
    title: str
    reason: str
    members: list[CardTask]


class MergeService:
    """Implements todoimpl.http.merge.MergeApi over the cached cards, the todo client and merge.json."""

    def __init__(  # noqa: PLR0913 - the collaborators; all injectable for tests
        self,
        client: TodoClient,
        cache: TaskCache,
        root: Path,
        *,
        classifier: Callable[[str], str] | None = None,
        clock: Callable[[], float] = time.time,
        spawn: Callable[[Callable[[], None]], None] = _spawn,
        umbrella: Callable[[str], str] = create_umbrella,
    ) -> None:
        """Nothing runs until `suggestions()` or `refresh_if_due()` is called."""
        self.client = client
        self.cache = cache
        self.root = root
        self.store = MergeStore(root)
        self._classifier = classifier or partial(claude_classifier, root=root)
        self._clock = clock
        self._spawn = spawn
        self._umbrella = umbrella
        self._classifying = threading.Lock()
        self._merging = threading.Lock()

    # ---- classification (background) ----
    def eligible(self) -> list[CardTask]:
        """Open cards of a repo that a human has not claimed (manual work is never merged away)."""
        return [
            card
            for card in self.cache.snapshot().tasks
            if card.status in OPEN and card.repo and not card.title.startswith("MANUAL WORK REQUIRED:")
        ]

    def refresh_if_due(self) -> bool:
        """Start a background run when notes are new or edited and 10 minutes passed; never blocks.

        Only the new or edited notes are sent (`incremental`); a removal alone just updates the stored ids.
        """
        cards = self.eligible()
        ids = sorted(card.id for card in cards)
        state = self.store.load()
        if len(ids) < MIN_MEMBERS:
            return False
        delta = incremental.diff(state, cards)
        if not delta.changed:
            if ids != state.ids:  # notes were closed: no model call, keep the ids and hashes current
                self.store.update(lambda s: self._remember(s, ids, delta.hashes))
            return False
        if self._clock() - state.at < INTERVAL or not self._classifying.acquire(blocking=False):
            return False
        self._spawn(lambda: self._classify(cards, ids, delta))
        return True

    @staticmethod
    def _remember(state: MergeState, ids: list[str], hashes: dict[str, str]) -> None:
        state.ids, state.hashes = ids, hashes

    def _classify(self, cards: list[CardTask], ids: list[str], delta: incremental.Delta) -> None:
        try:
            state = self.store.load()
            reply = self._classifier(incremental.prompt(state, delta, cards))
            rows = incremental.fold(state, delta, parse_groups(reply, set(ids)), cards)

            def record(state: MergeState) -> None:
                self._remember(state, ids, delta.hashes)
                state.at, state.groups = self._clock(), rows

            self.store.update(record)
        except Exception:
            log.exception("merge classification failed")
            self.store.update(lambda s: setattr(s, "at", self._clock()))  # retry after the interval
        finally:
            self._classifying.release()

    # ---- reads ----
    def _suggestions(self) -> list[Suggestion]:
        """Return stored groups cut down to the notes still open, minus dismissed ones; largest first."""
        by_id = {card.id: card for card in self.eligible()}
        state = self.store.load()
        found: list[Suggestion] = []
        for row in state.groups:
            # A member counts only while its id still names the section Haiku saw (cutting renumbers ids).
            pairs = zip(row["ids"], row["titles"], strict=True)
            members = [by_id[i] for i, title in pairs if i in by_id and by_id[i].title == title]
            group_id = fingerprint(card.id for card in members)
            if len(members) >= MIN_MEMBERS and group_id not in state.dismissed:
                found.append(Suggestion(group_id, row["title"], row["reason"], members))
        return sorted(found, key=lambda s: (-len(s.members), s.title))

    def _view(self) -> list[dict[str, Any]]:
        out = []
        for s in self._suggestions():
            why = live_reason(self.root, [card.id for card in s.members])
            merge = {"id": "merge", "label": "Merge", "enabled": why is None, "reason": why}
            dismiss = {"id": "dismiss", "label": "Dismiss", "enabled": True, "reason": None}
            members = [{"id": c.id, "title": c.title, "repo": c.repo} for c in s.members]
            out.append(
                {
                    "id": s.id,
                    "title": s.title,
                    "reason": s.reason,
                    "members": members,
                    "actions": [merge, dismiss],
                }
            )
        return out

    def suggestions(self) -> dict[str, Any]:
        """GET /api/merges: the cached suggestions; a due classification starts in the background."""
        self.refresh_if_due()
        return {"suggestions": self._view()}

    # ---- clicks ----
    def _find(self, group_id: str) -> Suggestion:
        found = next((s for s in self._suggestions() if s.id == group_id), None)
        if found is None:
            msg = "no such suggestion"
            raise BackendError(NOT_FOUND, msg)
        return found

    def merge(self, group_id: str) -> dict[str, Any]:
        """POST merge: refuse while a member has a live run, else make the note and close the members."""
        suggestion = self._find(group_id)
        if not self._merging.acquire(blocking=False):
            msg = "another merge is running"
            raise BackendError(CONFLICT, msg)
        try:
            result = apply_merge(
                self.client, self.root, self.store, suggestion.members, suggestion.title, self._umbrella
            )
        except MergeError as exc:
            raise BackendError(exc.code, exc.message) from exc
        except TodoError as exc:
            msg = f"todo MCP: {exc}"
            raise BackendError(UPSTREAM, msg) from exc
        finally:
            self._merging.release()
            self.cache.refresh()
        return {"ok": True, "new_id": result.new_id, "suggestions": self._view()}

    def dismiss(self, group_id: str) -> dict[str, Any]:
        """POST dismiss: never suggest this exact group again."""
        self._find(group_id)
        self.store.update(lambda s: s.dismissed.append(group_id))
        return {"ok": True, "new_id": None, "suggestions": self._view()}
