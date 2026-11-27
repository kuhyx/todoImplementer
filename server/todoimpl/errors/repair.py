"""Fold twin parts into one: one open part per signature and per issue on every card (T2570).

Before T2570 a tick over a board that was not loaded yet made a second part of every open ticket, so kartka's
card showed the same `[sig8]` twice. Each tick this repair keeps the first open part of a group and closes
the others in place (`closed: duplicate of <key>`). A group is the open parts of one card that share a
signature, or the app and `Error:` line (`twin.issues`). A twin's signature that the kept part lacks moves
over first (its block is appended), so no report loses its ticket. Closing in place renumbers no section,
so run dirs and ticks keep pointing at the same parts. A card whose run is live is left until it rests.
Idempotent: a twin already closed reads as done and is skipped; any todo error leaves the rest to the next
tick.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from todoimpl.board.status import CLOSED
from todoimpl.merge.live import live_reason
from todoimpl.todo_mcp.items import split_items
from todoimpl.todo_mcp.model import TodoError

from . import ledger, twin
from .marks import signatures

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from todoimpl.repotask.model import Part
    from todoimpl.service.cards import CardTask
    from todoimpl.todo_mcp.items import Item

    from .ports import Tasks

log = logging.getLogger("todoimpl.errors")


def _marks(part: Part) -> set[str]:
    return {*signatures(part.body), *twin.issues(part.body)}


def groups(parts: Sequence[Part]) -> list[list[Part]]:
    """Return the groups of two or more parts that share a signature or an issue, in card order."""
    found: list[tuple[set[str], list[Part]]] = []
    for part in parts:
        marks = _marks(part)
        hits = [group for group in found if group[0] & marks]
        if not hits:
            if marks:
                found.append((marks, [part]))
            continue
        first = hits[0]
        first[0].update(marks)
        first[1].append(part)
        for other in hits[1:]:  # a part that bridges two groups joins them
            first[0].update(other[0])
            first[1].extend(other[1])
            found.remove(other)
    return [members for _marks_, members in found if len(members) > 1]


def _open(tasks: Tasks, part: Part) -> Item | None:
    """Return the part's item read fresh, None when it moved or is closed already."""
    items = split_items(tasks.get_task(part.note_id))
    item = items[part.index] if part.index < len(items) else None
    return item if item is not None and item.title == part.title and item.status != "done" else None


def _close(tasks: Tasks, root: Path, keep: Part, dup: Part) -> bool:
    """Move the twin's missing signatures onto `keep`, then close the twin; False when either is not open."""
    item, held = _open(tasks, dup), _open(tasks, keep)
    if item is None or held is None:
        return False
    if set(signatures(item.body)) - set(signatures(held.body)):
        spot = twin.Spot(keep.note_id, keep.index, keep.title, held.body, same=False)
        twin.attach(tasks, spot, twin.block(item.body))
    tasks.close_item(item, f"duplicate of {keep.key}: one part per error signature (T2570)")
    for key in signatures(item.body):
        if ledger.load(root).get(key, {}).get("state") == "ticket":
            ledger.put(root, key, title=keep.title, count=0)  # the kept part's Seen line is rewritten next
    return True


def fold(root: Path, cards: Sequence[CardTask], tasks: Tasks) -> int:
    """Close every twin part of every resting card; return how many were closed."""
    closed = 0
    for card in cards:
        if card.status in CLOSED or not (found := groups(card.parts)):
            continue
        if live_reason(root, [card.id, *(part.key for part in card.parts)]) is not None:
            continue
        try:
            for keep, *dups in found:
                closed += sum(_close(tasks, root, keep, dup) for dup in dups)
        except TodoError as exc:
            log.warning("card %s: twins not folded: %s", card.id, exc)
    return closed
