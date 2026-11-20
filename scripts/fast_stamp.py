"""Remember the last tree `make fast` passed on, so the pre-commit hook can skip a second full gate (T2410).

The stall watch (2026-11-20) showed every quiet stretch over 60 s on this repo's own cards was the gate: a
session ran `make fast`, then `git commit` ran it again through pre-commit on the very same files. The key is
the tree object of the whole working tree (tracked and untracked, minus ignored files), built in a scratch
index so the real index is never touched. `make fast` records the key it computed before it started, so an
edit made while the gate ran leaves the stamp stale. The tests are hermetic, so the same tree gives the same
result.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

STAMP = "fast-green"
SCRATCH = "fast-key-index"


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """Run git in `repo` and return its stdout, stripped."""
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "-C", str(repo), *args],  # noqa: S607 - git from PATH, like every gate script
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def _git_path(repo: Path, name: str) -> Path:
    """Return `name` under this worktree's own git dir (a linked worktree has one of its own)."""
    return (repo / _git(repo, "rev-parse", "--git-path", name)).resolve()


def key(repo: Path) -> str:
    """Return the tree hash of the working tree as it is on disk."""
    scratch = _git_path(repo, SCRATCH)
    env = {**os.environ, "GIT_INDEX_FILE": str(scratch)}
    try:
        _git(repo, "add", "-A", env=env)
        return _git(repo, "write-tree", env=env)
    finally:
        scratch.unlink(missing_ok=True)


def record(repo: Path, tree: str) -> None:
    """Remember that `make fast` passed on `tree`."""
    _git_path(repo, STAMP).write_text(tree + "\n")


def fresh(repo: Path) -> bool:
    """Tell whether the working tree is the one `make fast` last passed on."""
    stamp = _git_path(repo, STAMP)
    return stamp.is_file() and stamp.read_text().strip() == key(repo)


def main(argv: list[str]) -> int:
    """`key [repo]` prints the key, `record <repo> <key>` stores it, `check [repo]` exits 0 when fresh."""
    match argv:
        case ["key", *rest]:
            print(key(Path(rest[0] if rest else ".")))
            return 0
        case ["record", repo, tree]:
            record(Path(repo), tree)
            return 0
        case ["check", *rest]:
            return 0 if fresh(Path(rest[0] if rest else ".")) else 1
        case _:
            print("usage: fast_stamp.py key [repo] | record <repo> <key> | check [repo]", file=sys.stderr)
            return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
