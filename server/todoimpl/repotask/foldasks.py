"""Move the answers kuhy gave on a repo's former human card onto its one card, once (T2114).

From T1980 to T2114 a repo's MANUAL WORK REQUIRED parts sat on a card of their own, `<hash>-1`, and kuhy's
answers to their asks were saved in that card's run dir (`asks.json`). Since kuhy's 2026-11-19 decision
those parts sit on the repo card `<hash>-0`, which reads answers from its own run dir. The board fetch calls
`fold_all` before grouping, so a part he released there stays released and nothing is asked twice.

Only the ask ids an open manual part of the repo asks now move: an answer from a manual note closed long
ago would otherwise answer a new ask that happens to reuse its id. A record the repo card already has wins.
A mark file in the old dir makes the move happen once; the old dir is never deleted.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from todoimpl import atomic
from todoimpl.asks import store
from todoimpl.asks.parse import parse_asks
from todoimpl.board.types import is_manual
from todoimpl.todo_mcp.items import split_items
from todoimpl.umbrella.note import is_umbrella

from .ids import former_human_id, norm, repo_card_id

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from todoimpl.todo_mcp.model import Task

MARK = "asks-folded.json"


def _asked(notes: Iterable[Task]) -> dict[str, tuple[str, set[str]]]:
    """Return {norm(repo): (repo, ask ids of its open manual parts)} for the notes that group per repo."""
    found: dict[str, tuple[str, set[str]]] = {}
    for note in notes:
        if note.repo is None or is_umbrella(note.body):
            continue
        _, ids = found.setdefault(norm(note.repo), (note.repo, set()))
        for item in split_items(note):
            if item.status != "done" and is_manual(item.title):
                ids.update(ask.id for ask in parse_asks(item.body))
    return found


def fold(root: Path, repo: str, ids: set[str]) -> bool:
    """Copy the old card's records of `ids` the repo card lacks; return True when the repo card changed."""
    old = root / former_human_id(repo)
    if not (old / store.FILE).is_file() or (old / MARK).is_file():
        return False
    source, target = store.load(old), root / repo_card_id(repo)
    data = store.load(target)
    moved = sorted(i for i in ids if i in source["items"] and i not in data["items"])
    for ask_id in moved:
        data["items"][ask_id] = source["items"][ask_id]
        if ask_id in source["seen"]:
            data["seen"].setdefault(ask_id, source["seen"][ask_id])
    if moved:
        data["log"].append(f"fold: {', '.join(moved)} from {old.name} (one card per repo, T2114)")
        store.save(target, data)
    atomic.write_text(old / MARK, json.dumps({"moved": moved, "to": target.name}))
    return bool(moved)


def fold_all(root: Path, notes: Iterable[Task]) -> list[str]:
    """Fold every repo of `notes` that still has unfolded answers; return the repo cards that changed."""
    return [repo_card_id(repo) for repo, ids in _asked(notes).values() if fold(root, repo, ids)]
