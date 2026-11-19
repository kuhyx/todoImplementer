"""New task with numbered images: `[Image #N]` above each image link, uploads and inline bytes alike."""

import re
from pathlib import Path

import pytest
from servicefakes import Rig
from todoimpl.http.backend import BackendError
from todoimpl.http.newtask import NewTask
from todoimpl.newtask import images as dufs
from todoimpl.newtask import uploads
from todoimpl.newtask.service import NewTaskService

PNG = b"\x89PNG\r\n\x1a\n" + b"png"
JPEG = b"\xff\xd8\xff\xe0jpeg"
URL = re.escape(dufs.URL)


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setenv("TODOIMPL_IMAGES_ROOT", str(tmp_path / "todo-images"))
    monkeypatch.setenv("TODOIMPL_UPLOADS_ROOT", str(tmp_path / "uploads"))
    return tmp_path / "todo-images", tmp_path / "uploads"


def stage(data: bytes, name: str) -> str:
    left = [data, b""]
    return uploads.stage(lambda _n: left.pop(0), len(data), name, uploads.root()).id


def create(rig: Rig, task: NewTask) -> str:
    found = rig.backend.new_task_service
    assert isinstance(found, NewTaskService)
    note, _ = found.create(task)
    (stored,) = [n for n in rig.fake.store.notes.values() if n.id.startswith(note)]
    return stored.text


def test_t2321_images_are_numbered_in_order_above_their_links(rig: Rig, roots: tuple[Path, Path]) -> None:
    pictures, staging = roots
    shot, pdf = stage(PNG, "shot.png"), stage(b"%PDF-1", "spec.pdf")
    text = create(
        rig, NewTask("kuhyx/fresh", "Fix it", "[Image #2] wraps, see [Image #1]", (JPEG, shot), (pdf,))
    )
    found = re.findall(rf"\[Image #(\d)\]\n!\[\]\({URL}/([\w-]+)/(\d\.\w+)\)", text)
    assert [(n, name) for n, _, name in found] == [("1", "1.jpg"), ("2", "2.png")]
    folder = pictures / found[0][1]
    assert (folder / "1.jpg").read_bytes() == JPEG
    assert (folder / "2.png").read_bytes() == PNG
    assert re.search(rf"\[spec\.pdf\]\({URL}/[\w-]+/[\w-]+\.pdf\)", text)
    assert list(staging.iterdir()) == []


def test_t2321_the_session_reads_each_number_next_to_its_local_path(
    rig: Rig, roots: tuple[Path, Path]
) -> None:
    pictures, _ = roots
    text = create(rig, NewTask("kuhyx/fresh", "Fix it", "see [Image #1]", (stage(PNG, "a.png"),)))
    (folder,) = pictures.iterdir()
    local, paths = dufs.localize(text, pictures)  # what the prompt builder hands the session
    assert paths == (folder / "1.png",)
    assert f"see [Image #1]\n\n[Image #1]\n![]({folder / '1.png'})" in local


def test_t2321_a_staged_file_that_is_not_an_image_refuses_and_writes_nothing(
    rig: Rig, roots: tuple[Path, Path]
) -> None:
    pictures, staging = roots
    with pytest.raises(BackendError) as caught:
        create(rig, NewTask("kuhyx/fresh", "Fix it", "", (JPEG, stage(b"%PDF-1", "x.png"))))
    assert caught.value.message == "image 2 is not a PNG, JPEG, WebP or GIF"
    assert not pictures.exists()
    assert len(list(staging.iterdir())) == 1
