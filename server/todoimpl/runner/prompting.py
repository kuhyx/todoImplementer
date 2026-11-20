"""Which prompt a turn gets, given what the session already knows (`session.Situation`).

A resumed session keeps its context (`resume`): stage prompts name plan.md by path. A new session
(first turn of a role, or the role's session was dropped) gets the plan text. A session idle for over an hour
is gone from the prompt cache: it starts fresh from a handoff summary. The live check is its own Sonnet
session; when it starts fresh it is seeded from the same summary (without the plan, which its prompt carries).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.prompts import build

from .session import handoff_summary

if TYPE_CHECKING:
    from collections.abc import Callable

    from .pipeline import Driver
    from .session import Situation


@dataclass(frozen=True)
class Ask:
    """What one `Driver.turn` call wants: the stage (or explicit prompt), its failure tail, runner notes."""

    stage: str
    prompt: str = ""
    failure_tail: str = ""
    nudge: bool | str = False
    cont: bool = False
    new_session: bool = False
    note: str = ""  # cheap-tier addendum of the implement role
    seed: str = ""  # why the session is fresh when the context cap cut the last one (`ctxcap.seed`)


def prompt_for(d: Driver, ask: Ask) -> Callable[[Situation], str]:
    """Return the prompt builder `run_turn` calls once it knows the session situation."""
    st = d.state

    def handoff(*, with_plan: bool) -> str:
        return handoff_summary(
            d.ctx.run_dir,
            str(st.extra.get("last_reply", "")),
            st.self_check,
            str((st.live_check or {}).get("report_md", "")),
            with_plan=with_plan,
        )

    def text_for(situation: Situation) -> str:
        if situation == "killed":
            return build("resume_after_kill", d.context(nudge=ask.nudge, tier=ask.note))
        new = situation in ("", "idle") or ask.new_session  # no usable session: this turn starts a new one
        if ask.stage == "live_check" and new:  # seeded from the implementer's work; the plan is in the prompt
            ctx = d.context(handoff=handoff(with_plan=False), failure_tail=ask.failure_tail, nudge=ask.nudge)
            return build(ask.prompt or ask.stage, ctx)
        if (situation == "idle" or ask.new_session) and ask.stage not in ("spec", "plan") and not ask.prompt:
            ctx = d.context(handoff=handoff(with_plan=True), nudge=ask.nudge, tier=ask.note)
            return build("fresh_after_idle", ctx)
        return build(
            ask.prompt or ask.stage,
            d.context(
                failure_tail=ask.failure_tail, nudge=ask.nudge, cont=ask.cont, tier=ask.note,
                resumed=situation == "resume",
            ),
        )  # fmt: skip

    def build_for(situation: Situation) -> str:
        text = text_for(situation)
        return f"{text}\n{ask.seed}" if ask.seed else text

    return build_for
