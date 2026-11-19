"""Ship (click or auto-ship): one `Todo: <id8>` commit, rebase, recheck, push, close the item, clean up."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from todoimpl.repotask import files
from todoimpl.todo_mcp.model import TodoError

from . import deploy, deployline, gate
from .checks import CheckResult, run_all
from .files import NeedsYouError
from .worktree import base_ref, git, has_conflicts, output_tail, remove

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.todo_mcp.items import Item
    from todoimpl.todo_mcp.model import Task

SUBJECT_MAX = 50
EVIDENCE_TAIL = 8
PUSH_TIMEOUT = 600.0
PUSH_TRIES = 3  # a push that lost a race is rebased and gated again, this many pushes in all
OUTPUT_TAIL = 3000
REBASING = "rebasing"  # in the run dir while Ship's own rebase runs: a restart may leave it half done


class CommitRefusedError(NeedsYouError):
    """`git commit` failed; `output` is what the hooks printed."""

    def __init__(self, output: str) -> None:  # noqa: D107
        super().__init__(f"git commit was refused: {output[-600:]}", "run_failed")
        self.output = output


class RedAfterRebaseError(NeedsYouError):
    """The checks are red on the rebased tree; `output` briefs the session's fix turn (T2008)."""

    def __init__(self, text: str, tail: str) -> None:  # noqa: D107
        super().__init__(text, "checks_failed")
        ask = "Fix them yourself: commit, rebase, push, deploy (you have permission)."
        self.output = f"{tail[-1800:]}\n\n{text}. {ask}"


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
    base_sha: str = ""  # where the run's branch began: the session's own commits are base_sha..HEAD
    step: Callable[[str], None] = lambda _step: None  # told each step the ship enters (T2060)


def commit_message(title: str, id8: str) -> str:  # noqa: D103
    subject = " ".join(title.split()) or f"Todo {id8}"
    if len(subject) > SUBJECT_MAX:
        subject = subject[: SUBJECT_MAX - 1].rstrip() + "…"
    return f"{subject}\n\nTodo: {id8}\n"


def evidence(sha: str, branch: str, results: list[CheckResult], live: str = "", head: str = "") -> str:
    """Return the close evidence: the commit (or no code change), the live-check summary, each check tail.

    The deploy is a result like any check (`deploy `<command>` exit 0:`), the last one.
    """
    head = head or (f"Shipped {sha[:12]} to origin/{branch}." if sha else "Closed with no code change.")
    parts = [head, *([live] if live else [])]
    for r in results:
        tail = "\n".join(r.tail.splitlines()[-EVIDENCE_TAIL:])
        parts.append(f"{r.name} `{r.command}` exit {r.exit_code}:\n{tail}".rstrip())
    return "\n".join(parts if results else [*parts, "No checks were found."])


def _on_origin(wt: Path, ref: str) -> bool:
    """Return True when HEAD is already on `ref`."""
    return git(wt, "merge-base", "--is-ancestor", "HEAD", ref, check=False).returncode == 0


def _landed(plan: ShipPlan, ref: str) -> list[str]:
    """Short shas of the commits the session already pushed, when nothing is left for Ship to push (T1865)."""
    wt = plan.worktree
    if not plan.base_sha or git(wt, "status", "--porcelain").stdout.strip() or not _on_origin(wt, ref):
        return []
    return git(wt, "rev-list", "--reverse", "--abbrev-commit", f"{plan.base_sha}..HEAD").stdout.split()


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
    title, notes = files.commit_identity(plan.item, plan.run_dir)
    message = commit_message(title, "\nTodo: ".join(notes))
    commit = git(wt, "commit", "--quiet", "-m", message, check=False, timeout=plan.timeout)
    if commit.returncode:
        raise CommitRefusedError(output_tail(commit, OUTPUT_TAIL))
    return True


def _rebase(plan: ShipPlan, ref: str) -> None:
    wt = plan.worktree
    mark = plan.run_dir / REBASING  # a restart can kill the rebase half way: the next ship aborts it (T1988)
    mark.write_text("1", encoding="utf-8")
    if git(wt, "rebase", ref, check=False, timeout=plan.timeout).returncode == 0:
        mark.unlink()
        return
    files = git(wt, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
    git(wt, "rebase", "--abort", check=False)
    mark.unlink()
    where = ", ".join(files) or "unknown files"
    msg = f"Rebase on {ref} conflicts in {where}: resolve it in {wt}, then Retry"
    raise NeedsYouError(msg, "run_failed")


def _verified(plan: ShipPlan, ref: str, *, changed: bool) -> list[CheckResult]:
    """Rerun the checks on the rebased tree, then the repo's pre-push gate (it leaves the hook's receipt)."""
    results, _ = run_all(plan.checks, plan.worktree, plan.run_dir, plan.timeout)
    if red := [r for r in results if not r.passed]:
        msg = f"Checks went red after the rebase on {ref}: {', '.join(r.name for r in red)}"
        tail = "\n\n".join(f"== {r.name}: {r.command} (exit {r.exit_code})\n{r.tail}" for r in red)
        raise RedAfterRebaseError(msg, tail)
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
    if (plan.run_dir / REBASING).exists():  # a restart cut Ship's own rebase (never kuhy's or the session's)
        git(wt, "rebase", "--abort", check=False)
        (plan.run_dir / REBASING).unlink()
    if has_conflicts(wt):  # `add --all` would commit the markers as if resolved
        msg = f"Unresolved conflicts in {wt}: resolve them and finish the rebase, then Retry"
        raise NeedsYouError(msg, "run_failed")
    if (own := deploy.pushed(plan.run_dir, wt)) and _on_origin(wt, ref):  # a Retry after this ship's own push
        kept = {
            "commit": own["commit"],
            "pushed_at": own["pushed_at"],
        }  # checked then: only the deploy is left
        return _finish(plan, client, now, kept, [CheckResult(**row) for row in own["results"]], branch)
    if landed := _landed(plan, ref):  # the session pushed its own work: check it, deploy it, close (T1964)
        command = deployline.command_of(wt, plan.item.repo)  # no line: stop before the checks run
        plan.step("running the checks")
        results = _verified(plan, ref, changed=False)
        said = f"Pushed by the session: {', '.join(landed)}."
        head = git(wt, "rev-parse", "HEAD").stdout.strip()
        return _finish(plan, client, now, {"commit": head}, results, branch, said, command)
    plan.step("squashing the work")
    changed = _squash(plan, ref, allow_empty=allow_empty)
    if changed:
        plan.step("rebasing")
        _rebase(plan, ref)
    plan.step("running the checks")
    results = _verified(plan, ref, changed=changed)
    info: dict[str, Any] = {"commit": ""}
    if changed:
        plan.step("pushing")
        info.update(commit=_push_rebasing(plan, ref, branch, results), pushed_at=now())
        deploy.mark_pushed(plan.run_dir, str(info["commit"]), info["pushed_at"], results)
    return _finish(plan, client, now, info, results, branch)


def _finish(  # noqa: PLR0913, PLR0917 - one ship's parts
    plan: ShipPlan,
    client: Closer,
    now: Callable[[], float],
    info: dict[str, Any],
    results: list[CheckResult],
    branch: str,
    head: str = "",
    command: str | None = None,
) -> dict[str, Any]:
    """Deploy what was pushed (a close with no code change deploys nothing), then close with the evidence."""
    if info["commit"]:
        plan.step("deploying")
        card = f"{plan.item.note_id}-{plan.item.index}"
        results = [*results, deploy.run(plan.worktree, plan.run_dir, card, plan.item.repo, command)]
    text = evidence(str(info["commit"]), branch, results, plan.live_summary, head)
    return _close(plan, client, text, info, now)


def _close(
    plan: ShipPlan, client: Closer, text: str, info: dict[str, Any], now: Callable[[], float]
) -> dict[str, Any]:
    """Close the note with `text` as evidence, remove the worktree, and return `info` plus the close time."""
    sha = str(info["commit"])
    plan.step("closing the note")
    try:
        client.close_task(f"{plan.item.note_id}-{plan.item.index}", text)
    except TodoError as exc:
        done = f"Pushed {sha[:8]}" if sha else "Nothing to push"
        msg = f"{done} but closing the note failed: {exc}"
        raise NeedsYouError(msg, "run_failed") from exc
    remove(plan.repo, plan.worktree, plan.branch)
    return {**info, "closed_at": now()}
