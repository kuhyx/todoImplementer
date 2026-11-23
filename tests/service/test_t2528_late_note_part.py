"""T2528: a late note added to a repo whose parts all shipped is the repo card's one part at once."""

from __future__ import annotations

import pytest
from servicefakes import Rig
from todoimpl.repotask.ids import repo_card_id
from todoimpl.service import ItemView
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.model import TodoError


def test_t2528_the_new_part_is_found_by_the_next_drive_without_waiting_for_a_refresh(rig: Rig) -> None:
    card = rig.note("demo todos", "## [x] Shipped part\ndone\n")
    assert rig.backend.cache.snapshot().loaded
    view = ItemView(TodoClient(rig.fake.url, rig.fake.token), rig.backend.cache, rig.root)
    view.add_task(
        "kuhyx/demo", "remember to ALSO analyze what went well", "remember to ALSO analyze what went well"
    )
    found = view.get_task(card)  # no cache refresh in between: the drive starts right after the add
    assert card == repo_card_id("kuhyx/demo")
    assert [p.title for p in found.item.parts] == ["remember to ALSO analyze what went well"]


def test_t2528_a_failed_repo_read_leaves_the_poked_refresh(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    rig.note("demo todos", "## [x] Shipped part\ndone\n")

    def down(repo: str) -> None:
        msg = f"{repo}: todo app offline"
        raise TodoError(msg)

    monkeypatch.setattr(rig.backend.cache, "refresh_repo", down)
    view = ItemView(TodoClient(rig.fake.url, rig.fake.token), rig.backend.cache, rig.root)
    assert view.add_task("kuhyx/demo", "late", "late").repo == "kuhyx/demo"
    assert rig.backend.cache._wake.is_set()
