"""Closing runs: a passing trusted done_check, one read-only Sonnet turn, then kuhy's Close click.

No plan, no implement, no worktree, no Ship; the repo's main checkout is never edited.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.board.state import RunState
from todoimpl.todo_mcp.model import TodoError

from .autocheck import POLL_TIMEOUT, note_red
from .checks import record, run_check
from .files import NeedsYouError
from .worktree import repo_dir

if TYPE_CHECKING:
    from .checks import CheckResult
    from .pipeline import Driver
    from .scheduler import Scheduler

EVIDENCE_LINES = 8
REPLY_CHARS = 600


def _recheck(d: Driver, timeout: float) -> CheckResult:
    """Run the item's done_check in the repo's main checkout and record it as the run's checks."""
    result = run_check("done_check", str(d.item.done_check), repo_dir(d.item.repo), d.ctx.run_dir, timeout)
    d.state.checks = record([result], result.log, d.ctx.now())
    return result


def closing_stage(d: Driver) -> str | None:
    """Run the closing turn, then the server's own re-run of the check decides: green rests at the gate."""
    if not d.item.done_check:
        msg = "The item no longer has a done_check: a closing run needs one"
        raise NeedsYouError(msg, "run_failed")
    d.turn("closing", "closing")
    result = _recheck(d, d.ctx.check_timeout)
    d.activity(f"done_check re-run: exit {result.exit_code}")
    if not result.passed:
        why = "timed out" if result.exit_code is None else f"exit {result.exit_code}"
        note_red(d.ctx.root, d.state.task_id, d.ctx.now())
        msg = f"The done_check is red again ({why}): nothing was closed"
        raise NeedsYouError(msg, "checks_failed")
    return "gate"


def evidence(result: CheckResult, reply: str, now: float) -> str:
    """Return the close evidence: the check, its output tail and the closing turn's confirmation."""
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
    tail = "\n".join(result.tail.splitlines()[-EVIDENCE_LINES:])
    parts = [f"Closed by todoImplementer (auto close) at {when}.", f"done_check `{result.command}` exit 0:"]
    parts += [tail] if tail else []
    parts += [f"Closing turn: {reply.strip()[-REPLY_CHARS:]}"] if reply.strip() else []
    return "\n".join(parts)


def auto_start(sched: Scheduler, card: str, passed_at: float) -> bool:
    """Create the closing run if the item still has none; the same lock as Start, so one of them wins."""
    try:
        item = sched.client.get_task(card).item
    except TodoError:
        return False
    with sched._cv:  # noqa: SLF001 - the Scheduler's own lock, shared on purpose
        try:
            existing = store.load(sched.root / card)
        except StateError:
            return False
        if existing is not None or sched.busy(card):
            return False
        st = RunState(task_id=card, stage="closing", started_at=sched.clock(), repo=item.repo)
        st.auto_start = {"reason": "done_check", "passed_at": passed_at}
        sched.save(card, st)
        sched.enqueue(card)
    return True


def close(sched: Scheduler, card: str) -> None:
    """Handle the Close click: re-run the check once; green closes the item (closed), red fails the run."""
    from .scheduler import RunnerError  # noqa: PLC0415 - scheduler imports this module

    with sched._cv:  # noqa: SLF001
        st = sched.idle(card)
        if st.stage != "gate" or not st.closing:
            msg = "Close is offered only at Ready to close"
            raise RunnerError(msg, "disabled")
        sched.mark_active(card, active=True)
    try:
        _close(sched, card, st)
    finally:
        with sched._cv:  # noqa: SLF001
            sched.mark_active(card, active=False)
            sched.save(card, st)
        sched.bus.publish(card, {"type": "done"})


def _verified(sched: Scheduler, card: str, st: RunState) -> CheckResult:
    """Re-run the item's done_check (poll timeout) in its repo; raise NeedsYouError when it is red."""
    item = sched.client.get_task(card).item
    result = run_check(
        "done_check", str(item.done_check), repo_dir(item.repo), sched.root / card, POLL_TIMEOUT
    )
    st.checks = record([result], result.log, sched.clock())
    if not result.passed:
        why = "timed out" if result.exit_code is None else f"exit {result.exit_code}"
        note_red(sched.root, card, sched.clock())
        msg = f"The done_check is red at Close ({why}): the item stays open"
        raise NeedsYouError(msg, "checks_failed")
    return result


def _close(sched: Scheduler, card: str, st: RunState) -> None:
    try:
        result = _verified(sched, card, st)
        sched.client.close_task(card, evidence(result, str(st.extra.get("last_reply", "")), sched.clock()))
    except (TodoError, NeedsYouError) as exc:
        st.extra["failed_stage"] = "gate"
        st.error = exc.text if isinstance(exc, NeedsYouError) else f"Closing the item failed: {exc}"
        st.stage = "failed"
        return
    st.extra["closed_at"] = sched.clock()
    st.stage = "closed"
