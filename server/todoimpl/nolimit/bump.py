"""Repo step: bump dependency pins to the newest stable versions, kept only when the full gate stays green.

After the visit's gate is green: `~/.claude/scripts/apply_dep_pins.py .` rewrites the manifests to the pins
the freshness gate asks for (exit 1 = some left for a human, 2 = the gate could not ask the registries, e.g.
offline: neither is a failure of the repo). When it changed anything, the lockfiles follow (`uv lock`,
`pnpm install --lockfile-only`, `flutter pub get`), one commit holds it all (the repo's own hooks run), and
the gate runs again. Green: the commit stays and the visit pushes it. Red: the commit is dropped
(`reset --hard HEAD~1`, the autofix commit before it stays) and each failure is a `nolimit-bump-*` ticket.
Every command is one capped step under 60 s; the script missing is a ticket, never a silent skip.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import fixes, steps, tickets, worktree

if TYPE_CHECKING:
    from .repos import Repo
    from .worktree import Tree

GATE = Path("scripts") / "check_dependency_freshness.sh"
SCRIPT = Path(".claude") / "scripts" / "apply_dep_pins.py"
BUMP = "python3 {script} . ; c=$?; [ $c -le 2 ]"
LOCKS = (
    ("uv.lock", "bump-uv", "uv lock --quiet"),
    ("pnpm-lock.yaml", "bump-pnpm", "pnpm install --lockfile-only --reporter=silent"),
    ("pubspec.lock", "bump-pub", "flutter pub get"),
)
COMMIT = "git add -A && git commit -q -m 'Bump dependency pins to the newest stable' -m 'No-limit runner.'"
KEPT, NONE, DROPPED, FAILED, SLOW = "kept", "none", "dropped", "failed", "slow"


def _ok(repo: Repo, done: steps.Step, now: float) -> bool:
    """Say whether a step passed; a cut or red one files its ticket."""
    if done.slow:
        tickets.slow(repo, done, now)
    elif not done.passed:
        tickets.red(repo, done, now)
    return done.passed


def _commit(repo: Repo, tree: Tree, now: float) -> bool:
    """Relock every lockfile the bump touched and commit; False (changes dropped) when a step failed."""
    relock = [(n, fixes.in_dir(rel, c)) for f, n, c in LOCKS for rel in fixes.locked(tree.path, f)]
    for name, command in [*relock, ("bump-commit", COMMIT)]:
        if not _ok(repo, steps.run(name, command, tree.path), now):
            worktree.discard_changes(tree)
            return False
    return True


def _regate(repo: Repo, tree: Tree, gate: str, now: float) -> str:
    """Run the gate on the bump commit; drop the commit when it is not green."""
    again = steps.run("bump-gate", gate, tree.path)
    if again.passed:
        return KEPT
    worktree.drop_last(tree)
    if again.slow:
        tickets.slow(repo, again, now)
        return SLOW
    tickets.red(repo, steps.Step("bump", again.command, again.exit_code, again.tail, again.seconds), now)
    return DROPPED


def run(repo: Repo, tree: Tree, gate: str, now: float) -> str:
    """Bump, relock, commit and re-gate; return what happened (`KEPT` means a commit to push).

    A repo without the freshness gate (`scripts/check_dependency_freshness.sh`) has no pins to bump.
    """
    if not (tree.path / GATE).is_file():
        return NONE
    script = Path.home() / SCRIPT
    if not script.is_file():
        tickets.red(repo, steps.failed("bump", "apply_dep_pins.py", f"{script} is missing"), now)
        return FAILED
    if not _ok(repo, steps.run("bump", BUMP.format(script=script), tree.path), now):
        worktree.discard_changes(tree)
        return FAILED
    if not worktree.dirty(tree):
        return NONE
    return _regate(repo, tree, gate, now) if _commit(repo, tree, now) else FAILED
