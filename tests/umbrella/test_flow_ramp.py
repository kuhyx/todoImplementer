"""An umbrella run end to end: the width doubles on clean rounds, children ship through their own pipeline."""

from __future__ import annotations

import time

from runnerfakes import Env
from tierfakes import Free
from todoimpl.umbrella import issues
from umbrellarig import CARD, NOTE, at_rest, boot, manager, script_live, umbrella


def test_clean_rounds_double_the_width_and_every_child_reaches_its_gate(world: Env, free: Free) -> None:
    sched, client = boot(world)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script(NOTE, *manager("CHILD kuhyx/beta: clean", "CHILD kuhyx/gamma: clean"))
    script_live(world)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "gate")
    finally:
        sched.close()
    rec = st.extra["umbrella"]
    assert [(r["n"], r["width"], r["next"]) for r in rec["rounds"]] == [(1, 1, 2), (2, 2, 4)]
    assert rec["width"] == 4
    assert [k["id"] for k in rec["kids"]] == ["umbr0001-1", "umbr0001-2", "umbr0001-3"]
    managers = [c for c in world.calls() if "Umbrella manager" in str(c["prompt"])]
    assert [c["model"] for c in managers] == ["sonnet", "sonnet"]
    assert "todoimpl.runner.freeworker" in str(managers[0]["prompt"])
    assert "kuhyx/alpha" in str(managers[0]["prompt"])
    assert "kuhyx/beta" not in str(managers[0]["prompt"])
    assert not client.closed


def test_ship_pushes_every_child_ticks_the_note_and_closes_the_umbrella(world: Env, free: Free) -> None:
    sched, client = boot(world, 2)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script(NOTE, *manager("CHILD kuhyx/beta: clean"))
    script_live(world, 2)
    try:
        sched.start(CARD)
        at_rest(world, sched, "gate")
        sched.ship(CARD)
        st = at_rest(world, sched, "shipped")
    finally:
        sched.close()
    assert sorted(client.ticked) == ["aaaa1111-0", "bbbb2222-0"]
    assert [c for c, _ in client.closed] == [CARD]
    assert "kuhyx/alpha" in client.closed[0][1]
    assert st.ship is not None
    assert st.ship["commit"] == ""


def test_fixed_or_unfree_children_keep_the_width(world: Env, free: Free) -> None:
    sched, _ = boot(world)
    free.public = False
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script(NOTE, *manager("CHILD kuhyx/beta: fixed edited a config"))
    world.script(NOTE, *manager("CHILD kuhyx/gamma: clean"))
    script_live(world)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "gate")
    finally:
        sched.close()
    rec = st.extra["umbrella"]
    assert [r["next"] for r in rec["rounds"]] == [1, 1, 1]
    assert [c["free"] for r in rec["rounds"] for c in r["children"]] == [False, False, False]


def test_a_fixed_child_without_an_issue_line_is_warned_about(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: fixed rewrote the edit"))
    script_live(world, 1)
    try:
        sched.start(CARD)
        at_rest(world, sched, "gate")
    finally:
        sched.close()
    feed = (world.root / CARD / "events.jsonl").read_text(encoding="utf-8")
    assert "kuhyx/alpha: reported fixed with no line in free-issues.jsonl" in feed


def test_a_fixed_child_with_an_issue_line_is_not_warned_about(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(
        NOTE,
        {"_fake": "tool", "name": "Bash", "input": {"command": "log"}},
        *manager("CHILD kuhyx/alpha: fixed x"),
    )
    script_live(world, 1)

    issues.append(
        world.root / CARD, time.time() + 600, "kuhyx/alpha", "edit", "bad edit", "redid it", fixed=True
    )
    try:
        sched.start(CARD)
        at_rest(world, sched, "gate")
    finally:
        sched.close()
    feed = (world.root / CARD / "events.jsonl").read_text(encoding="utf-8")
    assert "reported fixed with no line" not in feed
    assert umbrella(world).extra["umbrella"]["rounds"][0]["children"][0]["verdict"] == "fixed"
