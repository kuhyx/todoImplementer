"""Run a free worker with kuhy's checkouts read-only: a real barrier, not a rule it may ignore (T2519).

T2515's deny rules stop the writer tools only; a worker's shell (`sed -i`, `>`, `git apply`) still reached
`~/src/<other repo>`. `wrap` returns a bubblewrap prefix that sees the whole filesystem as it is but mounts
the src root read-only, then its worktree and the git dir behind it (`git worktree add` keeps index, refs
and objects in `~/src/<repo>/.git`) writable again, so the worker still commits. No new network
or pid namespace: the worker runs as before otherwise. Free workers only: board turns stay unrestricted
(a deploy pulls in `~/src/<repo>`), and they get the before/after check in `srcguard`.
"""

from __future__ import annotations

import functools
import shutil
import subprocess
from pathlib import Path

from . import worktree as git_tree

BWRAP = "bwrap"
PROBE_TIMEOUT = 10.0
SHARE_ALL = ("--dev-bind", "/", "/")


@functools.cache
def _works(tool: str) -> bool:
    """Say whether bwrap can make its mount namespace here (user namespaces can be off)."""
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [tool, *SHARE_ALL, "--", "true"], capture_output=True, timeout=PROBE_TIMEOUT, check=False
        )
    except OSError, subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


def _git_dirs(worktree: Path) -> list[Path]:
    """Return the worktree's shared git dir (absolute); [] when it is no repo."""
    out = git_tree.git(
        worktree, "rev-parse", "--path-format=absolute", "--git-common-dir", check=False
    ).stdout
    return [Path(line) for line in out.splitlines()]


def wrap(worktree: Path, src: Path) -> tuple[list[str], str | None]:
    """Return (argv prefix, why there is none): the prefix keeps `src` read-only but the worker's dirs.

    No src root = nothing to guard (no prefix, no reason). No bwrap, or one that cannot sandbox here = no
    prefix and the reason, so the caller logs that the worker ran unguarded.
    """
    if not src.is_dir():
        return [], None
    tool = shutil.which(BWRAP)
    if tool is None:
        return [], "bwrap is not installed"
    if not _works(tool):
        return [], "bwrap cannot make a sandbox here"
    root = src.resolve()
    argv = [tool, *SHARE_ALL, "--ro-bind", str(root), str(root)]
    for path in (worktree.resolve(), *(p.resolve() for p in _git_dirs(worktree))):
        if path.is_relative_to(root):
            argv += ["--bind", str(path), str(path)]
    return [*argv, "--die-with-parent", "--"], None
