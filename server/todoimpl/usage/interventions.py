"""kuhy's own clicks on a card, one append-only line each in `<run dir>/interventions.jsonl`.

Ship is never recorded (it is the intended gate). Cards that predate the record are rebuilt by `legacy`;
restarts, cancels and `go` clicks left no trace before, so those cannot be backfilled.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

log = logging.getLogger("todoimpl.usage")
FILE = "interventions.jsonl"
UNCOUNTED = frozenset({"start", "ship"})


def record(root: Path, card: str, kind: str, at: float) -> None:
    """Append one intervention; a failing disk must not fail an action that already worked."""
    path = root / card / FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            out.write(json.dumps({"at": at, "kind": kind}) + "\n")
    except OSError:
        log.exception("cannot record the %s intervention for %s", kind, card)


def _lines(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def recorded(run_dir: Path) -> list[tuple[float, str]] | None:
    """Return the record as (epoch, kind), None when the run has no record file."""
    if not (run_dir / FILE).exists():
        return None
    return [
        (float(row["at"]), row["kind"])
        for row in _lines(run_dir / FILE)
        if isinstance(row.get("at"), int | float) and isinstance(row.get("kind"), str)
    ]


def legacy(run_dir: Path, state: RunState) -> list[tuple[float, str]]:
    """Interventions a pre-record card still shows: Send notes, answers, Spec OK, credits."""
    seen = state.started_at or state.updated
    rows = [
        (float(row["at"]) if isinstance(row.get("at"), int | float) else seen, "send")
        for row in _lines(run_dir / "events.jsonl")
        if row.get("type") == "activity" and row.get("kind") == "user"
    ]
    if any(q.answer is not None for q in state.spec_questions):
        rows.append((seen, "spec_answers"))
    if state.extra.get("spec_ok"):
        rows.append((seen, "spec_ok"))
    if state.using_credits:
        rows.append((seen, "credits"))
    return rows
