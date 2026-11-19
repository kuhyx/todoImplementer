"""A run pushed but not deployed: Retry goes straight back to Ship, a restart mid-deploy adopts the deploy."""

import pytest
from runnerfakes import Env, FakeClient, executable, sh
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, wait_stage
from todoimpl.board import state as store
from todoimpl.runner.scheduler import Scheduler

SPENT = {"deploy_fixes": 2}  # T2050 fix turns used up: these tests are about the red state


def _booted(world: Env, monkeypatch: pytest.MonkeyPatch) -> tuple[Scheduler, FakeClient]:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, done_check="test -f hello.txt")
    hook = world.src / "demo" / ".git" / "hooks" / "pre-push"
    executable(hook, f"#!/bin/sh\necho push >> {world.tmp}/pushes\n")
    monkeypatch.setenv("DEPLOY_LOG", str(world.tmp / "deploys"))
    return sched, client


def _count(world: Env, name: str) -> int:
    path = world.tmp / name
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def test_t1961_retry_after_a_failed_deploy_ships_again_by_itself_and_never_pushes_twice(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = _booted(world, monkeypatch)
    monkeypatch.setenv("DEPLOY_EXIT", "3")
    try:
        sched.start(CARD, auto_ship=True, extra=SPENT)
        st = wait_stage(world, sched, "failed")
        assert str(st.error).startswith("pushed, not deployed: deploy failed (exit 3)")
        assert client.closed == []
        monkeypatch.setenv("DEPLOY_EXIT", "0")
        sched.start(CARD)  # Retry
        st = wait_stage(world, sched, "shipped")
        assert st.ship is not None
        assert (_count(world, "pushes"), _count(world, "deploys")) == (1, 2)
        assert len(client.closed) == 1
        assert client.closed[0][1].startswith(f"Shipped {st.ship['commit'][:12]} to origin/main.")
        assert "deploy `echo deployed" in client.closed[0][1]
    finally:
        sched.close()


def test_t1968_a_restart_during_the_deploy_goes_on_to_the_deploy_instead_of_failing(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = _booted(world, monkeypatch)
    monkeypatch.setenv("DEPLOY_EXIT", "3")
    try:
        sched.start(CARD, auto_ship=True, extra=SPENT)
        st = wait_stage(world, sched, "failed")
    finally:
        sched.close()
    st.stage, st.error = "shipping", None  # what a restart leaves while the deploy unit still ran
    store.save(world.root / CARD, st)
    monkeypatch.setenv("DEPLOY_EXIT", "0")
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        done = wait_stage(world, again, "shipped")
    finally:
        again.close()
    assert done.error is None
    assert (_count(world, "pushes"), len(client.closed)) == (1, 1)


def test_t1970_a_note_after_a_failed_deploy_is_new_work_that_ships_and_deploys_too(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = _booted(world, monkeypatch)
    monkeypatch.setenv("DEPLOY_EXIT", "3")
    more = ({"_fake": "write", "path": "more.txt", "text": "more\n"}, *reply("C1: done\n\nD: done"))
    try:
        sched.start(CARD, auto_ship=True, extra=SPENT)
        wait_stage(world, sched, "failed")
        monkeypatch.setenv("DEPLOY_EXIT", "0")
        world.script("abcd1234", *more)
        world.script("abcd1234", *LIVE_OK)
        sched.send(CARD, "also add more.txt, the deploy line is fine")
        st = wait_stage(world, sched, "shipped")
    finally:
        sched.close()
    assert st.ship is not None
    assert st.ship["commit"] == sh(world.tmp / "remotes" / "demo.git", "git", "rev-parse", "main").strip()
    remote = world.tmp / "remotes" / "demo.git"
    assert (_count(world, "pushes"), _count(world, "deploys")) == (2, 2)  # the new work is a second push
    tree = sh(remote, "git", "ls-tree", "-r", "--name-only", "main").split()
    assert "more.txt" in tree
    assert "deploy-artifact.txt" not in tree  # the first deploy's leftovers were cleaned, not squashed in
    assert len(client.closed) == 1
