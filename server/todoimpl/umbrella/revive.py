"""Children that already failed for a reason Claude can fix go back to work when the server starts (T2344).

A child that failed before `shipfix.heal` existed (or under an older server) sits in `failed` with only its
error text: a killed or red gate step, a missing `- deploy:` line, a red or killed deploy. The text (and the
deploy's own record for its log tail) rebuilds the failure, and `shipfix.heal` decides as it would have live:
a plain rerun enters `shipping` at once (the restart was the wait), a fix turn enters `implement` with its
brief. The bound is counted and saved before any drive, so restarts never revive a child without end. A
child whose failure needs kuhy, or whose bound is spent, stays as it is. `ship_again` (a text the board heals
itself: a cut Ship, a dirty deploy) serves server start's top-level cards too, once per text (T2517).
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
REFUSALS = "refusal_revives"  # the T2511 server's mark: its refusal kind is spent
KINDS = "ship_revives"  # the self-heal texts a card already shipped again for, each once: no loop (T2517)


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


def _kind(st: RunState, run_dir: Path) -> str | None:
    """Name the self-heal text a failed Ship carries when it may ship again now, no fix turn, no kuhy (T2510).

    A Ship an older server parked after restarts; a deploy kuhy's edits blocked, once the files his step names
    are clean again; a red deploy whose log only refused a dirty checkout, or the dirty text before T2507.
    """
    text = st.error or ""
    if text.startswith(INTERRUPTED):
        return "interrupted"
    if deployheal.is_step(text):
        checkout = _checkout(st)
        try:
            clean = checkout is not None and not deployheal.still_dirty(checkout, deployheal.files_of(text))
        except NeedsYouError:  # his own git holds a lock there: look again next time
            clean = False
        return "dirty" if clean else None
    record = read_json(run_dir / DEPLOY_DIR / EXIT_FILE)
    tail = str(record.get("tail") or "") if isinstance(record, dict) else ""
    return "refused" if (DEPLOY.match(text) and deployheal.blocked(tail)) or LEGACY in text else None


def _back_to(st: RunState, stage: str) -> None:
    st.stage, st.error, st.last_tag, st.assignee = stage, None, None, "claude"
    for key in DROPPED:
        st.extra.pop(key, None)


def ship_again(st: RunState, run_dir: Path) -> bool:
    """Send a card or child a self-heal text parked back to `shipping`, at most once per text (T2517)."""
    failed = st.extra.get("failed_stage")
    if st.stage != "failed" or failed not in ("shipping", "gate"):  # "gate": a cut Ship's legacy form
        return False
    kind = _kind(st, run_dir)
    spent = [*st.extra.get(KINDS, []), *(["refused"] if st.extra.get(REFUSALS) else [])]
    if kind is None or kind in spent or (failed == "gate" and kind != "interrupted"):
        return False
    st.extra[KINDS] = [*st.extra.get(KINDS, []), kind]
    if kind == "dirty":
        st.extra.pop("retries", None)  # the ladder starts afresh
    _back_to(st, "shipping")
    return True


def revive(st: RunState, run_dir: Path, now: float) -> bool:
    """Send a child that failed in Ship back to work when `shipfix.heal` would; True when it did."""
    if ship_again(st, run_dir):
        return True
    if st.stage != "failed" or st.extra.get("failed_stage") != "shipping":
        return False
    if (err := rebuilt(st, run_dir)) is None:
        return False
    try:
        shipfix.heal(st, err, now)
        stage = "implement"
    except retry.RetryLaterError:
        stage = "shipping"
    except NeedsYouError:  # kuhy's, or the bound is spent: nothing was counted
        return False
    _back_to(st, stage)
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
