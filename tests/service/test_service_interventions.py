"""Every accepted click of kuhy (except Ship) leaves a line in the run's interventions.jsonl."""

import pytest
from servicefakes import Rig
from todoimpl.http.backend import BackendError
from todoimpl.runner.scheduler import RunnerError
from todoimpl.usage.interventions import recorded


def test_accepted_clicks_are_recorded_and_ship_is_not(rig: Rig) -> None:
    b = rig.backend
    b._clock = lambda: 42.0
    b.start("t1")
    rig.run("t1", "failed")
    b.start("t1")
    b.spec_answers("t1", {"Q1": "a"})
    b.spec_ok("t1")
    b.send("t1", "hi")
    b.cancel("t1")
    b.ship("t1")
    kinds = [kind for _, kind in recorded(rig.root / "t1") or []]
    assert kinds == ["start", "retry", "spec_answers", "spec_ok", "send", "cancel"]
    assert {at for at, _ in recorded(rig.root / "t1") or []} == {42.0}


def test_a_refused_action_leaves_no_record(rig: Rig) -> None:
    rig.scheduler.failure = RunnerError("nope", "conflict")
    with pytest.raises(BackendError):
        rig.backend.send("t1", "hi")
    assert recorded(rig.root / "t1") is None


def test_go_and_rerun_clicks_are_recorded(rig: Rig) -> None:
    for kind in ("go", "rerun"):
        tid = rig.note()
        rig.run(tid, "failed", extra={"permission": {"command": "echo hi", "tty": False}})
        rig.backend.fix_runner = lambda _command: (0, "")
        getattr(rig.backend, kind)(tid)
        assert [k for _, k in recorded(rig.root / tid) or []] == [kind]
