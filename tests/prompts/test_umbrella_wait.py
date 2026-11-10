"""The umbrella manager waits for its workers inside the turn; ending the turn early escalates the round."""

from __future__ import annotations

from todoimpl.prompts import PromptContext, build


def test_t1883_the_manager_polls_in_short_calls_and_never_ends_its_turn_early(ctx: PromptContext) -> None:
    text = build("manager", ctx)
    assert "never end your turn" in text
    assert "Never use Monitor" in text
    assert "kill -0" in text
    assert "never `pgrep -f" in text
