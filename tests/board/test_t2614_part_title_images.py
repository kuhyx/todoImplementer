"""[T2614] A part titled with an image link showed its raw `![](...)` markdown in the card (live C8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from contract_lib import validate
from todoimpl.board.card import Context, build_card
from todoimpl.repotask.model import Part
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.items import Item

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

DUFS = "https://kuhy-cloud.duckdns.org/todo-images/5968f0e1-aaaa/0a7910bf.jpg"


def _part(key: str, title: str) -> Part:
    return Part(key, key[:8], int(key[-1]), title, "b", "medium", None, human=False, held=False)


def test_t2614_part_titles_drop_image_markdown_and_keep_the_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TODOIMPL_IMAGES_ROOT", str(tmp_path))
    parts = (
        _part("aaaa1111-0", f"![]({DUFS})"),
        _part("bbbb2222-0", f"Fix it ![x]({DUFS})"),
        _part("cccc3333-0", "plain"),
    )
    item = Item("deadbeef", 0, "demo", "body", "kuhyx/demo", "todo", None, "kuhy", parts=parts)
    card = build_card(
        CardTask("deadbeef-0", "demo", "body", "kuhyx/demo", "todo", "medium", None, item), None, Context()
    )
    validate("common", card, "task_card")
    only, mixed, plain = card["parts"]
    assert (only["title"], only["title_source"]) == ("0a7910bf.jpg", f"![]({DUFS})")
    assert (mixed["title"], mixed["title_source"]) == ("Fix it", f"Fix it ![x]({DUFS})")
    assert plain["title"] == "plain"
    assert "title_source" not in plain
