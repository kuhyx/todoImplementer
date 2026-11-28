"""The deterministic note check that gates Start (no LLM): a done condition and a sane size.

See DOCS-priority.md.

The repo half of the check is `norepo.is_yours` plus the board's `repo_missing`: a note with a repo must have
a checkout; a note with no repo is routed to triage on Start (DOCS-triage.md), so it passes here.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.errors.marks import own
from todoimpl.triage.label import RESEARCH
from todoimpl.umbrella.note import is_umbrella

if TYPE_CHECKING:
    from .types import TaskLike

MAX_BODY = 20_000  # characters of the card body (a repo card's body is its open parts joined)
MAX_PARTS = 30  # open parts of one repo card
# A done condition: `Done:`, `Done when`, `Done means`, `Success:`, `Verify:`, `Acceptance:` at a line start
# (bullet and bold allowed), or a checkbox line `- [ ] <step>`.
DONE_LINE = re.compile(
    r"^[ \t]*(?:[-*>][ \t]*)*(?:\*\*)?"
    r"(?:done(?:[ \t]+(?:when|means)\b|(?:\*\*)?[ \t]*:)"
    r"|(?:success|acceptance)(?:[ \t]+criteria)?(?:\*\*)?[ \t]*:"
    r"|verify(?:\*\*)?[ \t]*:"
    r"|[-*][ \t]\[[ xX]\][ \t]+\S)",
    re.IGNORECASE | re.MULTILINE,
)
NO_DONE = "note has no done line (Done:, Success:, Verify: or - [ ])"


def has_done_line(text: str) -> bool:
    """Say whether the text states how to tell the work is done."""
    return DONE_LINE.search(text or "") is not None


def machine_made(task: TaskLike) -> bool:
    """Say whether the board or an app wrote the card: it is exempt from the done-line rule.

    Exempt: the board's own and an app's notes (`created_by` claude), an umbrella (its children carry the
    done conditions), error tickets and token optimizations (`Error-Signature:` / `Reset-Key:` lines), and a
    repo-less note triaged as `research` (a reading list has no done condition; its session makes actions).
    """
    parts = [p.body for p in getattr(task, "parts", ())]
    return (
        task.created_by == "claude"
        or is_umbrella(task.body)
        or own("\n".join([task.body or "", *parts]))
        or getattr(task, "triage", None) == RESEARCH
    )


def note_block(task: TaskLike) -> str | None:
    """Return why the note cannot start (size, done line), None when it passes.

    Size applies to every card; the done-line rule only to notes kuhy wrote. A done_check on the card or on
    one of its open parts counts as a done condition.
    """
    work = [p for p in getattr(task, "parts", ()) if p.actionable]
    if len(task.body or "") > MAX_BODY:
        return f"note is over {MAX_BODY} characters: split it"
    if len(work) > MAX_PARTS:
        return f"card has over {MAX_PARTS} open parts: split it"
    if machine_made(task) or task.done_check or any(p.done_check for p in work):
        return None
    texts = [task.body or "", *(p.body for p in work)]
    return None if any(has_done_line(text) for text in texts) else NO_DONE
