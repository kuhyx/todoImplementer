"""The manager's verdict lines and the width rule. The server adjudicates; the LLM only reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .note import Child

NO_LINE = "the manager gave no verdict line"
_LINE = re.compile(
    r"^[ \t>*_#-]*CHILD[ \t]+(?P<repo>kuhyx/[\w.-]+)(?:[ \t]*\((?P<key>[A-Za-z0-9]{8})\))?[ \t]*:[ \t]*"
    r"(?P<kind>clean|fixed|escalate)\b[ \t*_]*(?P<detail>.*?)[ \t*_]*$",
    re.MULTILINE,
)
_WORST = {"clean": 0, "fixed": 1, "escalate": 2}


@dataclass(frozen=True)
class Verdict:
    """One child's line: `clean` (worker needed no help), `fixed <what>` or `escalate <reason>`."""

    kind: str
    detail: str


def parse_verdicts(text: str, kids: Sequence[Child]) -> dict[str, Verdict]:
    """Return a verdict per child id; a child without a line escalates, a repeated line keeps the worst."""
    got: dict[str, Verdict] = {}
    keys = {c.cid for c in kids}
    for match in _LINE.finditer(text):
        said = match.group("key")
        same = [c.cid for c in kids if c.repo == match.group("repo") and said in (None, c.key)]
        key = next((k for k in same if k not in got), same[0] if same else None)
        if key not in keys:
            continue
        found = Verdict(match.group("kind"), match.group("detail"))
        if key not in got or _WORST[found.kind] > _WORST[got[key].kind]:
            got[str(key)] = found
    return {c.cid: got.get(c.cid, Verdict("escalate", NO_LINE)) for c in kids}


def all_escalate(kids: Sequence[Child], reason: str) -> dict[str, Verdict]:
    """Return an escalation for every child: the manager's turn failed."""
    return {c.cid: Verdict("escalate", reason) for c in kids}


def ok(verdict: Verdict, *, free: bool, checks: bool | None) -> bool:
    """Return True when a child counts toward doubling: clean, done by a free worker, checks green."""
    return verdict.kind == "clean" and free and checks is True


def next_width(width: int, oks: Sequence[bool]) -> int:
    """Return the next round's width: doubled when every child of the round was ok, else unchanged."""
    return width * 2 if oks and all(oks) else width


def take(pending: Sequence[str], width: int) -> list[str]:
    """Return the next `width` children, in order."""
    return list(pending[:width])
