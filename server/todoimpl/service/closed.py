"""Cards of fully closed notes: the todo app stops listing a note once every section is shipped and closed.

The run dir is the memory: an item whose state.json says `shipped` keeps its card on the board (Done column)
after its note left `list_tasks`. A closed note never changes, so it is fetched once and its cards are kept.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from todoimpl.board.parse import StateError
from todoimpl.board.state import FILE, load

from .cards import card_tasks

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.todo_mcp.client import TodoClient

    from .cards import CardTask

log = logging.getLogger("todoimpl.service")


class ClosedNotes:
    """Finds shipped run dirs whose note is no longer open and memoizes the cards of those notes."""

    def __init__(self, client: TodoClient, root: Path) -> None:
        """`root` is the run root holding one `<id8>-<n>` dir per item."""
        self._client = client
        self._root = root
        self._cards: dict[str, list[CardTask]] = {}

    def cards(self, open_ids: set[str]) -> list[CardTask]:
        """Return the cards of closed notes with a shipped item; a failed fetch skips that note this round."""
        found: list[CardTask] = []
        for id8 in sorted(self._shipped_ids() - open_ids):
            if id8 not in self._cards:
                try:
                    self._cards[id8] = card_tasks(self._client.get_task(id8))
                except Exception as exc:  # noqa: BLE001 - one unreachable closed note must not blank the board
                    log.warning("closed note %s not fetched: %s", id8, exc)
                    continue
            found.extend(self._cards[id8])
        return found

    def _shipped_ids(self) -> set[str]:
        """Return the note id8 of every run dir whose state is `shipped`."""
        ids: set[str] = set()
        if not self._root.is_dir():
            return ids
        for directory in self._root.iterdir():
            id8, _, index = directory.name.rpartition("-")
            if not (id8 and index.isdigit() and (directory / FILE).is_file()):
                continue
            try:
                run = load(directory)
            except StateError:
                continue
            if run is not None and run.stage == "shipped":
                ids.add(id8)
        return ids
