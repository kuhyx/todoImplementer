"""What a restart finds in the run root: the runs to queue again, a half-done ship included."""

from __future__ import annotations

import time
from pathlib import Path

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.umbrella import revive

from . import hold, live, orphans, retry
from .closing import CLOSE_ONLY
from .pipeline import WORK_STAGES
from .restart import resume_ship


def interrupted(root: Path) -> list[str]:
    """Return the card ids to queue again; a run caught mid-ship ships again, at most `MAX_RESUMES` times."""
    queue: list[str] = []
    for path in sorted(root.glob("*/state.json")):
        try:
            st = store.load(path.parent)
        except StateError:
            continue
        if st is None:  # pragma: no cover - the file was just globbed
            continue
        if st.stage == "shipping":  # Ship is idempotent: it goes on by itself, no click, no Needs you (T1988)
            if "umbrella" in st.extra or resume_ship(st):  # the umbrella's children count their own resumes
                queue.append(st.task_id)
            store.save(path.parent, st)
        elif (
            st.stage == "gate" and not hold.held()
        ):  # a run that rested here before T2060 ships or closes now
            st.stage, st.error = ("closing", None) if st.closing else ("shipping", None)
            st.extra[CLOSE_ONLY] = st.closing
            store.save(path.parent, st)
            queue.append(st.task_id)
        elif st.stage == "failed" and "umbrella" in st.extra and revive.children(path.parent, time.time()):
            st.stage, st.error = "implement", None  # its children Claude can fix work again (T2344)
            st.extra.pop("failed_stage", None)
            store.save(path.parent, st)
            queue.append(st.task_id)
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
