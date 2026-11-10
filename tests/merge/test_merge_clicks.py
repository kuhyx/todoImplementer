"""MergeService clicks and the view: dismiss, shrinking groups, live-run refusal, merge, error mapping."""

import json
import threading

import pytest
from mergefakes import Rig
from test_merge_service import Brain, Clock, make, seed
from todoimpl.http.backend import BackendError
from todoimpl.merge import service as service_module


def test_dismissed_and_closed_members_are_not_suggested_again(rig: Rig) -> None:
    ids = seed(rig)
    service = make(rig, Brain(), Clock())
    shown = service.suggestions()["suggestions"][0]
    out = service.dismiss(shown["id"])
    assert out == {"ok": True, "new_id": None, "suggestions": []}
    assert service.suggestions()["suggestions"] == []
    assert make(rig, Brain(), Clock()).suggestions()["suggestions"] == []  # survives a restart
    assert ids  # the notes themselves are untouched
    assert rig.open_titles("kuhyx/a") == ["Make a text-free", "Make b text-free", "Other"]


def test_a_group_loses_members_that_closed_and_vanishes_below_two(rig: Rig) -> None:
    ids = rig.sections("kuhyx/a", [("A", ""), ("B", ""), ("C", "")])
    brain = Brain()
    brain.answer = lambda found: json.dumps({"groups": [{"ids": found, "title": "All", "reason": "r"}]})
    service = make(rig, brain, Clock())
    assert len(service.suggestions()["suggestions"][0]["members"]) == 3
    rig.client.close_item(rig.cards(ids)[0].item, "done by hand")
    rig.cache.refresh()
    assert len(service.suggestions()["suggestions"][0]["members"]) == 2
    rig.client.close_item(rig.cards(ids[1:])[0].item, "done by hand")
    rig.cache.refresh()
    assert service.suggestions()["suggestions"] == []


def test_a_live_run_disables_merge_with_its_reason_and_the_click_is_refused(rig: Rig) -> None:
    ids = seed(rig)
    service = make(rig, Brain(), Clock())
    shown = service.suggestions()["suggestions"][0]
    rig.run(shown["members"][0]["id"], "implement")
    merge = service.suggestions()["suggestions"][0]["actions"][0]
    assert merge["enabled"] is False
    assert "live run (implement)" in merge["reason"]
    with pytest.raises(BackendError) as err:
        service.merge(shown["id"])
    assert err.value.code == "disabled"
    assert rig.open_titles("kuhyx/a") == ["Make a text-free", "Make b text-free", "Other"]
    assert ids


def test_merge_click_creates_the_note_and_answers_the_fresh_suggestions(rig: Rig) -> None:
    ids = seed(rig)
    service = make(rig, Brain(), Clock())
    shown = service.suggestions()["suggestions"][0]
    out = service.merge(shown["id"])
    assert out["ok"] is True
    assert out["new_id"].startswith(ids[0][:8])
    assert out["suggestions"] == []
    assert rig.open_titles("kuhyx/a") == ["Other", "Both"]


def test_clicks_on_an_unknown_group_are_not_found(rig: Rig) -> None:
    service = make(rig, Brain(), Clock())
    for click in (service.merge, service.dismiss):
        with pytest.raises(BackendError) as err:
            click("0" * 12)
        assert err.value.code == "not_found"


def test_a_second_merge_while_one_runs_is_a_conflict(rig: Rig) -> None:
    seed(rig)
    service = make(rig, Brain(), Clock())
    shown = service.suggestions()["suggestions"][0]
    assert service._merging.acquire(blocking=False)
    with pytest.raises(BackendError) as err:
        service.merge(shown["id"])
    assert err.value.code == "conflict"


def test_merge_errors_become_backend_errors(rig: Rig) -> None:
    seed(rig)
    service = make(rig, Brain(), Clock())
    shown = service.suggestions()["suggestions"][0]
    rig.fake.fail_method("tools/call", 500)
    with pytest.raises(BackendError) as err:
        service.merge(shown["id"])
    assert err.value.code == "upstream_unavailable"
    rig.fake.fail_method("tools/call", None)
    rig.sections("kuhyx/a", [("Both", "")])  # the proposed title is now taken
    shown = service.suggestions()["suggestions"][0]
    with pytest.raises(BackendError) as err2:
        service.merge(shown["id"])
    assert err2.value.code == "conflict"


def test_the_default_spawn_runs_the_job_on_a_thread() -> None:
    done = threading.Event()
    service_module._spawn(done.set)
    assert done.wait(5)


def test_an_unreadable_run_state_disables_merge(rig: Rig) -> None:
    seed(rig)
    service = make(rig, Brain(), Clock())
    shown = service.suggestions()["suggestions"][0]
    state = rig.root / shown["members"][0]["id"] / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{nope")
    merge = service.suggestions()["suggestions"][0]["actions"][0]
    assert merge["enabled"] is False
    assert "unreadable" in merge["reason"]


def test_a_member_whose_title_changed_leaves_the_group(rig: Rig) -> None:
    rig.sections("kuhyx/a", [("A", ""), ("B", ""), ("C", "")])
    brain = Brain()
    brain.answer = lambda found: json.dumps({"groups": [{"ids": found, "title": "All", "reason": "r"}]})
    service = make(rig, brain, Clock())
    assert len(service.suggestions()["suggestions"][0]["members"]) == 3
    note = next(iter(rig.fake.store.notes.values()))
    # as if a cut had moved another section into B's place
    note.text = note.text.replace("## B", "## Renamed")
    rig.cache.refresh()
    members = service.suggestions()["suggestions"][0]["members"]
    assert [m["title"] for m in members] == ["A", "C"]
