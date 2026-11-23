"""What a restart finds in the run root: the runs to queue again, a half-done ship included."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.board.status import Status, compute
from todoimpl.todo_mcp.model import TodoError
from todoimpl.umbrella import revive

from . import hold, live, orphans, retry
from .closing import CLOSE_ONLY
from .pipeline import WORK_STAGES
from .restart import resume_ship

if TYPE_CHECKING:
    from todoimpl.board.state import RunState
    from todoimpl.board.types import TaskLike


class Notes(Protocol):
    """The todo view: the note behind a card, fresh (the runner's client)."""

    def get_task(self, card: str) -> TaskLike: ...  # noqa: D102


def interrupted(root: Path, notes: Notes) -> list[str]:
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
            if "umbrella" not in st.extra:  # the umbrella's children count their own resumes
                resume_ship(st, time.time())  # past the cap it waits on the ladder (T2510)
            queue.append(st.task_id)
            store.save(path.parent, st)
        elif (
            st.stage == "gate" and not hold.held()
        ):  # a run that rested here before T2060 ships or closes now
            st.stage, st.error = ("closing", None) if st.closing else ("shipping", None)
            st.extra[CLOSE_ONLY] = st.closing
            store.save(path.parent, st)
            queue.append(st.task_id)
        elif _back_to_work(st, path.parent, notes):
            store.save(path.parent, st)
            queue.append(st.task_id)
        elif st.stage in (*WORK_STAGES, "paused_limit", retry.PAUSED) and (
            st.last_tag not in ("Q", "A") or orphans.read(path.parent) is not None
        ):  # a turn still recorded means last_tag is stale: it is running or its result waits
            queue.append(st.task_id)
    return queue


def _parked(notes: Notes, st: RunState) -> bool:
    """Say whether the board shows the card in Needs you; done, won't do or an unknown note stay (T2517)."""
    try:
        task = notes.get_task(st.task_id)
    except TodoError:  # the todo app is down or the section is gone: look again next start
        return False
    return compute(task, st, live=False, limit_until=None) == Status.NEEDS_YOU


def _back_to_work(st: RunState, run_dir: Path, notes: Notes) -> bool:
    """Move a failed run the board can take on itself back to work; True when it did."""
    if st.stage != "failed":
        return False
    if "umbrella" in st.extra:  # its children Claude can fix work again (T2344), while kuhy has not closed it
        if _parked(notes, st) and revive.children(run_dir, time.time()):
            st.stage, st.error = "implement", None
            st.extra.pop("failed_stage", None)
            return True
    elif (kind := revive.ship_kind(st, run_dir)) is not None and _parked(
        notes, st
    ):  # a self-heal text (T2517)
        revive.ship_on(st, kind)
        return True
    if live.rejudgeable(st):  # judged under older rules: judge the stored report again, no turn
        st.stage, st.error, st.last_tag, st.assignee = "live_check", None, None, "claude"
        st.extra.pop("failed_stage", None)
        st.extra["resettle"] = True
        return True
    return False
