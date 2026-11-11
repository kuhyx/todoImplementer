"""Group a repo's open notes into its one task card (DOCS-repotask.md).

Umbrella notes and notes without a repo stay as they were. Every other open section is a part; the parts of
a repo become ONE card whose id is `ids.repo_card_id(repo)`. A part an older per-section run still works on
(`held`) keeps that run's own card until the run rests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.board.types import is_manual
from todoimpl.repotask.ids import norm, repo_card_id, repo_human_id
from todoimpl.repotask.legacy import Older
from todoimpl.repotask.model import Part
from todoimpl.todo_mcp.items import Item, split_items
from todoimpl.umbrella.note import is_umbrella, scan_size

from .cards import CardTask, card_id, card_tasks

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.todo_mcp.model import Task

PRIORITIES = ("high", "medium", "low")
MIDDLE = 1


@dataclass(frozen=True)
class _Entry:
    task: Task
    item: Item
    part: Part


def _rank(priority: str) -> int:
    return PRIORITIES.index(priority) if priority in PRIORITIES else MIDDLE


def _order(entry: _Entry) -> tuple[int, int, int, int, str, int]:
    """Priority first, then easiest: the smallest `Scan` count, else the shortest text; stable by note."""
    part = entry.part
    scan = scan_size(part.body)
    size = (0, scan, 0) if scan is not None else (1, 0, len(part.body))
    return (_rank(part.priority), *size, part.note_id, part.index)


def _entries(note: Task, older: Callable[[str], Older]) -> list[_Entry]:
    found = []
    for item in split_items(note):
        if item.status == "done":
            continue
        key = card_id(item.note_id, item.index)
        human = is_manual(item.title)
        before = Older() if human else older(key)  # human work is never the board's
        part = Part(key, item.note_id, item.index, item.title, item.body, note.priority, item.done_check,
                    human, before.held, before.note)  # fmt: skip
        found.append(_Entry(note, item, part))
    return found


def _body(parts: list[Part]) -> str:
    return "\n\n".join(f"### Part {p.key}: {p.title}\n{p.body}".rstrip() for p in parts)


def _check(parts: list[Part]) -> str | None:
    """Return the done_check of the work: the one there is, or the distinct ones chained (all must pass)."""
    checks = list(dict.fromkeys(p.done_check for p in parts if p.done_check))
    if len(checks) <= 1:
        return checks[0] if checks else None
    return " && ".join(f"({c})" for c in checks)


def _repo_card(repo: str, entries: list[_Entry], cid: str) -> CardTask:
    parts = [entry.part for entry in entries]
    work = [part for part in parts if part.actionable]
    title = repo.rpartition("/")[2] or repo
    if not work:  # only human work (or parts held by older runs) is open: the card reads as that work
        title = next(part.title for part in parts if part.human)
    top = min((part.priority for part in work or parts), key=_rank)
    by = "claude" if all(entry.task.created_by == "claude" for entry in entries) else "kuhy"
    body, check = _body(work), _check(work)
    status = "in progress" if any(entry.task.status == "in progress" for entry in entries) else "todo"
    note, _, index = cid.partition("-")  # `-0` Claude's parts, `-1` the human ones (T1980)
    item = Item(note, int(index), title, body, repo, status, check, by, parts=tuple(parts))
    return CardTask(cid, title, body, repo, status, top, check, item, by)


def group_cards(notes: list[Task], older: Callable[[str], Older]) -> list[CardTask]:
    """Return the board's cards: one per repo, the held parts' own cards, and the notes that never group."""
    cards: list[CardTask] = []
    repos: dict[str, list[_Entry]] = {}
    names: dict[str, str] = {}
    for note in notes:
        if note.repo is None or is_umbrella(note.body):
            cards += card_tasks(note)
            continue
        key = norm(note.repo)
        names.setdefault(key, note.repo)
        repos.setdefault(key, []).extend(_entries(note, older))
    for key, entries in repos.items():
        entries.sort(key=_order)
        cards += [CardTask.of(entry.task, entry.item) for entry in entries if entry.part.held]
        # Claude's parts ship and go to Done; the human parts wait in Backlog on a card of their own (T1980)
        work = [entry for entry in entries if not entry.part.human]  # held parts still show on it
        human = [entry for entry in entries if entry.part.human]
        if any(not entry.part.held for entry in work):
            cards.append(_repo_card(names[key], work, repo_card_id(names[key])))
        if human:
            cards.append(_repo_card(names[key], human, repo_human_id(names[key])))
    return cards


def section_cards(cards: list[CardTask]) -> list[CardTask]:
    """Expand repo cards back into one card per open part (what "Merge similar tasks" works on)."""
    out: list[CardTask] = []
    for card in cards:
        if not card.item.parts:
            out.append(card)
            continue
        for part in card.item.parts:
            if part.held:
                continue
            item = Item(part.note_id, part.index, part.title, part.body, card.repo, "todo", part.done_check,
                        card.created_by)  # fmt: skip
            out.append(CardTask(part.key, part.title, part.body, card.repo, "todo", part.priority,
                                part.done_check, item, card.created_by))  # fmt: skip
    return out
