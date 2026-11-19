"""The note `merge/text.py` writes is the note the umbrella reads, and the board finds it with no repo."""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_todo_mcp import FakeTodoMcp
from todoimpl.board.state import run_root
from todoimpl.merge.store import MergeStore
from todoimpl.merge.text import umbrella_text
from todoimpl.service import ServiceBackend, build_backend
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.items import Item
from todoimpl.todo_mcp.model import Task
from todoimpl.umbrella import note, registry


def _card(  # noqa: PLR0917
    note_id: str, index: int, repo: str, title: str, body: str, check: str | None = None
) -> CardTask:
    task = Task(note_id, f"{repo} todos", body, repo, "todo", "medium", None)
    return CardTask.of(task, Item(note_id, index, title, body, repo, "todo", check))


CARDS = [
    _card(
        "aaaa1111",
        0,
        "kuhyx/alpha",
        "Make alpha text-free (textgate-rework)",
        "Scan textgate: 5 items",
        "make lint",
    ),
    _card("bbbb2222", 1, "kuhyx/beta", "Make beta text-free (textgate-rework)", "Scan textgate: 2 items"),
    _card("bbbb2222", 3, "kuhyx/beta", "Make beta2 text-free (textgate-rework)", "Scan textgate: 9 items"),
]


def test_a_merge_written_umbrella_parses_into_children_with_unique_ids() -> None:
    text = umbrella_text("Make the repos text-free", CARDS)
    body = text.split("\n", 1)[1]
    assert note.is_umbrella(body)
    assert note.tier(body) == "cheap"
    kids = note.children(body)
    assert [k.label for k in kids] == ["aaaa1111-0", "bbbb2222-1", "bbbb2222-3"]
    assert [k.repo for k in kids] == ["kuhyx/alpha", "kuhyx/beta", "kuhyx/beta"]
    assert [k.scan for k in kids] == [5, 2, 9]
    assert kids[0].done_check == "make lint"  # merge renames it `member done_check:`; the umbrella keeps it
    assert [c.key for c in note.ordered(kids)] == ["bbbb2222-1", "aaaa1111", "bbbb2222-3"]


def test_ticking_a_card_id_labelled_child_leaves_the_others() -> None:
    body = umbrella_text("t", CARDS).split("\n", 1)[1]
    once = note.tick(body, "bbbb2222-3")
    assert [k.done for k in note.children(once)] == [False, False, True]
    assert note.tick(once, "bbbb2222-3") == once


@pytest.fixture
def backend(fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ServiceBackend:
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path / "run"))
    return build_backend(
        root=tmp_path / "run", build="b1", client=TodoClient(fake.url, fake.token), refresh=False
    )


def test_t2058_a_repo_less_umbrella_is_listed_and_the_merge_ledger_adds_no_second_card(
    fake: FakeTodoMcp, backend: ServiceBackend
) -> None:
    text = umbrella_text("Make the repos text-free", CARDS)
    title, body = text.split("\n", 1)
    note_id = fake.seed(None, title.removeprefix("# "), body)
    backend.cache.refresh()
    (card,) = backend.board()["tasks"]  # list_tasks(no_repo) brings it with no ledger entry
    MergeStore(run_root()).update(lambda s: s.created.update({"fp": {"id": note_id, "titles": []}}))
    backend.cache.refresh()
    (card,) = backend.board()["tasks"]
    assert card["id"] == f"{note_id[:8]}-0"
    assert (card["repo"], card["status"], card["assignee"]) == (None, "backlog", "claude")
    assert card["umbrella"]["total"] == 3
    assert "start" in [a["id"] for a in card["actions"] if a["enabled"]]


def test_the_ledger_names_the_same_note_the_registry_file_does(tmp_path: Path) -> None:
    MergeStore(tmp_path).update(lambda s: s.created.update({"a": {"id": "abc12345"}, "b": {"titles": []}}))
    assert registry.ids(tmp_path) == ["abc12345"]
