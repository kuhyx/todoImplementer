"""Coached children count toward doubling, a lazy `fixed` is warned about, the rules reach the task."""

from __future__ import annotations

import time

from runnerfakes import Env
from schedfakes import wait
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.prompts import coach
from todoimpl.umbrella import issues
from umbrellarig import CARD, NOTE, at_rest, boot, manager, script_live, umbrella


def _feed(world: Env) -> str:
    return (world.root / CARD / "events.jsonl").read_text(encoding="utf-8")


def test_t2054_a_coached_child_doubles_the_width_and_the_task_file_carries_the_textgate_rules(
    world: Env, free: Free
) -> None:
    sched, _ = boot(world, 2)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: coached 1 added the rules"))
    world.script(NOTE, *manager("CHILD kuhyx/beta: clean"))
    script_live(world, 2)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "shipped")
    finally:
        sched.close()
    assert [(r["n"], r["next"]) for r in st.extra["umbrella"]["rounds"]] == [(1, 2), (2, 4)]
    task = (world.root / CARD / "children" / "umbr0001-1" / "task.md").read_text(encoding="utf-8")
    assert task.startswith("TEXTGATE RULES")
    assert "proper noun" in task
    assert "Make alpha text-free" in task


def test_t2054_a_fixed_free_child_with_fewer_than_three_coaching_lines_is_warned_about(
    world: Env, free: Free
) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: fixed did it myself"))
    script_live(world, 1)
    for i in range(2):
        issues.append(
            world.root / CARD, time.time() + 600 + i, "kuhyx/alpha", "prompt", "misread", "clarified"
        )
    try:
        sched.start(CARD)
        at_rest(world, sched, "shipped")
    finally:
        sched.close()
    assert "kuhyx/alpha: reported fixed after 2 of 3 coaching attempts" in _feed(world)


def test_t2054_a_fixed_child_after_three_coaching_lines_is_not_warned_about(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: fixed after three tries"))
    script_live(world, 1)
    for i in range(3):
        issues.append(
            world.root / CARD, time.time() + 600 + i, "kuhyx/alpha", "prompt", "misread", "clarified"
        )
    try:
        sched.start(CARD)
        at_rest(world, sched, "shipped")
    finally:
        sched.close()
    assert "coaching attempts" not in _feed(world)
    assert umbrella(world).extra["umbrella"]["rounds"][0]["children"][0]["verdict"] == "fixed"


def test_t1888_a_restarted_round_gets_a_fresh_manager_prompt_and_the_rules_on_an_old_task_file(
    world: Env, free: Free
) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, {"_fake": "sleep", "sec": 30})
    try:
        sched.start(CARD)
        wait(lambda: any("Umbrella manager" in str(c["prompt"]) for c in world.calls()))
        sched.cancel(CARD)
        st = at_rest(world, sched, "cancelled")
        st.sessions["manager"] = {"session_id": "dead-session", "last_turn_end": time.time(), "route": "plan"}
        store.save(world.root / CARD, st)
        task = world.root / CARD / "children" / "umbr0001-1" / "task.md"
        task.write_text("old task without rules\n", encoding="utf-8")
        world.script(NOTE, *manager("CHILD kuhyx/alpha: coached 1 rules added"))
        script_live(world, 1)
        sched.start(CARD)
        at_rest(world, sched, "shipped")
    finally:
        sched.close()
    managers = [c for c in world.calls() if "Umbrella manager" in str(c["prompt"])]
    assert [c["resume"] for c in managers] == [None, None]
    assert task.read_text(encoding="utf-8").startswith("TEXTGATE RULES")
    assert task.read_text(encoding="utf-8").endswith("old task without rules\n")
    assert coach.TEXTGATE_RULES not in task.read_text(encoding="utf-8").split("old task", 1)[1]
