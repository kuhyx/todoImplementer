"""TodoClient behaviour against the fake server, JSON and SSE modes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_todo_mcp import FakeTodoMcp
from todoimpl.todo_mcp.client import Task, TodoClient, TodoError
from todoimpl.todo_mcp.transport import Transport


def test_list_open_by_default_and_hides_no_repo_notes(fake: FakeTodoMcp, client: TodoClient) -> None:
    fake.seed("kuhyx/a", "a todos", priority="high")
    fake.seed("kuhyx/b", "b todos", status="in_progress")
    fake.seed("kuhyx/c", "c todos", status="done")
    fake.seed(None, "personal note")
    tasks = client.list_tasks()
    assert [(t.title, t.status, t.priority) for t in tasks] == [
        ("a todos", "todo", "high"),
        ("b todos", "in progress", "medium"),
    ]
    assert all(t.body == "" and t.done_check is None for t in tasks)


def test_list_filters(fake: FakeTodoMcp, client: TodoClient) -> None:
    fake.seed("kuhyx/a", "a todos")
    fake.seed("kuhyx/b", "b todos", status="done")
    assert [t.repo for t in client.list_tasks(status="todo")] == ["kuhyx/a"]
    assert [t.repo for t in client.list_tasks(status="done")] == ["kuhyx/b"]
    assert len(client.list_tasks(status="all")) == 2
    assert [t.repo for t in client.list_tasks(repo="kuhyx/b", status="all")] == ["kuhyx/b"]
    assert client.list_tasks(status="abandoned") == []
    assert fake.calls[0] == ("list_tasks", {"status": "todo"})
    assert fake.calls[-1] == ("list_tasks", {"status": "abandoned"})


def test_list_in_progress_status_maps_to_wire(fake: FakeTodoMcp, client: TodoClient) -> None:
    fake.seed("kuhyx/a", "a todos", status="in_progress")
    assert [t.status for t in client.list_tasks(status="in progress")] == ["in progress"]
    assert fake.calls[0][1] == {"status": "in_progress"}


def test_list_full_fetches_details(fake: FakeTodoMcp, client: TodoClient) -> None:
    fake.seed("kuhyx/a", "a todos", "## x\nbody", done_check="true")
    (task,) = client.list_tasks(full=True)
    assert task.body == "## x\nbody"
    assert task.done_check == "true"


def test_list_server_error_is_not_empty(client: TodoClient) -> None:
    with pytest.raises(TodoError, match="status: must be one of"):
        client.list_tasks(status="bogus")


def test_get_task(fake: FakeTodoMcp, client: TodoClient) -> None:
    full = fake.seed("kuhyx/a", "a todos", "## x\nbody", priority="low", done_check="make")
    task = client.get_task(full[:8])
    assert task == Task(full[:8], "a todos", "## x\nbody", "kuhyx/a", "todo", "low", "make")


def test_get_task_unknown(client: TodoClient) -> None:
    with pytest.raises(TodoError, match="no live note"):
        client.get_task("deadbeef")


def test_get_task_short_id(client: TodoClient) -> None:
    with pytest.raises(TodoError, match="at least 8"):
        client.get_task("abc")


def test_add_task_creates_then_appends(fake: FakeTodoMcp, client: TodoClient) -> None:
    first = client.add_task("kuhyx/new", "do it", "what and where", "true", "high")
    assert (first.title, first.repo, first.priority, first.done_check) == (
        "new todos",
        "kuhyx/new",
        "high",
        "true",
    )
    assert first.body == "## do it\nwhat and where"
    second = client.add_task("kuhyx/new", "again")
    assert second.id == first.id
    assert second.body.endswith("## again")
    assert second.priority == "high"
    assert fake.calls[0] == (
        "add_task",
        {
            "repo": "kuhyx/new",
            "title": "do it",
            "body": "what and where",
            "done_check": "true",
            "priority": "high",
        },
    )


def test_add_task_rejects_bad_repo(client: TodoClient) -> None:
    with pytest.raises(TodoError, match="repo: must look like"):
        client.add_task("nope", "t")


def test_update_task(fake: FakeTodoMcp, client: TodoClient) -> None:
    full = fake.seed("kuhyx/a", "a todos", "body", done_check="old")
    updated = client.update_task(
        full[:8], title="renamed", status="in progress", done_check="", priority="high"
    )
    assert (updated.title, updated.status, updated.priority, updated.done_check) == (
        "renamed",
        "in progress",
        "high",
        None,
    )
    assert updated.body == "body"
    assert fake.calls[0][1]["status"] == "in_progress"


def test_update_task_skips_none_and_rejects_unknown_fields(fake: FakeTodoMcp, client: TodoClient) -> None:
    full = fake.seed("kuhyx/a", "a todos")
    assert client.update_task(full[:8], body=None, title="t").title == "t"
    assert fake.calls[0][1] == {"id": full[:8], "title": "t"}
    with pytest.raises(TodoError, match="unknown update field"):
        client.update_task(full[:8], colour="red")


def test_update_task_cannot_mark_done(fake: FakeTodoMcp, client: TodoClient) -> None:
    full = fake.seed("kuhyx/a", "a todos")
    with pytest.raises(TodoError, match="use close_task"):
        client.update_task(full[:8], status="done")


def test_close_task(fake: FakeTodoMcp, client: TodoClient) -> None:
    full = fake.seed("kuhyx/a", "a todos")
    client.close_task(full[:8], "abc1234 exit 0")
    note = fake.store.notes[full]
    assert (note.status, note.evidence) == ("done", "abc1234 exit 0")
    assert client.get_task(full[:8]).status == "done"


def test_close_task_requires_evidence(fake: FakeTodoMcp, client: TodoClient) -> None:
    full = fake.seed("kuhyx/a", "a todos")
    with pytest.raises(TodoError, match="evidence: required"):
        client.close_task(full[:8], "  ")
    assert fake.store.notes[full].status == "todo"


def test_search_tasks(fake: FakeTodoMcp, client: TodoClient) -> None:
    fake.seed("kuhyx/a", "a todos", "needle here", status="done")
    fake.seed("kuhyx/b", "b todos")
    assert [t.repo for t in client.search_tasks("NEEDLE")] == ["kuhyx/a"]
    assert client.search_tasks("zzz") == []


def test_unexpected_tool_text_is_error(fake: FakeTodoMcp, client: TodoClient) -> None:
    fake.force_text("list_tasks", "a\tb")
    with pytest.raises(TodoError, match="malformed"):
        client.list_tasks()
    fake.force_text("add_task", "weird")
    with pytest.raises(TodoError, match="malformed"):
        client.add_task("kuhyx/a", "t")


def test_forced_error_text(fake: FakeTodoMcp, client: TodoClient) -> None:
    fake.force_text("get_task", "error: boom", is_error=True)
    with pytest.raises(TodoError, match="boom"):
        client.get_task("abcdef12")


def test_from_env_defaults_read_token_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    token_dir = tmp_path / ".config" / "todo-mcp-client"
    token_dir.mkdir(parents=True)
    (token_dir / "token").write_text("sekret\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TODOIMPL_MCP_URL", raising=False)
    monkeypatch.delenv("TODOIMPL_MCP_TOKEN_FILE", raising=False)
    client = TodoClient.from_env()
    assert client.url == "http://127.0.0.1:8735/mcp"
    assert "sekret" not in repr(client)


def test_from_env_works_end_to_end(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with FakeTodoMcp(token="tok-123") as fake:
        token_file = tmp_path / "t"
        token_file.write_text("tok-123\n")
        monkeypatch.setenv("TODOIMPL_MCP_URL", fake.url)
        monkeypatch.setenv("TODOIMPL_MCP_TOKEN_FILE", str(token_file))
        assert TodoClient.from_env().list_tasks() == []


def test_from_env_explicit_mapping(tmp_path: Path) -> None:
    token_file = tmp_path / "t"
    token_file.write_text("x")
    client = TodoClient.from_env(
        {"TODOIMPL_MCP_TOKEN_FILE": str(token_file), "TODOIMPL_MCP_URL": "http://h/mcp"}
    )
    assert client.url == "http://h/mcp"


def test_from_env_missing_or_empty_token(tmp_path: Path) -> None:
    with pytest.raises(TodoError, match="token file"):
        TodoClient.from_env({"TODOIMPL_MCP_TOKEN_FILE": str(tmp_path / "absent")})
    empty = tmp_path / "empty"
    empty.write_text("\n")
    with pytest.raises(TodoError, match="empty"):
        TodoClient.from_env({"TODOIMPL_MCP_TOKEN_FILE": str(empty)})


def test_from_env_home_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(TodoError, match=str(tmp_path)):
        TodoClient.from_env({})


def test_repr_hides_token(fake: FakeTodoMcp, client: TodoClient) -> None:
    assert fake.token not in repr(client)
    assert fake.token not in repr(Transport(fake.url, fake.token))
