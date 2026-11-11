"""Todo images: the session reads dufs links as local files (it cannot log in to the dufs URL)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from todoimpl.newtask import images
from todoimpl.prompts import PromptContext, build

URL = "https://kuhy-cloud.duckdns.org/todo-images"


def test_root_is_the_env_or_the_dufs_folder_under_home() -> None:
    assert images.root({"TODOIMPL_IMAGES_ROOT": "/x/imgs", "HOME": "/h"}) == Path("/x/imgs")
    assert images.root({"HOME": "/h"}) == Path("/h/data/cloud/todo-images")


def test_localize_rewrites_every_dufs_link_and_lists_the_files() -> None:
    text = f"see ![]({URL}/abc-1/one.jpg) and ![x]({URL}/abc-1/two.png)\nkeep https://example.com/a.jpg"
    out, found = images.localize(text, Path("/imgs"))
    assert out == "see ![](/imgs/abc-1/one.jpg) and ![x](/imgs/abc-1/two.png)\nkeep https://example.com/a.jpg"
    assert found == (Path("/imgs/abc-1/one.jpg"), Path("/imgs/abc-1/two.png"))


def test_localize_leaves_unsafe_names_alone() -> None:
    text = f"{URL}/../etc/passwd {URL}/a/b.TOOLONGEXTENSIONX"
    assert images.localize(text, Path("/imgs")) == (text, ())


def test_save_writes_numbered_jpegs_and_answers_their_links(tmp_path: Path) -> None:
    links = images.save((b"\xff\xd8\xffA", b"\xff\xd8\xffB"), tmp_path, "f-1")
    assert links == (f"{URL}/f-1/1.jpg", f"{URL}/f-1/2.jpg")
    assert (tmp_path / "f-1" / "2.jpg").read_bytes() == b"\xff\xd8\xffB"


def test_jpeg_magic() -> None:
    assert images.is_jpeg(b"\xff\xd8\xff\xe0")
    assert not images.is_jpeg(b"\x89PNG")


def test_session_dirs_name_the_root_only_when_it_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TODOIMPL_IMAGES_ROOT", str(tmp_path / "imgs"))
    assert images.session_dirs() == ()
    (tmp_path / "imgs").mkdir()
    assert images.session_dirs() == (tmp_path / "imgs",)


def test_a_prompt_names_local_image_paths_and_tells_the_session_to_read_them(
    ctx: PromptContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TODOIMPL_IMAGES_ROOT", "/imgs")
    body = f"Broken header.\n![]({URL}/f-1/1.jpg)\n![]({URL}/f-1/2.jpg)"
    text = build("implement", replace(ctx, body=body))
    assert URL not in text
    assert "![](/imgs/f-1/1.jpg)" in text
    assert (
        "Images attached to this item: open each with the Read tool: /imgs/f-1/1.jpg, /imgs/f-1/2.jpg" in text
    )


def test_a_prompt_without_images_has_no_image_line(ctx: PromptContext) -> None:
    assert "Images attached" not in build("implement", ctx)
