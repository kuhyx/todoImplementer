"""Priority click (T2583): kuhy sets a card's priority on the notes behind it; `ServiceBackend.priority`.

A repo card spans notes: the pick goes to every note that holds an open part of kuhy's or the board's (other
apps' reports always count as low, DOCS-errors.md). A plain card is one note. The cache is refreshed at once,
so the board shows the new order on the next read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board.prioaction import refusal
from todoimpl.http.backend import BackendError
from todoimpl.repotask import lane
from todoimpl.todo_mcp.model import TodoError, upstream_text

from .view import ItemView

if TYPE_CHECKING:
    from .backend import ServiceBackend
    from .cards import CardTask

NOT_FOUND, DISABLED, UPSTREAM = "not_found", "disabled", "upstream_unavailable"


def notes_of(card: CardTask) -> list[str]:
    """Return the note ids a pick changes: the notes of the card's open non-report parts, else its own."""
    if not card.parts:
        return [card.item.note_id]
    found = [p.note_id for p in card.parts if p.actionable and lane.of_text(p.body) != lane.APP]
    return list(dict.fromkeys(found))


def set_priority(backend: ServiceBackend, id8: str, *, priority: str) -> None:
    """Set `priority` on the notes behind card `id8`; refused for a card of only other apps' reports."""
    card = next((t for t in backend.cache.snapshot().tasks if t.id == id8), None)
    view = getattr(backend.scheduler, "client", None)  # the real Scheduler reads notes via an ItemView
    if card is None or not isinstance(view, ItemView):
        msg = f"unknown task {id8}"
        raise BackendError(NOT_FOUND, msg)
    if (why := refusal(card)) is not None:
        raise BackendError(DISABLED, why)
    try:
        for note in notes_of(card):
            view.set_note_priority(note, priority)
    except TodoError as exc:
        msg = upstream_text(str(exc))
        raise BackendError(UPSTREAM, msg) from exc
    finally:
        backend.cache.poke()
