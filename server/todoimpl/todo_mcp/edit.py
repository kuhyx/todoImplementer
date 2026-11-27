"""Rewrite one part's own text in its note (856c0f0a): a section's heading and lines, or a section-less note.

Checked by reading the result back, not by guessing at bad input: the rewritten body must split into the
same sections, every other one unchanged and the edited one holding exactly the new title and text. That one
check refuses a new `## ` line, an unclosed fence, a `[x] ` done marker and a title that is no heading.
"""

from __future__ import annotations

from todoimpl.todo_mcp.items import Section, sections
from todoimpl.umbrella.note import is_umbrella


class EditError(ValueError):
    """The new title or text would change more of the note than the one part."""


def _shape(found: list[Section]) -> list[tuple[str, bool, str]]:
    return [(part.title, part.done, "\n".join(part.lines).strip()) for part in found]


def rewrite_section(body: str, index: int, title: str, text: str) -> str:
    """Return `body` with section `index` titled `title` and holding `text`; raise EditError otherwise."""
    before = sections(body)
    part = before[index]
    lines = body.split("\n")
    end = part.heading + 1 + len(part.lines)
    gap = next((n for n, line in enumerate(reversed(part.lines)) if line.strip()), len(part.lines))
    text = text.strip()
    new = [f"## {title}", *([text] if text else []), *[""] * gap]
    result = "\n".join([*lines[: part.heading], *new, *lines[end:]])
    want = _shape(before)
    want[index] = (title, False, text)
    if "\n" in title or _shape(sections(result)) != want:  # same sections: same header too
        msg = "the new title or text would change other parts of the note"
        raise EditError(msg)
    return result


def whole_note(text: str) -> str:
    """Return the new body of a section-less note; raise EditError when it would gain sections."""
    text = text.strip()
    if sections(text) or is_umbrella(text):
        msg = "the new text would split the note into sections"
        raise EditError(msg)
    return text
