"""T2517: server start revives top-level cards a self-heal text parked, each at most once per text."""

from __future__ import annotations

from pathlib import Path

from runnerfakes import Env, Notes, make_repo
from todoimpl.board import state as store
from todoimpl.runner import recovery
from todoimpl.runner.deployheal import DirtyCheckoutError
from todoimpl.runner.restart import INTERRUPTED
from todoimpl.umbrella import revive
from todoimpl.umbrella.store import child_dir

CUT = f"{INTERRUPTED}: check origin and the note before shipping again"  # the text older servers wrote
OLD_DIRTY = "pushed, not deployed: the deploy's pull into ~/src/demo stops on uncommitted edits to a"


def _park(world: Env, error: str, failed_stage: str = "shipping", **extra: object) -> Path:
    run = world.root / "abcd1234-1"
    st = store.RunState(task_id="abcd1234-1", stage="failed", error=error, repo="kuhyx/demo", last_tag="D")
    st.extra.update({"failed_stage": failed_stage, "ship_resumes": 3, **extra})
    store.save(run, st)
    return run


def _state(run: Path) -> store.RunState:
    st = store.load(run)
    assert st is not None
    return st


def test_t2517_a_top_level_card_a_restart_parked_ships_again_once(world: Env) -> None:
    run = _park(world, CUT, failed_stage="gate")  # the legacy form the live cards carry
    assert recovery.interrupted(world.root, Notes()) == ["abcd1234-1"]
    st = _state(run)
    assert (st.stage, st.error, st.last_tag) == ("shipping", None, None)
    assert "ship_resumes" not in st.extra
    assert "failed_stage" not in st.extra
    assert st.extra[revive.KINDS] == ["interrupted"]
    st.stage, st.error, st.extra["failed_stage"] = "failed", CUT, "shipping"
    store.save(run, st)
    assert recovery.interrupted(world.root, Notes()) == []  # the same text again: it stays, no loop
    assert _state(run).stage == "failed"


def test_t2517_a_top_level_card_on_the_old_dirty_text_ships_again_once(world: Env) -> None:
    run = _park(world, OLD_DIRTY)
    assert recovery.interrupted(world.root, Notes()) == ["abcd1234-1"]
    assert _state(run).extra[revive.KINDS] == ["refused"]


def test_t2517_a_top_level_card_kuhys_edits_blocked_ships_again_once_they_are_clean(world: Env) -> None:
    checkout = make_repo(world, files={"lib.txt": "old\n"})
    run = _park(world, DirtyCheckoutError("pushed, not deployed", checkout, ["lib.txt"]).text, retries=12)
    (checkout / "lib.txt").write_text("his\n", encoding="utf-8")
    assert recovery.interrupted(world.root, Notes()) == []  # still his
    assert _state(run).stage == "failed"
    (checkout / "lib.txt").write_text("old\n", encoding="utf-8")
    assert recovery.interrupted(world.root, Notes()) == ["abcd1234-1"]
    st = _state(run)
    assert st.stage == "shipping"
    assert "retries" not in st.extra
    assert st.extra[revive.KINDS] == ["dirty"]


def test_t2517_another_failure_or_a_gate_form_of_a_dirty_text_stays(world: Env) -> None:
    run = _park(world, "Pre-push gate step lint is red (exit 1):\nE501")
    assert recovery.interrupted(world.root, Notes()) == []  # a fix turn is not a self-heal text
    _park(world, OLD_DIRTY, failed_stage="gate")
    assert recovery.interrupted(world.root, Notes()) == []
    assert _state(run).stage == "failed"


def test_t2517_a_failed_umbrella_with_no_child_to_revive_is_not_revived_as_a_card(world: Env) -> None:
    run = _park(world, CUT, umbrella={"children": []})
    assert recovery.interrupted(world.root, Notes()) == []
    assert _state(run).stage == "failed"


def test_t2517_a_child_revives_once_per_text_and_an_old_refusal_mark_counts(tmp_path: Path) -> None:
    st = store.RunState(task_id="abcd1234-1", stage="failed", error=CUT, extra={"failed_stage": "shipping"})
    assert revive.revive(st, tmp_path, 0.0)
    st.stage, st.error, st.extra["failed_stage"] = "failed", CUT, "shipping"
    assert not revive.revive(st, tmp_path, 0.0)
    st.error = OLD_DIRTY
    st.extra[revive.REFUSALS] = 1  # what the T2511 server saved
    assert not revive.revive(st, tmp_path, 0.0)


def test_t2517_a_card_kuhy_closed_or_an_unreachable_todo_app_revives_nothing(world: Env) -> None:
    run = _park(world, CUT, failed_stage="gate")
    for closed in ("done", "abandoned", None):  # done, won't do, the todo app down: it stays as it is
        assert recovery.interrupted(world.root, Notes(closed)) == []
        assert _state(run).stage == "failed"
    assert recovery.interrupted(world.root, Notes()) == ["abcd1234-1"]  # only a card still in Needs you


def test_t2517_children_of_an_umbrella_kuhy_closed_stay(world: Env) -> None:
    run = _park(world, "2 of 2 children need you", umbrella={"children": []})
    child = store.RunState(
        task_id="abcd1234-1", stage="failed", error=CUT, extra={"failed_stage": "shipping"}
    )
    store.save(child_dir(run, "kid"), child)
    assert recovery.interrupted(world.root, Notes("done")) == []
    assert _state(child_dir(run, "kid")).stage == "failed"
    assert recovery.interrupted(world.root, Notes()) == ["abcd1234-1"]
    assert _state(child_dir(run, "kid")).stage == "shipping"
