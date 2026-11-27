"""Repo step: bump dependency pins to the newest stable versions, kept only when the full gate stays green.

Before the visit's one gate run (T2617: the suite once, not once per commit),
`~/.claude/scripts/apply_dep_pins.py .` rewrites the manifests to the pins the freshness gate asks for (exit 1
= some left for a human, 2 = the gate could not ask the registries, e.g. offline: neither is a failure of the
repo). When it changed anything, the lockfiles follow (`uv lock`, `pnpm install --lockfile-only`, `flutter pub
get`), the setup installs them so the gate tests the new versions, and one commit holds it all (the repo's own
hooks run). The gate then runs on the autofix and bump commits together. Green: both are pushed. Red: `undo`
drops the bump commit (`reset --hard HEAD~1`, the autofix commit before it stays) and reinstalls the old pins,
and the visit gates the base again: green there makes the red run a `nolimit-bump` ticket (`blame`), red there
is the base's own failure.
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
COMMITTED, NONE, FAILED = "committed", "none", "failed"


def _ok(repo: Repo, done: steps.Step, now: float) -> bool:
    """Say whether a step passed; a cut or red one files its ticket."""
    if done.slow:
        tickets.slow(repo, done, now)
    elif not done.passed:
        tickets.red(repo, done, now)
    return done.passed


def _install(repo: Repo, tree: Tree, now: float, prefix: str) -> bool:
    """Run the setup steps (the locked deps) as `<prefix>-<step>`; False when one failed."""
    return all(_ok(repo, steps.run(f"{prefix}-{n}", c, tree.path), now) for n, c in fixes.setup(tree.path))


def _commit(repo: Repo, tree: Tree, now: float) -> bool:
    """Relock and install every lockfile the bump touched, then commit; False (changes dropped) on failure."""
    relock = [(n, fixes.in_dir(rel, c)) for f, n, c in LOCKS for rel in fixes.locked(tree.path, f)]
    ok = (
        all(_ok(repo, steps.run(n, c, tree.path), now) for n, c in relock)
        and _install(repo, tree, now, "bump")
        and _ok(repo, steps.run("bump-commit", COMMIT, tree.path), now)
    )
    if not ok:
        worktree.discard_changes(tree)
        _install(repo, tree, now, "restore")
    return ok


def apply(repo: Repo, tree: Tree, now: float) -> str:
    """Bump, relock, install and commit; return `COMMITTED` (the gate decides on it), `NONE` or `FAILED`.

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
    return COMMITTED if _commit(repo, tree, now) else FAILED


def undo(repo: Repo, tree: Tree, now: float) -> None:
    """Drop the bump commit the gate went red on and reinstall the old pins."""
    worktree.drop_last(tree)
    _install(repo, tree, now, "restore")


def blame(repo: Repo, red: steps.Step, now: float) -> None:
    """File the red gate run as the bump's (`nolimit-bump`): the base without it was green."""
    tickets.red(repo, steps.Step("bump", red.command, red.exit_code, red.tail, red.seconds), now)
