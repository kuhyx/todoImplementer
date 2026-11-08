"""Auto-ship: a run started with `auto_ship` on a done_check note ships itself once every check is green."""

import subprocess
import time

from contract_lib import validate
from runnerfakes import Env, sh, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait, wait_stage
from todoimpl.runner import limits

NO_CHANGE = reply("C1: done - nothing to change\n\nD: done")
OTHER = "bbbb2222-0"


def _log(world: Env) -> list[str]:
    return sh(world.tmp / "remotes" / "demo.git", "git", "log", "--format=%s", "main").splitlines()


def test_auto_ship_on_a_green_done_check_note_pushes_and_closes_without_a_click(world: Env) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD, auto_ship=True)
        st = wait_stage(world, sched, "shipped")
        validate("state", st.to_dict())
        assert st.auto_ship
        assert _log(world) == ["Add hello file", "init"]
        assert st.ship is not None
        assert sh(world.tmp / "remotes" / "demo.git", "git", "rev-parse", "main").strip() == st.ship["commit"]
        assert len(client.closed) == 1
        assert client.closed[0][1].startswith(f"Shipped {st.ship['commit'][:12]} to origin/main.")
        assert "done_check `test -f hello.txt` exit 0" in client.closed[0][1]
        shown = [e["text"] for e in sched.bus.history(CARD, 0) if e["kind"] == "system"]
        assert f"shipped {st.ship['commit'][:12]} to origin/main" in shown
    finally:
        sched.close()


def test_auto_ship_off_keeps_the_gate(world: Env) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD, auto_ship=False)
        st = wait_stage(world, sched, "gate")
        assert not st.auto_ship
        assert "auto_ship" not in st.to_dict()
        assert _log(world) == ["init"]
        assert client.closed == []
    finally:
        sched.close()


def test_auto_ship_without_a_done_check_keeps_the_gate(world: Env) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, body="done: hello.txt exists")
    try:
        sched.start(CARD, auto_ship=True)
        wait_stage(world, sched, "gate")
        assert _log(world) == ["init"]
        assert client.closed == []
    finally:
        sched.close()


def test_auto_ship_with_no_diff_closes_once_and_pushes_nothing(world: Env) -> None:
    sched, client = boot(world, PLAN, NO_CHANGE, LIVE_OK, done_check="true")
    try:
        sched.start(CARD, auto_ship=True)
        st = wait_stage(world, sched, "shipped")
        validate("state", st.to_dict())
        assert _log(world) == ["init"]
        assert len(client.closed) == 1
        lines = client.closed[0][1].splitlines()
        assert lines[0] == "Closed with no code change."
        assert "live C1: done (ran `cat hello.txt` -> saw hi)" in lines
        assert "done_check `true` exit 0:" in lines
        assert st.worktree is not None
        assert not (world.root / CARD / "wt").exists()
        assert st.ship is not None
        assert st.ship["commit"] == ""
        assert "pushed_at" not in st.ship
    finally:
        sched.close()


def test_auto_ship_red_recheck_fails_and_send_reopens_implement(world: Env) -> None:
    count = world.tmp / "runs"
    # The second run of the check (the recheck after the rebase) is red, every other run is green.
    check = f'n=$(cat {count} 2>/dev/null || echo 0); echo $((n+1)) > {count}; [ "$n" -ne 1 ]'
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, done_check=check)
    try:
        sched.start(CARD, auto_ship=True)
        st = wait_stage(world, sched, "failed")
        assert st.error is not None
        assert "red after the rebase" in st.error
        assert st.extra["failed_stage"] == "shipping"
        assert st.worktree is not None
        assert (world.root / CARD / "wt").exists()
        assert _log(world) == ["init"]
        assert client.closed == []
        session = st.sessions["implement"]["session_id"]
        world.script("abcd1234", *reply("C1: done - still there\n\nD: done"))
        world.script("abcd1234", *LIVE_OK)
        sched.send(CARD, "the recheck flaked, try again")
        st = wait_stage(world, sched, "shipped")
        assert "Implement stage." in world.calls()[3]["prompt"]
        assert world.calls()[3]["resume"] == session
        assert st.auto_ship
        assert len(client.closed) == 1
    finally:
        sched.close()


def test_auto_ship_red_checks_after_two_fixes_need_you_and_push_nothing(world: Env) -> None:
    turns = [PLAN, IMPL, LIVE_OK, IMPL, LIVE_OK, IMPL, LIVE_OK]
    sched, client = boot(world, *turns, done_check="test -f nope.txt")
    try:
        sched.start(CARD, auto_ship=True)
        st = wait_stage(world, sched, "failed")
        assert st.error == "Checks still red after 2 fix attempts: done_check"
        assert st.extra["failed_stage"] == "checks"
        assert st.auto_ship
        assert st.ship is None
        assert _log(world) == ["init"]
        assert client.closed == []
    finally:
        sched.close()


def test_auto_ship_survives_a_limit_pause(world: Env) -> None:
    slow = ({"_fake": "sleep", "sec": 1.0}, *IMPL)
    sched, client = boot(world, PLAN, slow, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD, auto_ship=True)
        wait(lambda: len(world.calls()) == 2)
        limits.write_until(world.root, time.time() + 3600)
        assert wait_stage(world, sched, "paused_limit").auto_ship
        sched.credits(CARD)
        wait_stage(world, sched, "shipped")
        assert len(client.closed) == 1
    finally:
        sched.close()


def test_retry_keeps_auto_ship_and_restart_takes_the_new_choice(world: Env) -> None:
    sched, _ = boot(world, PLAN, reply("done-ish"), reply("still"), reply("hm"), done_check="true")
    try:
        sched.start(CARD, auto_ship=True)
        wait_stage(world, sched, "failed")
        world.script("abcd1234", *reply("x\n\nQ: which file?"))
        sched.start(CARD)
        assert wait_stage(world, sched, "plan", tag="Q").auto_ship
        sched.cancel(CARD)
        sched.start(CARD, auto_ship=False)
        sched.cancel(CARD)
        assert not state(world).auto_ship
    finally:
        sched.close()


def test_auto_ship_and_ship_click_close_with_the_same_evidence(world: Env) -> None:
    impl2 = ({"_fake": "write", "path": "other.txt", "text": "hi\n"}, *IMPL[1:])
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    client.tasks["bbbb2222"] = task("bbbb2222", done_check="true")
    for turn in (PLAN, impl2, LIVE_OK):
        world.script("bbbb2222", *turn)
    try:
        sched.start(CARD, auto_ship=True)
        auto = wait_stage(world, sched, "shipped")
        sched.start(OTHER)
        wait_stage(world, sched, "gate", OTHER)
        sched.ship(OTHER)
        click = wait_stage(world, sched, "shipped", OTHER)
        assert auto.ship is not None
        assert click.ship is not None
        texts = dict(client.closed)
        a = texts[CARD].replace(auto.ship["commit"][:12], "SHA")
        b = texts[OTHER].replace(click.ship["commit"][:12], "SHA")
        assert a == b
    finally:
        sched.close()


def test_the_push_shim_still_refuses_a_non_local_remote(world: Env) -> None:
    repo = world.tmp / "probe"
    repo.mkdir()
    sh(repo, "git", "init", "-q")
    out = subprocess.run(
        ["git", "push", "https://github.com/kuhyx/demo.git", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode != 0
    assert "refused" in out.stderr
