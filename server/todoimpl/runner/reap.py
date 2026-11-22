"""Free a resting run's disk (T2433): its worktrees, landed branches and venvs.

Ship removed only `<run>/wt`; the `<run>/wt-<name>` worktrees sessions add for other repos (the standing grant
tells them to) and their venvs stayed for ever (the run root reached 112 GB). `clean` removes each `<run>/wt*`
worktree through the repo that owns it (`git worktree remove --force`, then `prune`), deletes its branch only
when every commit is on a remote or landed by content (`git cherry`), else keeps the branch (Retry and Restart
re-add the worktree from it), and deletes top-level venvs, `node_modules` and the turns' python user base.
state.json, events, logs, shots and turn files stay: the board reads them.

Never touched: a run whose stage is not resting, a run with a live turn record, a pending inbox, handoff or
Done-manually file, a run any live process has its cwd in, and a worktree with uncommitted changes. User units
that run from the run's worktrees are stopped first (T2494, `units`).
"""

from __future__ import annotations

import logging
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.board.status import MANUAL_STAGE

from . import orphans, units, userbase
from .worktree import GitError, git

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .engine import Engine

RESTING = ("shipped", "closed", "cancelled", MANUAL_STAGE, "failed")
PENDING = ("inbox.json", "start-when-free.json", "done-manually.json")
PROC = Path("/proc")
TAKEN = "taken again"  # `ok` said no: a Start took the run, or the sweep's budget is spent
REMOVE_TIMEOUT = 600.0  # deleting a 2 GB tree on a busy disk outlasts git()'s 50 s default
log = logging.getLogger("todoimpl.runner")


@dataclass
class Report:
    """What `clean` did (or, in a dry run, would do) to one run dir."""

    run: Path
    refused: str = ""
    removed: list[str] = field(default_factory=list)  # worktrees
    branches: list[str] = field(default_factory=list)  # deleted: landed
    kept: list[str] = field(default_factory=list)  # branches with commits no remote has
    skipped: list[str] = field(default_factory=list)  # "<path>: why"
    payload: list[str] = field(default_factory=list)  # venvs and node_modules
    units: list[str] = field(default_factory=list)  # user units that ran from a worktree (T2494): stopped


def live_cwds() -> list[Path]:
    """Return the cwd of every process this user can see."""
    found: list[Path] = []
    try:
        entries = list(PROC.iterdir())
    except OSError:
        return found
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            found.append(Path((entry / "cwd").readlink()))
        except OSError:  # gone meanwhile, or another user's
            continue
    return found


def refusal(run: Path, stages: Iterable[str], *, cwds: bool = True) -> str:
    """Return why `run` must not be cleaned now, "" when it may; `cwds=False` skips the live-cwd check."""
    st = store.load(run)
    if st is None:
        return "no state"
    if st.stage not in stages:
        return f"stage {st.stage}"
    rec = orphans.read(run)
    if rec is not None and (orphans.alive(rec.pid, rec.start) or orphans.alive(rec.host_pid, rec.host_start)):
        return "a turn is live"
    if waiting := next((name for name in PENDING if (run / name).exists()), None):
        return f"{waiting} waits"
    if cwds and any(cwd == run or run in cwd.parents for cwd in live_cwds()):
        return "a live process works in it"
    return ""


def clean(
    run: Path, *, apply: bool, stages: Iterable[str] = RESTING, ok: Callable[[], bool] | None = None
) -> Report:
    """Clean one run dir; `ok` is asked again before each worktree (a Start may take the run meanwhile)."""
    stages = tuple(stages)
    rep = Report(run, refused=refusal(run, stages, cwds=False))
    if rep.refused:
        return rep
    # A unit a session left running from its worktree (a dev server) would hold the run for ever (T2494).
    rep.units = units.in_worktrees(run)
    if apply and rep.units:
        units.stop(rep.units)
    rep.refused = refusal(run, stages)
    if rep.refused:
        return rep
    for wt in sorted(
        p for p in run.iterdir() if p.name.startswith("wt") and p.is_dir() and not p.is_symlink()
    ):
        if ok is not None and not ok():
            rep.refused = TAKEN
            return rep
        _worktree(wt, rep, apply=apply)
    for path in sorted(run.iterdir()):
        if path.is_dir() and not path.is_symlink() and _regenerable(path):
            rep.payload.append(str(path))
            if apply:
                shutil.rmtree(path, ignore_errors=True)
    return rep


def _regenerable(path: Path) -> bool:
    # A turn's python user base (T2495, T2503) holds the worker's pip installs; the next turn rebuilds it.
    return path.name in {"node_modules", userbase.DIR} or (path / "pyvenv.cfg").is_file()


def _worktree(wt: Path, rep: Report, *, apply: bool) -> None:
    dot = wt / ".git"
    if not dot.is_file() or dot.is_symlink():
        rep.skipped.append(f"{wt}: not a worktree")
        return
    try:
        common = _common(wt)
        if common is None:
            rep.skipped.append(f"{wt}: no repo owns it")
            return
        if git(wt, "status", "--porcelain").stdout.strip():
            rep.skipped.append(f"{wt}: uncommitted changes")
            return
        branch = git(wt, "symbolic-ref", "-q", "--short", "HEAD", check=False).stdout.strip()
        landed = bool(branch) and _landed(common, branch)
        if apply:
            _git(common, "worktree", "remove", "--force", str(wt), timeout=REMOVE_TIMEOUT)
            _git(common, "worktree", "prune")
        rep.removed.append(str(wt))
        if not branch.startswith("todo/"):
            return
        if not landed:
            rep.kept.append(branch)
            return
        if apply:
            _git(common, "branch", "-D", branch)
        rep.branches.append(branch)
    except GitError as exc:
        rep.skipped.append(f"{wt}: {exc}")


def _common(wt: Path) -> Path | None:
    proc = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir", check=False)
    path = Path(proc.stdout.strip())
    return path if proc.returncode == 0 and path.is_dir() and wt not in path.parents else None


def _git(common: Path, *args: str, check: bool = True, timeout: float | None = None) -> str:
    return git(common, f"--git-dir={common}", *args, check=check, timeout=timeout).stdout


def _landed(common: Path, branch: str) -> bool:
    """Say whether every commit of `branch` is on a remote, or its change is on origin's default branch."""
    if not _git(common, "rev-list", branch, "--not", "--remotes").strip():
        return True
    head = _git(common, "symbolic-ref", "-q", "refs/remotes/origin/HEAD", check=False).strip()
    for upstream in (head, "refs/remotes/origin/main", "refs/remotes/origin/master"):
        if upstream and _git(common, "rev-parse", "-q", "--verify", upstream, check=False).strip():
            return all(
                not line.startswith("+") for line in _git(common, "cherry", upstream, branch).splitlines()
            )
    return False


def summary(rep: Report) -> str:
    """One log line for a report."""
    if rep.refused:
        return f"{rep.run.name}: left ({rep.refused})"
    return (
        f"{rep.run.name}: {len(rep.removed)} worktrees, {len(rep.branches)} branches deleted, "
        f"{len(rep.kept)} kept, {len(rep.payload)} venvs, {len(rep.skipped)} skipped {rep.skipped}"
    )


AUTO = ("shipped", "closed", "cancelled", MANUAL_STAGE)  # a failed run is left for Retry (the sweep takes it)
_cleaning: set[str] = set()
_guard = threading.Lock()
_settled = threading.Condition(_guard)


def settle(card: str) -> None:
    """Block until no reap of `card` runs: a drive must not use a worktree a reap is removing (T2443).

    The reap asks `ok` before each worktree only, so a Restart that lands during a removal waits here for that
    one removal; the next `ok` sees the drive and stops. Never call it under the Scheduler's lock: `ok`
    takes it.
    """
    with _settled:
        _settled.wait_for(lambda: card not in _cleaning)


def spawn(sched: Engine, card: str) -> threading.Thread | None:
    """Clean a card whose run just came to rest, in a thread of its own: never under the Scheduler's lock."""
    st = store.load(sched.root / card)
    if st is None or st.stage not in AUTO:
        return None
    with _guard:
        if card in _cleaning:
            return None
        _cleaning.add(card)
    thread = threading.Thread(target=_after, args=(sched, card), name=f"reap-{card}", daemon=True)
    thread.start()
    return thread


def _after(sched: Engine, card: str) -> None:
    def ok() -> bool:  # a Start (a handoff's, or kuhy's Restart) may take the run back meanwhile
        with sched._cv:  # noqa: SLF001 - the Scheduler's own lock, as in stopping.cancel
            st = store.load(sched.root / card)
            idle = card not in sched._active and card not in sched._queue  # noqa: SLF001
            return idle and st is not None and st.stage in AUTO

    try:
        log.info("reap %s", summary(clean(sched.root / card, apply=True, stages=AUTO, ok=ok)))
    except Exception:
        log.exception("reap %s failed", card)
    finally:
        with _settled:
            _cleaning.discard(card)
            _settled.notify_all()
