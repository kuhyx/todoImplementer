"""New task from the board: images in the dufs folder, linked from the note, the card on the board at once."""

import re
from dataclasses import replace
from pathlib import Path

import pytest
from servicefakes import Rig
from todoimpl.http.backend import BackendError
from todoimpl.http.newtask import NewTask
from todoimpl.newtask import uploads
from todoimpl.newtask.service import NewTaskService, _holds
from todoimpl.repotask.ids import repo_card_id, repo_human_id
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.items import Item
from todoimpl.todo_mcp.model import TodoError

JPEG = b"\xff\xd8\xff\xe0jpeg-bytes"
LINK = re.compile(r"!\[\]\(https://kuhy-cloud\.duckdns\.org/todo-images/([A-Za-z0-9_-]+)/([0-9]+\.jpg)\)")


@pytest.fixture
def images(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "todo-images"
    monkeypatch.setenv("TODOIMPL_IMAGES_ROOT", str(root))
    return root


def service(rig: Rig) -> NewTaskService:
    found = rig.backend.new_task_service
    assert isinstance(found, NewTaskService)
    return found


def test_a_new_repo_gets_a_note_with_linked_images_and_its_card_at_once(rig: Rig, images: Path) -> None:
    note, card = service(rig).create(
        NewTask("kuhyx/fresh", "Fix the header", "It wraps.", (JPEG, JPEG + b"2"))
    )
    assert card == repo_card_id("kuhyx/fresh")
    assert rig.backend.task(card) is not None  # the cache was refreshed before the answer
    (stored,) = [n for n in rig.fake.store.notes.values() if n.id.startswith(note)]
    links = LINK.findall(stored.text)
    assert [name for _, name in links] == ["1.jpg", "2.jpg"]
    (folder,) = {f for f, _ in links}
    assert (images / folder / "1.jpg").read_bytes() == JPEG
    assert (images / folder / "2.jpg").read_bytes() == JPEG + b"2"
    assert "It wraps." in stored.text


def test_each_task_gets_a_fresh_folder_and_no_images_means_no_folder(rig: Rig, images: Path) -> None:
    make = service(rig)
    make.create(NewTask("kuhyx/a", "one", "", (JPEG,)))
    make.create(NewTask("kuhyx/a", "two", "", (JPEG,)))
    make.create(NewTask("kuhyx/a", "three", "text only", ()))
    assert len(list(images.iterdir())) == 2


def test_a_second_part_joins_the_repo_card(rig: Rig, images: Path) -> None:
    first = rig.note(title="older part", repo="kuhyx/demo")
    _, card = service(rig).create(NewTask("kuhyx/demo", "newer part", "", ()))
    assert card == first
    detail = rig.backend.task(card)
    assert detail is not None
    assert "newer part" in detail["body"]


def test_a_manual_title_answers_the_human_card(rig: Rig, images: Path) -> None:
    _, card = service(rig).create(NewTask("kuhyx/demo", "MANUAL WORK REQUIRED: plug it in", "", ()))
    assert card == repo_human_id("kuhyx/demo")


def test_an_open_part_with_the_same_title_is_a_conflict_and_writes_nothing(rig: Rig, images: Path) -> None:
    rig.note(title="Fix the header", repo="kuhyx/demo")
    with pytest.raises(BackendError) as caught:
        service(rig).create(NewTask("kuhyx/demo", "Fix the header", "", (JPEG,)))
    assert caught.value.code == "conflict"
    assert not images.exists()


def test_the_todo_app_failing_is_upstream_unavailable(
    rig: Rig, images: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*_a: object, **_k: object) -> None:
        raise TodoError("connection refused")

    monkeypatch.setattr(service(rig)._client, "list_tasks", down)
    with pytest.raises(BackendError) as caught:
        service(rig).create(NewTask("kuhyx/demo", "x", "", ()))
    assert caught.value.code == "upstream_unavailable"


def test_check_twin_answers_before_anything_is_written(
    rig: Rig, images: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig.note(title="Fix the header", repo="kuhyx/demo")
    make = service(rig)
    make.check_twin(NewTask("kuhyx/demo", "Another title", "", ()))
    with pytest.raises(BackendError) as twin:
        make.check_twin(NewTask("kuhyx/demo", "Fix the header", "", ()))
    assert twin.value.code == "conflict"

    def down(*_a: object, **_k: object) -> None:
        raise TodoError("connection refused")

    monkeypatch.setattr(make._client, "list_tasks", down)
    with pytest.raises(BackendError) as broken:
        make.check_twin(NewTask("kuhyx/demo", "x", "", ()))
    assert broken.value.code == "upstream_unavailable"


def test_a_done_card_never_holds_the_new_section() -> None:
    item = Item("abcd1234-full-id", 0, "Fix it", "", "kuhyx/demo", "done", None)
    done = CardTask("abcd1234-0", "Fix it", "", "kuhyx/demo", "done", "medium", None, item)
    assert not _holds(done, "abcd1234", "Fix it")
    assert _holds(replace(done, status="todo"), "abcd1234", "Fix it")


def test_a_card_missing_after_the_add_is_not_found(
    rig: Rig, images: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rig.backend.cache, "refresh", lambda: None)
    with pytest.raises(BackendError) as caught:
        service(rig).create(NewTask("kuhyx/brand-new", "x", "", ()))
    assert caught.value.code == "not_found"


def test_staged_files_are_moved_into_the_folder_and_linked_by_kind(rig: Rig, images: Path) -> None:
    def stage(data: bytes, name: str) -> str:
        left = [data, b""]
        return uploads.stage(lambda _n: left.pop(0), len(data), name, uploads.root()).id

    pdf, png = stage(b"%PDF-1", "spec.pdf"), stage(b"\x89PNG", "shot.png")
    note, _ = service(rig).create(NewTask("kuhyx/fresh", "Read it", "", (JPEG,), files=(pdf, png)))
    (stored,) = [n for n in rig.fake.store.notes.values() if n.id.startswith(note)]
    url = re.escape("https://kuhy-cloud.duckdns.org/todo-images/")
    assert re.search(rf"\[spec\.pdf\]\({url}[\w-]+/[\w-]+\.pdf\)", stored.text)
    assert re.search(rf"!\[\]\({url}[\w-]+/[\w-]+\.png\)", stored.text)
    (folder,) = images.iterdir()
    assert sorted(p.read_bytes() for p in folder.iterdir()) == sorted([JPEG, b"%PDF-1", b"\x89PNG"])


def test_an_unknown_staged_file_is_a_bad_request_and_writes_nothing(rig: Rig, images: Path) -> None:
    with pytest.raises(BackendError) as caught:
        service(rig).create(NewTask("kuhyx/fresh", "Read it", "", (), files=("0" * 32,)))
    assert caught.value.code == "bad_request"
    assert not images.exists()
