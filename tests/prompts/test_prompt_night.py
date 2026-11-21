"""The standing grant tells every session about kuhy's night: no questions, park them for the morning."""

import pytest
from todoimpl.prompts import PromptContext, build, standing


def test_grant_carries_the_night_rule() -> None:
    assert "22:55" in standing.NIGHT
    assert "05:55" in standing.NIGHT
    assert standing.NIGHT.rstrip() in standing.GRANT


def test_t2431_spec_asks_nothing_at_night(ctx: PromptContext, monkeypatch: pytest.MonkeyPatch) -> None:
    assert "kuhy sleeps" not in build("spec", ctx)  # by day the spec stage grills as before
    monkeypatch.setenv("TODOIMPL_NIGHT", "00:00-23:59")
    text = build("spec", ctx)
    assert "reply only `D:`" in text.split("kuhy sleeps", 1)[1]


@pytest.mark.parametrize("stage", ["plan"])
def test_t2431_the_plan_stage_carries_the_night_rule(stage: str, ctx: PromptContext) -> None:
    assert "22:55" in build(stage, ctx)
