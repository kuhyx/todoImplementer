"""Every working prompt carries the wait rules: no self-matching pgrep, no poll loop, no fake life (T2199)."""

from __future__ import annotations

import pytest
from todoimpl.prompts import PromptContext, build
from todoimpl.runner import resume

RULES = (
    "`pgrep -f`",
    "`$(...)`",
    "`flock -n`",
    "when_free.sh",
    "another card",
    "`systemd-run --wait`",
    "`inotifywait`",
    "`gh run watch`",
    "still waiting",
)


@pytest.mark.parametrize("stage", ["implement", "fix", "live_check", "resume_after_kill", "fresh_after_idle"])
def test_t2199_a_working_prompt_names_every_wait_rule(stage: str, ctx: PromptContext) -> None:
    text = build(stage, ctx)
    assert [rule for rule in RULES if rule not in text] == []


def test_t2199_the_self_resume_note_asks_for_an_event_wait_not_a_sleep_loop() -> None:
    assert "short sleeps" not in resume.RESUMED
    assert "`systemd-run --wait`" in resume.RESUMED
