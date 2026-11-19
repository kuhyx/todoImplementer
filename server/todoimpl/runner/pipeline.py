"""Drive one run through its work stages until it rests: on kuhy, the plan limit, or the end."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl.board import state as store
from todoimpl.credits import route
from todoimpl.prompts import PromptContext
from todoimpl.repotask.prompt import addendum

from . import checks, deploy, phone, resume, retry, tags, tiering, turncheck, worktree
from .askform import needs_form
from .files import KilledError, NeedsYouError
from .grant import auto_grant
from .permit import gate, with_grant
from .prompting import Ask, prompt_for
from .repolock import RepoLocks
from .turn import TurnEnv, run_turn

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.board.state import RunState
    from todoimpl.todo_mcp.items import Item

    from .launch import Handle
    from .ship import Closer
    from .stream import TurnResult

log = logging.getLogger("todoimpl.runner")
SIGNAL_EXIT = 128  # a shell reports death by signal N as 128 + N
WORK_STAGES = ("spec", "plan", "implement", "live_check", "checks", "shipping", "closing")
NUDGE = "(runner) Your last reply had no status tag line: finish the work and end with `D:`, `Q:` or `A:`."
CONTINUE = "(runner) Continue. Report with a `D:`, `Q:` or `A:` tag line when your background work is done."


class CancelledError(Exception):
    """kuhy cancelled the run."""


class LimitHitError(Exception):
    """The plan limit is active until `until`."""

    def __init__(self, until: float) -> None:  # noqa: D107
        super().__init__(until)
        self.until = until


@dataclass(frozen=True)
class Ctx:
    """What a drive needs from the scheduler."""

    root: Path
    run_dir: Path
    client: Closer
    publish: Callable[[dict[str, Any]], None]
    register: Callable[[Handle | None], None]
    now: Callable[[], float]
    cancelled: Callable[[], bool]
    check_timeout: float
    inbox: Callable[[], list[str]]
    locks: RepoLocks = field(
        default_factory=RepoLocks
    )  # the engine's per-repo lock; umbrella children take it too


class Driver:
    """One drive of one run; the scheduler guarantees a run has at most one live driver."""

    def __init__(self, ctx: Ctx, state: RunState, item: Item) -> None:  # noqa: D107
        self.ctx = ctx
        self.state = state
        self.item = item

    def run(self) -> None:
        """Loop stage handlers until a resting stage, a Q/A tag, cancel, the limit or a Needs-you."""
        from .stages import HANDLERS  # noqa: PLC0415 - stages imports this module

        st = self.state
        if st.stage in ("paused_limit", retry.PAUSED):
            st.stage = st.extra.pop("resume_stage", "implement")
            st.extra.pop("retry_reason", None)
            st.resume_at = None
        if st.stage != "shipping":  # work may follow: the record of an earlier push no longer fits the tree
            deploy.forget(self.ctx.run_dir)
        try:
            self._worktree()
            while st.stage in WORK_STAGES:
                nxt = HANDLERS[st.stage](self)
                self._check_cancel()
                if nxt is None:
                    break
                self.set_stage(nxt)
        except CancelledError:
            self.set_stage("cancelled")
        except LimitHitError as hit:
            st.extra["resume_stage"] = st.stage
            st.resume_at = hit.until
            self.set_stage("paused_limit")
        except retry.RetryLaterError as later:
            until, why = later.args
            retry.pause(st, until, why, later.kind)
            self.set_stage(retry.PAUSED)
        except NeedsYouError as exc:
            self.fail(exc)
        except Exception as exc:
            log.exception("run %s crashed", st.task_id)
            self.fail(NeedsYouError(f"The runner crashed: {exc!r}"))
        self.save()

    def _check_cancel(self) -> None:
        if self.ctx.cancelled():
            raise CancelledError

    def _worktree(self) -> None:
        if self.state.closing:
            return  # a closing run has no worktree: it works read-only in the repo's main checkout
        worktree.attach(self.state, self.item.repo, self.ctx.root)  # also rebases a reused worktree (T1864)
        self.save()

    def save(self) -> None:  # noqa: D102
        self.state.updated = self.ctx.now()
        store.save(self.ctx.run_dir, self.state)

    def set_stage(self, stage: str) -> None:  # noqa: D102
        self.state.stage = stage
        self.save()
        self.ctx.publish({"type": "stage", "stage": stage})

    def fail(self, exc: NeedsYouError) -> None:
        """Stop in `failed` with the reason; a missing repo hands the item to kuhy."""
        st = self.state
        st.extra["failed_stage"] = st.stage
        st.error = exc.text
        if exc.kind == "handed_to_you":
            st.assignee = "human"
        self.set_stage("failed")

    def activity(self, text: str) -> None:  # noqa: D102
        self.ctx.publish(
            {"type": "activity", "at": self.ctx.now(), "kind": "system", "text": text, "tool": None}
        )

    def plan_md(self) -> str:  # noqa: D102
        plan = self.ctx.run_dir / "plan.md"
        return plan.read_text(encoding="utf-8") if plan.exists() else ""

    def context(  # noqa: PLR0913 - the prompt context's fields
        self,
        *,
        failure_tail: str = "",
        handoff: str = "",
        nudge: bool | str = False,
        cont: bool = False,
        tier: str = "",
        resumed: bool = False,
    ) -> PromptContext:
        """Build the prompts package's view of this run: item, plan, answers and kuhy's notes."""
        st, item = self.state, self.item
        answers = tuple((q.title, q.answer) for q in st.spec_questions if q.answer is not None)
        notes = tuple(str(n) for n in st.extra.get("notes", [])) + worktree.conflict_notes(st)
        notes += ((NUDGE if nudge is True else str(nudge),) if nudge else ()) + ((CONTINUE,) if cont else ())
        return PromptContext(
            title=item.title, body=item.body, repo=item.repo or "",
            worktree=(wt := worktree.turn_dir(st, item.repo)), run_dir=self.ctx.run_dir,
            done_check=checks.shown_done_check(item.done_check, wt),
            plan_md=self.plan_md(), spec_answers=answers,
            notes=notes, failure_tail=failure_tail, handoff=handoff,
            phone=st.extra.get("waiting_phone") if st.extra.get("phone_attached") else None,
            base=str(st.extra.get("base_branch", "main")), tier=tier, resumed=resumed,
            parts=addendum(item, self.ctx.run_dir),
        )  # fmt: skip

    def turn(self, role: str, stage: str, *, failure_tail: str = "", prompt: str = "") -> TurnResult:
        """One claude turn (`prompt` picks the builder, else `stage`); raises on cancel, limit, failure."""
        st, ctx = self.state, self.ctx
        choice = route.choose(ctx.root, ctx.now())
        if choice.route is None:  # the plan limit holds and the free credits cannot take over
            raise LimitHitError(choice.until or ctx.now())
        nudge = st.extra.pop("nudge", False)
        cont = bool(st.extra.pop("r_continue", False))
        new_session = bool(st.extra.pop("fresh", False))
        if new_session:
            st.sessions.pop(role, None)
        if fresh := ctx.inbox():
            st.extra.setdefault("notes", []).extend(fresh)
            st.extra[phone.REPLIED] = True  # this turn takes kuhy's reply in: its ask may not return (T1981)
        plan = tiering.plan_turn(self, role)

        ask = Ask(stage, prompt, failure_tail, nudge, cont, new_session, plan.note)
        build_for = prompt_for(self, ask)

        env = TurnEnv(ctx.run_dir, worktree.turn_dir(st, self.item.repo), ctx.publish, ctx.register, ctx.now)
        try:
            who = (env, st, role, with_grant(st, build_for, role), (ctx.run_dir,))
            if (claimed := route.claim(ctx.root, ctx.now(), ctx.run_dir.name)).route is None:
                raise LimitHitError(claimed.until or ctx.now())  # another card took the last of the pace
            res = run_turn(*who, claimed.route, plan.model, "high" if stage == "fix" else plan.effort)
        except KilledError as exc:  # the host died again and again: wait and retry before Needs you
            self.save()
            failure = retry.failure(st, now=ctx.now(), stage=stage, reason=exc.text, tail="", killed=True)
            raise failure from exc
        st.extra["last_reply"] = res.text[-1500:]
        if res.finished and not res.is_error:
            phone.after_turn(st, ctx.run_dir, res, stage)
        self.save()
        self._check_turn(res)
        if (
            st.extra.pop("cap_hit", None) and not res.finished
        ):  # the credit cap stopped the turn: go on at once, on the plan
            st.extra["r_continue"] = True
            return self.turn(role, stage, failure_tail=failure_tail, prompt=prompt)
        resume.rest(self, res, stage)  # a wait or resume line of Claude's own rests on the ladder (T2104)
        if gate(self, res, stage) or auto_grant(self, res, stage) or needs_form(self, res, stage):
            return self.turn(role, stage, failure_tail=failure_tail, prompt=prompt)
        return self._finished(res, role, stage)

    def _check_turn(self, res: TurnResult) -> None:
        if self.ctx.cancelled():
            raise CancelledError
        pause = turncheck.pause_after(self.state, self.ctx.root, res, self.ctx.now())
        if pause is not None:
            raise LimitHitError(pause)

    def _finished(self, res: TurnResult, role: str, stage: str) -> TurnResult:
        if res.is_error or not res.finished:
            reason = res.text.strip()[:300] or retry.NO_RESULT
            tail = retry.stderr_tail(self.ctx.run_dir, role)
            tiering.failed(self, role, reason)
            code = int(self.state.extra.get("last_exit", 0))
            killed = not res.finished and (code < 0 or code >= SIGNAL_EXIT)
            raise retry.failure(
                self.state, now=self.ctx.now(), stage=stage, reason=reason, tail=tail, killed=killed
            )
        for key in ("retries", "crash_retries", "kill_retries"):
            self.state.extra.pop(key, None)
        return res

    def r_continue(self, res: TurnResult) -> str | None:
        """Resume the same stage with a continue prompt after an `R:` turn (see tags.py)."""
        return tags.r_continue(self.state, res)

    def after_tag(self, res: TurnResult, nxt: str) -> str | None:
        """Q/A rests for kuhy, D moves on, R continues, no tag nudges (see tags.py)."""
        return tags.after_tag(self.state, res, nxt)
