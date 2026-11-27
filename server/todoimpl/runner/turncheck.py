"""Decide after a turn whether runs pause (plan limit, overage guard, credits exhausted)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.credits import errors, marks

from . import limits

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

    from .stream import TurnResult


def pause_after(st: RunState, root: Path, res: TurnResult, now: float) -> float | None:
    """Return the epoch runs pause until after this turn, None when it hit nothing.

    The overage guard already wrote the limit and the alert while it killed the turn. A credit turn that ends
    in a billing or key error records "credits exhausted" until the plan limit lifts, so the run waits for the
    plan instead of retrying (a credit error looks transient to retry.py). A plan turn is read for its limit.
    """
    if (hit := st.extra.pop("overage_hit", None)) is not None:
        return float(hit)
    if st.extra.get("route") == "free":  # the gateway's errors are no plan limit (T2531)
        return None
    if st.extra.get("route") == "credits":
        if not (res.is_error and errors.exhausted(res.text)):
            return None
        until = limits.active_until(root, now) or now + limits.FALLBACK_PAUSE
        marks.mark_exhausted(root, until, res.text)
        return until
    pause = limits.pause_until(res.limit, res.text, is_error=res.is_error, now=now)
    if pause is not None:
        limits.write_until(root, pause)
    return pause
