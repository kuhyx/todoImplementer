"""Ship (click or auto-ship): one `Todo: <id8>` commit, rebase, recheck, push, close the item, clean up."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from todoimpl.todo_mcp.model import TodoError

from . import gate
from .checks import run_all
from .files import NeedsYouError
from .worktree import base_ref, git, output_tail, remove

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.todo_mcp.items import Item
    from todoimpl.todo_mcp.model import Task

    from .checks import CheckResult

SUBJECT_MAX = 50
EVIDENCE_TAIL = 8
PUSH_TIMEOUT = 600.0
PUSH_TRIES = 3  # a push that lost a race is rebased and gated again, this many pushes in all
OUTPUT_TAIL = 3000


class CommitRefusedError(NeedsYouError):
    """`git commit` failed; `output` is what the hooks printed."""

    def __init__(self, output: str) -> None:  # noqa: D107
        super().__init__(f"git commit was refused: {output[-600:]}", "run_failed")
        self.output = output


class Closer(Protocol):
    """The part of the service's ItemView a run needs: closing a card and adding the live-check follow-up."""

    def close_task(self, card: str, evidence: str) -> None: ...  # noqa: D102
    def add_task(self, repo: str, title: str, body: str = "") -> Task: ...  # noqa: D102


@dataclass(frozen=True)
class ShipPlan:
    """Everything one ship needs; `checks` are rerun after the rebase."""

    repo: Path
    worktree: Path
    branch: str
    item: Item
    checks: list[tuple[str, str]]
    run_dir: Path
    timeout: float
    live_summary: str = ""


def commit_message(title: str, id8: str) -> str:  # noqa: D103
    subject = " ".join(title.split()) or f"Todo {id8}"
    if len(subject) > SUBJECT_MAX:
        subject = subject[: SUBJECT_MAX - 1].rstrip() + "…"
    return f"{subject}\n\nTodo: {id8}\n"


def evidence(sha: str, branch: str, results: list[CheckResult], live: str = "") -> str:
    """Return the close evidence: the commit (or no code change), the live-check summary, each check tail."""
    head = f"Shipped {sha[:12]} to origin/{branch}." if sha else "Closed with no code change."
    parts = [head, *([live] if live else [])]
    for r in results:
        tail = "\n".join(r.tail.splitlines()[-EVIDENCE_TAIL:])
        parts.append(f"{r.name} `{r.command}` exit {r.exit_code}:\n{tail}".rstrip())
    return "\n".join(parts if results else [*parts, "No checks were found."])


def _squash(plan: ShipPlan, ref: str, *, allow_empty: bool) -> bool:
    """Fold the work into one commit on the merge base; return False when there is nothing to commit."""
    wt = plan.worktree
    git(wt, "add", "--all")
    git(wt, "reset", "--soft", git(wt, "merge-base", "HEAD", ref).stdout.strip())
    if git(wt, "diff", "--cached", "--quiet", check=False).returncode == 0:
        if allow_empty:
            return False
        msg = "Nothing to ship: the worktree has no changes against its base"
        raise NeedsYouError(msg, "run_failed")
    message = commit_message(plan.item.title, plan.item.note_id)
    commit = git(wt, "commit", "--quiet", "-m", message, check=False, timeout=plan.timeout)
    if commit.returncode:
        raise CommitRefusedError(output_tail(commit, OUTPUT_TAIL))
    return True


def _rebase(plan: ShipPlan, ref: str) -> None:
    wt = plan.worktree
    if git(wt, "rebase", ref, check=False, timeout=plan.timeout).returncode == 0:
        return
    files = git(wt, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
    git(wt, "rebase", "--abort", check=False)
    where = ", ".join(files) or "unknown files"
    msg = f"Rebase on {ref} conflicts in {where}: resolve it in {wt}, then ship again"
    raise NeedsYouError(msg, "run_failed")


def _verified(plan: ShipPlan, ref: str, *, changed: bool) -> list[CheckResult]:
    """Rerun the checks on the rebased tree, then the repo's pre-push gate (it leaves the hook's receipt)."""
    results, _ = run_all(plan.checks, plan.worktree, plan.run_dir, plan.timeout)
    red = [r.name for r in results if not r.passed]
    if red:
        msg = f"Checks went red after the rebase on {ref}: {', '.join(red)}"
        raise NeedsYouError(msg, "checks_failed")
    card = f"{plan.item.note_id}-{plan.item.index}"
    return results + (gate.run(plan.worktree, plan.run_dir, card) if changed else [])


def _push(plan: ShipPlan, branch: str) -> tuple[str, str]:
    """Push HEAD to origin's default branch; return (sha, "") or ("", what git said when it refused)."""
    sha = git(plan.worktree, "rev-parse", "HEAD").stdout.strip()
    push = git(
        plan.worktree, "push", "origin", f"HEAD:refs/heads/{branch}", check=False, timeout=PUSH_TIMEOUT
    )
    return ("", output_tail(push, 400)) if push.returncode else (sha, "")


def _push_rebasing(plan: ShipPlan, ref: str, branch: str, results: list[CheckResult]) -> str:
    """Push; if origin moved meanwhile, rebase, verify and gate the new tree, and push again (T1838)."""
    for attempt in range(1, PUSH_TRIES + 1):
        sha, refusal = _push(plan, branch)
        if sha:
            return sha
        git(plan.worktree, "fetch", "--quiet", "origin")
        raced = git(plan.worktree, "merge-base", "--is-ancestor", ref, "HEAD", check=False).returncode != 0
        if attempt == PUSH_TRIES or not raced:
            head = git(plan.worktree, "rev-parse", "HEAD").stdout.strip()
            msg = f"Push of {head[:8]} to origin/{branch} was refused: {refusal}"
            raise NeedsYouError(msg, "run_failed")
        _rebase(plan, ref)
        results[:] = _verified(plan, ref, changed=True)
    raise AssertionError  # pragma: no cover - the loop always returns or raises


def ship(
    plan: ShipPlan, client: Closer, now: Callable[[], float], *, allow_empty: bool = False
) -> dict[str, Any]:
    """Run the whole ship; any refusal raises NeedsYouError and leaves the worktree in place.

    `allow_empty` (auto-ship only) closes a run with no diff without a commit or push; `commit` is then "".
    """
    wt = plan.worktree
    git(wt, "fetch", "--quiet", "origin")
    ref, branch = base_ref(plan.repo)
    changed = _squash(plan, ref, allow_empty=allow_empty)
    if changed:
        _rebase(plan, ref)
    results = _verified(plan, ref, changed=changed)
    info: dict[str, Any] = {"commit": ""}
    if changed:
        info.update(commit=_push_rebasing(plan, ref, branch, results), pushed_at=now())
    sha = str(info["commit"])
    try:
        client.close_task(
            f"{plan.item.note_id}-{plan.item.index}", evidence(sha, branch, results, plan.live_summary)
        )
    except TodoError as exc:
        done = f"Pushed {sha[:8]}" if sha else "Nothing to push"
        msg = f"{done} but closing the note failed: {exc}"
        raise NeedsYouError(msg, "run_failed") from exc
    remove(plan.repo, wt, plan.branch)
    return {**info, "closed_at": now()}
