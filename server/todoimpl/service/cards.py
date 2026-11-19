"""One board card = one todo-note section (Item), keyed by the 8-char id the contracts demand."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.todo_mcp.items import split_items

if TYPE_CHECKING:
    from todoimpl.repotask.model import Part
    from todoimpl.todo_mcp.items import Item
    from todoimpl.todo_mcp.model import Task


def card_id(note_id: str, index: int) -> str:
    """Return the card id `<note id8>-<section index>` (contracts item_id), also the run-dir name."""
    return f"{note_id[:8]}-{index}"


@dataclass(frozen=True)
class CardTask:
    """An Item dressed as the board's TaskLike: id is the card id, priority comes from the parent note."""

    id: str
    title: str
    body: str
    repo: str | None
    status: str
    priority: str
    done_check: str | None
    item: Item
    created_by: str = "kuhy"
    triage: str | None = None  # the label of a repo-less note (triage.json), set by the board fetch

    @property
    def parts(self) -> tuple[Part, ...]:
        """The parts of a repo task's card (DOCS-repotask.md); empty for a section card."""
        return self.item.parts

    @classmethod
    def of(cls, task: Task, item: Item) -> CardTask:
        """Build the card for one section of a note."""
        return cls(
            card_id(item.note_id, item.index),
            item.title,
            item.body,
            item.repo,
            item.status,
            task.priority,
            item.done_check,
            item,
            task.created_by,
        )

    @property
    def note_check(self) -> str | None:
        """The note-level done_check this item ignores because the note has several items."""
        return self.item.note_check


def card_tasks(task: Task) -> list[CardTask]:
    """Every section of a (full) note as a card."""
    return [CardTask.of(task, item) for item in split_items(task)]
