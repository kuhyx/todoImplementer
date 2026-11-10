"""Which session a turn resumes: the same one, a fresh one after 1 h idle, or the killed one."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from .stream import StreamParser

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

# The prompt cache expires after an hour; past that a resume re-reads the whole transcript at full price.
IDLE_FRESH_SEC = 3600.0
Situation = Literal["", "killed", "idle", "resume"]


@dataclass(frozen=True)
class Prior:
    """The session a role used last; `lost` describes a killed turn's last activity."""

    session_id: str | None
    last_turn_end: float
    lost: str | None


@dataclass(frozen=True)
class TurnPlan:
    """`resume` None: a new session. `situation` picks the prompt: killed, idle or "resume" (live)."""

    resume: str | None
    situation: Situation


def plan_turn(prior: Prior | None, *, now: float) -> TurnPlan:  # noqa: D103
    if prior is None or prior.session_id is None:
        return TurnPlan(None, "killed" if prior is not None and prior.lost else "")
    if now - prior.last_turn_end > IDLE_FRESH_SEC:
        return TurnPlan(None, "idle")
    return TurnPlan(prior.session_id, "killed" if prior.lost else "resume")


def prior_from(entry: Mapping[str, Any] | None) -> Prior | None:  # noqa: D103
    sid = entry.get("session_id") if entry else None
    if not isinstance(sid, str):
        return None
    assert entry is not None  # noqa: S101 - sid came from it
    return Prior(sid, float(entry.get("last_turn_end", 0.0)), None)


def lost_prior(stream: Path, entry: Mapping[str, Any] | None) -> Prior:
    """Read a killed turn's stream: its session (else the role's last) and its last activity."""
    parser = StreamParser()
    last = "nothing was recorded"
    for line in stream.read_text(encoding="utf-8", errors="replace").splitlines():
        for act in parser.feed(line):
            if act.kind != "system":
                last = f"{act.kind} {act.tool}: {act.text}" if act.tool else f"{act.kind}: {act.text}"
    known = prior_from(entry)
    sid = parser.result.session_id or (known.session_id if known else None)
    return Prior(sid, stream.stat().st_mtime, last)


def handoff_summary(
    run_dir: Path,
    last_reply: str,
    self_check: Sequence[Mapping[str, Any]] = (),
    live_report: str = "",
    *,
    with_plan: bool = True,
) -> str:
    """Built from files, never by a model: plan.md, the self-check, the live-check tail and the last reply."""
    plan = run_dir / "plan.md"
    parts = []
    if with_plan and plan.exists():
        parts.append("Plan (plan.md):\n" + plan.read_text(encoding="utf-8")[:3000])
    if self_check:
        rows = (f"{r['criterion']}: {'done' if r['done'] else 'not done'} - {r['note']}" for r in self_check)
        parts.append("Self-check:\n" + "\n".join(rows))
    if live_report.strip():
        parts.append("Live check report (tail):\n" + live_report.strip()[-1500:])
    if last_reply:
        parts.append("Last reply:\n" + last_reply[-1500:])
    return "\n\n".join(parts) or "No plan or reply was recorded yet."
