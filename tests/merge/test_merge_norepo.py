"""A note with no repo merges into a repo's note through the normal path (kuhy, 2026-11-19)."""

import pytest
from mergefakes import Rig
from todoimpl.merge import __main__ as cli
from todoimpl.merge.apply import MergeError, apply_merge
from todoimpl.service.cards import CardTask, card_tasks
from todoimpl.todo_mcp.client import TodoClient

REPO = "kuhyx/a"


def loose(rig: Rig, title: str, body: str) -> list[CardTask]:
    """Return a repo-less note as the merge sees it: fetched by id, as the repo cache never lists it."""
    return card_tasks(rig.client.get_task(rig.fake.seed(None, title, body)))


def test_t2093_a_note_with_no_repo_merges_into_the_repo_of_its_partner(rig: Rig) -> None:
    """The merge refused `has no repo`, so the logo note could only be merged by hand into the site's part."""
    ids = rig.sections(REPO, [("Design the logo", "site part"), ("Other", "o")])
    stray = loose(rig, "Logo for me", "K U / H Y in bold")
    result = apply_merge(
        rig.client,
        rig.root,
        rig.store(),
        [*rig.cards(ids[:1]), *stray],
        "Logo candidates",
        rig.create_umbrella,
    )
    assert (result.kind, rig.umbrellas) == ("repo", [])
    assert rig.open_titles(REPO) == ["Other", "Logo candidates"]
    text = next(n.text for n in rig.fake.store.notes.values() if n.repo == REPO)
    assert "Design the logo\n\nsite part" in text
    assert "Logo for me\n\nK U / H Y in bold" in text
    closed = next(n for n in rig.fake.store.notes.values() if n.repo is None)
    assert (closed.status, closed.evidence) == ("done", f"merged into {result.new_id}")


def test_t2093_the_cli_names_the_repo_less_note_by_its_id(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TodoClient, "from_env", classmethod(lambda _cls, _env=None: rig.client))
    ids = rig.sections(REPO, [("Design the logo", "site part"), ("Other", "o")])
    stray = rig.fake.seed(None, "Logo for me", "K U / H Y")
    assert cli.main(["--group", f"{ids[0]},{stray[:8]}", "--title", "Logos", "--dry-run"]) == 0
    assert cli.main(["--group", f"{ids[0]},{stray[:8]}", "--title", "Logos"]) == 0
    assert rig.open_titles(REPO) == ["Other", "Logos"]


def test_t2093_two_repo_less_notes_or_a_mix_of_repos_stay_refused(rig: Rig) -> None:
    one = rig.sections("kuhyx/one", [("A", "")])
    two = rig.sections("kuhyx/two", [("B", "")])
    for cards in (
        [*loose(rig, "x", ""), *loose(rig, "y", "")],  # nothing says where it goes
        [*rig.cards(one), *rig.cards(two), *loose(rig, "z", "")],  # two repos: an umbrella needs repos on all
    ):
        with pytest.raises(MergeError) as err:
            apply_merge(rig.client, rig.root, rig.store(), cards, "T", rig.create_umbrella)
        assert err.value.code == "bad_request"
