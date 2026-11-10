"""Texts of a merge: the combined same-repo body and the umbrella note. Pure functions of the member cards."""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

from todoimpl.runner.tier import is_cheap

if TYPE_CHECKING:
    from collections.abc import Iterable

    from todoimpl.service.cards import CardTask

CHECK_LINE = re.compile(r"^(\s*)done_check:", re.MULTILINE)


def fingerprint(ids: Iterable[str]) -> str:
    """Return the group id: 12 hex chars of the sorted member card ids (order never matters)."""
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()[:12]


def has_tier(card: CardTask) -> bool:
    """Say whether the card is cheap-tier (`Tier: cheap` line or text-free title, runner/tier.py)."""
    return is_cheap(card.title, card.body)


def member_text(card: CardTask) -> str:
    """Return the card's full text: title, blank line, body.

    A `done_check:` line would make the combined card run one member's check as its own, so it is renamed
    `member done_check:`; a note-level check that is not in the body is kept as such a line.
    """
    body = CHECK_LINE.sub(r"\1member done_check:", card.body)
    if card.done_check and card.done_check not in body:
        body = f"{body}\nmember done_check: {card.done_check}".strip()
    return f"{card.title}\n\n{body}" if body else card.title


def labels(cards: list[CardTask]) -> dict[str, str]:
    """Name each member: its note id8, or its card id when two members are sections of one note."""
    notes = [card.item.note_id[:8] for card in cards]
    return {
        card.id: note if notes.count(note) == 1 else card.id for card, note in zip(cards, notes, strict=True)
    }


def combined_body(cards: list[CardTask]) -> str:
    """Body of the one same-repo card: `Tier: cheap` if any member has it, then each member under `### <id>`.

    Level 3, not the `## <id>` of the umbrella: a `## ` line inside a section would split the new card.
    """
    names = labels(cards)
    parts = [f"### {names[card.id]}\n{member_text(card)}" for card in cards]
    head = ["Tier: cheap"] if any(has_tier(card) for card in cards) else []
    return "\n\n".join([*head, *parts])


def umbrella_text(title: str, cards: list[CardTask]) -> str:
    """Return the umbrella note (no repo field): header, a checklist line and a `## ` section per member."""
    names = labels(cards)
    cheap = any(has_tier(card) for card in cards)
    lines = [f"# {title}", "Umbrella: per-repo", *(["Tier: cheap"] if cheap else [])]
    lines += [f"- [ ] {card.repo} ({names[card.id]})" for card in cards]
    for card in cards:
        lines += [f"## {card.repo} ({names[card.id]})", member_text(card)]
    return "\n".join(lines)
