"""T2518: a stray set-aside moves every file blocking the pull; a git failure still files the ticket."""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import TYPE_CHECKING, Any

import pytest
from runnerfakes import Env, make_repo, sh
from schedfakes import CARD
from todoimpl.errors.sources import state_base
from todoimpl.runner import deploy, deployheal, srcguard, stray, worktree
from todoimpl.runner.deployheal import DirtyCheckoutError
from todoimpl.runner.files import NeedsYouError

if TYPE_CHECKING:
    from pathlib import Path


def _repo(world: Env) -> tuple[Path, Path, Path]:
    """Push a commit changing `a.txt` and `b.txt`; return (worktree, run dir, kuhy's checkout)."""
    md = "# demo\n\n## Commands\n\n- deploy: `true`\n"
    checkout = make_repo(world, files={"CLAUDE.md": md, "a.txt": "old a\n", "b.txt": "old b\n"})
    wt = worktree.add(checkout, world.root, CARD).path
    for name in ("a.txt", "b.txt"):
        (wt / name).write_text(f"new {name[0]}\n", encoding="utf-8")
    sh(wt, "git", "commit", "-qam", "incoming")
    sh(wt, "git", "push", "-q", "origin", "HEAD:main")
    return wt, world.root / CARD, checkout


def _stray(checkout: Path, files: dict[str, str]) -> None:
    """Leave a free worker's edits, at rest long enough to count as strays."""
    for name, text in files.items():
        (checkout / name).write_text(text, encoding="utf-8")
        os.utime(checkout / name, (time.time() - deployheal.QUIET - 60,) * 2)


def _command(checkout: Path, *, refusing: bool) -> str:
    pull = f"git -C {checkout} pull -q --ff-only"
    if not refusing:
        return pull
    guard = f'test -z "$(git -C {checkout} status --porcelain)" || {{ echo "{checkout} is dirty"; exit 1; }}'
    return f"{guard}; {pull}"


def _filed() -> list[dict[str, Any]]:
    path = state_base() / "app-errors" / stray.FILE
    return json.loads(path.read_text(encoding="utf-8"))["errors"] if path.exists() else []


@pytest.mark.parametrize("refusing", [False, True])
def test_t2518_a_blocking_file_equal_to_origin_is_set_aside_with_the_differing_one(
    world: Env, *, refusing: bool
) -> None:
    wt, run_dir, checkout = _repo(world)
    _stray(checkout, {"a.txt": "new a\n", "b.txt": "stray b\n"})  # a.txt already equals origin
    done = deploy.run(wt, run_dir, CARD, "kuhyx/demo", _command(checkout, refusing=refusing))
    assert done.passed
    assert sh(checkout, "git", "rev-parse", "HEAD") == sh(wt, "git", "rev-parse", "HEAD")
    (entry,) = sh(checkout, "git", "stash", "list", "--format=%gs").splitlines()  # one stash holds both
    assert f"todoimpl-stray-{CARD}" in entry
    sh(checkout, "git", "checkout", "-q", "HEAD~1")
    sh(checkout, "git", "stash", "pop", "-q")  # nothing was lost
    assert (checkout / "b.txt").read_text(encoding="utf-8") == "stray b\n"
    assert (checkout / "a.txt").read_text(encoding="utf-8") == "new a\n"


def _failing(hits: list[str], *sub: str) -> Any:
    """Return a git that fails (as git does: GitError) for the `sub` command, else runs the real one."""
    real = worktree.git

    def fake(cwd: Path, *args: str, **kw: Any) -> subprocess.CompletedProcess[str]:
        if args[: len(sub)] == sub:
            hits.append(" ".join(sub))
            return real(cwd, "rev-parse", "--verify", "no-such-ref", **{**kw, "check": True})
        return real(cwd, *args, **kw)

    return fake


@pytest.mark.parametrize(("module", "sub"), [(stray, ("ls-tree",)), (deployheal, ("stash", "show"))])
def test_t2518_a_git_failure_after_the_stash_still_files_the_stray_ticket(
    world: Env, monkeypatch: pytest.MonkeyPatch, module: object, sub: tuple[str, ...]
) -> None:
    wt, run_dir, checkout = _repo(world)
    _stray(checkout, {"b.txt": "new b\n", "extra.txt": "untracked\n"})  # tracked part merges: ls-tree runs
    hits: list[str] = []
    monkeypatch.setattr(module, "git", _failing(hits, *sub))
    done = deploy.run(wt, run_dir, CARD, "kuhyx/demo", _command(checkout, refusing=True))
    assert hits == [" ".join(sub)]  # the failing git command really ran
    assert done.passed
    (row,) = _filed()
    stash = sh(checkout, "git", "stash", "list", "--format=%H").split()[0]
    assert stash in row["detail"]  # the work stays in the stash, the ticket names it
    assert row["signature"].endswith(stray.SUFFIX)
    assert "for Claude" in done.tail


def test_t2518_a_failed_stash_show_keeps_a_patch_naming_the_stash(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir, checkout = _repo(world)
    _stray(checkout, {"b.txt": "stray b\n"})
    monkeypatch.setattr(deployheal, "git", _failing([], "stash", "show"))
    assert deploy.run(wt, run_dir, CARD, "kuhyx/demo", _command(checkout, refusing=False)).passed
    (patch,) = (run_dir / "deploy").glob("stray-*.patch")
    stash = sh(checkout, "git", "stash", "list", "--format=%H").split()[0]
    assert stash in patch.read_text(encoding="utf-8")  # each failed patch is its own ticket, never one hash


def test_t2518_no_incoming_ref_counts_as_origin_lacking_the_work(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir, checkout = _repo(world)
    _stray(checkout, {"b.txt": "stray b\n"})
    aside = deployheal.set_aside(checkout, ["b.txt"], run_dir / "deploy", CARD, time.time())
    assert aside is not None

    def gone(_checkout: Path) -> str:
        raise NeedsYouError("no origin/main or origin/master", "run_failed")

    monkeypatch.setattr(deployheal, "incoming_ref", gone)
    assert "for Claude" in stray.route(checkout, "kuhyx/demo", aside, ["b.txt"], time.time())
    assert len(_filed()) == 1
    assert wt.is_dir()


def _left_by(world: Env, card: str, checkout: Path, files: dict[str, str]) -> None:
    """Write `files` into the checkout as a turn of `card` just did; srcguard records them (T2515)."""
    run = world.root / card
    run.mkdir(parents=True, exist_ok=True)
    srcguard.begin(run, "turn-1", "kuhyx/demo")
    for name, text in files.items():
        (checkout / name).write_text(text, encoding="utf-8")
    srcguard.end(run, "turn-1", "kuhyx/demo", time.time(), lambda _line: None)


def test_t2518_fresh_edits_a_board_card_left_are_set_aside_at_once_and_named(world: Env) -> None:
    wt, run_dir, checkout = _repo(world)
    _left_by(world, "0wner123-0", checkout, {"a.txt": "new a\n", "b.txt": "stray b\n"})  # fresh, no rest
    done = deploy.run(wt, run_dir, CARD, "kuhyx/demo", _command(checkout, refusing=False))
    assert done.passed
    (row,) = _filed()
    assert "card 0wner123-0" in row["detail"]
    assert "card 0wner123-0" in done.tail
    assert sh(checkout, "git", "status", "--porcelain") == ""


def test_t2518_a_recorded_file_kuhy_edited_since_keeps_the_quiet_wait(world: Env) -> None:
    wt, run_dir, checkout = _repo(world)
    _left_by(world, "0wner123-0", checkout, {"b.txt": "stray b\n"})
    (checkout / "b.txt").write_text("his own edit\n", encoding="utf-8")  # no longer what the card left
    with pytest.raises(DirtyCheckoutError):
        deploy.run(wt, run_dir, CARD, "kuhyx/demo", _command(checkout, refusing=False))
    assert (checkout / "b.txt").read_text(encoding="utf-8") == "his own edit\n"
    assert _filed() == []
