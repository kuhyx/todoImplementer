"""A failing free worker is coached (prompt, context, smaller task), not replaced by its manager."""

from __future__ import annotations

from pathlib import Path

from todoimpl.prompts import PromptContext, build, coach
from todoimpl.prompts import tier as texts


def test_t2054_the_umbrella_manager_diagnoses_and_coaches_before_doing_the_edits(ctx: PromptContext) -> None:
    text = build("manager", ctx)
    assert "DIAGNOSE" in text
    assert "textgate-rework/SKILL.md" in text
    assert "freeworker command again" in text
    assert "3 coached attempts" in text
    assert 'phase "prompt"' in text
    assert "CHILD kuhyx/<repo>: coached <n>" in text
    assert "never do the edits yourself before" in text


def test_t2054_the_cheap_tier_manager_coaches_the_same_way() -> None:
    text = texts.manager(Path("/wt/x"), Path("/run/r1"), "W-CMD", "kuhyx/x")
    assert "DIAGNOSE" in text
    assert "textgate/SKILL.md" in text
    assert "3 coached attempts" in text
    assert 'phase "prompt"' in text


def test_t2054_the_textgate_rules_say_a_proper_noun_in_the_ui_is_not_an_excuse() -> None:
    assert coach.is_textgate("Make x text-free (textgate-rework)")
    assert coach.is_textgate("Scan textgate: 1 items")
    assert not coach.is_textgate("Fix the login bug")
    assert "proper noun" in coach.TEXTGATE_RULES
    assert "scan still lists" in coach.TEXTGATE_RULES
    assert coach.task_text("body", textgate=False) == "body"
    assert coach.task_text("body", textgate=True).startswith(coach.TEXTGATE_RULES)
    assert coach.task_text("body", textgate=True).endswith("body")
