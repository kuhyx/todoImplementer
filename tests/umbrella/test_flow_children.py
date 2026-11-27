"""Children that need more than the free tier: escalation, red checks, missing clones, retries."""

from __future__ import annotations

from typing import Any

from runnerfakes import Env, make_repo, sh
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.scheduler import Scheduler
from todoimpl.umbrella.driver import UmbrellaDriver
from umbrellarig import CARD, LIVE, NOTE, at_rest, boot, manager, script_live, umbrella

FIX = (
    {"_fake": "write", "path": "ok.txt", "text": "ok\n"},
    {"_fake": "result", "text": "C1: done - fixed\n\nD: done"},
)


def _run(world: Env, sched: Scheduler, stage: str) -> Any:
    try:
        sched.start(CARD)
        return at_rest(world, sched, stage)
    finally:
        sched.close()


def test_an_escalated_child_gets_one_more_effort_attempt_and_the_width_stays(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: escalate the worker looped"))
    world.script("umbr0001-1", {"_fake": "result", "text": "C1: done\n\nD: done"})
    script_live(world, 1)
    st = _run(world, sched, "shipped")
    rec = st.extra["umbrella"]
    assert rec["rounds"][0]["next"] == 1
    assert rec["rounds"][0]["children"][0]["checks"] is None
    impl = [c for c in world.calls() if "Implement stage" in str(c["prompt"])]
    assert [c["model"] for c in impl] == ["sonnet"]  # the default model (T2615)
    assert "the worker looped" in str(impl[0]["prompt"])
    assert "Escalation:" in str(impl[0]["prompt"])


def test_a_child_without_a_verdict_line_escalates(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("no verdict here"))
    world.script("umbr0001-1", {"_fake": "result", "text": "C1: done\n\nD: done"})
    script_live(world, 1)
    st = _run(world, sched, "shipped")
    assert st.extra["umbrella"]["rounds"][0]["children"][0]["detail"] == "the manager gave no verdict line"


def test_red_checks_after_the_manager_send_the_child_to_a_fix_turn(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1, checks={"alpha": "test -f ok.txt"})
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", *FIX)
    world.script(
        "umbr0001-1",
        {"_fake": "result", "text": "- [x] C1: ran it -> ok\n- [x] C2: ran the check -> ok\n\nD: done"},
    )
    st = _run(world, sched, "shipped")  # T1923: a green child ships itself
    row = st.extra["umbrella"]["rounds"][0]["children"][0]
    assert (row["verdict"], row["checks"], row["ok"]) == ("clean", False, False)
    assert st.extra["umbrella"]["width"] == 1
    fix = [c for c in world.calls() if "Fix stage" in str(c["prompt"])]
    assert len(fix) == 1
    assert "test -f ok.txt" in str(fix[0]["prompt"])


def test_a_missing_clone_fails_that_child_and_retry_picks_it_up(world: Env, free: Free) -> None:
    sched, _ = boot(world, 2, missing=("alpha",))
    world.script(NOTE, *manager("CHILD kuhyx/beta: clean"))
    world.script("umbr0001-2", *LIVE)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "failed")
        assert "1 of 2 children need you: kuhyx/alpha" in str(st.error)
        assert st.extra["umbrella"]["rounds"][0]["children"][0]["detail"].startswith(
            "Repo kuhyx/alpha has no local clone"
        )
        make_repo(world, "alpha")
        world.script("umbr0001-1", {"_fake": "result", "text": "C1: done\n\nD: done"})
        world.script("umbr0001-1", *LIVE)
        sched.start(CARD)
        st = at_rest(world, sched, "shipped")
    finally:
        sched.close()
    assert st.error is None


def test_a_ticked_child_is_not_run_again(world: Env, free: Free) -> None:
    sched, _ = boot(world, 2, done=("aaaa1111",))
    world.script(NOTE, *manager("CHILD kuhyx/beta: clean"))
    script_live(world, 2)
    st = _run(world, sched, "shipped")
    assert [r["n"] for r in st.extra["umbrella"]["rounds"]] == [1]
    assert [c["id"] for c in st.extra["umbrella"]["rounds"][0]["children"]] == ["umbr0001-2"]


def test_a_manager_that_fails_escalates_every_child(world: Env, free: Free, monkeypatch: Any) -> None:
    def broken(*_a: object, **_k: object) -> None:
        msg = "the manager turn was lost 3 times"
        raise NeedsYouError(msg)

    monkeypatch.setattr(UmbrellaDriver, "turn", broken)
    sched, _ = boot(world, 2)
    for key in ("umbr0001-1", "umbr0001-2"):
        world.script(key, {"_fake": "result", "text": "C1: done\n\nD: done"})
    script_live(world, 2)
    st = _run(world, sched, "shipped")
    kinds = [c["verdict"] for c in st.extra["umbrella"]["rounds"][0]["children"]]
    assert kinds == ["escalate"]


def test_an_umbrella_without_children_asks_for_them(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1, body="Umbrella: per-repo\nTier: cheap\n")
    st = _run(world, sched, "failed")
    assert "lists no children" in str(st.error)
    assert umbrella(world).stage == "failed"


def test_a_child_never_shares_a_branch_with_a_live_card_of_its_source_note(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    repo = world.src / "alpha"
    elsewhere = world.tmp / "card-worktree"
    sh(repo, "git", "worktree", "add", "-b", "todo/aaaa1111-0", str(elsewhere), "main")
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    script_live(world, 1)
    st = _run(world, sched, "shipped")
    assert st.error is None
    child = store.load(world.root / CARD / "children" / "umbr0001-1")
    assert child is not None
    assert child.branch == "todo/umbr0001-1"
    assert sh(repo, "git", "rev-parse", "--abbrev-ref", "todo/aaaa1111-0").strip() == "todo/aaaa1111-0"
