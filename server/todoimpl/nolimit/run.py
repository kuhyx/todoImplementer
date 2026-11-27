"""One repo's visit: worktree, deps, autofixes, commit, the full gate, then push and deploy or discard.

Order: (1) the board worktree from `origin/<default>`; (2) setup (locked deps); (3) autofixes, committed on
the `nolimit/<date>` branch when they changed anything (the repo's own commit hooks run, never skipped);
(4) the full gate; (5) green: push fast-forward to origin's default branch and run the CLAUDE.md deploy,
unless `push` is off or nothing was committed; red: the commit is discarded and each failure is a ticket.
A read-only repo (no gate) runs its `lint` only and never commits.

Before each step `still()` is asked again: False ends the visit at once (`stopped`, a Claude route opened).
A step cut at 60 s ends the visit (`slow`) and files its slow-step ticket.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.runner import deployline
from todoimpl.runner.worktree import GitError

from . import fixes, status, steps, tickets, worktree

if TYPE_CHECKING:
    from collections.abc import Callable

    from .repos import Repo
    from .worktree import Tree

COMMIT = "git add -A && git commit -q -m 'Apply lint and format autofixes' -m 'No-limit runner.'"
PUSH = (
    "git fetch -q origin && git merge-base --is-ancestor origin/{base} HEAD && git push -q origin HEAD:{base}"
)


class EndedError(Exception):
    """The visit ends early with `result`."""

    def __init__(self, result: str) -> None:
        """Carry the visit's result."""
        super().__init__(result)
        self.result = result


class Visit:
    """One repo's steps; `run()` returns the result `status` records."""

    def __init__(self, repo: Repo, now: float, still: Callable[[], bool], *, push: bool) -> None:
        """Nothing runs until `run()`."""
        self.repo, self.now, self.still, self.push = repo, now, still, push
        self.red = False

    def step(self, name: str, command: str, tree: Tree) -> steps.Step:
        """Run one step unless a route opened; a cut step ends the visit, a red one files its failures."""
        if not self.still():
            raise EndedError(status.STOPPED)
        done = steps.run(name, command, tree.path)
        if done.slow:
            tickets.slow(self.repo, done, self.now)
            raise EndedError(status.SLOW)
        if not done.passed:
            tickets.red(self.repo, done, self.now)
            self.red = True
        return done

    def run(self) -> str:
        """Visit the repo; return its result."""
        try:
            return self._visit()
        except EndedError as stop:
            return stop.result
        except GitError as exc:
            tickets.red(self.repo, steps.failed("git", "git fetch/worktree", str(exc)), self.now)
            return status.RED

    def _visit(self) -> str:
        if not self.still():
            return status.STOPPED
        tree = worktree.prepare(self.repo, self.now)
        for name, command in fixes.setup(tree.path):
            if not self.step(name, command, tree).passed:
                return status.RED
        if left := worktree.changes(tree):  # the fix commit would carry them: a lockfile that is not frozen
            tickets.red(self.repo, steps.failed("setup-dirty", "git status --porcelain", left), self.now)
            return status.RED
        if self.repo.gate is None:
            lint = self.repo.commands.get("lint")
            ok = lint is None or self.step("lint", lint, tree).passed
            worktree.discard(tree)
            return status.READONLY if ok else status.RED
        return self._gate(tree, self.repo.gate)

    def _gate(self, tree: Tree, gate: str) -> str:
        for name, command in fixes.autofix(tree.path):
            if not self.step(name, command, tree).passed:
                worktree.discard(tree)
        if worktree.dirty(tree):
            self.step("commit", COMMIT, tree)
        if not self.step("gate", gate, tree).passed or self.red:
            worktree.discard(tree)
            return status.RED
        tickets.resolve(self.repo)
        if not (self.push and worktree.ahead(tree)):
            return status.GREEN
        if not self.step("push", PUSH.format(base=tree.base), tree).passed:
            return status.RED
        deploy = deployline.declared(deployline.claude_md(tree.path))
        if deploy is None or deployline.is_none(deploy):
            return status.PUSHED
        return status.DEPLOYED if self.step("deploy", deploy, tree).passed else status.RED


def visit(repo: Repo, now: float, still: Callable[[], bool] = lambda: True, *, push: bool = True) -> str:
    """Visit one repo and return its result (`status.RESULTS`)."""
    return Visit(repo, now, still, push=push).run()
