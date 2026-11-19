"""Send to Claude with images: staged uploads land in the run's inbox folder and the note names each path."""

import re
from pathlib import Path

import pytest
from servicefakes import Rig
from todoimpl.board.state import run_dir
from todoimpl.http.backend import BackendError
from todoimpl.newtask import noteimages, uploads
from todoimpl.runner.scheduler import RunnerError

PNG = b"\x89PNG\r\n\x1a\n" + b"png-bytes"
JPEG = b"\xff\xd8\xff\xe0jpeg"
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 "
GIF = b"GIF89a-gif"


@pytest.fixture
def staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "uploads"
    monkeypatch.setenv("TODOIMPL_UPLOADS_ROOT", str(base))
    return base


def stage(base: Path, data: bytes, name: str = "shot.png") -> str:
    left = [data, b""]
    return uploads.stage(lambda _n: left.pop(0), len(data), name, base).id


def test_t2320_kind_reads_the_magic_bytes_never_the_name() -> None:
    assert [noteimages.kind(d) for d in (PNG, JPEG, WEBP, GIF, b"GIF87a")] == [
        "png",
        "jpg",
        "webp",
        "gif",
        "gif",
    ]
    assert noteimages.kind(b"%PDF-1.7") is None
    assert noteimages.kind(b"RIFF\x00\x00\x00\x00WAVE") is None


def test_t2320_send_copies_each_image_into_the_inbox_and_names_its_path(rig: Rig, staging: Path) -> None:
    rig.run("t1", "implement", session_id="s")
    one, two = stage(staging, PNG), stage(staging, JPEG, "b.jpg")
    rig.backend.send("t1", "[Image #1] is cut off, [Image #2] is fine", (one, two))
    ((_, card, note),) = rig.scheduler.calls
    inbox = run_dir(rig.root, "t1") / "inbox"
    first, second = sorted(inbox.iterdir(), key=lambda p: p.name[-5:])
    assert re.fullmatch(r"[0-9]+-1\.png", first.name)
    assert re.fullmatch(r"[0-9]+-2\.jpg", second.name)
    assert (first.read_bytes(), second.read_bytes()) == (PNG, JPEG)
    assert card == "t1"
    assert note == (
        "[Image #1] is cut off, [Image #2] is fine\n\n"
        "(runner) kuhy attached images; open each with the Read tool:\n"
        f"[Image #1] = {first}\n[Image #2] = {second}"
    )
    assert first.is_absolute()
    assert list(staging.iterdir()) == []  # the staged copies are gone once the note is queued


def test_t2320_a_refused_send_keeps_the_staged_files_and_drops_the_copies(rig: Rig, staging: Path) -> None:
    rig.run("t1", "implement", session_id="s")
    one = stage(staging, PNG)
    rig.scheduler.failure = RunnerError("The run is done: nothing to send to", "disabled")
    with pytest.raises(BackendError):
        rig.backend.send("t1", "see [Image #1]", (one,))
    assert list((run_dir(rig.root, "t1") / "inbox").iterdir()) == []
    rig.scheduler.failure = None
    rig.backend.send("t1", "see [Image #1]", (one,))  # the page's retry sends the same id
    assert len(rig.scheduler.calls) == 1


@pytest.mark.parametrize(
    ("data", "why"),
    [(b"%PDF-1.7", "is not a PNG, JPEG, WebP or GIF"), (PNG + b"0" * 64, "is over")],
)
def test_t2320_a_bad_image_refuses_the_send_and_copies_nothing(
    rig: Rig, staging: Path, monkeypatch: pytest.MonkeyPatch, data: bytes, why: str
) -> None:
    monkeypatch.setattr(noteimages, "MAX_IMAGE", 32)
    rig.run("t1", "implement", session_id="s")
    good, bad = stage(staging, PNG), stage(staging, data)
    with pytest.raises(BackendError) as caught:
        rig.backend.send("t1", "x", (good, bad))
    assert caught.value.code == "bad_request"
    assert f"image 2 {why}" in caught.value.message
    assert rig.scheduler.calls == []
    assert not (run_dir(rig.root, "t1") / "inbox").exists()
    assert len(list(staging.iterdir())) == 2


def test_t2320_a_gone_upload_is_a_bad_request(rig: Rig, staging: Path) -> None:
    with pytest.raises(BackendError) as caught:
        rig.backend.send("t1", "x", ("0" * 32,))
    assert "attach it again" in caught.value.message


def test_t2320_a_model_command_carries_the_images_to_the_rerun(rig: Rig, staging: Path) -> None:
    rig.run("t1", "implement", session_id="s")
    one = stage(staging, GIF, "a.gif")
    rig.backend.send("t1", "rerun on opus", (one,))
    ((kind, card, model, rest),) = rig.scheduler.calls
    assert (kind, card, model) == ("set_model", "t1", "claude-opus-5-5")
    assert rest.startswith("(runner) kuhy attached images; open each with the Read tool:\n[Image #1] = /")
    assert rest.endswith("-1.gif")


def test_t2322_an_inline_image_is_written_like_an_upload(rig: Rig, staging: Path) -> None:
    rig.run("t1", "implement", session_id="s")
    rig.backend.send("t1", "see [Image #1]", (WEBP,))
    (path,) = (run_dir(rig.root, "t1") / "inbox").iterdir()
    assert path.read_bytes() == WEBP
    assert rig.scheduler.calls[0][2].endswith(f"[Image #1] = {path}")


def test_t2320_no_images_leaves_the_note_and_the_run_dir_alone(rig: Rig, staging: Path) -> None:
    rig.run("t1", "implement", session_id="s")
    rig.backend.send("t1", "plain")
    assert rig.scheduler.calls == [("send", "t1", "plain")]
    assert not (run_dir(rig.root, "t1") / "inbox").exists()
