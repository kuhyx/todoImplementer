"""Classify only what changed: new or edited notes are judged against the stored groups (DOCS-merge.md).

A note's hash covers the line the classifier sees (id, repo, title, first 300 characters of the body), so an
edit that the model could not see does not cost a call. A removal costs nothing at all: stored groups are
cut to the notes still open when they are read. A `merge.json` with no hashes gets one full run.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .classify import build_incremental, build_prompt, row
from .store import MergeState

if TYPE_CHECKING:
    from collections.abc import Sequence

    from todoimpl.service.cards import CardTask

    from .classify import Group


@dataclass(frozen=True)
class Delta:
    """What a classification run has to look at: `changed` notes (all of them when `full`) and every hash."""

    changed: list[CardTask]
    hashes: dict[str, str]
    full: bool


def card_hash(card: CardTask) -> str:
    """Return a short hash of the line the classifier sees for the card."""
    return hashlib.sha256(row(card).encode()).hexdigest()[:12]


def diff(state: MergeState, cards: Sequence[CardTask]) -> Delta:
    """Return the notes that are new or edited since the stored run (all of them without stored hashes)."""
    hashes = {card.id: card_hash(card) for card in cards}
    full = not state.hashes
    changed = [c for c in cards if full or state.hashes.get(c.id) != hashes[c.id]]
    return Delta(changed, hashes, full)


def _kept(state: MergeState, cards: Sequence[CardTask], changed: set[str]) -> list[dict[str, Any]]:
    """Return stored groups cut to the notes still open and unedited; a broken-up pair is dropped."""
    open_ids = {c.id for c in cards} - changed
    kept = []
    for stored in state.groups:
        pairs = [(i, t) for i, t in zip(stored["ids"], stored["titles"], strict=True) if i in open_ids]
        if len(pairs) >= 2:  # noqa: PLR2004 - a group needs two members
            kept.append({**stored, "ids": [i for i, _ in pairs], "titles": [t for _, t in pairs]})
    return kept


def prompt(state: MergeState, delta: Delta, cards: Sequence[CardTask]) -> str:
    """Return the full prompt, or (stored hashes exist) the changed notes with the groups as context."""
    if delta.full:
        return build_prompt(list(cards))
    changed = {c.id for c in delta.changed}
    kept = _kept(state, cards, changed)
    grouped = {i for g in kept for i in g["ids"]}
    lines = [f"{g['title']}: {', '.join(g['ids'])}" for g in kept]
    seen = [c for c in cards if c.id not in changed and c.id not in grouped]
    return build_incremental(delta.changed, lines, seen)


def fold(
    state: MergeState, delta: Delta, found: list[Group], cards: Sequence[CardTask]
) -> list[dict[str, Any]]:
    """Return the new stored groups: the model's groups for this run, over the kept ones minus overlaps."""
    titles = {c.id: c.title for c in cards}

    def make(group: Group) -> dict[str, Any]:
        ids = list(group.ids)
        return {"ids": ids, "titles": [titles[i] for i in ids], "title": group.title, "reason": group.reason}

    if delta.full:
        return [make(g) for g in found]
    changed = {c.id for c in delta.changed}
    fresh = [make(g) for g in found if changed & set(g.ids)]  # a group without a new note is not news
    taken = {i for g in fresh for i in g["ids"]}
    kept = _kept(state, cards, changed)
    for stored in kept:  # a note the model moved leaves its old group
        stored["titles"] = [t for i, t in zip(stored["ids"], stored["titles"], strict=True) if i not in taken]
        stored["ids"] = [i for i in stored["ids"] if i not in taken]
    return [g for g in kept if len(g["ids"]) >= 2] + fresh  # noqa: PLR2004 - a group needs two members
