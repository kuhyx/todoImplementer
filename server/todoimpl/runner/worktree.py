"""Per-task git worktrees in the task's repo: `kuhyx/<name>` lives at `~/src/<name>`."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board.repos import repo_path
from todoimpl.prompts.standing import REBASE_NOTE

from . import orphans
from .checks import clean_env
from .files import NeedsYouError, worktree_path

if TYPE_CHECKING:
    from todoimpl.board.state import RunState

OWNER = "kuhyx"
# Machine-local files a repo's gate needs but git ignores (tunedeck: chaquopy.buildPython lives in
# android/local.properties). A named list, not a glob: nothing else leaves the main clone.
MACHINE_LOCAL = ("local.properties", "android/local.properties")
GIT_TIMEOUT = 50.0


class GitError(NeedsYouError):
    """A git command failed; the text carries its stderr tail."""


@dataclass(frozen=True)
class Worktree:
    """A task's worktree; `base_ref` is origin's default branch, `base_sha` the merge base with it."""

    path: Path
    branch: str
    base_sha: str
    base_ref: str
    remote_branch: str
    conflict: bool = False  # the rebase onto base_ref stopped on conflicts: left for the session to resolve


def git(
    cwd: Path, *args: str, check: bool = True, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Run git with prompts off; a failure (when checked) or a timeout raises GitError."""
    timeout = GIT_TIMEOUT if timeout is None else timeout
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            ["git", *args],  # noqa: S607 - git from PATH (tests put a push-refusing shim first)
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=clean_env({"GIT_TERMINAL_PROMPT": "0"}),  # hooks run target repos' pre-commit (T1836)
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"git {' '.join(args)} timed out after {timeout:g} s in {cwd}"
        raise GitError(msg, "run_failed") from exc
    if check and proc.returncode:
        msg = f"git {args[0]} failed in {cwd}: {output_tail(proc)}"
        raise GitError(msg, "run_failed")
    return proc


def output_tail(proc: subprocess.CompletedProcess[str], limit: int = 600) -> str:
    """Return the end of stdout then stderr of a finished command: findings print on either."""
    both = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
    return both[-limit:]


def repo_dir(repo: str | None) -> Path:
    """Return the local clone of a note's repo, or NeedsYouError saying what is missing."""
    if not repo:
        msg = "The note has no repo: set kuhyx/<name> on it, or do it yourself"
        raise NeedsYouError(msg, "handed_to_you")
    owner, _, name = repo.rpartition("/")
    if owner not in ("", OWNER):
        msg = f"Repo {repo} is not a {OWNER}/ repo; only ~/src clones of those run here"
        raise NeedsYouError(msg, "run_failed")
    path = repo_path(f"{OWNER}/{name}")  # the owner lets it find a clone in a differently named directory
    if not (path / ".git").exists():
        msg = f"Repo {repo} is not cloned at {path}: clone it there, then start again"
        raise NeedsYouError(msg, "handed_to_you")
    return path


def base_ref(repo: Path) -> tuple[str, str]:  # noqa: D103
    for branch in ("main", "master"):
        if (
            git(
                repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}", check=False
            ).returncode
            == 0
        ):
            return f"origin/{branch}", branch
    msg = f"{repo} has no origin/main or origin/master to branch from"
    raise NeedsYouError(msg, "run_failed")


def copy_machine_local(repo: Path, wt: Path) -> None:
    """Copy the repo's ignored MACHINE_LOCAL files into the worktree where they are missing (T1860).

    Only files git ignores are copied, so `git add -A` can never ship them.
    """
    for rel in MACHINE_LOCAL:
        src, dest = repo / rel, wt / rel
        if not src.is_file() or dest.exists() or git(repo, "check-ignore", "-q", rel, check=False).returncode:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def has_conflicts(wt: Path) -> bool:
    """Return True while the worktree is mid-rebase or holds unmerged files (rebase or autostash conflict)."""
    rebasing = any(
        Path(wt, git(wt, "rev-parse", "--git-path", name).stdout.strip()).exists()  # absolute stays absolute
        for name in ("rebase-merge", "rebase-apply")
    )
    return rebasing or bool(git(wt, "diff", "--name-only", "--diff-filter=U", check=False).stdout.strip())


def _on(wt: Path, ancestor: str, descendant: str) -> bool:
    """Return True when `ancestor` is reachable from `descendant`."""
    return git(wt, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0


def unresolved(wt: Path, ref: str) -> bool:
    """Return True while a rebase onto `ref` has not gone through: conflicts open, or `ref` not in HEAD."""
    return has_conflicts(wt) or not _on(wt, ref, "HEAD")


def _sync(wt: Path, ref: str, prev_base: str | None) -> tuple[str, bool]:
    """Rebase a reused worktree onto `ref` (autostash keeps loose edits); return (base sha, rebase stopped).

    Work the session already pushed (HEAD is on origin, past the old base) stays where it is with its old
    base, so the drawer diff keeps showing it. A conflict is left as git left it, never aborted (T1864).
    """
    head = git(wt, "rev-parse", "HEAD").stdout.strip()
    if prev_base and head != prev_base and _on(wt, head, ref):
        return prev_base, False
    failed = False
    if not has_conflicts(wt):  # else an earlier conflict nobody resolved yet: leave it alone
        failed = git(wt, "rebase", "--autostash", ref, check=False).returncode != 0
    stopped = failed or has_conflicts(wt)  # a refused rebase, a stop, or an autostash that conflicts (exit 0)
    return git(wt, "merge-base", "HEAD", ref).stdout.strip(), stopped


def add(repo: Path, root: Path, run_id: str, prev_base: str | None = None, *, sync: bool = True) -> Worktree:
    """Create the run's worktree on branch `todo/<item id>` from origin's default branch, or reuse it rebased.

    A reused worktree is rebased onto origin's default branch (T1864): a card whose worktree predates work
    that already landed must not start from the old tree. `prev_base` is the base the run recorded; with
    `sync` off the reused tree is left as it is.
    """
    git(repo, "fetch", "--quiet", "origin", check=False)
    ref, remote_branch = base_ref(repo)
    path = worktree_path(root, run_id)
    branch = f"todo/{run_id}"
    reused = (path / ".git").exists()
    if not reused:
        path.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "worktree", "prune")
        exists = (
            git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0
        )
        git(repo, "worktree", "add", *([str(path), branch] if exists else ["-b", branch, str(path), ref]))
    copy_machine_local(repo, path)
    if reused and sync:
        base, stopped = _sync(path, ref, prev_base)
    else:
        keep = prev_base if reused else None  # an untouched reused tree keeps the base the run recorded
        base, stopped = keep or git(path, "merge-base", "HEAD", ref).stdout.strip(), False
    return Worktree(path, branch, base, ref, remote_branch, stopped and unresolved(path, ref))


def attach(st: RunState, repo_name: str | None, root: Path) -> None:
    """Point the run at its worktree (create or rebase it) and record base, branch and any conflict.

    No rebase while a turn of the old server is still editing the worktree (it is adopted after this), nor
    in the Ship drive: ship rebases itself and must never commit a half-rebased tree.
    """
    quiet = st.stage == "shipping" or orphans.read(root / st.task_id) is not None
    wt = add(repo_dir(repo_name), root, st.task_id, st.base_sha if st.worktree else None, sync=not quiet)
    st.worktree, st.branch, st.base_sha = str(wt.path), wt.branch, wt.base_sha
    st.extra["base_branch"] = wt.remote_branch
    if wt.conflict:
        st.extra["rebase_conflict"] = wt.base_ref
    elif not quiet:
        st.extra.pop("rebase_conflict", None)


def conflict_notes(st: RunState) -> tuple[str, ...]:
    """Return the prompt note for a rebase conflict, for as long as the session has not resolved it."""
    ref = st.extra.get("rebase_conflict")
    if ref and st.worktree and unresolved(Path(st.worktree), str(ref)):
        return (REBASE_NOTE.format(ref=ref),)
    return ()


def remove(repo: Path, wt: Path, branch: str) -> None:  # noqa: D103
    git(repo, "worktree", "remove", "--force", str(wt), check=False)
    git(repo, "branch", "-D", branch, check=False)
