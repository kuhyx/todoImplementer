"""T2007: a deploy whose pull git refuses for kuhy's edits heals losslessly or waits, never parks."""

from __future__ import annotations

from pathlib import Path

import pytest
from runnerfakes import Env, FakeClient, executable, make_repo, sh, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, state, wait_stage
from todoimpl.board.needs import needs
from todoimpl.runner import deploy, deployheal, shipfix, worktree
from todoimpl.runner.checks import CheckResult
from todoimpl.runner.deployheal import DirtyCheckoutError
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.scheduler import Scheduler

TRACKED, FRESH = "lib.txt", "fresh.txt"


def _pull_md(world: Env) -> str:
    return f"# demo\n\n## Commands\n\n- run: `./run.sh`\n- deploy: `git -C {world.src}/demo pull --ff-only`\n"


def _incoming(world: Env) -> tuple[Path, Path, Path]:
    """Push a commit that changes lib.txt and adds fresh.txt; return (worktree, run dir, kuhy's checkout)."""
    checkout = make_repo(world, files={"CLAUDE.md": _pull_md(world), TRACKED: "old\n"})
    wt = worktree.add(checkout, world.root, CARD).path
    (wt / TRACKED).write_text("new\n", encoding="utf-8")
    (wt / FRESH).write_text("fresh\n", encoding="utf-8")
    sh(wt, "git", "add", "-A")
    sh(wt, "git", "commit", "-q", "-m", "incoming")
    sh(wt, "git", "push", "-q", "origin", "HEAD:main")
    return wt, world.root / CARD, checkout


def _deploy(wt: Path, run_dir: Path, checkout: Path) -> CheckResult:
    return deploy.run(wt, run_dir, CARD, "kuhyx/demo", f"git -C {checkout} pull --ff-only")


def _stage(checkout: Path, name: str) -> None:
    sh(checkout, "git", "add", name)


@pytest.mark.parametrize("how", ["untracked", "staged"])
def test_t2007_edits_that_already_equal_the_incoming_files_are_restored_and_the_pull_goes_on(
    world: Env, how: str
) -> None:
    wt, run_dir, checkout = _incoming(world)
    (checkout / TRACKED).write_text("new\n", encoding="utf-8")  # a session wrote the same change here
    (checkout / FRESH).write_text("fresh\n", encoding="utf-8")  # same as the incoming file
    if how == "staged":
        _stage(checkout, FRESH)  # git lets a staged copy pass; it is put back with the blocking one
    assert _deploy(wt, run_dir, checkout).passed
    assert sh(checkout, "git", "status", "--porcelain") == ""
    assert (checkout / TRACKED).read_text(encoding="utf-8") == "new\n"
    assert sh(checkout, "git", "rev-parse", "HEAD") == sh(wt, "git", "rev-parse", "HEAD")


def test_t2007_a_different_edit_of_kuhy_is_never_touched_and_nothing_else_is_restored(world: Env) -> None:
    wt, run_dir, checkout = _incoming(world)
    (checkout / TRACKED).write_text("mine\n", encoding="utf-8")
    (checkout / FRESH).write_text("fresh\n", encoding="utf-8")  # equal, but all-or-nothing
    with pytest.raises(DirtyCheckoutError) as stop:
        _deploy(wt, run_dir, checkout)
    assert stop.value.files == [TRACKED]
    assert stop.value.kind == "run_failed"
    assert stop.value.text.startswith("pushed, not deployed: ")
    assert f"{TRACKED}" in stop.value.text
    assert "stash push -u" in stop.value.text  # one exact step (T2507)
    assert (checkout / TRACKED).read_text(encoding="utf-8") == "mine\n"
    assert (checkout / FRESH).read_text(encoding="utf-8") == "fresh\n"


@pytest.mark.parametrize(("name", "incoming"), [(TRACKED, "new\n"), (FRESH, "fresh\n")])
def test_t2007_a_staged_edit_of_kuhy_survives_when_the_tree_holds_the_incoming_content(
    world: Env, name: str, incoming: str
) -> None:
    wt, run_dir, checkout = _incoming(world)
    (checkout / name).write_text("mine\n", encoding="utf-8")
    _stage(checkout, name)  # his staged edit is in neither HEAD nor origin
    (checkout / name).write_text(
        incoming, encoding="utf-8"
    )  # while the tree already equals the incoming file
    with pytest.raises(DirtyCheckoutError) as stop:
        _deploy(wt, run_dir, checkout)
    assert stop.value.files == [name]
    assert sh(checkout, "git", "show", f":{name}") == "mine\n"
    assert (checkout / name).read_text(encoding="utf-8") == incoming


def test_t2007_a_blocked_pull_with_nothing_to_restore_names_the_files_git_lists(world: Env) -> None:
    wt, run_dir, checkout = _incoming(world)
    sh(checkout, "git", "mv", TRACKED, "moved.txt")  # kuhy's rename: the incoming change meets a deleted file
    with pytest.raises(DirtyCheckoutError) as stop:
        _deploy(wt, run_dir, checkout)
    assert stop.value.files == [TRACKED]
    assert (checkout / "moved.txt").is_file()


def test_t2007_a_git_failure_while_healing_waits_instead_of_parking_on_a_bare_error(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    wt, run_dir, checkout = _incoming(world)
    (checkout / FRESH).write_text("mine\n", encoding="utf-8")

    def locked(_checkout: Path, *, every: bool) -> list[str]:
        raise NeedsYouError("fatal: Unable to create '.git/index.lock': File exists.")

    monkeypatch.setattr(deployheal, "heal", locked)
    with pytest.raises(DirtyCheckoutError) as stop:
        _deploy(wt, run_dir, checkout)
    assert stop.value.files == [FRESH]
    assert stop.value.text.startswith("pushed, not deployed: ")


def test_t2007_without_a_checkout_the_blocked_pull_is_a_plain_failure(world: Env) -> None:
    wt, run_dir, _ = _incoming(world)
    command = "echo 'error: ... would be overwritten by merge:'; exit 1"
    with pytest.raises(NeedsYouError, match=r"^pushed, not deployed: deploy failed \(exit 1\)") as stop:
        deploy.run(wt, run_dir, CARD, None, command)
    assert not isinstance(stop.value, DirtyCheckoutError)


def test_t2007_another_failure_is_still_a_plain_needs_you(world: Env) -> None:
    wt, run_dir, checkout = _incoming(world)
    with pytest.raises(NeedsYouError, match=r"^pushed, not deployed: deploy failed \(exit 3\)") as stop:
        deploy.run(wt, run_dir, CARD, "kuhyx/demo", "echo broken; exit 3")
    assert not isinstance(stop.value, DirtyCheckoutError)
    assert checkout.is_dir()


def _boot(world: Env) -> tuple[Scheduler, FakeClient, Path]:
    checkout = make_repo(world, files={"CLAUDE.md": _pull_md(world), "README.md": "demo\n"})
    executable(checkout / ".git" / "hooks" / "pre-push", f"#!/bin/sh\necho push >> {world.tmp}/pushes\n")
    client = FakeClient({"abcd1234": task(done_check="test -f hello.txt")})
    for turn in (PLAN, IMPL, LIVE_OK):
        world.script("abcd1234", *turn)
    return Scheduler(client, world.root, check_timeout=20), client, checkout


def _pushes(world: Env) -> int:
    path = world.tmp / "pushes"
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def test_t2007_a_blocked_pull_rests_on_the_ladder_then_deploys_once_the_edit_is_gone(world: Env) -> None:
    sched, client, checkout = _boot(world)
    (checkout / "hello.txt").write_text("mine\n", encoding="utf-8")  # kuhy's own file, in the way
    try:
        sched.start(CARD, auto_ship=True)
        st = wait_stage(world, sched, "paused_retry")
        assert st.extra["retry_reason"].startswith("deploy waits")
        assert "hello.txt" in st.extra["retry_reason"]
        assert st.error is None
        assert client.closed == []
        (checkout / "hello.txt").unlink()
        st = wait_stage(world, sched, "shipped")
    finally:
        sched.close()
    assert (checkout / "hello.txt").read_text(encoding="utf-8") == "hi\n"
    assert (_pushes(world), len(client.closed)) == (1, 1)  # the retry never pushed again


def test_t2007_the_same_file_in_the_checkout_is_restored_with_no_wait_at_all(world: Env) -> None:
    sched, client, checkout = _boot(world)
    (checkout / "hello.txt").write_text("hi\n", encoding="utf-8")  # what the session wrote there too
    try:
        sched.start(CARD, auto_ship=True)
        st = wait_stage(world, sched, "shipped")
    finally:
        sched.close()
    assert "retry_reason" not in st.extra
    assert (checkout / "hello.txt").read_text(encoding="utf-8") == "hi\n"
    assert (_pushes(world), len(client.closed)) == (1, 1)


def test_t2007_after_the_ladder_kuhy_gets_the_files_and_retry_deploys(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shipfix, "MAX_DEPLOY_WAITS", 1)
    sched, client, checkout = _boot(world)
    (checkout / "hello.txt").write_text("mine\n", encoding="utf-8")
    try:
        sched.start(CARD, auto_ship=True)
        st = wait_stage(world, sched, "failed", turns=3)
        assert (st.error or "").startswith("pushed, not deployed: ")
        assert "hello.txt" in (st.error or "")
        assert needs(st).kind == "run_failed"
        assert st.extra["retries"] == 1  # one wait, then the bound
        (checkout / "hello.txt").unlink()
        sched.start(CARD)  # Retry goes straight back to Ship
        st = wait_stage(world, sched, "shipped")
        assert state(world).error is None
    finally:
        sched.close()
    assert (_pushes(world), len(client.closed)) == (1, 1)
