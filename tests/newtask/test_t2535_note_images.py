"""T2535: a note's images showed as `![](...)` markdown on the board; now they are links the page can show.

`imagelinks` finds the todo-images links (the dufs URL and the local path forms), strips the markdown from a
title, and reads one image safely: names must match the dufs link's character classes and stay inside
the root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from todoimpl.newtask import imagelinks

if TYPE_CHECKING:
    from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
DUFS = "https://kuhy-cloud.duckdns.org/todo-images"


def test_t2535_links_in_both_forms_in_order_without_repeats(tmp_path: Path) -> None:
    text = (
        f"see ![]({DUFS}/abc-1/1.jpg) and ![x]({tmp_path}/def_2/2.png)\n"
        f"again ![]({DUFS}/abc-1/1.jpg) and a plain {DUFS}/ghi/3.webp link"
    )
    found = [(one["folder"], one["file"]) for one in imagelinks.links(text, tmp_path)]
    assert found == [("abc-1", "1.jpg"), ("def_2", "2.png"), ("ghi", "3.webp")]


def test_t2535_title_loses_its_image_markdown(tmp_path: Path) -> None:
    assert imagelinks.strip_title(f"Fix this ![]({DUFS}/a/1.jpg) now", tmp_path) == "Fix this now"
    assert imagelinks.strip_title(f"![]({tmp_path}/a/1.jpg)", tmp_path) == ""


def test_t2535_read_serves_an_image_and_its_type(tmp_path: Path) -> None:
    (tmp_path / "abc").mkdir()
    (tmp_path / "abc" / "1.png").write_bytes(PNG)
    assert imagelinks.read(tmp_path, "abc", "1.png") == (PNG, "image/png")


@pytest.mark.parametrize(
    ("folder", "file"), [("..", "x.png"), ("abc", "..png"), ("a/b", "1.png"), ("abc", "x")]
)
def test_t2535_read_refuses_bad_names(tmp_path: Path, folder: str, file: str) -> None:
    with pytest.raises(imagelinks.ImageLinkError, match="bad image name"):
        imagelinks.read(tmp_path, folder, file)


def test_t2535_read_refuses_a_symlink_out_of_the_root_and_missing_or_non_image_files(tmp_path: Path) -> None:
    root, outside = tmp_path / "root", tmp_path / "secret.png"
    (root / "abc").mkdir(parents=True)
    outside.write_bytes(PNG)
    (root / "abc" / "leak.png").symlink_to(outside)
    (root / "abc" / "note.png").write_bytes(b"not an image")
    for name, why in (("leak.png", "outside"), ("gone.png", "no such image"), ("note.png", "not an image")):
        with pytest.raises(imagelinks.ImageLinkError, match=why):
            imagelinks.read(root, "abc", name)
