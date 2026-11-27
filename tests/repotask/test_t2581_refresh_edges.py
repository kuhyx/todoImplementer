"""T2581 edges: a plain card has no parts to re-read; an unreachable todo app keeps the drive's parts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from todoimpl.runner import partrefresh
from todoimpl.todo_mcp.model import TodoError

if TYPE_CHECKING:
    from todoimpl.runner.pipeline import Driver


def _client_down(_card: str) -> None:
    raise TodoError("todo app offline")


def _driver(parts: tuple[object, ...], nudge: object = False) -> Driver:
    item = SimpleNamespace(parts=parts)
    ctx = SimpleNamespace(
        run_dir=Path("/nonexistent/abcd1234-0"), client=SimpleNamespace(get_task=_client_down)
    )
    return cast("Driver", SimpleNamespace(item=item, ctx=ctx, state=SimpleNamespace(extra={"nudge": nudge})))


def test_t2581_a_plain_card_keeps_its_nudge() -> None:
    assert partrefresh.before_turn(_driver((), nudge="note"), "implement") == "note"


def test_t2581_an_unreachable_todo_app_keeps_the_parts_and_the_turn_goes_on() -> None:
    parts = ("a part",)
    driver = _driver(parts)
    assert partrefresh.before_turn(driver, "implement") is False
    assert driver.item.parts is cast("object", parts)  # the drive keeps its own parts
    assert partrefresh.before_turn(_driver(("a part",), nudge=True), "plan") is True
