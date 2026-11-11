"""An umbrella card tells children that need kuhy from children that are pushed but not deployed (T1967)."""

from __future__ import annotations

import pytest
from runnerfakes import Env, FakeClient, executable, sh
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.runner.scheduler import Scheduler
from todoimpl.umbrella import bounce
from todoimpl.umbrella.store import child_dir
from umbrellarig import CARD, LIVE, NOTE, at_rest, boot, manager

KEY = "umbr0001-1"
NO_LINE = "kuhyx/alpha declares no deploy: command in CLAUDE.md"


def test_t1967_a_child_pushed_but_not_deployed_is_named_as_such_not_as_needing_kuhy(
    world: Env, free: Free
) -> None:
    sched, client = boot(world, 1, undeployed=("alpha",))
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script(KEY, *LIVE)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "failed")
    finally:
        sched.close()
    assert (
        st.error
        == "1 of 1 children pushed, not deployed: kuhyx/alpha (declares no deploy: command in CLAUDE.md)"
    )
    child = store.load(world.root / CARD / "children" / KEY)
    assert child is not None
    assert child.error == f"pushed, not deployed: {NO_LINE}"
    remote = world.tmp / "remotes" / "alpha.git"
    assert sh(remote, "git", "log", "-1", "--format=%s", "main").startswith("Make alpha text-free")  # pushed
    assert "- [ ] kuhyx/alpha" in client.tasks[NOTE].body  # not ticked, the note stays open


def test_t1967_the_summary_lists_the_two_kinds_apart() -> None:
    need = [("kuhyx/a", "lib/ui/tile.dart still shows Text"), ("kuhyx/b", "")]
    held = [
        ("kuhyx/c", "kuhyx/c declares no deploy: command in CLAUDE.md"),
        ("kuhyx/d", "deploy failed (exit 2): boom"),
    ]
    assert bounce.summary(9, need, []) == (
        "2 of 9 children need you: kuhyx/a (lib/ui/tile.dart still shows Text); kuhyx/b"
    )
    assert bounce.summary(9, need, held) == (
        "2 of 9 children need you: kuhyx/a (lib/ui/tile.dart still shows Text); kuhyx/b. "
        "2 pushed, not deployed: kuhyx/c (declares no deploy: command in CLAUDE.md); "
        "kuhyx/d (deploy failed (exit 2): boom)"
    )
    assert bounce.summary(9, [], held) == (
        "2 of 9 children pushed, not deployed: kuhyx/c (declares no deploy: command in CLAUDE.md); "
        "kuhyx/d (deploy failed (exit 2): boom)"
    )


def test_t1967_what_a_pushed_child_waits_for_drops_the_deploy_prefix() -> None:
    st = store.RunState(
        task_id="x-1", stage="failed", error="pushed, not deployed: deploy failed (exit 2): boom"
    )
    assert bounce.undeployed(st) is True
    assert bounce.needs(st) == "deploy failed (exit 2): boom"
    assert bounce.undeployed(None) is False
    assert bounce.undeployed(store.RunState(task_id="x-1", stage="failed", error="other")) is False


def _failing_deploy(world: Env, monkeypatch: pytest.MonkeyPatch) -> tuple[Scheduler, FakeClient]:
    sched, client = boot(world, 1)
    executable(
        world.src / "alpha" / ".git" / "hooks" / "pre-push", f"#!/bin/sh\necho push >> {world.tmp}/pushes\n"
    )
    monkeypatch.setenv("DEPLOY_LOG", str(world.tmp / "deploys"))
    monkeypatch.setenv("DEPLOY_EXIT", "3")
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script(KEY, *LIVE)
    return sched, client


def _count(world: Env, name: str) -> int:
    return len((world.tmp / name).read_text(encoding="utf-8").splitlines())


def test_t1967_retry_deploys_a_failed_child_again_and_does_not_push_it_twice(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = _failing_deploy(world, monkeypatch)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "failed")
        assert str(st.error).startswith(
            "1 of 1 children pushed, not deployed: kuhyx/alpha (deploy failed (exit 3)"
        )
        monkeypatch.setenv("DEPLOY_EXIT", "0")
        sched.start(CARD)  # Retry
        at_rest(world, sched, "shipped")
    finally:
        sched.close()
    assert (_count(world, "pushes"), _count(world, "deploys")) == (1, 2)
    assert "- [x] kuhyx/alpha" in client.tasks[NOTE].body


def test_t1968_a_child_whose_push_landed_goes_on_to_its_deploy_after_a_restart(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = _failing_deploy(world, monkeypatch)
    try:
        sched.start(CARD)
        at_rest(world, sched, "failed")
    finally:
        sched.close()
    kid = child_dir(world.root / CARD, KEY)
    child = store.load(kid)
    assert child is not None
    child.stage, child.error = "shipping", None  # a restart found it mid-deploy
    store.save(kid, child)
    umbrella = store.load(world.root / CARD)
    assert umbrella is not None
    umbrella.stage, umbrella.error = "implement", None  # and its umbrella mid-run
    store.save(world.root / CARD, umbrella)
    monkeypatch.setenv("DEPLOY_EXIT", "0")
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        at_rest(world, again, "shipped")
    finally:
        again.close()
    assert (_count(world, "pushes"), "- [x] kuhyx/alpha" in client.tasks[NOTE].body) == (1, True)
