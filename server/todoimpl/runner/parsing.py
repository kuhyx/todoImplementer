"""Parsers for the reply formats the prompts ask for: question cards, criteria, self and live checks."""

from __future__ import annotations

import re

from todoimpl.board.state import SpecQuestion

QUESTION = re.compile(
    r"^\s*❓️?\s*\*\*(Q\d+)\*\*\s*(?:[-:\u2013\u2014]\s*)?(?:\*\*(.+?)\*\*\s*:?\s*)?(.*?)\s*$"
)
# The same card with id and title in one bold: `❓ **Q1 - title**: body` (T2524).
QUESTION_JOINED = re.compile(r"^\s*❓️?\s*\*\*(Q\d+)\s*[-:\u2013\u2014]\s*(.+?)\*\*\s*:?\s*(.*?)\s*$")
RECOMMENDATION = re.compile(r"^\s*➡️?\s*(.*?)\s*$")
CRITERIA_HEADING = re.compile(r"^#+\s*acceptance criteria\b", re.IGNORECASE)
# One parser for a plan criterion's head, shared by approval.py and crithash.py (T2523). Plans write the id
# as `C1.`, `C1 [part key]:` (T2460), `**C1**`, or bare `C1` right before the `(kuhy)` mark, with or without
# a list bullet in front; the mark follows the id or the part key, and anywhere else is no mark.
ID = r"C\d+(?:\s*\[[\w-]+\])?"
BULLET = re.compile(rf"^\s*(?:[-*]|\d+[.)]|{ID}[.:)]|\*\*{ID}[.:)]?\*\*[.:)]?|{ID}(?=\s+\(kuhy\)))\s+(.*\S)")
HEAD = re.compile(
    rf"^\s*(?:(?:[-*]|\d+[.)])\s+)?(?:\*{{0,2}}\b{ID}[.:)]?\*{{0,2}}[.:)]?\s+)?(?P<mark>\(kuhy\)\s*)?",
    re.IGNORECASE,
)
SELF_CHECK = re.compile(
    r"^\s*(?:[-*]\s*)?`?(C\d+|.{2,}?)`?:\s*`?(done|not done)\b`?[\s:,.;()-]*(.*?)\)?`?\s*$", re.IGNORECASE
)
LIVE = re.compile(
    r"^\s*(?:[-*]\s*)?\[([ xX~])\]\s*(?:\*{0,2}(C\d+)\*{0,2}(?:\s*\[([\w-]+)\])?\*{0,2}\s*[:.)\u2013\u2014-]?"
    r"\s*\*{0,2}\s*)?(.*?)\s*$"
)

KEYED_ROW = re.compile(r"^live C\d+ \[([\w-]+)\]:")  # a row of shipstage.live_summary naming its part


def parse_questions(text: str) -> list[SpecQuestion]:
    """`❓ **Qn** - **title**: body` cards, each closed by a `➡️ recommendation` line; a repeated id wins."""
    cards: dict[str, SpecQuestion] = {}
    current: SpecQuestion | None = None
    for line in text.splitlines():
        if found := QUESTION.match(line) or QUESTION_JOINED.match(line):
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


def _head(criterion: str) -> re.Match[str]:
    return next(HEAD.finditer(criterion))  # every part of HEAD is optional: the first match is at 0


def is_kuhy(criterion: str) -> bool:
    """Return True when the criterion's head carries the `(kuhy)` mark: kuhy's to tick (T2362)."""
    return _head(criterion).group("mark") is not None


def words(criterion: str) -> str:
    """Return the criterion's text after its head (bullet, id, part key, mark), on single spaces."""
    return " ".join(criterion[_head(criterion).end() :].split())


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
    `C1 [<part key>]:` names the part of a repo card the row checks (`part`, None when absent; T2460).
    """
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        if found := LIVE.match(line):
            mark, cid, part, note = found.groups()
            done, deferred = mark in "xX", mark == "~"
            row = {"criterion": cid or note, "part": part, "done": done, "note": note, "deferred": deferred}
            rows.append(row)
    return rows


def for_part(evidence: str, key: str) -> str:
    """Drop the `live Cn [<other part>]:` lines from close evidence, so a note gets its own rows (T2460)."""
    lines = evidence.split("\n")
    return "\n".join(ln for ln in lines if not (row := KEYED_ROW.match(ln)) or row.group(1) == key)
