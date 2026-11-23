"""Children that already failed for a reason Claude can fix go back to work when the server starts (T2344).

A child that failed before `shipfix.heal` existed (or under an older server) sits in `failed` with only its
error text: a killed or red gate step, a missing `- deploy:` line, a red or killed deploy. The text (and the
deploy's own record for its log tail) rebuilds the failure, and `shipfix.heal` decides as it would have live:
a plain rerun enters `shipping` at once (the restart was the wait), a fix turn enters `implement` with its
brief. The bound is counted and saved before any drive, so restarts never revive a child without end. A
child whose failure needs kuhy, or whose bound is spent, stays as it is.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.runner import deployheal, retry, shipfix
from todoimpl.runner.deploy import DeployFailedError
from todoimpl.runner.deployhost import DEPLOY_DIR, EXIT_FILE
from todoimpl.runner.deployline import PREFIX, NoDeployLineError
from todoimpl.runner.files import NeedsYouError, read_json
from todoimpl.runner.gate import GateRedError
from todoimpl.runner.restart import INTERRUPTED
from todoimpl.runner.worktree import repo_dir

from .store import children_root

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

GATE = re.compile(r"^Pre-push gate step (\S+) is red \((?:exit (-?\d+)|timed out)\):\n?(.*)\Z", re.DOTALL)
DEPLOY = re.compile(rf"^{PREFIX}: deploy failed \((?:exit (-?\d+)|timed out)\)")
NO_LINE = re.compile(rf"^{PREFIX}: .* declares no deploy: command in CLAUDE\.md$")
DROPPED = ("failed_stage", "retry_reason", "ship_resumes")  # a revived Ship starts its resume count afresh
LEGACY = "stops on uncommitted edits"  # the dirty text before T2507: its Ship now sets strays aside (T2512)
REFUSALS = "refusal_revives"  # a red deploy that only refused a dirty checkout ships again once (T2511)


def _code(text: str | None) -> int | None:
    return None if text is None else int(text)


def rebuilt(st: RunState, run_dir: Path) -> GateRedError | NoDeployLineError | DeployFailedError | None:
    """Return the failure a child's error text names, when it is one `shipfix.heal` routes; else None."""
    text = st.error or ""
    if found := GATE.match(text):
        return GateRedError(text, found.group(1), _code(found.group(2)), found.group(3))
    if NO_LINE.match(text):
        return NoDeployLineError(text)
    if found := DEPLOY.match(text):
        record = read_json(run_dir / DEPLOY_DIR / EXIT_FILE)
        tail = str(record.get("tail") or "") if isinstance(record, dict) else ""
        return DeployFailedError(text, _code(found.group(1)), tail or text)
    return None


def _checkout(st: RunState) -> Path | None:
    try:
        return repo_dir(st.repo)
    except NeedsYouError:
        return None


def _ship_again(st: RunState, run_dir: Path) -> bool:
    """Say whether the Ship goes on as it is: no fix turn, no kuhy (T2510, T2511).

    A Ship an older server parked after restarts; a deploy kuhy's edits blocked, once the files his step names
    are clean again (the ladder starts afresh); a red deploy whose log only refused a dirty checkout, once.
    """
    text = st.error or ""
    if text.startswith(INTERRUPTED):
        return True
    if deployheal.is_step(text):
        checkout = _checkout(st)
        try:
            if checkout is None or deployheal.still_dirty(checkout, deployheal.files_of(text)):
                return False
        except NeedsYouError:  # his own git holds a lock there: look again next time
            return False
        st.extra.pop("retries", None)
        return True
    record = read_json(run_dir / DEPLOY_DIR / EXIT_FILE)
    tail = str(record.get("tail") or "") if isinstance(record, dict) else ""
    refused = (DEPLOY.match(text) and deployheal.blocked(tail)) or LEGACY in text
    if not refused or int(st.extra.get(REFUSALS, 0)):
        return False
    st.extra[REFUSALS] = 1
    return True


def revive(st: RunState, run_dir: Path, now: float) -> bool:
    """Send a child that failed in Ship back to work when `shipfix.heal` would; True when it did."""
    if st.stage != "failed" or st.extra.get("failed_stage") != "shipping":
        return False
    if _ship_again(st, run_dir):
        stage = "shipping"
    elif (err := rebuilt(st, run_dir)) is None:
        return False
    else:
        try:
            shipfix.heal(st, err, now)
            stage = "implement"
        except retry.RetryLaterError:
            stage = "shipping"
        except NeedsYouError:  # kuhy's, or the bound is spent: nothing was counted
            return False
    st.stage, st.error, st.last_tag, st.assignee = stage, None, None, "claude"
    for key in DROPPED:
        st.extra.pop(key, None)
    return True


def children(run_dir: Path, now: float) -> int:
    """Revive every child of the umbrella at `run_dir` that `revive` takes, saving each; return how many."""
    revived = 0
    for path in sorted(children_root(run_dir).glob("*/state.json")):
        try:
            st = store.load(path.parent)
        except StateError:
            continue
        if st is not None and revive(st, path.parent, now):
            store.save(path.parent, st)
            revived += 1
    return revived
