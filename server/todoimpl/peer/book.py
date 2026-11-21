"""The messages, one file per card (`<run dir>/peer.json`, its last KEEP), all held in memory.

A message id is `<card>.<hex>`, so a lookup reads only its own card. Callers hold the hub's lock.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl.runner.files import read_json, write_json

from .limits import KEEP

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

FILE = "peer.json"
PRIVATE = ("uuid", "mark")  # delivery bookkeeping, never shown
OPEN = "queued"


def view(msg: dict[str, Any]) -> dict[str, Any]:
    """The message as the card and the API show it."""
    return {k: v for k, v in msg.items() if k not in PRIVATE}


def thread_of(directory: Path) -> list[dict[str, Any]]:
    """A run dir's Peer thread as the card shows it, straight from its file (the task drawer reads this)."""
    rows = read_json(directory / FILE)
    return [view(r) for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


class Book:
    """Every card's thread."""

    def __init__(self, root: Path) -> None:
        """Load every card's file under the run root."""
        self._root = root
        self._cards: dict[str, list[dict[str, Any]]] = {}
        for path in sorted(root.glob(f"*/{FILE}")):
            rows = read_json(path)
            if isinstance(rows, list):
                self._cards[path.parent.name] = [r for r in rows if isinstance(r, dict)]

    def add(self, msg: dict[str, Any]) -> None:
        """File a new message on its card and trim the card to KEEP."""
        card = str(msg["card"])
        self._cards[card] = [*self._cards.get(card, []), msg][-KEEP:]
        self.save(card)

    def save(self, card: str) -> None:
        """Write one card's thread."""
        write_json(self._root / card / FILE, self._cards.get(card, []))

    def get(self, msg_id: str) -> dict[str, Any] | None:
        """The message with this id, None when there is none (or it was trimmed)."""
        card = msg_id.rpartition(".")[0]
        return next((m for m in self._cards.get(card, []) if m["id"] == msg_id), None)

    def thread(self, card: str) -> list[dict[str, Any]]:
        """A card's messages, oldest first."""
        return list(self._cards.get(card, []))

    def queued(self) -> Iterator[dict[str, Any]]:
        """Every message not yet delivered, across cards."""
        for rows in list(self._cards.values()):
            yield from (m for m in rows if m["state"] == OPEN)
