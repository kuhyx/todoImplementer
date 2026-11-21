"""The pump's round: deliver queued messages into live turns, confirm them by their echo, expire the rest.

Callers hold the hub's lock. A message to a task is written once per turn (`pipe.write`) and is `delivered`
when the stream replays its uuid (`pipe.echoed`); if that turn ends unread, the next one gets it again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from . import envelope, limits

if TYPE_CHECKING:
    from collections.abc import Callable

    from .book import Book

ENDED = ("answered", "expired", "dead_end")
type Mark = tuple[str, int]
type Changed = Callable[..., None]


class Pipe(Protocol):
    """A task session's stdin and its stream."""

    def write(self, card: str, line: dict[str, Any]) -> Mark | None:  # noqa: D102
        ...

    def echoed(self, card: str, mark: Mark, uuid: str) -> bool:  # noqa: D102
        ...

    def is_open(self, card: str) -> bool:  # noqa: D102
        ...


def tick(book: Book, live: Callable[[str], str | None], pipe: Pipe, now: float, changed: Changed) -> None:
    """One round over every queued message."""
    for row in list(book.queued()):
        card = row["to_card"]
        state = live(card) if card else "live"
        if now >= row["at"] + limits.EXPIRE or state is None:
            why = "the session ended" if state is None else "not delivered in 30 min"
            row |= {"state": "expired", "reason": why}
            changed(row, save=True)
        elif card and state != "held":
            _push(book, pipe, card, row, now, changed)


def _mark(row: dict[str, Any]) -> Mark | None:
    found = row["mark"]
    return (str(found[0]), int(found[1])) if found else None


def _push(book: Book, pipe: Pipe, card: str, row: dict[str, Any], now: float, changed: Changed) -> None:  # noqa: PLR0913, PLR0917 - one message's delivery step
    mark = _mark(row)
    if mark is not None and not pipe.echoed(card, mark, row["uuid"]):
        if pipe.is_open(card):
            return  # written into this session's stdin: it reads it at its next tool boundary
        mark = None  # that turn ended unread: the next session gets it
    if mark is None:
        text = envelope.wrap(row["from"], row["id"], row["hop"], row["text"])
        mark = pipe.write(
            card, {"type": "user", "uuid": row["uuid"], "message": {"role": "user", "content": text}}
        )
        row["mark"] = list(mark) if mark is not None else None
        book.save(card)
    if mark is not None and pipe.echoed(card, mark, row["uuid"]):
        row |= {"state": "delivered", "delivered_at": now}
        changed(row, save=True)
