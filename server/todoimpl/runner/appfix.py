"""Runs that fix an app error: the ledger after Ship, and the wait for a phone the deploy cannot reach.

kuhy's rule: an error already fixed but not on his phone yet reads "wait for phone to connect, then update
the app", and the update happens by itself when the phone connects. The fix is pushed (`pushed.json` keeps
that); only the deploy is left, so the phone watcher restarts the failed Ship and `ship()` just deploys again
(T1968).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.errors import ledger, marks
from todoimpl.repotask import files

from .phone import SERIAL, adb_command, attached_serials
from .stray import SUFFIX as STRAY_SUFFIX

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState
    from todoimpl.todo_mcp.items import Item

    from .deploy import DeployFailedError
    from .scheduler import Scheduler

PHONE_EXIT = 30  # `phone_deploy.sh`: the phone was not reachable
MAX_TRIES = 5  # phone waits per cycle: a deploy that keeps failing with the phone attached needs kuhy


def phone_wait(st: RunState, failed: DeployFailedError, now: float) -> None:
    """Rest a failed deploy as "waiting for the phone" when the phone is why it failed.

    Exit 30 says so; so does any failed deploy of an error run while the Pixel is not in `adb devices`. After
    `MAX_TRIES` tries the failure is an ordinary one. Any other failure drops the wait an earlier deploy left:
    else it holds this one (a dirty checkout, a Gradle error) in the phone wait for ever (T2465).
    """
    tries = int(st.extra.get(marks.PHONE_TRIES, 0)) + 1
    away = tries <= MAX_TRIES and (
        failed.exit_code == PHONE_EXIT
        or (marks.is_error_run(st) and SERIAL not in attached_serials(adb_command()))
    )
    if not away:
        st.extra.pop(marks.PHONE, None)
        return
    st.extra[marks.PHONE_TRIES] = tries
    st.extra[marks.PHONE] = {"since": now, "tries": tries}


def forget(st: RunState) -> None:
    """Drop the marks of the last cycle (error run, phone tries, tokenopt) when a new one starts."""
    for key in (marks.KEY, marks.PHONE_TRIES, marks.TOKENOPT):
        st.extra.pop(key, None)


def shipped(root: Path, run_dir: Path, item: Item, commit: str, now: float) -> None:
    """Mark the tickets of the ticked parts as shipped in `commit`; the loop tells their sources.

    With no commit only stray-work tickets count: "none of it is worth landing" closes them, and a ticket
    left open would be filed again once its note is done (T2518). An app error closed so is not fixed.
    """
    texts = [part.body for part in files.ticked(run_dir, item)] if item.parts else [item.body]
    found = [key for text in texts for key in marks.signatures(text)]
    if keys := [key for key in found if commit or key.endswith(STRAY_SUFFIX)]:
        ledger.mark_shipped(root, keys, commit, now)


def restart(sched: Scheduler, card: str) -> bool:
    """Restart the Ship of a card that waits for the phone; False when it no longer waits or cannot start."""
    from .scheduler import RunnerError  # noqa: PLC0415 - the scheduler imports this module

    with sched._cv:  # noqa: SLF001 - the Scheduler's own lock, as in closing.auto_start
        if sched.updating(card) is None:
            return False
    try:
        sched.start(card)
    except RunnerError:
        return False
    return True
