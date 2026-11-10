"""The merge state file: ids/time of the last classification, groups, dismissed and created ledgers."""

from pathlib import Path

from todoimpl.merge.store import MergeStore


def test_empty_root_gives_the_blank_state(tmp_path: Path) -> None:
    state = MergeStore(tmp_path / "run").load()
    assert (state.ids, state.at, state.groups, state.dismissed, state.created) == (None, 0.0, [], [], {})


def test_update_round_trips_and_keeps_other_fields(tmp_path: Path) -> None:
    store = MergeStore(tmp_path)
    store.update(lambda s: s.dismissed.append("fp1"))
    store.update(lambda s: s.created.update({"fp2": {"id": "abcd1234-0", "titles": {}}}))
    store.update(lambda s: setattr(s, "ids", ["a-0"]))
    again = MergeStore(tmp_path).load()
    assert (again.dismissed, again.created, again.ids) == (
        ["fp1"],
        {"fp2": {"id": "abcd1234-0", "titles": {}}},
        ["a-0"],
    )


def test_corrupt_or_wrong_shaped_file_reads_as_blank(tmp_path: Path) -> None:
    (tmp_path / "merge.json").write_text("{nope")
    assert MergeStore(tmp_path).load().ids is None
    (tmp_path / "merge.json").write_text("[1]")
    assert MergeStore(tmp_path).load().groups == []
    (tmp_path / "merge.json").write_text('{"ids": "x", "at": "y", "groups": 3, "dismissed": 4, "created": 5}')
    state = MergeStore(tmp_path).load()
    assert (state.ids, state.at, state.groups, state.dismissed, state.created) == (None, 0.0, [], [], {})
