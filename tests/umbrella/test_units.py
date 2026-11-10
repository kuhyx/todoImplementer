"""Small pieces: the fan-out handle, the closer, the pool's crash guard, child rows, the registry."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from fake_todo_mcp import FakeTodoMcp
from todoimpl.board import state as store
from todoimpl.runner.launch import Handle
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.model import Task
from todoimpl.umbrella import children, note, registry, view
from todoimpl.umbrella.store import child_dir
from umbrellafakes import sample

NOTE = Task("n0000001", "t", "", None, "todo", "medium", None)


def _handle(tmp: Path, stops: list[str], name: str) -> Handle:
    class Stopper(Handle):
        def stop(self, grace: float = 3.0) -> None:
            stops.append(name)

    return Stopper(tmp, name, None)


def test_the_fan_stops_every_registered_turn_and_later_ones_too(tmp_path: Path) -> None:
    stops: list[str] = []
    fan = children.make_fan(tmp_path)
    fan.slot("a")(_handle(tmp_path, stops, "a"))
    fan.slot("b")(_handle(tmp_path, stops, "b"))
    fan.slot("b")(None)
    fan.stop()
    assert stops == ["a"]
    fan.slot("c")(_handle(tmp_path, stops, "c"))
    deadline = time.monotonic() + 5
    while "c" not in stops and time.monotonic() < deadline:
        time.sleep(0.01)
    assert stops == ["a", "c"]


def test_detaching_the_fan_detaches_current_and_later_handles(tmp_path: Path) -> None:
    fan = children.make_fan(tmp_path)
    first = _handle(tmp_path, [], "a")
    fan.slot("a")(first)
    fan.detach.set()
    assert first.detach.is_set()
    late = _handle(tmp_path, [], "b")
    fan.slot("b")(late)
    assert late.detach.is_set()


@dataclass
class Parent:
    ticks: list[tuple[str, str]]
    added: list[tuple[str, str, str]]

    def tick_child(self, card: str, cid: str) -> None:
        self.ticks.append((card, cid))

    def add_task(self, repo: str, title: str, body: str = "") -> Task:
        self.added.append((repo, title, body))
        return NOTE


def test_the_closer_ticks_the_checkbox_and_forwards_follow_ups() -> None:
    parent = Parent([], [])
    client = children.ChildClient(parent, "umbr0001-0", {"umbr0001-1": "aaaa1111-0"})
    client.close_task("umbr0001-1", "evidence is kept in the child's state")
    assert parent.ticks == [("umbr0001-0", "aaaa1111-0")]
    assert client.add_task("kuhyx/a", "follow", "body") is NOTE
    assert parent.added == [("kuhyx/a", "follow", "body")]


def test_a_crashing_child_drive_is_logged_not_raised(tmp_path: Path) -> None:
    class Boom:
        state = store.RunState(task_id="aaaa1111-0", stage="implement")

        def run(self) -> None:
            msg = "boom"
            raise RuntimeError(msg)

    pool = children.Pool.__new__(children.Pool)
    pool.detached = False
    pool._drive(Boom())  # type: ignore[arg-type]
    assert not pool.detached
    pool.threads = {"x": threading.Thread(target=lambda: None)}
    pool.threads["x"].start()
    pool.wait()
    assert pool.threads == {}


def test_a_corrupt_child_state_reads_as_a_failed_row(tmp_path: Path) -> None:
    (child_dir(tmp_path, "aaaa1111-0")).mkdir(parents=True)
    (child_dir(tmp_path, "aaaa1111-0") / "state.json").write_text("{nope", encoding="utf-8")
    st = view.child_state(tmp_path, "aaaa1111-0")
    assert st is not None
    assert (st.stage, "not valid JSON" in str(st.error)) == ("failed", True)


def test_overlay_adds_child_rows_and_cost_and_leaves_plain_runs_alone(tmp_path: Path) -> None:
    plain = store.RunState(task_id="x-0", stage="implement")
    assert view.overlay(tmp_path, plain, live=False, limit_until=None) is plain
    kid = {"id": "aaaa1111-0", "repo": "kuhyx/alpha", "title": "Alpha", "done": False}
    st = store.RunState(
        task_id="umbr0001-0", stage="implement", cost_usd=1.0, extra={"umbrella": {"kids": [kid]}}
    )
    child = store.RunState(task_id="aaaa1111-0", stage="live_check", cost_usd=0.5)
    child.extra.update(verdict={"kind": "clean", "detail": ""}, free=True, umbrella_round=2)
    store.save(child_dir(tmp_path, "aaaa1111-0"), child)
    out = view.overlay(tmp_path, st, live=True, limit_until=None)
    (row,) = out.extra["umbrella_view"]["rows"]
    assert (row["status"], row["verdict"], row["free"], row["round"]) == ("working", "clean", True, 2)
    assert out.cost_usd == 1.5
    assert "umbrella_view" not in st.extra


def test_registry_reads_ids_with_comments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert registry.ids(tmp_path) == []
    file = tmp_path / "u.txt"
    monkeypatch.setenv("TODOIMPL_UMBRELLAS", str(file))
    file.write_text("# umbrellas\nabc12345  # the text-free one\n\n  def67890\n", encoding="utf-8")
    assert registry.ids(tmp_path) == ["abc12345", "def67890"]
    monkeypatch.delenv("TODOIMPL_UMBRELLAS")
    assert registry.path().name == "umbrellas.txt"


def test_registry_fetches_only_open_umbrellas_the_list_missed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake: FakeTodoMcp, client: TodoClient
) -> None:
    body = sample().split("\n", 1)[1]
    mine = fake.seed(None, "Umbrella", body)
    closed = fake.seed(None, "Closed umbrella", body, status="done")
    plain = fake.seed(None, "Just a note", "nothing")
    file = tmp_path / "u.txt"
    ids = [mine[:8], closed[:8], plain[:8], "deadbeef", "listed00"]
    file.write_text("\n".join(ids), encoding="utf-8")
    monkeypatch.setenv("TODOIMPL_UMBRELLAS", str(file))
    found = registry.notes(client, tmp_path, {"listed00"})
    assert [t.id[:8] for t in found] == [mine[:8]]


def test_a_child_with_no_text_is_titled_by_its_repo() -> None:
    lines = [
        "Umbrella: per-repo",
        "- [ ] kuhyx/a (aaaa1111)",
        "## kuhyx/a (aaaa1111)",
        "",
        "## kuhyx/b (bbbb2222)",
        "# ",
        "x",
    ]
    body = "\n".join(lines)
    assert [c.title for c in note.children(body)] == ["kuhyx/a", "kuhyx/b"]
