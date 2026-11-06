"""How much of the work ran without kuhy: four metrics over all run dirs and per ISO week.

Higher is better for `done_unassisted`; lower is better (target 0) for the other three.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from todoimpl.board.parse import StateError
from todoimpl.board.state import RunState, load
from todoimpl.runner.live import verdict
from todoimpl.runner.parsing import parse_criteria, parse_live
from todoimpl.usage.asks import is_permission_ask, turns
from todoimpl.usage.interventions import UNCOUNTED, legacy, recorded

if TYPE_CHECKING:
    from pathlib import Path

REACHED_GATE = ("gate", "shipping", "shipped")
SETTLED = ("checks", *REACHED_GATE)
COUNTS = ("permission_asks", "questions_asked", "criteria_failed")


def week_of(epoch: float) -> str:
    """ISO week label such as `2026-W45`, in local time."""
    year, week, _ = datetime.fromtimestamp(epoch).astimezone().isocalendar()
    return f"{year}-W{week:02d}"


@dataclass
class Tally:
    """Weekly numbers summed over every card."""

    finished: Counter[str] = field(default_factory=Counter)
    unassisted: Counter[str] = field(default_factory=Counter)
    counts: dict[str, Counter[str]] = field(default_factory=lambda: {name: Counter() for name in COUNTS})
    cards: int = 0
    backfilled: int = 0

    def add(self, name: str, epoch: float, amount: int) -> None:
        """Add `amount` to the metric's week (an amount of 0 still opens the week)."""
        self.counts[name][week_of(epoch)] += amount


def _finished_at(state: RunState) -> float | None:
    gate_failed = state.stage == "failed" and state.extra.get("failed_stage") in ("gate", "shipping")
    if state.stage not in REACHED_GATE and not gate_failed:
        return None
    pushed = (state.ship or {}).get("pushed_at")
    return float(pushed) if isinstance(pushed, int | float) else state.updated


def _criteria(directory: Path, state: RunState) -> tuple[float, int] | None:
    """(epoch, open + deferred criteria) of the card's live check, None while it is not settled."""
    report_file = directory / "live_check.md"
    at = report_file.stat().st_mtime if report_file.exists() else state.updated
    partial = state.extra.get("partial")
    if isinstance(partial, dict):
        return at, len(partial.get("open", [])) + len(partial.get("deferred", []))
    report = (state.live_check or {}).get("report_md")
    failed_live = state.stage == "failed" and state.extra.get("failed_stage") == "live_check"
    if not isinstance(report, str) or not (state.stage in SETTLED or failed_live):
        return None
    plan = directory / "plan.md"
    criteria = parse_criteria(plan.read_text(encoding="utf-8", errors="replace") if plan.exists() else "")
    found = verdict(parse_live(report), criteria)
    return at, len(found.open) + len(found.deferred)


def _tally_card(tally: Tally, directory: Path, state: RunState) -> None:
    tally.cards += 1
    rows, found = recorded(directory), turns(directory)
    traces = False
    if rows is None:
        tally.backfilled += 1
        rows, traces = legacy(directory, state), any(turn.tag in ("Q", "A") for turn in found)
    assisted = traces or any(kind not in UNCOUNTED for _, kind in rows)
    if (finished_at := _finished_at(state)) is not None:
        tally.finished[week_of(finished_at)] += 1
        tally.unassisted[week_of(finished_at)] += 0 if assisted else 1
    for turn in found:
        if turn.tag == "A" and turn.ask is not None and is_permission_ask(turn.ask):
            tally.add("permission_asks", turn.at, 1)
        if turn.tag == "Q" and turn.role != "spec":
            tally.add("questions_asked", turn.at, turn.questions)
    if state.spec_questions:
        tally.add("questions_asked", state.started_at or state.updated, len(state.spec_questions))
    if (live := _criteria(directory, state)) is not None:
        tally.add("criteria_failed", *live)


def _weekly(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"week": week, "value": counter[week]} for week in sorted(counter)]


def autonomy_summary(root: Path) -> dict[str, Any]:
    """Build the `autonomy` block of GET /api/usage (see contracts/autonomy.schema.json)."""
    tally = Tally()
    for directory in sorted(root.glob("*/")):
        try:
            state = load(directory)
        except StateError:
            continue
        if state is not None:
            _tally_card(tally, directory, state)
    done, finished = sum(tally.unassisted.values()), sum(tally.finished.values())
    out: dict[str, Any] = {
        "done_unassisted": {
            "value": round(100 * done / finished, 1) if finished else None,
            "count": done,
            "finished": finished,
            "target": 100,
            "direction": "up",
            "weekly": [
                {
                    "week": week,
                    "value": round(100 * tally.unassisted[week] / tally.finished[week], 1),
                    "count": tally.unassisted[week],
                    "finished": tally.finished[week],
                }
                for week in sorted(tally.finished)
            ],
        },
    }
    for name in COUNTS:
        out[name] = {
            "value": sum(tally.counts[name].values()),
            "target": 0,
            "direction": "down",
            "weekly": _weekly(tally.counts[name]),
        }
    return {**out, "cards": tally.cards, "backfilled": tally.backfilled}
