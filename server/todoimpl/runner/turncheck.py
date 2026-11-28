"""Decide after a turn whether runs pause (plan limit, overage guard, credits exhausted)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.credits import errors, marks, setting

from . import limits

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

    from .stream import TurnResult


def pause_after(st: RunState, root: Path, res: TurnResult, now: float) -> float | None:
    """Return the epoch runs pause until after this turn, None when it hit nothing.

    The overage guard already wrote the limit and the alert while it killed the turn. A credit turn that ends
    in a billing or key error records "credits exhausted" until the plan limit lifts, so the run waits for the
    plan instead of retrying (a credit error looks transient to retry.py). An empty balance is worse: it
    switches the credits off in settings.json for good, and the card goes on at once on the plan route (or
    waits for the plan limit). A plan turn is read for its limit.
    """
    if (hit := st.extra.pop("overage_hit", None)) is not None:
        return float(hit)
    if st.extra.get("route") == "free":  # the gateway's errors are no plan limit (T2531)
        return None
    if st.extra.get("route") == "credits":
        if res.is_error and errors.balance_low(res.text):  # kuhy, 2026-11-28: off until he turns it on
            setting.turn_off(errors.BALANCE_REASON, now)
            return limits.active_until(root, now) or now  # no failure: the card goes on at the plan
        if not (res.is_error and errors.exhausted(res.text)):
            return None
        until = limits.active_until(root, now) or now + limits.FALLBACK_PAUSE
        marks.mark_exhausted(root, until, res.text)
        return until
    pause = limits.pause_until(res.limit, res.text, is_error=res.is_error, now=now)
    if pause is not None:
        limits.write_until(root, pause)
    return pause
