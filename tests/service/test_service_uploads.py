"""Staged attachments: claimed by id with the per-task cap, moved into the dufs folder, swept when stale."""

import os
import re
from pathlib import Path

import pytest
from todoimpl.newtask import images, uploads

URL = re.escape(images.URL)


def stage(base: Path, data: bytes, name: str) -> uploads.Staged:
    left = [data, b""]
    return uploads.stage(lambda _n: left.pop(0), len(data), name, base)


def test_claim_answers_each_staged_file_and_refuses_an_unknown_or_bad_id(tmp_path: Path) -> None:
    one, two = stage(tmp_path, b"a", "a.pdf"), stage(tmp_path, b"bb", "b.zip")
    assert uploads.claim((one.id, two.id), tmp_path) == (one, two)
    gone = "0" * 32
    assert gone in str(uploads.claim((gone,), tmp_path))
    assert isinstance(uploads.claim(("../x",), tmp_path), str)


def test_claim_refuses_a_task_over_the_total_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(uploads, "MAX_TASK", 3)
    one, two = stage(tmp_path, b"ab", "a"), stage(tmp_path, b"cd", "b")
    assert "total over" in str(uploads.claim((one.id, two.id), tmp_path))
    assert uploads.claim((one.id,), tmp_path) == (one,)


def test_sweep_drops_staged_files_older_than_a_day(tmp_path: Path) -> None:
    old = stage(tmp_path, b"a", "a")
    past = old.path.stat().st_mtime - uploads.MAX_AGE - 5
    os.utime(old.path.parent, (past, past))
    fresh = stage(tmp_path, b"b", "b")  # staging sweeps first
    assert not old.path.parent.exists()
    assert fresh.path.exists()
    (tmp_path / "stray.txt").write_text("x")
    uploads.sweep(tmp_path, 10**12)
    assert list(tmp_path.iterdir()) == [tmp_path / "stray.txt"]


def test_attach_moves_each_file_into_the_folder_and_links_images_inline(tmp_path: Path) -> None:
    base = tmp_path / "imgs"
    files = (
        stage(tmp_path / "up", b"%PDF", "Spec [v2].PDF"),
        stage(tmp_path / "up", b"\x89PNG", "shot.png"),
        stage(tmp_path / "up", b"zz", "noext"),
    )
    pdf, png, raw = images.attach(files, base, "f-1")
    pdf_m = re.fullmatch(rf"\[Spec \(v2\)\.PDF\]\({URL}/f-1/([0-9a-f-]+\.pdf)\)", pdf)
    png_m = re.fullmatch(rf"!\[\]\({URL}/f-1/([0-9a-f-]+\.png)\)", png)
    raw_m = re.fullmatch(rf"\[noext\]\({URL}/f-1/([0-9a-f-]+\.bin)\)", raw)
    assert pdf_m
    assert png_m
    assert raw_m
    assert (base / "f-1" / pdf_m.group(1)).read_bytes() == b"%PDF"
    assert (base / "f-1" / png_m.group(1)).read_bytes() == b"\x89PNG"
    assert not files[0].path.parent.exists()
    assert images.localize(pdf, base)[1] == (base / "f-1" / pdf_m.group(1),)


@pytest.mark.parametrize(
    ("name", "ext"),
    [("a.JPG", "jpg"), ("a.tar.gz", "gz"), (".bashrc", "bin"), ("a.", "bin"), ("a.verylongextension", "bin")],
)
def test_extension_of(name: str, ext: str) -> None:
    assert images.extension_of(name) == ext


def test_label_never_breaks_the_link() -> None:
    assert images.label("a]b[c\nd") == "a)b(c d"
    assert images.label(" \n ") == "file"
