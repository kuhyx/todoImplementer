"""A repo task's run goes in cycles: a shipped cycle that left parts open is followed by the next on Start."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import files

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

FILES = ("plan.md", "live_check.md", "questions.json")


def new_cycle(st: RunState, run_dir: Path) -> None:
    """Clear everything the shipped cycle left (worktree, session, plan, ticks); cost and history stay."""
    st.extra["cycle"] = int(st.extra.get("cycle", 1)) + 1
    st.worktree = st.branch = st.base_sha = st.head_sha = st.session_id = None
    st.ship = st.checks = st.live_check = st.lesson = None
    st.sessions, st.self_check, st.spec_questions = {}, [], []
    files.reset(run_dir)
    for name in FILES:
        (run_dir / name).unlink(missing_ok=True)
    # The tier is decided from the cycle's parts; a card id outlives its cycles (T1999).
    # The last cycle's reply asked that cycle's questions: answering one now would steer this one (T2360).
    keys = (
        "spec_ok",
        "partial",
        "followup_id",
        "tier",
        "free_models",
        "escalated",
        "escalate_reason",
        "last_reply",
    )
    for key in keys:
        st.extra.pop(key, None)
