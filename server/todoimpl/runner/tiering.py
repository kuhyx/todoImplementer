"""The cheap tier inside a drive (DOCS-tiers.md): pick the model and prompt addendum, escalate at most once.

State, all in `extra` (state.schema.json): `tier` (`cheap` | `normal`, decided at the first implement-role
turn), `free_models` (the server's verdict before the latest implement turn), `escalated`, `escalate_reason`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.prompts import coach
from todoimpl.prompts import tier as texts
from todoimpl.umbrella import issues

from . import freegate, freeworker, tier

if TYPE_CHECKING:
    from .pipeline import Driver
    from .stream import TurnResult

IMPLEMENT = "implement"  # the role (and the stage) a cheap note changes


@dataclass(frozen=True)
class Turn:
    """What a turn changes for its tier; None = the default; `note` is an addendum."""

    model: str | None = None
    note: str = ""
    effort: str | None = None


def _cheap(d: Driver) -> bool:
    return d.state.extra.get("tier") == "cheap"


def plan_turn(d: Driver, role: str) -> Turn:
    """Decide the model and addendum of one turn; an implement turn first takes the free-models verdict."""
    st = d.state
    if role != IMPLEMENT:
        return Turn()
    if st.extra.get("research"):  # the role default like every card turn (T2476), no free workers
        return Turn()
    # `tier` stays across a repo card's cycles; a cycle holding an error ticket is never cheap (T2445)
    if "tier" not in st.extra or tier.TICKET_LINE.search(d.item.body):
        st.extra["tier"] = "cheap" if tier.is_cheap(d.item.title, d.item.body, d.item.parts) else "normal"
    if not _cheap(d):
        return Turn()
    if st.extra.get("escalated"):
        note = texts.escalated(str(st.extra.get("escalate_reason", "")))
        return Turn(None, note, tier.ESCALATED_EFFORT)
    verdict = freegate.check(Path(str(st.worktree)))
    st.extra["free_models"] = verdict.allowed
    if verdict.allowed:
        d.activity("tier cheap: opus manages free models")
        wt, repo = Path(str(st.worktree)), d.item.repo or ""
        rules = coach.TEXTGATE_RULES if coach.is_textgate(d.item.title, d.item.body) else ""
        note = texts.manager(wt, d.ctx.run_dir, freeworker.command(), repo, rules)
        return Turn(tier.MANAGER_MODEL, note, tier.MANAGER_EFFORT)
    d.activity(f"tier cheap: opus alone, {verdict.why}")
    if verdict.detail:  # a gateway failure the server saw itself goes to the same issue log
        issues.append(
            d.ctx.run_dir, d.ctx.now(), d.item.repo or "", "start", verdict.detail, "opus works alone"
        )
    return Turn(tier.MANAGER_MODEL, texts.alone(verdict.why), tier.MANAGER_EFFORT)


def escalate(d: Driver, reason: str) -> None:
    """Record the one escalation of the run; the next implement-role turn runs at a higher effort."""
    d.state.extra.update(escalated=True, escalate_reason=reason)
    d.activity(f"tier escalated to higher effort: {reason}")


def gave_up(d: Driver, res: TurnResult) -> bool:
    """Return True when a cheap implement turn ended with `ESCALATE:` and the run has not escalated yet."""
    st = d.state
    if not _cheap(d) or st.extra.get("escalated") or (reason := tier.escalation(res.text)) is None:
        return False
    escalate(d, reason)
    return True


def failed(d: Driver, role: str, reason: str) -> None:
    """Escalate when a turn of a cheap run failed: the retry is the escalation (once per run)."""
    if role == IMPLEMENT and _cheap(d) and not d.state.extra.get("escalated"):
        escalate(d, f"cheap turn failed: {reason}")
