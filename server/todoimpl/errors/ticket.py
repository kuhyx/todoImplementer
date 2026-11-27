"""The ticket of one app error: its title and text, finding it again on the board, editing its lines.

A ticket is one `## title` part of the repo's note. Its identity is the `Error-Signature: <app>:<signature>`
line; the `Seen:` line carries the count and is the only line the loop rewrites. kuhy's textgate does not
reach this text: it is a todo note (user content) read by a session, not a screen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.todo_mcp.items import sections

from .marks import SIGNATURE, signatures

if TYPE_CHECKING:
    from collections.abc import Iterable

    from todoimpl.service.cards import CardTask

    from .record import AppError

__all__ = ["Found", "body", "error_line", "find", "refresh", "seen", "signatures", "title"]

MESSAGE_IN_TITLE = 80
GOAL = (
    "Fix this error / bring this wait under 1 s without breaking existing behaviour. "
    "Do not ask kuhy anything; take recommended answers."
)
DONE = "done: fixed, tests green, shipped and deployed (the error no longer reproduces)."
PERF = (  # kuhy, 2026-11-21: a step over 60 s is the session's to fix, never his (T2467)
    "How: measure where the time goes, then optimise in as many rounds as it takes (cache, drop redundant "
    "work, parallelise, a faster tool); split it into calls under 60 s only when optimising ran out. Never "
    "hand it to kuhy. Proof: the live check runs it timed and writes the seconds."
)
STRAY = "work.stray"  # stray edits a deploy stashed in kuhy's checkout, origin lacking them (T2514)
STRAY_GOAL = (
    "Decide whether this stray work belongs in the repo: a board run left it uncommitted in kuhy's checkout, "
    "a deploy stashed it, and origin does not hold it. Read it in your worktree (Detail names the stash and "
    "the patch), land what is useful (apply it, test, ship) and drop the rest. Never pop or drop the stash "
    "in kuhy's checkout. Do not ask kuhy anything; take recommended answers."
)
STRAY_DONE = (
    "done: the useful part is shipped and deployed, or this part says why none of it is worth landing."
)
SEEN = re.compile(r"^[ \t]*Seen:")


@dataclass(frozen=True)
class Found:
    """An open ticket on the board: the card that holds it, its note, its heading and its text."""

    card: str
    note: str
    title: str
    text: str


def _flat(text: str) -> str:
    """One line, no backticks: a stray fence or `## ` in an error message must not split the note."""
    return " ".join(text.replace("`", "'").split())


def error_line(record: AppError) -> str:
    """Return the `Error:` line: kind and the whole flattened message, what one issue looks like (T2570)."""
    return f"Error: {record.kind}: {_flat(record.message)}"


def title(record: AppError) -> str:
    """`Fix <app>: <kind> <message>` plus the short signature, so two errors never share a title."""
    return (
        f"Fix {record.app}: {record.kind} {_flat(record.message)[:MESSAGE_IN_TITLE]} [{record.signature[:8]}]"
    )


def seen(record: AppError) -> str:
    """Return the `Seen:` line: how often, first and last time."""
    return f"Seen: {record.count}x, first {record.first_seen}, last {record.last_seen}"


def _regression(record: AppError, fixed_build: int) -> str:
    if record.build > 0 and fixed_build > 0:
        return f"Regression: seen again on build {record.build}; the fix shipped in build {fixed_build}."
    return "Regression: seen again, after the fix reached the phone."


def body(record: AppError, *, regression: int | None = None) -> str:
    """Return the part's text: goal, done line, what is known of the error, the Seen and signature lines."""
    how = [PERF] if record.kind.startswith("perf.") else []
    goal = [STRAY_GOAL, STRAY_DONE] if record.kind == STRAY else [GOAL, DONE]
    lines = [*goal, *how, "", error_line(record)]
    for label, value in (("Top frame", record.top_frame), ("Detail", record.detail)):
        if value:
            lines.append(f"{label}: {_flat(value)}")
    if record.build > 0 or record.version_name:
        lines.append(f"Build: {record.build if record.build > 0 else 'unknown'}" + _version(record))
    if regression is not None:
        lines.append(_regression(record, regression))
    return "\n".join([*lines, seen(record), f"Error-Signature: {record.key}"])


def _version(record: AppError) -> str:
    return f" ({_flat(record.version_name)})" if record.version_name else ""


def find(cards: Iterable[CardTask], key: str) -> Found | None:
    """Return the open part that carries `key`, looking at every part of every open card.

    A Done card keeps the text of what it shipped (`ClosedNotes`): it is no ticket, so it never matches.
    """
    for card in cards:
        if card.status in ("done", "abandoned"):
            continue
        held = [(p.note_id, p.title, p.body) for p in card.parts] or [
            (card.item.note_id, card.title, card.body)
        ]
        for note, name, text in held:
            if key in signatures(text):
                return Found(card.id, note, name, text)
    return None


def _spot(lines: list[str], key: str) -> tuple[int, int] | None:
    """Return (the signature line's index, the first line index of its block) in the open part of `key`.

    A part may hold several signatures (a merged card, one issue seen under two signatures): a block starts
    after the previous signature line or `### ` heading, so each signature keeps its own `Seen:` line (T2571).
    A closed section (a folded twin) is never the one refreshed.
    """
    for part in sections("\n".join(lines)):
        start = part.heading + 1
        for at, line in enumerate(part.lines, part.heading + 1):
            if (hit := SIGNATURE.match(line)) is not None and not part.done:
                if hit.group(1) == key:
                    return at, start
                start = at + 1
            elif line.startswith("### "):
                start = at + 1
    return None


def refresh(note: str, key: str, seen_text: str) -> str | None:
    """Return the note with the part's `Seen:` line set to `seen_text`; None when it is set (or no part)."""
    lines = note.split("\n")
    spot = _spot(lines, key)
    if spot is None:
        return None
    sig, first = spot
    at = next((i for i in range(first, sig) if SEEN.match(lines[i])), None)
    if at is None:
        lines.insert(sig, seen_text)
    elif lines[at] == seen_text:
        return None
    else:
        lines[at] = seen_text
    return "\n".join(lines)
