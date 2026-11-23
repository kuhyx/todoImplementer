"""A restart mid-Ship: kuhy's click survives it, whichever point it cut (T1988)."""

import subprocess
from pathlib import Path

import pytest
from runnerfakes import Env, FakeClient, Notes, executable, sh
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, state, wait_stage
from todoimpl.board import state as store
from todoimpl.runner import deploy, recovery
from todoimpl.runner.restart import INTERRUPTED, MAX_RESUMES, restart_stage
from todoimpl.runner.scheduler import Scheduler
from todoimpl.todo_mcp.items import Item


def _booted(world: Env, monkeypatch: pytest.MonkeyPatch) -> tuple[Scheduler, FakeClient]:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, done_check="test -f hello.txt")
    hook = world.src / "demo" / ".git" / "hooks" / "pre-push"
    executable(hook, f"#!/bin/sh\necho push >> {world.tmp}/pushes\n")
    monkeypatch.setenv("DEPLOY_LOG", str(world.tmp / "deploys"))
    return sched, client


def _count(world: Env, name: str) -> int:
    path = world.tmp / name
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def _cut(world: Env, sched: Scheduler, *, drop_record: bool = False) -> None:
    """Close the scheduler and leave the run in `shipping` as a restart in mid-Ship would."""
    sched.close()
    st = state(world)
    st.stage, st.error = "shipping", None
    st.extra.pop("failed_stage", None)
    if drop_record:
        (world.root / CARD / deploy.PUSHED).unlink()
    store.save(world.root / CARD, st)


def _resume(world: Env, client: FakeClient) -> store.RunState:
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        return wait_stage(world, again, "shipped")
    finally:
        again.close()


def _one_push_one_close(world: Env, client: FakeClient) -> None:
    remote = world.tmp / "remotes" / "demo.git"
    assert _count(world, "pushes") == 1
    assert len(client.closed) == 1
    assert sh(remote, "git", "rev-list", "--count", "main").strip() == "2"  # the seed commit and one push


def test_t1988_a_restart_before_the_push_ships_again_by_itself(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = _booted(world, monkeypatch)
    sched.start(CARD)
    wait_stage(world, sched, "gate")
    _cut(world, sched)  # kuhy clicked Ship; the board restarted before anything was pushed
    done = _resume(world, client)
    assert done.error is None
    assert done.extra["ship_resumes"] == 1
    _one_push_one_close(world, client)


def test_t1988_a_restart_after_the_push_before_the_record_ships_again_without_a_second_push(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = _booted(world, monkeypatch)
    monkeypatch.setenv("DEPLOY_EXIT", "3")
    sched.start(CARD, auto_ship=True)
    wait_stage(world, sched, "failed")  # pushed, deploy red
    _cut(world, sched, drop_record=True)  # the push landed, pushed.json did not
    monkeypatch.setenv("DEPLOY_EXIT", "0")
    done = _resume(world, client)
    assert done.error is None
    _one_push_one_close(world, client)
    assert "Pushed by the session" in client.closed[0][1]


def test_t1988_a_restart_after_the_deploy_closes_the_note_without_deploying_again(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = _booted(world, monkeypatch)
    client.fail_close = True
    sched.start(CARD, auto_ship=True)
    st = wait_stage(world, sched, "failed")  # pushed and deployed, the note refused the close
    assert "closing the note failed" in str(st.error)
    _cut(world, sched)
    client.fail_close = False
    done = _resume(world, client)
    assert done.error is None
    _one_push_one_close(world, client)
    assert _count(world, "deploys") == 1  # the green record is reused


def test_t1988_a_restart_during_ships_own_rebase_aborts_it_and_ships(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = _booted(world, monkeypatch)
    sched.start(CARD)
    st = wait_stage(world, sched, "gate")
    wt = Path(str(st.worktree))
    sh(wt, "git", "add", "--all")
    sh(wt, "git", "commit", "--quiet", "-m", "squashed")
    with pytest.raises(subprocess.CalledProcessError):
        sh(wt, "git", "rebase", "--exec", "false", "origin/main")  # stops half way, as a kill would
    (world.root / CARD / "rebasing").write_text("1", encoding="utf-8")  # what Ship's own rebase leaves
    _cut(world, sched)
    done = _resume(world, client)
    assert done.error is None
    assert not (world.root / CARD / "rebasing").exists()
    _one_push_one_close(world, client)


def test_t2510_a_ship_cut_more_than_twice_rests_on_the_ladder_and_never_needs_kuhy(world: Env) -> None:
    for left in (0, MAX_RESUMES - 1, MAX_RESUMES):
        name = f"card{left}-0"
        store.save(
            world.root / name, store.RunState(task_id=name, stage="shipping", extra={"ship_resumes": left})
        )
    assert recovery.interrupted(world.root, Notes()) == [
        "card0-0",
        f"card{MAX_RESUMES - 1}-0",
        f"card{MAX_RESUMES}-0",
    ]
    resting_ship = store.load(world.root / f"card{MAX_RESUMES}-0")
    assert resting_ship is not None
    assert (resting_ship.stage, resting_ship.error) == ("paused_retry", None)
    assert resting_ship.extra["resume_stage"] == "shipping"
    assert (resting_ship.resume_at or 0) > 0
    assert f"{MAX_RESUMES + 1} restarts" in resting_ship.extra["retry_reason"]
    resting = store.load(world.root / "card0-0")
    assert resting is not None
    assert resting.extra["ship_resumes"] == 1


def test_t1988_a_failed_interrupted_ship_goes_straight_back_to_shipping_on_retry(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = Item("abcd1234", 0, "t", "b", "demo", "todo", None)
    for gate_form in ("gate", "shipping"):  # the form a restart left before T1988, and the cap's own
        st = store.RunState(task_id=CARD, stage="failed", extra={"failed_stage": gate_form})
        st.error = f"{INTERRUPTED}: check origin and the note before shipping again"
        assert restart_stage(st, item) == "shipping"
    other = store.RunState(task_id=CARD, stage="failed", extra={"failed_stage": "gate"}, error="checks red")
    assert restart_stage(other, item) == "gate"  # any other failed Ship still waits for the click
    sched, client = _booted(world, monkeypatch)
    sched.start(CARD)
    st = wait_stage(world, sched, "gate")
    st.stage, st.extra = "failed", {"failed_stage": "gate", "ship_resumes": MAX_RESUMES}
    st.error = f"{INTERRUPTED} {MAX_RESUMES + 1} times in a row"
    store.save(world.root / CARD, st)
    try:
        sched.start(CARD)  # Retry, no Ship click
        done = wait_stage(world, sched, "shipped")
    finally:
        sched.close()
    assert "ship_resumes" not in done.extra
    _one_push_one_close(world, client)
