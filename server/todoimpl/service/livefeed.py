"""GET /api/live behind the backend: one card's activity from its current cycle on, then its live events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl.board import cyclefloor
from todoimpl.board.card import build_card, cycle_end
from todoimpl.board.state import load, run_dir
from todoimpl.runner.bus import last_seq

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .backend import ServiceBackend

CARD_FIELDS = ("status", "column", "current", "needs", "actions")  # what live.schema.json adds to a stage


def floor(backend: ServiceBackend, id8: str) -> int:
    """Return the newest activity seq the card no longer shows: its earlier cycles' (T2479), else 0.

    A repo card between cycles shows none of the shipped one's lines: its floor is the newest line.
    """
    directory = run_dir(backend.root, id8)
    run = load(directory)
    task = next((t for t in backend.cache.snapshot().tasks if t.id == id8), None)
    if task is not None and cycle_end(task, run):
        return last_seq(directory)
    return cyclefloor.seq(run)


def subscribe(backend: ServiceBackend, id8: str) -> Iterator[dict[str, Any]]:
    """Live events above the card's floor; stage/done carry the fresh card fields (live.schema.json)."""
    for event in backend.scheduler.subscribe(id8, floor(backend, id8)):
        if event.get("type") not in ("stage", "done"):
            yield event
            continue
        card = _card(backend, id8)
        if card is None:  # the note vanished: a half-empty event would break the contract
            continue
        if event["type"] == "done":
            yield {"type": "done", "status": card["status"]}
        else:
            yield {"type": "stage", "stage": event["stage"], **{k: card[k] for k in CARD_FIELDS}}


def _card(backend: ServiceBackend, id8: str) -> dict[str, Any] | None:
    found = next((t for t in backend.cache.snapshot().tasks if t.id == id8), None)
    if found is None:
        return None
    run = backend._with_extras(load(run_dir(backend.root, id8)))  # noqa: SLF001 - the backend's own overlay
    return build_card(found, run, backend._context())  # noqa: SLF001
