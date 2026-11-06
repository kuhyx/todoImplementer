"""Parsers for the reply formats the prompts ask for: question cards, criteria, self and live checks."""

from __future__ import annotations

import re

from todoimpl.board.state import SpecQuestion

QUESTION = re.compile(
    r"^\s*❓️?\s*\*\*(Q\d+)\*\*\s*(?:[-:\u2013\u2014]\s*)?(?:\*\*(.+?)\*\*\s*:?\s*)?(.*?)\s*$"
)
RECOMMENDATION = re.compile(r"^\s*➡️?\s*(.*?)\s*$")
CRITERIA_HEADING = re.compile(r"^#+\s*acceptance criteria\b", re.IGNORECASE)
BULLET = re.compile(r"^\s*(?:[-*]|\d+[.)]|C\d+[.:)])\s+(.*\S)")
SELF_CHECK = re.compile(
    r"^\s*(?:[-*]\s*)?`?(C\d+|.{2,}?)`?:\s*`?(done|not done)\b`?[\s:,.;()-]*(.*?)\)?`?\s*$", re.IGNORECASE
)
LIVE = re.compile(
    r"^\s*(?:[-*]\s*)?\[([ xX~])\]\s*(?:\*{0,2}(C\d+)\*{0,2}\s*[:.)\u2013\u2014-]?\s*\*{0,2}\s*)?(.*?)\s*$"
)


def parse_questions(text: str) -> list[SpecQuestion]:
    """`❓ **Qn** - **title**: body` cards, each closed by a `➡️ recommendation` line; a repeated id wins."""
    cards: dict[str, SpecQuestion] = {}
    current: SpecQuestion | None = None
    for line in text.splitlines():
        if found := QUESTION.match(line):
            qid, title, rest = found.groups()
            current = SpecQuestion(qid, (title or rest or qid).strip(), rest if title else "")
            cards[qid] = current
        elif current is not None and (rec := RECOMMENDATION.match(line)):
            current.recommendation = rec.group(1)
            current = None
        elif current is not None and line.strip():
            current.body = f"{current.body}\n{line.strip()}".strip()
    return list(cards.values())


def parse_criteria(plan: str) -> list[str]:
    """Bullets under the `## Acceptance criteria` heading, up to the next heading."""
    found: list[str] = []
    inside = False
    for line in plan.splitlines():
        if line.lstrip().startswith("#"):
            inside = bool(CRITERIA_HEADING.match(line.strip()))
        elif inside and (bullet := BULLET.match(line)):
            found.append(bullet.group(1))
    return found


def parse_self_check(text: str) -> list[dict[str, object]]:
    """`Cn: done` / `Cn: not done` lines plus their evidence (state.json `self_check`)."""
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        if found := SELF_CHECK.match(line):
            criterion, verdict, note = found.groups()
            rows.append({"criterion": criterion.strip("` "), "done": verdict.lower() == "done", "note": note})
    return rows


def parse_live(text: str) -> list[dict[str, object]]:
    """`- [x] C1: what I did -> what I saw` rows of live_check.md.

    `[ ]` failed or not tried; `[~]` deferred (after ship, needs phone); no dash, `**C1**`, no colon all pass.
    """
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        if found := LIVE.match(line):
            mark, cid, note = found.groups()
            rows.append(
                {"criterion": cid or note, "done": mark in "xX", "note": note, "deferred": mark == "~"}
            )
    return rows
