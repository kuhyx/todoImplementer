"""An umbrella child that ends on `A:`/`Q:` or has red checks is sent back to work before kuhy is paged."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from runnerfakes import Env
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.runner.scheduler import Scheduler
from todoimpl.runner.stages import _shipping
from todoimpl.umbrella import bounce
from todoimpl.umbrella.children import fresh_state
from todoimpl.umbrella.note import children
from todoimpl.umbrella.store import child_dir
from umbrellarig import CARD, LIVE, NOTE, at_rest, boot, manager

KEY = "umbr0001-1"
STUCK = {"_fake": "result", "text": "- [ ] C1: text left\n\nA: lib/ui/tile.dart still shows Text('Not set')"}
FIXED = {"_fake": "result", "text": "C1: done - fixed\n\nD: done"}


def _turns(world: Env, *turns: Any) -> None:
    """Queue the child's turns in order; each argument is one turn's events."""
    for events in turns:
        world.script(KEY, *events)


def _run(world: Env, sched: Scheduler, stage: str) -> Any:
    try:
        sched.start(CARD)
        return at_rest(world, sched, stage)
    finally:
        sched.close()


def test_t1952_a_live_check_that_ends_on_a_goes_back_to_implement(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    _turns(world, [STUCK], [FIXED], LIVE)
    st = _run(world, sched, "shipped")
    assert st.error is None
    fix = [c for c in world.calls() if "Fix stage" in str(c["prompt"])]
    assert len(fix) == 1
    assert "Text('Not set')" in str(fix[0]["prompt"])
    assert "unattended" in str(fix[0]["prompt"])


def test_t1952_a_child_that_keeps_ending_on_a_rests_on_kuhy_after_three_passes(
    world: Env, free: Free
) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    _turns(world, [STUCK], [FIXED], [STUCK], [FIXED], [STUCK], [FIXED], [STUCK])
    _run(world, sched, "failed")
    fix = [c for c in world.calls() if "Fix stage" in str(c["prompt"])]
    assert len(fix) == 3
    child = store.load(world.root / CARD / "children" / KEY)
    assert child is not None
    assert (child.stage, child.last_tag) == ("live_check", "A")
    assert child.error is None


def test_t1953_the_umbrella_says_what_each_child_needs(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    _turns(world, [STUCK], [FIXED], [STUCK], [FIXED], [STUCK], [FIXED], [STUCK])
    st = _run(world, sched, "failed")
    assert "1 of 1 children need you: kuhyx/alpha (lib/ui/tile.dart still shows Text('Not set'))" in str(
        st.error
    )


def test_t1954_red_checks_of_a_child_get_more_than_two_fixes_and_own_the_old_red(
    world: Env, free: Free
) -> None:
    sched, _ = boot(world, 1, checks={"alpha": "test -f ok.txt"})
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    write = {"_fake": "write", "path": "ok.txt", "text": "ok\n"}
    _turns(world, [FIXED], LIVE, [FIXED], LIVE, [FIXED], LIVE, [write, FIXED], LIVE)
    st = _run(world, sched, "shipped")
    assert st.error is None
    fix = [str(c["prompt"]) for c in world.calls() if "Fix stage" in str(c["prompt"])]
    assert len(fix) >= 4
    assert "also one that was red before you started" in fix[-1]


def test_t1955_a_child_whose_checks_did_not_pass_never_ships() -> None:
    kid = SimpleNamespace(body="", parts=[])
    red = store.RunState(task_id="x-1", stage="shipping", extra={"umbrella_round": 1})
    red.checks = {"passed": False, "results": []}
    assert _shipping(SimpleNamespace(state=red, item=kid)) == "checks"  # type: ignore[arg-type]
    never = store.RunState(task_id="x-1", stage="shipping", extra={"umbrella_round": 1})
    assert _shipping(SimpleNamespace(state=never, item=kid)) == "checks"  # type: ignore[arg-type]


def test_t1955_the_umbrella_does_not_close_over_a_done_child_with_unpassed_checks(
    world: Env, free: Free
) -> None:
    sched, client = boot(world, 1, done=("aaaa1111",))
    sched.close()
    (kid,) = children(client.tasks[NOTE].body, NOTE)
    child = fresh_state(kid, 1, 0.0, auto_ship=True)
    child.stage = "shipped"
    child.checks = {"passed": False, "results": []}
    store.save(child_dir(world.root / CARD, kid.cid), child)
    row = {"id": kid.cid, "repo": kid.repo, "title": kid.title, "done": True}
    record = {"width": 1, "tier": None, "kids": [row], "current": None, "rounds": []}
    store.save(world.root / CARD, store.RunState(task_id=CARD, stage="implement", extra={"umbrella": record}))
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        st = at_rest(world, again, "failed")
    finally:
        again.close()
    assert "1 of 1 children need you: kuhyx/alpha (checks not green)" in str(st.error)


def test_t1952_an_implement_turn_that_asks_a_question_is_told_nobody_answers(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: escalate the worker looped"))
    ask = {"_fake": "result", "text": "Q: which wording do you want for the title?"}
    _turns(world, [ask], [FIXED], LIVE)
    st = _run(world, sched, "shipped")
    assert st.error is None
    impl = [str(c["prompt"]) for c in world.calls() if "Implement stage" in str(c["prompt"])]
    assert len(impl) == 2
    assert "unattended" in impl[1]


def test_t1953_what_a_child_waits_for_comes_from_its_tag_line_error_or_last_issue() -> None:
    assert bounce.needs(None, "pins stale") == "pins stale"
    waiting = store.RunState(task_id="x-1", stage="live_check", extra={"umbrella_round": 1})
    waiting.last_tag, waiting.error = "A", "boom"
    waiting.extra["last_reply"] = "Did the thing.\nA: reconnect the\n  web driver\n"
    assert bounce.needs(waiting, "old") == "reconnect the web driver"
    waiting.extra["last_reply"] = "no tag line here"
    assert bounce.needs(waiting, "old") == "boom"
    waiting.error = None
    assert bounce.needs(waiting, "x" * 300) == "x" * 99 + "…"
