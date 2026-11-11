"""Ask clicks: answer, take recommended, run, undo, screenshot verdict, 24 h auto-adopt (C2-C6, C10-C12)."""
# ruff: noqa: PT018, PLC0415

import json
from pathlib import Path

import pytest
from asksfakes import ID, Rig
from contract_lib import validate
from todoimpl.asks import allow, view
from todoimpl.board.state import RunState, save
from todoimpl.http.backend import BackendError


def states(rig: Rig) -> dict[str, str]:
    return {i["id"]: i["state"] for i in view.items(rig.cache.tasks[0].body, None, rig.dir)}


def with_run(rig: Rig, worktree: str | None = None) -> None:
    run = RunState(task_id=ID, stage="implement", worktree=worktree)
    rig.dir.mkdir(parents=True, exist_ok=True)
    save(rig.dir, run)


def test_view_matches_the_contract(rig: Rig) -> None:
    got = view.items(rig.cache.tasks[0].body, None, rig.dir)
    validate("ask", got)
    assert [i["type"] for i in got] == ["choice", "choice", "command", "screenshot"]
    assert got[0]["risk"] == "reversible" and got[1]["risk"] == "risky"
    assert got[2]["mode"] == "add_run" and got[3]["shot"] == "shots/a.png"
    assert view.items("no block", None, rig.dir) == []


def test_c2_answer_is_saved_and_sent_once_all_choices_are_resolved(rig: Rig) -> None:
    with_run(rig)
    rig.svc.answer(ID, "c1", "red")
    assert states(rig)["c1"] == "answered" and rig.sched.sent == []
    rig.svc.answer(ID, "c2", "yes")
    assert len(rig.sched.sent) == 1 and "Wipe the disk: yes" in rig.sched.sent[0][1]
    validate("ask", view.items(rig.cache.tasks[0].body, None, rig.dir))


def test_answer_refusals(rig: Rig) -> None:
    with pytest.raises(BackendError, match="not an option"):
        rig.svc.answer(ID, "c1", "green")
    with pytest.raises(BackendError, match="not an option"):
        rig.svc.answer(ID, "k1", "x")
    with pytest.raises(BackendError, match="no such ask"):
        rig.svc.answer(ID, "zz", "x")
    with pytest.raises(BackendError, match="unknown task"):
        rig.svc.answer("zzzzzzzz-9", "c1", "x")
    rig.cache.tasks[0].body = "plain"
    with pytest.raises(BackendError, match="no asks"):
        rig.svc.answer(ID, "c1", "red")


def test_c3_take_recommended_answers_every_open_choice(rig: Rig) -> None:
    with_run(rig)
    rig.svc.answer(ID, "c1", "red")
    rig.svc.take_recommended(ID)
    got = {i["id"]: i for i in view.items(rig.cache.tasks[0].body, None, rig.dir)}
    assert got["c1"]["answer"] == "red" and got["c2"]["answer"] == "no" and got["c2"]["state"] == "answered"
    with pytest.raises(BackendError, match="no open choice"):
        rig.svc.take_recommended(ID)


def test_answer_without_a_run_is_saved_but_sends_nothing(rig: Rig) -> None:
    rig.svc.take_recommended(ID)
    assert rig.sched.sent == [] and states(rig)["c1"] == "answered"


def test_send_failure_keeps_the_saved_answer(rig: Rig) -> None:
    with_run(rig)
    rig.sched.fail = True
    rig.svc.take_recommended(ID)
    assert states(rig)["c2"] == "answered"


def test_c6_add_then_run_then_plain_run(rig: Rig, tmp_path: Path) -> None:
    with_run(rig, str(tmp_path))
    with pytest.raises(BackendError, match="terminal"):
        rig.svc.run_command(ID, "k1", add=False)
    out = rig.svc.run_command(ID, "k1", add=True)
    assert out["exit"] == 0 and rig.calls == [("make fast", tmp_path)]
    assert allow.mode(rig.root, "make fast") == "run"
    rig.svc.run_command(ID, "k1", add=False)
    got = view.items(rig.cache.tasks[0].body, None, rig.dir)
    validate("ask", got)
    assert got[2]["state"] == "done" and got[2]["result"]["tail"] == "ok"
    with pytest.raises(BackendError, match="not a command"):
        rig.svc.run_command(ID, "c1", add=False)


def test_c7_c9_never_add_and_root_commands_never_run(rig: Rig) -> None:
    for command in ("! textgate approve", "sudo make install"):
        rig.cache.tasks[0].body = f"```ask\ncommand k1: {command}\n```"
        for add in (False, True):
            with pytest.raises(BackendError, match="terminal"):
                rig.svc.run_command(ID, "k1", add=add)
        item = view.items(rig.cache.tasks[0].body, None, rig.dir)[0]
        assert item["mode"] == "terminal" and item["warning"] is True
    assert rig.calls == []


def test_c11_reversible_choice_auto_adopts_after_a_day_and_undo_reopens(rig: Rig) -> None:
    with_run(rig)
    assert rig.svc.adopt_due() == 0
    first = view.items(rig.cache.tasks[0].body, None, rig.dir)[0]
    assert first["auto_at"] == 1000.0 + 24 * 3600
    rig.clock.now += 24 * 3600
    assert rig.svc.adopt_due() == 1  # c1 only: c2 is risky
    assert states(rig) == {"c1": "auto", "c2": "open", "k1": "open", "s1": "open"}
    assert json.loads((rig.dir / "asks.json").read_text())["log"] == ["auto-adopted c1: blue"]
    assert rig.svc.adopt_due() == 0
    rig.svc.undo(ID, "c1")
    assert states(rig)["c1"] == "open"
    rig.clock.now += 99 * 3600
    assert rig.svc.adopt_due() == 0  # an undone choice never auto-adopts again
    with pytest.raises(BackendError, match="nothing to undo"):
        rig.svc.undo(ID, "c1")


def test_c12_risky_choice_never_auto_adopts(rig: Rig) -> None:
    from asksfakes import Task

    rig.cache.tasks.append(Task("eeeeeeee-0", "plain note"))
    rig.svc.adopt_due()
    rig.clock.now += 1000 * 3600
    rig.svc.adopt_due()
    assert states(rig)["c2"] == "open"


def test_c10_screenshot_approve_and_reject(rig: Rig) -> None:
    with_run(rig)
    rig.svc.verdict(ID, "s1", approve=False)
    assert states(rig)["s1"] == "rejected" and "rejected the screenshot" in rig.sched.sent[0][1]
    rig.svc.verdict(ID, "s1", approve=True)
    assert states(rig)["s1"] == "approved"
    with pytest.raises(BackendError, match="not a screenshot"):
        rig.svc.verdict(ID, "c1", approve=True)


def test_reject_without_a_run_sends_nothing(rig: Rig) -> None:
    rig.svc.verdict(ID, "s1", approve=False)
    assert rig.sched.sent == []


def test_ask_in_the_run_reply_wins_over_the_note(rig: Rig) -> None:
    run = RunState(task_id=ID, stage="implement", extra={"last_reply": "```ask\ncommand z1: ls\n```"})
    rig.dir.mkdir(parents=True)
    save(rig.dir, run)
    from todoimpl.board.state import load

    assert [i["id"] for i in view.items("", load(rig.dir), rig.dir)] == ["z1"]


def test_corrupt_store_is_empty(rig: Rig) -> None:
    rig.dir.mkdir(parents=True)
    (rig.dir / "asks.json").write_text("[1]")
    assert states(rig)["c1"] == "open"


def test_start_runs_the_tick_in_a_daemon_thread(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    from todoimpl.asks import service

    ticks: list[int] = []
    done = threading.Event()

    def fake_adopt() -> int:
        ticks.append(1)
        if len(ticks) == 1:
            raise RuntimeError("boom")
        done.set()
        return 0

    monkeypatch.setattr(service, "TICK", 0.01)
    monkeypatch.setattr(rig.svc, "adopt_due", fake_adopt)
    rig.svc.start()
    assert done.wait(5)
