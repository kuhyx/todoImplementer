"""Fakes for the gate tests: a repo whose pre-push hook demands the receipt a stamp tool leaves."""

from __future__ import annotations

from typing import TYPE_CHECKING

from runnerfakes import Env, FakeClient, executable, make_repo, sh, task
from todoimpl.runner import ship, worktree

if TYPE_CHECKING:
    from pathlib import Path

# Same contract as scripts/check_gate_stamp.sh -> ~/src/utils/scripts/gate_stamp.sh, minus pre-commit.
STAMP_TOOL = r"""#!/bin/bash
set -eu
git_dir=$(git rev-parse --git-dir)
tree=$(git rev-parse 'HEAD^{tree}')
case "$1" in
  full) printf 'one\ntwo\n' ;;
  write) echo "$tree" > "$git_dir/gate-stamp" ;;
  step) echo "$tree $2" >> "$git_dir/gate-steps"
        [ "${FAIL_STEP:-}" = "$2" ] && { echo "step $2 is red" >&2; exit 1; }
        echo "$tree $2" >> "$(git rev-parse --git-common-dir)/steps.log"
        [ "$2" = two ] && echo "$tree" > "$git_dir/gate-stamp"; exit 0 ;;
  check) stamped=$(cut -d' ' -f1 "$git_dir/gate-stamp" 2>/dev/null || true)
         [ "$stamped" = "$tree" ] || { echo "no receipt" >&2; exit 1; } ;;
esac
"""
G = "env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE git -C {}"  # a hook runs with GIT_DIR set
HOOK = "#!/bin/sh\nscripts/check_gate_stamp.sh check\n"


def gated(world: Env, tool: str = STAMP_TOOL) -> tuple[Path, worktree.Worktree, FakeClient]:
    repo = make_repo(world)
    (repo / "scripts").mkdir()
    executable(repo / "scripts" / "check_gate_stamp.sh", tool)
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-q", "-m", "gate")
    sh(repo, "git", "push", "-q", "origin", "main")
    executable(repo / ".git" / "hooks" / "pre-push", HOOK)
    wt = worktree.add(repo, world.root, "abcd1234-0")
    (wt.path / "hello.txt").write_text("hi\n", encoding="utf-8")
    return repo, wt, FakeClient({"abcd1234": task()})


def ship_plan(world: Env, repo: Path, wt: worktree.Worktree) -> ship.ShipPlan:
    item = FakeClient({"abcd1234": task()}).item("abcd1234")
    return ship.ShipPlan(repo, wt.path, wt.branch, item, [], world.root / "abcd1234-0", 10)


def steps(repo: Path) -> list[str]:
    return (repo / ".git" / "steps.log").read_text(encoding="utf-8").splitlines()
