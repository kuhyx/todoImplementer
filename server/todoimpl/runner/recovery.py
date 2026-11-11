"""What a restart finds in the run root: the runs to queue again, and the half-done ship it marks failed."""

from __future__ import annotations

from pathlib import Path

from todoimpl.board import state as store
from todoimpl.board.parse import StateError

from . import deploy, live, orphans, retry
from .pipeline import WORK_STAGES


def interrupted(root: Path) -> list[str]:
    """Return the card ids to queue again; a run caught mid-ship becomes `failed` (never shipped twice)."""
    queue: list[str] = []
    for path in sorted(root.glob("*/state.json")):
        try:
            st = store.load(path.parent)
        except StateError:
            continue
        if st is None:  # pragma: no cover - the file was just globbed
            continue
        if st.stage == "shipping" and st.worktree and deploy.pushed(path.parent, Path(st.worktree)):
            queue.append(st.task_id)  # its own push landed: Ship goes on at the deploy, which it adopts
        elif st.stage == "shipping":
            st.extra["failed_stage"] = "gate"
            st.error = "Ship was interrupted by a restart: check origin and the note before shipping again"
            st.stage = "failed"
            store.save(path.parent, st)
        elif live.rejudgeable(st):  # judged under older rules: judge the stored report again, no turn
            st.stage, st.error, st.last_tag, st.assignee = "live_check", None, None, "claude"
            st.extra.pop("failed_stage", None)
            st.extra["resettle"] = True
            store.save(path.parent, st)
            queue.append(st.task_id)
        elif st.stage in (*WORK_STAGES, "paused_limit", retry.PAUSED) and (
            st.last_tag not in ("Q", "A") or orphans.read(path.parent) is not None
        ):  # a turn still recorded means last_tag is stale: it is running or its result waits
            queue.append(st.task_id)
    return queue
