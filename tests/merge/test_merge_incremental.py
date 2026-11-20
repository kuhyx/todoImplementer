"""The classifier sees only new or edited notes, plus a short view of what is already grouped."""

import json
import re

from mergefakes import Rig
from test_merge_service import Brain, Clock, looked, make
from todoimpl.merge.service import INTERVAL


def rows(prompt: str) -> list[str]:
    """Ids of the full note rows (`id | repo | title | body`), not of the indented context lines."""
    return re.findall(r"^([0-9a-f]{8}-\d+) \| ", prompt, re.MULTILINE)


def seed(rig: Rig) -> list[str]:
    return rig.sections(
        "kuhyx/a", [("Make a text-free", "BODYAAAA"), ("Make b text-free", "BODYBBBB"), ("Other", "BODYCCCC")]
    )


def test_t1895_a_new_note_is_classified_against_the_groups_without_resending_the_old_ones(rig: Rig) -> None:
    ids = seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    looked(service)
    assert sorted(rows(brain.prompts[0])) == sorted(ids)  # the first run sends everything
    (new,) = rig.sections("kuhyx/b", [("Make c text-free", "BODYDDDD")])
    brain.answer = lambda _ids: json.dumps({"groups": []})
    clock.now += INTERVAL + 1
    looked(service)
    second = brain.prompts[1]
    assert rows(second) == [new]
    assert "BODYAAAA" not in second
    assert "BODYDDDD" in second
    stored = rig.store().load()
    assert new in stored.hashes
    assert set(stored.hashes) == {*ids, new}


def test_t1895_the_model_may_add_the_new_note_to_a_group_it_was_shown(rig: Rig) -> None:
    ids = seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    looked(service)
    first = rig.store().load().groups[0]["ids"]
    (new,) = rig.sections("kuhyx/b", [("Make c text-free", "BODYDDDD")])
    brain.answer = lambda _ids: json.dumps(
        {"groups": [{"ids": [*first, new], "title": "All three", "reason": "same work"}]}
    )
    clock.now += INTERVAL + 1
    looked(service)
    assert "Both" in brain.prompts[1]  # the existing group's title is context for the model
    groups = rig.store().load().groups
    assert [g["ids"] for g in groups] == [[*first, new]]
    assert [g["title"] for g in groups] == ["All three"]
    assert set(first) <= set(ids)


def test_t1895_a_new_note_can_pair_with_an_older_ungrouped_one(rig: Rig) -> None:
    ids = seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    looked(service)
    ungrouped = next(i for i in ids if i not in rig.store().load().groups[0]["ids"])
    (new,) = rig.sections("kuhyx/b", [("Other again", "BODYEEEE")])
    brain.answer = lambda _ids: json.dumps(
        {"groups": [{"ids": [ungrouped, new], "title": "Others", "reason": "duplicates"}]}
    )
    clock.now += INTERVAL + 1
    looked(service)
    assert f"  {ungrouped} | " in brain.prompts[1]  # shown by title only, without its body
    assert "BODYCCCC" not in brain.prompts[1]
    titles = sorted(g["title"] for g in rig.store().load().groups)
    assert titles == ["Both", "Others"]


def test_t1895_a_group_that_does_not_involve_a_new_note_is_ignored(rig: Rig) -> None:
    seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    looked(service)
    before = rig.store().load().groups
    old = before[0]["ids"]
    rig.sections("kuhyx/b", [("Unrelated", "")])
    brain.answer = lambda _ids: json.dumps({"groups": [{"ids": old, "title": "Rewritten", "reason": "x"}]})
    clock.now += INTERVAL + 1
    looked(service)
    assert rig.store().load().groups == before


def test_t1895_closing_a_note_asks_nothing_and_records_the_new_id_set(rig: Rig) -> None:
    ids = seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    looked(service)
    clock.now += INTERVAL + 1
    gone = next(i for i in ids if i not in rig.store().load().groups[0]["ids"])
    rig.client.close_item(rig.cards([gone])[0].item, "done by hand")
    rig.cache.refresh()
    assert service.refresh_if_due() is False
    assert len(brain.prompts) == 1
    stored = rig.store().load()
    assert gone not in (stored.ids or [])
    assert gone not in stored.hashes


def test_t1895_an_edited_note_is_classified_again_and_leaves_its_old_group(rig: Rig) -> None:
    ids = seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    looked(service)
    assert rig.store().load().groups[0]["ids"] == ids[:2]
    member = ids[0]
    for note in rig.fake.store.notes.values():
        note.text = note.text.replace("BODYAAAA", "CHANGED")
    rig.cache.refresh()
    brain.answer = lambda _ids: json.dumps({"groups": []})
    clock.now += INTERVAL + 1
    looked(service)
    assert len(brain.prompts) == 2
    assert rows(brain.prompts[1]) == [member]
    assert rig.store().load().groups == []  # the edited note left a pair with nobody else in it


def test_t1895_a_merge_json_from_before_the_hashes_gets_one_full_run(rig: Rig) -> None:
    ids = seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    looked(service)
    rig.store().update(lambda s: setattr(s, "hashes", {}))  # an old file: ids, no hashes
    clock.now += INTERVAL + 1
    looked(service)
    assert sorted(rows(brain.prompts[1])) == sorted(ids)


def test_t1895_a_failed_incremental_run_is_retried_for_the_same_notes(rig: Rig) -> None:
    seed(rig)
    brain, clock = Brain(), Clock()
    service = make(rig, brain, clock)
    looked(service)
    (new,) = rig.sections("kuhyx/b", [("Make c text-free", "")])
    brain.error = RuntimeError("down")
    clock.now += INTERVAL + 1
    looked(service)
    brain.error = None
    brain.answer = lambda _ids: json.dumps({"groups": []})
    clock.now += INTERVAL + 1
    looked(service)
    assert rows(brain.prompts[-1]) == [new]
