"""A child dropped from the umbrella (`- [-]`, its repo archived) never runs and leaves the record (T1924)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from runnerfakes import Env, FakeClient
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.umbrella import store as ustore
from umbrellarig import CARD, NOTE, at_rest, boot, manager, script_live

DROPPED = "- [-] kuhyx/alpha (aaaa1111)"


def _drop_alpha(client: FakeClient) -> None:
    task = client.tasks[NOTE]
    client.tasks[NOTE] = replace(task, body=task.body.replace("- [ ] kuhyx/alpha", "- [-] kuhyx/alpha"))


def test_t1924_a_dropped_child_never_runs_and_the_rest_ship(world: Env, free: Free) -> None:
    sched, client = boot(world, 2)
    _drop_alpha(client)
    world.script(NOTE, *manager("CHILD kuhyx/beta: clean"))
    script_live(world, 2)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "shipped")
    finally:
        sched.close()
    assert [k["id"] for k in ustore.record(st)["kids"]] == ["umbr0001-2"]
    assert store.load(world.root / CARD / "children" / "umbr0001-1") is None
    assert DROPPED in client.tasks[NOTE].body
    assert [c for c, _ in client.closed] == [CARD]


def test_t1924_a_child_dropped_mid_round_leaves_the_round(world: Env, free: Free) -> None:
    sched, client = boot(world, 2)
    sched.close()
    _drop_alpha(client)
    current = {
        "n": 1, "width": 2, "ids": ["umbr0001-1", "umbr0001-2"], "started": 0.0, "free": {}, "failed": {},
        "verdicts": None, "checks": None,
    }  # fmt: skip
    record: dict[str, Any] = {"width": 2, "tier": None, "kids": [], "rounds": [], "current": current}
    store.save(world.root / CARD, store.RunState(task_id=CARD, stage="implement", extra={"umbrella": record}))
    world.script(NOTE, *manager("CHILD kuhyx/beta: clean"))
    script_live(world, 2)
    again = type(sched)(client, world.root, check_timeout=20)  # recovery requeues the umbrella
    try:
        st = at_rest(world, again, "shipped")
    finally:
        again.close()
    (row,) = ustore.record(st)["rounds"][0]["children"]
    assert row["id"] == "umbr0001-2"
    assert again.locks.free("kuhyx/alpha", "x")


def test_t1924_a_child_whose_repo_is_archived_is_dropped_when_claimed(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_GH_ARCHIVED", "kuhyx/alpha")  # the gh shim answers `.archived` true for it
    sched, client = boot(world, 2)
    world.script(NOTE, *manager("CHILD kuhyx/beta: clean"))
    script_live(world, 2)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "shipped")
    finally:
        sched.close()
    assert DROPPED in client.tasks[NOTE].body
    assert [k["id"] for k in ustore.record(st)["kids"]] == ["umbr0001-2"]
    assert store.load(world.root / CARD / "children" / "umbr0001-1") is None


def test_t1924_an_archived_child_is_dropped_even_when_its_box_will_not_change(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_GH_ARCHIVED", "kuhyx/alpha")
    sched, client = boot(world, 2)
    client.fail_tick = True  # the note refuses every checkbox write, beta's tick at ship too
    world.script(NOTE, *manager("CHILD kuhyx/beta: clean"))
    script_live(world, 2)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "failed")
    finally:
        sched.close()
    assert "1 of 1 children need you: kuhyx/beta" in str(st.error)
    assert store.load(world.root / CARD / "children" / "umbr0001-1") is None
