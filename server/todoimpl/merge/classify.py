"""The Haiku classifier: groups open notes of one kind of work (a narrow one-shot, `runner/oneshot.py`)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from todoimpl.board.state import run_root
from todoimpl.runner import oneshot
from todoimpl.runner.claude import DENY_ALWAYS, DENY_READONLY, model_for

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.service.cards import CardTask

TIMEOUT_S = 50.0  # under the 60 s per-action cap
BODY_CHARS = 300
MIN_MEMBERS = 2
PROMPT = """override
You group todo notes that are the same kind of work: many notes that ask for the same change in different
repos or apps, or duplicate notes for one thing. Do not group notes that merely share a topic.
Notes, one per line as `id | repo | title | first characters of the text`:
{notes}

Reply with ONLY a JSON object {{"groups": [{{"ids": [...], "title": "...", "reason": "..."}}]}}.
Each group has at least 2 ids taken from the list, a note appears in at most one group, "title" is the
title of the one combined note, "reason" is one line on why they belong together.
No group is fine: {{"groups": []}}.
"""


INCREMENTAL = """override
You group todo notes that are the same kind of work: many notes that ask for the same change in different
repos or apps, or duplicate notes for one thing. Do not group notes that merely share a topic.
Earlier you grouped some of the open notes. Already grouped, one group per line as `title: ids`:
{groups}
Already seen, not in a group, one per line as `id | repo | title`:
{seen}
New or edited notes, one per line as `id | repo | title | first characters of the text`:
{notes}

Reply with ONLY a JSON object {{"groups": [{{"ids": [...], "title": "...", "reason": "..."}}]}}.
Return only groups that contain at least one NEW note. A new note may join a group above (then list all of
that group's ids again with it), pair with a note that is not in a group, or pair with another new note.
Each group has at least 2 ids taken from the lists, a note appears in at most one group, "title" is the
title of the one combined note, "reason" is one line on why they belong together.
No group is fine: {{"groups": []}}.
"""


class ClassifyError(Exception):
    """The classifier call or its answer was unusable."""


@dataclass(frozen=True)
class Group:
    """A validated proposal: card ids (distinct, >= 2), the combined title and the reason."""

    ids: tuple[str, ...]
    title: str
    reason: str


def row(card: CardTask) -> str:
    """Return the line the classifier sees for a note: id, repo, title, first 300 characters of the body."""
    return f"{card.id} | {card.repo} | {card.title} | {' '.join(card.body.split())[:BODY_CHARS]}"


def build_prompt(cards: list[CardTask]) -> str:
    """Return the prompt listing every given note, one line each."""
    return PROMPT.format(notes="\n".join(row(card) for card in cards))


def build_incremental(new: list[CardTask], groups: list[str], seen: list[CardTask]) -> str:
    """Return the prompt for new or edited notes: stored groups and the older ungrouped notes are context.

    Context lines are indented and carry no body, so only the new notes cost their full text.
    """
    return INCREMENTAL.format(
        groups="\n".join(f"  {line}" for line in groups) or "  (none)",
        seen="\n".join(f"  {c.id} | {c.repo} | {c.title}" for c in seen) or "  (none)",
        notes="\n".join(row(card) for card in new),
    )


def claude_classifier(prompt: str, root: Path | None = None, *, batch: bool = False) -> str:
    """Run the narrow, read-only Haiku one-shot (`runner/oneshot.py`); return its text.

    `batch`: the refresh is background work, so the Batches API may take it (T2532).
    """
    return oneshot.run(
        prompt, model=model_for("classify"), kind="classify", root=root or run_root(), timeout=TIMEOUT_S,
        error=ClassifyError, deny=DENY_ALWAYS + DENY_READONLY, batch=batch,
    )  # fmt: skip


def _group(raw: Any, valid: set[str], used: set[str]) -> Group | None:  # noqa: ANN401 - parsed JSON
    """One proposed group, or None when any rule is broken (ids known and unused, >= 2 distinct, texts)."""
    if not isinstance(raw, dict):
        return None
    ids, title, reason = raw.get("ids"), raw.get("title"), raw.get("reason")
    if not (isinstance(ids, list) and isinstance(title, str) and isinstance(reason, str)):
        return None
    if not all(isinstance(i, str) and i in valid and i not in used for i in ids):
        return None
    distinct = tuple(dict.fromkeys(ids))
    line = next(iter(reason.strip().splitlines()), "").strip()
    if len(distinct) < MIN_MEMBERS or not title.strip() or not line:
        return None
    return Group(distinct, title.strip(), line)


def parse_groups(text: str, valid: set[str]) -> list[Group]:
    """Pull the JSON object out of the model text and keep only valid groups (a note in at most one)."""
    start, end = text.find("{"), text.rfind("}")
    try:
        data: Any = json.loads(text[start : end + 1]) if 0 <= start < end else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("groups"), list):
        msg = f"answer is not a JSON object with groups: {text[:200]!r}"
        raise ClassifyError(msg)
    found: list[Group] = []
    used: set[str] = set()
    for raw in data["groups"]:
        group = _group(raw, valid, used)
        if group is not None:
            found.append(group)
            used.update(group.ids)
    return found
