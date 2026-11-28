"""Remember the last tree `make fast` passed on, so the pre-commit hook can skip a second full gate (T2410).

The stall watch (2026-11-20) showed every quiet stretch over 60 s on this repo's own cards was the gate: a
session ran `make fast`, then `git commit` ran it again through pre-commit on the very same files. The key is
the tree object of the whole working tree (tracked and untracked, minus ignored files), built in a scratch
index so the real index is never touched. `make fast` records the key it computed before it started, so an
edit made while the gate ran leaves the stamp stale. The tests are hermetic, so the same tree gives the same
result.

A board session runs the gate one step per call instead (T2485): `make private`, `make web-build`, six test
shards and `make test-cov`. Each step marks the tree it passed on (`mark`: one file per step in `fast-steps/`), and
a tree that every step marked is as fresh as one `make fast` passed on: the BASE steps plus either one whole
`test` run or all N shards of one sharding together with `cov-of-<N>` (written by `make test-cov` once every
shard marker exists; no coverage is measured since 2026-11-27).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

STAMP = "fast-green"
SCRATCH = "fast-key-index"
STEPS = "fast-steps"
BASE = ("private", "md", "web-build", "web-test")
COV = re.compile(r"cov-of-([1-9]\d*)")


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
    scratch = _git_path(repo, f"{SCRATCH}.{os.getpid()}")  # steps run side by side: one scratch index each
    env = {**os.environ, "GIT_INDEX_FILE": str(scratch)}
    try:
        _git(repo, "add", "-A", env=env)
        return _git(repo, "write-tree", env=env)
    finally:
        scratch.unlink(missing_ok=True)


def record(repo: Path, tree: str) -> None:
    """Remember that `make fast` passed on `tree`."""
    _git_path(repo, STAMP).write_text(tree + "\n")


def mark(repo: Path, step: str, tree: str) -> None:
    """Remember that one gate step passed on `tree`."""
    folder = _git_path(repo, STEPS)
    folder.mkdir(exist_ok=True)
    (folder / step).write_text(tree + "\n")


def _marked(repo: Path, tree: str) -> set[str]:
    """Return the steps whose last pass was on `tree`."""
    folder = _git_path(repo, STEPS)
    files = folder.iterdir() if folder.is_dir() else iter(())
    return {f.name for f in files if f.read_text().strip() == tree}


def _tested(done: set[str]) -> bool:
    """Tell whether the marked steps hold one whole test run: `test`, or N shards plus `cov-of-<N>`."""
    if "test" in done:
        return True
    shardings = (int(m[1]) for step in done if (m := COV.fullmatch(step)))
    return any(all(f"shard{k}of{n}" in done for k in range(1, n + 1)) for n in shardings)


def _steps_cover(done: set[str]) -> bool:
    """Tell whether the marked steps add up to a whole `make fast`."""
    return done.issuperset(BASE) and _tested(done)


def fresh(repo: Path) -> bool:
    """Tell whether the working tree is one `make fast`, or every one of its steps, last passed on."""
    stamp = _git_path(repo, STAMP)
    tree = key(repo)
    return (stamp.is_file() and stamp.read_text().strip() == tree) or _steps_cover(_marked(repo, tree))


def main(argv: list[str]) -> int:
    """`key [repo]` prints the key, `record <repo> <key>` stores it, `check [repo]` exits 0 when fresh."""
    match argv:
        case ["key", *rest]:
            print(key(Path(rest[0] if rest else ".")))
            return 0
        case ["record", repo, tree]:
            record(Path(repo), tree)
            return 0
        case ["mark", repo, step, tree]:
            mark(Path(repo), step, tree)
            return 0
        case ["tested", repo, tree]:
            return 0 if _tested(_marked(Path(repo), tree)) else 1
        case ["check", *rest]:
            return 0 if fresh(Path(rest[0] if rest else ".")) else 1
        case _:
            usage = "key [repo] | record <repo> <key> | mark <repo> <step> <key> | tested <repo> <key>"
            print(f"usage: fast_stamp.py {usage} | check [repo]", file=sys.stderr)
            return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
