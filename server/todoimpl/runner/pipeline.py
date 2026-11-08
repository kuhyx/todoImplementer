"""Drive one run through its work stages until it rests: on kuhy, the plan limit, or the end."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl.board import state as store
from todoimpl.prompts import PromptContext, build

from . import checks, limits, phone, retry, worktree
from .files import NeedsYouError
from .permit import gate, with_grant
from .session import handoff_summary
from .turn import TurnEnv, run_turn

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.board.state import RunState
    from todoimpl.todo_mcp.items import Item

    from .launch import Handle
    from .session import Situation
    from .ship import Closer
    from .stream import TurnResult

log = logging.getLogger("todoimpl.runner")
WORK_STAGES = ("spec", "plan", "implement", "live_check", "checks", "shipping")
MAX_NUDGES = 2
NUDGE = "(runner) Your last reply had no status tag line: finish the work and end with `D:`, `Q:` or `A:`."
CONTINUE = "(runner) Continue. Report with a `D:`, `Q:` or `A:` tag line when your background work is done."
MAX_R_CONTINUES = 3


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
        if st.using_credits and limits.active_until(self.ctx.root, self.ctx.now()) is None:
            st.using_credits = False
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
            retry.pause(st, until, why)
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
        st = self.state
        if st.worktree and (Path(st.worktree) / ".git").exists():
            return
        wt = worktree.add(worktree.repo_dir(self.item.repo), self.ctx.root, st.task_id)
        st.worktree, st.branch, st.base_sha = str(wt.path), wt.branch, wt.base_sha
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

    def context(
        self, *, failure_tail: str = "", handoff: str = "", nudge: bool | str = False, cont: bool = False
    ) -> PromptContext:
        """Build the prompts package's view of this run: item, plan, answers and kuhy's notes."""
        st, item = self.state, self.item
        answers = tuple((q.title, q.answer) for q in st.spec_questions if q.answer is not None)
        notes = tuple(str(n) for n in st.extra.get("notes", []))
        notes += ((NUDGE if nudge is True else str(nudge),) if nudge else ()) + ((CONTINUE,) if cont else ())
        return PromptContext(
            title=item.title, body=item.body, repo=item.repo or "", worktree=(wt := Path(str(st.worktree))),
            run_dir=self.ctx.run_dir, done_check=checks.shown_done_check(item.done_check, wt),
            plan_md=self.plan_md(), spec_answers=answers,
            notes=notes, failure_tail=failure_tail, handoff=handoff,
            phone=st.extra.get("waiting_phone") if st.extra.get("phone_attached") else None,
        )  # fmt: skip

    def turn(self, role: str, stage: str, *, failure_tail: str = "", prompt: str = "") -> TurnResult:
        """One claude turn (`prompt` picks the builder, else `stage`); raises on cancel, limit, failure."""
        st, ctx = self.state, self.ctx
        until = limits.active_until(ctx.root, ctx.now())
        if until is not None and not st.using_credits:
            raise LimitHitError(until)
        nudge = st.extra.pop("nudge", False)
        cont = bool(st.extra.pop("r_continue", False))
        new_session = bool(st.extra.pop("fresh", False))
        if new_session:
            st.sessions.pop(role, None)
        if fresh := ctx.inbox():
            st.extra.setdefault("notes", []).extend(fresh)

        def prompt_for(situation: Situation) -> str:
            if situation == "killed":
                return build("resume_after_kill", self.context(nudge=nudge))
            if (situation == "idle" or new_session) and stage != "spec":
                handoff = handoff_summary(
                    ctx.run_dir,
                    str(st.extra.get("last_reply", "")),
                    st.self_check,
                    str((st.live_check or {}).get("report_md", "")),
                )
                return build("fresh_after_idle", self.context(handoff=handoff, nudge=nudge))
            return build(prompt or stage, self.context(failure_tail=failure_tail, nudge=nudge, cont=cont))

        env = TurnEnv(ctx.run_dir, Path(str(st.worktree)), ctx.publish, ctx.register, ctx.now)
        res = run_turn(env, st, role, with_grant(st, prompt_for, role), (ctx.run_dir,))
        st.extra["last_reply"] = res.text[-1500:]
        if res.finished and not res.is_error:
            phone.after_turn(st, ctx.run_dir, res)
        self.save()
        self._check_turn(res)
        if gate(self, res, stage):
            return self.turn(role, stage, failure_tail=failure_tail, prompt=prompt)
        return self._finished(res, role, stage)

    def _check_turn(self, res: TurnResult) -> None:
        if self.ctx.cancelled():
            raise CancelledError
        pause = limits.pause_until(res.limit, res.text, is_error=res.is_error, now=self.ctx.now())
        if pause is not None:
            limits.write_until(self.ctx.root, pause)
            raise LimitHitError(pause)

    def _finished(self, res: TurnResult, role: str, stage: str) -> TurnResult:
        if res.is_error or not res.finished:
            reason = res.text.strip()[:300] or retry.NO_RESULT
            tail = retry.stderr_tail(self.ctx.run_dir, role)
            raise retry.failure(self.state, now=self.ctx.now(), stage=stage, reason=reason, tail=tail)
        for key in ("retries", "crash_retries"):
            self.state.extra.pop(key, None)
        return res

    def r_continue(self, res: TurnResult) -> str | None:
        """Resume the same stage with a continue prompt after an `R:` turn, up to MAX_R_CONTINUES times."""
        st = self.state
        conts = int(st.extra.get("r_continues", 0))
        if res.tag != "R" or conts >= MAX_R_CONTINUES:
            return None
        st.extra["r_continues"] = conts + 1
        st.extra["r_continue"] = True
        return st.stage

    def after_tag(self, res: TurnResult, nxt: str) -> str | None:
        """Q/A rests for kuhy, D moves on, R continues the session, no tag nudges, then one fresh retry."""
        st = self.state
        if res.tag in ("Q", "A"):
            return None
        if res.tag == "D":
            for key in ("nudges", "r_continues", "tagless_retry"):
                st.extra.pop(key, None)
            return nxt
        if (again := self.r_continue(res)) is not None:
            return again
        nudges = int(st.extra.get("nudges", 0)) + 1
        if nudges > MAX_NUDGES:
            if st.extra.get("tagless_retry"):
                msg = f"Claude ended {nudges} turns without a status tag: read the feed and send guidance"
                raise NeedsYouError(msg, "run_failed")
            st.extra["tagless_retry"] = True
            st.extra["fresh"] = True
            return st.stage
        st.extra["nudges"] = nudges
        st.extra["nudge"] = True
        return st.stage
