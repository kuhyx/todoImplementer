"""What Claude asked kuhy, read from a run's finished turns (`<role>-<epoch>.result.json` plus its stream).

Only A: turns and non-spec Q: turns need their reply, read from the stream's tail, never the whole stream.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.runner.parsing import parse_questions

if TYPE_CHECKING:
    from pathlib import Path

TAIL_BYTES = 262_144
RESULT_SUFFIX = ".result.json"
PERMISSION = re.compile(
    r"\bpermissions?\b|\bapprov\w*|\ballow(?:s|ed|list)?\b|\bgrant(?:ed|s)?\b|\bsudo\b|`!\s", re.IGNORECASE
)


@dataclass(frozen=True)
class Turn:
    """One finished turn: role, start epoch, status tag, the A:/Q: line and the number of questions."""

    role: str
    at: float
    tag: str | None
    ask: str | None
    questions: int


def is_permission_ask(text: str) -> bool:
    """Return True when an `A:` line asks for a permission or approval, not a physical step."""
    return PERMISSION.search(text) is not None


def last_result_text(stream: Path) -> str:
    """Return the text of the last result event in the stream's tail, empty when there is none."""
    try:
        with stream.open("rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - TAIL_BYTES))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    for line in reversed(tail.splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            return str(event.get("result", ""))
    return ""


def _tag(result: Path) -> str | None:
    try:
        data = json.loads(result.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    tag = data.get("tag") if isinstance(data, dict) else None
    return tag if isinstance(tag, str) else None


def turns(run_dir: Path) -> list[Turn]:
    """Every finished turn of a run, oldest first; files that do not look like a turn are skipped."""
    from todoimpl.runner.stream import last_tag_line  # noqa: PLC0415 - runner.stream -> usage.limits cycle

    out: list[Turn] = []
    for result in sorted(run_dir.glob(f"*{RESULT_SUFFIX}")):
        name = result.name.removesuffix(RESULT_SUFFIX)
        role, _, stamp = name.rpartition("-")
        try:
            at = float(stamp)
        except ValueError:
            continue
        tag = _tag(result)
        ask, count = None, 0
        if tag == "A" or (tag == "Q" and role != "spec"):
            text = last_result_text(run_dir / f"{name}.stream.jsonl")
            found = last_tag_line(text)
            ask = found[1] if found else None
            count = (len(parse_questions(text)) or 1) if tag == "Q" else 0
        out.append(Turn(role, at, tag, ask, count))
    return out
