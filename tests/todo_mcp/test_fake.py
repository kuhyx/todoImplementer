"""The fake server itself: the faithfulness the other agents' tests rely on."""

from __future__ import annotations

import pytest
from fake_todo_mcp import FakeTodoMcp
from fake_todo_store import FakeStore, ToolError
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.transport import Transport


def test_add_appends_to_oldest_open_note_and_joins_checks() -> None:
    store = FakeStore()
    a = store.seed("kuhyx/r", "r todos", created="1", done_check="a", priority="low")
    store.seed("kuhyx/r", "r todos", created="2")
    out = store.call("add_task", {"repo": "kuhyx/r", "title": "t", "done_check": "b", "priority": "high"})
    assert out.startswith(f"appended to {a}")
    assert store.notes[a].done_check == "( a ) && ( b )"
    assert store.notes[a].priority == "high"


def test_add_without_existing_checks() -> None:
    store = FakeStore()
    store.call("add_task", {"repo": "kuhyx/r", "title": "t", "done_check": "x"})
    store.call("add_task", {"repo": "kuhyx/r", "title": "u"})
    (note,) = store.notes.values()
    assert note.done_check == "x"
    store.call("add_task", {"repo": "kuhyx/r", "title": "v", "done_check": ""})
    assert note.done_check == "x"


def test_prefix_ambiguity_and_unknown_tool() -> None:
    store = FakeStore()
    store.seed("kuhyx/a", "a", id="abcdef12-1")
    store.seed("kuhyx/a", "b", id="abcdef12-2")
    with pytest.raises(ToolError, match="matches 2 notes"):
        store.call("get_task", {"id": "abcdef12"})
    with pytest.raises(ToolError, match="unknown tool"):
        store.call("nope", {})
    assert store.call("get_task", {"id": "abcdef12-1"}).startswith("id: abcdef12-1")


@pytest.mark.parametrize(
    ("tool", "args", "match"),
    [
        ("add_task", {"repo": "kuhyx/r", "title": 5}, "title: must be a string"),
        ("add_task", {"repo": "kuhyx/r", "title": "t", "priority": "urgent"}, "priority: must be one of"),
        ("list_tasks", {"repo": "bad"}, "repo: must look like"),
    ],
)
def test_validation(tool: str, args: dict[str, object], match: str) -> None:
    with pytest.raises(ToolError, match=match):
        FakeStore().call(tool, args)


def test_update_reopen_clears_evidence_and_sets_repo() -> None:
    store = FakeStore()
    note_id = store.seed("kuhyx/a", "a", "body", status="done", evidence="e")
    store.call("update_task", {"id": note_id, "status": "todo", "repo": "kuhyx/z", "body": ""})
    note = store.notes[note_id]
    assert (note.status, note.evidence, note.repo, note.text) == ("todo", None, "kuhyx/z", "a")


def test_fail_next_and_clearing_method_failure() -> None:
    with FakeTodoMcp() as fake:
        fake.fail_method("tools/call", 500)
        fake.fail_method("tools/call", None)
        fake.fail_method("never-set", None)
        assert Transport(fake.url, fake.token).call_tool("list_tasks", {}) == "no tasks match"


def test_fake_is_idempotent_to_stop() -> None:
    fake = FakeTodoMcp().start()
    fake.stop()
    fake.stop()


def test_seed_sections() -> None:
    with FakeTodoMcp() as fake:
        note = fake.seed_sections("kuhyx/demo", [("a", "text"), ("b", "")])
        assert fake.store.notes[note].text == "demo todos\n\n## a\ntext\n\n## b"


def test_fake_reports_the_creator_in_detail_and_list() -> None:
    with FakeTodoMcp() as fake:
        fake.seed("kuhyx/r", "mine")
        fake.seed("kuhyx/r", "theirs", created_by="claude")
        client = TodoClient(fake.url, fake.token)
        assert sorted(t.created_by for t in client.list_tasks()) == ["claude", "kuhy"]
        assert sorted(t.created_by for t in client.list_tasks(full=True)) == ["claude", "kuhy"]
        added = client.add_task("kuhyx/new", "x")
        assert added.created_by == "claude"
