"""A Ship failure that heals by itself: a deploy blocked by kuhy's edits waits on the ladder (T2007)."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

from . import retry

if TYPE_CHECKING:
    from todoimpl.board.state import RunState

    from .deployheal import DirtyCheckoutError

MAX_DEPLOY_WAITS = 12  # 1, 2, 5, 10 minutes, then 30 each: about 4 h, as long as a 5xx is retried


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
