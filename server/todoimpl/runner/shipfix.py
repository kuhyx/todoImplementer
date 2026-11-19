"""A Ship failure that heals by itself: a deploy blocked by kuhy's edits waits on the ladder (T2007)."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

from todoimpl.errors import marks

from . import retry

if TYPE_CHECKING:
    from todoimpl.board.state import RunState

    from .deploy import DeployFailedError
    from .deployheal import DirtyCheckoutError

MAX_DEPLOY_WAITS = 12  # 1, 2, 5, 10 minutes, then 30 each: about 4 h, as long as a 5xx is retried
MAX_DEPLOY_FIXES = 2  # session fix turns for a red deploy per Start (the checks' own bounce is `ship_fixes`)


def deploy_fix(st: RunState, failed: DeployFailedError) -> str:
    """Brief the session's fix turn for a red deploy (T2050); return its feed line.

    Raises `failed` for the phone (`marks.PHONE`), an umbrella child, or `MAX_DEPLOY_FIXES` spent. The
    implement drive drops the push record: the session's commits and tag ship as pushed work, deploy reruns.
    """
    fixes = int(st.extra.get("deploy_fixes", 0))
    if marks.PHONE in st.extra or "umbrella_round" in st.extra or fixes >= MAX_DEPLOY_FIXES:
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
