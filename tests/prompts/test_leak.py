"""T1885: board sessions must not leave probe notes in kuhy's real todo app."""

from __future__ import annotations

import pytest
from todoimpl.prompts import PromptContext, build


@pytest.mark.parametrize("stage", ["implement", "live_check", "fix", "resume_after_kill", "fresh_after_idle"])
def test_t1885_work_stages_forbid_probe_notes_in_the_real_todo(stage: str, ctx: PromptContext) -> None:
    text = build(stage, ctx)
    assert "Never write test or probe notes into kuhy's real todo app" in text
    assert "fake MCP or a scratch data dir under /run/ab12cd34" in text
    assert "abandon any you leaked before `D:`" in text
