"""A running card's "updated" is its last real activity, not the last state.json save (T2404)."""

from __future__ import annotations

from dataclasses import replace

from board_helpers import NOW, Note, ctx, run
from todoimpl.board.card import build_card

LATE = NOW + 900.0


def _card(stage: str, seen: dict[str, float | None], *, live: bool = True) -> dict[str, object]:
    base = ctx(live=("c59d2588-0",) if live else ())
    return build_card(Note(), run(stage=stage), replace(base, activity=seen.get))


def test_t2404_a_running_card_shows_its_newest_activity() -> None:
    assert _card("implement", {"c59d2588-0": LATE})["updated"] == LATE


def test_t2404_activity_older_than_the_save_does_not_move_the_time_back() -> None:
    assert _card("implement", {"c59d2588-0": NOW - 50})["updated"] == NOW


def test_t2404_a_running_card_with_no_activity_keeps_its_save_time() -> None:
    assert _card("implement", {})["updated"] == NOW


def test_t2404_a_card_that_is_not_running_keeps_its_save_time() -> None:
    assert _card("failed", {"c59d2588-0": LATE}, live=False)["updated"] == NOW


def test_t2404_a_card_without_a_run_has_no_time() -> None:
    assert build_card(Note(), None, ctx())["updated"] is None
