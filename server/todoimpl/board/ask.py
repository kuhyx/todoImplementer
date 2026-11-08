"""The concrete ask of a Needs-you card, derived from the run's last reply (no LLM, no guessing)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.runner.parsing import parse_questions
from todoimpl.runner.stream import last_tag_match, tag_letter

if TYPE_CHECKING:
    from .state import RunState

NO_REPLY = "Claude ended without a reply: open Activity"
MAX_ASK = 200
MAX_TAGGED = 300
NOTE_PREFIX = re.compile(r"^N\s*:\s*")


def _clip(text: str, limit: int = MAX_ASK) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _paragraphs(lines: list[str]) -> list[str]:
    """Blank-line separated paragraphs, each joined on single spaces."""
    out: list[str] = [""]
    for line in lines:
        if line.strip():
            out[-1] = f"{out[-1]} {line.strip()}".strip()
        elif out[-1]:
            out.append("")
    return [p for p in out if p]


def _first(lines: list[str]) -> str:
    found = _paragraphs(lines)
    return NOTE_PREFIX.sub("", found[0]) if found else ""


def _last(lines: list[str]) -> str:
    found = _paragraphs(lines)
    return _clip(found[-1]) if found else ""


def _question_round(run: RunState, reply: str) -> str | None:
    """`<n> questions: <first title>` from the open cards, else from the cards in the reply."""
    cards = run.open_questions() or parse_questions(reply)
    if not cards:
        return None
    return f"{len(cards)} question{'' if len(cards) == 1 else 's'}: {cards[0].title}"


def _tagged(run: RunState, reply: str, tag: re.Match[str]) -> str:
    line_end = reply.find("\n", tag.end())
    rest = reply[tag.end() : None if line_end < 0 else line_end].strip(" \t*_`")
    after = [] if line_end < 0 else reply[line_end + 1 :].splitlines()
    if rest:
        more = _first(after) if rest.endswith(":") else ""
        return _clip(f"{rest} {more}", MAX_TAGGED) if more else rest
    if run.last_tag == "Q" and (asked := _question_round(run, reply)):
        return asked
    return _first(after) or _last(reply[: tag.start()].splitlines())


def concrete_ask(run: RunState) -> str | None:
    """Return what the last reply asks of kuhy, None only when the run has no reply text at all.

    That is the `A:`/`Q:` text, the `N:` line or question round after an empty tag, else the last paragraph.
    """
    reply = str(run.extra.get("last_reply", "")).strip()
    if not reply:
        return None
    tag = last_tag_match(reply)
    if tag is not None and run.last_tag in (None, tag_letter(tag)):
        return _tagged(run, reply, tag) or None
    if run.last_tag == "Q" and (asked := _question_round(run, reply)):
        return asked
    return _last(reply.splitlines()) or None
