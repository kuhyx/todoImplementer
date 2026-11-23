"""T2521: a git failure once the stray stash is made still files the ticket and redeploys."""

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING, Any

import pytest
from runnerfakes import Env, make_repo, sh
from schedfakes import CARD
from todoimpl.errors.sources import state_base
from todoimpl.runner import deploy, deployheal, stray, worktree
from todoimpl.runner.worktree import GitError

if TYPE_CHECKING:
    import subprocess
    from pathlib import Path

PUSH = ("stash", "push")


def _repo(world: Env) -> tuple[Path, Path, Path]:
    """Push a commit changing `b.txt`, leave a stray edit of it at rest; return (worktree, run, checkout)."""
    md = "# demo\n\n## Commands\n\n- deploy: `true`\n"
    checkout = make_repo(world, files={"CLAUDE.md": md, "b.txt": "old b\n"})
    wt = worktree.add(checkout, world.root, CARD).path
    (wt / "b.txt").write_text("new b\n", encoding="utf-8")
    sh(wt, "git", "commit", "-qam", "incoming")
    sh(wt, "git", "push", "-q", "origin", "HEAD:main")
    (checkout / "b.txt").write_text("stray b\n", encoding="utf-8")
    os.utime(checkout / "b.txt", (time.time() - deployheal.QUIET - 60,) * 2)
    return wt, world.root / CARD, checkout


def _broken(hits: list[str], sub: tuple[str, ...]) -> Any:
    """Return a git whose `sub` command raises GitError once the stash push ran (a push: after it ran)."""
    real = worktree.git
    pushed: list[bool] = []

    def fake(cwd: Path, *args: str, **kw: Any) -> subprocess.CompletedProcess[str]:
        if args[:2] == PUSH:
            pushed.append(True)
            done = real(cwd, *args, **kw)
            if sub != PUSH:
                return done
        elif not pushed or args[: len(sub)] != sub:
            return real(cwd, *args, **kw)
        hits.append(" ".join(sub))
        msg = f"git {' '.join(sub)} timed out after 30 s in {cwd}"
        raise GitError(msg, "run_failed")

    return fake


@pytest.mark.parametrize("sub", [("status",), ("stash", "list"), PUSH])
def test_t2521_a_git_failure_after_the_stash_files_the_ticket_and_redeploys(
    world: Env, monkeypatch: pytest.MonkeyPatch, sub: tuple[str, ...]
) -> None:
    wt, run_dir, checkout = _repo(world)
    hits: list[str] = []
    monkeypatch.setattr(deployheal, "git", _broken(hits, sub))
    done = deploy.run(wt, run_dir, CARD, "kuhyx/demo", f"git -C {checkout} pull -q --ff-only")
    assert hits  # the failing git command really ran after the stash
    assert done.passed  # the rerun pull went through: no Needs you
    assert "for Claude" in done.tail
    (tag,) = sh(checkout, "git", "stash", "list", "--format=%gs").splitlines()  # the work stays in the stash
    path = state_base() / "app-errors" / stray.FILE
    (row,) = json.loads(path.read_text(encoding="utf-8"))["errors"]
    assert tag.rpartition(": ")[2] in row["detail"]  # the ticket names the stash tag
    sh(checkout, "git", "checkout", "-q", "HEAD~1")
    sh(checkout, "git", "stash", "pop", "-q")  # nothing was lost
    assert (checkout / "b.txt").read_text(encoding="utf-8") == "stray b\n"
