"""T2535: a card carries its note's images and a title without the image markdown."""

from __future__ import annotations

from typing import TYPE_CHECKING

from board_helpers import Note, ctx
from contract_lib import validate
from todoimpl.board import board

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

DUFS = "https://kuhy-cloud.duckdns.org/todo-images"


def test_t2535_a_card_carries_its_images_and_a_title_without_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TODOIMPL_IMAGES_ROOT", str(tmp_path))
    notes = [
        Note(
            id="aaaaaaaa-0",
            title=f"Fix the logo ![]({DUFS}/f1/1.jpg)",
            repo="beta",
            body=f"![]({tmp_path}/f1/2.png)",
        ),
        Note(id="bbbbbbbb-0", title=f"![]({DUFS}/f2/9.png)", repo="beta"),
        Note(id="cccccccc-0", title="plain", repo="beta"),
    ]
    out = board.build_board(notes, {}, ctx(), "b")
    validate("board", out)
    first, only, plain = out["tasks"]
    assert first["title"] == "Fix the logo"
    assert first["images"] == [{"folder": "f1", "file": "1.jpg"}, {"folder": "f1", "file": "2.png"}]
    assert (only["title"], only["images"]) == ("9.png", [{"folder": "f2", "file": "9.png"}])
    assert "images" not in plain
