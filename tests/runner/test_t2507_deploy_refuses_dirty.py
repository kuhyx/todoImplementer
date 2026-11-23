"""T2507-T2509: a deploy that refuses kuhy's dirty checkout waits with one exact step; no lock line leads."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from runnerfakes import Env, make_repo, sh
from schedfakes import CARD
from todoimpl.board.state import RunState
from todoimpl.runner import deploy, deployheal, worktree
from todoimpl.runner.deploy import DeployFailedError
from todoimpl.runner.deployheal import DirtyCheckoutError
from todoimpl.umbrella import bounce

LOCK_LINE = "waiting for build lock held by ? (java -jar emulator.jar) since 2026-11-22 18:14:08; 5 ahead"


def _repo(world: Env) -> tuple[Path, Path, Path]:
    """Push one commit; return (worktree, run dir, kuhy's checkout)."""
    md = "# demo\n\n## Commands\n\n- deploy: `true`\n"
    checkout = make_repo(world, files={"CLAUDE.md": md, "lib.txt": "old\n", "own.txt": "his\n"})
    wt = worktree.add(checkout, world.root, CARD).path
    (wt / "lib.txt").write_text("new\n", encoding="utf-8")
    sh(wt, "git", "commit", "-qam", "incoming")
    sh(wt, "git", "push", "-q", "origin", "HEAD:main")
    return wt, world.root / CARD, checkout


def _refusing(checkout: Path) -> str:
    """Return a deploy that refuses any dirty checkout before its pull (signal-bot's scripts/deploy.sh)."""
    return (
        f"echo '{LOCK_LINE}' >&2; "
        f'if [ -n "$(git -C {checkout} status --porcelain)" ]; then '
        f"echo 'deploy: {checkout} is dirty (before the pull); commit or revert there first'; exit 1; fi; "
        f"git -C {checkout} pull -q --ff-only"
    )


def test_t2507_a_deploy_that_refuses_a_dirty_checkout_waits_and_never_touches_kuhys_edit(world: Env) -> None:
    wt, run_dir, checkout = _repo(world)
    (checkout / "own.txt").write_text("his edit\n", encoding="utf-8")  # not a file the push changes
    with pytest.raises(DirtyCheckoutError) as stop:
        deploy.run(wt, run_dir, CARD, "kuhyx/demo", _refusing(checkout))
    assert stop.value.files == ["own.txt"]
    assert (checkout / "own.txt").read_text(encoding="utf-8") == "his edit\n"
    step = f"git -C {stop.value.where} stash push -u -m todoimpl-{CARD} -- own.txt"
    assert f"run `{step}`, then Retry" in stop.value.text
    sh(checkout, "git", *step.split()[3:])  # kuhy's step, as the text says it
    assert deploy.run(wt, run_dir, CARD, "kuhyx/demo", _refusing(checkout)).passed
    sh(checkout, "git", "stash", "pop", "-q")  # nothing of his was lost
    assert (checkout / "own.txt").read_text(encoding="utf-8") == "his edit\n"


def test_t2507_the_refusal_with_a_clean_checkout_is_a_red_deploy_for_the_session(world: Env) -> None:
    wt, run_dir, checkout = _repo(world)
    command = "echo 'deploy: the build tree is dirty'; exit 1"
    with pytest.raises(DeployFailedError):
        deploy.run(wt, run_dir, CARD, "kuhyx/demo", command)
    assert sh(checkout, "git", "status", "--porcelain") == ""


def test_t2507_a_dirty_file_that_already_equals_the_push_is_restored_and_the_deploy_goes_on(
    world: Env,
) -> None:
    wt, run_dir, checkout = _repo(world)
    (checkout / "lib.txt").write_text(
        "new\n", encoding="utf-8"
    )  # a session wrote the pushed change there too
    assert deploy.run(wt, run_dir, CARD, "kuhyx/demo", _refusing(checkout)).passed
    assert sh(checkout, "git", "rev-parse", "HEAD") == sh(wt, "git", "rev-parse", "HEAD")


def test_t2508_a_red_deploy_text_does_not_lead_with_the_build_lock_wait_line() -> None:
    failed = DeployFailedError.build(1, f"{LOCK_LINE}\ndeploy: the real reason\n")
    assert "waiting for build lock" not in failed.text
    assert failed.text.endswith("deploy failed (exit 1): deploy: the real reason")
    assert LOCK_LINE in failed.output  # the fix brief still has the whole log tail


def test_t2509_the_umbrella_card_keeps_a_dirty_childs_whole_step() -> None:
    error = DirtyCheckoutError(
        "pushed, not deployed", Path.home() / "src" / "demo", ["a" * 60, "b" * 60], CARD
    )
    child = RunState(task_id=CARD, stage="failed", error=error.text)
    assert bounce.needs(child) == error.text.removeprefix("pushed, not deployed: ")
    assert "b" * 60 in bounce.needs(child)


@pytest.mark.parametrize("refusing", [True, False])
def test_t2512_stray_edits_at_rest_are_set_aside_losslessly_and_the_deploy_goes_on(
    world: Env, *, refusing: bool
) -> None:
    wt, run_dir, checkout = _repo(world)
    for name in ("lib.txt", "stray.txt"):  # a free worker's leftovers: a tracked edit and a new file
        (checkout / name).write_text("stray\n", encoding="utf-8")
        os.utime(checkout / name, (time.time() - deployheal.QUIET - 60,) * 2)
    command = _refusing(checkout) if refusing else f"git -C {checkout} pull -q --ff-only"
    done = deploy.run(wt, run_dir, CARD, "kuhyx/demo", command)
    assert done.passed
    assert "set aside stray edits" in done.tail
    assert sh(checkout, "git", "rev-parse", "HEAD") == sh(wt, "git", "rev-parse", "HEAD")
    assert f"todoimpl-stray-{CARD}" in sh(checkout, "git", "stash", "list")
    (patch,) = (run_dir / "deploy").glob("stray-*.patch")
    assert "+stray" in patch.read_text(encoding="utf-8")
    sh(checkout, "git", "checkout", "-q", "HEAD~1")  # the stash restores exactly what was there
    sh(checkout, "git", "stash", "pop", "-q")
    assert (checkout / "stray.txt").read_text(encoding="utf-8") == "stray\n"
    assert (checkout / "lib.txt").read_text(encoding="utf-8") == "stray\n"


def test_t2512_a_stray_deletion_has_no_time_and_counts_as_at_rest(world: Env) -> None:
    wt, run_dir, checkout = _repo(world)
    (checkout / "own.txt").unlink()  # a file a worker removed: no mtime to judge
    assert deploy.run(wt, run_dir, CARD, "kuhyx/demo", _refusing(checkout)).passed
    assert f"todoimpl-stray-{CARD}" in sh(checkout, "git", "stash", "list")
