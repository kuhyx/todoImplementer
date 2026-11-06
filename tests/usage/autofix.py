"""Builders for fixture run dirs the autonomy metrics read (state, turn results, streams, records)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from todoimpl.board.state import RunState, SpecQuestion, save


def noon(month: int, day: int) -> float:
    """Local noon of a 2026 day: far from any week boundary, so the timezone cannot flip the ISO week."""
    return datetime(2026, month, day, 12, 0).timestamp()  # noqa: DTZ001


WEEK45 = noon(11, 4)  # Wed 2026-W45
WEEK46 = noon(11, 11)  # Wed 2026-W46

CRITERIA_PLAN = "# Plan\n\n## Acceptance criteria\n- first thing\n- second thing\n- third thing\n"


def make_run(root: Path, card: str, stage: str = "gate", **fields: Any) -> Path:
    """Write `<root>/<card>/state.json`; `answers` marks spec questions answered, `extra` is state.extra."""
    answered, asked = int(fields.pop("answers", 0)), int(fields.pop("questions", 0))
    questions = [
        SpecQuestion(f"Q{n}", f"title {n}", answer="yes" if n <= answered else None)
        for n in range(1, asked + 1)
    ]
    state = RunState(task_id=card, stage=stage, spec_questions=questions, **fields)
    directory = root / card
    save(directory, state)
    return directory


def tail(text: str | None, tag: str) -> str:
    """Return a reply that ends with a status tag line."""
    return f"{text or 'work'}\n\n{tag}"


def add_turn(directory: Path, role: str, epoch: float, tag: str, reply: str | None = None) -> None:
    """Write a turn's result.json and a stream whose last event is the result carrying `reply`."""
    base = directory / f"{role}-{epoch:.3f}"
    base.with_suffix(".result.json").write_text(json.dumps({"tag": tag, "finished": True}))
    events = [{"type": "assistant"}, {"type": "result", "result": reply if reply is not None else tag}]
    base.with_suffix(".stream.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")


def add_interventions(directory: Path, rows: list[tuple[float, str]]) -> None:
    """Write the interventions.jsonl record (a run started after the record existed)."""
    lines = [json.dumps({"at": at, "kind": kind}) for at, kind in rows]
    (directory / "interventions.jsonl").write_text("\n".join(lines) + "\n")


def add_live_report(directory: Path, report: str, plan: str = CRITERIA_PLAN, at: float = WEEK45) -> None:
    """Write live_check.md (mtime `at`) and plan.md; the state's live_check.report_md is set by the caller."""
    (directory / "plan.md").write_text(plan)
    (directory / "live_check.md").write_text(report)
    os.utime(directory / "live_check.md", (at, at))
