"""Scheduler live events are enriched with the server-computed card fields (T102)."""

from typing import Any

from contract_lib import validate
from servicefakes import Rig

ACTIVITY = {"type": "activity", "seq": 1, "at": 5.0, "kind": "text", "text": "hi", "tool": None}


def stream(rig: Rig, card: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rig.scheduler.events = events
    return list(rig.backend.subscribe(card))


def test_t102_every_event_type_validates_against_live_schema(rig: Rig) -> None:
    tid = rig.note()
    rig.run(tid, "gate")
    out = stream(
        rig,
        tid,
        [ACTIVITY, {"type": "stage", "stage": "gate"}, {"type": "cost", "cost_usd": 1.5}, {"type": "done"}],
    )
    assert [e["type"] for e in out] == ["activity", "stage", "cost", "done"]
    for event in out:
        validate("live", event)
    card = rig.card(tid)
    stage = out[1]
    assert (stage["status"], stage["column"], stage["actions"]) == (
        card["status"],
        card["column"],
        card["actions"],
    )
    assert out[3]["status"] == card["status"]
    assert out[0] == ACTIVITY
    assert out[2] == {"type": "cost", "cost_usd": 1.5}


def test_stage_event_for_a_card_without_a_run_uses_the_event_stage(rig: Rig) -> None:
    tid = rig.note()
    (event,) = stream(rig, tid, [{"type": "stage", "stage": "spec"}])
    validate("live", event)
    assert event["stage"] == "spec"
    assert event["status"] == rig.card(tid)["status"]


def test_events_that_need_a_card_are_dropped_when_the_card_is_gone(rig: Rig) -> None:
    out = stream(rig, "zzzzzzzz-0", [{"type": "stage", "stage": "gate"}, {"type": "done"}, ACTIVITY])
    assert out == [ACTIVITY]
