"""Ship failures that heal by themselves: a rerun on the ladder or a session fix turn (DOCS-landing.md).

Only what Claude cannot do reaches kuhy (2026-11-19, umbrella 2556952d-0). A deploy blocked by kuhy's edits
waits (T2007), and so does a deploy that exits 52, "busy, rerun later" (T2400). A gate step or deploy killed
by a signal reruns once as it is (T2340, T2341, T2343), and a gate step killed while it only waited for the
build lock reruns without counting. Everything else that is Claude's work goes back to the session with a
brief: a red or twice-killed gate step, a missing `- deploy:` line, a red deploy (T2050, T2342, T2343). Each
kind has its own bound; past it the failure stays with kuhy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

from todoimpl.errors import marks

from . import appfix, retry
from .deployline import NoDeployLineError
from .gate import GateRedError

if TYPE_CHECKING:
    from todoimpl.board.state import RunState

    from .deploy import DeployFailedError
    from .deployheal import DirtyCheckoutError

MAX_DEPLOY_WAITS = 12  # 1, 2, 5, 10 minutes, then 30 each: about 4 h, as long as a 5xx is retried
BUSY_EXIT = 52  # a deploy's "busy, rerun later" (tunedeck while it plays): the ladder reruns it (T2400)
MAX_DEPLOY_FIXES = 2  # session fix turns for a red or undeclared deploy per Start
MAX_SHIP_FIXES = 2  # session fix turns for a refused commit, red checks or a red gate step per Start
MAX_KILL_RERUNS = 1  # plain reruns of a gate step or deploy a signal killed, each per Start
MAX_LOCK_WAITS = 12  # reruns of a gate step stopped while it waited for the build lock: the ladder, ~4 h
NO_LINE_ASK = (
    "(runner) Your work is pushed, but CLAUDE.md declares no deploy, so nothing was installed or released. "
    "Add a `- deploy: `<command>`` bullet to its Commands section that installs, releases and deploys this "
    "repo everywhere it runs (idempotent, non-zero unless its own health check passes; never uninstall an "
    "app or `pm clear`), commit and push it, run it and read the result. Only when nothing of this repo runs "
    "or is installed anywhere (a document, a library nobody installs) write `- deploy: none (<why>)` "
    "instead. You have permission; do not end on `A:` for this."
)


def heal(st: RunState, err: GateRedError | NoDeployLineError | DeployFailedError, now: float) -> str:
    """Route a Ship failure Claude can fix; return the feed line of the fix turn (the next stage: implement).

    Raises `retry.RetryLaterError` for a plain rerun of the Ship (it resumes at `shipping`), `err` (or its
    spent form) when kuhy is needed.
    """
    if isinstance(err, GateRedError):
        if err.waited_only and _count(st, "gate_waits", MAX_LOCK_WAITS):
            raise retry.later(st, now, f"gate step {err.step} stopped while queued: it runs again", "killed")
        if err.killed and _count(st, "gate_kills", MAX_KILL_RERUNS):
            raise retry.later(st, now, f"gate step {err.step} was killed: it runs again", "killed")
        what = "killed again, the session makes it fit" if err.killed else "red, the session fixes it"
        return _fix(st, "ship_fixes", MAX_SHIP_FIXES, err, f"gate step {err.step} {what}")
    if isinstance(err, NoDeployLineError):
        return _fix(st, "deploy_fixes", MAX_DEPLOY_FIXES, err, "no deploy line, the session adds one")
    if err.exit_code == BUSY_EXIT:  # nothing to fix: the target is busy (music playing); rerun later
        if int(st.extra.get("retries", 0)) >= MAX_DEPLOY_WAITS:
            raise err
        raise retry.later(st, now, f"deploy busy (exit {BUSY_EXIT}): it runs again later")
    appfix.phone_wait(st, err, now)  # pushed, not deployed: maybe only because the phone is away
    if err.exit_code is not None and err.exit_code < 0 and _count(st, "deploy_kills", MAX_KILL_RERUNS):
        raise retry.later(st, now, f"deploy was killed (exit {err.exit_code}): it runs again", "killed")
    return deploy_fix(st, err)


def _count(st: RunState, key: str, cap: int) -> bool:
    """Count one more use of `key`; False once `cap` were used."""
    used = int(st.extra.get(key, 0))
    if used >= cap:
        return False
    st.extra[key] = used + 1
    return True


def _fix(st: RunState, key: str, cap: int, err: GateRedError | NoDeployLineError, what: str) -> str:
    """Brief the session's fix turn under bound `key`; past `cap` raise the failure for kuhy."""
    if not _count(st, key, cap):
        if isinstance(err, NoDeployLineError):
            spent = f"{err.text}: {cap} fix turns did not add one; Retry gives the session {cap} more"
            raise NoDeployLineError(spent)
        raise err
    brief = f"{err.text}\n\n{NO_LINE_ASK}" if isinstance(err, NoDeployLineError) else err.output
    st.extra.update(failure_tail=brief, reship=True)
    return f"{what} ({st.extra[key]}/{cap})"


def deploy_fix(st: RunState, failed: DeployFailedError) -> str:
    """Brief the session's fix turn for a red deploy (T2050; umbrella children too, T2343); return its line.

    Raises `failed` for the phone (`marks.PHONE`) or `MAX_DEPLOY_FIXES` spent. The implement drive drops the
    push record: the session's commits and tag ship as pushed work, the deploy reruns.
    """
    fixes = int(st.extra.get("deploy_fixes", 0))
    if marks.PHONE in st.extra or fixes >= MAX_DEPLOY_FIXES:
        raise failed
    st.extra.update(deploy_fixes=fixes + 1, failure_tail=failed.output, reship=True)
    return f"deploy red, the session fixes it ({fixes + 1}/{MAX_DEPLOY_FIXES})"


def wait_for_edits(st: RunState, err: DirtyCheckoutError, now: float) -> NoReturn:
    """Rest the run in `paused_retry` for the next ladder step; past `MAX_DEPLOY_WAITS` raise `err`.

    The counter is `retries`, which the ladder reads (Start, Retry and a finished turn clear it); nothing of
    kuhy's is touched meanwhile. The push is recorded (`pushed.json`), so the resumed Ship only deploys again.
    """
    if int(st.extra.get("retries", 0)) >= MAX_DEPLOY_WAITS:
        raise err
    first = err.files[0] if err.files else "files"
    more = f" +{len(err.files) - 1}" if len(err.files) > 1 else ""
    raise retry.later(st, now, f"deploy waits: edits in {err.where} block the pull ({first}{more})")
