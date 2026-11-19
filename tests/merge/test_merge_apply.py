"""apply_merge against the fake todo MCP: same-repo card, umbrella note, refusals, reruns."""

from typing import Any

import pytest
from mergefakes import Rig
from todoimpl.merge.apply import MergeError, MergeResult, apply_merge
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.items import Item
from todoimpl.todo_mcp.model import TodoError

REPO = "kuhyx/a"


def merge(rig: Rig, ids: list[str], title: str = "Text-free sweep") -> MergeResult:
    return apply_merge(rig.client, rig.root, rig.store(), rig.cards(ids), title, rig.create_umbrella)


def note_text(rig: Rig, card_id: str) -> str:
    return next(n.text for k, n in rig.fake.store.notes.items() if k.startswith(card_id[:8]))


def test_same_repo_adds_one_combined_card_and_cuts_every_member_out(rig: Rig) -> None:
    ids = rig.sections(
        REPO, [("Make a text-free", "body one"), ("Make b text-free", "body two"), ("Unrelated", "u")]
    )
    result = merge(rig, ids[:2])
    assert rig.open_titles(REPO) == ["Unrelated", "Text-free sweep"]  # one new card, not one per member
    assert (result.kind, result.removed, result.closed) == ("repo", tuple(ids[:2]), ())
    assert result.new_id == f"{ids[0][:8]}-1"  # the new card moved up when the members left
    text = note_text(rig, ids[0])
    assert "## Make a text-free" not in text
    assert f"### {ids[0][:8]}-0\nMake a text-free\n\nbody one" in text
    assert "### " + ids[1][:8] + "-1\nMake b text-free" in text
    assert rig.store().load().created[next(iter(rig.store().load().created))]["id"] == result.new_id


def test_tier_and_top_priority_carry_over(rig: Rig) -> None:
    ids = rig.sections(REPO, [("A", "Tier: cheap"), ("B", "")])
    rig.fake.store.notes[next(iter(rig.fake.store.notes))].priority = "high"
    rig.cache.refresh()
    merge(rig, ids)
    text = note_text(rig, ids[0])
    assert "## Text-free sweep\nTier: cheap" in text


def test_several_repos_make_one_umbrella_note_without_a_repo(rig: Rig) -> None:
    one = rig.sections("kuhyx/one", [("Make one text-free (textgate-rework)", "b1")])
    two = rig.sections("kuhyx/two", [("Make two text-free (textgate-rework)", "b2")])
    result = merge(rig, [*one, *two], "Text-free everywhere")
    assert result.kind == "umbrella"
    umbrella = rig.fake.store.notes[next(k for k in rig.fake.store.notes if k.startswith(result.new_id))]
    assert umbrella.repo is None
    assert rig.umbrellas[0].startswith(
        "# Text-free everywhere\nUmbrella: per-repo\nTier: cheap\n- [ ] kuhyx/one ("
    )
    assert f"## kuhyx/two ({two[0][:8]})\nMake two text-free (textgate-rework)\n\nb2" in rig.umbrellas[0]
    assert (result.removed, result.closed) == ((*one, *two), ())
    for note in rig.fake.store.notes.values():
        if note.repo is not None:  # emptied notes close with the evidence
            assert (note.status, note.evidence) == ("done", f"merged into {result.new_id}")
    assert rig.open_titles("kuhyx/one") == [] == rig.open_titles("kuhyx/two")


def test_a_rerun_after_a_failed_cut_finishes_without_a_second_note(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    one = rig.sections(REPO, [("A", ""), ("Keep one", "")])
    two = rig.sections(REPO, [("B", ""), ("Keep two", "")])
    real = rig.client.update_task
    calls: list[str] = []

    def flaky(note: str, **fields: str | None) -> Any:
        calls.append(note)
        if len(calls) == 2:
            raise TodoError("boom")
        return real(note, **fields)

    monkeypatch.setattr(rig.client, "update_task", flaky)
    ids = [one[0], two[0]]
    with pytest.raises(TodoError, match="boom"):
        merge(rig, ids)
    monkeypatch.undo()
    result = merge(rig, ids)  # the first note's ids already name other sections: they are skipped
    assert result.removed == (two[0],)
    assert sorted(rig.open_titles(REPO)) == ["Keep one", "Keep two", "Text-free sweep"]
    assert merge(rig, ids).removed == ()


def test_sections_after_a_cut_keep_their_titles_and_runs_block_a_cut(rig: Rig) -> None:
    ids = rig.sections(REPO, [("A", ""), ("B", ""), ("Later", "")])
    rig.run(ids[2], "failed")  # a section after the cut has a run dir: ids must not shift
    result = merge(rig, ids[:2])
    assert (result.removed, result.closed) == ((), tuple(ids[:2]))
    assert rig.open_titles(REPO) == ["Later", "Text-free sweep"]
    assert note_text(rig, ids[0]).count(f"closed: merged into {result.new_id}") == 2


def test_a_member_with_its_own_resting_run_is_closed_in_place(rig: Rig) -> None:
    ids = rig.sections(REPO, [("A", ""), ("B", "")])
    rig.run(ids[0], "cancelled")
    assert merge(rig, ids).closed == tuple(ids)


def test_a_note_left_with_only_done_sections_is_closed_with_the_evidence(rig: Rig) -> None:
    ids = rig.sections(REPO, [("Done already", ""), ("A", "")])
    rig.client.close_item(rig.cards(ids[:1])[0].item, "by hand")
    other = rig.sections("kuhyx/b", [("B", "")])
    rig.cache.refresh()
    result = merge(rig, [ids[1], *other])
    note = rig.fake.store.notes[next(k for k in rig.fake.store.notes if k.startswith(ids[0][:8]))]
    assert (note.status, note.evidence) == ("done", f"merged into {result.new_id}")


def test_a_whole_note_member_is_closed_in_place(rig: Rig) -> None:
    one = rig.fake.seed(REPO, "Plain note one", "text")
    rig.fake.seed("kuhyx/b", "Plain note two", "text")
    rig.cache.refresh()
    ids = [f"{one[:8]}-0", next(c.id for c in rig.cache.snapshot().tasks if c.repo == "kuhyx/b")]
    result = merge(rig, ids)
    assert result.removed == ()
    assert set(result.closed) == set(ids)


def test_a_title_already_open_in_the_repo_is_a_conflict(rig: Rig) -> None:
    ids = rig.sections(REPO, [("A", ""), ("B", ""), ("Text-free sweep", "")])
    with pytest.raises(MergeError) as err:
        merge(rig, ids[:2])
    assert err.value.code == "conflict"
    assert rig.open_titles(REPO) == ["A", "B", "Text-free sweep"]


@pytest.mark.parametrize("stage", ["implement", "gate", "paused_retry", "shipping"])
def test_a_live_run_blocks_the_merge_and_changes_nothing(rig: Rig, stage: str) -> None:
    ids = rig.sections(REPO, [("A", ""), ("B", "")])
    rig.run(ids[1], stage)
    with pytest.raises(MergeError) as err:
        merge(rig, ids)
    assert (err.value.code, ids[1] in err.value.message, stage in err.value.message) == (
        "disabled",
        True,
        True,
    )
    assert rig.open_titles(REPO) == ["A", "B"]


@pytest.mark.parametrize("stage", ["failed", "cancelled", "spec_wait", "paused_limit"])
def test_a_resting_run_does_not_block(rig: Rig, stage: str) -> None:
    ids = rig.sections(REPO, [("A", ""), ("B", "")])
    rig.run(ids[0], stage)
    assert merge(rig, ids).kind == "repo"


def card(card_id: str, repo: str | None, status: str = "todo") -> CardTask:
    item = Item(card_id[:8], 0, "t", "", repo, status, None)
    return CardTask(card_id, "t", "", repo, status, "medium", None, item)


@pytest.mark.parametrize(
    ("cards", "title"),
    [
        ([card("aaaaaaaa-0", REPO)], "T"),
        ([card("aaaaaaaa-0", REPO), card("aaaaaaaa-0", REPO)], "T"),
        ([card("aaaaaaaa-0", REPO), card("bbbbbbbb-0", REPO)], "  "),
        ([card("aaaaaaaa-0", None), card("bbbbbbbb-0", None)], "T"),
        ([card("aaaaaaaa-0", REPO), card("bbbbbbbb-0", REPO, "done")], "T"),
        ([card("aaaaaaaa-0", REPO), card("bbbbbbbb-0", REPO, "abandoned")], "T"),
    ],
)
def test_bad_input_is_refused(rig: Rig, cards: list[CardTask], title: str) -> None:
    with pytest.raises(MergeError) as err:
        apply_merge(rig.client, rig.root, rig.store(), cards, title, rig.create_umbrella)
    assert err.value.code == "bad_request"


def test_an_umbrella_the_todo_app_does_not_have_closes_nothing(rig: Rig) -> None:
    one = rig.sections("kuhyx/one", [("A", "")])
    two = rig.sections("kuhyx/two", [("B", "")])

    def lost(text: str) -> str:
        return "ffffffff"

    with pytest.raises(MergeError) as err:
        apply_merge(rig.client, rig.root, rig.store(), rig.cards([*one, *two]), "T", lost)
    assert err.value.code == "upstream_unavailable"
    assert rig.open_titles("kuhyx/one") == ["A"]


def test_a_combined_note_that_cannot_be_found_is_internal(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = rig.sections(REPO, [("A", ""), ("B", "")])
    real: Any = rig.client.add_task
    monkeypatch.setattr(rig.client, "add_task", lambda *_a, **_k: real(REPO, "Other", "x"))
    with pytest.raises(MergeError) as err:
        merge(rig, ids)
    assert err.value.code == "internal"


def test_a_lagging_umbrella_is_not_created_twice(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    one = rig.sections("kuhyx/one", [("A", "")])
    two = rig.sections("kuhyx/two", [("B", "")])
    real = rig.client.get_task
    seen: list[str] = []

    def lagging(note: str) -> Any:
        seen.append(note)
        if len(seen) == 1:
            raise TodoError("not synced yet")
        return real(note)

    monkeypatch.setattr(rig.client, "get_task", lagging)
    with pytest.raises(MergeError) as err:
        merge(rig, [*one, *two])
    assert err.value.code == "upstream_unavailable"
    assert rig.open_titles("kuhyx/one") == ["A"]
    monkeypatch.undo()
    assert merge(rig, [*one, *two]).kind == "umbrella"
    assert len(rig.umbrellas) == 1
