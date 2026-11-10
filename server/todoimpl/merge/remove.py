"""Take merged sections out of their source notes, so they leave the board instead of piling up as Done.

Card ids are `<note id8>-<section index>`: cutting a section renumbers the ones after it. That is only safe
while no section at or after the first cut one has a run dir (its state, branch and worktree are named by the
index); a note that fails that test keeps its sections and the caller closes them in place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board.state import run_dir
from todoimpl.todo_mcp.items import sections

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.service.cards import CardTask
    from todoimpl.todo_mcp.client import TodoClient


def cut(body: str, indexes: set[int]) -> str:
    """Return the body without the `## ` sections at these indexes (heading to the next heading)."""
    lines = body.split("\n")
    parts = sections(body)
    keep = lines[: parts[0].heading] if parts else lines
    for index, part in enumerate(parts):
        if index not in indexes:
            keep += lines[part.heading : part.heading + 1 + len(part.lines)]
    return "\n".join(keep)


def _removable(root: Path, note_id: str, indexes: set[int], total: int) -> bool:
    """Say whether cutting leaves every remaining card id and run dir pointing at the same section."""
    return not any(run_dir(root, f"{note_id}-{i}").exists() for i in range(min(indexes), total))


def remove_members(
    client: TodoClient, root: Path, cards: list[CardTask]
) -> tuple[list[CardTask], list[CardTask], list[str]]:
    """Cut each note's member sections where that is safe.

    Returns (removed cards, cards left for an in-place close, ids of notes now finished). A note is finished
    when nothing but done sections (or nothing at all) is left; the caller closes it with its evidence.
    """
    by_note: dict[str, list[CardTask]] = {}
    for card in cards:
        by_note.setdefault(card.item.note_id, []).append(card)
    removed: list[CardTask] = []
    finished: list[str] = []
    for note_id, members in by_note.items():
        note = client.get_task(note_id)
        parts = sections(note.body)
        indexes = {card.item.index for card in members}
        titles_match = all(
            card.item.index < len(parts) and parts[card.item.index].title == card.title for card in members
        )
        if not parts or not titles_match or not _removable(root, note_id, indexes, len(parts)):
            continue
        body = cut(note.body, indexes)
        client.update_task(note_id, body=body)
        left = sections(body)
        if (left and all(part.done for part in left)) or (not left and not body.strip()):
            finished.append(note_id)
        removed += members
    return removed, [card for card in cards if card not in removed], finished
