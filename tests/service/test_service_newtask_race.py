"""A new task's card lookup never trusts a fetch that began before the add; an earlier handoff is adopted."""

import threading
from pathlib import Path

import pytest
from servicefakes import Rig
from todoimpl.http.backend import BackendError
from todoimpl.http.newtask import NewTask
from todoimpl.newtask import service as newtask_service
from todoimpl.newtask.service import NewTaskService
from todoimpl.repotask.ids import repo_card_id
from todoimpl.todo_mcp.model import TodoError

REPO = "kuhyx/brand-new"


@pytest.fixture
def images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "todo-images"
    monkeypatch.setenv("TODOIMPL_IMAGES_ROOT", str(root))
    return root


def service(rig: Rig) -> NewTaskService:
    found = rig.backend.new_task_service
    assert isinstance(found, NewTaskService)
    return found


def test_t2046_a_lookup_waits_out_a_fetch_in_flight_and_fetches_after_the_add(
    rig: Rig, images: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = rig.backend.cache
    real = cache._fetch
    entered, release = threading.Event(), threading.Event()

    def stale() -> list[object]:
        before = real()  # read before the add: the snapshot the single-flight refresh hands back
        entered.set()
        release.wait(5)
        return before  # type: ignore[return-value]

    monkeypatch.setattr(cache, "_fetch", stale)
    flight = threading.Thread(target=cache.refresh)
    flight.start()
    assert entered.wait(5)
    monkeypatch.setattr(cache, "_fetch", real)
    monkeypatch.setattr(newtask_service, "_PAUSE_S", 0.0)
    threading.Timer(0.5, release.set).start()
    _, card = service(rig).create(NewTask(REPO, "x", "", ()))
    flight.join(5)
    assert card == repo_card_id(REPO)
    assert any(c.id == card for c in cache.snapshot().tasks)  # the stale fetch landed under the patch


def test_a_card_already_in_the_snapshot_needs_no_fetch(rig: Rig, images: Path) -> None:
    note8 = service(rig).add(NewTask(REPO, "x", "", ()))
    rig.backend.cache.refresh()
    calls: list[int] = []

    def counted() -> list[object]:
        calls.append(1)
        return []

    rig.backend.cache._fetch = counted  # type: ignore[assignment]
    assert service(rig).card_of(note8, NewTask(REPO, "x", "", ())) == repo_card_id(REPO)
    assert calls == []


def test_adopt_finds_the_open_part_this_very_task_became(rig: Rig, images: Path) -> None:
    task = NewTask(REPO, "Stalled thing", "### what\nFinish the manual Claude Code session abc-123", ())
    assert service(rig).adopt(task, "session abc-123") is None
    note8, card = service(rig).create(task)
    assert service(rig).adopt(task, "session abc-123") == (note8, card)
    with pytest.raises(BackendError, match="already has an open part"):  # same title, someone else's
        service(rig).adopt(task, "session other")


def test_adopt_skips_a_done_part(rig: Rig, images: Path) -> None:
    task = NewTask(REPO, "Stalled thing", "session abc-123", ())
    note8, _ = service(rig).create(task)
    note = next(n for k, n in rig.fake.store.notes.items() if k.startswith(note8))
    note.text = note.text.replace("## Stalled thing", "## [x] Stalled thing")
    assert service(rig).adopt(task, "session abc-123") is None


def test_a_todo_app_error_while_reading_the_repo_is_upstream_unavailable(
    rig: Rig, images: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(_repo: str) -> object:
        raise TodoError("todo MCP is down")

    monkeypatch.setattr(rig.backend.cache, "refresh_repo", down)
    with pytest.raises(BackendError) as caught:
        service(rig).create(NewTask(REPO, "x", "", ()))
    assert caught.value.code == "upstream_unavailable"


def test_adopt_reports_a_todo_app_error_as_upstream_unavailable(
    rig: Rig, images: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(**_: object) -> object:
        raise TodoError("todo MCP is down")

    monkeypatch.setattr(service(rig)._client, "list_tasks", down)
    with pytest.raises(BackendError, match="down"):
        service(rig).adopt(NewTask(REPO, "x", "", ()), "session s")


def test_adopt_of_a_part_whose_card_never_shows_is_none(
    rig: Rig, images: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = NewTask(REPO, "Stalled thing", "session abc-123", ())
    service(rig).create(task)
    monkeypatch.setattr(service(rig), "card_of", lambda *_: None)
    assert service(rig).adopt(task, "session abc-123") is None
